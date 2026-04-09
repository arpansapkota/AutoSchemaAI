"""
ui/tab_profiling.py
-------------------
Renders the 🔬 Data Profiling tab.

Three profiling modes:
  1. Manual     — user enters every field via form inputs
  2. Code logic — deterministic regex / pandas detection
  3. AI agent   — multi-agent profiling on Groq

Parse options are no longer shown here; the tab receives an already-parsed
DataFrame and separator from app.py.
"""

import pandas as pd
import streamlit as st

from core.config import GROQ_MODEL
from profiling.detectors import build_code_profile
from profiling.agent import run_agent
from ssis.type_mapper import build_ssis_xml, build_create_table_sql


def _safe_base_name(file_name: str) -> str:
    return file_name.rsplit(".", 1)[0] if "." in file_name else file_name


# ── Shared result renderer ─────────────────────────────────────────────────────

def _render_profile_results(profile: dict, df: pd.DataFrame, file_name: str) -> None:
    """Display file metadata, per-column profile table, null heatmap, SSIS export and T-SQL export."""
    fm = profile.get("file_metadata", {})
    cols_data = profile.get("columns", [])
    file_stub = _safe_base_name(file_name)

    # File metadata
    st.markdown("#### File metadata")
    fm1, fm2, fm3 = st.columns(3)
    fm1.metric("Field delimiter", fm.get("field_delimiter", "—"))
    fm2.metric("Line ending", fm.get("line_ending", "—"))
    fm3.metric("Text delimiter", fm.get("text_delimiter", "—"))
    fm4, fm5, fm6 = st.columns(3)
    fm4.metric("Has headers", "Yes" if fm.get("has_headers") else "No")
    fm5.metric("Encoding", fm.get("encoding", "—"))
    fm6.metric("File size", f"{fm.get('file_size_kb', 0)} KB")

    st.divider()

    # Dataset summary
    st.markdown("#### Dataset summary")
    total_cells = df.shape[0] * df.shape[1]
    total_nulls = int(df.isna().sum().sum())
    total_dupes = int(df.duplicated().sum())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total cells", f"{total_cells:,}")
    m2.metric(
        "Missing values",
        f"{total_nulls:,}",
        delta=f"{(total_nulls / total_cells * 100):.1f}% of total" if total_cells else "0.0% of total",
        delta_color="inverse",
    )
    m3.metric("Duplicate rows", f"{total_dupes:,}")
    m4.metric("Memory usage", f"{df.memory_usage(deep=True).sum()/1024:.1f} KB")

    ai_data_profile = st.session_state.get("ai_data_profile")
    if ai_data_profile:
        st.caption(
            f"AI data profile: missing={ai_data_profile.get('missing_values', 0):,}, "
            f"duplicates={ai_data_profile.get('duplicate_rows', 0):,}, "
            f"memory={ai_data_profile.get('memory_usage_kb', 0)} KB"
        )

    validation_summary = profile.get("validation_summary") or st.session_state.get("ai_validation_summary")
    if validation_summary:
        st.markdown("#### Validation summary")
        v1, v2 = st.columns(2)
        v1.metric("Validation status", str(validation_summary.get("status", "approved")).capitalize())
        v2.metric("Issues found", int(validation_summary.get("issues_found", 0)))

    st.divider()

    # Per-column profile table
    st.markdown("#### Per-column profile")
    if cols_data:
        display_cols = [
            "column_name", "pandas_dtype", "predicted_type", "predicted_size",
            "ssis_data_type", "validation_status",
            "non_null_count", "null_count", "null_pct",
            "unique_count", "avg_length",
        ]
        rename_map = {
            "column_name": "Column",
            "pandas_dtype": "Pandas type",
            "predicted_type": "Predicted type",
            "predicted_size": "Predicted size",
            "ssis_data_type": "SSIS data type",
            "validation_status": "Validation",
            "non_null_count": "Non-null",
            "null_count": "Nulls",
            "null_pct": "Null %",
            "unique_count": "Unique values",
            "avg_length": "Avg length (chars)",
        }
        prof_df = pd.DataFrame(cols_data)
        existing = [c for c in display_cols if c in prof_df.columns]
        prof_df = prof_df[existing].rename(columns=rename_map)
        st.dataframe(prof_df, width="stretch", hide_index=True)
    else:
        st.warning("No column profile data available.")

    # Missing value heatmap
    if total_nulls > 0:
        st.divider()
        st.markdown("**Missing value map** (red = missing)")
        null_map = df.isna().astype(int)
        styled = null_map.head(100).style.map(
            lambda v: "background-color: #f28b82;" if v == 1 else ""
        )
        st.dataframe(styled, width="stretch", height=300)
        if len(df) > 100:
            st.caption("Showing first 100 rows only.")

    st.divider()

    # SSIS export
    st.markdown("#### Export as SSIS metadata")
    st.caption(
        "Downloads a `DTS:ConnectionManager` XML fragment — "
        "paste into any `.dtsx` package."
    )
    ssis_xml = build_ssis_xml(profile, file_name)
    with st.expander("Preview SSIS XML", expanded=False):
        st.code(ssis_xml, language="xml")

    st.download_button(
        "⬇️ Download SSIS metadata (.xml)",
        data=ssis_xml.encode("utf-8"),
        file_name=f"{file_stub}_ssis_metadata.xml",
        mime="application/xml",
        key=f"profiling_download_ssis_{file_stub}",
    )

    st.divider()

    # T-SQL export
    st.markdown("#### Export as T-SQL table")
    st.caption(
        "Generates a SQL Server `CREATE TABLE` statement from the validated schema."
    )
    sql_text = build_create_table_sql(profile, file_name=file_name)
    with st.expander("Preview CREATE TABLE", expanded=False):
        st.code(sql_text, language="sql")

    st.download_button(
        "⬇️ Download CREATE TABLE (.sql)",
        data=sql_text.encode("utf-8"),
        file_name=f"{file_stub}_create_table.sql",
        mime="text/sql",
        key=f"profiling_download_sql_{file_stub}",
    )


# ── Mode 1: Manual entry ───────────────────────────────────────────────────────

def _render_manual_mode(
    df: pd.DataFrame, raw_bytes: bytes, raw_text: str,
    file_name: str, sep: str, has_header: bool, encoding: str,
) -> None:
    st.info(
        "Manually enter the type information for each field. "
        "Use this when you want full control over the output schema."
    )

    if st.button("▶️ Build manual profile", type="primary", key="run_manual_profile_btn"):
        st.session_state["manual_df"] = df
        st.session_state["manual_profile"] = build_code_profile(
            df, raw_bytes, raw_text, file_name, sep, has_header, encoding
        )

    if st.session_state.get("manual_profile"):
        st.divider()
        render_df = st.session_state.get("manual_df", df)
        _render_profile_results(st.session_state["manual_profile"], render_df, file_name)


# ── Mode 2: Code logic ─────────────────────────────────────────────────────────

def _render_code_mode(
    df: pd.DataFrame, raw_bytes: bytes, raw_text: str,
    file_name: str, sep: str, has_header: bool, encoding: str,
) -> None:
    st.info(
        "Profile fields are detected automatically using deterministic "
        "regex and pandas logic — no AI involved."
    )
    if st.button("▶️ Run code-logic profiling", type="primary", key="run_code_profile_btn"):
        with st.spinner("Analysing…"):
            profile = build_code_profile(
                df, raw_bytes, raw_text, file_name, sep, has_header, encoding
            )
        st.session_state["code_profile"] = profile

    if st.session_state.get("code_profile"):
        st.divider()
        _render_profile_results(st.session_state["code_profile"], df, file_name)


# ── Mode 3: Multi-agent AI ─────────────────────────────────────────────────────

def _render_ai_mode(
    df: pd.DataFrame, raw_bytes: bytes, raw_text: str,
    file_name: str, sep: str, has_header: bool, encoding: str,
) -> None:
    st.info(
        f"Profile fields are predicted by **{GROQ_MODEL}** on Groq "
        "using a multi-agent flow: file profiling, data profiling, schema detection, "
        "validation, and output generation."
    )
    if st.button("▶️ Run multi-agent profiling", type="primary", key="run_multiagent_profile_btn"):
        st.session_state["ai_profile"] = None
        st.session_state.pop("ai_data_profile", None)
        st.session_state.pop("ai_validation_summary", None)
        st.session_state.pop("ai_ssis_xml", None)
        st.session_state.pop("ai_create_table_sql", None)

        try:
            profile = run_agent(
                df, raw_bytes, raw_text, file_name, sep, has_header, encoding
            )
            st.session_state["ai_profile"] = profile
        except Exception as exc:
            st.error(f"Agent error: {exc}")

    if st.session_state.get("ai_profile"):
        st.divider()
        _render_profile_results(st.session_state["ai_profile"], df, file_name)


# ── Main entry point ───────────────────────────────────────────────────────────

def render(
    df: pd.DataFrame,
    raw_bytes: bytes,
    raw_text: str,
    file_name: str,
    sep: str,
    has_header: bool,
    encoding: str,
) -> None:
    """
    Full Data Profiling tab renderer.
    Receives an already-parsed DataFrame — no parse options shown here.
    """
    st.subheader("Data profiling")

    st.markdown("#### Choose profiling method")
    mode = st.radio(
        "Profiling method",
        options=[
            "1 — Manual entry",
            "2 — Code logic (auto-detect)",
            "3 — Multi-agent AI",
        ],
        label_visibility="collapsed",
        horizontal=True,
        key="profiling_mode_radio",
    )

    st.divider()

    if st.session_state.get("_last_mode") != mode:
        for key in (
            "manual_profile", "code_profile", "ai_profile",
            "ai_data_profile", "ai_validation_summary",
            "ai_ssis_xml", "ai_create_table_sql",
        ):
            st.session_state.pop(key, None)
        st.session_state["_last_mode"] = mode

    kwargs = dict(
        df=df, raw_bytes=raw_bytes, raw_text=raw_text,
        file_name=file_name, sep=sep,
        has_header=has_header, encoding=encoding,
    )

    if mode.startswith("1"):
        _render_manual_mode(**kwargs)
    elif mode.startswith("2"):
        _render_code_mode(**kwargs)
    elif mode.startswith("3"):
        _render_ai_mode(**kwargs)
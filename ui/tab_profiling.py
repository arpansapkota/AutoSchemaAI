"""
ui/tab_profiling.py
-------------------
Renders the 🔬 Data Profiling tab.

Three profiling modes:
  1. Manual     — user enters every field via form inputs
  2. Code logic — deterministic regex / pandas detection
  3. AI agent   — llama-3.3-70b-versatile via Groq tool-calling loop

Parse options are no longer shown here; the tab receives an already-parsed
DataFrame and separator from app.py.
"""

import pandas as pd
import streamlit as st

from core.config import GROQ_MODEL
from profiling.detectors import build_code_profile
from profiling.agent import run_agent
from ssis.type_mapper import build_ssis_xml


# ── Shared result renderer ─────────────────────────────────────────────────────

def _render_profile_results(profile: dict, df: pd.DataFrame, file_name: str) -> None:
    """Display file metadata, per-column profile table, null heatmap and SSIS export."""
    fm        = profile.get("file_metadata", {})
    cols_data = profile.get("columns", [])

    # File metadata
    st.markdown("#### File metadata")
    fm1, fm2, fm3 = st.columns(3)
    fm1.metric("Field delimiter", fm.get("field_delimiter", "—"))
    fm2.metric("Line ending",     fm.get("line_ending",     "—"))
    fm3.metric("Text delimiter",  fm.get("text_delimiter",  "—"))
    fm4, fm5, fm6 = st.columns(3)
    fm4.metric("Has headers", "Yes" if fm.get("has_headers") else "No")
    fm5.metric("Encoding",    fm.get("encoding", "—"))
    fm6.metric("File size",   f"{fm.get('file_size_kb', 0)} KB")

    st.divider()

    # Dataset summary
    st.markdown("#### Dataset summary")
    total_cells = df.shape[0] * df.shape[1]
    total_nulls = int(df.isna().sum().sum())
    total_dupes = int(df.duplicated().sum())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total cells",    f"{total_cells:,}")
    m2.metric("Missing values", f"{total_nulls:,}",
              delta=f"{total_nulls/total_cells*100:.1f}% of total", delta_color="inverse")
    m3.metric("Duplicate rows", f"{total_dupes:,}")
    m4.metric("Memory usage",   f"{df.memory_usage(deep=True).sum()/1024:.1f} KB")

    st.divider()

    # Per-column profile table
    st.markdown("#### Per-column profile")
    if cols_data:
        display_cols = [
            "column_name", "pandas_dtype", "predicted_type", "predicted_size",
            "ssis_data_type", "non_null_count", "null_count", "null_pct",
            "unique_count", "avg_length",
        ]
        rename_map = {
            "column_name":    "Column",
            "pandas_dtype":   "Pandas type",
            "predicted_type": "Predicted type",
            "predicted_size": "Predicted size",
            "ssis_data_type": "SSIS data type",
            "non_null_count": "Non-null",
            "null_count":     "Nulls",
            "null_pct":       "Null %",
            "unique_count":   "Unique values",
            "avg_length":     "Avg length (chars)",
        }
        prof_df = pd.DataFrame(cols_data)
        # Keep only known display columns that exist in the data
        existing = [c for c in display_cols if c in prof_df.columns]
        prof_df  = prof_df[existing].rename(columns=rename_map)
        st.dataframe(prof_df, use_container_width=True, hide_index=True)
    else:
        st.warning("No column profile data available.")

    # Missing value heatmap
    if total_nulls > 0:
        st.divider()
        st.markdown("**Missing value map** (red = missing)")
        null_map = df.isna().astype(int)
        styled   = null_map.head(100).style.map(
            lambda v: "background-color: #f28b82;" if v == 1 else ""
        )
        st.dataframe(styled, use_container_width=True, height=300)
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
        file_name=f"{file_name.rsplit('.', 1)[0]}_ssis_metadata.xml",
        mime="application/xml",
    )


# ── Mode 1: Manual entry ───────────────────────────────────────────────────────

def _render_manual_mode(
    df: pd.DataFrame, raw_bytes: bytes, raw_text: str,
    file_name: str, sep: str, has_header: bool, encoding: str,
) -> None:
    st.info(
        "Enter the **file-level** metadata below. "
        "Per-column fields (types, sizes, nulls) are then generated automatically "
        "by re-parsing the file with your chosen settings."
    )

    LINE_ENDINGS    = ["LF", "CRLF", "CR", "None"]
    TEXT_DELIMITERS = ['Double quote (")', "Single quote (')", "None"]
    ENCODINGS       = ["utf-8", "latin-1", "utf-16"]
    # Delimiter choices and their actual separator chars
    FD_LABELS  = [",", ";", "\\t", "|", "space"]
    FD_CHARS   = {",": ",", ";": ";", "\\t": "\t", "|": "|", "space": " "}

    with st.form("manual_profile_form"):
        st.markdown("**File metadata**")
        mc1, mc2, mc3 = st.columns(3)
        m_fd  = mc1.selectbox("Field delimiter",  FD_LABELS,       index=0)
        m_le  = mc2.selectbox("Line ending",       LINE_ENDINGS,    index=0)
        m_td  = mc3.selectbox("Text delimiter",    TEXT_DELIMITERS, index=0)
        mc4, mc5 = st.columns(2)
        m_hdr = mc4.selectbox("Has headers", ["Yes", "No"], index=0)
        m_enc = mc5.selectbox("Encoding",     ENCODINGS,     index=0)

        submitted = st.form_submit_button("▶️ Generate column profile", type="primary")

    if submitted:
        from core.file_parser import parse_flat_file
        from profiling.detectors import get_column_stats
        from ssis.type_mapper import PREDICTED_TO_SSIS

        user_has_header = m_hdr == "Yes"
        user_sep_char   = FD_CHARS.get(m_fd, m_fd)
        user_encoding   = m_enc

        # Re-parse the raw file with the user's chosen settings so that
        # column detection reflects their actual inputs (delimiter, header, encoding)
        try:
            parsed_df, actual_sep = parse_flat_file(
                raw_bytes,
                delimiter_choice=m_fd,          # file_parser resolves "\\t" → "\t" etc.
                has_header=user_has_header,
                skip_rows=0,
                encoding=user_encoding,
            )
        except Exception as exc:
            st.error(f"Could not re-parse file with these settings: {exc}")
            return

        col_entries = []
        for col in parsed_df.columns:
            stats     = get_column_stats(parsed_df[col])
            ssis_type = PREDICTED_TO_SSIS.get(stats["predicted_type"], "DT_STR")
            col_entries.append({
                "column_name":    col,
                "ssis_data_type": ssis_type,
                **stats,
            })

        profile = {
            "file_metadata": {
                "file_name":       file_name,
                "file_size_kb":    round(len(raw_bytes) / 1024, 2),
                "field_delimiter": m_fd,
                "line_ending":     m_le,
                "text_delimiter":  m_td,
                "has_headers":     user_has_header,
                "encoding":        user_encoding,
                "row_count":       len(parsed_df),
                "column_count":    len(parsed_df.columns),
            },
            "columns": col_entries,
        }
        st.session_state["manual_profile"] = profile
        # Store the re-parsed df so _render_profile_results uses the right frame
        st.session_state["manual_df"] = parsed_df

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
    if st.button("▶️ Run code-logic profiling", type="primary", key="run_code"):
        with st.spinner("Analysing…"):
            profile = build_code_profile(
                df, raw_bytes, raw_text, file_name, sep, has_header, encoding
            )
        st.session_state["code_profile"] = profile

    if st.session_state.get("code_profile"):
        st.divider()
        _render_profile_results(st.session_state["code_profile"], df, file_name)


# ── Mode 3: AI agent ───────────────────────────────────────────────────────────

def _render_ai_mode(
    df: pd.DataFrame, raw_bytes: bytes, raw_text: str,
    file_name: str, sep: str, has_header: bool, encoding: str,
) -> None:
    st.info(
        f"Profile fields are predicted by **{GROQ_MODEL}** on Groq "
        "via an agentic tool-calling loop. The model inspects each column "
        "independently before submitting results."
    )
    if st.button("▶️ Run AI profiling", type="primary", key="run_ai"):
        st.session_state["ai_profile"] = None
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

    # Mode selector
    st.markdown("#### Choose profiling method")
    mode = st.radio(
        "Profiling method",
        options=[
            "1 — Manual entry",
            "2 — Code logic (auto-detect)",
            "3 — AI agent (llama-3.3-70b)",
        ],
        label_visibility="collapsed",
        horizontal=True,
        key="profiling_mode",
    )

    st.divider()

    # Clear stale results when switching modes
    if st.session_state.get("_last_mode") != mode:
        for key in ("manual_profile", "code_profile", "ai_profile"):
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
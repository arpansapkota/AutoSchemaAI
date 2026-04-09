"""
ui/tab_edit_export.py
---------------------
✏️ Edit & Export tab.

Shows the latest profiling result (from any mode), lets the user edit
every field inline, and exports the edited result as:
  - SSIS metadata XML
  - T-SQL CREATE TABLE
"""

import copy

import pandas as pd
import streamlit as st

from ssis.type_mapper import (
    build_ssis_xml,
    build_create_table_sql,
    PREDICTED_TO_SSIS,
)

SSIS_TYPES = ["DT_STR", "DT_I4", "DT_R8", "DT_BOOL",
              "DT_DBDATE", "DT_DBTIMESTAMP", "DT_NUMERIC"]
PRED_TYPES = ["Text", "Integer", "Float", "Boolean", "Date",
              "Datetime", "Numeric (formatted)", "Email", "Empty"]
LINE_ENDINGS = ["LF", "CRLF", "CR", "None"]
TEXT_DELIMITERS = ['Double quote (")', "Single quote (')", "None"]
FD_OPTIONS = [",", ";", "\\t", "|", "space"]
ENCODINGS = ["utf-8", "latin-1", "utf-16"]


def _pick(lst: list, val):
    """Return index of val in lst, defaulting to 0."""
    try:
        return lst.index(val)
    except ValueError:
        return 0


def _safe_stub(file_name: str) -> str:
    return file_name.rsplit(".", 1)[0] if "." in file_name else file_name


def render(file_name: str) -> None:
    st.subheader("Edit & Export")

    profile = (
        st.session_state.get("ai_profile")
        or st.session_state.get("code_profile")
        or st.session_state.get("manual_profile")
    )

    if not profile:
        st.info(
            "No profiling results yet. "
            "Run a profile in the **🔬 Data Profiling** tab first, then come back here."
        )
        return

    if (
        "edited_profile" not in st.session_state
        or st.session_state.get("_edited_profile_source_file") != file_name
    ):
        st.session_state["edited_profile"] = copy.deepcopy(profile)
        st.session_state["_edited_profile_source_file"] = file_name
        st.session_state["edited_sql_schema"] = "dbo"
        st.session_state["edited_sql_table"] = _safe_stub(file_name).replace(" ", "_")

    ep = st.session_state["edited_profile"]
    fm = ep.get("file_metadata", {})
    cols_data: list[dict] = ep.get("columns", [])
    file_stub = _safe_stub(file_name)

    st.caption(
        "Edit any field below, then click **Save changes** to update the profile "
        "and export SSIS metadata and T-SQL."
    )

    with st.form("edit_export_form"):
        # ── File metadata ──────────────────────────────────────────────────────
        st.markdown("#### File metadata")
        fc1, fc2, fc3 = st.columns(3)
        new_fd = fc1.selectbox(
            "Field delimiter", FD_OPTIONS,
            index=_pick(FD_OPTIONS, fm.get("field_delimiter", ",")),
            key="edit_fd_select",
        )
        new_le = fc2.selectbox(
            "Line ending", LINE_ENDINGS,
            index=_pick(LINE_ENDINGS, fm.get("line_ending", "LF")),
            key="edit_le_select",
        )
        new_td = fc3.selectbox(
            "Text delimiter", TEXT_DELIMITERS,
            index=_pick(TEXT_DELIMITERS, fm.get("text_delimiter", "None")),
            key="edit_td_select",
        )

        fc4, fc5, fc6 = st.columns(3)
        new_hdr = fc4.selectbox(
            "Has headers", ["Yes", "No"],
            index=0 if fm.get("has_headers", True) else 1,
            key="edit_hdr_select",
        )
        new_enc = fc5.selectbox(
            "Encoding", ENCODINGS,
            index=_pick(ENCODINGS, fm.get("encoding", "utf-8")),
            key="edit_encoding_select",
        )
        fc6.metric("File size", f"{fm.get('file_size_kb', 0)} KB")

        st.markdown("#### SQL output options")
        sc1, sc2 = st.columns(2)
        default_table = file_stub.replace(" ", "_")
        sql_schema = sc1.text_input(
            "SQL schema name",
            value=st.session_state.get("edited_sql_schema", "dbo"),
            key="edit_sql_schema_input",
        )
        sql_table = sc2.text_input(
            "SQL table name",
            value=st.session_state.get("edited_sql_table", default_table),
            key="edit_sql_table_input",
        )

        # ── Per-column fields ──────────────────────────────────────────────────
        st.markdown("#### Per-column profile")
        st.caption("Edit predicted type, SSIS type and predicted size for each column.")

        edited_cols = []
        for idx, col in enumerate(cols_data):
            cname = col.get("column_name", f"col_{idx}")
            safe_key = f"{idx}_{str(cname).replace(' ', '_')}"

            st.markdown(
                f"**`{cname}`**  —  pandas: `{col.get('pandas_dtype', '?')}`  |  "
                f"nulls: {col.get('null_count', 0)} ({col.get('null_pct', '0%')})  |  "
                f"unique: {col.get('unique_count', '?')}  |  "
                f"avg len: {col.get('avg_length', '?')} chars"
            )

            cc1, cc2, cc3 = st.columns(3)
            new_pt = cc1.selectbox(
                "Predicted type", PRED_TYPES,
                index=_pick(PRED_TYPES, col.get("predicted_type", "Text")),
                key=f"edit_pt_{safe_key}",
            )

            auto_ssis = PREDICTED_TO_SSIS.get(new_pt, "DT_STR")
            new_st = cc2.selectbox(
                "SSIS data type", SSIS_TYPES,
                index=_pick(SSIS_TYPES, col.get("ssis_data_type", auto_ssis)),
                key=f"edit_st_{safe_key}",
            )
            new_ps = cc3.text_input(
                "Predicted size",
                value=col.get("predicted_size", ""),
                key=f"edit_ps_{safe_key}",
            )

            edited_cols.append({
                **col,
                "predicted_type": new_pt,
                "ssis_data_type": new_st,
                "predicted_size": new_ps,
            })

        saved = st.form_submit_button("💾 Save changes")

    if saved:
        st.session_state["edited_profile"] = {
            "file_metadata": {
                **fm,
                "field_delimiter": new_fd,
                "line_ending": new_le,
                "text_delimiter": new_td,
                "has_headers": new_hdr == "Yes",
                "encoding": new_enc,
            },
            "columns": edited_cols,
            "validation_summary": ep.get("validation_summary", {}),
            "data_profile": ep.get("data_profile", {}),
        }
        st.session_state["edited_sql_schema"] = sql_schema
        st.session_state["edited_sql_table"] = sql_table

        st.success("Changes saved.")
        ep = st.session_state["edited_profile"]
        fm = ep["file_metadata"]
        cols_data = ep["columns"]

    else:
        sql_schema = st.session_state.get("edited_sql_schema", "dbo")
        sql_table = st.session_state.get("edited_sql_table", file_stub.replace(" ", "_"))

    st.divider()

    # ── Read-only preview of current profile ──────────────────────────────────
    st.markdown("#### Current profile preview")
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
        pdf = pd.DataFrame(cols_data)
        existing = [c for c in display_cols if c in pdf.columns]
        st.dataframe(
            pdf[existing].rename(columns=rename_map),
            width="stretch",
            hide_index=True,
        )

    st.divider()

    # ── SSIS export ────────────────────────────────────────────────────────────
    st.markdown("#### Export as SSIS metadata")
    st.caption(
        "Exports the **edited** profile as a `DTS:ConnectionManager` XML fragment "
        "for a Flat File Connection Manager."
    )
    ssis_xml = build_ssis_xml(ep, file_name)
    with st.expander("Preview SSIS XML", expanded=False):
        st.code(ssis_xml, language="xml")

    st.download_button(
        "⬇️ Download edited SSIS metadata (.xml)",
        data=ssis_xml.encode("utf-8"),
        file_name=f"{file_stub}_edited_ssis_metadata.xml",
        mime="application/xml",
        key=f"edit_export_download_ssis_{file_stub}",
    )

    st.divider()

    # ── T-SQL export ───────────────────────────────────────────────────────────
    st.markdown("#### Export as T-SQL table")
    st.caption(
        "Exports the **edited** profile as a SQL Server `CREATE TABLE` statement."
    )
    create_sql = build_create_table_sql(
        profile=ep,
        file_name=file_name,
        table_name=sql_table,
        schema_name=sql_schema,
    )
    with st.expander("Preview CREATE TABLE", expanded=False):
        st.code(create_sql, language="sql")

    st.download_button(
        "⬇️ Download CREATE TABLE (.sql)",
        data=create_sql.encode("utf-8"),
        file_name=f"{sql_table}_create_table.sql",
        mime="text/sql",
        key=f"edit_export_download_sql_{file_stub}_{sql_schema}_{sql_table}",
    )
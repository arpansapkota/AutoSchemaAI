"""
ui/tab_edit_export.py
---------------------
✏️ Edit & Export tab.

Shows the latest profiling result (from any mode), lets the user edit
every field inline, and exports the edited result as SSIS metadata XML.
"""

import copy

import pandas as pd
import streamlit as st

from ssis.type_mapper import build_ssis_xml, PREDICTED_TO_SSIS

SSIS_TYPES = ["DT_STR", "DT_I4", "DT_R8", "DT_BOOL",
              "DT_DBDATE", "DT_DBTIMESTAMP", "DT_NUMERIC"]
PRED_TYPES = ["Text", "Integer", "Float", "Boolean", "Date",
              "Datetime", "Numeric (formatted)", "Email", "Empty"]
LINE_ENDINGS    = ["LF", "CRLF", "CR", "None"]
TEXT_DELIMITERS = ['Double quote (")', "Single quote (')", "None"]
FD_OPTIONS      = [",", ";", "\\t", "|", "space"]
ENCODINGS       = ["utf-8", "latin-1", "utf-16"]


def _pick(lst: list, val):
    """Return index of val in lst, defaulting to 0."""
    try:
        return lst.index(val)
    except ValueError:
        return 0


def render(file_name: str) -> None:
    st.subheader("Edit & Export")

    # ── Check for a profile in session state ──────────────────────────────────
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

    # Work on a deep copy so edits don't corrupt the source profile
    if "edited_profile" not in st.session_state:
        st.session_state["edited_profile"] = copy.deepcopy(profile)

    ep = st.session_state["edited_profile"]
    fm = ep.get("file_metadata", {})
    cols_data: list[dict] = ep.get("columns", [])

    st.caption("Edit any field below, then click **Save changes** to update the profile and download SSIS metadata.")

    with st.form("edit_export_form"):

        # ── File metadata ──────────────────────────────────────────────────────
        st.markdown("#### File metadata")
        fc1, fc2, fc3 = st.columns(3)
        new_fd  = fc1.selectbox("Field delimiter",  FD_OPTIONS,
                                index=_pick(FD_OPTIONS, fm.get("field_delimiter", ",")))
        new_le  = fc2.selectbox("Line ending",       LINE_ENDINGS,
                                index=_pick(LINE_ENDINGS, fm.get("line_ending", "LF")))
        new_td  = fc3.selectbox("Text delimiter",    TEXT_DELIMITERS,
                                index=_pick(TEXT_DELIMITERS, fm.get("text_delimiter", "None")))
        fc4, fc5, fc6 = st.columns(3)
        new_hdr = fc4.selectbox("Has headers", ["Yes", "No"],
                                index=0 if fm.get("has_headers", True) else 1)
        new_enc = fc5.selectbox("Encoding", ENCODINGS,
                                index=_pick(ENCODINGS, fm.get("encoding", "utf-8")))
        fc6.metric("File size", f"{fm.get('file_size_kb', 0)} KB")

        # ── Per-column fields ──────────────────────────────────────────────────
        st.markdown("#### Per-column profile")
        st.caption("Edit predicted type, SSIS type and predicted size for each column.")

        edited_cols = []
        for col in cols_data:
            cname = col.get("column_name", "?")
            st.markdown(f"**`{cname}`**  —  pandas: `{col.get('pandas_dtype', '?')}`  |  "
                        f"nulls: {col.get('null_count', 0)} ({col.get('null_pct', '0%')})  |  "
                        f"unique: {col.get('unique_count', '?')}  |  "
                        f"avg len: {col.get('avg_length', '?')} chars")

            cc1, cc2, cc3 = st.columns(3)
            new_pt = cc1.selectbox(
                "Predicted type", PRED_TYPES,
                index=_pick(PRED_TYPES, col.get("predicted_type", "Text")),
                key=f"edit_pt_{cname}",
            )
            # Auto-suggest SSIS type from predicted type, but let user override
            auto_ssis = PREDICTED_TO_SSIS.get(new_pt, "DT_STR")
            new_st = cc2.selectbox(
                "SSIS data type", SSIS_TYPES,
                index=_pick(SSIS_TYPES, col.get("ssis_data_type", auto_ssis)),
                key=f"edit_st_{cname}",
            )
            new_ps = cc3.text_input(
                "Predicted size",
                value=col.get("predicted_size", ""),
                key=f"edit_ps_{cname}",
            )

            edited_cols.append({
                **col,
                "predicted_type": new_pt,
                "ssis_data_type": new_st,
                "predicted_size": new_ps,
            })

        saved = st.form_submit_button("💾 Save changes", type="primary")

    if saved:
        st.session_state["edited_profile"] = {
            "file_metadata": {
                **fm,
                "field_delimiter": new_fd,
                "line_ending":     new_le,
                "text_delimiter":  new_td,
                "has_headers":     new_hdr == "Yes",
                "encoding":        new_enc,
            },
            "columns": edited_cols,
        }
        st.success("Changes saved.")
        ep       = st.session_state["edited_profile"]
        fm       = ep["file_metadata"]
        cols_data = ep["columns"]

    st.divider()

    # ── Read-only preview of current (possibly edited) profile ─────────────────
    st.markdown("#### Current profile preview")
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
        pdf = pd.DataFrame(cols_data)
        existing = [c for c in display_cols if c in pdf.columns]
        st.dataframe(pdf[existing].rename(columns=rename_map), use_container_width=True, hide_index=True)

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
        file_name=f"{file_name.rsplit('.', 1)[0]}_edited_ssis_metadata.xml",
        mime="application/xml",
    )
"""
ui/tab_data_table.py
--------------------
Renders the 📋 Data Table tab.

Features:
  - Top-N rows selector (default 10)
  - Start-from-row-N offset (default 0)
  - Full-text row search
  - Column selector
  - CSV download of the current view
"""

import pandas as pd
import streamlit as st


def render(df: pd.DataFrame, raw_bytes: bytes, sep: str, file_name: str) -> None:
    fd_label = {",": ",", ";": ";", "\t": "\\t", "|": "|", " ": "space"}.get(sep, sep)

    # ── Summary metrics ────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total rows", f"{len(df):,}")
    c2.metric("Columns", len(df.columns))
    c3.metric("File size", f"{len(raw_bytes)/1024:.1f} KB")
    c4.metric("Delimiter", fd_label)

    st.divider()

    # ── View controls ──────────────────────────────────────────────────────────
    vc1, vc2 = st.columns(2)
    start_row = vc1.number_input(
        "Start from row",
        min_value=0,
        max_value=max(len(df) - 1, 0),
        value=0,
        step=1,
        help="0-indexed: row 0 is the first data row.",
        key="dt_start_row",
    )
    top_n = vc2.number_input(
        "Number of rows to display",
        min_value=1,
        max_value=max(len(df), 1),
        value=min(10, max(len(df), 1)),
        step=1,
        key="dt_top_n",
    )

    # ── Search ─────────────────────────────────────────────────────────────────
    search = st.text_input(
        "🔍 Search rows",
        placeholder="Type to filter across all columns…",
        key="dt_search",
    )

    # ── Column selector ────────────────────────────────────────────────────────
    selected_cols = st.multiselect(
        "Show columns",
        options=list(df.columns),
        default=list(df.columns),
        key="dt_columns",
    )

    if not selected_cols:
        st.warning("Select at least one column to display.")
        return

    # ── Filter rows ────────────────────────────────────────────────────────────
    view_df = df[selected_cols].copy()

    if search.strip():
        mask = view_df.astype(str).apply(
            lambda col: col.str.contains(search, case=False, na=False)
        ).any(axis=1)
        view_df = view_df[mask]

    # ── Slice rows ─────────────────────────────────────────────────────────────
    sliced = view_df.iloc[start_row:start_row + top_n]

    st.caption(
        f"Showing {len(sliced):,} row(s)"
        + (f" from filtered result of {len(view_df):,}" if len(view_df) != len(df) else "")
    )

    st.dataframe(sliced, width="stretch", hide_index=True)

    # ── Download current view ──────────────────────────────────────────────────
    csv_bytes = sliced.to_csv(index=False).encode("utf-8")
    file_stub = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.download_button(
        "⬇️ Download current view as CSV",
        data=csv_bytes,
        file_name=f"{file_stub}_view.csv",
        mime="text/csv",
        key=f"download_current_view_{file_stub}",
    )
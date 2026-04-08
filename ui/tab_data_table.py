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
    c1.metric("Total rows",  f"{len(df):,}")
    c2.metric("Columns",     len(df.columns))
    c3.metric("File size",   f"{len(raw_bytes)/1024:.1f} KB")
    c4.metric("Delimiter",   fd_label)

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
        max_value=len(df),
        value=min(10, len(df)),
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
    with st.expander("Choose columns to display", expanded=False):
        sel = st.multiselect(
            "Columns",
            options=list(df.columns),
            default=list(df.columns),
            key="dt_col_select",
        )
        if sel:
            view_df = df[sel]
        else:
            view_df = df
    if not sel:
        view_df = df

    # ── Apply search ───────────────────────────────────────────────────────────
    if search:
        mask = view_df.apply(
            lambda col: col.astype(str).str.contains(search, case=False, na=False)
        ).any(axis=1)
        view_df = view_df[mask]

    # ── Apply start-row + top-n ────────────────────────────────────────────────
    sliced = view_df.iloc[int(start_row): int(start_row) + int(top_n)]

    st.caption(
        f"Showing rows {int(start_row) + 1}–{int(start_row) + len(sliced):,} "
        f"of {len(view_df):,} {'matching ' if search else ''}rows"
    )

    st.dataframe(sliced, use_container_width=True, height=460)

    # ── Download ───────────────────────────────────────────────────────────────
    csv_out = sliced.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download current view as CSV",
        data=csv_out,
        file_name=f"{file_name.rsplit('.', 1)[0]}_view.csv",
        mime="text/csv",
    )
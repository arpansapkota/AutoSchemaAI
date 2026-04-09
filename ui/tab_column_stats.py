"""
ui/tab_column_stats.py
----------------------
Renders the 📈 Column Stats tab.
"""

import pandas as pd
import streamlit as st


def render(df: pd.DataFrame) -> None:
    st.subheader("Column statistics")

    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if not numeric_cols:
        st.warning("No numeric columns found.")
        return

    sc = st.selectbox("Select a column", numeric_cols, key="stat_col")
    s = df[sc].dropna()

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Mean", f"{s.mean():.4g}")
    s2.metric("Median", f"{s.median():.4g}")
    s3.metric("Std dev", f"{s.std():.4g}")
    s4.metric("Variance", f"{s.var():.4g}")

    s5, s6, s7, s8 = st.columns(4)
    s5.metric("Min", f"{s.min():.4g}")
    s6.metric("Max", f"{s.max():.4g}")
    s7.metric("Range", f"{s.max() - s.min():.4g}")
    s8.metric("Count", f"{len(s):,}")

    s9, s10, s11, s12 = st.columns(4)
    s9.metric("Q1 (25%)", f"{s.quantile(0.25):.4g}")
    s10.metric("Q2 (50%)", f"{s.quantile(0.50):.4g}")
    s11.metric("Q3 (75%)", f"{s.quantile(0.75):.4g}")
    s12.metric("IQR", f"{(s.quantile(0.75) - s.quantile(0.25)):.4g}")

    st.divider()

    st.markdown("#### Distribution preview")
    hist_df = pd.DataFrame({sc: s})
    st.bar_chart(hist_df, width="stretch")

    st.markdown("#### Sample values")
    st.dataframe(hist_df.head(50), width="stretch", hide_index=True)
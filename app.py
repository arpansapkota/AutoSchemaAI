"""
app.py
------
Entry point for the Flat File Reader Streamlit application.
Thin orchestrator — delegates everything to ui/ and core/ modules.

Tab order:
  1. 📋 Data Table
  2. 🔬 Data Profiling
  3. ✏️ Edit & Export

Run with:
    streamlit run app.py
    OR
    python -m streamlit run app.py  
"""

import sys
import streamlit as st

# Check if running outside Streamlit context
if "streamlit" not in sys.modules or not hasattr(st, "_is_running_with_streamlit"):
    try:
        # Try to detect if we're in a bare Python execution
        if getattr(st, "_is_running_with_streamlit", None) is False:
            print("\n" + "="*60)
            print("❌ ERROR: This app must be run with Streamlit!")
            print("="*60)
            print("\nRun this command instead:\n")
            print("    streamlit run app.py\n")
            print("="*60 + "\n")
            sys.exit(1)
    except:
        pass

st.set_page_config(page_title="AutoSchemaAI", page_icon="📂", layout="wide")

from core.file_parser import parse_flat_file
from ui import tab_data_table, tab_profiling, tab_edit_export

st.title("📂 AutoSchemaAI")
st.caption("Upload a `.csv` or `.txt` file to explore, profile and export its contents.")

# ── File upload ────────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "Choose a file", type=["csv", "txt"], label_visibility="collapsed"
)
if not uploaded_file:
    st.info("Upload a `.csv` or `.txt` file above to get started.")
    st.stop()

try:
    raw_bytes = uploaded_file.read()
except AttributeError:
    st.error("❌ This app must be run with Streamlit!\n\nRun: `streamlit run app.py`")
    sys.exit(1)

DEFAULT_ENCODING = "utf-8"
DEFAULT_HEADER   = True

try:
    df, sep = parse_flat_file(
        raw_bytes,
        delimiter_choice="Auto-detect",
        has_header=DEFAULT_HEADER,
        skip_rows=0,
        encoding=DEFAULT_ENCODING,
    )
except Exception as e:
    st.error(f"Could not parse file: {e}")
    st.stop()

raw_text = raw_bytes.decode(DEFAULT_ENCODING, errors="replace")

# Clear all cached state when a new file is uploaded
if st.session_state.get("_last_file") != uploaded_file.name:
    for key in (
        "manual_profile", "manual_df",
        "code_profile", "ai_profile",
        "edited_profile", "_last_mode",
    ):
        st.session_state.pop(key, None)
    st.session_state["_last_file"] = uploaded_file.name

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📋 Data Table",
    "🔬 Data Profiling",
    "✏️ Edit & Export",
])

with tab1:
    tab_data_table.render(
        df=df,
        raw_bytes=raw_bytes,
        sep=sep,
        file_name=uploaded_file.name,
    )

with tab2:
    tab_profiling.render(
        df=df,
        raw_bytes=raw_bytes,
        raw_text=raw_text,
        file_name=uploaded_file.name,
        sep=sep,
        has_header=DEFAULT_HEADER,
        encoding=DEFAULT_ENCODING,
    )

with tab3:
    tab_edit_export.render(file_name=uploaded_file.name)
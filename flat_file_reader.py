"""
Flat File Reader — Agentic Data Profiling
==========================================
• File parsing  : pandas (local, instant)
• Data Profiling: llama-3.3-70b-versatile on Groq via agentic tool-calling loop
• API key       : loaded from config.ini (same directory as this script)
• SSIS export   : built from the AI profile results
"""

import configparser
import io
import json
import os
import re
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom

import pandas as pd
import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# Load API key from config.ini
# ──────────────────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

def load_api_key(path: str) -> str:
    """Read the Groq API key from config.ini next to this script."""
    if not os.path.exists(path):
        st.error(
            f"**config.ini not found.**\n\n"
            f"Expected location: `{path}`\n\n"
            "Create it with the following content:\n"
            "```ini\n[groq]\napi_key = gsk_YOUR_KEY_HERE\n```"
        )
        st.stop()

    cfg = configparser.ConfigParser()
    cfg.read(path)

    try:
        key = cfg["groq"]["api_key"].strip()
    except KeyError:
        st.error(
            "**config.ini is missing the `[groq]` section or `api_key` field.**\n\n"
            "Expected format:\n```ini\n[groq]\napi_key = gsk_YOUR_KEY_HERE\n```"
        )
        st.stop()

    if not key or key == "gsk_YOUR_GROQ_API_KEY_HERE":
        st.error(
            "**Groq API key is not set in config.ini.**\n\n"
            f"Open `{path}` and replace the placeholder with your real key."
        )
        st.stop()

    return key


GROQ_API_KEY = load_api_key(CONFIG_PATH)
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Flat File Reader", page_icon="📂", layout="wide")
st.title("📂 Flat File Reader")
st.caption("Upload a `.csv` or `.txt` file to explore its contents.")

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — parse options only (no API key input)
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Parse options")
    delimiter  = st.selectbox("Field delimiter", ["Auto-detect", ",", ";", "\\t", "|", " "], index=0)
    has_header = st.toggle("First row is header", value=True)
    skip_rows  = st.number_input("Skip rows at top", min_value=0, value=0, step=1)
    encoding   = st.selectbox("Encoding", ["utf-8", "latin-1", "utf-16"], index=0)

    st.divider()
    #st.markdown("🤖 **AI model**")
    #st.caption(f"`{GROQ_MODEL}` via Groq")
    #st.caption(f"Key loaded from `config.ini`")

# ──────────────────────────────────────────────────────────────────────────────
# File upload
# ──────────────────────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "Choose a file", type=["csv", "txt"], label_visibility="collapsed"
)
if not uploaded_file:
    st.info("Upload a `.csv` or `.txt` file above to get started.")
    st.stop()

raw_bytes = uploaded_file.read()
raw_text  = raw_bytes.decode(encoding, errors="replace")

# ──────────────────────────────────────────────────────────────────────────────
# Lightweight local helper — CSV parsing only
# ──────────────────────────────────────────────────────────────────────────────
def _resolve_sep(delimiter: str, raw_text: str) -> str:
    if delimiter == "Auto-detect":
        counts = {d: raw_text[:4096].count(d) for d in [",", ";", "\t", "|"]}
        return max(counts, key=counts.get)
    return "\t" if delimiter == "\\t" else delimiter


sep = _resolve_sep(delimiter, raw_text)

try:
    df = pd.read_csv(
        io.BytesIO(raw_bytes),
        sep=sep,
        header=0 if has_header else None,
        skiprows=int(skip_rows),
        encoding=encoding,
        on_bad_lines="warn",
    )
except Exception as e:
    st.error(f"Could not parse file: {e}")
    st.stop()

numeric_cols     = df.select_dtypes(include="number").columns.tolist()
categorical_cols = df.select_dtypes(exclude="number").columns.tolist()

# ──────────────────────────────────────────────────────────────────────────────
# Agent tool functions
# ──────────────────────────────────────────────────────────────────────────────

def tool_get_file_metadata() -> dict:
    """Detect and return file-level metadata."""
    raw = raw_bytes

    crlf = raw.count(b"\r\n")
    lf   = raw.count(b"\n") - crlf
    cr   = raw.count(b"\r") - crlf
    if crlf >= lf and crlf >= cr and crlf > 0:
        line_ending = "CRLF"
    elif lf >= cr and lf > 0:
        line_ending = "LF"
    elif cr > 0:
        line_ending = "CR"
    else:
        line_ending = "None"

    sample = raw_text[:8192]
    dq, sq = sample.count('"'), sample.count("'")
    if dq == 0 and sq == 0:
        text_delim = "None"
    elif dq >= sq:
        text_delim = 'Double quote (")'
    else:
        text_delim = "Single quote (')"

    fd_map = {",": ",", ";": ";", "\t": "\\t", "|": "|", " ": "space"}
    field_delim_label = fd_map.get(sep, sep)

    return {
        "file_name":       uploaded_file.name,
        "file_size_kb":    round(len(raw_bytes) / 1024, 2),
        "field_delimiter": field_delim_label,
        "line_ending":     line_ending,
        "text_delimiter":  text_delim,
        "has_headers":     has_header,
        "encoding":        encoding,
        "row_count":       len(df),
        "column_count":    len(df.columns),
    }


def tool_get_all_columns() -> dict:
    """Return all column names."""
    return {"columns": list(df.columns)}


def tool_get_column_sample(column_name: str, max_rows: int = 30) -> dict:
    """Return a sample + stats for one column."""
    if column_name not in df.columns:
        return {"error": f"Column '{column_name}' not found."}
    s = df[column_name]
    sample = s.dropna().astype(str).head(max_rows).tolist()
    top_val = s.value_counts().idxmax() if s.notna().any() else None
    return {
        "column_name":   column_name,
        "pandas_dtype":  str(s.dtype),
        "total_rows":    len(s),
        "null_count":    int(s.isna().sum()),
        "unique_count":  int(s.nunique()),
        "max_length":    int(s.dropna().astype(str).str.len().max()) if s.notna().any() else 0,
        "avg_length":    round(s.dropna().astype(str).str.len().mean(), 1) if s.notna().any() else 0,
        "most_frequent": str(top_val) if top_val is not None else "—",
        "sample_values": sample,
    }


def tool_submit_profile_results(profile: dict) -> dict:
    """Accept the final profiling result from the agent."""
    return {"status": "accepted", "columns_received": len(profile.get("columns", []))}


# ── Tool registry ──────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_file_metadata",
            "description": (
                "Detect and return file-level metadata: field delimiter, line ending "
                "(CRLF/LF/CR/None), text delimiter, encoding, has_headers, file size, "
                "row count and column count."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_columns",
            "description": "Return the list of all column names in the uploaded file.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_column_sample",
            "description": (
                "Return sample values, null count, unique count, max/avg length and "
                "pandas dtype for a single column. Call this for every column before "
                "submitting results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "column_name": {
                        "type": "string",
                        "description": "Exact column name as returned by get_all_columns.",
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Number of sample rows to return (default 30).",
                        "default": 30,
                    },
                },
                "required": ["column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_profile_results",
            "description": (
                "Call this ONCE when ALL columns have been profiled. "
                "Submit the complete structured profiling results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "description": (
                            "Object with keys: "
                            "'file_metadata' (dict from get_file_metadata) and "
                            "'columns' (array of per-column objects). "
                            "Each column object must include: column_name, pandas_dtype, "
                            "predicted_type (one of: Integer | Float | Boolean | Date | "
                            "Datetime | Numeric (formatted) | Email | Text | Empty), "
                            "predicted_size (e.g. '4 bytes (INT)' or '~80 bytes (VARCHAR 100)'), "
                            "ssis_data_type (one of: DT_I4 | DT_R8 | DT_BOOL | DT_DBDATE | "
                            "DT_DBTIMESTAMP | DT_NUMERIC | DT_STR), "
                            "null_count (int), null_pct (string e.g. '3.2%'), "
                            "unique_count (int), avg_length (float), "
                            "most_frequent (string), non_null_count (int)."
                        ),
                    }
                },
                "required": ["profile"],
            },
        },
    },
]

TOOL_DISPATCH = {
    "get_file_metadata":      lambda args: tool_get_file_metadata(),
    "get_all_columns":        lambda args: tool_get_all_columns(),
    "get_column_sample":      lambda args: tool_get_column_sample(
                                  args["column_name"], args.get("max_rows", 30)
                              ),
    "submit_profile_results": lambda args: tool_submit_profile_results(args["profile"]),
}

SYSTEM_PROMPT = """You are a data profiling agent for flat files (CSV/TXT).

Your job:
1. Call get_file_metadata to retrieve file-level properties.
2. Call get_all_columns to get the full column list.
3. For EVERY column, call get_column_sample to inspect its values.
4. Based on your analysis, determine for each column:
   - predicted_type: Integer | Float | Boolean | Date | Datetime | Numeric (formatted) | Email | Text | Empty
   - predicted_size: human-readable storage estimate (e.g. "4 bytes (INT)", "~80 bytes (VARCHAR 100)")
   - ssis_data_type: DT_I4 | DT_R8 | DT_BOOL | DT_DBDATE | DT_DBTIMESTAMP | DT_NUMERIC | DT_STR
   - most_frequent: the most commonly occurring non-null value
5. When ALL columns have been profiled, call submit_profile_results ONCE with the complete profile JSON.

Rules:
- You MUST call get_column_sample for every column before submitting.
- Do not guess — inspect sample values carefully.
- For DT_STR columns, set predicted_size based on max observed length rounded up to nearest: 50, 100, 255, 500, 1000, 2000, 4000.
- Only call submit_profile_results after every column has been sampled.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Groq agentic loop
# ──────────────────────────────────────────────────────────────────────────────

def run_groq_agent() -> dict:
    """Run the DeepSeek-R1 agentic tool-calling loop on Groq. Returns the final profile dict."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": "Please profile this file now."},
    ]

    final_profile  = None
    max_iterations = 60
    total_cols     = len(df.columns)

    status_box   = st.empty()
    progress_bar = st.progress(0)
    log_expander = st.expander("🔍 Agent reasoning log", expanded=False)
    log_lines    = []

    for iteration in range(max_iterations):
        payload = {
            "model":       GROQ_MODEL,
            "messages":    messages,
            "tools":       TOOLS,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens":  4096,
        }

        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text}")

        data       = resp.json()
        message    = data["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        messages.append(message)

        if not tool_calls:
            break  # model finished without a submit — stop

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"] or "{}")
            tc_id   = tc["id"]

            log_lines.append(
                f"→ **{fn_name}**"
                + (f"(`{fn_args.get('column_name')}`)" if "column_name" in fn_args else "()")
            )
            with log_expander:
                st.markdown("\n".join(log_lines))

            # Progress feedback
            if fn_name == "get_file_metadata":
                status_box.info("🤖 Detecting file metadata…")
                progress_bar.progress(5)
            elif fn_name == "get_all_columns":
                status_box.info("🤖 Enumerating columns…")
                progress_bar.progress(8)
            elif fn_name == "get_column_sample":
                col_done = sum(1 for l in log_lines if "get_column_sample" in l)
                pct = min(10 + int(col_done / max(total_cols, 1) * 80), 90)
                status_box.info(
                    f"🤖 Profiling column **{fn_args.get('column_name')}** "
                    f"({col_done}/{total_cols})"
                )
                progress_bar.progress(pct)
            elif fn_name == "submit_profile_results":
                status_box.info("🤖 Finalising profile…")
                progress_bar.progress(95)

            # Execute tool
            try:
                result = TOOL_DISPATCH[fn_name](fn_args)
            except Exception as exc:
                result = {"error": str(exc)}

            if fn_name == "submit_profile_results":
                final_profile = fn_args.get("profile", {})

            messages.append({
                "role":         "tool",
                "tool_call_id": tc_id,
                "content":      json.dumps(result),
            })

        if final_profile is not None:
            break

    progress_bar.progress(100)
    status_box.success("✅ AI profiling complete!")
    return final_profile or {}


# ──────────────────────────────────────────────────────────────────────────────
# SSIS XML builder
# ──────────────────────────────────────────────────────────────────────────────
SSIS_TYPE_ATTRS = {
    "DT_I4":          {"Length": "0",   "Precision": "10", "Scale": "0", "CodePage": "0"},
    "DT_R8":          {"Length": "0",   "Precision": "15", "Scale": "0", "CodePage": "0"},
    "DT_BOOL":        {"Length": "0",   "Precision": "0",  "Scale": "0", "CodePage": "0"},
    "DT_DBDATE":      {"Length": "0",   "Precision": "0",  "Scale": "0", "CodePage": "0"},
    "DT_DBTIMESTAMP": {"Length": "0",   "Precision": "0",  "Scale": "3", "CodePage": "0"},
    "DT_NUMERIC":     {"Length": "0",   "Precision": "18", "Scale": "4", "CodePage": "0"},
    "DT_STR":         {"Length": "255", "Precision": "0",  "Scale": "0", "CodePage": "1252"},
}
LINE_ENDING_SSIS = {"CRLF": "CRLF", "LF": "LF", "CR": "CR", "None": "LF"}
TEXT_DELIM_SSIS  = {'Double quote (")': '"', "Single quote (')": "'", "None": ""}
CP_MAP           = {"utf-8": "65001", "latin-1": "1252", "utf-16": "1200"}


def _str_length_from_size(predicted_size: str) -> str:
    m = re.search(r"VARCHAR\s*(\d+)", predicted_size or "")
    return m.group(1) if m else "255"


def build_ssis_xml(profile: dict, file_name: str) -> str:
    fm        = profile.get("file_metadata", {})
    cols_data = profile.get("columns", [])

    conn_name  = file_name.rsplit(".", 1)[0]
    conn_id    = "{" + str(uuid.uuid4()).upper() + "}"
    row_delim  = LINE_ENDING_SSIS.get(fm.get("line_ending", "LF"), "LF")
    text_qual  = TEXT_DELIM_SSIS.get(fm.get("text_delimiter", "None"), "")
    field_delim= fm.get("field_delimiter", ",")
    col_delim  = "\t" if field_delim == "\\t" else field_delim
    code_page  = CP_MAP.get(fm.get("encoding", "utf-8"), "1252")

    root = ET.Element("DTS:ConnectionManager", {
        "xmlns:DTS":        "www.microsoft.com/SqlServer/Dts",
        "DTS:refId":        f"Package.ConnectionManagers[{conn_name}]",
        "DTS:CreationName": "FLATFILE",
        "DTS:DTSID":        conn_id,
        "DTS:ObjectName":   conn_name,
    })
    obj_data = ET.SubElement(root, "DTS:ObjectData")
    ff_cm    = ET.SubElement(obj_data, "DTS:FlatFileConnectionManager", {
        "DTS:ColumnNamesInFirstDataRow": "true" if fm.get("has_headers") else "false",
        "DTS:CodePage":                  code_page,
        "DTS:Format":                    "Delimited",
        "DTS:RowDelimiter":              row_delim,
        "DTS:TextQualifier":             text_qual if text_qual else "_x007B__x007D_",
        "DTS:ConnectionString":          file_name,
        "DTS:HeaderRowsToSkip":          "0",
        "DTS:DataRowsToSkip":            "0",
        "DTS:Unicode":                   "true" if fm.get("encoding") == "utf-16" else "false",
    })
    ff_cols = ET.SubElement(ff_cm, "DTS:FlatFileColumns")

    for idx, col in enumerate(cols_data):
        ssis_type = col.get("ssis_data_type", "DT_STR")
        attrs     = SSIS_TYPE_ATTRS.get(ssis_type, SSIS_TYPE_ATTRS["DT_STR"]).copy()
        if ssis_type == "DT_STR":
            attrs["Length"] = _str_length_from_size(col.get("predicted_size", ""))
        is_last = (idx == len(cols_data) - 1)
        ET.SubElement(ff_cols, "DTS:FlatFileColumn", {
            "DTS:ColumnDelimiter": row_delim if is_last else col_delim,
            "DTS:ColumnType":      "Delimited",
            "DTS:DataType":        ssis_type,
            "DTS:Length":          attrs["Length"],
            "DTS:Precision":       attrs["Precision"],
            "DTS:Scale":           attrs["Scale"],
            "DTS:CodePage":        attrs["CodePage"] if ssis_type == "DT_STR" else "0",
            "DTS:TextQualified":   "true" if text_qual else "false",
            "DTS:ObjectName":      col.get("column_name", f"Column{idx}"),
            "DTS:DTSID":           "{" + str(uuid.uuid4()).upper() + "}",
        })

    raw_xml = ET.tostring(root, encoding="unicode")
    pretty  = minidom.parseString(raw_xml).toprettyxml(indent="  ")
    return "\n".join(pretty.split("\n")[1:])


# ──────────────────────────────────────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Data Table", "📊 Charts", "🔬 Data Profiling", "📈 Column Stats"]
)

# ── Tab 1: Data Table ──────────────────────────────────────────────────────────
with tab1:
    c1, c2, c3, c4 = st.columns(4)
    fd_label = {",": ",", ";": ";", "\t": "\\t", "|": "|", " ": "space"}.get(sep, sep)
    c1.metric("Rows",      f"{len(df):,}")
    c2.metric("Columns",   len(df.columns))
    c3.metric("File size", f"{len(raw_bytes)/1024:.1f} KB")
    c4.metric("Delimiter", fd_label)

    st.divider()
    search_query = st.text_input("🔍 Search rows", placeholder="Type to filter…")
    if search_query:
        mask = df.apply(
            lambda col: col.astype(str).str.contains(search_query, case=False, na=False)
        ).any(axis=1)
        display_df = df[mask]
        st.caption(f"{len(display_df):,} of {len(df):,} rows match")
    else:
        display_df = df

    with st.expander("Choose columns to display", expanded=False):
        sel_cols = st.multiselect("Columns", options=list(df.columns), default=list(df.columns))
        if sel_cols:
            display_df = display_df[sel_cols]

    st.dataframe(display_df, use_container_width=True, height=480)
    csv_out = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download filtered data as CSV", data=csv_out,
        file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}_filtered.csv",
        mime="text/csv",
    )

# ── Tab 2: Charts ──────────────────────────────────────────────────────────────
with tab2:
    st.subheader("Charts")
    if not numeric_cols:
        st.warning("No numeric columns found for charting.")
    else:
        chart_type = st.selectbox(
            "Chart type", ["Histogram", "Bar chart", "Line chart", "Scatter plot"]
        )
        if chart_type == "Histogram":
            col  = st.selectbox("Column", numeric_cols, key="hist_col")
            bins = st.slider("Bins", 5, 100, 20)
            cuts, _ = pd.cut(df[col].dropna(), bins=bins, retbins=True)
            hdf = cuts.value_counts(sort=False).reset_index()
            hdf.columns = ["Bin", "Count"]
            hdf["Bin"] = hdf["Bin"].astype(str)
            st.bar_chart(hdf.set_index("Bin")["Count"])

        elif chart_type == "Bar chart":
            if categorical_cols:
                xc = st.selectbox("Category (X)", categorical_cols, key="bar_x")
                yc = st.selectbox("Value (Y)", numeric_cols, key="bar_y")
                ag = st.selectbox("Aggregation", ["sum", "mean", "count", "max", "min"])
                bd = (
                    df.groupby(xc)[yc].agg(ag)
                    .reset_index()
                    .sort_values(yc, ascending=False)
                    .head(30)
                )
                st.bar_chart(bd.set_index(xc)[yc])
            else:
                st.info("No categorical columns for X axis.")

        elif chart_type == "Line chart":
            ycs = st.multiselect("Y columns", numeric_cols, default=numeric_cols[:1], key="line_y")
            xc  = st.selectbox("X axis", ["Row index"] + list(df.columns), key="line_x")
            if ycs:
                pld = df[ycs].copy()
                if xc != "Row index" and xc in df.columns:
                    pld.index = df[xc]
                st.line_chart(pld)

        elif chart_type == "Scatter plot":
            if len(numeric_cols) >= 2:
                xc = st.selectbox("X axis", numeric_cols, key="scat_x")
                yc = st.selectbox("Y axis", [c for c in numeric_cols if c != xc], key="scat_y")
                st.scatter_chart(df[[xc, yc]].dropna(), x=xc, y=yc)
            else:
                st.info("Need at least 2 numeric columns.")

# ── Tab 3: Data Profiling (AI-powered) ────────────────────────────────────────
with tab3:
    st.subheader("Data profiling")
    st.caption(
        f"Powered by **{GROQ_MODEL}** via Groq — "
        "the AI agent inspects each column and the file structure autonomously."
    )

    run_btn = st.button("▶️ Run AI profiling", type="primary")

    if "ai_profile" not in st.session_state:
        st.session_state.ai_profile = None

    if run_btn:
        st.session_state.ai_profile = None
        try:
            profile = run_groq_agent()
            st.session_state.ai_profile = profile
        except Exception as exc:
            st.error(f"Agent error: {exc}")

    profile = st.session_state.ai_profile
    if not profile:
        st.info("Click **Run AI profiling** to start the agent.")
        st.stop()

    fm = profile.get("file_metadata", {})

    # File metadata
    st.markdown("#### File metadata")
    fm1, fm2, fm3 = st.columns(3)
    fm1.metric("Field delimiter", fm.get("field_delimiter", "—"))
    fm2.metric("Line ending",     fm.get("line_ending", "—"))
    fm3.metric("Text delimiter",  fm.get("text_delimiter", "—"))
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

    # Per-column AI profile
    st.markdown("#### Per-column profile  *(AI-generated)*")
    cols_data = profile.get("columns", [])
    if cols_data:
        prof_df = pd.DataFrame(cols_data).rename(columns={
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
            "most_frequent":  "Most frequent",
        })
        st.dataframe(prof_df, use_container_width=True, hide_index=True)
    else:
        st.warning("No column profiles returned by the agent.")

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
        "Downloads a `DTS:ConnectionManager` XML fragment using AI-derived types, "
        "ready to paste into any `.dtsx` package."
    )
    ssis_xml = build_ssis_xml(profile, uploaded_file.name)
    with st.expander("Preview SSIS XML", expanded=False):
        st.code(ssis_xml, language="xml")
    st.download_button(
        "⬇️ Download SSIS metadata (.xml)",
        data=ssis_xml.encode("utf-8"),
        file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}_ssis_metadata.xml",
        mime="application/xml",
    )

# ── Tab 4: Column Stats ────────────────────────────────────────────────────────
with tab4:
    st.subheader("Column statistics")
    if not numeric_cols:
        st.warning("No numeric columns found.")
    else:
        sc = st.selectbox("Select a column", numeric_cols, key="stat_col")
        s  = df[sc].dropna()
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Mean",     f"{s.mean():.4g}")
        s2.metric("Median",   f"{s.median():.4g}")
        s3.metric("Std dev",  f"{s.std():.4g}")
        s4.metric("Variance", f"{s.var():.4g}")
        s5, s6, s7, s8 = st.columns(4)
        s5.metric("Min",   f"{s.min():.4g}")
        s6.metric("Max",   f"{s.max():.4g}")
        s7.metric("Range", f"{s.max() - s.min():.4g}")
        s8.metric("Count", f"{len(s):,}")
        s9, s10, s11, s12 = st.columns(4)
        s9.metric("Q1 (25%)",  f"{s.quantile(0.25):.4g}")
        s10.metric("Q2 (50%)", f"{s.quantile(0.50):.4g}")
        s11.metric("Q3 (75%)", f"{s.quantile(0.75):.4g}")
        s12.metric("IQR",      f"{s.quantile(0.75) - s.quantile(0.25):.4g}")
        st.divider()
        st.markdown(f"**Distribution of `{sc}`**")
        bins = st.slider("Bins", 5, 100, 20, key="stat_bins")
        cuts2, _ = pd.cut(s, bins=bins, retbins=True)
        hdf2 = cuts2.value_counts(sort=False).reset_index()
        hdf2.columns = ["Bin", "Count"]
        hdf2["Bin"] = hdf2["Bin"].astype(str)
        st.bar_chart(hdf2.set_index("Bin")["Count"])
    st.divider()
    st.markdown("**Full `describe()` output**")
    st.dataframe(df.describe(include="all").T, use_container_width=True)
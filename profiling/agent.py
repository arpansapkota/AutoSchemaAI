"""
profiling/agent.py
------------------
Agentic profiling loop powered by llama-3.3-70b-versatile on Groq.
"""

import json

import pandas as pd
import requests
import streamlit as st

from core.config import GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL
from profiling.detectors import build_file_metadata

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a data profiling agent for flat files (CSV / TXT).

Workflow — follow this order exactly:
1. Call get_file_metadata   → gather file-level properties.
2. Call get_all_columns     → get the full column list.
3. For EVERY column call get_column_sample → inspect values, nulls, lengths.
4. Determine for each column:
   - predicted_type  : Integer | Float | Boolean | Date | Datetime |
                       Numeric (formatted) | Email | Text | Empty
   - predicted_size  : based strictly on type — use these exact values:
       Integer             -> "4 bytes (INT)"
       Float               -> "8 bytes (DOUBLE)"
       Boolean             -> "1 byte (BIT)"
       Date                -> "3 bytes (DATE)"
       Datetime            -> "8 bytes (DATETIME)"
       Numeric (formatted) -> "8 bytes (DECIMAL)"
       Email               -> "~100 bytes (VARCHAR 100)"
       Text                -> use max_length from sample, rounded up to nearest
                             of 50, 100, 255, 500, 1000, 2000, 4000
                             e.g. "~255 bytes (VARCHAR 255)"
       Empty               -> "0 bytes"
   - ssis_data_type  : DT_I4 | DT_R8 | DT_BOOL | DT_DBDATE |
                       DT_DBTIMESTAMP | DT_NUMERIC | DT_STR
5. Once ALL columns are done, call submit_profile_results ONCE.

Rules:
- Never skip a column; always call get_column_sample for every one.
- Do not guess types — base decisions on actual sample values.
- Do NOT include most_frequent in column results.
"""

# ── Tool schemas ───────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_file_metadata",
            "description": (
                "Detect and return file-level metadata: field delimiter, line ending "
                "(CRLF/LF/CR/None), text delimiter, encoding, has_headers, "
                "file size, row count and column count."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_columns",
            "description": "Return the list of all column names in the file.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_column_sample",
            "description": (
                "Return sample values, null count, unique count, max/avg length "
                "and pandas dtype for a single column."
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
                        "description": "Number of sample rows (default 30).",
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
                "Call ONCE when every column has been profiled. "
                "Submit the complete structured profile as JSON."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "description": (
                            "Keys: 'file_metadata' (dict) and 'columns' (array). "
                            "Each column object must have: column_name, pandas_dtype, "
                            "predicted_type, predicted_size, ssis_data_type, "
                            "null_count (int), null_pct (string), unique_count (int), "
                            "avg_length (float), non_null_count (int)."
                        ),
                    }
                },
                "required": ["profile"],
            },
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────────

def make_tool_dispatch(
    df: pd.DataFrame,
    raw_bytes: bytes,
    raw_text: str,
    file_name: str,
    sep: str,
    has_header: bool,
    encoding: str,
) -> dict:
    def _get_file_metadata(_args) -> dict:
        return build_file_metadata(
            raw_bytes, raw_text, file_name, sep,
            has_header, encoding, len(df), len(df.columns),
        )

    def _get_all_columns(_args) -> dict:
        return {"columns": list(df.columns)}

    def _get_column_sample(args) -> dict:
        args       = args if isinstance(args, dict) else {}
        col_name   = args.get("column_name", "")
        max_rows   = int(args.get("max_rows", 30))
        if col_name not in df.columns:
            return {"error": f"Column '{col_name}' not found. Available: {list(df.columns)}"}
        s = df[col_name]
        return {
            "column_name":   col_name,
            "pandas_dtype":  str(s.dtype),
            "total_rows":    len(s),
            "null_count":    int(s.isna().sum()),
            "unique_count":  int(s.nunique()),
            "max_length":    int(s.dropna().astype(str).str.len().max()) if s.notna().any() else 0,
            "avg_length":    round(float(s.dropna().astype(str).str.len().mean()), 1) if s.notna().any() else 0.0,
            "sample_values": s.dropna().astype(str).head(max_rows).tolist(),
        }

    def _submit_profile_results(args) -> dict:
        args    = args if isinstance(args, dict) else {}
        profile = args.get("profile")
        if not isinstance(profile, dict):
            return {"error": "profile must be a JSON object"}
        cols = profile.get("columns")
        n    = len(cols) if isinstance(cols, list) else 0
        return {"status": "accepted", "columns_received": n}

    return {
        "get_file_metadata":      _get_file_metadata,
        "get_all_columns":        _get_all_columns,
        "get_column_sample":      _get_column_sample,
        "submit_profile_results": _submit_profile_results,
    }


def _safe_parse_args(raw: str | None) -> dict:
    """Parse tool-call arguments JSON safely; always returns a dict."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _safe_profile_from_args(fn_args: dict) -> dict | None:
    """
    Extract the 'profile' payload from submit_profile_results args.
    Returns None if the payload is missing, null, or malformed.
    """
    profile = fn_args.get("profile")
    if not isinstance(profile, dict):
        return None
    # Must have both required keys
    if "file_metadata" not in profile or "columns" not in profile:
        return None
    if not isinstance(profile.get("columns"), list):
        return None
    return profile


# ── Main agentic loop ──────────────────────────────────────────────────────────

def run_agent(
    df: pd.DataFrame,
    raw_bytes: bytes,
    raw_text: str,
    file_name: str,
    sep: str,
    has_header: bool,
    encoding: str,
) -> dict:
    """
    Run the llama-3.3-70b agentic loop on Groq.
    Returns a profile dict identical in schema to build_code_profile().
    Raises RuntimeError on API failure; returns {} if agent doesn't submit.
    """
    dispatch = make_tool_dispatch(
        df, raw_bytes, raw_text, file_name, sep, has_header, encoding
    )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": "Please profile this file now."},
    ]

    final_profile  = None
    max_iterations = 80
    total_cols     = len(df.columns)

    status_box   = st.empty()
    progress_bar = st.progress(0)
    log_expander = st.expander("🔍 Agent reasoning log", expanded=False)
    log_lines: list[str] = []

    for _iteration in range(max_iterations):
        payload = {
            "model":       GROQ_MODEL,
            "messages":    messages,
            "tools":       TOOLS,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens":  500,
        }

        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text}")

        data    = resp.json()
        choice  = data["choices"][0]
        message = choice.get("message", {})

        # tool_calls can be absent, None, or a list — normalise to list
        raw_tool_calls = message.get("tool_calls")
        tool_calls: list = raw_tool_calls if isinstance(raw_tool_calls, list) else []

        messages.append(message)

        # No tool calls → model is done
        if not tool_calls:
            break

        for tc in tool_calls:
            # Guard: tc must be a dict with function key
            if not isinstance(tc, dict) or "function" not in tc:
                continue

            fn_info = tc["function"]
            fn_name = fn_info.get("name", "")
            fn_args = _safe_parse_args(fn_info.get("arguments"))
            tc_id   = tc.get("id", "")

            col_label = f"(`{fn_args['column_name']}`)" if "column_name" in fn_args else "()"
            log_lines.append(f"→ **{fn_name}**{col_label}")
            with log_expander:
                st.markdown("\n".join(log_lines))

            # Progress updates
            if fn_name == "get_file_metadata":
                status_box.info("🤖 Detecting file metadata…")
                progress_bar.progress(5)
            elif fn_name == "get_all_columns":
                status_box.info("🤖 Enumerating columns…")
                progress_bar.progress(8)
            elif fn_name == "get_column_sample":
                done = sum(1 for l in log_lines if "get_column_sample" in l)
                pct  = min(10 + int(done / max(total_cols, 1) * 80), 90)
                status_box.info(
                    f"🤖 Profiling column **{fn_args.get('column_name', '?')}** "
                    f"({done}/{total_cols})"
                )
                progress_bar.progress(pct)
            elif fn_name == "submit_profile_results":
                status_box.info("🤖 Finalising profile…")
                progress_bar.progress(95)

            # Execute tool
            tool_fn = dispatch.get(fn_name)
            if tool_fn is None:
                result = {"error": f"Unknown tool: {fn_name}"}
            else:
                try:
                    result = tool_fn(fn_args)
                except Exception as exc:
                    result = {"error": str(exc)}

            # Capture submitted profile with strict validation
            if fn_name == "submit_profile_results":
                candidate = _safe_profile_from_args(fn_args)
                if candidate is not None:
                    final_profile = candidate

            messages.append({
                "role":         "tool",
                "tool_call_id": tc_id,
                "content":      json.dumps(result if isinstance(result, dict) else {"result": str(result)}),
            })

        if final_profile is not None:
            break

    progress_bar.progress(100)
    status_box.success("✅ AI profiling complete!")
    return final_profile if isinstance(final_profile, dict) else {}
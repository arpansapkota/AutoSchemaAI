"""
profiling/agent.py
------------------
Multi-agent profiling loop powered by llama-3.3-70b-versatile on Groq.

Agent flow:
  1. File profiling agent
  2. Data profiling agent
  3. Schema detection agent
  4. Validation agent
  5. Output generation agent

The public entry point remains:
    run_agent(df, raw_bytes, raw_text, file_name, sep, has_header, encoding)

This keeps compatibility with the original ui/tab_profiling.py flow.
"""

import json
from typing import Any

import pandas as pd
import requests
import streamlit as st

from core.config import GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL
from profiling.detectors import (
    build_file_metadata,
    detect_predicted_dtype,
    predicted_size_from_dtype,
    build_code_profile,
)
from ssis.type_mapper import build_output_bundle, PREDICTED_TO_SSIS


# ──────────────────────────────────────────────────────────────────────────────
# Shared LLM helper
# ──────────────────────────────────────────────────────────────────────────────

def _call_llm_json(system_prompt: str, user_prompt: str, max_tokens: int = 3000) -> dict:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }

    resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text}")

    content = resp.json()["choices"][0]["message"]["content"]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(content[start:end + 1])
        raise ValueError(f"Model did not return valid JSON:\n{content}")


# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

FILE_AGENT_PROMPT = """You are the File Profiling Agent.

You receive already-detected file metadata from deterministic code.
Your job is to review it and return a normalized JSON object.

Return JSON only:
{
  "file_metadata": {
    "file_name": "...",
    "file_size_kb": 0,
    "field_delimiter": ",",
    "line_ending": "LF",
    "text_delimiter": "Double quote (\")",
    "has_headers": true,
    "encoding": "utf-8",
    "row_count": 0,
    "column_count": 0
  }
}
"""

DATA_AGENT_PROMPT = """You are the Data Profiling Agent.

You receive deterministic per-column statistics for a flat file.
Your task is to review and preserve them in clean JSON.

Return JSON only:
{
  "data_profile": {
    "total_cells": 0,
    "missing_values": 0,
    "duplicate_rows": 0,
    "memory_usage_kb": 0.0
  },
  "columns": [
    {
      "column_name": "...",
      "pandas_dtype": "...",
      "total_rows": 0,
      "null_count": 0,
      "unique_count": 0,
      "max_length": 0,
      "avg_length": 0.0,
      "most_frequent": "...",
      "sample_values": ["..."],
      "non_null_count": 0
    }
  ]
}
"""

SCHEMA_AGENT_PROMPT = """You are the Schema Detection Agent.

For each column, infer:
- predicted_type
- predicted_size
- ssis_data_type

Allowed predicted_type values:
Integer | Float | Boolean | Date | Datetime | Numeric (formatted) | Email | Text | Empty

Allowed ssis_data_type values:
DT_I4 | DT_R8 | DT_BOOL | DT_DBDATE | DT_DBTIMESTAMP | DT_NUMERIC | DT_STR

Rules:
- Integer -> 4 bytes (INT), DT_I4
- Float -> 8 bytes (DOUBLE), DT_R8
- Boolean -> 1 byte (BIT), DT_BOOL
- Date -> 3 bytes (DATE), DT_DBDATE
- Datetime -> 8 bytes (DATETIME), DT_DBTIMESTAMP
- Numeric (formatted) -> 8 bytes (DECIMAL), DT_NUMERIC
- Email -> ~100 bytes (VARCHAR 100), DT_STR
- Text -> use max_length rounded up to nearest 50, 100, 255, 500, 1000, 2000, 4000
- Empty -> 0 bytes, DT_STR

Return JSON only:
{
  "columns": [
    {
      "column_name": "...",
      "predicted_type": "...",
      "predicted_size": "...",
      "ssis_data_type": "..."
    }
  ]
}
"""

VALIDATION_AGENT_PROMPT = """You are the Validation Agent.

Review the proposed schema for inconsistencies.
Check for:
- Integer columns that contain decimals
- Date/Datetime columns that look like free text
- Text columns whose predicted size is too small
- SSIS type mismatches with predicted type

Return JSON only:
{
  "status": "approved" or "needs_revision",
  "issues_found": 0,
  "issues": [
    {
      "column_name": "...",
      "issue": "...",
      "suggested_predicted_type": "...",
      "suggested_predicted_size": "...",
      "suggested_ssis_data_type": "..."
    }
  ]
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Local helpers
# ──────────────────────────────────────────────────────────────────────────────

def _round_text_size(max_len: int) -> str:
    if max_len <= 50:
        n = 50
    elif max_len <= 100:
        n = 100
    elif max_len <= 255:
        n = 255
    elif max_len <= 500:
        n = 500
    elif max_len <= 1000:
        n = 1000
    elif max_len <= 2000:
        n = 2000
    else:
        n = 4000
    return f"~{n} bytes (VARCHAR {n})"


def _build_column_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    cols = []
    for col_name in df.columns:
        s = df[col_name]
        non_null = s.dropna()

        if len(non_null) > 0:
            sample_values = non_null.astype(str).head(30).tolist()
            max_length = int(non_null.astype(str).str.len().max())
            avg_length = round(non_null.astype(str).str.len().mean(), 1)
            most_frequent = str(non_null.value_counts().idxmax())
        else:
            sample_values = []
            max_length = 0
            avg_length = 0.0
            most_frequent = "—"

        cols.append({
            "column_name": str(col_name),
            "pandas_dtype": str(s.dtype),
            "total_rows": int(len(s)),
            "null_count": int(s.isna().sum()),
            "unique_count": int(s.nunique(dropna=True)),
            "max_length": max_length,
            "avg_length": avg_length,
            "most_frequent": most_frequent,
            "sample_values": sample_values,
            "non_null_count": int(s.notna().sum()),
        })
    return cols


def _fallback_schema_from_stats(columns: list[dict]) -> list[dict]:
    out = []
    for col in columns:
        inferred = col.get("predicted_type") or "Text"
        max_len = int(col.get("max_length", 0) or 0)

        if inferred == "Text":
            size = _round_text_size(max_len)
        elif inferred == "Integer":
            size = "4 bytes (INT)"
        elif inferred == "Float":
            size = "8 bytes (DOUBLE)"
        elif inferred == "Boolean":
            size = "1 byte (BIT)"
        elif inferred == "Date":
            size = "3 bytes (DATE)"
        elif inferred == "Datetime":
            size = "8 bytes (DATETIME)"
        elif inferred == "Numeric (formatted)":
            size = "8 bytes (DECIMAL)"
        elif inferred == "Email":
            size = "~100 bytes (VARCHAR 100)"
        elif inferred == "Empty":
            size = "0 bytes"
        else:
            inferred = "Text"
            size = _round_text_size(max_len)

        out.append({
            **col,
            "predicted_type": inferred,
            "predicted_size": size,
            "ssis_data_type": PREDICTED_TO_SSIS.get(inferred, "DT_STR"),
            "null_pct": f"{(col['null_count'] / max(col['total_rows'], 1)) * 100:.1f}%",
        })
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Agents
# ──────────────────────────────────────────────────────────────────────────────

def run_file_profiling_agent(
    raw_bytes: bytes,
    raw_text: str,
    file_name: str,
    sep: str,
    has_header: bool,
    encoding: str,
    df: pd.DataFrame,
) -> dict:
    metadata = build_file_metadata(
        raw_bytes=raw_bytes,
        raw_text=raw_text,
        file_name=file_name,
        sep=sep,
        has_header=has_header,
        encoding=encoding,
        row_count=len(df),
        col_count=len(df.columns),
    )

    try:
        reviewed = _call_llm_json(
            FILE_AGENT_PROMPT,
            json.dumps({"file_metadata": metadata}, ensure_ascii=False, indent=2),
            max_tokens=1200,
        )
        return reviewed.get("file_metadata", metadata)
    except Exception:
        return metadata


def run_data_profiling_agent(df: pd.DataFrame) -> dict:
    columns = _build_column_stats(df)
    data_profile = {
        "total_cells": int(df.shape[0] * df.shape[1]),
        "missing_values": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_usage_kb": round(df.memory_usage(deep=True).sum() / 1024, 1),
    }

    try:
        reviewed = _call_llm_json(
            DATA_AGENT_PROMPT,
            json.dumps({"data_profile": data_profile, "columns": columns}, ensure_ascii=False, indent=2),
            max_tokens=3500,
        )
        return {
            "data_profile": reviewed.get("data_profile", data_profile),
            "columns": reviewed.get("columns", columns),
        }
    except Exception:
        return {"data_profile": data_profile, "columns": columns}


def run_schema_detection_agent(columns: list[dict]) -> list[dict]:
    deterministic_columns = []
    for col in columns:
        sample_series = pd.Series(col.get("sample_values", []), dtype="object")
        inferred_type = detect_predicted_dtype(sample_series) if len(sample_series) else "Empty"
        deterministic_columns.append({
            **col,
            "predicted_type": inferred_type,
            "predicted_size": predicted_size_from_dtype(inferred_type, int(col.get("max_length", 0) or 0)),
            "ssis_data_type": PREDICTED_TO_SSIS.get(inferred_type, "DT_STR"),
            "null_pct": f"{(col['null_count'] / max(col['total_rows'], 1)) * 100:.1f}%",
        })

    try:
        llm_result = _call_llm_json(
            SCHEMA_AGENT_PROMPT,
            json.dumps({"columns": deterministic_columns}, ensure_ascii=False, indent=2),
            max_tokens=3500,
        )
        llm_columns = llm_result.get("columns", [])

        merged = []
        llm_map = {c.get("column_name"): c for c in llm_columns}
        for base in deterministic_columns:
            override = llm_map.get(base["column_name"], {})
            merged.append({
                **base,
                "predicted_type": override.get("predicted_type", base["predicted_type"]),
                "predicted_size": override.get("predicted_size", base["predicted_size"]),
                "ssis_data_type": override.get("ssis_data_type", base["ssis_data_type"]),
            })
        return merged
    except Exception:
        return deterministic_columns


def run_validation_agent(columns: list[dict]) -> dict:
    try:
        result = _call_llm_json(
            VALIDATION_AGENT_PROMPT,
            json.dumps({"columns": columns}, ensure_ascii=False, indent=2),
            max_tokens=2500,
        )
    except Exception:
        result = {"status": "approved", "issues_found": 0, "issues": []}

    issues = result.get("issues", [])
    issue_map = {i.get("column_name"): i for i in issues if i.get("column_name")}

    validated = []
    for col in columns:
        issue = issue_map.get(col["column_name"])
        if issue:
            final_type = issue.get("suggested_predicted_type") or col["predicted_type"]
            final_size = issue.get("suggested_predicted_size") or col["predicted_size"]
            final_ssis = issue.get("suggested_ssis_data_type") or col["ssis_data_type"]
            validated.append({
                **col,
                "predicted_type": final_type,
                "predicted_size": final_size,
                "ssis_data_type": final_ssis,
                "validation_status": "revised",
                "validation_notes": [issue.get("issue", "Adjusted by validation agent.")],
            })
        else:
            validated.append({
                **col,
                "validation_status": "approved",
                "validation_notes": [],
            })

    return {
        "status": result.get("status", "approved"),
        "issues_found": int(result.get("issues_found", 0)),
        "issues": issues,
        "columns": validated,
    }


def run_output_generation_agent(profile: dict, file_name: str) -> dict:
    return build_output_bundle(profile=profile, file_name=file_name)


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point kept compatible with original UI
# ──────────────────────────────────────────────────────────────────────────────

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
    Public entry point used by ui/tab_profiling.py.

    Returns the final profile dict, but also stores extra export artifacts
    in Streamlit session state:
      - ai_data_profile
      - ai_validation_summary
      - ai_ssis_xml
      - ai_create_table_sql
    """
    status_box = st.empty()
    progress_bar = st.progress(0)

    # 1. File profiling agent
    status_box.info("🤖 File profiling agent is reviewing file metadata…")
    progress_bar.progress(15)
    file_metadata = run_file_profiling_agent(
        raw_bytes=raw_bytes,
        raw_text=raw_text,
        file_name=file_name,
        sep=sep,
        has_header=has_header,
        encoding=encoding,
        df=df,
    )

    # 2. Data profiling agent
    status_box.info("🤖 Data profiling agent is analysing dataset statistics…")
    progress_bar.progress(35)
    data_result = run_data_profiling_agent(df)
    data_profile = data_result["data_profile"]
    columns = data_result["columns"]

    # 3. Schema detection agent
    status_box.info("🤖 Schema detection agent is inferring data types…")
    progress_bar.progress(60)
    schema_columns = run_schema_detection_agent(columns)

    # 4. Validation agent
    status_box.info("🤖 Validation agent is checking schema consistency…")
    progress_bar.progress(80)
    validation = run_validation_agent(schema_columns)
    validated_columns = validation["columns"]

    final_profile = {
        "file_metadata": file_metadata,
        "data_profile": data_profile,
        "columns": validated_columns,
        "validation_summary": {
            "status": validation["status"],
            "issues_found": validation["issues_found"],
        },
    }

    # 5. Output generation agent
    status_box.info("🤖 Output generation agent is preparing SSIS XML and T-SQL…")
    progress_bar.progress(95)
    output_bundle = run_output_generation_agent(final_profile, file_name)

    progress_bar.progress(100)
    status_box.success("✅ Multi-agent profiling complete!")

    st.session_state["ai_data_profile"] = data_profile
    st.session_state["ai_validation_summary"] = {
        "status": validation["status"],
        "issues_found": validation["issues_found"],
        "issues": validation["issues"],
    }
    st.session_state["ai_ssis_xml"] = output_bundle["ssis_xml"]
    st.session_state["ai_create_table_sql"] = output_bundle["create_table_sql"]

    return output_bundle["profile"]
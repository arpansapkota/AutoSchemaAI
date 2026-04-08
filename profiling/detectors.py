"""
profiling/detectors.py
----------------------
Pure-Python / pandas detection helpers used by both the
'Code logic' profiling mode and the AI agent's tool functions.
No Streamlit or AI imports here — this module is side-effect-free.
"""

import re

import pandas as pd


# ── File-level detectors ───────────────────────────────────────────────────────

def detect_line_ending(raw_bytes: bytes) -> str:
    crlf = raw_bytes.count(b"\r\n")
    lf   = raw_bytes.count(b"\n") - crlf
    cr   = raw_bytes.count(b"\r") - crlf
    if crlf >= lf and crlf >= cr and crlf > 0:
        return "CRLF"
    if lf >= cr and lf > 0:
        return "LF"
    if cr > 0:
        return "CR"
    return "None"


def detect_text_delimiter(raw_text: str) -> str:
    sample = raw_text[:8192]
    dq, sq = sample.count('"'), sample.count("'")
    if dq == 0 and sq == 0:
        return "None"
    return 'Double quote (")' if dq >= sq else "Single quote (')"


def build_file_metadata(
    raw_bytes: bytes,
    raw_text: str,
    file_name: str,
    sep: str,
    has_header: bool,
    encoding: str,
    row_count: int,
    col_count: int,
) -> dict:
    """Assemble the complete file-level metadata dict."""
    fd_map = {",": ",", ";": ";", "\t": "\\t", "|": "|", " ": "space"}
    return {
        "file_name":       file_name,
        "file_size_kb":    round(len(raw_bytes) / 1024, 2),
        "field_delimiter": fd_map.get(sep, sep),
        "line_ending":     detect_line_ending(raw_bytes),
        "text_delimiter":  detect_text_delimiter(raw_text),
        "has_headers":     has_header,
        "encoding":        encoding,
        "row_count":       row_count,
        "column_count":    col_count,
    }


# ── Column-level detectors ─────────────────────────────────────────────────────

def detect_predicted_dtype(series: pd.Series) -> str:
    """Infer a human-friendly semantic type from a column's values."""
    s = series.dropna().astype(str).str.strip()
    if s.empty:
        return "Empty"
    try:
        s.apply(lambda x: int(x.replace(",", "")))
        return "Integer"
    except Exception:
        pass
    try:
        s.apply(lambda x: float(x.replace(",", "")))
        return "Float"
    except Exception:
        pass
    date_pat = re.compile(
        r"^\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4}(\s+\d{1,2}:\d{2}(:\d{2})?)?$"
    )
    if s.apply(lambda x: bool(date_pat.match(x))).mean() > 0.7:
        return "Datetime" if s.str.contains(r"\d{1,2}:\d{2}").any() else "Date"
    bool_vals = {"true", "false", "yes", "no", "1", "0", "y", "n"}
    if s.str.lower().isin(bool_vals).mean() > 0.8:
        return "Boolean"
    if s.str.match(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$").mean() > 0.7:
        return "Email"
    if s.str.match(r"^[\$£€]?[\d,]+\.?\d*%?$").mean() > 0.7:
        return "Numeric (formatted)"
    return "Text"


def predicted_col_size(series: pd.Series) -> str:
    """
    Return a storage size estimate based strictly on predicted semantic type.
    Fixed types get their canonical DB size; Text/Email get a VARCHAR sized
    to the column's actual maximum observed length.
    """
    ptype = detect_predicted_dtype(series)
    fixed = {
        "Integer":             "4 bytes (INT)",
        "Float":               "8 bytes (DOUBLE)",
        "Boolean":             "1 byte (BIT)",
        "Date":                "3 bytes (DATE)",
        "Datetime":            "8 bytes (DATETIME)",
        "Numeric (formatted)": "8 bytes (DECIMAL)",
        "Empty":               "0 bytes",
    }
    if ptype in fixed:
        return fixed[ptype]
    # For Text / Email — size to actual max observed length
    max_len = series.dropna().astype(str).str.len().max()
    if pd.isna(max_len):
        return "~50 bytes (VARCHAR 50)"
    max_len = int(max_len)
    for boundary in [50, 100, 255, 500, 1000, 2000, 4000]:
        if max_len <= boundary:
            return f"~{boundary} bytes (VARCHAR {boundary})"
    return "~4000 bytes (VARCHAR 4000)"


def get_column_stats(series: pd.Series) -> dict:
    """Return a stat bundle for one column (used by code-logic mode)."""
    null_count   = int(series.isna().sum())
    total        = len(series)
    non_null     = total - null_count
    unique_count = int(series.nunique())
    avg_len      = (
        round(series.dropna().astype(str).str.len().mean(), 1)
        if series.notna().any() else 0
    )
    pred_type = detect_predicted_dtype(series)
    pred_size = predicted_col_size(series)
    return {
        "null_count":     null_count,
        "non_null_count": non_null,
        "null_pct":       f"{null_count / total * 100:.1f}%" if total else "0%",
        "unique_count":   unique_count,
        "avg_length":     avg_len,
        "pandas_dtype":   str(series.dtype),
        "predicted_type": pred_type,
        "predicted_size": pred_size,
    }


def build_code_profile(
    df: pd.DataFrame,
    raw_bytes: bytes,
    raw_text: str,
    file_name: str,
    sep: str,
    has_header: bool,
    encoding: str,
) -> dict:
    """
    Build a complete profile dict using only deterministic code logic —
    no AI involved.  Returns the same schema as the AI agent so the rest
    of the app can treat both identically.
    """
    from ssis.type_mapper import PREDICTED_TO_SSIS   # local import avoids circular deps

    file_metadata = build_file_metadata(
        raw_bytes, raw_text, file_name, sep,
        has_header, encoding, len(df), len(df.columns),
    )

    columns = []
    for col in df.columns:
        stats     = get_column_stats(df[col])
        ssis_type = PREDICTED_TO_SSIS.get(stats["predicted_type"], "DT_STR")
        columns.append({
            "column_name":    col,
            **stats,
            "ssis_data_type": ssis_type,
        })

    return {"file_metadata": file_metadata, "columns": columns}
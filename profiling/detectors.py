import re
import pandas as pd


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


def detect_predicted_dtype(series: pd.Series) -> str:
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

    if s.str.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$").mean() > 0.8:
        return "Email"

    if s.str.contains(r"[,$%]").mean() > 0.5:
        return "Numeric (formatted)"

    return "Text"


def predicted_size_from_dtype(predicted_type: str, max_length: int = 0) -> str:
    if predicted_type == "Integer":
        return "4 bytes (INT)"
    if predicted_type == "Float":
        return "8 bytes (DOUBLE)"
    if predicted_type == "Boolean":
        return "1 byte (BIT)"
    if predicted_type == "Date":
        return "3 bytes (DATE)"
    if predicted_type == "Datetime":
        return "8 bytes (DATETIME)"
    if predicted_type == "Numeric (formatted)":
        return "8 bytes (DECIMAL)"
    if predicted_type == "Email":
        return "~100 bytes (VARCHAR 100)"
    if predicted_type == "Empty":
        return "0 bytes"

    if max_length <= 50:
        n = 50
    elif max_length <= 100:
        n = 100
    elif max_length <= 255:
        n = 255
    elif max_length <= 500:
        n = 500
    elif max_length <= 1000:
        n = 1000
    elif max_length <= 2000:
        n = 2000
    else:
        n = 4000

    return f"~{n} bytes (VARCHAR {n})"


def build_code_profile(
    df: pd.DataFrame,
    raw_bytes: bytes,
    raw_text: str,
    file_name: str,
    sep: str,
    has_header: bool,
    encoding: str,
) -> dict:
    file_metadata = build_file_metadata(
        raw_bytes=raw_bytes,
        raw_text=raw_text,
        file_name=file_name,
        sep=sep,
        has_header=has_header,
        encoding=encoding,
        row_count=len(df),
        col_count=len(df.columns),
    )

    columns = []
    for col_name in df.columns:
        s = df[col_name]
        non_null = s.dropna()

        max_length = int(non_null.astype(str).str.len().max()) if len(non_null) else 0
        avg_length = round(non_null.astype(str).str.len().mean(), 1) if len(non_null) else 0.0
        predicted_type = detect_predicted_dtype(s)

        columns.append({
            "column_name": str(col_name),
            "pandas_dtype": str(s.dtype),
            "predicted_type": predicted_type,
            "predicted_size": predicted_size_from_dtype(predicted_type, max_length),
            "ssis_data_type": {
                "Integer": "DT_I4",
                "Float": "DT_R8",
                "Boolean": "DT_BOOL",
                "Date": "DT_DBDATE",
                "Datetime": "DT_DBTIMESTAMP",
                "Numeric (formatted)": "DT_NUMERIC",
                "Email": "DT_STR",
                "Text": "DT_STR",
                "Empty": "DT_STR",
            }.get(predicted_type, "DT_STR"),
            "non_null_count": int(s.notna().sum()),
            "null_count": int(s.isna().sum()),
            "null_pct": f"{(s.isna().sum() / max(len(s), 1)) * 100:.1f}%",
            "unique_count": int(s.nunique(dropna=True)),
            "avg_length": avg_length,
            "max_length": max_length,
        })

    return {
        "file_metadata": file_metadata,
        "columns": columns,
    }
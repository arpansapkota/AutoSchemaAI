"""
ssis/type_mapper.py
-------------------
Maps predicted semantic types to SSIS DT_ data types, builds the
DTS:ConnectionManager XML fragment for a Flat File Connection Manager,
and generates T-SQL CREATE TABLE output from the same validated profile.
"""

import os
import re
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom

# ── Type mappings ──────────────────────────────────────────────────────────────

PREDICTED_TO_SSIS: dict[str, str] = {
    "Integer":             "DT_I4",
    "Float":               "DT_R8",
    "Boolean":             "DT_BOOL",
    "Date":                "DT_DBDATE",
    "Datetime":            "DT_DBTIMESTAMP",
    "Numeric (formatted)": "DT_NUMERIC",
    "Email":               "DT_STR",
    "Text":                "DT_STR",
    "Empty":               "DT_STR",
}

SSIS_TYPE_ATTRS: dict[str, dict] = {
    "DT_I4":          {"Length": "0",   "Precision": "10", "Scale": "0", "CodePage": "0"},
    "DT_R8":          {"Length": "0",   "Precision": "15", "Scale": "0", "CodePage": "0"},
    "DT_BOOL":        {"Length": "0",   "Precision": "0",  "Scale": "0", "CodePage": "0"},
    "DT_DBDATE":      {"Length": "0",   "Precision": "0",  "Scale": "0", "CodePage": "0"},
    "DT_DBTIMESTAMP": {"Length": "0",   "Precision": "0",  "Scale": "3", "CodePage": "0"},
    "DT_NUMERIC":     {"Length": "0",   "Precision": "18", "Scale": "4", "CodePage": "0"},
    "DT_STR":         {"Length": "255", "Precision": "0",  "Scale": "0", "CodePage": "1252"},
}

LINE_ENDING_SSIS: dict[str, str] = {
    "CRLF": "CRLF", "LF": "LF", "CR": "CR", "None": "LF",
}

TEXT_DELIM_SSIS: dict[str, str] = {
    'Double quote (")': '"',
    "Single quote (')": "'",
    "None":             "",
}

ENCODING_CODEPAGE: dict[str, str] = {
    "utf-8":   "65001",
    "latin-1": "1252",
    "utf-16":  "1200",
}


def _str_length_from_size(predicted_size: str) -> str:
    """Extract VARCHAR length from a size string like '~80 bytes (VARCHAR 100)'."""
    m = re.search(r"VARCHAR\s*(\d+)", predicted_size or "")
    return m.group(1) if m else "255"


# ── Existing SSIS XML builder ─────────────────────────────────────────────────

def build_ssis_xml(profile: dict, file_name: str) -> str:
    """
    Generate a SSIS DTS:ConnectionManager XML fragment from a profile dict.
    Compatible with SQL Server Integration Services .dtsx packages.
    """
    fm        = profile.get("file_metadata", {})
    cols_data = profile.get("columns", [])

    conn_name   = file_name.rsplit(".", 1)[0]
    conn_id     = "{" + str(uuid.uuid4()).upper() + "}"
    row_delim   = LINE_ENDING_SSIS.get(fm.get("line_ending", "LF"), "LF")
    text_qual   = TEXT_DELIM_SSIS.get(fm.get("text_delimiter", "None"), "")
    field_delim = fm.get("field_delimiter", ",")
    col_delim   = "\t" if field_delim == "\\t" else field_delim
    code_page   = ENCODING_CODEPAGE.get(fm.get("encoding", "utf-8"), "1252")

    root = ET.Element("DTS:ConnectionManager", {
        "xmlns:DTS":        "www.microsoft.com/SqlServer/Dts",
        "DTS:refId":        f"Package.ConnectionManagers[{conn_name}]",
        "DTS:CreationName": "FLATFILE",
        "DTS:DTSID":        conn_id,
        "DTS:ObjectName":   conn_name,
    })
    obj_data = ET.SubElement(root, "DTS:ObjectData")
    ff_cm = ET.SubElement(obj_data, "DTS:FlatFileConnectionManager", {
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
        attrs = SSIS_TYPE_ATTRS.get(ssis_type, SSIS_TYPE_ATTRS["DT_STR"]).copy()
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
    pretty = minidom.parseString(raw_xml).toprettyxml(indent="  ")
    return "\n".join(pretty.split("\n")[1:])


# ── New T-SQL helpers ─────────────────────────────────────────────────────────

def _sanitize_sql_identifier(name: str) -> str:
    if not name:
        return "unnamed_column"
    safe = str(name).strip()
    safe = re.sub(r"\s+", "_", safe)
    safe = re.sub(r"[^A-Za-z0-9_]", "_", safe)
    if re.match(r"^\d", safe):
        safe = f"col_{safe}"
    return safe


def _default_table_name(file_name: str) -> str:
    base = os.path.splitext(os.path.basename(file_name or "input_file"))[0]
    return _sanitize_sql_identifier(base)


def predicted_to_tsql_type(col: dict) -> str:
    predicted_type = col.get("predicted_type", "Text")
    predicted_size = col.get("predicted_size", "")
    max_length = int(col.get("max_length", 0) or 0)

    if predicted_type == "Integer":
        return "INT"
    if predicted_type == "Float":
        return "FLOAT"
    if predicted_type == "Boolean":
        return "BIT"
    if predicted_type == "Date":
        return "DATE"
    if predicted_type == "Datetime":
        return "DATETIME2"
    if predicted_type == "Numeric (formatted)":
        return "DECIMAL(18,4)"
    if predicted_type == "Email":
        return "VARCHAR(100)"
    if predicted_type in ("Text", "Empty"):
        try:
            length = int(_str_length_from_size(predicted_size))
        except ValueError:
            length = max_length if max_length > 0 else 255

        if length <= 50:
            return "VARCHAR(50)"
        if length <= 100:
            return "VARCHAR(100)"
        if length <= 255:
            return "VARCHAR(255)"
        if length <= 500:
            return "VARCHAR(500)"
        if length <= 1000:
            return "VARCHAR(1000)"
        if length <= 2000:
            return "VARCHAR(2000)"
        if length <= 4000:
            return "VARCHAR(4000)"
        return "VARCHAR(MAX)"

    return "VARCHAR(255)"


def build_create_table_sql(
    profile: dict,
    file_name: str,
    table_name: str | None = None,
    schema_name: str = "dbo",
) -> str:
    fm = profile.get("file_metadata", {})
    cols_data = profile.get("columns", [])

    resolved_table = table_name or _default_table_name(fm.get("file_name") or file_name)

    lines = [f"CREATE TABLE [{schema_name}].[{resolved_table}] ("]
    col_defs = []

    for col in cols_data:
        col_name = _sanitize_sql_identifier(col.get("column_name", "unnamed_column"))
        sql_type = predicted_to_tsql_type(col)
        nullable = "NULL" if int(col.get("null_count", 0)) > 0 else "NOT NULL"
        col_defs.append(f"    [{col_name}] {sql_type} {nullable}")

    lines.append(",\n".join(col_defs))
    lines.append(");")

    return "\n".join(lines)


def build_output_bundle(
    profile: dict,
    file_name: str,
    table_name: str | None = None,
    schema_name: str = "dbo",
) -> dict:
    return {
        "profile": profile,
        "ssis_xml": build_ssis_xml(profile, file_name),
        "create_table_sql": build_create_table_sql(
            profile=profile,
            file_name=file_name,
            table_name=table_name,
            schema_name=schema_name,
        ),
    }
"""
core/file_parser.py
-------------------
Responsible solely for turning raw bytes from an uploaded flat file into
a pandas DataFrame.  No profiling logic lives here.
"""

import io

import pandas as pd


def resolve_separator(delimiter_choice: str, raw_text: str) -> str:
    """
    Convert the user's delimiter choice into the actual separator character.
    When 'Auto-detect' is chosen, sniff the first 4 KB of the file.
    """
    if delimiter_choice == "Auto-detect":
        counts = {d: raw_text[:4096].count(d) for d in [",", ";", "\t", "|"]}
        return max(counts, key=counts.get)
    return "\t" if delimiter_choice == "\\t" else delimiter_choice


def parse_flat_file(
    raw_bytes: bytes,
    delimiter_choice: str,
    has_header: bool,
    skip_rows: int,
    encoding: str,
) -> tuple[pd.DataFrame, str]:
    """
    Parse a flat file from raw bytes.

    Returns
    -------
    df  : parsed DataFrame
    sep : the actual separator character that was used
    """
    raw_text = raw_bytes.decode(encoding, errors="replace")
    sep      = resolve_separator(delimiter_choice, raw_text)

    df = pd.read_csv(
        io.BytesIO(raw_bytes),
        sep=sep,
        header=0 if has_header else None,
        skiprows=int(skip_rows),
        encoding=encoding,
        on_bad_lines="warn",
    )
    return df, sep


def delimiter_label(sep: str) -> str:
    """Return a human-readable label for a separator character."""
    return {",": ",", ";": ";", "\t": "\\t", "|": "|", " ": "space"}.get(sep, sep)
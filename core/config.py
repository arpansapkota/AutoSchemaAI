"""
core/config.py
--------------
Loads application configuration from config.ini located next to the
project root.  Exposes GROQ_API_KEY and GROQ_MODEL as module-level
constants so every other module can import them without re-reading disk.
"""

import configparser
import os

import streamlit as st

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)          # one level up from core/
CONFIG_PATH  = os.path.join(_PROJECT_ROOT, "config.ini")

# ── Model ──────────────────────────────────────────────────────────────────────
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def load_api_key(path: str = CONFIG_PATH) -> str:
    """
    Read the Groq API key from config.ini.
    Stops the Streamlit app with a user-friendly error if anything is wrong.
    """
    if not os.path.exists(path):
        st.error(
            f"**config.ini not found.**\n\n"
            f"Expected: `{path}`\n\n"
            "Create it with:\n```ini\n[groq]\napi_key = gsk_YOUR_KEY\n```"
        )
        st.stop()

    cfg = configparser.ConfigParser()
    cfg.read(path)

    try:
        key = cfg["groq"]["api_key"].strip()
    except KeyError:
        st.error(
            "**config.ini** is missing the `[groq]` section or `api_key` field.\n\n"
            "Expected:\n```ini\n[groq]\napi_key = gsk_YOUR_KEY\n```"
        )
        st.stop()

    if not key or key == "gsk_YOUR_GROQ_API_KEY_HERE":
        st.error(
            f"Groq API key is not set in `{path}`.\n\n"
            "Replace the placeholder with your real key."
        )
        st.stop()

    return key


# Load once at import time — all modules use this value
GROQ_API_KEY: str = load_api_key()
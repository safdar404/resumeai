"""Application configuration.

Secrets are read from environment variables first and then from Streamlit
secrets. Values are returned exactly as stored: nothing is stripped or
replaced, so formatting problems can be reported instead of silently fixed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:  # local development: load .env if present (never overrides real environment variables)
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:  # optional dependency
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
EXAMPLES_DIR = ROOT_DIR / "examples"

APP_NAME = "CareerRainbow AI"
APP_TAGLINE = "Agentic CV & Resume Studio"

MAX_UPLOAD_MB = 5
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = (".pdf", ".docx", ".txt", ".json")
MAX_JOB_DESCRIPTION_CHARS = 20_000
MAX_CHAT_MESSAGE_CHARS = 6_000

LLM_MAX_TRANSIENT_RETRIES = 2      # bounded retries for timeouts / rate limits / 5xx
LLM_MAX_FORMAT_RETRIES = 1         # one retry for malformed structured output
LLM_TIMEOUT_SECONDS = 60
MAX_DRAFT_ATTEMPTS = 2             # drafting <-> factual review loop bound

PROVIDERS = {
    "none": {"label": "Offline rules engine (no AI provider)", "default_model": "", "secret": None},
    "openai": {"label": "OpenAI", "default_model": "gpt-4o-mini", "secret": "OPENAI_API_KEY"},
    "anthropic": {"label": "Anthropic", "default_model": "claude-sonnet-4-5", "secret": "ANTHROPIC_API_KEY"},
    "openai_compatible": {
        "label": "OpenAI-compatible endpoint (Groq, OpenRouter, Ollama, ...)",
        "default_model": "llama-3.3-70b-versatile",
        "secret": "OPENAI_COMPATIBLE_API_KEY",
    },
}

READINESS_NOTE = (
    "This is an internal readiness assessment, not a score from an employer's ATS. "
    "Results vary across systems and job requirements."
)


def get_secret(name: str) -> Optional[str]:
    """Return a secret from the environment or Streamlit secrets, unmodified."""
    if not name:
        return None
    value = os.environ.get(name)
    if value is not None:
        return value
    try:  # Streamlit is optional for library use and tests
        import streamlit as st

        if name in st.secrets:
            raw = st.secrets[name]
            return raw if isinstance(raw, str) else str(raw)
    except Exception:  # secrets file missing or not running under Streamlit
        return None
    return None


@dataclass
class ProviderDefaults:
    provider: str = "none"
    model: str = ""
    base_url: str = ""
    extra: dict = field(default_factory=dict)


def provider_defaults() -> ProviderDefaults:
    provider = (get_secret("LLM_PROVIDER") or "none")
    if provider not in PROVIDERS:
        provider = "none"
    model = get_secret("LLM_MODEL") or PROVIDERS[provider]["default_model"]
    base_url = get_secret("OPENAI_COMPATIBLE_BASE_URL") or ""
    return ProviderDefaults(provider=provider, model=model, base_url=base_url)

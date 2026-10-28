"""Credential checks that never print, log or modify the credential."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CredentialCheck:
    ok: bool
    problems: list[str]


def check_api_key(key: str | None) -> CredentialCheck:
    """Report formatting problems without revealing the key or altering it.

    Characters are NOT stripped or replaced: a key with stray whitespace is
    rejected so the user can fix the source (secrets file, env var, paste).
    """
    problems: list[str] = []
    if key is None or key == "":
        return CredentialCheck(False, ["No API key was provided."])
    if key != key.strip():
        problems.append("The key starts or ends with whitespace or a line break.")
    if any(ch.isspace() for ch in key.strip()):
        problems.append("The key contains spaces, tabs or line breaks inside it.")
    non_ascii = sum(1 for ch in key if ord(ch) > 127)
    if non_ascii:
        problems.append(
            f"The key contains {non_ascii} non-ASCII character(s) (often smart quotes or "
            "invisible characters from copy-paste)."
        )
    if key[:1] in "\"'" or key[-1:] in "\"'":
        problems.append("The key appears to be wrapped in quotation marks.")
    if len(key.strip()) < 16:
        problems.append("The key is unusually short; it may be truncated.")
    return CredentialCheck(not problems, problems)


def mask(key: str | None) -> str:
    """Safe display form: never shows key material, only its length."""
    if not key:
        return "(not set)"
    return f"(set, {len(key)} characters)"

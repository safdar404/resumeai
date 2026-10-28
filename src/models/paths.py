"""Read and write nested values in a profile dict using paths like
``experience[0].bullets[2]``."""
from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$")


class PathError(KeyError):
    pass


def _steps(path: str) -> list[tuple[str, int | None]]:
    steps = []
    for part in path.split("."):
        m = _TOKEN.match(part)
        if not m:
            raise PathError(f"Invalid path segment: {part!r}")
        steps.append((m.group(1), int(m.group(2)) if m.group(2) is not None else None))
    return steps


def get_path(data: dict, path: str) -> Any:
    cur: Any = data
    for key, idx in _steps(path):
        if not isinstance(cur, dict) or key not in cur:
            raise PathError(path)
        cur = cur[key]
        if idx is not None:
            if not isinstance(cur, list) or idx >= len(cur):
                raise PathError(path)
            cur = cur[idx]
    return cur


def set_path(data: dict, path: str, value: Any) -> None:
    steps = _steps(path)
    cur: Any = data
    for n, (key, idx) in enumerate(steps):
        last = n == len(steps) - 1
        if not isinstance(cur, dict) or key not in cur:
            raise PathError(path)
        if idx is None:
            if last:
                cur[key] = value
                return
            cur = cur[key]
        else:
            lst = cur[key]
            if not isinstance(lst, list) or idx >= len(lst):
                raise PathError(path)
            if last:
                lst[idx] = value
                return
            cur = lst[idx]


def path_exists(data: dict, path: str) -> bool:
    try:
        get_path(data, path)
        return True
    except PathError:
        return False


def describe_path(path: str) -> str:
    """Human-friendly label for a profile path."""
    try:
        steps = _steps(path)
    except PathError:
        return path
    labels = {
        "experience": "Experience", "education": "Education", "projects": "Project",
        "bullets": "bullet", "details": "detail", "summary": "Summary", "headline": "Headline",
        "awards": "Award", "volunteering": "Volunteering", "description": "description",
        "contact": "Contact", "certifications": "Certification", "skills": "Skills",
    }
    out = []
    for key, idx in steps:
        lbl = labels.get(key, key.replace("_", " "))
        out.append(f"{lbl} {idx + 1}" if idx is not None else lbl)
    return " › ".join(out)

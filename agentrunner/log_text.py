"""Decode captured process output for the CLI and task viewers."""

from __future__ import annotations

import os
from pathlib import Path


def decode_output(data: bytes) -> str:
    """Prefer UTF-8, then the Windows ANSI code page used by native tools."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        if os.name == "nt":
            return data.decode("mbcs", errors="replace")
        return data.decode("utf-8", errors="replace")


def read_tail(path: Path, limit: int) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as source:
        source.seek(0, 2)
        start = max(0, source.tell() - limit)
        source.seek(start)
        data = source.read()
    if start:
        boundary = data.find(b"\n")
        if boundary >= 0:
            data = data[boundary + 1:]
    return decode_output(data)

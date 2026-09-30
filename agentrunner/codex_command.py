"""Remember the Codex CLI supplied by a submission for later desktop launches."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from . import store


def remember() -> str | None:
    executable = shutil.which("codex")
    if not executable:
        return None
    executable = str(Path(executable).resolve())
    target = store.home() / "codex-executable.txt"
    temporary: str | None = None
    try:
        try:
            if target.is_file() and target.read_text(encoding="utf-8") == executable:
                return executable
        except UnicodeError:
            pass
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".codex-executable-", delete=False) as output:
            temporary = output.name
            output.write(executable)
        os.replace(temporary, target)
    except OSError:
        # A writable cache is optional when this process already has the CLI.
        pass
    finally:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass
    return executable


def resolve() -> str:
    executable = remember()
    if executable:
        return executable
    try:
        cached = Path((store.home() / "codex-executable.txt").read_text(encoding="utf-8").strip())
        if cached.is_absolute() and cached.is_file():
            return str(cached)
    except (OSError, UnicodeError):
        pass
    raise FileNotFoundError("Codex CLI unavailable; submit a task from Codex to refresh its executable path")

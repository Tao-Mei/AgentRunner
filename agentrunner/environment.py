"""Build a deliberately small environment for task processes."""

from __future__ import annotations

import os
import re


NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SENSITIVE = re.compile(r"(^|_)(KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL|AUTH)(_|$)", re.IGNORECASE)
BASE = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL",
    "PYTHONIOENCODING", "PYTHONUTF8", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
}


def validate(names: list[str] | None) -> list[str]:
    if names is None:
        return []
    if not isinstance(names, list) or not all(isinstance(name, str) and NAME.fullmatch(name) for name in names):
        raise ValueError("pass_env must be a list of environment variable names")
    if len(names) != len(set(names)):
        raise ValueError("pass_env contains duplicate names")
    for name in names:
        if name not in os.environ:
            raise ValueError(f"Environment variable is not defined: {name}")
        if SENSITIVE.search(name) and len(os.environ[name]) < 4:
            raise ValueError(f"Sensitive variable {name} must contain at least four characters for log redaction")
    return names


def child_environment(names: list[str] | None = None) -> dict[str, str]:
    selected = set(validate(names))
    selected.update(name for name in os.environ if name.upper() in BASE)
    return {name: os.environ[name] for name in selected}


def known_secrets() -> list[str]:
    """Values already known to the supervisor that should never enter captured logs."""
    return sorted({value for name, value in os.environ.items() if SENSITIVE.search(name) and len(value) >= 4},
                  key=len, reverse=True)

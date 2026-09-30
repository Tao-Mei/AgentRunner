"""Check independent launches and stale-path refresh without sending messages."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from agentrunner import codex_command


def main() -> None:
    live = shutil.which("codex")
    test_root = Path(__file__).resolve().parent / ".probe-state"
    test_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=test_root, prefix="codex-path-") as root:
        with patch.dict(os.environ, {"AGENTRUNNER_HOME": root}):
            # Exercise executable relocation on app update and missing cache.
            first = Path(root) / "old-codex.exe"
            second = Path(root) / "new-codex.exe"
            first.touch()
            second.touch()
            with patch("shutil.which", return_value=str(first)):
                assert codex_command.remember() == str(first.resolve())
            with patch("shutil.which", return_value=None):
                assert codex_command.resolve() == str(first.resolve())
            first.unlink()
            with patch("shutil.which", return_value=None):
                try:
                    codex_command.resolve()
                except FileNotFoundError:
                    pass
                else:
                    raise AssertionError("Missing CLI was accepted")
            with patch("shutil.which", return_value=str(second)):
                assert codex_command.resolve() == str(second.resolve())
            if live:
                with patch("shutil.which", return_value=live):
                    codex_command.remember()
                system_path = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32")
                with patch.dict(os.environ, {"PATH": system_path}):
                    assert shutil.which("codex") is None
                    executable = codex_command.resolve()
                    result = subprocess.run([executable, "queue", "--help"],
                                            capture_output=True, timeout=20)
                    assert result.returncode == 0, result.stderr
                print("Actual Codex queue help works without Codex on PATH")
            else:
                print("Actual Codex check skipped: CLI absent; resolver cases passed")


if __name__ == "__main__":
    main()

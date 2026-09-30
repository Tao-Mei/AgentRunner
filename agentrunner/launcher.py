"""On-demand local service and desktop process management."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import store


SERVICE_PORT = 8765


def service_available() -> bool:
    token_path = store.home() / "ui-token"
    if not token_path.is_file():
        return False
    try:
        token = token_path.read_text(encoding="ascii").strip()
        request = Request(
            f"http://127.0.0.1:{SERVICE_PORT}/api/jobs",
            headers={"Authorization": "Bearer " + token},
        )
        with urlopen(request, timeout=0.4) as response:
            return response.status == 200
    except (OSError, HTTPError, URLError, ValueError):
        return False


def detached_command(mode: str) -> tuple[list[str], Path]:
    if getattr(sys, "frozen", False):
        return [sys.executable, mode], store.home()
    return [sys.executable, "-m", "agentrunner", mode], Path(__file__).resolve().parent.parent


def ensure_service() -> bool:
    """Start maintenance service if needed; return whether it was started now."""
    if service_available():
        return False
    root = store.home()
    root.mkdir(parents=True, exist_ok=True)
    mode = "_service" if getattr(sys, "frozen", False) else "serve"
    command, cwd = detached_command(mode)
    if getattr(sys, "frozen", False):
        runner = Path(sys.executable).with_name("runner.exe")
        if runner.is_file():
            command[0] = str(runner)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    extra = {} if os.name == "nt" else {"start_new_session": True}
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(root)
    with (root / "service.log").open("ab") as log:
        subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, close_fds=True, creationflags=flags, **extra)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if service_available():
            return True
        time.sleep(0.1)
    raise RuntimeError("Local AgentRunner service did not become available on port 8765; see service.log")


def stop_service() -> dict[str, object]:
    """Ask the authenticated local Service to exit only when no work needs it."""
    if not service_available():
        return {"status": "NOT_RUNNING"}
    token = (store.home() / "ui-token").read_text(encoding="ascii").strip()
    request = Request(
        f"http://127.0.0.1:{SERVICE_PORT}/api/service/shutdown", data=b"{}", method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=2) as response:
            if response.status != 200:
                raise RuntimeError(f"Service shutdown returned HTTP {response.status}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 409:
            return {"status": "BLOCKED", **json.loads(detail)}
        raise RuntimeError(detail) from exc
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not service_available():
            return {"status": "STOPPED"}
        time.sleep(0.1)
    raise RuntimeError("Service accepted shutdown but did not stop within five seconds")


def show_desktop(job_id: str | None = None) -> None:
    """Ask the installed windowed executable to show; it handles singleton routing."""
    if not getattr(sys, "frozen", False):
        command = [sys.executable, "-m", "agentrunner", "desktop"]
    else:
        target = Path(sys.executable).with_name("AgentRunner.exe")
        if not target.is_file():
            raise RuntimeError(f"Desktop executable missing: {target}")
        command = [str(target)]
    if job_id:
        command.extend(["--show-job", job_id])
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    extra = {} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen(command, cwd=store.home(), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, creationflags=flags, **extra)

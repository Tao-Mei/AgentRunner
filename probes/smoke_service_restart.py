"""Confirm a service restart does not stop an independently owned command."""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def launch(root: Path, env: dict[str, str]):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, "-m", "agentrunner", "serve", "--port", "0"],
        cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, creationflags=flags,
    )
    line = process.stdout.readline()
    if not line:
        raise RuntimeError(process.stderr.read())
    return process, json.loads(line)["url"]


def stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "restart-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    first, _ = launch(root, env)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "agentrunner", "run", "--cwd", str(root), "--",
             "pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "probes" / "smoke_job.ps1")],
            cwd=root, env=env, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        job = json.loads(result.stdout)
        assert job["status"] == "ACCEPTED", job
    finally:
        stop(first)
    time.sleep(6)
    second, url = launch(root, env)
    try:
        token = (home / "ui-token").read_text(encoding="ascii").strip()
        request = urllib.request.Request(
            url + "api/jobs/" + job["job_id"],
            headers={"Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            detail = json.load(response)
        assert detail["status"] == "COMPLETED" and detail["exit_code"] == 0, detail
        print(json.dumps({"job_id": job["job_id"], "after_restart": detail["status"]}))
    finally:
        stop(second)


if __name__ == "__main__":
    main()

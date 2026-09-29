"""Isolated local API/UI smoke test; never sends a Codex callback."""

import json
import os
import queue
import subprocess
import sys
from contextlib import nullcontext
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    state_root = root / "probes" / ".probe-state" / "server-home"
    state_root.mkdir(parents=True, exist_ok=True)
    assert state_root.resolve().is_relative_to(root.resolve())
    with nullcontext(str(state_root)) as temporary:
        env = os.environ.copy()
        env["AGENTRUNNER_HOME"] = temporary
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [sys.executable, "-m", "agentrunner", "serve", "--port", "0"],
            cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, creationflags=flags,
        )
        try:
            lines: queue.Queue[str] = queue.Queue()
            threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            line = lines.get(timeout=10)
            if not line:
                raise RuntimeError(f"Server exited: {process.stderr.read()}")
            url = json.loads(line)["url"]
            token = (Path(temporary) / "ui-token").read_text(encoding="ascii").strip()

            def request(path: str, body: dict | None = None, authorized: bool = True):
                headers = {"Content-Type": "application/json"}
                if authorized:
                    headers["Authorization"] = f"Bearer {token}"
                data = json.dumps(body).encode() if body is not None else None
                with urllib.request.urlopen(urllib.request.Request(url + path, data=data, headers=headers), timeout=10) as response:
                    return response.status, response.read()

            status, page = request("")
            assert status == 200 and b"AgentRunner" in page
            try:
                request("api/jobs", authorized=False)
                raise AssertionError("API accepted a missing token")
            except urllib.error.HTTPError as error:
                assert error.code == 401

            status, response = request("api/jobs", {"command": [sys.executable, "-c", "print('api-ok')"], "cwd": str(root)})
            job = json.loads(response)
            assert status == 202 and job["status"] == "ACCEPTED", job
            time.sleep(2)
            _, response = request("api/jobs/" + job["job_id"])
            detail = json.loads(response)
            assert detail["status"] == "COMPLETED", detail
            _, response = request("api/jobs/" + job["job_id"] + "/logs?stream=stdout")
            assert "api-ok" in json.loads(response)["tail"]
            print(json.dumps({"api": "ok", "auth": "ok", "job": detail["status"], "ui": "ok"}))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()

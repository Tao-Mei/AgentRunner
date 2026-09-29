"""Restart the UI service while an independent command is still running."""

import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import psutil

from smoke_service_restart import launch, stop


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / ("live-restart-" + uuid.uuid4().hex[:8])
    home.mkdir(parents=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    first, _ = launch(root, env)
    try:
        submitted = subprocess.run(
            [sys.executable, "-m", "agentrunner", "run", "--cwd", str(root), "--",
             sys.executable, "-c", "import time; time.sleep(8); print('finished-after-restart')"],
            cwd=root, env=env, capture_output=True, text=True, timeout=10,
        )
        assert submitted.returncode == 0, submitted.stderr
        job_id = json.loads(submitted.stdout)["job_id"]
    finally:
        stop(first)
    second, url = launch(root, env)
    try:
        token = (home / "ui-token").read_text(encoding="ascii").strip()

        def read_job() -> dict:
            request = urllib.request.Request(url + "api/jobs/" + job_id,
                                             headers={"Authorization": "Bearer " + token})
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)

        running = read_job()
        assert running["status"] == "RUNNING", running
        child = psutil.Process(running["child_pid"])
        assert abs(child.create_time() - running["child_create_time"]) < 0.01
        assert not running["cancel_requested"]
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            final = read_job()
            if final["status"] in {"COMPLETED", "FAILED", "UNKNOWN"}:
                break
            time.sleep(0.5)
        assert final["status"] == "COMPLETED" and final["exit_code"] == 0, final
        assert final["child_pid"] == running["child_pid"]
        print(json.dumps({"running_after_restart": True, "same_child": True,
                          "terminal": final["status"]}))
    finally:
        stop(second)


if __name__ == "__main__":
    main()

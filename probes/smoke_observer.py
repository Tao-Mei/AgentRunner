"""Verify live structured, process, and watched-file observations."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path


def show(root: Path, env: dict[str, str], job_id: str) -> dict:
    result = subprocess.run([sys.executable, "-m", "agentrunner", "show", job_id],
                            cwd=root, env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "observer-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    output = home / f"observed-{uuid.uuid4().hex[:8]}.txt"
    submitted = subprocess.run(
        [sys.executable, "-m", "agentrunner", "run", "--cwd", str(root), "--watch", str(output),
         "--", sys.executable, "-u", str(root / "probes" / "observer_job.py"), str(output)],
        cwd=root, env=env, capture_output=True, text=True, timeout=10,
    )
    assert submitted.returncode == 0, submitted.stderr
    job_id = json.loads(submitted.stdout)["job_id"]
    time.sleep(2)
    middle = show(root, env, job_id)
    assert middle["status"] == "RUNNING", middle
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        final = show(root, env, job_id)
        if final["status"] in {"COMPLETED", "FAILED", "UNKNOWN"}:
            break
        time.sleep(0.5)
    assert final["status"] == "COMPLETED", final
    kinds = [event["kind"] for event in final["events"]]
    for expected in ("structured_stage", "structured_progress", "process_observed", "file_observed"):
        assert expected in kinds, kinds
    log = (home / "jobs" / job_id / "stdout.log").read_text(encoding="utf-8")
    assert "observer-finished" in log and "@@RUNNER" in log
    print(json.dumps({"job_id": job_id, "running_during_quiet_period": True,
                      "structured": 2, "process_observed": True, "file_observed": True}))


if __name__ == "__main__":
    main()

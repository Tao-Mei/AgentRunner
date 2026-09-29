"""Ensure known sensitive values are redacted across log chunk boundaries."""

import json
import os
import subprocess
import sys
from pathlib import Path


DUMMY_SECRET = "AR_TEST_PRIVATE_VALUE_82754"


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "redaction-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    env["AGENTRUNNER_TEST_TOKEN"] = DUMMY_SECRET
    result = subprocess.run(
        [sys.executable, "-m", "agentrunner", "exec", "--cwd", str(root), "--",
         sys.executable, str(root / "probes" / "redaction_job.py")],
        cwd=root, env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    job = json.loads(result.stdout)
    directory = home / "jobs" / job["job_id"]
    stdout = (directory / "stdout.log").read_text(encoding="utf-8")
    stderr = (directory / "stderr.log").read_text(encoding="utf-8")
    assert DUMMY_SECRET not in stdout + stderr
    assert stdout.count("[REDACTED]") == 2 and "[REDACTED]" in stderr
    showed = subprocess.run([sys.executable, "-m", "agentrunner", "show", job["job_id"]],
                            cwd=root, env=env, capture_output=True, text=True, timeout=5)
    detail = json.loads(showed.stdout)
    stages = [event["detail"]["value"] for event in detail["events"] if event["kind"] == "structured_stage"]
    assert stages == ["[REDACTED]"], stages
    print(json.dumps({"job_id": job["job_id"], "stdout": "redacted", "stderr": "redacted", "event": "redacted"}))


if __name__ == "__main__":
    main()

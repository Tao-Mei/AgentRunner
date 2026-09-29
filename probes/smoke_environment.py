"""Check child environment allowlisting for commands and workflows."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml


PRINT = "import json,os; print(json.dumps({k:os.getenv(k) for k in ['RUNNER_VISIBLE','RUNNER_HIDDEN','AGENTRUNNER_TEST_TOKEN']}))"


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "environment-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"AGENTRUNNER_HOME": str(home), "RUNNER_VISIBLE": "yes", "RUNNER_HIDDEN": "hidden",
                "AGENTRUNNER_TEST_TOKEN": "private"})
    result = subprocess.run(
        [sys.executable, "-m", "agentrunner", "exec", "--cwd", str(root), "--pass-env", "RUNNER_VISIBLE",
         "--", sys.executable, "-c", PRINT],
        cwd=root, env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    job = json.loads(result.stdout)
    assert job["status"] == "COMPLETED", job
    output = json.loads((home / "jobs" / job["job_id"] / "stdout.log").read_text().strip())
    assert output == {"RUNNER_VISIBLE": "yes", "RUNNER_HIDDEN": None, "AGENTRUNNER_TEST_TOKEN": None}, output

    sensitive = subprocess.run(
        [sys.executable, "-m", "agentrunner", "exec", "--cwd", str(root), "--pass-env", "AGENTRUNNER_TEST_TOKEN",
         "--", sys.executable, "-c", PRINT],
        cwd=root, env=env, capture_output=True, text=True, timeout=15,
    )
    assert sensitive.returncode == 0, sensitive.stderr
    sensitive_job = json.loads(sensitive.stdout)
    sensitive_log = (home / "jobs" / sensitive_job["job_id"] / "stdout.log").read_text(encoding="utf-8")
    assert "private" not in sensitive_log
    assert json.loads(sensitive_log)["AGENTRUNNER_TEST_TOKEN"] == "[REDACTED]"

    path = home / f"env-{uuid.uuid4().hex[:8]}.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "steps": [
        {"id": "check", "command": [sys.executable, "-c", PRINT],
         "pass_env": ["RUNNER_VISIBLE", "AGENTRUNNER_TEST_TOKEN"]},
    ]}, sort_keys=False), encoding="utf-8")
    submitted = subprocess.run([sys.executable, "-m", "agentrunner", "submit", str(path)],
                               cwd=root, env=env, capture_output=True, text=True, timeout=10)
    assert submitted.returncode == 0, submitted.stderr
    workflow_id = json.loads(submitted.stdout)["job_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        showed = subprocess.run([sys.executable, "-m", "agentrunner", "show", workflow_id],
                                cwd=root, env=env, capture_output=True, text=True, timeout=5)
        detail = json.loads(showed.stdout)
        if detail["status"] in {"COMPLETED", "FAILED", "UNKNOWN"}:
            break
        time.sleep(0.5)
    assert detail["status"] == "COMPLETED", detail
    workflow_output = json.loads((home / "jobs" / workflow_id / "steps" / "check" / "stdout.log").read_text().strip())
    assert workflow_output == {"RUNNER_VISIBLE": "yes", "RUNNER_HIDDEN": None,
                               "AGENTRUNNER_TEST_TOKEN": "[REDACTED]"}, workflow_output
    print(json.dumps({"command": job["status"], "workflow": detail["status"], "secret_default": "absent",
                      "explicit_secret": "redacted"}))


if __name__ == "__main__":
    main()

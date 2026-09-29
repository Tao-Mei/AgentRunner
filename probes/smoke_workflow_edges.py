"""Check failed dependencies, explicit retry, cancellation, and finalizers."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml
from smoke_workflow import command, submit_and_wait


def write_yaml(home: Path, name: str, document: dict) -> Path:
    path = home / f"{name}-{uuid.uuid4().hex[:8]}.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def show(root: Path, env: dict[str, str], job_id: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "agentrunner", "show", job_id],
        cwd=root, env=env, capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "workflow-edge-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    script = root / "probes" / "workflow_step.ps1"

    failure_folder = home / uuid.uuid4().hex[:8]
    failure_doc = {
        "version": 1,
        "steps": [
            {"id": "fail", "command": command(script, failure_folder, "fail", fail=True)},
            {"id": "blocked", "after": ["fail"], "command": command(script, failure_folder, "blocked")},
        ],
        "finalizers": [{"id": "cleanup", "command": command(script, failure_folder, "cleanup")}],
    }
    failed = submit_and_wait(root, env, write_yaml(home, "fail", failure_doc))
    states = {row["step_id"]: row["status"] for row in failed["steps"]}
    assert failed["status"] == "FAILED" and states == {"fail": "FAILED", "blocked": "SKIPPED", "cleanup": "COMPLETED"}, states
    assert (failure_folder / "cleanup.done").exists()

    retry_folder = home / uuid.uuid4().hex[:8]
    retry_doc = {
        "version": 1,
        "steps": [{"id": "flaky", "command": ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                                  str(root / "probes" / "workflow_flaky_step.ps1"), "-Folder", str(retry_folder)],
                   "safe_to_retry": True, "retry": {"max_attempts": 2, "delay_seconds": 0.1}}],
    }
    retried = submit_and_wait(root, env, write_yaml(home, "retry", retry_doc))
    assert retried["status"] == "COMPLETED" and retried["steps"][0]["attempts"] == 2, retried

    cancel_folder = home / uuid.uuid4().hex[:8]
    cancel_doc = {
        "version": 1,
        "steps": [{"id": "long", "command": command(script, cancel_folder, "long", 30000)}],
        "finalizers": [{"id": "cleanup", "command": command(script, cancel_folder, "cleanup")}],
    }
    path = write_yaml(home, "cancel", cancel_doc)
    submission = subprocess.run(
        [sys.executable, "-m", "agentrunner", "submit", str(path)],
        cwd=root, env=env, capture_output=True, text=True, timeout=10,
    )
    assert submission.returncode == 0, submission.stderr
    job_id = json.loads(submission.stdout)["job_id"]
    cancellation = subprocess.run(
        [sys.executable, "-m", "agentrunner", "cancel", job_id],
        cwd=root, env=env, capture_output=True, text=True, timeout=10,
    )
    assert cancellation.returncode == 0, cancellation.stderr
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        cancelled = show(root, env, job_id)
        if cancelled["status"] in {"CANCELLED", "FAILED", "UNKNOWN"}:
            break
        time.sleep(0.5)
    assert cancelled["status"] == "CANCELLED" and (cancel_folder / "cleanup.done").exists(), cancelled
    print(json.dumps({"failed": failed["status"], "retry_attempts": retried["steps"][0]["attempts"],
                      "cancelled": cancelled["status"], "finalizers": "ran"}))


if __name__ == "__main__":
    main()

"""Ensure a completed step is not repeated when the UI service restarts."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml
from smoke_service_restart import launch, stop
from smoke_workflow import command


def show(root: Path, env: dict[str, str], job_id: str) -> dict:
    result = subprocess.run([sys.executable, "-m", "agentrunner", "show", job_id],
                            cwd=root, env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "workflow-restart-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    folder = home / uuid.uuid4().hex[:8]
    script = root / "probes" / "workflow_step.ps1"
    document = {"version": 1, "steps": [
        {"id": "prepare", "command": command(script, folder, "prepare")},
        {"id": "slow", "after": ["prepare"], "command": command(script, folder, "slow", 3000)},
    ], "finalizers": [{"id": "cleanup", "command": command(script, folder, "cleanup")}]}
    path = home / f"restart-{uuid.uuid4().hex[:8]}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    first, _ = launch(root, env)
    try:
        result = subprocess.run([sys.executable, "-m", "agentrunner", "submit", str(path)],
                                cwd=root, env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        job_id = json.loads(result.stdout)["job_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = show(root, env, job_id)
            states = {step["step_id"]: step["status"] for step in job["steps"]}
            if states["prepare"] == "COMPLETED" and states["slow"] == "RUNNING":
                break
            time.sleep(0.3)
        else:
            raise TimeoutError("Workflow did not enter the expected checkpoint")
    finally:
        stop(first)
    time.sleep(4)
    second, _ = launch(root, env)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            final = show(root, env, job_id)
            if final["status"] in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN"}:
                break
            time.sleep(0.5)
        assert final["status"] == "COMPLETED", final
        steps = {step["step_id"]: step for step in final["steps"]}
        assert steps["prepare"]["attempts"] == 1 and steps["slow"]["attempts"] == 1, steps
        assert (folder / "cleanup.done").exists()
        print(json.dumps({"job_id": job_id, "after_restart": final["status"], "prepare_attempts": 1,
                          "slow_attempts": 1}))
    finally:
        stop(second)


if __name__ == "__main__":
    main()

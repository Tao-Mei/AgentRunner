"""Kill an idle supervisor at a checkpoint, then resume without rerunning prior work."""

import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil
import yaml
from smoke_workflow import command


def cli(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "agentrunner", *args], cwd=root, env=env,
                          capture_output=True, text=True, timeout=15)


def show(root: Path, env: dict[str, str], job_id: str) -> dict:
    result = cli(root, env, "show", job_id)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def wait_until(root: Path, env: dict[str, str], job_id: str, predicate, seconds: float = 15) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = show(root, env, job_id)
        if predicate(job):
            return job
        time.sleep(0.3)
    raise TimeoutError(f"Job {job_id} did not reach expected state")


def write_yaml(home: Path, document: dict) -> Path:
    path = home / f"recovery-{uuid.uuid4().hex[:8]}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def submit(root: Path, env: dict[str, str], path: Path) -> str:
    result = cli(root, env, "submit", str(path))
    assert result.returncode == 0, result.stderr
    accepted = json.loads(result.stdout)
    assert accepted["status"] == "ACCEPTED", accepted
    return accepted["job_id"]


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "recovery-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    script = root / "probes" / "workflow_step.ps1"
    resource = "lock_" + uuid.uuid4().hex[:8]
    blocker_folder = home / uuid.uuid4().hex[:8]
    blocker_doc = {"version": 1, "resources": [{"id": resource, "capacity": 1}],
                   "steps": [{"id": "hold", "resources": [resource],
                              "command": command(script, blocker_folder, "hold", 6000)}]}
    blocker_id = submit(root, env, write_yaml(home, blocker_doc))
    wait_until(root, env, blocker_id,
               lambda job: any(step["step_id"] == "hold" and step["status"] == "RUNNING" for step in job["steps"]))

    folder = home / uuid.uuid4().hex[:8]
    target_doc = {"version": 1, "resources": [{"id": resource, "capacity": 1}],
                  "steps": [
                      {"id": "prepare", "command": command(script, folder, "prepare")},
                      {"id": "use", "after": ["prepare"], "resources": [resource],
                       "command": command(script, folder, "use")},
                  ], "finalizers": [{"id": "cleanup", "command": command(script, folder, "cleanup")}]}
    target_id = submit(root, env, write_yaml(home, target_doc))
    checkpoint = wait_until(
        root, env, target_id,
        lambda job: {step["step_id"]: step["status"] for step in job["steps"]}.get("prepare") == "COMPLETED"
                    and {step["step_id"]: step["status"] for step in job["steps"]}.get("use") == "PENDING",
    )
    supervisor = psutil.Process(checkpoint["worker_pid"])
    assert abs(supervisor.create_time() - checkpoint["worker_create_time"]) < 0.01
    supervisor.kill()
    supervisor.wait(timeout=5)
    reconciled = cli(root, env, "reconcile")
    assert reconciled.returncode == 0, reconciled.stderr
    unknown = show(root, env, target_id)
    assert unknown["status"] == "UNKNOWN", unknown
    resumed = cli(root, env, "resume", target_id)
    assert resumed.returncode == 0, resumed.stderr + resumed.stdout
    assert json.loads(resumed.stdout)["status"] == "ACCEPTED"
    final = wait_until(root, env, target_id, lambda job: job["status"] in {"COMPLETED", "FAILED", "UNKNOWN"}, 20)
    assert final["status"] == "COMPLETED", final
    steps = {step["step_id"]: step for step in final["steps"]}
    assert steps["prepare"]["attempts"] == 1 and steps["use"]["attempts"] == 1, steps
    assert (folder / "cleanup.done").exists()
    with sqlite3.connect(home / "runner.db") as con:
        assert con.execute("SELECT count(*) FROM resource_leases WHERE job_id = ?", (target_id,)).fetchone()[0] == 0
    print(json.dumps({"job_id": target_id, "resumed": final["status"], "prepare_attempts": 1,
                      "use_attempts": 1, "resource_released": True}))


if __name__ == "__main__":
    main()

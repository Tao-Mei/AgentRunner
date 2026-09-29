"""Stop a confirmed live orphan without losing its finalizer or resource lease."""

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

import psutil
from smoke_workflow import command
from smoke_workflow_recovery import cli, show, submit, wait_until, write_yaml


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "orphan-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    folder = home / uuid.uuid4().hex[:8]
    resource = "orphan_" + uuid.uuid4().hex[:8]
    script = root / "probes" / "workflow_step.ps1"
    doc = {"version": 1, "resources": [{"id": resource, "capacity": 1}],
           "steps": [{"id": "long", "resources": [resource],
                      "command": command(script, folder, "long", 30000)}],
           "finalizers": [{"id": "cleanup", "command": command(script, folder, "cleanup")}]}
    job_id = submit(root, env, write_yaml(home, doc))
    running = wait_until(root, env, job_id,
                         lambda job: any(step["step_id"] == "long" and step["status"] == "RUNNING" and step["pid"]
                                         for step in job["steps"]))
    parent = psutil.Process(running["worker_pid"])
    assert abs(parent.create_time() - running["worker_create_time"]) < 0.01
    parent.kill()
    parent.wait(timeout=5)
    assert cli(root, env, "reconcile").returncode == 0
    unknown = show(root, env, job_id)
    assert unknown["status"] == "UNKNOWN"
    stopped = cli(root, env, "stop-orphan", job_id, "long")
    assert stopped.returncode == 0, stopped.stderr + stopped.stdout
    assert json.loads(stopped.stdout)["process_action"] == "termination_requested"
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        assert cli(root, env, "reconcile").returncode == 0
        state = show(root, env, job_id)
        step = next(row for row in state["steps"] if row["step_id"] == "long")
        if step["status"] == "UNKNOWN":
            break
        time.sleep(0.3)
    assert step["status"] == "UNKNOWN", step
    resolved = cli(root, env, "resolve-step", job_id, "long", "--outcome", "failed",
                   "--evidence", "Probe terminated verified orphan process")
    assert resolved.returncode == 0, resolved.stderr
    resumed = cli(root, env, "resume", job_id)
    assert resumed.returncode == 0, resumed.stderr + resumed.stdout
    final = wait_until(root, env, job_id, lambda job: job["status"] in {"COMPLETED", "FAILED", "UNKNOWN"}, 10)
    assert final["status"] == "FAILED", final
    assert (folder / "cleanup.done").exists()
    with sqlite3.connect(home / "runner.db") as con:
        assert con.execute("SELECT count(*) FROM resource_leases WHERE job_id = ?", (job_id,)).fetchone()[0] == 0
    print(json.dumps({"job_id": job_id, "orphan_stopped": True, "final_status": final["status"],
                      "finalizer": "ran", "resource_released": True}))


if __name__ == "__main__":
    main()

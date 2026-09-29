"""A killed supervisor must not automatically repeat an in-flight step."""

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
from smoke_workflow_recovery import cli, show, submit, wait_until, write_yaml


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "uncertain-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    folder = home / uuid.uuid4().hex[:8]
    script = root / "probes" / "workflow_step.ps1"
    resource = "uncertain_" + uuid.uuid4().hex[:8]
    doc = {"version": 1, "resources": [{"id": resource, "capacity": 1}],
           "steps": [{"id": "long", "resources": [resource], "safe_to_retry": True,
                      "retry": {"max_attempts": 2}, "command": command(script, folder, "long", 3500)}],
           "finalizers": [{"id": "cleanup", "command": command(script, folder, "cleanup")}]}
    job_id = submit(root, env, write_yaml(home, doc))
    running = wait_until(root, env, job_id,
                         lambda job: any(step["step_id"] == "long" and step["status"] == "RUNNING" and step["pid"]
                                         for step in job["steps"]))
    supervisor = psutil.Process(running["worker_pid"])
    assert abs(supervisor.create_time() - running["worker_create_time"]) < 0.01
    supervisor.kill()
    supervisor.wait(timeout=5)
    assert cli(root, env, "reconcile").returncode == 0
    uncertain = show(root, env, job_id)
    assert uncertain["status"] == "UNKNOWN"
    assert next(step for step in uncertain["steps"] if step["step_id"] == "long")["attempts"] == 1
    premature = cli(root, env, "resume", job_id)
    assert premature.returncode != 0 and json.loads(premature.stdout)["status"] == "NEEDS_DECISION"

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        assert cli(root, env, "reconcile").returncode == 0
        uncertain = show(root, env, job_id)
        long = next(step for step in uncertain["steps"] if step["step_id"] == "long")
        if long["status"] == "UNKNOWN":
            break
        time.sleep(0.5)
    assert long["status"] == "UNKNOWN" and long["attempts"] == 1, long
    with sqlite3.connect(home / "runner.db") as con:
        assert con.execute("SELECT count(*) FROM resource_leases WHERE job_id = ?", (job_id,)).fetchone()[0] == 1
    resolved = cli(root, env, "resolve-step", job_id, "long", "--outcome", "retry",
                   "--evidence", "Probe verified prior process exited; this step is idempotent")
    assert resolved.returncode == 0, resolved.stderr
    resumed = cli(root, env, "resume", job_id)
    assert resumed.returncode == 0, resumed.stderr + resumed.stdout
    final = wait_until(root, env, job_id, lambda job: job["status"] in {"COMPLETED", "FAILED", "UNKNOWN"}, 15)
    assert final["status"] == "COMPLETED", final
    steps = {step["step_id"]: step for step in final["steps"]}
    assert steps["long"]["attempts"] == 2 and steps["cleanup"]["attempts"] == 1, steps
    with sqlite3.connect(home / "runner.db") as con:
        assert con.execute("SELECT count(*) FROM resource_leases WHERE job_id = ?", (job_id,)).fetchone()[0] == 0
    print(json.dumps({"job_id": job_id, "premature_resume": "rejected", "explicit_retry": "COMPLETED",
                      "attempts": 2, "lease_released_after_resolution": True}))


if __name__ == "__main__":
    main()

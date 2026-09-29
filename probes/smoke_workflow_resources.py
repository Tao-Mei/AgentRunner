"""Verify cross-job capacity locks, timeout, release, and cycle rejection."""

import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml
from smoke_workflow import command, submit_and_wait


def submit(root: Path, env: dict[str, str], path: Path) -> str:
    result = subprocess.run([sys.executable, "-m", "agentrunner", "submit", str(path)],
                            cwd=root, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    accepted = json.loads(result.stdout)
    assert accepted["status"] == "ACCEPTED"
    return accepted["job_id"]


def wait_jobs(root: Path, env: dict[str, str], job_ids: list[str]) -> dict[str, dict]:
    final: dict[str, dict] = {}
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and len(final) < len(job_ids):
        for job_id in job_ids:
            if job_id in final:
                continue
            result = subprocess.run([sys.executable, "-m", "agentrunner", "show", job_id],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=5)
            assert result.returncode == 0, result.stderr
            job = json.loads(result.stdout)
            if job["status"] in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN"}:
                final[job_id] = job
        time.sleep(0.5)
    assert len(final) == len(job_ids), final
    return final


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "workflow-resource-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    script = root / "probes" / "workflow_step.ps1"
    folders = [home / uuid.uuid4().hex[:8] for _ in range(2)]
    paths = []
    for index, folder in enumerate(folders):
        doc = {"version": 1, "resources": [{"id": "gpu", "capacity": 1}],
               "steps": [{"id": "render", "resources": ["gpu"],
                          "command": command(script, folder, f"render{index}", 1000)}]}
        path = home / f"resource-{uuid.uuid4().hex[:8]}.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        paths.append(path)
    job_ids = [submit(root, env, path) for path in paths]
    jobs = wait_jobs(root, env, job_ids)
    assert all(job["status"] == "COMPLETED" for job in jobs.values()), jobs
    intervals = []
    for index, folder in enumerate(folders):
        start = (folder / f"render{index}.started").read_text().strip()
        end = (folder / f"render{index}.done").read_text().strip()
        intervals.append((start, end))
    assert intervals[0][1] <= intervals[1][0] or intervals[1][1] <= intervals[0][0], intervals

    timeout_folder = home / uuid.uuid4().hex[:8]
    timeout_doc = {"version": 1,
                   "steps": [{"id": "slow", "timeout_seconds": 0.3,
                              "command": command(script, timeout_folder, "slow", 5000)}],
                   "finalizers": [{"id": "cleanup", "command": command(script, timeout_folder, "cleanup")}]}
    timeout_path = home / f"timeout-{uuid.uuid4().hex[:8]}.yaml"
    timeout_path.write_text(yaml.safe_dump(timeout_doc, sort_keys=False), encoding="utf-8")
    timed_out = submit_and_wait(root, env, timeout_path)
    states = {step["step_id"]: step["status"] for step in timed_out["steps"]}
    assert timed_out["status"] == "FAILED" and states == {"slow": "TIMED_OUT", "cleanup": "COMPLETED"}, states
    with sqlite3.connect(home / "runner.db") as con:
        assert con.execute("SELECT count(*) FROM resource_leases").fetchone()[0] == 0
        prior_jobs = con.execute("SELECT count(*) FROM jobs").fetchone()[0]

    conflicting = {"version": 1, "resources": [{"id": "gpu", "capacity": 2}],
                   "steps": [{"id": "bad", "resources": ["gpu"],
                              "command": command(script, home / uuid.uuid4().hex[:8], "bad")}]}
    conflict_path = home / f"conflict-{uuid.uuid4().hex[:8]}.yaml"
    conflict_path.write_text(yaml.safe_dump(conflicting, sort_keys=False), encoding="utf-8")
    conflict = subprocess.run([sys.executable, "-m", "agentrunner", "submit", str(conflict_path)],
                              cwd=root, env=env, capture_output=True, text=True, timeout=5)
    assert conflict.returncode != 0 and "capacity" in conflict.stderr, conflict
    with sqlite3.connect(home / "runner.db") as con:
        assert con.execute("SELECT count(*) FROM jobs").fetchone()[0] == prior_jobs

    invalid = {"version": 1, "steps": [
        {"id": "a", "after": ["b"], "command": ["pwsh", "-Version"]},
        {"id": "b", "after": ["a"], "command": ["pwsh", "-Version"]},
    ]}
    invalid_path = home / f"cycle-{uuid.uuid4().hex[:8]}.yaml"
    invalid_path.write_text(yaml.safe_dump(invalid, sort_keys=False), encoding="utf-8")
    rejected = subprocess.run([sys.executable, "-m", "agentrunner", "submit", str(invalid_path)],
                              cwd=root, env=env, capture_output=True, text=True, timeout=5)
    assert rejected.returncode != 0 and "cycle" in rejected.stderr.lower(), rejected
    print(json.dumps({"cross_job_lock": "serialized", "timeout": states["slow"],
                      "finalizer": states["cleanup"], "leases": 0, "cycle": "rejected", "capacity_conflict": "rejected"}))


if __name__ == "__main__":
    main()

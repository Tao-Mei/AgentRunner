"""Exercise scheduling controls against independent workflow supervisors."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import yaml

from agentrunner import store
from agentrunner.cli import submit_workflow


def wait_for(job_id: str, predicate, seconds: float = 12) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {job_id}: {store.get_job(job_id)} {store.list_steps(job_id)}")


def run_case(root: Path, control: str) -> None:
    working = root / control
    working.mkdir()
    program = working / "step.py"
    program.write_text(
        "import pathlib,sys,time\n"
        "name=sys.argv[1]\n"
        "pathlib.Path(name+'.started').write_text('started')\n"
        "time.sleep(float(sys.argv[2]))\n"
        "pathlib.Path(name+'.finished').write_text('finished')\n",
        encoding="utf-8",
    )
    workflow = {
        "version": 1,
        "max_parallel": 1,
        "steps": [
            {"id": "first", "command": [sys.executable, str(program), "first", "1.5"]},
            {"id": "second", "after": ["first"], "command": [sys.executable, str(program), "second", "0"]},
        ],
        "finalizers": [{"id": "cleanup", "command": [sys.executable, str(program), "cleanup", "0"]}],
    }
    path = working / "workflow.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    result, _ = submit_workflow(str(path), str(working), None)
    assert result["status"] == "ACCEPTED", result
    job_id = result["job_id"]
    wait_for(job_id, lambda: (working / "first.started").exists())
    assert store.set_workflow_control(job_id, control)
    wait_for(job_id, lambda: (working / "first.finished").exists())
    if control == "pause":
        time.sleep(0.7)
        steps = {row["step_id"]: row for row in store.list_steps(job_id)}
        assert steps["second"]["status"] == "PENDING", steps
        assert not (working / "second.started").exists()
        assert store.get_job(job_id)["status"] == "RUNNING"
        assert store.set_workflow_control(job_id, "continue")
        wait_for(job_id, lambda: store.get_job(job_id)["status"] == "COMPLETED")
        assert (working / "second.finished").exists()
    else:
        wait_for(job_id, lambda: store.get_job(job_id)["status"] == "CANCELLED")
        assert not (working / "second.started").exists()
        steps = {row["step_id"]: row for row in store.list_steps(job_id)}
        assert steps["first"]["status"] == "COMPLETED", steps
        assert steps["second"]["status"] == "SKIPPED", steps
    assert (working / "cleanup.finished").exists()
    assert not [row for row in store.list_steps(job_id) if row["status"] == "RUNNING"]
    print(json.dumps({"control": control, "job_id": job_id, "status": store.get_job(job_id)["status"]}))


def main() -> None:
    probe_root = Path(__file__).resolve().parent / ".probe-state"
    probe_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agentrunner-controls-", dir=probe_root) as temporary:
        root = Path(temporary)
        os.environ["AGENTRUNNER_HOME"] = str(root / "state")
        run_case(root, "pause")
        run_case(root, "stop-after-current")


if __name__ == "__main__":
    main()

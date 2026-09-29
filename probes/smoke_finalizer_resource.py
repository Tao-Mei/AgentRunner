"""A finalizer waits for a resource held by another local workflow."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml

from smoke_workflow import command


def call(root: Path, env: dict[str, str], *args: str) -> dict:
    result = subprocess.run([sys.executable, "-m", "agentrunner", *args], cwd=root, env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    return json.loads(result.stdout)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / ("finalizer-resource-" + uuid.uuid4().hex[:8])
    home.mkdir(parents=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    script = root / "probes" / "workflow_step.ps1"
    holder_folder, target_folder = home / "holder", home / "target"
    resources = [{"id": "shared", "capacity": 1}]
    holder = {"version": 1, "resources": resources,
              "steps": [{"id": "hold", "resources": ["shared"],
                         "command": command(script, holder_folder, "hold", 2500)}]}
    target = {"version": 1, "resources": resources,
              "steps": [{"id": "fail", "command": command(script, target_folder, "fail", fail=True)}],
              "finalizers": [{"id": "cleanup", "resources": ["shared"],
                              "command": command(script, target_folder, "cleanup")}]}
    for name, document in (("holder", holder), ("target", target)):
        (home / f"{name}.yaml").write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    holder_id = call(root, env, "submit", str(home / "holder.yaml"))["job_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not (holder_folder / "hold.started").exists():
        time.sleep(0.1)
    assert (holder_folder / "hold.started").exists(), "Holder never acquired resource"
    target_id = call(root, env, "submit", str(home / "target.yaml"))["job_id"]
    jobs = {}
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and len(jobs) < 2:
        for job_id in (holder_id, target_id):
            if job_id not in jobs:
                job = call(root, env, "show", job_id)
                if job["status"] in {"COMPLETED", "FAILED", "UNKNOWN"}:
                    jobs[job_id] = job
        time.sleep(0.25)
    assert len(jobs) == 2, jobs
    assert jobs[holder_id]["status"] == "COMPLETED", jobs[holder_id]
    assert jobs[target_id]["status"] == "FAILED", jobs[target_id]
    states = {row["step_id"]: row["status"] for row in jobs[target_id]["steps"]}
    assert states == {"fail": "FAILED", "cleanup": "COMPLETED"}, states
    assert (holder_folder / "hold.done").read_text().strip() <= (target_folder / "cleanup.started").read_text().strip()
    print(json.dumps({"holder": "COMPLETED", "target": "FAILED", "finalizer": "COMPLETED",
                      "waited_for_resource": True}))


if __name__ == "__main__":
    main()

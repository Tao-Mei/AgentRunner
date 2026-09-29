"""Run a real local Python/R statistics DAG without an Agent polling loop."""

import csv
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil
import yaml


def main() -> None:
    recover = "--recover" in sys.argv[1:]
    root = Path(__file__).resolve().parent.parent
    scripts = root / "probes" / "statistics"
    rscript = shutil.which("Rscript")
    if not rscript:
        raise RuntimeError("Rscript is required for this acceptance probe")
    home = root / "probes" / ".probe-state" / ("python-r-" + uuid.uuid4().hex[:8])
    home.mkdir(parents=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    data = home / "responses.csv"
    alpha = home / "alpha.csv"
    cfa = home / "cfa.csv"
    bootstrap = home / "bootstrap.csv"
    table = home / "report.csv"
    steps = [
        {"id": "clean", "command": [sys.executable, str(scripts / "make_data.py"), str(data)],
         "artifacts": [data.name]},
        {"id": "reliability", "after": ["clean"],
         "command": [rscript, str(scripts / "reliability.R"), str(data), str(alpha)], "artifacts": [alpha.name]},
        {"id": "cfa", "after": ["clean"],
         "command": [rscript, str(scripts / "cfa.R"), str(data), str(cfa)], "artifacts": [cfa.name]},
        {"id": "bootstrap", "after": ["clean"],
         "command": [rscript, str(scripts / "bootstrap.R"), str(data), str(bootstrap)],
         "artifacts": [bootstrap.name]},
        {"id": "export", "after": ["reliability", "cfa", "bootstrap"],
         "command": [sys.executable, str(scripts / "export_table.py"), str(alpha), str(cfa),
                     str(bootstrap), str(table)], "artifacts": [table.name]},
    ]
    resource = "cfa_lock"
    if recover:
        steps[2]["resources"] = [resource]
        blocker = home / "blocker.yaml"
        blocker.write_text(yaml.safe_dump({
            "version": 1, "resources": [{"id": resource, "capacity": 1}],
            "steps": [{"id": "hold", "resources": [resource], "command": [
                "pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(root / "probes" / "workflow_step.ps1"), "-Name", "hold", "-Folder", str(home / "blocker"),
                "-DelayMs", "8000"]}]
        }, sort_keys=False), encoding="utf-8")
        held = subprocess.run([sys.executable, "-m", "agentrunner", "submit", str(blocker)],
                              cwd=root, env=env, capture_output=True, text=True, timeout=15)
        assert held.returncode == 0, held.stderr + held.stdout
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not (home / "blocker" / "hold.started").exists():
            time.sleep(0.1)
        assert (home / "blocker" / "hold.started").exists(), "Blocker did not start"
    workflow = home / "statistics.yaml"
    workflow.write_text(yaml.safe_dump({"version": 1, "job": {"name": "python-r-statistics"},
                                        "max_parallel": 3, "steps": steps,
                                        "resources": [{"id": resource, "capacity": 1}] if recover else []},
                                       sort_keys=False), encoding="utf-8")
    accepted = subprocess.run([sys.executable, "-m", "agentrunner", "submit", str(workflow), "--cwd", str(home)],
                              cwd=root, env=env, capture_output=True, text=True, timeout=15)
    assert accepted.returncode == 0, accepted.stderr + accepted.stdout
    job_id = json.loads(accepted.stdout)["job_id"]
    if recover:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            snapshot = subprocess.run([sys.executable, "-m", "agentrunner", "show", job_id],
                                      cwd=root, env=env, capture_output=True, text=True, timeout=5)
            assert snapshot.returncode == 0, snapshot.stderr
            checkpoint = json.loads(snapshot.stdout)
            states = {step["step_id"]: step["status"] for step in checkpoint["steps"]}
            if (states.get("clean") == states.get("reliability") == states.get("bootstrap") == "COMPLETED"
                    and states.get("cfa") == "PENDING"):
                break
            time.sleep(0.2)
        else:
            raise TimeoutError("Statistics checkpoint not reached")
        supervisor = psutil.Process(checkpoint["worker_pid"])
        assert abs(supervisor.create_time() - checkpoint["worker_create_time"]) < 0.01
        supervisor.kill()
        supervisor.wait(timeout=5)
        reconciled = subprocess.run([sys.executable, "-m", "agentrunner", "reconcile"],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=15)
        assert reconciled.returncode == 0, reconciled.stderr
        resumed = subprocess.run([sys.executable, "-m", "agentrunner", "resume", job_id],
                                 cwd=root, env=env, capture_output=True, text=True, timeout=15)
        assert resumed.returncode == 0 and json.loads(resumed.stdout)["status"] == "ACCEPTED", resumed.stderr
    # The test harness observes the machine process; a Codex turn would stop after ACCEPTED.
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = subprocess.run([sys.executable, "-m", "agentrunner", "show", job_id], cwd=root, env=env,
                                capture_output=True, text=True, timeout=5)
        assert result.returncode == 0, result.stderr
        job = json.loads(result.stdout)
        if job["status"] in {"COMPLETED", "FAILED", "UNKNOWN"}:
            break
        time.sleep(0.5)
    else:
        raise TimeoutError(job_id)
    assert job["status"] == "COMPLETED", job
    assert all(step["status"] == "COMPLETED" for step in job["steps"]), job["steps"]
    if recover:
        assert all(step["attempts"] == 1 for step in job["steps"]), job["steps"]
        assert job["resume_count"] == 1, job
    with table.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    metrics = {row["metric"]: float(row["value"]) for row in rows}
    assert 0.7 < metrics["cronbach_alpha"] < 1
    assert 0 <= metrics["cfi"] <= 1.01
    assert 0 < metrics["ci_low"] < metrics["mean"] < metrics["ci_high"] < 5
    assert any(item["path"] == table.name for step in job["steps"] for item in step["artifacts"])
    print(json.dumps({"job_id": job_id, "status": job["status"], "steps": len(job["steps"]),
                      "metrics": sorted(metrics), "report_artifact": table.name,
                      "resumed_without_rerun": recover}))


if __name__ == "__main__":
    main()

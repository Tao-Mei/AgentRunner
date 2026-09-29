"""Submit a real DAG with foreach, after_each, resource lock, and finalizer."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml


def command(script: Path, folder: Path, name: str, delay: int = 0, fail: bool = False):
    result = ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
              "-Name", name, "-Folder", str(folder), "-DelayMs", str(delay)]
    if fail:
        result.append("-Fail")
    return result


def submit_and_wait(root: Path, env: dict[str, str], path: Path):
    submission = subprocess.run(
        [sys.executable, "-m", "agentrunner", "submit", str(path)],
        cwd=root, env=env, capture_output=True, text=True, timeout=15,
    )
    assert submission.returncode == 0, submission.stderr + submission.stdout
    accepted = json.loads(submission.stdout)
    assert accepted["status"] == "ACCEPTED", accepted
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        result = subprocess.run(
            [sys.executable, "-m", "agentrunner", "show", accepted["job_id"]],
            cwd=root, env=env, capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0, result.stderr
        job = json.loads(result.stdout)
        if job["status"] in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN"}:
            return job
        time.sleep(0.5)
    raise TimeoutError(f"Workflow did not finish: {accepted['job_id']}")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "workflow-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    script = root / "probes" / "workflow_step.ps1"
    label = uuid.uuid4().hex[:8]
    folder = home / label
    yaml_path = home / f"smoke-{label}.yaml"
    document = {
        "version": 1, "job": {"name": "workflow-smoke"}, "max_parallel": 3,
        "resources": [{"id": "gpu", "capacity": 1}],
        "steps": [
            {"id": "prepare", "command": command(script, folder, "prepare")},
            {"id": "render", "foreach": ["A", "B"], "after": ["prepare"],
             "command": command(script, folder, "render-{{ item }}", 500),
             "concurrency": 1, "resources": ["gpu"],
             "artifacts": [str(folder / "render-{{ item }}.done")]},
            {"id": "download", "foreach": ["A", "B"], "after_each": {"step": "render"},
             "command": command(script, folder, "download-{{ item }}", 100)},
            {"id": "verify", "after_all": ["render", "download"],
             "command": command(script, folder, "verify")},
        ],
        "finalizers": [{"id": "cleanup", "command": command(script, folder, "cleanup")}],
    }
    yaml_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    job = submit_and_wait(root, env, yaml_path)
    assert job["status"] == "COMPLETED", job
    steps = {row["step_id"]: row for row in job["steps"]}
    assert len(steps) == 7 and all(row["status"] == "COMPLETED" for row in steps.values()), steps
    assert (folder / "cleanup.done").exists()
    assert any(item["path"].endswith("render-A.done") for item in steps["render[A]"]["artifacts"])
    render_a_finished = (folder / "render-A.done").read_text().strip()
    render_b_started = (folder / "render-B.started").read_text().strip()
    assert render_a_finished <= render_b_started, "GPU capacity/concurrency was not respected"
    download_a_started = (folder / "download-A.started").read_text().strip()
    download_a_finished = (folder / "download-A.done").read_text().strip()
    render_b_finished = (folder / "render-B.done").read_text().strip()
    assert render_a_finished <= download_a_started < render_b_finished, "A postprocessing did not start while B rendered"
    assert render_b_started < download_a_finished, "A postprocessing did not overlap B rendering"
    print(json.dumps({"job_id": job["id"], "status": job["status"], "steps": len(steps), "finalizer": "COMPLETED"}))


if __name__ == "__main__":
    main()

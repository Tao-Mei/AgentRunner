"""Confirm a large stdout stream is bounded across rotating files."""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentrunner.observer import MAX_LOG_BYTES


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / "rotation-home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(home)
    payload = MAX_LOG_BYTES + 100_000
    result = subprocess.run(
        [sys.executable, "-m", "agentrunner", "exec", "--cwd", str(root), "--",
         sys.executable, "-c", f"import sys; sys.stdout.write('x'*{payload})"],
        cwd=root, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    job = json.loads(result.stdout)
    assert job["status"] == "COMPLETED", job
    directory = home / "jobs" / job["job_id"]
    current = directory / "stdout.log"
    previous = directory / "stdout.log.1"
    assert previous.exists() and previous.stat().st_size > 0
    assert current.stat().st_size < MAX_LOG_BYTES
    assert current.stat().st_size + previous.stat().st_size == payload
    print(json.dumps({"job_id": job["job_id"], "bytes": payload, "rotated": True}))


if __name__ == "__main__":
    main()

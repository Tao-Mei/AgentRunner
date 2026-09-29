"""A launch failure returns the Job ID; a database failure leaves no orphan Job directory."""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentrunner import cli, store


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / ("submission-failure-" + uuid.uuid4().hex[:8])
    os.environ["AGENTRUNNER_HOME"] = str(home)
    with patch.object(cli.subprocess, "Popen", side_effect=OSError("injected launch failure")):
        result, worker = cli.submit([sys.executable, "-V"], str(root), None)
    assert worker is None and result["status"] == "UNKNOWN_SUBMISSION", result
    job = store.get_job(result["job_id"])
    assert job and job["status"] == "CREATED"
    assert any(event["kind"] == "worker_launch_unconfirmed" for event in store.list_events(result["job_id"]))
    other_id = "JOB-" + uuid.uuid4().hex[:12]
    with patch.object(store, "connect", side_effect=OSError("injected database failure")):
        try:
            store.create_job({"id": other_id, "event_id": "EVT-" + uuid.uuid4().hex[:16],
                              "command": [sys.executable, "-V"], "cwd": str(root)})
        except OSError:
            pass
        else:
            raise AssertionError("Database failure was not surfaced")
    assert not store.job_dir(other_id).exists()
    print({"launch_failure": "job_id_returned", "database_failure": "directory_rolled_back"})


if __name__ == "__main__":
    main()

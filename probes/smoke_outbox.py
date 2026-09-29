"""Exercise durable callback failure, retry, and duplicate suppression offline."""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentrunner import callback, store


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    state = root / "probes" / ".probe-state" / "outbox-home"
    state.mkdir(parents=True, exist_ok=True)
    os.environ["AGENTRUNNER_HOME"] = str(state)
    job_id = "JOB-" + uuid.uuid4().hex[:12]
    message_id = str(uuid.uuid4())
    store.create_job({
        "id": job_id, "event_id": "EVT-" + uuid.uuid4().hex[:16],
        "command": ["python", "-V"], "cwd": str(root),
        "callback_thread": str(uuid.uuid4()),
    })
    store.transition(job_id, "COMPLETED", "process_exited", exit_code=0, finished_at=store.utc_now())
    assert store.get_job(job_id)["callback_status"] == "PENDING"
    failed = subprocess.CompletedProcess([], 1, "", "unavailable")
    accepted = subprocess.CompletedProcess([], 0, f"Queued message {message_id} for thread", "")
    with patch.object(callback.subprocess, "run", side_effect=[failed, accepted]) as mocked:
        assert callback.deliver(job_id) == "UNKNOWN"
        after_failure = store.get_job(job_id)
        assert after_failure["callback_attempts"] == 1
        assert job_id not in store.due_callbacks()
        assert callback.deliver(job_id, force=True) == "SENT"
        assert callback.deliver(job_id, force=True) == "SENT"
        assert mocked.call_count == 2
    final = store.get_job(job_id)
    assert final["callback_attempts"] == 2
    assert final["callback_message_id"] == message_id
    print(json.dumps({"job_id": job_id, "first": "UNKNOWN", "retry": "SENT", "queue_calls": 2}))


if __name__ == "__main__":
    main()

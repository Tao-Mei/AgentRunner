"""Verify callback identity, atomic claims, acknowledgement, and stale recovery."""

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentrunner import store


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / ("callback-receipt-" + uuid.uuid4().hex[:8])
    home.mkdir(parents=True)
    os.environ["AGENTRUNNER_HOME"] = str(home)
    job_id = "JOB-" + uuid.uuid4().hex[:12]
    event_id = "EVT-" + uuid.uuid4().hex[:16]
    thread_id = str(uuid.uuid4())
    store.create_job({"id": job_id, "event_id": event_id, "command": [sys.executable, "-V"],
                      "cwd": str(root), "callback_thread": thread_id})
    store.transition(job_id, "COMPLETED", "process_exited", exit_code=0, finished_at=store.utc_now())
    assert store.claim_callback(job_id)
    assert store.finish_callback(job_id, message_id=str(uuid.uuid4())) == "SENT"

    env = os.environ.copy()
    def invoke(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "agentrunner", *args], cwd=root, env=env,
                              capture_output=True, text=True, timeout=5)

    options = ("callback-claim", job_id, event_id, "--status", "COMPLETED", "--thread-id", thread_id)
    assert invoke("callback-claim", job_id, "EVT-wrong", "--status", "COMPLETED").returncode == 2
    assert invoke("callback-claim", job_id, event_id, "--status", "FAILED").returncode == 2
    assert invoke("callback-claim", job_id, event_id, "--status", "COMPLETED", "--thread-id", str(uuid.uuid4())).returncode == 2
    first = json.loads(invoke(*options).stdout)
    assert first["result"] == "new" and first["exit_code"] == 0, first
    second = json.loads(invoke(*options).stdout)
    assert second["result"] == "in_progress", second
    assert invoke("callback-ack", job_id, event_id, "--claim-token", "wrong").returncode == 2
    ack = invoke("callback-ack", job_id, event_id, "--claim-token", first["claim_token"])
    assert ack.returncode == 0 and json.loads(ack.stdout)["acknowledged"]
    assert json.loads(invoke(*options).stdout)["result"] == "duplicate"

    # A second event simulates an interrupted handler before acknowledgement.
    other_id = "JOB-" + uuid.uuid4().hex[:12]
    other_event = "EVT-" + uuid.uuid4().hex[:16]
    store.create_job({"id": other_id, "event_id": other_event, "command": [sys.executable, "-V"],
                      "cwd": str(root), "callback_thread": thread_id})
    store.transition(other_id, "FAILED", "process_exited", exit_code=7, finished_at=store.utc_now())
    assert store.claim_callback(other_id)
    assert store.finish_callback(other_id, message_id=str(uuid.uuid4())) == "SENT"
    stale_options = ("callback-claim", other_id, other_event, "--status", "FAILED", "--thread-id", thread_id)
    stale_first = json.loads(invoke(*stale_options).stdout)
    with sqlite3.connect(home / "runner.db") as con:
        con.execute("UPDATE callback_receipts SET claimed_at = ? WHERE job_id = ?",
                    ((datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(), other_id))
    recovered = json.loads(invoke(*stale_options).stdout)
    assert recovered["result"] == "recovered" and recovered["claim_token"] != stale_first["claim_token"]
    assert invoke("callback-ack", other_id, other_event, "--claim-token", stale_first["claim_token"]).returncode == 2
    assert invoke("callback-ack", other_id, other_event, "--claim-token", recovered["claim_token"]).returncode == 0
    print(json.dumps({"identity": "verified", "in_progress": "suppressed", "ack_duplicate": "suppressed",
                      "stale_claim": "recovered", "old_token": "rejected"}))


if __name__ == "__main__":
    main()

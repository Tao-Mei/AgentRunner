"""Codex callback transport for completed local jobs."""

from __future__ import annotations

import re
import subprocess

from . import codex_command, store


QUEUE_ID = re.compile(r"Queued message ([0-9a-f-]+) for thread")


def deliver(job_id: str, force: bool = False) -> str:
    job = store.get_job(job_id)
    if job is None:
        raise ValueError(f"Unknown job: {job_id}")
    if not job["callback_thread"]:
        return "NOT_REQUESTED"
    if job["status"] not in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise ValueError("Job is not terminal")
    if job["callback_status"] == "SENT":
        return "SENT"
    if not store.claim_callback(job_id, force=force):
        current = store.get_job(job_id)
        return current["callback_status"] if current else "UNKNOWN"

    message = (
        "$agent-runner-callback AGENTRUNNER_CALLBACK_V1 "
        f"job_id={job_id} event_id={job['event_id']} status={job['status']}"
    )
    try:
        result = subprocess.run(
            [codex_command.resolve(), "queue", "--thread", job["callback_thread"], "--message", message],
            capture_output=True, text=True, timeout=20, check=False,
        )
        output = result.stdout + result.stderr
        match = QUEUE_ID.search(output)
        if result.returncode != 0 or match is None:
            return store.finish_callback(job_id, error=f"queue exit={result.returncode}; accepted message ID unavailable")
        return store.finish_callback(job_id, message_id=match.group(1))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return store.finish_callback(job_id, error=f"{type(exc).__name__}: callback result unavailable")

"""Persist ownership of an explicitly authorized Codex goal pause."""
from __future__ import annotations

import json

from . import goal_rpc, store


def ensure_available(thread_id: str) -> None:
    with store.connect() as con:
        if con.execute("SELECT 1 FROM goal_handoffs WHERE thread_id = ? AND state IN ('PREPARING','PAUSED','RESUMING','UNKNOWN')",
                       (thread_id,)).fetchone():
            raise ValueError("This chat already has an unresolved goal handoff")


def dismiss(job_id: str) -> dict:
    """Explicit human recovery closes our ownership record, never the Codex goal."""
    job = store.get_job(job_id)
    if not job or job["status"] not in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise ValueError("Manual recovery needs a terminal Job")
    if record(job_id) is None:
        return {"status": "NOT_REQUESTED"}
    return finish(job_id, "ABANDONED")


def record(job_id: str) -> dict | None:
    with store.connect() as con:
        row = con.execute("SELECT * FROM goal_handoffs WHERE job_id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def finish(job_id: str, state: str, *, paused: dict | None = None, error: str | None = None) -> dict:
    with store.connect() as con:
        con.execute("UPDATE goal_handoffs SET state = ?, paused_json = COALESCE(?, paused_json), error = ? WHERE job_id = ?",
                    (state, json.dumps(paused) if paused else None, error, job_id))
    store.add_event(job_id, "goal_handoff", {"state": state, "error": error})
    return {"status": state, "error": error}


def pause(job_id: str) -> dict:
    job = store.get_job(job_id)
    if not job or not job.get("callback_thread"):
        raise ValueError("Goal pause needs a Job with an originating callback thread")
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM goal_handoffs WHERE thread_id = ? AND state IN ('PREPARING','PAUSED','RESUMING','UNKNOWN')",
                       (job["callback_thread"],)).fetchone():
            raise ValueError("This chat already has an unresolved goal handoff")
        con.execute("INSERT INTO goal_handoffs (job_id,event_id,thread_id,state) VALUES (?,?,?,'PREPARING')",
                    (job_id, job["event_id"], job["callback_thread"]))
    try:
        original = goal_rpc.exchange(job["callback_thread"])
        if original is not None and original.get("threadId") != job["callback_thread"]:
            raise ValueError("Goal protocol returned another chat")
        if original is None or original["status"] != "active":
            return finish(job_id, "NOT_ACTIVE")
        with store.connect() as con:
            con.execute("UPDATE goal_handoffs SET original_json = ? WHERE job_id = ?", (json.dumps(original), job_id))
        paused = goal_rpc.exchange(job["callback_thread"], "paused", original)
        return finish(job_id, "PAUSED", paused=paused)
    except Exception as exc:
        # A lost response may have followed an effective pause. Never guess or retry it.
        return finish(job_id, "UNKNOWN", error=type(exc).__name__)


def release(job_id: str, event_id: str, claim_token: str, thread_id: str) -> dict:
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        job = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        receipt = con.execute("SELECT * FROM callback_receipts WHERE job_id = ? AND event_id = ?", (job_id, event_id)).fetchone()
        if (not job or job["event_id"] != event_id or job["callback_thread"] != thread_id or
                job["status"] not in {"COMPLETED", "FAILED", "CANCELLED"} or not receipt or
                receipt["state"] != "HANDLING" or receipt["claim_token"] != claim_token):
            raise ValueError("Goal release requires the current terminal callback claim and its thread")
        row = con.execute("SELECT * FROM goal_handoffs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return {"status": "NOT_REQUESTED"}
        if row["event_id"] != event_id or row["thread_id"] != thread_id:
            raise ValueError("Saved goal handoff does not match this callback")
        if row["state"] != "PAUSED":
            return {"status": row["state"], "error": row["error"]}
        others = con.execute("SELECT id FROM jobs WHERE callback_thread = ? AND id != ? AND status IN ('CREATED','RUNNING','FINALIZING','RESUMING','UNKNOWN')",
                             (thread_id, job_id)).fetchall()
        if others:
            return {"status": "BLOCKED", "active_jobs": [other["id"] for other in others]}
        con.execute("UPDATE goal_handoffs SET state = 'RESUMING' WHERE job_id = ?", (job_id,))
        expected = json.loads(row["paused_json"])
    try:
        current = goal_rpc.exchange(thread_id)
        if current is None or not goal_rpc.matches(current, expected):
            return finish(job_id, "CHANGED", error="Goal changed after handoff; resume manually if intended")
        goal_rpc.exchange(thread_id, "active", expected)
        return finish(job_id, "RELEASED")
    except Exception as exc:
        return finish(job_id, "UNKNOWN", error=type(exc).__name__)

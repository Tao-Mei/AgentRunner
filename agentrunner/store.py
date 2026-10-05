"""Durable job and event state for the local prototype."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import environment


class StoreConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool | None:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def home() -> Path:
    return Path(os.environ.get("AGENTRUNNER_HOME", Path.home() / ".agentrunner")).resolve()


def job_dir(job_id: str) -> Path:
    return home() / "jobs" / job_id


def connect() -> sqlite3.Connection:
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "runner.db", timeout=10, factory=StoreConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL DEFAULT 'command',
            name TEXT,
            command_json TEXT NOT NULL,
            pass_env_json TEXT NOT NULL DEFAULT '[]',
            watch_json TEXT NOT NULL DEFAULT '[]',
            cwd TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            worker_pid INTEGER,
            child_pid INTEGER,
            worker_create_time REAL,
            child_create_time REAL,
            resume_claimed_at TEXT,
            resume_count INTEGER NOT NULL DEFAULT 0,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            pause_requested INTEGER NOT NULL DEFAULT 0,
            stop_after_current_requested INTEGER NOT NULL DEFAULT 0,
            exit_code INTEGER,
            callback_thread TEXT,
            event_id TEXT NOT NULL,
            callback_status TEXT NOT NULL,
            callback_message_id TEXT,
            callback_error TEXT,
            callback_attempts INTEGER NOT NULL DEFAULT 0,
            callback_updated_at TEXT,
            callback_next_at TEXT,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            at TEXT NOT NULL,
            kind TEXT NOT NULL,
            detail_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_job_id ON events(job_id, id);
        CREATE TABLE IF NOT EXISTS workflow_steps (
            job_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            spec_json TEXT NOT NULL,
            is_finalizer INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            not_before TEXT,
            started_at TEXT,
            finished_at TEXT,
            pid INTEGER,
            process_create_time REAL,
            exit_code INTEGER,
            error TEXT,
            artifacts_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (job_id, step_id)
        );
        CREATE TABLE IF NOT EXISTS resource_limits (
            name TEXT PRIMARY KEY,
            capacity INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resource_leases (
            name TEXT NOT NULL,
            slot INTEGER NOT NULL,
            job_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            PRIMARY KEY (name, slot)
        );
        CREATE INDEX IF NOT EXISTS resource_leases_job ON resource_leases(job_id, step_id);
        CREATE TABLE IF NOT EXISTS desktop_instance (
            slot INTEGER PRIMARY KEY CHECK (slot = 1),
            pid INTEGER NOT NULL,
            process_create_time REAL NOT NULL,
            request_seq INTEGER NOT NULL DEFAULT 0,
            requested_job_id TEXT
        );
        CREATE TABLE IF NOT EXISTS callback_receipts (
            job_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            state TEXT NOT NULL,
            claim_token TEXT NOT NULL,
            claimed_at TEXT NOT NULL,
            acknowledged_at TEXT,
            claims INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (job_id, event_id)
        );
        CREATE TABLE IF NOT EXISTS goal_handoffs (
            job_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            state TEXT NOT NULL,
            original_json TEXT,
            paused_json TEXT,
            error TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS goal_handoff_thread ON goal_handoffs(thread_id)
            WHERE state IN ('PREPARING','PAUSED','RESUMING','UNKNOWN');
        """
    )
    columns = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
    if "callback_error" not in columns:
        con.execute("ALTER TABLE jobs ADD COLUMN callback_error TEXT")
    for name, declaration in (
        ("worker_create_time", "REAL"),
        ("child_create_time", "REAL"),
        ("cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
        ("pause_requested", "INTEGER NOT NULL DEFAULT 0"),
        ("stop_after_current_requested", "INTEGER NOT NULL DEFAULT 0"),
        ("callback_attempts", "INTEGER NOT NULL DEFAULT 0"),
        ("callback_updated_at", "TEXT"),
        ("callback_next_at", "TEXT"),
        ("kind", "TEXT NOT NULL DEFAULT 'command'"),
        ("name", "TEXT"),
        ("pass_env_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("watch_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("resume_claimed_at", "TEXT"),
        ("resume_count", "INTEGER NOT NULL DEFAULT 0"),
        ("user_locked", "INTEGER NOT NULL DEFAULT 0"),
        ("note", "TEXT NOT NULL DEFAULT ''"),
        ("archived", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in columns:
            con.execute(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}")
    return con


def claim_desktop(requested_job_id: str | None = None) -> tuple[bool, int]:
    """Claim the single desktop process or persist a request to show an existing one."""
    from . import processes

    pid = os.getpid()
    created = processes.created_at(pid)
    if created is None:
        raise RuntimeError("Cannot verify desktop process identity")
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM desktop_instance WHERE slot = 1").fetchone()
        if row is not None and processes.same_process(row["pid"], row["process_create_time"]) is not False:
            sequence = row["request_seq"] + 1
            con.execute("UPDATE desktop_instance SET request_seq = ?, requested_job_id = ? WHERE slot = 1",
                        (sequence, requested_job_id))
            return False, sequence
        con.execute(
            "INSERT OR REPLACE INTO desktop_instance "
            "(slot, pid, process_create_time, request_seq, requested_job_id) VALUES (1, ?, ?, 0, ?)",
            (pid, created, requested_job_id),
        )
        return True, 0


def desktop_show_request() -> tuple[int, str | None]:
    with connect() as con:
        row = con.execute("SELECT request_seq, requested_job_id FROM desktop_instance WHERE slot = 1").fetchone()
    return (row["request_seq"], row["requested_job_id"]) if row is not None else (0, None)


def release_desktop() -> None:
    from . import processes

    created = processes.created_at(os.getpid())
    if created is not None:
        with connect() as con:
            con.execute("DELETE FROM desktop_instance WHERE slot = 1 AND pid = ? AND process_create_time = ?",
                        (os.getpid(), created))


def create_job(job: dict[str, Any]) -> None:
    directory = job_dir(job["id"])
    directory.mkdir(parents=True, exist_ok=False)
    try:
        with connect() as con:
            con.execute(
                """INSERT INTO jobs
                (id, command_json, pass_env_json, watch_json, cwd, status, created_at, callback_thread, event_id, callback_status, name, note)
                VALUES (?, ?, ?, ?, ?, 'CREATED', ?, ?, ?, 'NOT_REQUESTED', ?, ?)""",
                (
                    job["id"], json.dumps(job["command"], ensure_ascii=False), json.dumps(job.get("pass_env", [])),
                    json.dumps(job.get("watch", [])), job["cwd"],
                    utc_now(), job.get("callback_thread"), job["event_id"], job.get("name"), job.get("note", ""),
                ),
            )
            con.execute(
                "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, ?, ?)",
                (job["id"], utc_now(), "created", "{}"),
            )
    except Exception:
        directory.rmdir()
        raise


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["command"] = json.loads(result.pop("command_json"))
    result["pass_env"] = json.loads(result.pop("pass_env_json"))
    result["watch"] = json.loads(result.pop("watch_json"))
    return result


def list_jobs() -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            "SELECT id, kind, name, status, callback_status, created_at, started_at, finished_at, exit_code, user_locked, note "
            "FROM jobs WHERE archived = 0 ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def create_workflow_job(job: dict[str, Any], spec: dict[str, Any]) -> None:
    directory = job_dir(job["id"])
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "workflow.json"
    try:
        path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        with connect() as con:
            con.execute("BEGIN IMMEDIATE")
            for name, capacity in spec["resources"].items():
                existing = con.execute("SELECT capacity FROM resource_limits WHERE name = ?", (name,)).fetchone()
                if existing and existing["capacity"] != capacity:
                    raise ValueError(f"Resource {name} already has capacity {existing['capacity']}")
            con.execute(
                """INSERT INTO jobs
                (id, kind, name, command_json, cwd, status, created_at, callback_thread, event_id, callback_status, note)
                VALUES (?, 'workflow', ?, '[]', ?, 'CREATED', ?, ?, ?, 'NOT_REQUESTED', ?)""",
                (job["id"], spec["name"], job["cwd"], utc_now(), job.get("callback_thread"), job["event_id"], job.get("note", "")),
            )
            con.execute(
                "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'created', '{}')",
                (job["id"], utc_now()),
            )
            for is_finalizer, rows in ((0, spec["steps"]), (1, spec["finalizers"])):
                for step in rows:
                    con.execute(
                        "INSERT INTO workflow_steps (job_id, step_id, spec_json, is_finalizer) VALUES (?, ?, ?, ?)",
                        (job["id"], step["id"], json.dumps(step, ensure_ascii=False), is_finalizer),
                    )
            for name, capacity in spec["resources"].items():
                con.execute("INSERT OR IGNORE INTO resource_limits (name, capacity) VALUES (?, ?)", (name, capacity))
    except Exception:
        path.unlink(missing_ok=True)
        directory.rmdir()
        raise


def list_steps(job_id: str) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute("SELECT * FROM workflow_steps WHERE job_id = ? ORDER BY rowid", (job_id,)).fetchall()
    result = []
    for row in rows:
        step = dict(row)
        step["spec"] = json.loads(step.pop("spec_json"))
        step["artifacts"] = json.loads(step.pop("artifacts_json"))
        result.append(step)
    return result


def start_step(job_id: str, step_id: str) -> bool:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT status, spec_json, not_before, is_finalizer FROM workflow_steps WHERE job_id = ? AND step_id = ?",
            (job_id, step_id),
        ).fetchone()
        if row is None or row["status"] != "PENDING" or (row["not_before"] and row["not_before"] > utc_now()):
            con.rollback()
            return False
        job = con.execute("SELECT status, cancel_requested, pause_requested, stop_after_current_requested "
                          "FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None or (not row["is_finalizer"] and
                           (job["status"] != "RUNNING" or job["cancel_requested"] or
                            job["pause_requested"] or job["stop_after_current_requested"])):
            con.rollback()
            return False
        spec = json.loads(row["spec_json"])
        leases: list[tuple[str, int]] = []
        for name in sorted(spec["resources"]):
            limit = con.execute("SELECT capacity FROM resource_limits WHERE name = ?", (name,)).fetchone()
            if limit is None:
                con.rollback()
                return False
            used = {value[0] for value in con.execute("SELECT slot FROM resource_leases WHERE name = ?", (name,))}
            slot = next((number for number in range(limit["capacity"]) if number not in used), None)
            if slot is None:
                con.rollback()
                return False
            leases.append((name, slot))
        for name, slot in leases:
            con.execute(
                "INSERT INTO resource_leases (name, slot, job_id, step_id) VALUES (?, ?, ?, ?)",
                (name, slot, job_id, step_id),
            )
        now = utc_now()
        con.execute(
            "UPDATE workflow_steps SET status = 'RUNNING', attempts = attempts + 1, started_at = ?, "
            "finished_at = NULL, error = NULL, exit_code = NULL WHERE job_id = ? AND step_id = ?",
            (now, job_id, step_id),
        )
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'step_started', ?)",
            (job_id, now, json.dumps({"step_id": step_id, "resources": leases})),
        )
        con.commit()
        return True
    finally:
        con.close()


def step_spawned(job_id: str, step_id: str, pid: int, process_create_time: float | None) -> None:
    with connect() as con:
        con.execute(
            "UPDATE workflow_steps SET pid = ?, process_create_time = ? "
            "WHERE job_id = ? AND step_id = ? AND status = 'RUNNING'",
            (pid, process_create_time, job_id, step_id),
        )


def finish_step(job_id: str, step_id: str, status: str, exit_code: int | None = None,
                error: str | None = None, artifacts: list[dict[str, Any]] | None = None) -> None:
    if status not in {"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED", "SKIPPED"}:
        raise ValueError("Invalid step terminal state")
    with connect() as con:
        now = utc_now()
        result = con.execute(
            "UPDATE workflow_steps SET status = ?, finished_at = ?, exit_code = ?, error = ?, artifacts_json = ? "
            "WHERE job_id = ? AND step_id = ? AND status IN ('RUNNING','PENDING')",
            (status, now, exit_code, error, json.dumps(artifacts or [], ensure_ascii=False), job_id, step_id),
        )
        if result.rowcount == 0:
            return
        con.execute("DELETE FROM resource_leases WHERE job_id = ? AND step_id = ?", (job_id, step_id))
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'step_finished', ?)",
            (job_id, now, json.dumps({"step_id": step_id, "status": status, "exit_code": exit_code, "error": error})),
        )


def retry_step(job_id: str, step_id: str, delay_seconds: float) -> bool:
    next_at = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
    with connect() as con:
        result = con.execute(
            "UPDATE workflow_steps SET status = 'PENDING', not_before = ? "
            "WHERE job_id = ? AND step_id = ? AND status IN ('FAILED','TIMED_OUT')",
            (next_at, job_id, step_id),
        )
        if result.rowcount:
            con.execute(
                "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'step_retry_scheduled', ?)",
                (job_id, utc_now(), json.dumps({"step_id": step_id, "not_before": next_at})),
            )
        return bool(result.rowcount)


def mark_step_unknown_if_running(job_id: str, step_id: str, reason: str) -> bool:
    with connect() as con:
        result = con.execute(
            "UPDATE workflow_steps SET status = 'UNKNOWN', error = ? "
            "WHERE job_id = ? AND step_id = ? AND status = 'RUNNING'",
            (reason, job_id, step_id),
        )
        if result.rowcount:
            con.execute(
                "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'step_unknown', ?)",
                (job_id, utc_now(), json.dumps({"step_id": step_id, "reason": reason})),
            )
        return bool(result.rowcount)


def resolve_step(job_id: str, step_id: str, outcome: str, evidence: str) -> None:
    if outcome not in {"completed", "failed", "retry"} or not evidence.strip():
        raise ValueError("Resolution needs completed, failed, or retry and nonempty evidence")
    clean_evidence = evidence[:500]
    for secret in environment.known_secrets():
        clean_evidence = clean_evidence.replace(secret, "[REDACTED]")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        job = con.execute("SELECT status, kind FROM jobs WHERE id = ?", (job_id,)).fetchone()
        row = con.execute(
            "SELECT status, attempts, spec_json FROM workflow_steps WHERE job_id = ? AND step_id = ?",
            (job_id, step_id),
        ).fetchone()
        if job is None or job["kind"] != "workflow" or job["status"] != "UNKNOWN" or row is None or row["status"] != "UNKNOWN":
            raise ValueError("Only an UNKNOWN step of an UNKNOWN workflow can be resolved")
        spec = json.loads(row["spec_json"])
        if outcome == "retry":
            if not spec.get("safe_to_retry") or row["attempts"] >= spec["max_attempts"]:
                raise ValueError("Retry requires a declared safe retry with attempts remaining")
            status, finished_at = "PENDING", None
        else:
            status, finished_at = outcome.upper(), utc_now()
        con.execute(
            "UPDATE workflow_steps SET status = ?, finished_at = ?, error = ?, not_before = NULL "
            "WHERE job_id = ? AND step_id = ?",
            (status, finished_at, f"Manually resolved: {clean_evidence}", job_id, step_id),
        )
        con.execute("DELETE FROM resource_leases WHERE job_id = ? AND step_id = ?", (job_id, step_id))
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'step_resolved', ?)",
            (job_id, utc_now(), json.dumps({"step_id": step_id, "outcome": outcome, "evidence": clean_evidence})),
        )
        con.commit()
    finally:
        con.close()


def claim_resume(job_id: str) -> bool:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT status, kind FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or row["kind"] != "workflow" or row["status"] != "UNKNOWN":
            con.rollback()
            return False
        unresolved = con.execute(
            "SELECT count(*) FROM workflow_steps WHERE job_id = ? AND status IN ('RUNNING','UNKNOWN')",
            (job_id,),
        ).fetchone()[0]
        if unresolved:
            con.rollback()
            return False
        now = utc_now()
        con.execute(
            "UPDATE jobs SET status = 'RESUMING', resume_claimed_at = ?, resume_count = resume_count + 1, error = NULL "
            "WHERE id = ?", (now, job_id),
        )
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'resume_claimed', '{}')",
            (job_id, now),
        )
        con.commit()
        return True
    finally:
        con.close()


def transition(job_id: str, status: str, kind: str, **changes: Any) -> None:
    allowed = {"started_at", "finished_at", "worker_pid", "child_pid", "worker_create_time", "child_create_time", "exit_code", "error"}
    if not changes.keys() <= allowed:
        raise ValueError("Unsupported job field")
    fields = ["status = ?", *[f"{field} = ?" for field in changes]]
    values = [status, *changes.values(), job_id]
    with connect() as con:
        con.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, ?, ?)",
            (job_id, utc_now(), kind, json.dumps(changes, ensure_ascii=False)),
        )
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            now = utc_now()
            pending = con.execute(
                "UPDATE jobs SET callback_status = 'PENDING', callback_updated_at = ?, callback_next_at = ? "
                "WHERE id = ? AND callback_thread IS NOT NULL AND callback_status = 'NOT_REQUESTED'",
                (now, now, job_id),
            )
            if pending.rowcount:
                con.execute(
                    "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'callback_pending', '{}')",
                    (job_id, now),
                )


def request_cancel(job_id: str) -> bool:
    with connect() as con:
        row = con.execute("SELECT status, cancel_requested FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or row["status"] not in {"CREATED", "RUNNING"}:
            return False
        if row["cancel_requested"]:
            return True
        con.execute("UPDATE jobs SET cancel_requested = 1 WHERE id = ?", (job_id,))
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'cancel_requested', '{}')",
            (job_id, utc_now()),
        )
        return True


def set_workflow_control(job_id: str, action: str) -> bool:
    """Atomically change scheduling, without freezing or killing active steps."""
    if action not in {"pause", "continue", "stop-after-current"}:
        raise ValueError("Invalid workflow control")
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT kind, status, cancel_requested, pause_requested, stop_after_current_requested "
            "FROM jobs WHERE id = ?", (job_id,),
        ).fetchone()
        if row is None or row["kind"] != "workflow" or row["status"] != "RUNNING" or row["cancel_requested"]:
            return False
        if action == "pause":
            if row["stop_after_current_requested"]:
                return False
            if row["pause_requested"]:
                return True
            con.execute("UPDATE jobs SET pause_requested = 1 WHERE id = ?", (job_id,))
            event = "scheduling_paused"
        elif action == "continue":
            if row["stop_after_current_requested"]:
                return False
            if not row["pause_requested"]:
                return True
            con.execute("UPDATE jobs SET pause_requested = 0 WHERE id = ?", (job_id,))
            event = "scheduling_resumed"
        else:
            if row["stop_after_current_requested"]:
                return True
            con.execute("UPDATE jobs SET stop_after_current_requested = 1, pause_requested = 0 WHERE id = ?", (job_id,))
            event = "stop_after_current_requested"
        con.execute("INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, ?, '{}')",
                    (job_id, utc_now(), event))
        return True


def clear_cancel_request(job_id: str, reason: str) -> None:
    with connect() as con:
        con.execute("UPDATE jobs SET cancel_requested = 0 WHERE id = ? AND status IN ('CREATED','RUNNING')", (job_id,))
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'cancel_unconfirmed', ?)",
            (job_id, utc_now(), json.dumps({"reason": reason})),
        )


def mark_unknown_if_active(job_id: str, reason: str) -> bool:
    with connect() as con:
        result = con.execute(
            "UPDATE jobs SET status = 'UNKNOWN', error = ? WHERE id = ? AND status IN ('CREATED','RUNNING','FINALIZING','RESUMING')",
            (reason, job_id),
        )
        if result.rowcount == 0:
            return False
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'process_identity_unconfirmed', ?)",
            (job_id, utc_now(), json.dumps({"reason": reason})),
        )
        return True


def claim_callback(job_id: str, force: bool = False) -> bool:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT status, callback_status, callback_updated_at, callback_next_at, callback_thread "
            "FROM jobs WHERE id = ?", (job_id,),
        ).fetchone()
        if row is None or not row["callback_thread"] or row["status"] not in {"COMPLETED", "FAILED", "CANCELLED"}:
            con.rollback()
            return False
        status = row["callback_status"]
        now = utc_now()
        if status == "SENT":
            con.rollback()
            return False
        if status == "SENDING" and row["callback_updated_at"]:
            stale = datetime.fromisoformat(row["callback_updated_at"]) + timedelta(seconds=45) <= datetime.now(timezone.utc)
            if not stale:
                con.rollback()
                return False
        if status == "UNKNOWN" and not force and row["callback_next_at"] and row["callback_next_at"] > now:
            con.rollback()
            return False
        if status not in {"PENDING", "UNKNOWN", "SENDING"}:
            con.rollback()
            return False
        con.execute(
            "UPDATE jobs SET callback_status = 'SENDING', callback_attempts = callback_attempts + 1, "
            "callback_updated_at = ?, callback_next_at = NULL WHERE id = ?",
            (now, job_id),
        )
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'callback_sending', '{}')",
            (job_id, now),
        )
        con.commit()
        return True
    finally:
        con.close()


def finish_callback(job_id: str, message_id: str | None = None, error: str | None = None) -> str:
    status = "SENT" if message_id else "UNKNOWN"
    with connect() as con:
        row = con.execute("SELECT callback_attempts FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown job: {job_id}")
        delay = min(30 * (2 ** min(row["callback_attempts"] - 1, 5)), 900)
        next_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat() if status == "UNKNOWN" else None
        con.execute(
            "UPDATE jobs SET callback_status = ?, callback_message_id = ?, callback_error = ?, "
            "callback_updated_at = ?, callback_next_at = ? WHERE id = ?",
            (status, message_id, error, utc_now(), next_at, job_id),
        )
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, ?, ?)",
            (job_id, utc_now(), "callback_" + status.lower(), json.dumps({"message_id": message_id, "error": error})),
        )
    return status


def due_callbacks() -> list[str]:
    now = utc_now()
    stale = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
    with connect() as con:
        rows = con.execute(
            "SELECT id FROM jobs WHERE callback_thread IS NOT NULL AND status IN ('COMPLETED','FAILED','CANCELLED') "
            "AND (callback_status = 'PENDING' OR (callback_status = 'UNKNOWN' AND (callback_next_at IS NULL OR callback_next_at <= ?)) "
            "OR (callback_status = 'SENDING' AND callback_updated_at <= ?))",
            (now, stale),
        ).fetchall()
    return [row["id"] for row in rows]


def claim_callback_event(job_id: str, event_id: str, status: str, thread_id: str | None = None) -> dict[str, Any]:
    """Validate a local callback and atomically claim one handling attempt."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        job = con.execute(
            "SELECT id, event_id, status, callback_thread, callback_status, exit_code FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if (job is None or job["event_id"] != event_id or job["status"] != status
                or status not in {"COMPLETED", "FAILED", "CANCELLED"} or not job["callback_thread"]
                or job["callback_status"] not in {"SENDING", "SENT", "UNKNOWN"}
                or (thread_id is not None and job["callback_thread"] != thread_id)):
            raise ValueError("Callback does not match a terminal Job and its configured thread")
        row = con.execute(
            "SELECT state, claim_token, claimed_at, claims FROM callback_receipts WHERE job_id = ? AND event_id = ?",
            (job_id, event_id),
        ).fetchone()
        result = {"job_id": job_id, "event_id": event_id, "job_status": status,
                  "exit_code": job["exit_code"], "callback_status": job["callback_status"]}
        handoff = con.execute("SELECT state FROM goal_handoffs WHERE job_id = ?", (job_id,)).fetchone()
        if handoff:
            result["goal_handoff"] = handoff["state"]
        if row and row["state"] == "HANDLED":
            return {**result, "result": "duplicate"}
        if row and datetime.fromisoformat(row["claimed_at"]) + timedelta(minutes=5) > datetime.now(timezone.utc):
            return {**result, "result": "in_progress"}
        token = uuid.uuid4().hex
        now = utc_now()
        if row:
            con.execute(
                "UPDATE callback_receipts SET state = 'HANDLING', claim_token = ?, claimed_at = ?, "
                "acknowledged_at = NULL, claims = claims + 1 WHERE job_id = ? AND event_id = ?",
                (token, now, job_id, event_id),
            )
            disposition = "recovered"
        else:
            con.execute(
                "INSERT INTO callback_receipts (job_id, event_id, state, claim_token, claimed_at) "
                "VALUES (?, ?, 'HANDLING', ?, ?)",
                (job_id, event_id, token, now),
            )
            disposition = "new"
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'callback_handling_claimed', ?)",
            (job_id, now, json.dumps({"event_id": event_id, "result": disposition})),
        )
        con.commit()
        return {**result, "result": disposition, "claim_token": token}
    finally:
        con.close()


def acknowledge_callback_event(job_id: str, event_id: str, claim_token: str) -> bool:
    with connect() as con:
        now = utc_now()
        changed = con.execute(
            "UPDATE callback_receipts SET state = 'HANDLED', acknowledged_at = ? "
            "WHERE job_id = ? AND event_id = ? AND claim_token = ? AND state = 'HANDLING'",
            (now, job_id, event_id, claim_token),
        ).rowcount
        if changed:
            con.execute(
                "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, 'callback_handling_acknowledged', ?)",
                (job_id, now, json.dumps({"event_id": event_id})),
            )
        return bool(changed)


def list_events(job_id: str) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            "SELECT at, kind, detail_json FROM events WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
    return [{"at": row["at"], "kind": row["kind"], "detail": json.loads(row["detail_json"])} for row in rows]


def add_event(job_id: str, kind: str, detail: dict[str, Any]) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO events (job_id, at, kind, detail_json) VALUES (?, ?, ?, ?)",
            (job_id, utc_now(), kind, json.dumps(detail, ensure_ascii=False)),
        )

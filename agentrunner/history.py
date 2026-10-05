"""User metadata and conservative removal of finished task history."""

import re
import shutil
import stat

from . import store


def update(job_id: str, *, locked: bool | None = None, note: str | None = None, name: str | None = None) -> bool:
    if locked is None and note is None and name is None:
        return False
    fields, values = [], []
    if locked is not None:
        fields.append("user_locked = ?")
        values.append(int(locked))
    if note is not None:
        fields.append("note = ?")
        values.append(note)
    if name is not None:
        fields.append("name = ?")
        values.append(name.strip() or None)
    with store.connect() as con:
        return bool(con.execute(
            f"UPDATE jobs SET {', '.join(fields)} WHERE id = ? AND archived = 0",
            (*values, job_id),
        ).rowcount)


def clean() -> dict:
    """Hide eligible records atomically, retain receipts, then delete only Runner logs.

    Archived identities stay available to callback-claim for duplicate detection.
    Working directories and their artifacts are never followed or removed.
    A filesystem failure is reported and retried on the next cleanup.
    """
    removed, errors = [], []
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        rows = con.execute("""
            SELECT j.id, j.archived FROM jobs j
            WHERE j.status IN ('COMPLETED','FAILED','CANCELLED') AND j.user_locked = 0
              AND ((j.callback_status = 'NOT_REQUESTED' AND j.callback_thread IS NULL) OR
                   (j.callback_status = 'SENT' AND EXISTS (
                       SELECT 1 FROM callback_receipts r WHERE r.job_id=j.id
                       AND r.event_id=j.event_id AND r.state='HANDLED')))
              AND NOT EXISTS (SELECT 1 FROM goal_handoffs h WHERE h.job_id=j.id
                  AND h.state NOT IN ('RELEASED','NOT_ACTIVE','NOT_REQUESTED','ABANDONED'))
              AND NOT EXISTS (SELECT 1 FROM resource_leases l WHERE l.job_id=j.id)
        """).fetchall()
        for row in rows:
            job_id = row["id"]
            if not re.fullmatch(r"JOB-[0-9a-f]{12}", job_id):
                errors.append(job_id + ": invalid task directory identifier")
                continue
            path = store.home() / "jobs" / job_id
            if path.resolve().parent != path.parent.absolute() or (path.exists() and (path.is_symlink() or
                    getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)):
                errors.append(job_id + ": redirected directory cannot be cleaned")
                continue
            if not row["archived"]:
                con.execute("UPDATE jobs SET archived=1, name=NULL, note='', command_json='[]', "
                            "pass_env_json='[]', watch_json='[]', cwd='' WHERE id=?", (job_id,))
                con.execute("DELETE FROM events WHERE job_id=?", (job_id,))
                con.execute("DELETE FROM workflow_steps WHERE job_id=?", (job_id,))
                removed.append(job_id)
        con.commit()
    # Only rows archived by a committed transaction can lose their log directory.
    with store.connect() as con:
        archived = con.execute("SELECT id FROM jobs WHERE archived=1").fetchall()
    for row in archived:
        job_id = row["id"]
        if not re.fullmatch(r"JOB-[0-9a-f]{12}", job_id):
            continue
        path = store.home() / "jobs" / job_id
        try:
            if path.exists():
                if path.resolve().parent != path.parent.absolute() or path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise OSError("redirected directory cannot be cleaned")
                shutil.rmtree(path)
        except OSError as exc:
            errors.append(f"{job_id}: {exc}")
    return {"removed": removed, "errors": errors}

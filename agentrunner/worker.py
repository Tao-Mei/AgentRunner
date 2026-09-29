"""Detached per-job supervisor. It owns the command after CLI acknowledgement."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from . import callback, environment, observer, processes, store


def write_ack(directory: Path, status: str, error: str | None = None) -> None:
    target = directory / "start-ack.json"
    temporary = directory / "start-ack.tmp"
    temporary.write_text(json.dumps({"status": status, "error": error}), encoding="utf-8")
    os.replace(temporary, target)


def run(job_id: str) -> int:
    job = store.get_job(job_id)
    if job is None:
        return 2
    directory = store.job_dir(job_id)
    try:
        process = subprocess.Popen(
            job["command"], cwd=job["cwd"], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
            env=environment.child_environment(job["pass_env"]),
        )
        store.transition(
            job_id, "RUNNING", "process_started", worker_pid=os.getpid(),
            child_pid=process.pid, started_at=store.utc_now(),
            worker_create_time=processes.created_at(os.getpid()),
            child_create_time=processes.created_at(process.pid),
        )
        capture = observer.start_capture(process, directory, job_id)
        write_ack(directory, "RUNNING")
        seen_files: dict[str, tuple[int, float]] = {}
        while True:
            try:
                exit_code = process.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                observer.sample_process(job_id, process.pid)
                observer.sample_files(job_id, Path(job["cwd"]), job["watch"], seen_files)
        observer.sample_files(job_id, Path(job["cwd"]), job["watch"], seen_files)
        observer.finish_capture(capture)
        current = store.get_job(job_id)
        final = "CANCELLED" if current and current["cancel_requested"] else ("COMPLETED" if exit_code == 0 else "FAILED")
        store.transition(job_id, final, "process_exited", exit_code=exit_code, finished_at=store.utc_now())
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        store.transition(job_id, "FAILED", "worker_error", error=error, finished_at=store.utc_now())
        if not (directory / "start-ack.json").exists():
            write_ack(directory, "FAILED", error)
        final = "FAILED"
    if job["callback_thread"]:
        callback.deliver(job_id)
    return 0 if final == "COMPLETED" else 1


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m agentrunner.worker JOB-ID")
    raise SystemExit(run(sys.argv[1]))


if __name__ == "__main__":
    main()

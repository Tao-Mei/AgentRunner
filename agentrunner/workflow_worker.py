"""Independent DAG supervisor for a persisted local workflow."""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

from . import callback, environment, observer, processes, store
from .worker import write_ack


def artifacts_for(patterns: list[str], cwd: Path) -> list[dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for pattern in patterns:
        for match in glob.iglob(str(cwd / pattern), recursive=True):
            path = Path(match).resolve()
            if not path.is_file() or not path.is_relative_to(cwd):
                continue
            relative = str(path.relative_to(cwd))
            stat = path.stat()
            found[relative] = {"path": relative, "size": stat.st_size, "modified_at": stat.st_mtime}
            if len(found) >= 1000:
                return list(found.values())
    return list(found.values())


def execute_step(job_id: str, step: dict, cwd: Path, finalizer: bool = False) -> str:
    spec = step["spec"]
    step_id = step["step_id"]
    directory = store.job_dir(job_id) / "steps" / step_id
    directory.mkdir(parents=True, exist_ok=True)
    if not finalizer and store.get_job(job_id)["cancel_requested"]:
        store.finish_step(job_id, step_id, "CANCELLED")
        return "CANCELLED"
    try:
        process = subprocess.Popen(
            spec["command"], cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
            env=environment.child_environment(spec["pass_env"]),
        )
        created = processes.created_at(process.pid)
        store.step_spawned(job_id, step_id, process.pid, created)
        capture = observer.start_capture(process, directory, job_id, step_id)
        deadline = time.monotonic() + spec["timeout_seconds"] if spec["timeout_seconds"] is not None else None
        next_observation = time.monotonic() + 5
        seen_files: dict[str, tuple[int, float]] = {}
        timed_out = False
        while True:
            if not finalizer and store.get_job(job_id)["cancel_requested"]:
                if processes.terminate_tree(process.pid, created) not in {"termination_requested", "already_exited"}:
                    process.kill()
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                if processes.terminate_tree(process.pid, created) not in {"termination_requested", "already_exited"}:
                    process.kill()
            try:
                remaining = deadline - time.monotonic() if deadline is not None else 1.0
                exit_code = process.wait(timeout=max(0.01, min(1.0, remaining)))
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= next_observation:
                    observer.sample_process(job_id, process.pid, step_id)
                    observer.sample_files(job_id, cwd, spec["artifacts"], seen_files, step_id)
                    next_observation = time.monotonic() + 5
        observer.sample_files(job_id, cwd, spec["artifacts"], seen_files, step_id)
        observer.finish_capture(capture)
        cancelled = not finalizer and bool(store.get_job(job_id)["cancel_requested"])
        status = "CANCELLED" if cancelled else ("TIMED_OUT" if timed_out else ("COMPLETED" if exit_code == 0 else "FAILED"))
        artifacts = artifacts_for(spec["artifacts"], cwd) if status == "COMPLETED" else []
        store.finish_step(job_id, step_id, status, exit_code=exit_code, artifacts=artifacts)
    except Exception as exc:
        status = "FAILED"
        store.finish_step(job_id, step_id, status, error=f"{type(exc).__name__}: {exc}")
    if status in {"FAILED", "TIMED_OUT"} and not finalizer:
        current = next(row for row in store.list_steps(job_id) if row["step_id"] == step_id)
        if current["attempts"] < spec["max_attempts"] and not store.get_job(job_id)["cancel_requested"]:
            store.retry_step(job_id, step_id, spec["retry_delay_seconds"])
            return "RETRY_SCHEDULED"
    return status


def cancel_active(job_id: str) -> list[dict[str, object]]:
    actions = []
    for step in store.list_steps(job_id):
        if step["status"] == "RUNNING" and not step["is_finalizer"]:
            action = processes.terminate_tree(step["pid"], step["process_create_time"])
            actions.append({"step_id": step["step_id"], "action": action})
    return actions


def run_dag(job_id: str, spec: dict) -> str:
    cwd = Path(spec["cwd"])
    active: dict[Future[str], str] = {}
    with ThreadPoolExecutor(max_workers=spec["max_parallel"]) as pool:
        while True:
            job = store.get_job(job_id)
            steps = [row for row in store.list_steps(job_id) if not row["is_finalizer"]]
            by_id = {row["step_id"]: row for row in steps}
            cancelled = bool(job["cancel_requested"])
            stopping = bool(job["stop_after_current_requested"])
            paused = bool(job["pause_requested"])
            failed = any(row["status"] in {"FAILED", "TIMED_OUT"} for row in steps)
            if not cancelled and not stopping and not paused and not failed:
                active_bases = [by_id[step_id]["spec"]["base"] for step_id in active.values()]
                for step in steps:
                    if len(active) >= spec["max_parallel"]:
                        break
                    if step["status"] != "PENDING":
                        continue
                    step_spec = step["spec"]
                    if not all(by_id[dep]["status"] == "COMPLETED" for dep in step_spec["deps"]):
                        continue
                    base = step_spec["base"]
                    limit = step_spec["concurrency"]
                    if limit is not None and active_bases.count(base) >= limit:
                        continue
                    if not store.start_step(job_id, step["step_id"]):
                        continue
                    active_bases.append(base)
                    future = pool.submit(execute_step, job_id, step, cwd)
                    active[future] = step["step_id"]
            if not active:
                if cancelled or stopping or failed or all(row["status"] == "COMPLETED" for row in steps):
                    break
                time.sleep(0.5)
                continue
            completed, _ = wait(active, timeout=0.5, return_when=FIRST_COMPLETED)
            for future in completed:
                step_id = active.pop(future)
                try:
                    future.result()
                except Exception as exc:
                    store.finish_step(job_id, step_id, "FAILED", error=f"Worker future: {type(exc).__name__}: {exc}")
    remaining = [row for row in store.list_steps(job_id) if not row["is_finalizer"] and row["status"] == "PENDING"]
    for step in remaining:
        store.finish_step(job_id, step["step_id"], "SKIPPED", error="Dependency failed or workflow stopped")
    if store.get_job(job_id)["cancel_requested"]:
        return "CANCELLED"
    rows = [row for row in store.list_steps(job_id) if not row["is_finalizer"]]
    if any(row["status"] in {"FAILED", "TIMED_OUT"} for row in rows):
        return "FAILED"
    if store.get_job(job_id)["stop_after_current_requested"]:
        return "CANCELLED"
    return "FAILED" if any(row["status"] != "COMPLETED" for row in rows) else "COMPLETED"


def run_finalizers(job_id: str, spec: dict) -> bool:
    failed = False
    cwd = Path(spec["cwd"])
    for step in [row for row in store.list_steps(job_id) if row["is_finalizer"]]:
        if step["status"] == "COMPLETED":
            continue
        if step["status"] != "PENDING":
            failed = True
            continue
        acquired = False
        while not (acquired := store.start_step(job_id, step["step_id"])):
            current = next(row for row in store.list_steps(job_id) if row["step_id"] == step["step_id"])
            if current["status"] != "PENDING":
                failed = True
                break
            time.sleep(0.5)
        if not acquired:
            continue
        if execute_step(job_id, step, cwd, finalizer=True) != "COMPLETED":
            failed = True
    return not failed


def run(job_id: str) -> int:
    job = store.get_job(job_id)
    if job is None or job["kind"] != "workflow":
        return 2
    directory = store.job_dir(job_id)
    try:
        spec = json.loads((directory / "workflow.json").read_text(encoding="utf-8"))
        if any(step["status"] in {"RUNNING", "UNKNOWN"} for step in store.list_steps(job_id)):
            write_ack(directory, "FAILED", "Unresolved in-flight workflow step")
            return 2
        store.transition(
            job_id, "RUNNING", "workflow_started", worker_pid=os.getpid(),
            worker_create_time=processes.created_at(os.getpid()), started_at=store.utc_now(),
        )
        write_ack(directory, "RUNNING")
        outcome = run_dag(job_id, spec)
        store.transition(job_id, "FINALIZING", "finalizing")
        finalizers_ok = run_finalizers(job_id, spec)
        if not finalizers_ok and outcome == "COMPLETED":
            outcome = "FAILED"
        store.transition(
            job_id, outcome, "workflow_finished", finished_at=store.utc_now(),
            exit_code=0 if outcome == "COMPLETED" else 1,
            error="Finalizer failed" if not finalizers_ok else None,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        store.transition(job_id, "UNKNOWN", "workflow_worker_error", error=error)
        if not (directory / "start-ack.json").exists():
            write_ack(directory, "FAILED", error)
        return 2
    if job["callback_thread"]:
        callback.deliver(job_id)
    return 0 if outcome == "COMPLETED" else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m agentrunner.workflow_worker JOB-ID")
    raise SystemExit(run(sys.argv[1]))

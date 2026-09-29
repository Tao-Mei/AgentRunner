"""Small CLI for local command submission and observation."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import callback, environment, processes, store


THREAD_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


def command_args(raw: list[str]) -> list[str]:
    command = raw[1:] if raw and raw[0] == "--" else raw
    if not command:
        raise ValueError("Missing command after --")
    return command


def preflight(command: list[str], cwd: str, thread: str | None) -> Path:
    directory = Path(cwd).resolve()
    if not directory.is_dir():
        raise ValueError(f"Working directory does not exist: {directory}")
    executable = command[0]
    candidate = Path(executable)
    if not candidate.is_absolute():
        candidate = directory / candidate
    if shutil.which(executable, path=os.environ.get("PATH")) is None and not candidate.is_file():
        raise ValueError(f"Executable not found: {executable}")
    if thread and not THREAD_ID.fullmatch(thread):
        raise ValueError("Callback thread must be a UUID")
    return directory


def launch_worker(job_id: str, event_id: str, module: str) -> tuple[dict[str, str], subprocess.Popen[bytes] | None]:
    env = os.environ.copy()
    env["AGENTRUNNER_HOME"] = str(store.home())
    flags = 0
    kwargs: dict[str, object] = {}
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        with (store.job_dir(job_id) / "worker.log").open("wb") as worker_log:
            worker = subprocess.Popen(
                [sys.executable, "-m", module, job_id],
                cwd=str(Path(__file__).resolve().parent.parent), env=env,
                stdin=subprocess.DEVNULL, stdout=worker_log, stderr=worker_log,
                close_fds=True, creationflags=flags, **kwargs,
            )
    except OSError as exc:
        reason = f"Worker launch result unavailable: {type(exc).__name__}: {exc}"
        store.add_event(job_id, "worker_launch_unconfirmed", {"error": reason})
        return {"status": "UNKNOWN_SUBMISSION", "job_id": job_id, "event_id": event_id,
                "error": reason + "; inspect this Job before resubmitting"}, None
    ack = store.job_dir(job_id) / "start-ack.json"
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if ack.exists():
            result = json.loads(ack.read_text(encoding="utf-8"))
            if result["status"] == "RUNNING":
                return {"status": "ACCEPTED", "job_id": job_id, "event_id": event_id}, worker
            return {"status": "REJECTED", "job_id": job_id, "error": result.get("error") or "Worker failed"}, worker
        if worker.poll() is not None:
            return {"status": "UNKNOWN_SUBMISSION", "job_id": job_id, "error": f"Worker exited: {worker.returncode}"}, worker
        time.sleep(0.05)
    return {"status": "UNKNOWN_SUBMISSION", "job_id": job_id, "error": "Worker acknowledgement timeout; inspect this job before resubmitting"}, worker


def submit(command: list[str], cwd: str, thread: str | None,
           pass_env: list[str] | None = None,
           watch: list[str] | None = None) -> tuple[dict[str, str], subprocess.Popen[bytes] | None]:
    directory = preflight(command, cwd, thread)
    names = environment.validate(pass_env)
    if watch is None:
        watch = []
    if not isinstance(watch, list) or not all(isinstance(pattern, str) and pattern for pattern in watch):
        raise ValueError("watch must be a list of file patterns")
    job_id = "JOB-" + uuid.uuid4().hex[:12]
    event_id = "EVT-" + uuid.uuid4().hex[:16]
    store.create_job({"id": job_id, "event_id": event_id, "command": command, "cwd": str(directory),
                      "callback_thread": thread, "pass_env": names, "watch": watch})
    return launch_worker(job_id, event_id, "agentrunner.worker")


def submit_workflow(path: str, cwd: str | None, thread: str | None) -> tuple[dict[str, str], subprocess.Popen[bytes] | None]:
    from . import workflow
    if thread and not THREAD_ID.fullmatch(thread):
        raise ValueError("Callback thread must be a UUID")
    spec = workflow.load(path, cwd)
    job_id = "JOB-" + uuid.uuid4().hex[:12]
    event_id = "EVT-" + uuid.uuid4().hex[:16]
    store.create_workflow_job(
        {"id": job_id, "event_id": event_id, "cwd": spec["cwd"], "callback_thread": thread}, spec,
    )
    return launch_worker(job_id, event_id, "agentrunner.workflow_worker")


def finished_result(job_id: str) -> dict[str, object]:
    job = store.get_job(job_id)
    if job is None:
        return {"status": "UNKNOWN", "job_id": job_id, "error": "Job state missing"}
    return {
        "status": job["status"], "job_id": job_id, "event_id": job["event_id"],
        "exit_code": job["exit_code"], "callback_status": job["callback_status"],
    }


def reconcile() -> list[dict[str, object]]:
    changed: list[dict[str, object]] = []
    for summary in store.list_jobs():
        if summary["status"] not in {"CREATED", "RUNNING", "FINALIZING", "RESUMING", "UNKNOWN"}:
            continue
        job = store.get_job(summary["id"])
        assert job is not None
        if job["status"] == "UNKNOWN":
            if job["kind"] == "workflow":
                for step in store.list_steps(job["id"]):
                    if step["status"] != "RUNNING":
                        continue
                    alive = processes.same_process(step["pid"], step["process_create_time"])
                    if alive is not True and store.mark_step_unknown_if_running(
                        job["id"], step["step_id"], f"Step process identity={alive}; outcome unconfirmed",
                    ):
                        changed.append({"job_id": job["id"], "step_id": step["step_id"], "status": "UNKNOWN", "child_alive": alive})
            continue
        if job["status"] == "CREATED":
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(job["created_at"])).total_seconds()
            if age < 10:
                continue
        if job["status"] == "RESUMING" and job["resume_claimed_at"]:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(job["resume_claimed_at"])).total_seconds()
            if age < 10:
                continue
        worker_alive = processes.same_process(job["worker_pid"], job["worker_create_time"])
        if worker_alive is True:
            continue
        if job["kind"] == "workflow":
            child_states = [processes.same_process(step["pid"], step["process_create_time"])
                            for step in store.list_steps(job["id"]) if step["status"] == "RUNNING"]
            child_alive = True if True in child_states else (None if None in child_states else False)
        else:
            child_alive = processes.same_process(job["child_pid"], job["child_create_time"])
        reason = f"Worker identity={worker_alive}; child identity={child_alive}; exit result cannot be inferred"
        if store.mark_unknown_if_active(job["id"], reason):
            changed.append({"job_id": job["id"], "status": "UNKNOWN", "child_alive": child_alive})
            if job["kind"] == "workflow":
                for step in store.list_steps(job["id"]):
                    if step["status"] == "RUNNING":
                        alive = processes.same_process(step["pid"], step["process_create_time"])
                        if alive is not True and store.mark_step_unknown_if_running(
                            job["id"], step["step_id"], f"Step process identity={alive}; outcome unconfirmed",
                        ):
                            changed.append({"job_id": job["id"], "step_id": step["step_id"], "status": "UNKNOWN", "child_alive": alive})
    return changed


def resume_workflow(job_id: str) -> tuple[dict[str, object], int]:
    job = store.get_job(job_id)
    if job is None or job["kind"] != "workflow":
        raise ValueError("Workflow job not found")
    if job["status"] != "UNKNOWN":
        raise ValueError("Only an UNKNOWN workflow can be resumed")
    worker_alive = processes.same_process(job["worker_pid"], job["worker_create_time"])
    if worker_alive is not False:
        return {"status": "NEEDS_DECISION", "job_id": job_id, "reason": "Previous supervisor identity is not confirmed dead"}, 2
    unresolved = [step["step_id"] for step in store.list_steps(job_id) if step["status"] in {"RUNNING", "UNKNOWN"}]
    if unresolved:
        return {"status": "NEEDS_DECISION", "job_id": job_id, "unresolved_steps": unresolved}, 2
    if not store.claim_resume(job_id):
        return {"status": "NEEDS_DECISION", "job_id": job_id, "reason": "Recovery claim failed or state changed"}, 2
    (store.job_dir(job_id) / "start-ack.json").unlink(missing_ok=True)
    result, _ = launch_worker(job_id, job["event_id"], "agentrunner.workflow_worker")
    if result["status"] == "ACCEPTED":
        result["handoff"] = "Workflow resumed from persisted checkpoint; do not poll from the Agent turn"
    return result, 0 if result["status"] == "ACCEPTED" else 2


def resolve_workflow_step(job_id: str, step_id: str, outcome: str, evidence: str) -> dict[str, object]:
    job = store.get_job(job_id)
    if job is None or job["kind"] != "workflow" or job["status"] != "UNKNOWN":
        raise ValueError("Only an UNKNOWN workflow step can be resolved")
    step = next((row for row in store.list_steps(job_id) if row["step_id"] == step_id), None)
    if step is None or step["status"] != "UNKNOWN":
        raise ValueError("Step is not UNKNOWN")
    child_alive = processes.same_process(step["pid"], step["process_create_time"])
    if child_alive is True or (outcome == "retry" and child_alive is not False):
        raise ValueError("Step process may still be running; retry requires a confirmed exited process")
    store.resolve_step(job_id, step_id, outcome, evidence)
    return {"job_id": job_id, "step_id": step_id, "resolved_as": outcome}


def stop_orphan_step(job_id: str, step_id: str) -> tuple[dict[str, object], int]:
    job = store.get_job(job_id)
    if job is None or job["kind"] != "workflow" or job["status"] != "UNKNOWN":
        raise ValueError("Only an UNKNOWN workflow can contain a stoppable orphan step")
    step = next((row for row in store.list_steps(job_id) if row["step_id"] == step_id), None)
    if step is None or step["status"] != "RUNNING":
        raise ValueError("Step is not an in-flight orphan")
    if processes.same_process(step["pid"], step["process_create_time"]) is not True:
        return {"job_id": job_id, "step_id": step_id, "status": "UNKNOWN", "reason": "Process identity not confirmed"}, 2
    outcome = processes.terminate_tree(step["pid"], step["process_create_time"])
    store.add_event(job_id, "orphan_stop_requested", {"step_id": step_id, "process_action": outcome})
    return {"job_id": job_id, "step_id": step_id, "process_action": outcome}, 0 if outcome == "termination_requested" else 2


def cancel_job(job_id: str) -> tuple[dict[str, object], int]:
    job = store.get_job(job_id)
    if job is None:
        raise ValueError(f"Unknown job: {job_id}")
    if job["status"] not in {"CREATED", "RUNNING"}:
        return {"job_id": job_id, "status": job["status"], "cancel_requested": False}, 0
    if job["kind"] == "workflow":
        from .workflow_worker import cancel_active
        store.request_cancel(job_id)
        actions = cancel_active(job_id)
        return {"job_id": job_id, "cancel_requested": True, "process_actions": actions}, 0
    identity = processes.same_process(job["child_pid"], job["child_create_time"])
    if identity is not True:
        return {"job_id": job_id, "status": "UNKNOWN", "reason": "Child process identity is not confirmed"}, 2
    store.request_cancel(job_id)
    outcome = processes.terminate_tree(job["child_pid"], job["child_create_time"])
    if outcome not in {"termination_requested", "already_exited"}:
        store.clear_cancel_request(job_id, outcome)
    result = {"job_id": job_id, "cancel_requested": outcome in {"termination_requested", "already_exited"}, "process_action": outcome}
    return result, 0 if outcome in {"termination_requested", "already_exited"} else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="runner",
        description="Local detached command and workflow runner",
        epilog="ACCEPTED transfers execution to Runner. Codex callback needs --callback-thread and a working local codex queue; delivery is not exactly once. Inspect UNKNOWN_SUBMISSION by Job ID before resubmitting.",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    run_parser = sub.add_parser("run", help="Submit a local command to a detached worker")
    run_parser.add_argument("--cwd", default=".")
    run_parser.add_argument("--callback-thread")
    run_parser.add_argument("--pass-env", action="append", default=[])
    run_parser.add_argument("--watch", action="append", default=[])
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    exec_parser = sub.add_parser("exec", help="Run a short command or promote it after a grace period")
    exec_parser.add_argument("--cwd", default=".")
    exec_parser.add_argument("--callback-thread")
    exec_parser.add_argument("--pass-env", action="append", default=[])
    exec_parser.add_argument("--watch", action="append", default=[])
    exec_parser.add_argument("--adaptive", action="store_true")
    exec_parser.add_argument("--grace-seconds", type=float, default=10)
    exec_parser.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("jobs", help="List jobs")
    sub.add_parser("reconcile", help="Mark jobs whose supervisor identity cannot be confirmed")
    serve_parser = sub.add_parser("serve", help="Run the local status API and browser UI")
    serve_parser.add_argument("--port", type=int, default=8765)
    ui_parser = sub.add_parser("ui", help="Print a local UI URL with an access token")
    ui_parser.add_argument("--port", type=int, default=8765)
    show_parser = sub.add_parser("show", help="Show a job and its events")
    show_parser.add_argument("job_id")
    logs_parser = sub.add_parser("logs", help="Read a captured log")
    logs_parser.add_argument("job_id")
    logs_parser.add_argument("--stream", choices=["stdout", "stderr", "worker"], default="stdout")
    logs_parser.add_argument("--step", help="Workflow step ID")
    retry_parser = sub.add_parser("callback-retry", help="Retry an unresolved callback")
    retry_parser.add_argument("job_id")
    claim_parser = sub.add_parser("callback-claim", help="Validate and claim a callback event for handling")
    claim_parser.add_argument("job_id")
    claim_parser.add_argument("event_id")
    claim_parser.add_argument("--status", choices=["COMPLETED", "FAILED", "CANCELLED"], required=True)
    claim_parser.add_argument("--thread-id")
    ack_parser = sub.add_parser("callback-ack", help="Acknowledge a claimed callback event")
    ack_parser.add_argument("job_id")
    ack_parser.add_argument("event_id")
    ack_parser.add_argument("--claim-token", required=True)
    cancel_parser = sub.add_parser("cancel", help="Request cancellation of a running job")
    cancel_parser.add_argument("job_id")
    submit_parser = sub.add_parser("submit", help="Validate and submit a local workflow YAML")
    submit_parser.add_argument("workflow")
    submit_parser.add_argument("--cwd")
    submit_parser.add_argument("--callback-thread")
    resume_parser = sub.add_parser("resume", help="Resume an UNKNOWN workflow from a verified checkpoint")
    resume_parser.add_argument("job_id")
    resolve_parser = sub.add_parser("resolve-step", help="Record a decision for an unconfirmed workflow step")
    resolve_parser.add_argument("job_id")
    resolve_parser.add_argument("step_id")
    resolve_parser.add_argument("--outcome", choices=["completed", "failed", "retry"], required=True)
    resolve_parser.add_argument("--evidence", required=True)
    orphan_parser = sub.add_parser("stop-orphan", help="Stop a verified live step after its supervisor was lost")
    orphan_parser.add_argument("job_id")
    orphan_parser.add_argument("step_id")
    args = parser.parse_args(argv)
    try:
        if args.action in {"run", "exec"}:
            if args.action == "exec" and (args.grace_seconds < 0 or args.grace_seconds > 300):
                raise ValueError("Grace seconds must be between 0 and 300")
            result, worker = submit(command_args(args.command), args.cwd, args.callback_thread, args.pass_env, args.watch)
            if result["status"] == "ACCEPTED" and args.action == "exec":
                if args.adaptive:
                    try:
                        assert worker is not None
                        worker.wait(timeout=args.grace_seconds)
                    except subprocess.TimeoutExpired:
                        result["status"] = "PROMOTED_TO_BACKGROUND"
                        result["handoff"] = "Job is owned by the detached worker; do not poll it from the Agent turn"
                else:
                    assert worker is not None
                    worker.wait()
                if result["status"] == "ACCEPTED":
                    result = finished_result(result["job_id"])
            elif result["status"] == "ACCEPTED":
                result["handoff"] = "Job is owned by the detached worker; do not poll it from the Agent turn"
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["status"] in {"ACCEPTED", "PROMOTED_TO_BACKGROUND", "COMPLETED"} else 1
        if args.action == "submit":
            result, _ = submit_workflow(args.workflow, args.cwd, args.callback_thread)
            if result["status"] == "ACCEPTED":
                result["handoff"] = "Workflow is owned by the detached supervisor; do not poll it from the Agent turn"
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["status"] == "ACCEPTED" else 1
        if args.action == "resume":
            result, code = resume_workflow(args.job_id)
            print(json.dumps(result, ensure_ascii=False))
            return code
        if args.action == "resolve-step":
            result = resolve_workflow_step(args.job_id, args.step_id, args.outcome, args.evidence)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.action == "stop-orphan":
            result, code = stop_orphan_step(args.job_id, args.step_id)
            print(json.dumps(result, ensure_ascii=False))
            return code
        if args.action == "callback-claim":
            print(json.dumps(store.claim_callback_event(args.job_id, args.event_id, args.status, args.thread_id), ensure_ascii=False))
            return 0
        if args.action == "callback-ack":
            acknowledged = store.acknowledge_callback_event(args.job_id, args.event_id, args.claim_token)
            print(json.dumps({"acknowledged": acknowledged}))
            return 0 if acknowledged else 2
        if args.action == "jobs":
            print(json.dumps(store.list_jobs(), ensure_ascii=False, indent=2))
            return 0
        if args.action == "reconcile":
            print(json.dumps({"changed": reconcile()}, ensure_ascii=False, indent=2))
            return 0
        if args.action == "serve":
            from .server import serve
            serve(args.port)
            return 0
        if args.action == "ui":
            from .server import access_token
            print(f"http://127.0.0.1:{args.port}/#token={access_token()}")
            return 0
        job = store.get_job(args.job_id)
        if job is None:
            raise ValueError(f"Unknown job: {args.job_id}")
        if args.action == "show":
            job["events"] = store.list_events(args.job_id)
            if job["kind"] == "workflow":
                job["steps"] = store.list_steps(args.job_id)
            print(json.dumps(job, ensure_ascii=False, indent=2))
            return 0
        if args.action == "logs":
            if args.step:
                if args.step not in {row["step_id"] for row in store.list_steps(args.job_id)}:
                    raise ValueError(f"Unknown workflow step: {args.step}")
                if args.stream == "worker":
                    raise ValueError("Workflow steps have stdout and stderr logs only")
                path = store.job_dir(args.job_id) / "steps" / args.step / f"{args.stream}.log"
            else:
                path = store.job_dir(args.job_id) / f"{args.stream}.log"
            if path.exists():
                sys.stdout.write(path.read_text(encoding="utf-8", errors="replace"))
            return 0
        if args.action == "callback-retry":
            print(json.dumps({"callback_status": callback.deliver(args.job_id, force=True)}))
            return 0
        if args.action == "cancel":
            result, code = cancel_job(job["id"])
            print(json.dumps(result))
            return code
    except (OSError, ValueError) as exc:
        print(f"runner: {exc}", file=sys.stderr)
        return 2
    return 2

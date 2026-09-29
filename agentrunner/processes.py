"""Process identity and tree control for local jobs."""

from __future__ import annotations

import psutil


def created_at(pid: int) -> float | None:
    try:
        return psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def same_process(pid: int | None, expected_created_at: float | None) -> bool | None:
    """True/False for a known identity, None if identity cannot be checked."""
    if pid is None or expected_created_at is None:
        return None
    try:
        process = psutil.Process(pid)
        return abs(process.create_time() - expected_created_at) < 0.01 and process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return None


def terminate_tree(pid: int | None, expected_created_at: float | None) -> str:
    identity = same_process(pid, expected_created_at)
    if identity is False:
        return "already_exited"
    if identity is None:
        return "identity_unknown"
    assert pid is not None
    try:
        parent = psutil.Process(pid)
        if abs(parent.create_time() - expected_created_at) >= 0.01:
            return "identity_unknown"
        children = parent.children(recursive=True)
        for child in reversed(children):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        parent.terminate()
        _, alive = psutil.wait_procs([*children, parent], timeout=3)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        return "termination_requested"
    except psutil.NoSuchProcess:
        return "already_exited"
    except psutil.AccessDenied:
        return "access_denied"

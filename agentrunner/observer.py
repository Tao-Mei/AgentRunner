"""Bounded log capture and factual process/file/structured-event observations."""

from __future__ import annotations

import glob
import json
import math
import os
import threading
from pathlib import Path
from typing import BinaryIO

import psutil

from . import environment, store


MAX_LOG_BYTES = 20 * 1024 * 1024
MAX_EVENT_LINE = 4096


class Redactor:
    def __init__(self, secrets: list[str]) -> None:
        self.patterns = sorted({secret.encode("utf-8") for secret in secrets if secret}, key=len, reverse=True)
        self.longest = max((len(pattern) for pattern in self.patterns), default=1)
        self.pending = b""

    def feed(self, chunk: bytes, final: bool = False) -> bytes:
        raw = self.pending + chunk
        if not self.patterns:
            self.pending = b""
            return raw
        cut = len(raw) if final else max(0, len(raw) - self.longest + 1)
        output = bytearray()
        position = 0
        while position < cut:
            matches = [(raw.find(pattern, position), pattern) for pattern in self.patterns]
            matches = [(index, pattern) for index, pattern in matches if index >= 0]
            if not matches:
                output.extend(raw[position:cut])
                position = cut
                break
            index, pattern = min(matches, key=lambda match: (match[0], -len(match[1])))
            if index >= cut:
                output.extend(raw[position:cut])
                position = cut
                break
            output.extend(raw[position:index])
            output.extend(b"[REDACTED]")
            position = index + len(pattern)
        self.pending = raw[position:]
        return bytes(output)


def _structured(line: bytes, job_id: str, step_id: str | None, secrets: list[str]) -> None:
    if not line.startswith(b"@@RUNNER ") or len(line) > MAX_EVENT_LINE or not line.endswith(b"\n"):
        return
    try:
        raw = json.loads(line[len(b"@@RUNNER "):].decode("utf-8"))
        if not isinstance(raw, dict):
            return
        event = raw.get("event")
        detail: dict[str, object] = {"step_id": step_id} if step_id else {}
        if event == "stage" and isinstance(raw.get("value"), str):
            value = raw["value"]
            for secret in secrets:
                value = value.replace(secret, "[REDACTED]")
            detail["value"] = value[:256]
        elif event == "progress":
            current, total = raw.get("current"), raw.get("total")
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                       for value in (current, total)):
                return
            detail.update({"current": current, "total": total})
            if isinstance(raw.get("unit"), str):
                unit = raw["unit"]
                for secret in secrets:
                    unit = unit.replace(secret, "[REDACTED]")
                detail["unit"] = unit[:32]
        elif event != "heartbeat":
            return
        store.add_event(job_id, "structured_" + event, detail)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError):
        return


def _rotate(path: Path, output: BinaryIO) -> BinaryIO:
    output.close()
    try:
        for index in (2, 1):
            source = path.with_name(path.name + f".{index}")
            target = path.with_name(path.name + f".{index + 1}")
            if source.exists():
                os.replace(source, target)
        if path.exists():
            os.replace(path, path.with_name(path.name + ".1"))
    except OSError:
        pass
    return path.open("ab", buffering=0)


def _pump(stream: BinaryIO, path: Path, job_id: str, step_id: str | None,
          parse_events: bool, secrets: list[str]) -> None:
    output = path.open("ab", buffering=0)
    redactor = Redactor(secrets)
    try:
        while True:
            chunk = stream.readline(65536)
            if not chunk:
                break
            clean = redactor.feed(chunk)
            if output.tell() + len(clean) > MAX_LOG_BYTES:
                output = _rotate(path, output)
            output.write(clean)
            if parse_events:
                _structured(chunk, job_id, step_id, secrets)
        ending = redactor.feed(b"", final=True)
        if output.tell() + len(ending) > MAX_LOG_BYTES:
            output = _rotate(path, output)
        output.write(ending)
    finally:
        output.close()
        stream.close()


def start_capture(process: object, directory: Path, job_id: str, step_id: str | None = None) -> list[threading.Thread]:
    threads = []
    secrets = environment.known_secrets()
    for stream, name, parse in ((process.stdout, "stdout", True), (process.stderr, "stderr", False)):
        assert stream is not None
        thread = threading.Thread(target=_pump, args=(stream, directory / f"{name}.log", job_id, step_id, parse, secrets), daemon=True)
        thread.start()
        threads.append(thread)
    return threads


def finish_capture(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError("Log capture thread did not finish")


def sample_process(job_id: str, pid: int, step_id: str | None = None) -> None:
    try:
        process = psutil.Process(pid)
        memory = process.memory_info().rss
        cpu = process.cpu_times()
        detail: dict[str, object] = {
            "pid": pid, "rss_bytes": memory, "cpu_seconds": cpu.user + cpu.system,
            "child_count": len(process.children(recursive=True)),
        }
        if step_id:
            detail["step_id"] = step_id
        store.add_event(job_id, "process_observed", detail)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return


def sample_files(job_id: str, cwd: Path, patterns: list[str], seen: dict[str, tuple[int, float]],
                 step_id: str | None = None) -> None:
    if not patterns:
        return
    count = 0
    for pattern in patterns:
        for match in glob.iglob(str(cwd / pattern), recursive=True):
            path = Path(match).resolve()
            if not path.is_file() or not path.is_relative_to(cwd):
                continue
            stat = path.stat()
            relative = str(path.relative_to(cwd))
            signature = (stat.st_size, stat.st_mtime)
            if seen.get(relative) != signature:
                seen[relative] = signature
                detail: dict[str, object] = {"path": relative, "size": stat.st_size, "modified_at": stat.st_mtime}
                if step_id:
                    detail["step_id"] = step_id
                store.add_event(job_id, "file_observed", detail)
            count += 1
            if count >= 1000:
                return

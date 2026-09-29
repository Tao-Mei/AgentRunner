"""Local, token-protected status API and small browser UI."""

from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import callback, store


def access_token() -> str:
    path = store.home() / "ui-token"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        token = secrets.token_urlsafe(32)
        try:
            with path.open("x", encoding="ascii") as output:
                output.write(token)
            if os.name != "nt":
                path.chmod(0o600)
            return token
        except FileExistsError:
            return path.read_text(encoding="ascii").strip()


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentRunner/0.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def respond(self, status: int, data: object) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + access_token()
        if secrets.compare_digest(supplied, expected):
            return True
        self.respond(401, {"error": "Authorization token required"})
        return False

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            content = (Path(__file__).with_name("ui.html")).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if not self.authorized():
            return
        if parsed.path == "/api/jobs":
            self.respond(200, {"jobs": store.list_jobs()})
            return
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 3 and parts[:2] == ["api", "jobs"]:
            job_id = parts[2]
            job = store.get_job(job_id)
            if job is None:
                self.respond(404, {"error": "Job not found"})
                return
            if len(parts) == 3:
                job["events"] = store.list_events(job_id)
                if job["kind"] == "workflow":
                    job["steps"] = store.list_steps(job_id)
                self.respond(200, job)
                return
            if len(parts) == 4 and parts[3] == "events":
                self.respond(200, {"events": store.list_events(job_id)})
                return
            if len(parts) == 4 and parts[3] == "logs":
                stream = parse_qs(parsed.query).get("stream", ["stdout"])[0]
                if stream not in {"stdout", "stderr", "worker"}:
                    self.respond(400, {"error": "Invalid stream"})
                    return
                path = store.job_dir(job_id) / f"{stream}.log"
                if path.exists():
                    with path.open("rb") as source:
                        source.seek(0, 2)
                        source.seek(max(0, source.tell() - 65536))
                        content = source.read().decode("utf-8", errors="replace")
                else:
                    content = ""
                self.respond(200, {"stream": stream, "tail": content})
                return
            if len(parts) == 6 and parts[3] == "steps" and parts[5] == "logs":
                step_id = unquote(parts[4])
                if step_id not in {row["step_id"] for row in store.list_steps(job_id)}:
                    self.respond(404, {"error": "Step not found"})
                    return
                stream = parse_qs(parsed.query).get("stream", ["stdout"])[0]
                if stream not in {"stdout", "stderr"}:
                    self.respond(400, {"error": "Invalid stream"})
                    return
                path = store.job_dir(job_id) / "steps" / step_id / f"{stream}.log"
                if path.exists():
                    with path.open("rb") as source:
                        source.seek(0, 2)
                        source.seek(max(0, source.tell() - 65536))
                        content = source.read().decode("utf-8", errors="replace")
                else:
                    content = ""
                self.respond(200, {"stream": stream, "tail": content})
                return
        self.respond(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if not self.authorized():
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/api/jobs":
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65536:
                self.respond(400, {"error": "Invalid request size"})
                return
            try:
                from .cli import submit
                body = json.loads(self.rfile.read(length))
                command = body["command"]
                if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
                    raise ValueError("command must be a nonempty string array")
                result, _ = submit(command, body.get("cwd", "."), body.get("callback_thread"),
                                   body.get("pass_env"), body.get("watch"))
                self.respond(202 if result["status"] == "ACCEPTED" else 409, result)
            except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
                self.respond(400, {"error": str(exc)})
            return
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel":
            from .cli import cancel_job
            try:
                result, code = cancel_job(parts[2])
                self.respond(200 if code == 0 else 409, result)
            except ValueError as exc:
                self.respond(404, {"error": str(exc)})
            return
        self.respond(404, {"error": "Not found"})


def maintenance(stop: threading.Event) -> None:
    from .cli import reconcile
    while not stop.is_set():
        try:
            reconcile()
            for job_id in store.due_callbacks():
                callback.deliver(job_id)
        except Exception as exc:
            print(f"maintenance error: {type(exc).__name__}: {exc}", flush=True)
        stop.wait(10)


def serve(port: int = 8765) -> None:
    if not 0 <= port <= 65535:
        raise ValueError("Port out of range")
    access_token()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    stop = threading.Event()
    thread = threading.Thread(target=maintenance, args=(stop,), daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    print(json.dumps({"status": "SERVING", "url": f"http://127.0.0.1:{actual_port}/"}), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop.set()
        server.server_close()

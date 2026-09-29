"""Interrupt an HTTP transfer and prove the next request resumes by byte range."""

import json
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ai_install.download_resumable import download


DATA = bytes(range(256)) * 8192
REQUESTS: list[str | None] = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        value = self.headers.get("Range")
        REQUESTS.append(value)
        if value is None and len(REQUESTS) == 1:
            self.send_response(200)
            self.send_header("Content-Length", str(len(DATA)))
            self.end_headers()
            self.wfile.write(DATA[: len(DATA) // 2])
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        assert value == f"bytes={len(DATA) // 2}-", value
        self.send_response(206)
        self.send_header("Content-Length", str(len(DATA) // 2))
        self.send_header("Content-Range", f"bytes {len(DATA) // 2}-{len(DATA) - 1}/{len(DATA)}")
        self.end_headers()
        self.wfile.write(DATA[len(DATA) // 2:])

    def log_message(self, *_: object) -> None:
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        directory = Path(__file__).resolve().parent / ".probe-state" / ("download-" + uuid.uuid4().hex[:8])
        target = directory / "model.zip"
        result = download(f"http://127.0.0.1:{server.server_port}/model.zip", target, attempts=2)
        assert target.read_bytes() == DATA
        assert result == {"bytes": len(DATA), "resumed": True}, result
        assert REQUESTS == [None, f"bytes={len(DATA) // 2}-"], REQUESTS
        print(json.dumps({"interrupted": True, "range_resume": True, "bytes": len(DATA)}))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()

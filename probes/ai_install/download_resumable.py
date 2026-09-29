"""Download one model archive with an on-disk partial file and HTTP Range resume."""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)")


def progress(current: int, total: int | None) -> None:
    if total:
        print("@@RUNNER " + json.dumps({"event": "progress", "current": current,
                                         "total": total, "unit": "bytes"}), flush=True)


def download(url: str, target: Path, attempts: int = 5) -> dict[str, int | bool]:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    if target.is_file() and target.stat().st_size > 0:
        return {"bytes": target.stat().st_size, "resumed": False}
    resumed = False
    for attempt in range(attempts):
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                if status == 206:
                    match = CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", ""))
                    if not match or int(match.group(1)) != offset:
                        raise RuntimeError("Server returned an inconsistent Content-Range")
                    total = int(match.group(3))
                    mode = "ab"
                    resumed = resumed or offset > 0
                elif status == 200:
                    total = int(response.headers["Content-Length"]) if response.headers.get("Content-Length") else None
                    mode = "wb"
                    offset = 0
                else:
                    raise RuntimeError(f"Unexpected HTTP status {status}")
                received = offset
                next_report = received + 1024 * 1024
                with partial.open(mode) as stream:
                    while True:
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        stream.write(block)
                        received += len(block)
                        if received >= next_report:
                            progress(received, total)
                            next_report = received + 1024 * 1024
                    stream.flush()
                    os.fsync(stream.fileno())
                if total is None or received != total:
                    raise RuntimeError(f"Incomplete response: {received}/{total or 'unknown'} bytes")
                os.replace(partial, target)
                progress(received, total)
                return {"bytes": received, "resumed": resumed}
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and offset:
                match = re.fullmatch(r"bytes \*/(\d+)", exc.headers.get("Content-Range", ""))
                if match and int(match.group(1)) == offset:
                    os.replace(partial, target)
                    return {"bytes": offset, "resumed": True}
            if attempt == attempts - 1:
                raise
        except (OSError, RuntimeError) as exc:
            if attempt == attempts - 1:
                raise
        time.sleep(min(2 ** attempt, 15))
    raise RuntimeError("Download attempts exhausted")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print("@@RUNNER " + json.dumps({"event": "stage", "value": "model_download"}), flush=True)
    print(json.dumps(download(args.url, args.target)), flush=True)


if __name__ == "__main__":
    main()

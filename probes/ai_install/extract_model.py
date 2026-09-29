"""Validate and extract a Vosk model ZIP into a final directory atomically."""

import json
import os
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath


def main() -> None:
    archive_path = Path(sys.argv[1]).resolve()
    target = Path(sys.argv[2]).resolve()
    expected_root = target.name
    if target.exists():
        if (target / "am" / "final.mdl").is_file() and (target / "conf" / "model.conf").is_file():
            print(json.dumps({"model": str(target), "already_extracted": True}))
            return
        raise RuntimeError("Existing model directory is incomplete")
    stage = target.parent / (".extract-" + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    total = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > 10000:
                raise ValueError("Too many archive entries")
            for info in infos:
                name = info.filename
                parts = PurePosixPath(name).parts
                if (not parts or parts[0] != expected_root or ".." in parts or "\\" in name
                        or ":" in name or name.startswith("/")):
                    raise ValueError(f"Unsafe or unexpected archive entry: {name}")
                total += info.file_size
                if total > 1024 * 1024 * 1024:
                    raise ValueError("Archive expands beyond 1 GiB")
                destination = stage.joinpath(*parts)
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("wb") as output:
                        while block := source.read(1024 * 1024):
                            output.write(block)
        source_root = stage / expected_root
        if not (source_root / "am" / "final.mdl").is_file() or not (source_root / "conf" / "model.conf").is_file():
            raise ValueError("Model archive lacks required Vosk files")
        os.replace(source_root, target)
        print(json.dumps({"model": str(target), "unpacked_bytes": total}))
    finally:
        if stage.exists():
            for path in sorted(stage.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            stage.rmdir()


if __name__ == "__main__":
    main()

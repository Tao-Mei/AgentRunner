"""Check safe model extraction and rejection of traversal entries."""

import json
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / ("extract-" + uuid.uuid4().hex[:8])
    home.mkdir(parents=True)
    script = root / "probes" / "ai_install" / "extract_model.py"
    model = home / "vosk-model-small-en-us-0.15"
    good_zip = home / "good.zip"
    with zipfile.ZipFile(good_zip, "w") as archive:
        archive.writestr(model.name + "/am/final.mdl", b"model")
        archive.writestr(model.name + "/conf/model.conf", b"config")
    good = subprocess.run([sys.executable, str(script), str(good_zip), str(model)],
                          capture_output=True, text=True, timeout=5)
    assert good.returncode == 0, good.stderr
    assert (model / "am" / "final.mdl").is_file()
    repeated = subprocess.run([sys.executable, str(script), str(good_zip), str(model)],
                              capture_output=True, text=True, timeout=5)
    assert repeated.returncode == 0 and json.loads(repeated.stdout)["already_extracted"]
    bad_zip = home / "bad.zip"
    bad_model = home / "bad-model"
    with zipfile.ZipFile(bad_zip, "w") as archive:
        archive.writestr("../escape.txt", b"bad")
    bad = subprocess.run([sys.executable, str(script), str(bad_zip), str(bad_model)],
                         capture_output=True, text=True, timeout=5)
    assert bad.returncode != 0 and not (home / "escape.txt").exists()
    print(json.dumps({"extracted": True, "idempotent": True, "traversal_rejected": True}))


if __name__ == "__main__":
    main()

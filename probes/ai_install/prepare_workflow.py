"""Prepare an isolated real Vosk installation acceptance Workflow; do not submit it."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workdir", type=Path)
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    scripts = Path(__file__).resolve().parent
    base = subprocess.run(["py", "-3.10", "-c", "import sys; print(sys.executable)"],
                          capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    venv = workdir / "venv"
    venv_python = venv / "Scripts" / "python.exe"
    archive = workdir / f"{MODEL_NAME}.zip"
    model = workdir / MODEL_NAME
    report = workdir / "verification.json"
    runner = [sys.executable, str(scripts / "run_venv.py"), str(venv_python)]
    retry = {"safe_to_retry": True, "retry": {"max_attempts": 2, "delay_seconds": 5}}
    workflow = {
        "version": 1, "job": {"name": "vosk-local-install-acceptance"}, "max_parallel": 2,
        "steps": [
            {"id": "venv", "command": [base, "-m", "venv", str(venv)],
             "timeout_seconds": 120, "artifacts": ["venv/pyvenv.cfg"]},
            {"id": "install", "after": ["venv"],
             "command": [*runner, "-m", "pip", "install", "--disable-pip-version-check", "--retries", "5",
                         "--timeout", "30", "--index-url", "https://pypi.org/simple", "vosk==0.3.45"],
             "timeout_seconds": 900, "artifacts": ["venv/Lib/site-packages/vosk/__init__.py"], **retry},
            {"id": "download", "command": [sys.executable, str(scripts / "download_resumable.py"),
                                           MODEL_URL, str(archive)],
             "timeout_seconds": 900, "artifacts": [archive.name], **retry},
            {"id": "extract", "after": ["download"],
             "command": [sys.executable, str(scripts / "extract_model.py"), str(archive), str(model)],
             "timeout_seconds": 120, "artifacts": [f"{MODEL_NAME}/am/final.mdl"], **retry},
            {"id": "verify", "after": ["install", "extract"],
             "command": [*runner, str(scripts / "verify_model.py"), str(model), str(report)],
             "timeout_seconds": 120, "artifacts": [report.name]},
        ],
    }
    path = workdir / "vosk-install.yaml"
    path.write_text(yaml.safe_dump(workflow, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(json.dumps({"workflow": str(path), "workdir": str(workdir), "model_url": MODEL_URL}))


if __name__ == "__main__":
    main()

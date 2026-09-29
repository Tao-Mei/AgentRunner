"""Resolve an executable created by an earlier Workflow step at runtime."""

import subprocess
import sys
from pathlib import Path


python = Path(sys.argv[1])
if not python.is_file():
    raise SystemExit(f"Virtual environment Python is missing: {python}")
raise SystemExit(subprocess.run([str(python), *sys.argv[2:]], check=False).returncode)

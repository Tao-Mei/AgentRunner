import json
import sys
import time
from pathlib import Path


output = Path(sys.argv[1])
print("@@RUNNER " + json.dumps({"event": "stage", "value": "waiting"}), flush=True)
time.sleep(6.5)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("done", encoding="utf-8")
print("@@RUNNER " + json.dumps({"event": "progress", "current": 1, "total": 1, "unit": "file"}), flush=True)
print("observer-finished", flush=True)

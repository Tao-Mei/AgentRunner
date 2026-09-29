"""Load the installed offline speech model and run a silent PCM recognition pass."""

import json
import sys
from pathlib import Path

from vosk import KaldiRecognizer, Model


model_dir = Path(sys.argv[1])
report = Path(sys.argv[2])
model = Model(str(model_dir))
recognizer = KaldiRecognizer(model, 16000)
recognizer.AcceptWaveform(b"\x00\x00" * 16000)
decoded = json.loads(recognizer.FinalResult())
if "text" not in decoded:
    raise RuntimeError("Recognizer did not return a final result")
report.write_text(json.dumps({"model_loaded": True, "sample_rate": 16000,
                              "recognized_text": decoded["text"]}, indent=2), encoding="utf-8")
print(json.dumps({"verified": True, "report": str(report)}))

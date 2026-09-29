"""Create reproducible synthetic questionnaire responses for Runner acceptance."""

import csv
import random
import sys
from pathlib import Path


target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
rng = random.Random(20260929)
with target.open("w", encoding="utf-8", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow([f"item{i}" for i in range(1, 7)])
    for _ in range(400):
        latent = rng.gauss(0, 1)
        writer.writerow([max(1, min(5, round(3 + latent + rng.gauss(0, 0.7)))) for _ in range(6)])

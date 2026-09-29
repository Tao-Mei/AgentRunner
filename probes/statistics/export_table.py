"""Combine R outputs into one auditable CSV artifact."""

import csv
import sys
from pathlib import Path


target = Path(sys.argv[-1])
with target.open("w", encoding="utf-8", newline="") as out:
    writer = csv.writer(out)
    writer.writerow(["metric", "value"])
    for source in sys.argv[1:-1]:
        with Path(source).open(encoding="utf-8", newline="") as stream:
            writer.writerows(list(csv.reader(stream))[1:])

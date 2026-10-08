"""Measure local end-to-end latency, including ingest and validation, excluding process startup."""

import argparse
import json
import math
import platform
import statistics
import time
from pathlib import Path

from change_orders import extract

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--runs", type=int, default=100)
parser.add_argument("--ocr", action="store_true")
args = parser.parse_args()
if args.runs < 2:
    parser.error("--runs must be >=2")
rows = []
for filename in [
    "clean.txt",
    "messy-credit.txt",
    "audit/inline.txt",
    "digital.pdf",
    "audit/two-column.pdf",
] + (["scanned.pdf"] if args.ocr else []):
    mode = "auto" if filename == "scanned.pdf" else "off"
    extract(ROOT / "examples" / filename, ocr=mode)
    timings = []
    for _ in range(args.runs):
        start = time.perf_counter()
        extract(ROOT / "examples" / filename, ocr=mode)
        timings.append((time.perf_counter() - start) * 1000)
    rows.append(
        {
            "file": filename,
            "runs": args.runs,
            "median_ms": round(statistics.median(timings), 3),
            "p95_ms": round(sorted(timings)[math.ceil(0.95 * len(timings)) - 1], 3),
        }
    )
print(
    json.dumps(
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "measurement": "warm process, sequential, local fixtures, no network",
            "p95_method": "nearest rank; small samples have limited tail reliability",
            "results": rows,
        },
        indent=2,
    )
)

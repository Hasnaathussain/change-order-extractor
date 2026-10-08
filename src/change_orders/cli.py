"""JSON on stdout, operational errors on stderr, review signaled by exit code 2."""

import argparse
import os
import sys
import tempfile
from pathlib import Path

from . import extract
from .ingest import InputError
from .llm import ProviderError
from .models import Result


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as f:
            temporary = f.name
            f.write(content)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract change orders into evidence-backed JSON")
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--ocr", choices=("off", "auto", "always"), default="off")
    parser.add_argument("--date-order", choices=("auto", "mdy", "dmy"), default="auto")
    parser.add_argument("--model", help="Opt in to sending document text to an OpenAI model")
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--schema", action="store_true", help="Print JSON Schema and exit")
    args = parser.parse_args(argv)
    if args.schema:
        import json

        print(json.dumps(Result.model_json_schema(), indent=2))
        return 0
    if args.input is None:
        parser.error("input is required unless --schema is used")
    if args.output and args.input.resolve() == args.output.resolve():
        parser.error("output must differ from input")
    try:
        result = extract(
            args.input,
            ocr=args.ocr,
            date_order=args.date_order,
            model=args.model,
            threshold=args.threshold,
        )
        content = result.model_dump_json(indent=2) + "\n"
        if args.output:
            write_atomic(args.output, content)
        else:
            print(content, end="")
        return 2 if result.review_required else 0
    except (InputError, ProviderError, OSError, ValueError, ImportError) as exc:
        print(f"change-orders: {exc}", file=sys.stderr)
        return 1

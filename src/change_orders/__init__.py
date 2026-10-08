"""Evidence-backed change-order extraction."""

from pathlib import Path
from typing import Literal

from .extract import extract_document
from .ingest import read_document
from .models import Result

__all__ = ["Result", "extract"]


def extract(
    path: str | Path,
    *,
    ocr: Literal["off", "auto", "always"] = "off",
    date_order: Literal["auto", "mdy", "dmy"] = "auto",
    model: str | None = None,
    threshold: float = 0.85,
) -> Result:
    document = read_document(Path(path), ocr=ocr)
    candidates = None
    if model:
        from .llm import propose

        candidates = propose(document, model=model).candidates
    return extract_document(
        document, date_order=date_order, model_candidates=candidates, threshold=threshold
    )

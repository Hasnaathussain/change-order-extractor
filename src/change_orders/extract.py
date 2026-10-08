"""Candidate extraction, normalization, conflict resolution and business checks."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from .ingest import Document
from .models import Alternative, Candidate, Evidence, Extracted, Fields, Issue, PageInfo, Result

# Anchored labels prevent 'original contract amount' from becoming 'change amount'.
LABELS = {
    "change_order_number": (
        r"(?:change[ -]?order(?:\s*(?:no\.?|number|#))?"
        r"|CO\s*(?:no\.?|number|#))"
    ),
    "project_name": r"(?:project(?:\s*name)?|job\s*name)",
    "contract_number": r"contract\s*(?:no\.?|number|#)",
    "owner": r"(?:owner|client)",
    "contractor": r"(?:contractor|general\s*contractor)",
    "issue_date": r"(?:issue\s*date|date\s*issued|date)",
    "description": r"(?:description(?:\s*of\s*(?:change|work))?|scope(?:\s*of\s*work)?|reason)",
    "currency": r"currency",
    "change_amount": (
        r"(?:change(?:[ -]?order)?\s*(?:amount|total)"
        r"|net\s*change|total\s*(?:change|amount))"
    ),
    "original_contract_amount": r"original\s*contract\s*(?:amount|sum|price)",
    "prior_changes_amount": (
        r"(?:prior|previous)\s*(?:changes|change\s*orders)"
        r"(?:\s*(?:amount|total))?"
    ),
    "revised_contract_amount": r"(?:revised|new)\s*contract\s*(?:amount|sum|price)",
    "schedule_days": (
        r"(?:schedule\s*(?:change|impact)|time\s*(?:extension|change)"
        r"|additional\s*days)"
    ),
    "status": r"(?:status|approval\s*status)",
}
PATTERNS = {
    field: re.compile(rf"^[ \t]*{label}[ \t]*(?::|=|[ \t]{{2,}}|(?<=#))[ \t]*(.*)$", re.I)
    for field, label in LABELS.items()
}
# Common title form: 'CHANGE ORDER #004' (without a second delimiter).
TITLE = re.compile(r"^\s*(?:change[ -]?order|CO)\s*(?:#|no\.?|number)\s*([\w./-]+)\s*$", re.I)
MONEY_FIELDS = {
    "change_amount",
    "original_contract_amount",
    "prior_changes_amount",
    "revised_contract_amount",
}
CURRENCIES = r"USD|CAD|AUD|EUR|GBP|PKR"
REQUIRED = (
    "change_order_number",
    "project_name",
    "issue_date",
    "description",
    "currency",
    "change_amount",
)


def rule_candidates(document: Document) -> list[Candidate]:
    candidates = []
    for page in document.pages:
        lines = page.text.splitlines()
        for index, line in enumerate(lines):
            title = TITLE.fullmatch(line)
            if title:
                candidates.append(
                    Candidate(
                        field="change_order_number",
                        raw=title[1],
                        page=page.number,
                        quote=line,
                    )
                )
                continue
            for field, pattern in PATTERNS.items():
                match = pattern.fullmatch(line)
                if not match:
                    continue
                raw, quote = match[1].strip(), line
                # Wrapped values and multi-line scope stop at the next recognized label/blank line.
                if not raw or field == "description":
                    continuation = []
                    for next_line in lines[index + 1 :]:
                        if not next_line.strip() or any(
                            p.fullmatch(next_line) for p in PATTERNS.values()
                        ):
                            break
                        if TITLE.fullmatch(next_line):
                            break
                        continuation.append(next_line)
                        if field != "description":
                            break
                    if continuation:
                        quote = "\n".join([line, *continuation])
                        raw = "\n".join(([match[1]] if raw else []) + continuation).strip()
                if raw:
                    candidates.append(
                        Candidate(field=field, raw=raw, page=page.number, quote=quote)
                    )
                break
    # Infer only unambiguous currency markers associated with financial fields.
    for candidate in candidates.copy():
        if candidate.field in MONEY_FIELDS:
            for marker in re.finditer(rf"\b({CURRENCIES})\b|([€£])", candidate.raw, re.I):
                candidates.append(
                    Candidate(
                        field="currency",
                        raw=marker[0],
                        page=candidate.page,
                        quote=candidate.quote,
                    )
                )
    return candidates


def normalize_money(raw: str) -> str:
    text = raw.strip().upper()
    credit = bool(re.search(r"\b(?:CREDIT|DECREASE|DEDUCT)\b", text))
    increase = bool(re.search(r"\b(?:INCREASE|ADD)\b", text))
    if credit and increase:
        raise ValueError("Conflicting credit and increase indicators")
    text = re.sub(r"\b(?:CREDIT|DECREASE|DEDUCT|INCREASE|ADD)\b", "", text).strip()
    text = re.sub(rf"\b(?:{CURRENCIES})\b|[$€£]", "", text).strip()
    if text.startswith("(") and text.endswith(")"):
        credit = True
        text = text[1:-1].strip()
    # Only US/UK decimal notation. Do not silently reinterpret European separators.
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?", text):
        raise ValueError("Unsupported or ambiguous money format")
    amount = Decimal(text.replace(",", ""))
    if increase and amount < 0:
        raise ValueError("Negative amount contradicts increase indicator")
    if credit:
        amount = -abs(amount)
    if amount == 0:
        amount = Decimal(0)
    return f"{amount:.2f}"


def normalize_date(raw: str, date_order: Literal["auto", "mdy", "dmy"]) -> str:
    raw = raw.strip()
    if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}", raw):
        first, second, year = map(int, re.split(r"[/.-]", raw))
        if date_order == "auto":
            if first <= 12 and second <= 12 and first != second:
                raise ValueError("Ambiguous numeric date; specify --date-order mdy or dmy")
            order = "dmy" if first > 12 else "mdy"
        else:
            order = date_order
        month, day = (first, second) if order == "mdy" else (second, first)
        return datetime(year, month, day).date().isoformat()
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Unsupported or invalid date")


def normalize(field: str, raw: str, date_order: Literal["auto", "mdy", "dmy"]):
    if field in MONEY_FIELDS:
        return normalize_money(raw)
    if field == "issue_date":
        return normalize_date(raw, date_order)
    if field == "currency":
        currency = {"€": "EUR", "£": "GBP"}.get(raw, raw.upper())
        if currency not in CURRENCIES.split("|"):
            raise ValueError("Currency must be explicit; '$' alone is ambiguous")
        return currency
    if field == "schedule_days":
        match = re.fullmatch(r"([+-]?\d+)\s*(?:calendar\s*)?(?:days?)?", raw.strip(), re.I)
        if not match:
            raise ValueError("Schedule must be an explicit integer number of calendar days")
        return int(match[1])
    if field == "status":
        status = raw.strip().lower()
        if status not in {"proposed", "approved", "rejected", "pending"}:
            raise ValueError("Unrecognized approval status")
        return status
    value = re.sub(r"\s+", " ", raw).strip()
    if field in {"change_order_number", "contract_number"}:
        value = value.lstrip("#").strip()
        if not re.fullmatch(r"[\w./-]{1,80}", value):
            raise ValueError("Invalid identifier")
    if not value:
        raise ValueError("Empty value")
    return value


def extract_document(
    document: Document,
    *,
    date_order: Literal["auto", "mdy", "dmy"] = "auto",
    model_candidates: list[Candidate] | None = None,
    threshold: float = 0.85,
) -> Result:
    if date_order not in {"auto", "mdy", "dmy"} or not 0 <= threshold <= 1:
        raise ValueError("Invalid date order or review threshold")
    issues = list(document.issues)
    grouped: dict[str, dict[object, list[Evidence]]] = {field: {} for field in Fields.model_fields}
    invalid: set[str] = set()
    pages = {page.number: page for page in document.pages}
    candidates = [(c, "rules") for c in rule_candidates(document)]
    candidates.extend((c, "llm") for c in (model_candidates or []))
    for candidate, method in candidates:
        page = pages.get(candidate.page)
        if page is None or candidate.quote not in page.text or candidate.raw not in candidate.quote:
            invalid.add(candidate.field)
            issues.append(
                Issue(
                    code="ungrounded_candidate",
                    field=candidate.field,
                    message="Candidate has no exact supporting source span",
                )
            )
            continue
        start = page.text.index(candidate.quote)
        evidence = Evidence(
            page=page.number,
            start=start,
            end=start + len(candidate.quote),
            quote=candidate.quote,
            method=method,
            source=page.source,
        )
        try:
            value = normalize(candidate.field, candidate.raw, date_order)
        except ValueError as exc:
            invalid.add(candidate.field)
            issues.append(Issue(code="invalid_value", field=candidate.field, message=str(exc)))
            continue
        bucket = grouped[candidate.field].setdefault(value, [])
        if evidence not in bucket:
            bucket.append(evidence)
    output = {}
    for field, values in grouped.items():
        if len(values) > 1:
            output[field] = Extracted(
                state="conflict",
                alternatives=[
                    Alternative(value=value, evidence=evidence)
                    for value, evidence in values.items()
                ],
            )
            issues.append(
                Issue(
                    code="conflicting_values",
                    field=field,
                    message="Multiple distinct values; human review required",
                )
            )
        elif values:
            value, evidence = next(iter(values.items()))
            # Scores express extraction quality, not calibrated probabilities.
            score = max(
                0.70 if e.source == "ocr" else 0.80 if e.method == "llm" else 0.95 for e in evidence
            )
            if field in invalid:
                score = min(score, 0.60)
            output[field] = Extracted(
                value=value, confidence=score, state="extracted", evidence=evidence
            )
        else:
            output[field] = Extracted(state="invalid" if field in invalid else "missing")
    fields = Fields.model_validate({key: value.model_dump() for key, value in output.items()})
    # Do not invent missing prior changes or fill a revised sum from arithmetic.
    amounts = [
        getattr(fields, f).value
        for f in (
            "original_contract_amount",
            "prior_changes_amount",
            "change_amount",
            "revised_contract_amount",
        )
    ]
    if all(value is not None for value in amounts):
        original, prior, change, revised = map(Decimal, amounts)
        if original + prior + change != revised:
            issues.append(
                Issue(
                    code="contract_total_mismatch",
                    field="revised_contract_amount",
                    message="Original + prior changes + this change != revised contract",
                )
            )
    for field in REQUIRED:
        extracted = getattr(fields, field)
        if extracted.value is None:
            issues.append(
                Issue(
                    code="required_field_unresolved",
                    field=field,
                    message="Required field needs human review",
                )
            )
        elif extracted.confidence < threshold:
            issues.append(
                Issue(
                    code="low_confidence",
                    field=field,
                    message="Confidence is below the configured review threshold",
                )
            )
    overall = min(getattr(fields, field).confidence for field in REQUIRED)
    return Result(
        source_sha256=document.sha256,
        pages=[
            PageInfo(page=p.number, source=p.source, characters=len(p.text)) for p in document.pages
        ],
        fields=fields,
        issues=issues,
        review_required=bool(issues),
        overall_confidence=overall,
    )

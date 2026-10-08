"""Candidate extraction, normalization, conflict resolution and business checks."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from .ingest import Document
from .models import Alternative, Candidate, Evidence, Extracted, Fields, Issue, PageInfo, Result
from .rules import CURRENCIES, MONEY_FIELDS, rule_candidates

REQUIRED = (
    "change_order_number",
    "project_name",
    "issue_date",
    "description",
    "currency",
    "change_amount",
)


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
    if increase and credit:
        raise ValueError("Parenthesized credit contradicts increase indicator")
    # Only US/UK decimal notation. Do not silently reinterpret European separators.
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?", text):
        raise ValueError("Unsupported or ambiguous money format")
    amount = Decimal(text.replace(",", ""))
    if abs(amount) >= Decimal("1e18"):
        raise ValueError("Money is limited to 18 integer digits")
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


def normalize(field: str, raw: str, date_order: Literal["auto", "mdy", "dmy"], quote: str = ""):
    context = quote.upper()
    if field in MONEY_FIELDS:
        amount = normalize_money(raw)
        # A model can omit direction from its raw substring. Check the immediate context.
        start = quote.find(raw)
        if start >= 0:
            prefix = context[max(0, start - 180) : start]
            suffix = context[start + len(raw) :]
            if field == "change_amount" and re.search(
                r"\b(?:ORIGINAL|REVISED|NEW)\s+CONTRACT\s+(?:AMOUNT|SUM|PRICE)",
                prefix,
            ):
                raise ValueError("Change amount candidate cites a different contract total")
            negative = re.search(
                rf"(?:CREDIT(?: OF)?|DECREASED?(?: BY)?|DEDUCT(?:ION)?(?: OF)?|-)"
                rf"\s*(?:BY THIS CHANGE ORDER\s*)?(?:IN THE AMOUNT OF\s*)?"
                rf"(?:(?:{CURRENCIES})|[$€£])?\s*$",
                prefix,
            ) or re.match(r"\s*(?:CREDIT|DECREASE)\b", suffix)
            parenthesized = re.search(
                rf"\(\s*(?:(?:{CURRENCIES})|[$€£])?\s*" + re.escape(raw.upper()) + r"\s*\)", context
            )
            if negative or parenthesized:
                amount = f"{-abs(Decimal(amount)):.2f}" if Decimal(amount) else "0.00"
            positive = re.search(
                r"(?:INCREASED? BY|ADD)\s*"
                rf"(?:THIS CHANGE ORDER\s*)?(?:IN THE AMOUNT OF\s*)?"
                rf"(?:\(\s*)?(?:(?:{CURRENCIES})|[$€£])?\s*$",
                prefix,
            )
            if positive and Decimal(amount) < 0:
                raise ValueError("Negative amount contradicts source increase indicator")
        return amount
    if field == "issue_date":
        return normalize_date(raw, date_order)
    if field == "currency":
        currency = {"€": "EUR", "£": "GBP"}.get(raw, raw.upper())
        if currency not in CURRENCIES.split("|"):
            raise ValueError("Currency must be explicit; '$' alone is ambiguous")
        return currency
    if field == "schedule_days":
        words = dict(
            zip(
                (
                    "zero",
                    "one",
                    "two",
                    "three",
                    "four",
                    "five",
                    "six",
                    "seven",
                    "eight",
                    "nine",
                    "ten",
                ),
                range(11),
                strict=True,
            )
        )
        raw = re.sub(r"^[A-Za-z]+", lambda m: str(words.get(m[0].lower(), m[0])), raw.strip())
        match = re.fullmatch(r"([+-]?\d+)\s*(?:calendar\s*)?(?:days?)?", raw.strip(), re.I)
        if not match:
            raise ValueError("Schedule must be an explicit integer number of calendar days")
        days = int(match[1])
        if re.search(r"\bDECREASED BY\s+", context):
            days = -abs(days)
        return days
    if field == "status":
        status = raw.strip().lower()
        if status == "proposal":
            status = "proposed"
        if status == "approved" and re.search(
            r"\b(?:NOT(?: YET)?(?: BEEN)? APPROVED|APPROVAL (?:HAS )?NOT)\b", context
        ):
            raise ValueError("Approval candidate contradicts a source negation")
        if status == "approved" and re.search(r"\bAPPROVED\s+BY\s*:", context):
            raise ValueError("Approval cannot be established by a signature label alone")
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


def validate_options(date_order: str, threshold: float) -> None:
    if date_order not in {"auto", "mdy", "dmy"} or not 0 <= threshold <= 1:
        raise ValueError("Invalid date order or review threshold")


def extract_document(
    document: Document,
    *,
    date_order: Literal["auto", "mdy", "dmy"] = "auto",
    model_candidates: list[Candidate] | None = None,
    threshold: float = 0.85,
) -> Result:
    validate_options(date_order, threshold)
    issues = list(document.issues)
    grouped: dict[str, dict[object, list[Evidence]]] = {field: {} for field in Fields.model_fields}
    invalid: set[str] = set()
    pages = {page.number: page for page in document.pages}
    candidates = rule_candidates(document)
    rejected_evidence = {field: [] for field in Fields.model_fields}
    candidates.extend((c, "llm", None) for c in (model_candidates or []))
    for candidate, method, offset in candidates:
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
        start = page.text.index(candidate.quote) if offset is None else offset
        evidence = Evidence(
            page=page.number,
            start=start,
            end=start + len(candidate.quote),
            quote=candidate.quote,
            method=method,
            source=page.source,
        )
        try:
            value = normalize(candidate.field, candidate.raw, date_order, candidate.quote)
        except ValueError as exc:
            invalid.add(candidate.field)
            rejected_evidence[candidate.field].append(evidence)
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
                0.70 if e.source == "ocr" else 0.80 if e.method in {"llm", "context"} else 0.95
                for e in evidence
            )
            if field in invalid:
                score = min(score, 0.60)
            output[field] = Extracted(
                value=value, confidence=score, state="extracted", evidence=evidence
            )
        else:
            output[field] = Extracted(
                state="invalid" if field in invalid else "missing",
                evidence=rejected_evidence[field],
            )
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
    for field in Fields.model_fields:
        extracted = getattr(fields, field)
        if field in REQUIRED and extracted.value is None:
            issues.append(
                Issue(
                    code="required_field_unresolved",
                    field=field,
                    message="Required field needs human review",
                )
            )
        elif extracted.value is not None and extracted.confidence < threshold:
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

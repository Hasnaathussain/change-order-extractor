"""Explicit labels and bounded contextual phrases; no statistical or template inference."""

import re

from .ingest import Document
from .models import Candidate

CURRENCIES = r"USD|CAD|AUD|EUR|GBP|PKR"
MONEY_FIELDS = {
    "change_amount",
    "original_contract_amount",
    "prior_changes_amount",
    "revised_contract_amount",
}
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
        r"(?:change(?:[ -]?order)?\s*(?:amount|total)|net\s*change"
        r"|total\s*(?:change|amount))"
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
LABEL_TOKEN = re.compile(
    r"(?:^|[|;\t]| {2,})[ \t]*(?:"
    + "|".join(rf"(?P<{field}>{label})" for field, label in LABELS.items())
    + r")[ \t]*(?::|=|\||(?<=#)|[ \t]{2,}|$)[ \t]*",
    re.I,
)
TITLE = re.compile(r"^\s*(?:change[ -]?order|CO)\s*(?:#|no\.?|number)\s*([\w./-]+)\s*$", re.I)
FORM_START = re.compile(
    r"^\s*(?:The\s+)?(?:original\s+Contract\s+Sum|net\s+change\s+by\s+previously|new\s+Contract\s+Sum|Contract\s+(?:Sum|Time)\s+will)",
    re.I,
)
UNKNOWN_LABEL = re.compile(r"^\s*[A-Za-z][A-Za-z /-]{1,50}:\s*")
AMOUNT = (
    rf"(?:\(\s*)?[+-]?\s*(?:(?:{CURRENCIES})\s*|[$€£]\s*)?"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?(?!\d|[.,]\d)(?:\s*\))?"
)
DATE = r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|[A-Za-z]+\s+\d{1,2},\s+\d{4})"
NUMBER = r"(?:[+-]?\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)"

# These phrases are deliberately narrow. Unfamiliar prose is left for the optional model.
CONTEXT = {
    "change_order_number": r"\bchange[ -]order\s+(?P<raw>(?:CO-)?\d[\w./-]*)\b",
    "project_name": r"\bfor\s+the\s+(?P<raw>[^.;:]{1,200}?)\s+under\s+contract\b",
    "contract_number": r"\bunder\s+contract\s+(?P<raw>[\w/-]+(?:\.[\w/-]+)*)",
    "issue_date": rf"\bissued\s+on\s+(?P<raw>{DATE})",
    "description": r"\b(?:this\s+request\s+covers|scope\s+includes)\s+(?P<raw>[^.!?]{1,2000})",
    "contractor": r"(?P<raw>[A-Z][A-Za-z &'-]{1,150})\s+will\s+carry\s+out\s+the\s+work\s+for\b",
    "owner": r"\bwill\s+carry\s+out\s+the\s+work\s+for\s+(?P<raw>[^.!?\n]{1,150})",
    "change_amount": (
        rf"\b(?:proposed|net)\s+(?:adjustment|change)\s+is\s+"
        rf"(?:a\s+credit\s+of\s+)?(?P<raw>{AMOUNT})"
        rf"|\b(?:The\s+)?Contract\s+Sum\s+will\s+be\s+"
        rf"(?:increased|decreased)\s+by\s+this\s+Change\s+Order\s+"
        rf"(?:in\s+the\s+amount\s+of\s+)?(?P<form>{AMOUNT})"
    ),
    "original_contract_amount": (
        rf"\b(?:The\s+)?original\s+Contract\s+Sum\s+was\s+(?P<raw>{AMOUNT})"
    ),
    "prior_changes_amount": (
        rf"\b(?:The\s+)?net\s+change\s+by\s+previously\s+authorized\s+"
        rf"Change\s+Orders\s+(?:was\s+)?(?P<raw>{AMOUNT})"
    ),
    "revised_contract_amount": (
        rf"\b(?:The\s+)?new\s+Contract\s+Sum\s+including\s+this\s+"
        rf"Change\s+Order\s+will\s+be\s+(?P<raw>{AMOUNT})"
    ),
    "schedule_days": (
        rf"\bwith\s+(?P<raw>{NUMBER})\s+additional\s+calendar\s+days\b"
        rf"|\bContract\s+Time\s+will\s+be\s+(?:increased|decreased)\s+by\s+"
        rf"(?P<form>{NUMBER}(?:\s+calendar)?\s+days)\b"
    ),
    "status": r"\bthis\s+is\s+a\s+(?P<raw>proposal)\b",
}
CONTEXT_PATTERNS = {f: re.compile(p, re.I) for f, p in CONTEXT.items()}


def rule_candidates(document: Document) -> list[tuple[Candidate, str, int]]:
    proposals = []
    for page in document.pages:
        pieces = page.text.splitlines(keepends=True)
        lines = [piece.rstrip("\r\n") for piece in pieces]
        offset = 0
        for index, line in enumerate(lines):
            line_start = offset
            offset += len(pieces[index])
            title = TITLE.fullmatch(line)
            if title:
                proposals.append(
                    (
                        Candidate(
                            field="change_order_number", raw=title[1], page=page.number, quote=line
                        ),
                        "rules",
                        page.text.find(line, line_start),
                    )
                )
                continue
            tokens = list(LABEL_TOKEN.finditer(line))
            for position, token in enumerate(tokens):
                field = token.lastgroup
                end = tokens[position + 1].start() if position + 1 < len(tokens) else len(line)
                quote = line[token.start() : end].lstrip(" |;\t")
                raw = line[token.end() : end].strip(" |;\t")
                if (not raw or field == "description") and position == len(tokens) - 1:
                    continuation = []
                    for next_line in lines[index + 1 :]:
                        if (
                            not next_line.strip()
                            or LABEL_TOKEN.search(next_line)
                            or TITLE.fullmatch(next_line)
                            or UNKNOWN_LABEL.match(next_line)
                            or FORM_START.match(next_line)
                        ):
                            break
                        continuation.append(next_line)
                        if field != "description":
                            break
                    if continuation:
                        quote = "\n".join([quote, *continuation])
                        raw = "\n".join(
                            ([line[token.end() : end]] if raw else []) + continuation
                        ).strip()
                if raw:
                    # A generic 'Date' may be a signature date; it requires review.
                    method = (
                        "context"
                        if field == "issue_date" and token[field].lower() == "date"
                        else "rules"
                    )
                    proposals.append(
                        (
                            Candidate(field=field, raw=raw, page=page.number, quote=quote),
                            method,
                            page.text.find(quote, line_start),
                        )
                    )
        for field, pattern in CONTEXT_PATTERNS.items():
            for match in pattern.finditer(page.text):
                raw = match.groupdict().get("raw") or match.groupdict().get("form")
                proposals.append(
                    (
                        Candidate(field=field, raw=raw.strip(), page=page.number, quote=match[0]),
                        "context",
                        match.start(),
                    )
                )
    # Currency markers must be associated with a financial value.
    for candidate, method, start in proposals.copy():
        if candidate.field in MONEY_FIELDS:
            for marker in re.finditer(rf"\b({CURRENCIES})\b|([€£])", candidate.raw, re.I):
                proposals.append(
                    (
                        Candidate(
                            field="currency",
                            raw=marker[0],
                            page=candidate.page,
                            quote=candidate.quote,
                        ),
                        method,
                        start,
                    )
                )
    return proposals

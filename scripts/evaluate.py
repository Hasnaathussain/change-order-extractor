"""Exact-value evaluation of a small synthetic regression corpus, with abstention counted."""

import json
from pathlib import Path

from change_orders import extract

ROOT = Path(__file__).resolve().parents[1]


def main():
    corpus = json.loads((ROOT / "examples/expected.json").read_text())
    correct = total = resolved = resolved_correct = review_correct = abstentions = 0
    failures = []
    for case in corpus:
        result = extract(ROOT / "examples" / case["file"])
        review_correct += result.review_required == case["review_required"]
        for field, expected in case["fields"].items():
            actual = getattr(result.fields, field).value
            total += 1
            correct += actual == expected
            if actual is not None:
                resolved += 1
                resolved_correct += actual == expected
            if actual is None and expected is not None:
                abstentions += 1
            if actual != expected and not (actual is None and case.get("allow_abstention")):
                failures.append(
                    {"file": case["file"], "field": field, "expected": expected, "actual": actual}
                )
    report = {
        "corpus": "synthetic-v1",
        "documents": len(corpus),
        "asserted_fields": total,
        "exact_matches": correct,
        "exact_match_rate": correct / total,
        "resolved_asserted_fields": resolved,
        "abstentions_on_known_values": abstentions,
        "precision_on_resolved_fields": resolved_correct / resolved if resolved else None,
        "correct_review_decisions": review_correct,
        "failures": failures,
        "limitation": "Regression results only; not evidence of accuracy on real documents.",
    }
    print(json.dumps(report, indent=2))
    return int(bool(failures) or review_correct != len(corpus))


if __name__ == "__main__":
    raise SystemExit(main())

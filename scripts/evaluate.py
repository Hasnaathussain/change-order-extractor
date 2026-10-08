"""Synthetic regression evaluation with known values, abstention and review kept separate."""

import json
from pathlib import Path

from change_orders import extract

ROOT = Path(__file__).resolve().parents[1]


def main():
    corpus = json.loads((ROOT / "examples/expected.json").read_text())
    known = correct_known = resolved = correct_resolved = abstained = 0
    expected_null = correct_null = review_correct = 0
    failures = []
    for case in corpus:
        result = extract(ROOT / "examples" / case["file"])
        review_correct += result.review_required == case["review_required"]
        for field, expected in case["fields"].items():
            actual = getattr(result.fields, field).value
            if expected is None:
                expected_null += 1
                correct_null += actual is None
            else:
                known += 1
                correct_known += actual == expected
                abstained += actual is None
            if actual is not None:
                resolved += 1
                correct_resolved += actual == expected
            if actual != expected:
                failures.append(
                    {"file": case["file"], "field": field, "expected": expected, "actual": actual}
                )
        for field, state in case.get("states", {}).items():
            actual = getattr(result.fields, field).state
            if actual != state:
                failures.append(
                    {
                        "file": case["file"],
                        "field": field,
                        "expected_state": state,
                        "actual_state": actual,
                    }
                )
        codes = {issue.code for issue in result.issues}
        for code in case.get("issue_codes", []):
            if code not in codes:
                failures.append({"file": case["file"], "missing_issue": code})
    report = {
        "corpus": "synthetic-v2",
        "documents": len(corpus),
        "known_values": known,
        "correct_known_values": correct_known,
        "recall_on_known_values": correct_known / known,
        "resolved_asserted_fields": resolved,
        "precision_on_resolved_fields": correct_resolved / resolved if resolved else None,
        "abstentions_on_known_values": abstained,
        "expected_unresolved_fields": expected_null,
        "correct_unresolved_fields": correct_null,
        "correct_review_decisions": review_correct,
        "failures": failures,
        "limitation": "Development regression fixtures, not held-out or real-document accuracy.",
    }
    print(json.dumps(report, indent=2))
    return int(bool(failures) or review_correct != len(corpus))


if __name__ == "__main__":
    raise SystemExit(main())

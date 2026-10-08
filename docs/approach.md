# Approach and failure modes

The pipeline reads PDF text or UTF-8 text and optionally OCRs scanned pages. Local extraction handles labels, inline and pipe fields, stacked forms, common contract-summary wording and bounded narrative phrases. An optional strict-schema model handles unfamiliar prose. Both paths produce raw candidates with exact source quotes, then use the same normalization and validation code.

Money uses Decimal-backed strings; credits and schedule reductions stay negative. Dates are checked for calendar validity and ambiguity. Currency must be explicit. Conflicting values remain unresolved with their alternatives. Contract arithmetic is checked without correcting the document or inventing totals. The output model enforces field types, state consistency and source-span bounds.

Confidence is a documented heuristic: explicit labels score 0.95, contextual/model-only values 0.80, and fresh OCR 0.70. Invalid competing evidence caps a resolved field at 0.60. The default 0.85 review threshold applies to every resolved field, including optional fields. Scores are not calibrated probabilities.

| Failure mode | Behavior and limitation |
| --- | --- |
| OCR digit errors | OCR results require review; a valid-looking wrong digit may escape validation. Pre-existing OCR text layers cannot be reliably identified. |
| Ambiguous dates or conflicting revisions | Keep the field unresolved; retain evidence and alternatives. |
| Missing currency or totals | Keep null; do not infer USD from `$` or compute an absent total. |
| Complex layouts or unfamiliar prose | Local extraction may miss or misassociate values. The optional model improves coverage but still requires review. |
| Model cites the wrong field | Source checks reject some explicit credit, total-label and approval contradictions; exact quotes do not prove every semantic association. |
| Handwriting, signatures or multiple orders | Outside the supported scope. One change order per input. |

The local path avoids API latency and costs. The model path makes one bounded request and fails explicitly on refusal, truncation, timeout or invalid output. File, page, text, OCR-pixel and response-size limits bound routine work; production uploads still need isolated workers.

Verification includes 94 tests, real OCR, a two-column/two-page PDF, and a 14-document synthetic corpus with 128 known values and five expected unresolved fields. Evaluation separates precision, recall, abstention and review decisions. Benchmarks include ingestion and validation in a warm process. These are development fixtures, not held-out accuracy or production throughput evidence. Provider transport is mocked; live model accuracy remains unmeasured.

The next step is a permissioned, annotated corpus split by vendor/template to measure real coverage, review burden and confidence calibration.

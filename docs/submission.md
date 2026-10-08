# Submission writeup

I built a Python pipeline that extracts change-order fields from PDFs and UTF-8 text into a versioned JSON contract. The repository includes a CLI, Python API, scanned-PDF OCR, optional structured model extraction, source evidence, confidence scores, tests, CI and reproducible evaluation/benchmark scripts.

The local path handles labeled lines, inline and pipe fields, stacked forms, common contract-summary wording and bounded narrative phrases. An optional strict-schema model handles unfamiliar prose. Both paths share source verification, Decimal-backed money normalization, date validation, conflict resolution and contract arithmetic checks. Credits stay negative, and missing or ambiguous values stay unresolved. Source context also rejects obvious total substitutions and negated or signature-only approval claims.

Confidence is a documented heuristic based on evidence quality, not a model's self-reported certainty. Contextual, OCR and model-only values require review by default, including optional fields. Main failure modes are OCR digit errors, arbitrary PDF reading order and semantically wrong source associations. Evidence is preserved so a reviewer can inspect the document.

The synthetic development corpus covers 14 documents, 128 known values and five expected unresolved fields. Tests include real OCR and a two-column/two-page PDF. Performance is measured locally with reproducible scripts; these small fixtures do not establish production throughput or real-world accuracy. Provider transport is tested with mocks, but live model accuracy is not claimed. The next step is a permissioned, annotated corpus split by vendor/template to measure coverage, precision, review burden and confidence calibration.

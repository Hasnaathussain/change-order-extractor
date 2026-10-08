# Submission writeup

I built a Python pipeline that extracts change-order fields from native PDFs, scanned PDFs and UTF-8 text into a versioned JSON contract. Each resolved value includes a confidence score and source evidence. The repository includes a CLI, Python API, synthetic fixtures, example output, JSON Schema, tests, CI and reproducible evaluation/benchmark scripts.

The default path uses local label extraction, with page-level OCR when requested. An optional structured-output model handles prose and unfamiliar labels. Both paths share evidence verification, normalization and validation. Amounts use Decimal-backed strings; credits stay negative. Ambiguous dates, missing currency and competing values remain unresolved. Contract arithmetic is checked without rewriting source values or inventing missing totals.

Confidence is an explicit heuristic based on evidence quality, not a model's self-reported certainty. OCR and model-only values require review by default. Failure modes include misread OCR digits, multi-column reading order, conflicting revisions and a model attaching a real quote to the wrong field. The implementation exposes these limits and keeps evidence available for review.

Local median timings were approximately 1 ms for text, 5.5 ms for a native PDF and 2.7 seconds for the scanned fixture. These are small synthetic examples, not production throughput claims. Evaluation reports narrative abstentions as missed values; live model accuracy has not been measured. The next step is a permissioned corpus split by vendor/template to measure coverage, precision, review burden and confidence calibration.

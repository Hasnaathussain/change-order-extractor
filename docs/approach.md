# Approach and failure modes

The pipeline separates ingestion, candidate extraction and validation. PDF text is read first; optional OCR operates page by page. Local extraction covers explicit labels, inline fields, pipe tables, stacked labels, common contract-summary wording and a bounded set of narrative phrases. An optional strict-schema model proposes candidates for unfamiliar prose. Every resolved value carries its page, exact quote, offsets and extraction method.

Normalization is conservative. Money is parsed through Decimal and serialized as strings; credits and schedule reductions stay negative. Immediate quote context catches direction omitted from a model's raw value. Amounts are limited to 18 integer digits to preserve exact contract arithmetic. Dates become ISO dates after checking calendar validity and ambiguity; the public output model also rejects impossible dates. A dollar sign alone does not establish currency. Approval must be stated; negations and signature labels do not establish approval.

Missing values remain null. Distinct normalized candidates become a conflict regardless of the extractor. Rejected, grounded values keep their source evidence for review. Pydantic enforces types, extra-field rejection, field-state invariants and page-span bounds. Business validation checks original contract plus prior changes plus this change against the revised contract when all four values are present, without correcting source values or inventing totals.

Confidence is a versioned evidence policy rather than a model's self-assessment. Explicit labels score 0.95; contextual phrases and model-only values score 0.80; OCR values score 0.70. Invalid competing evidence caps a resolved field at 0.60. Missing, invalid and conflicting fields score zero. Every resolved field below the default 0.85 threshold requires review, including optional fields. Overall confidence summarizes the six required fields; validation issues independently control review.

The local path avoids network latency and token costs. Parsing and OCR have file/page/text/pixel bounds, with a Tesseract timeout. The model path uses one request, finite HTTP timeouts, a bounded streamed response, and explicit failure on refusal, truncation or invalid output. Examples, regression evaluation, tests and benchmark scripts make the choices inspectable.

## Failure modes

| Failure | Behavior / remaining limitation |
| --- | --- |
| Sparse or scanned page | Optional OCR; its evidence requires review. Auto detection can miss image bodies beneath long text headers. |
| OCR digit becomes another valid digit | Shape validation cannot catch every substitution. A reviewer must compare the page. Pre-existing OCR text layers may be indistinguishable from native text. |
| Conflicting amount or revision | Abstain and retain alternatives. No automatic latest-revision selection. |
| Ambiguous numeric date | Abstain unless the caller supplies the date convention. A generic Date label has lower confidence because it might refer to a signature. |
| Missing currency or total | Keep null; never infer USD or calculate an absent total. |
| Unfamiliar prose or complex tables | Local patterns may abstain or misassociate text. Optional model coverage helps but is not an accuracy guarantee. |
| Model cites a real quote for the wrong field | Explicit credit, total-label and approval checks reject some errors. Exact source presence is still weaker than correct interpretation, so model-only values require review. |
| Prompt injection in the document | The document is an untrusted data message and no tools are available. This limits impact without proving model immunity. |
| Multiple orders in one input | Unsupported. Conflicting shared fields often flag review, but document splitting is an upstream responsibility. |
| Handwriting, signatures, business days, European amounts | Unsupported or rejected; do not silently reinterpret them. |
| Hostile or pathological PDF | Input bounds are not process isolation. Use constrained workers before accepting arbitrary public uploads. |

## Evaluation and next step

The 14-document corpus is synthetic development data. It checks 128 known field values, five intended unresolved fields and all review decisions, with recall, precision and abstention reported separately. Tests include multi-column and multi-page PDF ingestion, real OCR, source grounding, state invariants, credits, provider failures and CLI semantics. Provider calls are mocked; live model quality has not been evaluated.

Benchmarks include ingestion and validation in a warm process; OCR is measured separately. Percentiles use nearest rank, and the five-run OCR sample has limited tail reliability. These fixtures do not establish real-world accuracy, confidence calibration or production throughput.

With a representative, permissioned set of real change orders, annotate values and evidence, split by vendor/template, and evaluate precision, recall, abstention and review burden separately for text layers, fresh OCR and model output. Calibrate thresholds on held-out documents. Add layout-aware line items or background workers only when coverage and measured throughput justify them.

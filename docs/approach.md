# Approach and failure modes

The pipeline keeps ingestion, candidate extraction and validation separate. Native PDF text is read first; optional OCR operates page by page. Anchored label rules cover common change-order forms without a model call. An optional strict-schema model proposes candidates for unfamiliar layouts and prose. Every resolved value carries its page, exact quote, offsets and extraction method.

Normalization is intentionally conservative. Money is parsed through `Decimal` and serialized as strings; credits are negative. Dates become ISO dates only after checking validity and ambiguity. A dollar sign alone does not establish currency. Approval is taken from an explicit status, never an empty signature line. Missing values remain null. Distinct normalized candidates become a conflict, regardless of which extractor produced them.

Pydantic enforces the output contract and rejects extra fields. Business validation checks original contract plus prior changes plus this change against the revised contract, when all four values are present. A mismatch is reported without correcting the document or inventing missing amounts. Confidence comes from a small, documented evidence policy rather than a model's self-assessment. OCR and model-only values are below the default acceptance threshold.

The local path avoids network latency and token costs. PDF parsing and OCR are bounded by file/page/text/pixel limits, with a Tesseract timeout. The optional model path makes one request and fails explicitly on refusal, truncation or invalid output. Reproducible examples, regression evaluation, tests and a benchmark script make these choices inspectable.

## Failure modes

| Failure | Behavior / remaining limitation |
| --- | --- |
| Sparse or scanned page | OCR can be enabled; OCR evidence is routed to review. Auto detection can miss image bodies beneath long text headers. |
| OCR misreads a digit into another valid digit | Schema validation cannot detect every substitution. The score remains capped; a reviewer must compare the page. |
| Conflicting amount or revision | Abstain and retain alternatives. No automatic latest-revision selection. |
| Ambiguous numeric date | Abstain unless the caller supplies the date convention. |
| Missing currency or total | Keep null; never infer USD or calculate an absent total. |
| Multi-column tables / unusual labels | Rules may miss or misassociate values. Optional model coverage helps, but is not an accuracy guarantee. |
| Model cites a real quote for the wrong field | Exact evidence matching does not establish meaning. Model-only output is reviewed; this risk needs evaluation on real documents. |
| Prompt injection embedded in text | Document stays in an untrusted user-data message; no tools are available. This reduces impact, but does not prove model immunity. |
| Multiple orders in one document | Unsupported: conflicting shared fields commonly flag review, but splitting must happen upstream. |
| Handwriting, signatures, business days, European amounts | Unsupported or rejected; do not silently reinterpret them. |
| Malicious or pathological PDF | Practical input bounds are not process isolation. Deploy in constrained workers before accepting arbitrary public uploads. |

## Evaluation and next step

The checked-in corpus is deliberately small and synthetic. Tests cover arithmetic, evidence grounding, credits, ambiguity, PDF ingestion, real OCR, provider failures and CLI semantics. Regression metrics count abstentions against expected values and expose the narrative parser's omissions. Local benchmarks include ingestion and validation; OCR is measured separately. Neither these fixtures nor mocked provider calls establish production accuracy.

With a representative, permissioned set of real change orders, the next step is to annotate field values and evidence, split by vendor/template, and report precision, recall, abstention rate and review burden separately for native PDFs, OCR and model output. Confidence thresholds should then be calibrated on held-out documents. Add layout-aware line items or a background queue only if document coverage and measured throughput justify them.

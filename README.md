# Change-order extractor

Extract construction change orders from PDF or UTF-8 text into validated JSON. Each resolved field includes a confidence score and an exact source quote. Ambiguous dates, conflicting values and inconsistent contract totals are routed to review.

The default path runs locally without an API key. It handles labeled lines, same-line fields, pipe tables, stacked labels, common contract-summary phrases and a bounded set of narrative phrases. An optional structured-output model handles unfamiliar prose and labels. Both paths share normalization, evidence checks and validation.

## Run it

Python 3.11 or later:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,ocr,llm]'
change-orders examples/clean.txt -o result.json
change-orders examples/digital.pdf
```

For scanned PDFs, install Tesseract with English language data, then:

```bash
# Ubuntu / Debian
sudo apt-get install tesseract-ocr tesseract-ocr-eng
change-orders examples/scanned.pdf --ocr auto -o scanned.json
```

Exit codes: **0** = no review flags; **2** = valid JSON that needs review; **1** = ingestion/provider failure. A review result still writes its JSON. Output files are replaced atomically. The CLI refuses to overwrite its input.

Try the deliberate failures:

```bash
change-orders examples/conflict.txt       # exit 2; conflicting amounts and ambiguous date
change-orders examples/messy-credit.txt   # wrapped fields, mixed case, negative credit
change-orders examples/audit/inline.txt   # same-line fields
change-orders examples/audit/pipe-table.txt
change-orders examples/audit/stacked-form.txt  # form wording, credit, schedule reduction
change-orders examples/audit/two-column.pdf   # two-column, two-page PDF
change-orders examples/narrative.txt      # local contextual extraction; exit 2
change-orders examples/conflict.txt --date-order mdy
change-orders --schema > schema.json
```

`auto` date handling accepts ISO dates and unambiguous numeric dates. Set `--date-order mdy` or `dmy` when the document's convention is known. Currency is never inferred from `$` alone. Amounts use decimal strings, preserving cents and avoiding binary floating-point arithmetic. Values are limited to 18 integer digits, so contract arithmetic stays within the Decimal precision budget.

## Output

Excerpt from `examples/clean.json`:

```json
{
  "value": "12450.75",
  "confidence": 0.95,
  "state": "extracted",
  "evidence": [{
    "page": 1,
    "start": 383,
    "end": 411,
    "quote": "Change Amount: USD 12,450.75",
    "method": "rules",
    "source": "text"
  }],
  "alternatives": []
}
```

The actual offsets are included in the generated example. Offsets refer to **page-local extracted text**, after CRLF/CR normalization to LF; they are not PDF byte offsets or bounding boxes. `source_sha256` identifies the original input bytes. Form-feed characters separate pages in text files.

The version 1.1 [JSON Schema](docs/schema.json) covers identifiers, project/parties, issue date, scope, currency, change amount, original/prior/revised contract amounts, calendar-day schedule impact and stated approval status. Calendar dates and field-state invariants are validated in addition to JSON shape. Missing fields have `null` values and zero confidence. Conflicts retain the alternatives and their evidence while leaving the field unresolved.

## Optional model extraction

```bash
export OPENAI_API_KEY='your-key'
change-orders examples/narrative.txt --model YOUR_STRUCTURED_OUTPUT_MODEL -o narrative.json
```

Choose an OpenAI model that supports strict JSON Schema outputs. This explicitly sends **all extracted page text** to OpenAI. The local path never sends documents. There is one bounded API request, no automatic retries, and a 60,000-character model input limit. No agent tools, document instructions, URLs or attachments are executed by the model path.

The model proposes raw values with page/quote evidence; it does not assign confidence. Code rejects values whose quote or raw substring cannot be found in the source, normalizes the survivors, and exposes disagreements with rules as conflicts. Immediate source context preserves omitted credit/minus direction and rejects obvious original/revised-total substitutions and negated or signature-only approval claims. Exact quote matching still does not prove every semantic association. Model-only values score 0.80 and require review at the default 0.85 threshold. Provider refusal, truncation and malformed responses fail explicitly; the CLI does not silently fall back to rules.

## Python API

```python
from change_orders import extract

result = extract("examples/digital.pdf")
if result.review_required:
    for issue in result.issues:
        print(issue.code, issue.field, issue.message)
else:
    print(result.fields.change_amount.value)

payload = result.model_dump_json(indent=2)
```

## Confidence and review

Scores are **versioned heuristics, not calibrated probabilities**:

| Evidence | Score |
| --- | ---: |
| Explicit label, PDF text layer / text input, valid normalization | 0.95 |
| Contextual phrase or generic Date label | 0.80 |
| Model-only candidate with exact supporting text | 0.80 |
| OCR-derived candidate | 0.70 |
| Valid candidate alongside rejected/invalid evidence for the same field | at most 0.60 |
| Missing, invalid or conflicting value | 0.00 |

The current policy is `heuristic-v2`. Repeated copies do not increase confidence. If native rule evidence and model/OCR evidence support the same normalized value, the strongest evidence determines its score. Overall confidence is the minimum score across the six required fields: change-order number, project, issue date, description, currency and change amount. Any validation issue triggers review, including low scores on optional fields. Absent optional fields do not require review. `--threshold` adjusts the score threshold for all resolved fields; it never disables ambiguity or arithmetic checks. A clean score is not authorization to approve a financial change order.

## Verify

```bash
pytest -q
ruff check .
ruff format --check .
python scripts/evaluate.py
python scripts/benchmark.py
python scripts/benchmark.py --ocr --runs 5
python -m build
```

PDF fixtures are checked in; regenerate with `python scripts/make_fixtures.py`. All examples are synthetic. The small regression corpus compares annotated values and reports abstentions; it is not a real-world accuracy benchmark. The current 14-document corpus checks 128 known values, five expected unresolved values and every review decision. Recall, precision and abstention are reported separately. These are development fixtures, not held-out evaluation data. Model transport and grounding are tested with mock responses; no live provider accuracy result is claimed.

See the [critical audit](docs/audit.md), [approach and failure modes](docs/approach.md), [measured local timings](docs/benchmark.json), and [OCR timings](docs/benchmark-ocr.json). CI tests Python 3.11–3.13, including real OCR, lint, regression evaluation and package building.

## Boundaries

One change order per input. English labels/OCR, US/UK decimal notation, calendar days, six explicit currencies. Line-item reconstruction, signatures, handwriting, attachments and multi-order splitting are outside this submission. `--ocr auto` OCRs only sparse pages; a mixed page with a substantial text header and an image-only body can require `--ocr always`. The included two-column example is tested, but arbitrary multi-column reading order can still be wrong. A pre-existing OCR text layer can look like PDF text; its origin and digit accuracy cannot be reliably established here.

Input limits are 20 MiB, 50 pages and 200,000 extracted characters. OCR rendering is capped at 25 million pixels per page; Tesseract has a 60-second page timeout. These are practical bounds, not a hostile-PDF sandbox. A production upload service should isolate parsing in workers with OS memory/time limits. No web server, database or queue is needed to review this implementation.

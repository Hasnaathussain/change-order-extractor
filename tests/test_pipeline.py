import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter

from change_orders import extract
from change_orders.cli import main
from change_orders.extract import extract_document, normalize_date, normalize_money
from change_orders.ingest import Document, InputError, Page, read_document
from change_orders.models import Candidate, Extracted, Result

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def doc(text, source="text"):
    return Document("a" * 64, [Page(1, text, source)], [])


def test_clean_complete_and_roundtrip():
    result = extract(EXAMPLES / "clean.txt")
    assert result.fields.change_order_number.value == "004"
    assert result.fields.change_amount.value == "12450.75"
    assert result.fields.issue_date.value == "2026-09-18"
    assert result.fields.schedule_days.value == 3
    assert "commissioning" in result.fields.description.value
    assert not result.review_required
    assert result.overall_confidence == 0.95
    assert Result.model_validate_json(result.model_dump_json()) == result


def test_credit_and_wrapped_values():
    result = extract(EXAMPLES / "messy-credit.txt")
    assert result.fields.change_order_number.value == "007"
    assert result.fields.project_name.value == "Riverside Library Retrofit"
    assert result.fields.change_amount.value == "-2300.00"
    assert result.fields.issue_date.value == "2026-09-18"
    assert not result.review_required


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("USD 1,234.50", "1234.50"),
        ("($45.10)", "-45.10"),
        ("-0.00", "0.00"),
        ("$12 CREDIT", "-12.00"),
        ("EUR +20.5", "20.50"),
    ],
)
def test_money(raw, expected):
    assert normalize_money(raw) == expected


@pytest.mark.parametrize("raw", ["1.234,56", "12,34", "1,2,3", "NaN", "1.234", "100 + 10", "10%"])
def test_money_rejects_ambiguous_and_malformed(raw):
    with pytest.raises(ValueError):
        normalize_money(raw)


@pytest.mark.parametrize("raw", ["01/02/2026", "2026-02-30", "31/13/2026", "09/18/26"])
def test_invalid_or_ambiguous_dates(raw):
    with pytest.raises(ValueError):
        normalize_date(raw, "auto")


def test_explicit_date_policy():
    assert normalize_date("01/02/2026", "mdy") == "2026-01-02"
    assert normalize_date("01/02/2026", "dmy") == "2026-02-01"


def test_conflict_abstains_and_keeps_alternatives():
    result = extract(EXAMPLES / "conflict.txt")
    amount = result.fields.change_amount
    assert amount.value is None and amount.confidence == 0
    assert amount.state == "conflict"
    assert {a.value for a in amount.alternatives} == {"8000.00", "9000.00"}
    assert result.fields.issue_date.state == "invalid"
    assert result.review_required


def test_identical_repeats_are_not_conflicts():
    result = extract_document(doc("Change Amount: USD 1,000.00\nChange Amount: USD 1000"))
    assert result.fields.change_amount.value == "1000.00"
    assert len(result.fields.change_amount.evidence) == 2


def test_currency_is_not_assumed_from_dollar_symbol():
    result = extract_document(doc("Change Amount: $100.00"))
    assert result.fields.change_amount.value == "100.00"
    assert result.fields.currency.value is None
    assert result.review_required


def test_currency_conflict():
    result = extract_document(doc("Currency: USD\nChange Amount: CAD 100"))
    assert result.fields.currency.state == "conflict"


def test_arithmetic_does_not_correct_document():
    result = extract_document(
        doc(
            "Original Contract Amount: USD 100\nPrior Changes: USD 0\n"
            "Change Amount: USD 10\nRevised Contract Amount: USD 120"
        )
    )
    assert result.fields.revised_contract_amount.value == "120.00"
    assert any(i.code == "contract_total_mismatch" for i in result.issues)


def test_no_invented_prior_changes():
    result = extract_document(doc("Original Contract Amount: USD 100\nChange Amount: USD 10"))
    assert result.fields.prior_changes_amount.value is None
    assert result.fields.revised_contract_amount.value is None


def test_business_days_and_blank_signature_are_not_inferred():
    result = extract_document(doc("Schedule Impact: 2 business days\nApproved by: _________"))
    assert result.fields.schedule_days.state == "invalid"
    assert result.fields.status.value is None


def test_ungrounded_model_value_is_rejected():
    candidate = Candidate(field="change_amount", raw="999", page=1, quote="Change Amount: USD 100")
    result = extract_document(doc("Change Amount: USD 100"), model_candidates=[candidate])
    assert result.fields.change_amount.value == "100.00"
    assert result.fields.change_amount.confidence == 0.6
    assert any(i.code == "ungrounded_candidate" for i in result.issues)


def test_grounded_model_value_and_rule_disagreement():
    text = "Change Amount: USD 100\nThe adjustment is USD 200."
    candidate = Candidate(
        field="change_amount", raw="USD 200", page=1, quote="The adjustment is USD 200."
    )
    result = extract_document(doc(text), model_candidates=[candidate])
    assert result.fields.change_amount.state == "conflict"


def test_model_only_confidence_is_capped():
    text = "The adjustment is USD 200."
    candidate = Candidate(field="change_amount", raw="USD 200", page=1, quote=text)
    result = extract_document(doc(text), model_candidates=[candidate])
    assert result.fields.change_amount.confidence == 0.8
    assert result.review_required


def test_ocr_caps_confidence():
    result = extract_document(doc((EXAMPLES / "clean.txt").read_text(), source="ocr"))
    assert result.overall_confidence == 0.7
    assert result.review_required


def test_all_evidence_spans_match_source():
    document = read_document(EXAMPLES / "clean.txt")
    result = extract_document(document)
    for field in result.fields.model_dump().values():
        for evidence in field["evidence"]:
            assert (
                document.pages[evidence["page"] - 1].text[evidence["start"] : evidence["end"]]
                == evidence["quote"]
            )


def test_digital_pdf():
    result = extract(EXAMPLES / "digital.pdf")
    assert result.fields.change_amount.value == "12450.75"
    assert not result.review_required
    assert result.pages[0].source == "pdf"


def test_scanned_pdf_without_ocr():
    with pytest.raises(InputError, match="No readable text"):
        extract(EXAMPLES / "scanned.pdf")


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract not installed")
def test_scanned_pdf_with_real_ocr():
    result = extract(EXAMPLES / "scanned.pdf", ocr="auto")
    assert result.fields.change_amount.value == "12450.75"
    assert result.pages[0].source == "ocr"
    assert result.review_required


def test_missing_ocr_dependency(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(InputError, match="Tesseract"):
        extract(EXAMPLES / "scanned.pdf", ocr="auto")


def test_encrypted_pdf(tmp_path):
    path = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    writer.write(path)
    with pytest.raises(InputError, match="Encrypted"):
        extract(path)


@pytest.mark.parametrize(
    "content,suffix", [(b"", ".txt"), (b"\xff", ".txt"), (b"invalid", ".pdf"), (b"x", ".exe")]
)
def test_invalid_input(tmp_path, content, suffix):
    path = tmp_path / f"input{suffix}"
    path.write_bytes(content)
    with pytest.raises(InputError):
        extract(path)


def test_size_limit(tmp_path):
    path = tmp_path / "large.txt"
    with path.open("wb") as f:
        f.truncate(20 * 1024 * 1024 + 1)
    with pytest.raises(InputError, match="20 MiB"):
        extract(path)


def test_schema_rejects_extra_and_bad_states():
    with pytest.raises(ValidationError):
        Extracted[str](value="x", state="missing")
    with pytest.raises(ValidationError):
        Extracted[str](value="x", state="extracted", confidence=0.9)
    with pytest.raises(ValidationError):
        Result.model_validate({"invented": True})


def test_cli_contract_and_atomic_output(tmp_path, capsys):
    output = tmp_path / "result.json"
    assert main([str(EXAMPLES / "clean.txt"), "-o", str(output)]) == 0
    Result.model_validate_json(output.read_text())
    assert main([str(EXAMPLES / "conflict.txt")]) == 2
    assert json.loads(capsys.readouterr().out)["review_required"]
    assert main([str(tmp_path / "missing.pdf")]) == 1
    assert "change-orders:" in capsys.readouterr().err


def test_cli_wont_overwrite_input():
    with pytest.raises(SystemExit):
        main([str(EXAMPLES / "clean.txt"), "-o", str(EXAMPLES / "clean.txt")])


def test_windows_line_endings(tmp_path):
    path = tmp_path / "windows.txt"
    path.write_bytes((EXAMPLES / "messy-credit.txt").read_bytes().replace(b"\n", b"\r\n"))
    result = extract(path)
    assert result.fields.project_name.value == "Riverside Library Retrofit"
    assert not any(i.code == "ungrounded_candidate" for i in result.issues)


def test_auto_ocr_runs_only_on_sparse_pages(monkeypatch):
    calls = []

    def fake_ocr(path, index):
        calls.append(index)
        return "Change Amount: USD 25\nDescription: Added work"

    monkeypatch.setattr("change_orders.ingest.ocr_page", fake_ocr)
    result = extract(EXAMPLES / "mixed.pdf", ocr="auto")
    assert calls == [1]
    assert [p.source for p in result.pages] == ["pdf", "ocr"]


def test_page_and_character_limits(tmp_path):
    for content in ("\f" * 51, "x" * 200_001):
        path = tmp_path / "large.txt"
        path.write_text(content)
        with pytest.raises(InputError, match="200,000"):
            extract(path)


@pytest.mark.parametrize("raw", ["USD 100 CREDIT INCREASE", "USD -100 INCREASE"])
def test_contradictory_money_direction(raw):
    with pytest.raises(ValueError):
        normalize_money(raw)

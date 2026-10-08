"""Regression cases discovered by the critical audit, separate from initial fixtures."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from change_orders import extract
from change_orders.extract import extract_document, normalize_money
from change_orders.ingest import Document, Page
from change_orders.models import Alternative, Candidate, Evidence, Extracted, Fields, Result

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def candidate_result(text, field, raw):
    document = Document("a" * 64, [Page(1, text, "text")], [])
    candidate = Candidate(field=field, raw=raw, page=1, quote=text)
    return extract_document(document, model_candidates=[candidate])


def evidence():
    return Evidence(page=1, start=0, end=1, quote="x", method="rules", source="text")


def test_inline_and_table_labels():
    for filename, amount in [("inline.txt", "2750.00"), ("pipe-table.txt", "950.25")]:
        result = extract(EXAMPLES / "audit" / filename)
        assert result.fields.project_name.value == "Harbor Clinic"
        assert result.fields.owner.value == "Harbor Facilities"
        assert result.fields.contractor.value == "Beacon Builders"
        assert result.fields.change_amount.value == amount
        assert not result.review_required


def test_stacked_form_financial_direction_and_scope_boundary():
    result = extract(EXAMPLES / "audit/stacked-form.txt")
    assert result.fields.change_amount.value == "-250.00"
    assert result.fields.revised_contract_amount.value == "104750.00"
    assert result.fields.schedule_days.value == -1
    assert (
        result.fields.description.value
        == "Omit the exterior sunshade and seal the anchor penetrations."
    )
    assert result.review_required  # context-derived values are reviewed
    assert not any(i.code == "contract_total_mismatch" for i in result.issues)


def test_native_multicolumn_multipage_pdf():
    result = extract(EXAMPLES / "audit/two-column.pdf")
    assert result.fields.project_name.value == "Harbor Clinic"
    assert result.fields.issue_date.value == "2026-09-29"
    assert result.fields.change_amount.value == "800.00"
    assert result.fields.change_amount.evidence[0].page == 2
    assert not result.review_required


def test_narrative_coverage_and_lower_confidence():
    result = extract(EXAMPLES / "narrative.txt")
    assert result.fields.change_order_number.value == "CO-019"
    assert result.fields.project_name.value == "Riverside Library Retrofit"
    assert result.fields.contract_number.value == "RL-2026-17"
    assert result.fields.owner.value == "Riverside Facilities"
    assert result.fields.contractor.value == "Northbridge Construction"
    assert result.fields.issue_date.value == "2026-09-21"
    assert result.fields.change_amount.value == "1850.00"
    assert result.fields.currency.value == "USD"
    assert result.fields.schedule_days.value == 2
    assert result.fields.status.value == "proposed"
    assert result.overall_confidence == 0.8
    assert result.review_required


@pytest.mark.parametrize(
    "text,raw",
    [
        ("The adjustment is a credit of USD 250.00.", "USD 250.00"),
        ("The adjustment is a credit of USD 250.00.", "250.00"),
        (
            "The Contract Sum will be decreased by this Change Order in the amount of USD 250.00",
            "USD 250.00",
        ),
        ("Change Amount: USD 250.00 CREDIT", "USD 250.00"),
        ("Change Amount: (USD 250.00)", "USD 250.00"),
        ("Change Amount: (USD 250.00)", "250.00"),
        ("Change Amount: -250.00", "250.00"),
    ],
)
def test_model_cannot_lose_credit_direction(text, raw):
    result = candidate_result(text, "change_amount", raw)
    assert result.fields.change_amount.value == "-250.00"
    assert result.fields.change_amount.state != "conflict"


@pytest.mark.parametrize(
    "text",
    [
        "Status: not approved",
        "This has not yet been approved.",
        "Approved by: __________________",
        "Approved by: Jane Smith",
    ],
)
def test_model_cannot_assert_negated_or_signature_approval(text):
    result = candidate_result(text, "status", "approved" if "approved" in text else "Approved")
    assert result.fields.status.value is None
    assert any(i.code == "invalid_value" for i in result.issues)


def test_model_cannot_relabel_original_total_as_change():
    result = candidate_result(
        "Original Contract Amount: USD 100000.00", "change_amount", "USD 100000.00"
    )
    assert result.fields.change_amount.value is None
    assert result.fields.change_amount.state == "invalid"


@pytest.mark.parametrize("raw", ["INCREASE (USD 100)", "1000000000000000000", "9" * 40])
def test_money_direction_and_precision_limits(raw):
    with pytest.raises(ValueError):
        normalize_money(raw)


def test_18_digit_financial_sum_preserves_cents():
    text = (
        "Original Contract Amount: USD 999999999999999990.01\n"
        "Prior Changes: USD 1.02\nChange Amount: USD 2.03\n"
        "Revised Contract Amount: USD 999999999999999993.06"
    )
    result = extract_document(Document("a" * 64, [Page(1, text, "text")], []))
    assert not any(i.code == "contract_total_mismatch" for i in result.issues)


def test_exported_model_rejects_impossible_calendar_date():
    with pytest.raises(ValidationError):
        Fields(
            issue_date=Extracted(
                value="2026-02-30", state="extracted", confidence=0.95, evidence=[evidence()]
            ).model_dump()
        )


def test_conflict_requires_distinct_alternatives():
    alternative = Alternative(value="100.00", evidence=[evidence()])
    with pytest.raises(ValidationError):
        Extracted(state="conflict", alternatives=[alternative, alternative])


def test_missing_state_cannot_include_source_evidence():
    with pytest.raises(ValidationError):
        Extracted(state="missing", evidence=[evidence()])


def test_review_flag_must_agree_with_issues():
    payload = extract(EXAMPLES / "conflict.txt").model_dump()
    payload["review_required"] = False
    with pytest.raises(ValidationError):
        Result.model_validate(payload)


def test_evidence_must_fit_page():
    payload = extract(EXAMPLES / "clean.txt").model_dump()
    payload["pages"][0]["characters"] = 1
    with pytest.raises(ValidationError):
        Result.model_validate(payload)


def test_invalid_values_keep_review_evidence():
    result = extract(EXAMPLES / "conflict.txt")
    assert result.fields.issue_date.evidence
    assert "09/10/2026" in result.fields.issue_date.evidence[0].quote


def test_generic_date_needs_review():
    text = (EXAMPLES / "clean.txt").read_text().replace("Issue Date:", "Date:")
    result = extract_document(Document("a" * 64, [Page(1, text, "text")], []))
    assert result.fields.issue_date.value == "2026-09-18"
    assert result.fields.issue_date.confidence == 0.8
    assert result.review_required


def test_unfamiliar_prose_abstains():
    result = candidate_result(
        "The existing estimate might rise eventually.", "change_amount", "999"
    )
    assert result.fields.change_amount.value is None
    assert result.review_required


def test_invalid_settings_precede_provider_call(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid settings must be rejected before calling the provider")

    monkeypatch.setattr("change_orders.llm.propose", forbidden)
    with pytest.raises(ValueError):
        extract(EXAMPLES / "clean.txt", model="test", threshold=float("nan"))


def test_increase_with_parenthesized_credit_is_not_silently_reversed():
    text = "The Contract Sum will be increased by this Change Order in the amount of (USD 250.00)"
    result = candidate_result(text, "change_amount", "250.00")
    assert result.fields.change_amount.value is None
    assert result.fields.change_amount.state == "invalid"


def test_unknown_label_stops_scope_continuation():
    text = "Description: Add lights.\nAuthorized by: John Doe\nChange Amount: USD 50"
    result = extract_document(Document("a" * 64, [Page(1, text, "text")], []))
    assert result.fields.description.value == "Add lights."


def test_wrapped_evidence_preserves_trailing_spaces():
    text = "Project Name:   \n  Harbor Clinic\nIssue Date: 2026-09-20"
    result = extract_document(Document("a" * 64, [Page(1, text, "text")], []))
    assert result.fields.project_name.value == "Harbor Clinic"
    quote = result.fields.project_name.evidence[0]
    assert text[quote.start : quote.end] == quote.quote


def test_optional_model_field_also_requires_review():
    text = (
        (EXAMPLES / "clean.txt")
        .read_text()
        .replace("Status: proposed", "The approval remains pending.")
    )
    document = Document("a" * 64, [Page(1, text, "text")], [])
    candidate = Candidate(
        field="status", raw="pending", page=1, quote="The approval remains pending."
    )
    result = extract_document(document, model_candidates=[candidate])
    assert result.overall_confidence == 0.95
    assert result.fields.status.confidence == 0.8
    assert result.review_required
    assert any(i.code == "low_confidence" and i.field == "status" for i in result.issues)


def test_identical_repeated_quotes_have_distinct_source_offsets():
    line = "Change Amount: USD 100.00"
    text = line + "\n" + line
    result = extract_document(Document("a" * 64, [Page(1, text, "text")], []))
    spans = result.fields.change_amount.evidence
    assert {e.start for e in spans} == {0, len(line) + 1}
    assert len(spans) == 2
    assert result.fields.change_amount.confidence == 0.95

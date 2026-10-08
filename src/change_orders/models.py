"""Public output contract. Missing and conflicting values are first-class states."""

from datetime import date
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")
Money = Annotated[str, Field(pattern=r"^-?(?:0|[1-9]\d{0,17})\.\d{2}$")]


def valid_date(value: str) -> str:
    date.fromisoformat(value)
    return value


ISODate = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}-\d{2}$", json_schema_extra={"format": "date"}),
    AfterValidator(valid_date),
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(Model):
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    method: Literal["rules", "context", "llm"]
    source: Literal["text", "pdf", "ocr"]

    @model_validator(mode="after")
    def valid_span(self):
        if self.end - self.start != len(self.quote):
            raise ValueError("Evidence offsets must match quote length")
        return self


class Alternative(Model, Generic[T]):
    value: T
    evidence: list[Evidence] = Field(min_length=1)


class Extracted(Model, Generic[T]):
    value: T | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    state: Literal["extracted", "missing", "invalid", "conflict"] = "missing"
    evidence: list[Evidence] = Field(default_factory=list)
    alternatives: list[Alternative[T]] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_state(self):
        if self.state == "extracted":
            if self.value is None or not self.evidence or self.confidence <= 0:
                raise ValueError("Extracted values require evidence and positive confidence")
        elif self.value is not None or self.confidence != 0:
            raise ValueError("Unresolved values must be null with zero confidence")
        if self.state == "conflict":
            if len({repr(a.value) for a in self.alternatives}) < 2:
                raise ValueError("Conflicts require at least two distinct alternatives")
        elif self.alternatives:
            raise ValueError("Only conflicts may contain alternatives")
        if self.state == "missing" and self.evidence:
            raise ValueError("Missing fields cannot contain evidence")
        return self


class Fields(Model):
    change_order_number: Extracted[str] = Field(default_factory=Extracted)
    project_name: Extracted[str] = Field(default_factory=Extracted)
    contract_number: Extracted[str] = Field(default_factory=Extracted)
    owner: Extracted[str] = Field(default_factory=Extracted)
    contractor: Extracted[str] = Field(default_factory=Extracted)
    issue_date: Extracted[ISODate] = Field(default_factory=Extracted)
    description: Extracted[str] = Field(default_factory=Extracted)
    currency: Extracted[Literal["USD", "CAD", "AUD", "EUR", "GBP", "PKR"]] = Field(
        default_factory=Extracted
    )
    change_amount: Extracted[Money] = Field(default_factory=Extracted)
    original_contract_amount: Extracted[Money] = Field(default_factory=Extracted)
    prior_changes_amount: Extracted[Money] = Field(default_factory=Extracted)
    revised_contract_amount: Extracted[Money] = Field(default_factory=Extracted)
    schedule_days: Extracted[int] = Field(default_factory=Extracted)
    status: Extracted[Literal["proposed", "approved", "rejected", "pending"]] = Field(
        default_factory=Extracted
    )


class Issue(Model):
    code: str
    field: str | None = None
    message: str


class PageInfo(Model):
    page: int = Field(ge=1)
    source: Literal["text", "pdf", "ocr"]
    characters: int = Field(ge=0)


class Result(Model):
    schema_version: Literal["1.1"] = "1.1"
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pages: list[PageInfo]
    fields: Fields
    issues: list[Issue]
    review_required: bool
    overall_confidence: float = Field(ge=0, le=1)
    confidence_policy: Literal["heuristic-v2"] = "heuristic-v2"

    @model_validator(mode="after")
    def valid_result(self):
        if self.review_required != bool(self.issues):
            raise ValueError("Review flag must agree with validation issues")
        numbers = [page.page for page in self.pages]
        if not numbers or len(set(numbers)) != len(numbers):
            raise ValueError("Pages must be present and uniquely numbered")
        page_sizes = {page.page: page.characters for page in self.pages}
        for extracted in (getattr(self.fields, name) for name in Fields.model_fields):
            evidence = extracted.evidence + [e for a in extracted.alternatives for e in a.evidence]
            if any(e.page not in page_sizes or e.end > page_sizes[e.page] for e in evidence):
                raise ValueError("Evidence must lie within a source page")
        return self


FieldName = Literal[
    "change_order_number",
    "project_name",
    "contract_number",
    "owner",
    "contractor",
    "issue_date",
    "description",
    "currency",
    "change_amount",
    "original_contract_amount",
    "prior_changes_amount",
    "revised_contract_amount",
    "schedule_days",
    "status",
]


class Candidate(Model):
    field: FieldName
    raw: str = Field(min_length=1, max_length=4000)
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=8000)


class Candidates(Model):
    candidates: list[Candidate] = Field(max_length=200)

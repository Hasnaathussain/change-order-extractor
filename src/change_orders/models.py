"""Public output contract. Missing and conflicting values are first-class states."""

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")
Money = Annotated[str, Field(pattern=r"^-?(?:0|[1-9]\d*)\.\d{2}$")]
ISODate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(Model):
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    method: Literal["rules", "llm"]
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
        if self.state == "conflict" and len(self.alternatives) < 2:
            raise ValueError("Conflicts require at least two alternatives")
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
    page: int
    source: Literal["text", "pdf", "ocr"]
    characters: int


class Result(Model):
    schema_version: Literal["1.0"] = "1.0"
    source_sha256: str
    pages: list[PageInfo]
    fields: Fields
    issues: list[Issue]
    review_required: bool
    overall_confidence: float = Field(ge=0, le=1)
    confidence_policy: Literal["heuristic-v1"] = "heuristic-v1"


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

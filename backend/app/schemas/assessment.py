"""API contract for credit assessment.

Validation is the first security control the service applies. Every numeric
field carries a range drawn from what is physically plausible for an Indian
retail credit application, so malformed or hostile input is rejected at the
edge with a 422 rather than reaching the model and producing a confident score
for nonsense.

Bureau fields are ``None``-able by design. A new-to-credit applicant genuinely
has no bureau score, and the model consumes that absence as a NaN rather than
having a median imputed into it. Making the field optional at the API boundary
is what allows that to remain true end to end.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Education = Literal["upto_secondary", "higher_secondary", "graduate", "postgraduate"]
Employment = Literal["salaried_formal", "salaried_informal", "self_employed", "gig_worker", "agri"]
LoanPurpose = Literal[
    "consumer_durable", "education", "medical", "business_working_capital", "two_wheeler"
]


class ApplicantInput(BaseModel):
    """One credit application.

    Note what is absent: no name, no PAN, no Aadhaar, no phone number, no
    address. The model does not need identity to assess repayment capacity, and
    under the DPDP Act's data-minimisation duty it should not receive what it
    does not need. Identity belongs in the lender's system of record, not in
    the scoring request.
    """

    model_config = ConfigDict(extra="forbid")

    applicant_id: Annotated[str, Field(max_length=64, pattern=r"^[A-Za-z0-9_-]+$")] = "ANON"

    # --- application ---
    age: Annotated[int, Field(ge=18, le=100)]
    education: Education
    employment_type: Employment
    monthly_income_declared: Annotated[float, Field(ge=1_000, le=10_000_000)]
    loan_amount_requested: Annotated[float, Field(ge=1_000, le=10_000_000)]
    loan_tenure_months: Annotated[int, Field(ge=3, le=120)]
    loan_purpose: LoanPurpose

    # --- bureau: absent for new-to-credit applicants ---
    is_new_to_credit: Annotated[int, Field(ge=0, le=1)] = 0
    bureau_score: Annotated[float | None, Field(ge=300, le=900)] = None
    credit_history_months: Annotated[float | None, Field(ge=0, le=600)] = None
    num_existing_loans: Annotated[int, Field(ge=0, le=50)] = 0
    enquiries_6m: Annotated[int, Field(ge=0, le=50)] = 0

    # --- Account Aggregator: banking and UPI ---
    upi_txn_count_3m: Annotated[int, Field(ge=0, le=10_000)] = 0
    upi_inflow_median: Annotated[float, Field(ge=0, le=10_000_000)] = 0
    upi_inflow_cv: Annotated[float, Field(ge=0, le=5)] = 0.5
    upi_merchant_diversity: Annotated[int, Field(ge=0, le=500)] = 0
    avg_balance_3m: Annotated[float, Field(ge=0, le=10_000_000)] = 0
    days_balance_below_500: Annotated[int, Field(ge=0, le=90)] = 0
    salary_regularity: Annotated[float, Field(ge=0, le=1)] = 0.0

    # --- telecom and utility ---
    mobile_tenure_months: Annotated[float, Field(ge=0, le=600)] = 0
    recharge_regularity: Annotated[float, Field(ge=0, le=1)] = 0.0
    utility_ontime_ratio: Annotated[float, Field(ge=0, le=1)] = 0.0
    sim_changes_12m: Annotated[int, Field(ge=0, le=20)] = 0

    @property
    def emi_to_income(self) -> float:
        """Derived: instalment against declared income, as the underwriter sees it."""
        emi = self.loan_amount_requested * 1.17 / max(self.loan_tenure_months, 1)
        return min(max(emi / max(self.monthly_income_declared, 1), 0.01), 5.0)


class ReasonCodeOut(BaseModel):
    rank: int
    feature: str
    label: str
    phrase: str
    value: float | str | None
    direction: Literal["adverse", "favourable"]
    actionability: str
    contribution: float | None = Field(
        default=None,
        description="Signed log-odds contribution. Underwriter view only.",
    )


class RecourseOut(BaseModel):
    feature: str
    label: str
    current_value: float
    target_value: float
    direction: str
    effort: str
    hint: str | None = None
    projected_pd: float | None = Field(
        default=None, description="Projected probability of default. Underwriter view only."
    )


class CitationOut(BaseModel):
    chunk_id: str
    heading: str
    instrument: str
    citation: str
    text: str
    score: float | None = None


class ProvenanceOut(BaseModel):
    narrative_source: str
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    guardrail_passed: bool = True
    guardrail_violations: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None


class AssessmentResponse(BaseModel):
    """The assessment as returned to the caller.

    Fields marked underwriter-only are omitted entirely for applicant tokens
    rather than nulled, so an applicant response carries no trace of the
    internal scoring surface.
    """

    applicant_id: str
    decision: Literal["APPROVE", "DECLINE"]
    is_new_to_credit: bool
    adverse_reasons: list[ReasonCodeOut]
    favourable_reasons: list[ReasonCodeOut]
    recourse: list[RecourseOut]
    citations: list[CitationOut]
    narrative: str

    probability_of_default: float | None = Field(
        default=None, description="Underwriter view only."
    )
    threshold: float | None = Field(default=None, description="Underwriter view only.")
    deterministic_notice: str | None = Field(
        default=None, description="Underwriter view only."
    )
    provenance: ProvenanceOut | None = Field(default=None, description="Underwriter view only.")


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: str
    expires_in_minutes: int

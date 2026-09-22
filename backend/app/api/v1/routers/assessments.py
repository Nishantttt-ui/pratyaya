"""Credit assessment endpoints."""

from __future__ import annotations

from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request

from backend.app.api.deps import ServiceDep
from backend.app.core.security import Role, TokenSubject, get_current_user
from backend.app.schemas.assessment import (
    ApplicantInput,
    AssessmentResponse,
    CitationOut,
    ProvenanceOut,
    ReasonCodeOut,
    RecourseOut,
)
from backend.app.services.decision_service import AssessmentResult

router = APIRouter(tags=["assessments"])


def applicant_to_frame(applicant: ApplicantInput) -> pd.DataFrame:
    """Convert the validated request into the single-row frame the model scores."""
    record = applicant.model_dump()
    record["emi_to_income"] = applicant.emi_to_income
    return pd.DataFrame([record])


def to_response(
    result: AssessmentResult, applicant_id: str, *, role: Role
) -> AssessmentResponse:
    """Project the assessment onto the view this role is entitled to see.

    Underwriter-only fields are omitted rather than nulled for applicants, so an
    applicant response carries no trace of the internal scoring surface.
    """
    is_underwriter = role is Role.UNDERWRITER

    # Underwriter-only fields are left *unset* rather than set to None, and the
    # route serialises with exclude_unset. Passing None would still emit the key
    # as null, which is a trace of the scoring surface rather than its absence.
    # A field that is genuinely null and meaningful - a reason code's `value`
    # for a feature the applicant has no record of - is always passed, so it
    # survives the exclusion.
    def reason_out(raw: dict) -> ReasonCodeOut:
        fields = {
            "rank": raw["rank"],
            "feature": raw["feature"],
            "label": raw["label"],
            "phrase": raw["phrase"],
            "value": raw["value"],
            "direction": raw["direction"],
            "actionability": raw["actionability"],
        }
        if is_underwriter:
            fields["contribution"] = raw["contribution"]
        return ReasonCodeOut(**fields)

    def recourse_out(raw: dict) -> RecourseOut:
        fields = {
            "feature": raw["feature"],
            "label": raw["label"],
            "current_value": raw["current_value"],
            "target_value": raw["target_value"],
            "direction": raw["direction"],
            "effort": raw["effort"],
            "hint": raw["hint"],
        }
        if is_underwriter:
            fields["projected_pd"] = raw["projected_pd"]
        return RecourseOut(**fields)

    fields = {
        "applicant_id": applicant_id,
        "decision": result.decision,
        "is_new_to_credit": result.is_new_to_credit,
        "adverse_reasons": [reason_out(r) for r in result.adverse_reasons],
        "favourable_reasons": [reason_out(r) for r in result.favourable_reasons],
        "recourse": [recourse_out(o) for o in result.recourse],
        "citations": [CitationOut(**c) for c in result.citations],
        "narrative": result.narrative,
    }
    if is_underwriter:
        fields["probability_of_default"] = result.probability_of_default
        fields["threshold"] = result.threshold
        fields["deterministic_notice"] = result.deterministic_notice
        fields["provenance"] = ProvenanceOut(**result.provenance.__dict__)
    return AssessmentResponse(**fields)


@router.post(
    "/assessments",
    response_model=AssessmentResponse,
    response_model_exclude_unset=True,
)
async def create_assessment(
    applicant: ApplicantInput,
    service: ServiceDep,
    user: Annotated[TokenSubject, Depends(get_current_user)],
) -> AssessmentResponse:
    """Assess one application and return the decision with its reasons.

    The decision is produced by a deterministic model. The narrative is written
    by a language model only when one is configured and its output passes the
    outbound guardrail; otherwise the deterministic notice is returned. The
    ``provenance`` block records which path was taken.
    """
    frame = applicant_to_frame(applicant)
    result = await service.assess(frame)
    return to_response(result, applicant.applicant_id, role=user.role)


@router.get("/applicants/sample")
async def sample_applicants(
    request: Request,
    user: Annotated[TokenSubject, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    new_to_credit_only: bool = False,
) -> list[dict]:
    """Return sample applications from the reference population.

    Provided so the interface can be explored without hand-entering 20 fields.
    These are generated records, not real people.
    """
    population: pd.DataFrame = request.app.state.population
    frame = population
    if new_to_credit_only:
        frame = frame[frame["is_new_to_credit"] == 1]

    sample = frame.sample(min(limit, len(frame)), random_state=None)
    drop = {"default_12m", "gender", "region_tier", "age_band"}
    columns = [c for c in sample.columns if c not in drop]
    records = sample[columns].to_dict(orient="records")
    return [
        {k: (None if pd.isna(v) else v) for k, v in record.items()} for record in records
    ]

"""API behaviour: authentication, authorisation, validation and role projection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

APPLICATION = {
    "applicant_id": "TEST001",
    "age": 26,
    "education": "higher_secondary",
    "employment_type": "gig_worker",
    "monthly_income_declared": 16000,
    "loan_amount_requested": 85000,
    "loan_tenure_months": 9,
    "loan_purpose": "two_wheeler",
    "is_new_to_credit": 1,
    "upi_txn_count_3m": 52,
    "upi_inflow_median": 5200,
    "upi_inflow_cv": 0.71,
    "upi_merchant_diversity": 7,
    "avg_balance_3m": 1400,
    "days_balance_below_500": 38,
    "salary_regularity": 0.25,
    "mobile_tenure_months": 14,
    "recharge_regularity": 0.42,
    "utility_ontime_ratio": 0.38,
    "sim_changes_12m": 1,
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _token(client, username, password):
    response = client.post("/api/v1/auth/token", data={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def underwriter_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'underwriter', 'test-underwriter-pw')}"}


@pytest.fixture(scope="module")
def applicant_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'applicant', 'test-applicant-pw')}"}


def test_health_is_public_and_reports_components(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["components"]["model"] is True
    assert body["components"]["policy_corpus"] == 37


def test_health_does_not_leak_configuration(client):
    """Readiness must not disclose keys, hosts or connection strings."""
    text = client.get("/health").text.lower()
    for secret in ("postgresql://", "password", "api_key", "secret", "@"):
        assert secret not in text


def test_assessment_requires_authentication(client):
    assert client.post("/api/v1/assessments", json=APPLICATION).status_code == 401


def test_invalid_credentials_are_rejected(client):
    response = client.post(
        "/api/v1/auth/token", data={"username": "underwriter", "password": "wrong"}
    )
    assert response.status_code == 401


def test_unknown_and_wrong_password_give_identical_responses(client):
    """The endpoint must not be usable to enumerate valid usernames."""
    unknown = client.post(
        "/api/v1/auth/token", data={"username": "nobody", "password": "x"}
    )
    wrong = client.post(
        "/api/v1/auth/token", data={"username": "underwriter", "password": "x"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_malformed_token_is_rejected(client):
    response = client.post(
        "/api/v1/assessments",
        json=APPLICATION,
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_underwriter_sees_the_full_decision(client, underwriter_headers):
    body = client.post("/api/v1/assessments", json=APPLICATION, headers=underwriter_headers).json()
    assert body["decision"] in {"APPROVE", "DECLINE"}
    assert body["probability_of_default"] is not None
    assert body["threshold"] is not None
    assert body["provenance"] is not None
    assert body["adverse_reasons"][0]["contribution"] is not None


def test_applicant_view_omits_the_scoring_surface(client, applicant_headers):
    body = client.post("/api/v1/assessments", json=APPLICATION, headers=applicant_headers).json()
    assert body["probability_of_default"] is None
    assert body["threshold"] is None
    assert body["provenance"] is None
    assert body["deterministic_notice"] is None
    assert body["adverse_reasons"][0]["contribution"] is None


def test_applicant_still_receives_reasons_and_rights(client, applicant_headers):
    """Withholding internals must not withhold the Fair Practices Code duty."""
    body = client.post("/api/v1/assessments", json=APPLICATION, headers=applicant_headers).json()
    assert body["adverse_reasons"]
    assert body["citations"]
    assert body["narrative"].strip()


def test_both_roles_receive_the_same_decision(client, underwriter_headers, applicant_headers):
    a = client.post("/api/v1/assessments", json=APPLICATION, headers=underwriter_headers).json()
    b = client.post("/api/v1/assessments", json=APPLICATION, headers=applicant_headers).json()
    assert a["decision"] == b["decision"]


@pytest.mark.parametrize(
    "mutation",
    [
        {"age": 5},
        {"age": 250},
        {"education": "phd"},
        {"monthly_income_declared": -1},
        {"days_balance_below_500": 500},
        {"utility_ontime_ratio": 2.0},
        {"loan_tenure_months": 0},
    ],
)
def test_out_of_range_input_is_rejected(client, underwriter_headers, mutation):
    response = client.post(
        "/api/v1/assessments", json={**APPLICATION, **mutation}, headers=underwriter_headers
    )
    assert response.status_code == 422


def test_personal_identifiers_are_refused_at_the_boundary(client, underwriter_headers):
    """The model has no business receiving a PAN, so the request is refused."""
    for field, value in (("pan", "ABCDE1234F"), ("aadhaar", "432187652109"), ("phone", "9876543210")):
        response = client.post(
            "/api/v1/assessments",
            json={**APPLICATION, field: value},
            headers=underwriter_headers,
        )
        assert response.status_code == 422


def test_new_to_credit_applicant_is_scored_without_a_bureau_record(client, underwriter_headers):
    body = client.post("/api/v1/assessments", json=APPLICATION, headers=underwriter_headers).json()
    assert body["is_new_to_credit"] is True
    assert 0.0 <= body["probability_of_default"] <= 1.0


def test_declines_carry_citations_and_recourse(client, underwriter_headers):
    body = client.post("/api/v1/assessments", json=APPLICATION, headers=underwriter_headers).json()
    if body["decision"] == "DECLINE":
        assert body["citations"]
        assert any(c["chunk_id"] == "FPC-01" for c in body["citations"])


def test_sample_endpoint_filters_to_new_to_credit(client, underwriter_headers):
    response = client.get(
        "/api/v1/applicants/sample?limit=5&new_to_credit_only=true", headers=underwriter_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert all(row["is_new_to_credit"] == 1 for row in body)


def test_sample_endpoint_excludes_protected_attributes(client, underwriter_headers):
    body = client.get("/api/v1/applicants/sample?limit=3", headers=underwriter_headers).json()
    for row in body:
        assert not {"gender", "region_tier", "age_band", "default_12m"} & set(row)

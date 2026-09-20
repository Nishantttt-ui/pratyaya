"""Guardrails around the explanation layer.

The threat model here is specific. This system does not let a user chat freely
with a model; it asks a model to describe a decision that has already been made.
So the risks worth defending against are:

1. **Leaking personal data to a third party.** Under the DPDP Act 2023 the
   lender is the Data Fiduciary and owes data minimisation. The outbound
   guardrail therefore asserts that no direct identifier is present in the
   prompt. By construction the prompt builder never includes one - this check
   exists to make that a tested invariant rather than an assumption.

2. **Prompt injection via applicant-controlled text.** Free-text fields reach
   the prompt, so an applicant could try to smuggle instructions into it.

3. **The explanation contradicting the decision.** This is the failure that
   actually matters in lending. If the model was declined but the generated
   text congratulates the applicant, the lender has mis-communicated a credit
   decision. ``verify_consistency`` rejects that outcome and the caller falls
   back to a deterministic template.

4. **Unsupported claims.** The narrative must not invent policy or promise
   future approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class GuardrailViolation(StrEnum):
    PII_IN_PROMPT = "pii_in_prompt"
    INJECTION_ATTEMPT = "injection_attempt"
    DECISION_CONTRADICTION = "decision_contradiction"
    UNSUPPORTED_GUARANTEE = "unsupported_guarantee"
    EMPTY_OUTPUT = "empty_output"


@dataclass
class GuardrailReport:
    """Outcome of a guardrail pass, recorded on the decision's audit trail."""

    passed: bool
    violations: list[GuardrailViolation] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    def fail(self, violation: GuardrailViolation, detail: str) -> None:
        self.passed = False
        self.violations.append(violation)
        self.details.append(detail)


# --- Indian identifier patterns -------------------------------------------
# Aadhaar: 12 digits, conventionally spaced 4-4-4, never starting 0 or 1.
_AADHAAR = re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b")
# PAN: five letters, four digits, one letter.
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
# Indian mobile: optional +91, then 6-9 followed by nine digits.
_PHONE = re.compile(r"\b(?:\+?91[\-\s]?)?[6-9]\d{9}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")

_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "aadhaar": _AADHAAR,
    "pan": _PAN,
    "phone": _PHONE,
    "email": _EMAIL,
}

_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard the above",
    "disregard previous",
    "system prompt",
    "you are now",
    "new instructions",
    "override",
    "approve this application",
    "act as",
    "pretend to be",
)

_GUARANTEE_MARKERS = (
    "guaranteed approval",
    "you will be approved",
    "we promise",
    "assured loan",
    "definitely approved",
    "100% approval",
)


def scan_for_pii(text: str) -> dict[str, list[str]]:
    """Return every PII-looking token found, grouped by kind."""
    found: dict[str, list[str]] = {}
    for label, pattern in _PII_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            found[label] = matches
    return found


def redact_pii(text: str) -> str:
    """Replace identifiers with typed placeholders.

    Used as defence in depth on any applicant-supplied free text that reaches a
    prompt. The placeholder keeps the sentence readable while removing the
    identifier.
    """
    redacted = text
    for label, pattern in _PII_PATTERNS.items():
        redacted = pattern.sub(f"[{label.upper()}_REDACTED]", redacted)
    return redacted


def check_prompt(prompt: str) -> GuardrailReport:
    """Inbound guardrail: run before anything is sent to a provider."""
    report = GuardrailReport(passed=True)

    pii = scan_for_pii(prompt)
    if pii:
        # Report the kinds found, never the values - this string gets logged.
        report.fail(
            GuardrailViolation.PII_IN_PROMPT,
            f"Prompt contained identifiers of type: {sorted(pii)}",
        )

    lowered = prompt.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            report.fail(
                GuardrailViolation.INJECTION_ATTEMPT,
                f"Prompt contained injection marker: {marker!r}",
            )
            break

    return report


def verify_consistency(generated: str, *, decision: str) -> GuardrailReport:
    """Outbound guardrail: the narrative must match the decision that was made.

    ``decision`` is the authoritative outcome from the scoring model. If the
    generated text asserts the opposite outcome, the explanation is rejected.
    """
    report = GuardrailReport(passed=True)
    text = generated.strip()

    if not text:
        report.fail(GuardrailViolation.EMPTY_OUTPUT, "Provider returned empty text")
        return report

    lowered = text.lower()

    approve_claims = ("approved", "you qualify", "congratulations", "has been accepted")
    decline_claims = ("declined", "rejected", "not approved", "unable to approve")

    says_approved = any(claim in lowered for claim in approve_claims)
    says_declined = any(claim in lowered for claim in decline_claims)

    decision_norm = decision.strip().upper()
    if decision_norm == "DECLINE" and says_approved and not says_declined:
        report.fail(
            GuardrailViolation.DECISION_CONTRADICTION,
            "Model was DECLINE but the explanation asserts approval",
        )
    if decision_norm == "APPROVE" and says_declined and not says_approved:
        report.fail(
            GuardrailViolation.DECISION_CONTRADICTION,
            "Model was APPROVE but the explanation asserts decline",
        )

    for marker in _GUARANTEE_MARKERS:
        if marker in lowered:
            report.fail(
                GuardrailViolation.UNSUPPORTED_GUARANTEE,
                f"Explanation contained an unsupported guarantee: {marker!r}",
            )
            break

    if pii := scan_for_pii(text):
        report.fail(
            GuardrailViolation.PII_IN_PROMPT,
            f"Generated text contained identifiers of type: {sorted(pii)}",
        )

    return report

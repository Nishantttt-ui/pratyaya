"""Deterministic rendering of a credit decision notice.

This module is the system's floor, not its ceiling. It produces a complete,
compliant, readable notice using only the model's reason codes, the recourse
options and the retrieved provisions - no language model involved.

It exists for three reasons:

1. **The RBI Fair Practices Code requires reasons to be conveyed** whenever an
   application is rejected. That obligation cannot be contingent on a
   third-party API being reachable, within quota, and returning something that
   passes a guardrail. So the lender's duty is discharged here, deterministically.
2. **It is the fallback.** When a guardrail rejects generated text, the service
   falls back to this rather than degrading to silence or shipping unchecked
   output.
3. **It is the audit baseline.** Because it is a pure function of the decision,
   the same decision always renders the same notice, which makes any divergence
   in the generated version visible.

The language model's contribution is to make this *warmer and clearer* for a
first-time borrower. It is never the source of the facts.
"""

from __future__ import annotations

from ml.explain.explainer import Explanation
from ml.explain.recourse import RecourseOption

_EFFORT_HORIZON = {
    "immediate": "straight away, by changing this application",
    "short_term": "over the next one to three months",
    "long_term": "over a longer period",
}


def _format_value(feature: str, value) -> str:
    """Render a feature value in units a person recognises."""
    if value is None:
        return "not available"
    if feature in {
        "monthly_income_declared", "loan_amount_requested",
        "avg_balance_3m", "upi_inflow_median",
    }:
        return f"Rs {float(value):,.0f}"
    if feature == "days_balance_below_500":
        return f"{float(value):.0f} of the last 90 days"
    if feature in {"utility_ontime_ratio", "recharge_regularity", "salary_regularity"}:
        return f"{float(value) * 100:.0f}%"
    if feature == "emi_to_income":
        return f"{float(value) * 100:.0f}% of declared income"
    if feature == "loan_tenure_months":
        return f"{float(value):.0f} months"
    if feature in {"mobile_tenure_months", "credit_history_months"}:
        return f"{float(value):.0f} months"
    if feature in {"upi_txn_count_3m", "upi_merchant_diversity", "sim_changes_12m",
                   "num_existing_loans", "enquiries_6m", "age"}:
        return f"{float(value):.0f}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def render_notice(
    explanation: Explanation,
    *,
    recourse: list[RecourseOption] | None = None,
    citations: list[dict] | None = None,
) -> str:
    """Render the full decision notice as plain text."""
    recourse = recourse or []
    citations = citations or []
    approved = explanation.decision == "APPROVE"

    lines: list[str] = []
    lines.append("KEY FACTS — CREDIT DECISION")
    lines.append("=" * 58)
    lines.append(f"Application reference : {explanation.applicant_id}")
    lines.append(
        f"Decision              : {'Approved' if approved else 'Not approved at this time'}"
    )
    if explanation.is_new_to_credit:
        lines.append(
            "Assessment basis      : No credit bureau record was available, so "
            "this application\n                        was assessed using the "
            "financial information you consented\n                        to share."
        )
    lines.append("")

    if approved:
        lines.append("WHY THIS WAS APPROVED")
        lines.append("-" * 58)
        drivers = explanation.favourable_reasons
        if drivers:
            for reason in drivers:
                lines.append(
                    f"  {reason.rank}. {reason.phrase.capitalize()} "
                    f"({_format_value(reason.feature, reason.value)})"
                )
        else:
            lines.append("  Your overall financial profile met our lending criteria.")
    else:
        lines.append("WHY THIS WAS NOT APPROVED")
        lines.append("-" * 58)
        lines.append("  The main factors that counted against this application were:")
        for reason in explanation.adverse_reasons:
            lines.append(
                f"  {reason.rank}. {reason.phrase.capitalize()} "
                f"({_format_value(reason.feature, reason.value)})"
            )
        if explanation.favourable_reasons:
            lines.append("")
            lines.append("  These factors counted in your favour:")
            for reason in explanation.favourable_reasons[:3]:
                lines.append(
                    f"     - {reason.phrase.capitalize()} "
                    f"({_format_value(reason.feature, reason.value)})"
                )

    if recourse and not approved:
        lines.append("")
        lines.append("WHAT COULD CHANGE THIS DECISION")
        lines.append("-" * 58)
        lines.append(
            "  Based on this assessment, any one of the following would have\n"
            "  been enough on its own to change the outcome:"
        )
        for option in recourse:
            horizon = _EFFORT_HORIZON.get(option.effort, "over time")
            lines.append(
                f"    - {option.label}: move from "
                f"{_format_value(option.feature, option.current_value)} to "
                f"{_format_value(option.feature, option.target_value)}, {horizon}."
            )
            if option.hint:
                lines.append(f"      {option.hint}")
        lines.append("")
        lines.append(
            "  These are estimates from the same model that assessed this\n"
            "  application. They are not a guarantee of approval."
        )

    if citations:
        lines.append("")
        lines.append("YOUR RIGHTS AND THE RULES THAT APPLY")
        lines.append("-" * 58)
        for citation in citations:
            lines.append(f"  [{citation['chunk_id']}] {citation['heading']}")
            lines.append(f"      {citation['citation']}")

    lines.append("")
    lines.append("-" * 58)
    lines.append(
        "This decision was produced by an automated model. You may ask for it\n"
        "to be reviewed, and you may request these reasons in writing. Contact\n"
        "details for the grievance redressal officer are published on our site."
    )
    return "\n".join(lines)

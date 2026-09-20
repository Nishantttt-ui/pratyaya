"""Human-readable meaning for every model feature.

A SHAP value is a number attached to a column name. Neither is an explanation
an applicant can act on. This dictionary is the translation layer between the
model's feature space and language a borrower or an underwriter can use, and it
records three things the explanation layer needs:

* ``label`` and ``adverse_phrase`` - how to name the factor in a sentence.
* ``higher_is_riskier`` - the direction of harm, so the narrative can say
  *"your requested EMI is high relative to income"* rather than the meaningless
  *"emi_to_income contributed +0.14"*.
* ``actionability`` - whether the applicant can realistically change this, and
  over what horizon. Recourse advice is only offered for factors they can
  actually move. Telling someone to change their age or their employment
  sector is not advice; it is insult framed as guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Actionability(StrEnum):
    """How far the applicant can move this factor, and how quickly."""

    IMMEDIATE = "immediate"        # controllable in this application
    SHORT_TERM = "short_term"      # roughly one to three months of behaviour
    LONG_TERM = "long_term"        # six months or more
    FIXED = "fixed"                # not reasonably changeable; never advise on it


@dataclass(frozen=True)
class FeatureMeaning:
    label: str
    adverse_phrase: str
    favourable_phrase: str
    higher_is_riskier: bool
    actionability: Actionability
    unit: str = ""
    recourse_hint: str | None = None
    # A derived feature is computed from others and cannot be moved on its own.
    # It still earns a reason code - the applicant should be told their
    # instalment is too large relative to income - but it must never be offered
    # as recourse, because "lower your instalment-to-income ratio" is not an
    # action. The actions are "borrow less" or "repay over longer", which are
    # offered separately.
    is_derived: bool = False


FEATURE_DICTIONARY: dict[str, FeatureMeaning] = {
    # --- application ---
    "age": FeatureMeaning(
        "Age", "age profile", "age profile", False, Actionability.FIXED, "years"
    ),
    "education": FeatureMeaning(
        "Education level", "education level recorded", "education level recorded",
        False, Actionability.FIXED,
    ),
    "employment_type": FeatureMeaning(
        "Employment type", "employment category", "employment category",
        False, Actionability.LONG_TERM,
    ),
    "monthly_income_declared": FeatureMeaning(
        "Declared monthly income", "declared income relative to the amount requested",
        "declared income", False, Actionability.LONG_TERM, "INR",
    ),
    "loan_amount_requested": FeatureMeaning(
        "Requested loan amount", "size of the loan requested", "size of the loan requested",
        True, Actionability.IMMEDIATE, "INR",
        recourse_hint="Requesting a smaller amount lowers the monthly instalment.",
    ),
    "loan_tenure_months": FeatureMeaning(
        "Requested tenure", "repayment period chosen", "repayment period chosen",
        False, Actionability.IMMEDIATE, "months",
        recourse_hint="A longer tenure reduces each monthly instalment.",
    ),
    "loan_purpose": FeatureMeaning(
        "Loan purpose", "stated purpose of the loan", "stated purpose of the loan",
        False, Actionability.IMMEDIATE,
    ),
    "emi_to_income": FeatureMeaning(
        "Instalment-to-income ratio", "monthly instalment is large relative to your income",
        "comfortable instalment relative to your income", True, Actionability.IMMEDIATE, "ratio",
        recourse_hint="Reduce the amount or extend the tenure to lower this ratio.",
        is_derived=True,
    ),
    # --- bureau ---
    "is_new_to_credit": FeatureMeaning(
        "New to credit", "no formal credit history on record",
        "existing credit history on record", True, Actionability.LONG_TERM,
    ),
    "bureau_score": FeatureMeaning(
        "Credit bureau score", "credit bureau score", "credit bureau score",
        False, Actionability.LONG_TERM, "points",
    ),
    "credit_history_months": FeatureMeaning(
        "Length of credit history", "short formal credit history",
        "established credit history", False, Actionability.LONG_TERM, "months",
    ),
    "num_existing_loans": FeatureMeaning(
        "Existing loans", "number of loans already running",
        "limited existing borrowing", True, Actionability.SHORT_TERM,
    ),
    "enquiries_6m": FeatureMeaning(
        "Recent credit enquiries", "several recent applications for credit",
        "few recent credit applications", True, Actionability.SHORT_TERM,
        recourse_hint="Spacing out new credit applications reduces this signal.",
    ),
    # --- Account Aggregator: banking and UPI ---
    "upi_txn_count_3m": FeatureMeaning(
        "UPI transaction count", "limited digital transaction activity",
        "active digital transaction record", False, Actionability.SHORT_TERM,
    ),
    "upi_inflow_median": FeatureMeaning(
        "Median monthly UPI inflow", "low money coming in each month",
        "steady money coming in each month", False, Actionability.LONG_TERM, "INR",
    ),
    "upi_inflow_cv": FeatureMeaning(
        "Income volatility", "income that varies sharply month to month",
        "stable month-to-month income", True, Actionability.LONG_TERM,
    ),
    "upi_merchant_diversity": FeatureMeaning(
        "Merchant diversity", "narrow range of payment activity",
        "varied, established payment activity", False, Actionability.SHORT_TERM,
    ),
    "avg_balance_3m": FeatureMeaning(
        "Average bank balance", "low average balance maintained",
        "healthy average balance maintained", False, Actionability.SHORT_TERM, "INR",
        recourse_hint="Holding a higher average balance over three months improves this.",
    ),
    "days_balance_below_500": FeatureMeaning(
        "Days with very low balance", "frequent days with a near-zero balance",
        "rarely runs a near-zero balance", True, Actionability.SHORT_TERM, "days",
        recourse_hint="Keeping the balance above Rs 500 more consistently improves this.",
    ),
    "salary_regularity": FeatureMeaning(
        "Income regularity", "no regular, predictable income credit",
        "regular, predictable income credits", False, Actionability.LONG_TERM,
    ),
    # --- telecom and utility ---
    "mobile_tenure_months": FeatureMeaning(
        "Mobile connection tenure", "short history on the current mobile number",
        "long-standing mobile connection", False, Actionability.LONG_TERM, "months",
    ),
    "recharge_regularity": FeatureMeaning(
        "Recharge regularity", "irregular mobile recharge pattern",
        "consistent mobile recharge pattern", False, Actionability.SHORT_TERM,
        recourse_hint="Recharging on a consistent schedule builds this signal.",
    ),
    "utility_ontime_ratio": FeatureMeaning(
        "Utility bill punctuality", "utility bills often paid late",
        "utility bills consistently paid on time", False, Actionability.SHORT_TERM, "ratio",
        recourse_hint="Paying utility bills on time for three months strengthens this.",
    ),
    "sim_changes_12m": FeatureMeaning(
        "SIM changes", "several SIM changes in the past year",
        "stable mobile identity", True, Actionability.SHORT_TERM,
    ),
}


def describe(feature: str) -> FeatureMeaning:
    """Look up a feature, falling back to a readable default."""
    if feature in FEATURE_DICTIONARY:
        return FEATURE_DICTIONARY[feature]
    return FeatureMeaning(
        label=feature.replace("_", " ").capitalize(),
        adverse_phrase=feature.replace("_", " "),
        favourable_phrase=feature.replace("_", " "),
        higher_is_riskier=True,
        actionability=Actionability.FIXED,
    )


def is_actionable(feature: str) -> bool:
    """True when recourse may be offered for this feature.

    Derived features are excluded: they carry signal, but they are not levers
    the applicant can pull directly.
    """
    meaning = describe(feature)
    return meaning.actionability is not Actionability.FIXED and not meaning.is_derived

"""Synthetic applicant population for thin-file / new-to-credit lending in India.

Why this is synthetic
---------------------
No public dataset contains Account Aggregator-style alternative data (UPI flows,
utility punctuality, telecom tenure) joined to realised loan outcomes for Indian
borrowers. Such data is personal financial information; it is not published, and
fabricating a "real" provenance for it would be dishonest. So the population is
generated here, openly, with its assumptions written down and testable.

The modelling pipeline is additionally validated against a real public credit
dataset (see ``ml/data/real_benchmark.py``) so that results are not an artefact
of assumptions baked into this generator.

Causal structure (this is the important part)
---------------------------------------------
Features do not predict the target by construction. Instead:

    latent repayment capacity  ──┐
                                 ├──►  probability of default  ──►  default_12m
    latent repayment willingness ┘

and the observable features are *noisy consequences* of those two latents. A
model has to recover signal through the noise, exactly as it would in reality.
This avoids the classic synthetic-data failure where a feature is a rescaled
copy of the label and the model scores a meaningless AUC of 0.99.

The deliberate fairness problem
-------------------------------
``gender`` and ``region_tier`` have **zero causal effect on default** in this
generator. Repayment depends only on capacity and willingness. But two realistic
mechanisms make the *observable record* systematically worse for women and rural
applicants:

1. **Data availability bias.** Women and rural applicants are far more likely to
   be new-to-credit, so ``bureau_score`` and ``credit_history_months`` are
   missing for them more often. Absence of evidence becomes evidence of absence.
2. **Declared income depression.** Women's *declared* income is scaled down,
   reflecting documented wage and formalisation gaps, while their true repayment
   capacity is drawn from the same distribution as everyone else's.

A model trained naively on these features will therefore under-approve women and
rural applicants *without any justification in their actual repayment
behaviour*. That is proxy discrimination, and it is the thing the fairness audit
in ``ml/fairness/`` is built to detect and correct. Because we know the ground
truth here, we can prove the mitigation works - which is not possible on a real
dataset where true counterfactual risk is unobservable.

Features deliberately excluded
------------------------------
Signals that are technically predictive but ethically or legally indefensible
are not generated at all: social-media graphs, contact lists, SMS scraping,
app-usage timing, and caste or religion proxies. The RBI Digital Lending
Directions restrict data collection to what is need-based, and the DPDP Act 2023
requires purpose limitation. Excluding them at source is stronger than
collecting them and promising not to use them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# --- Columns the model may never see -------------------------------------
# Held in the dataset only so fairness can be audited across them.
PROTECTED_ATTRIBUTES = ["gender", "region_tier", "age_band"]

# --- Feature families -----------------------------------------------------
# The central experiment of this project compares underwriting that sees only
# the traditional bureau record against underwriting that also sees consented
# alternative data. These lists define that split.
APPLICATION_FEATURES = [
    "age", "education", "employment_type", "monthly_income_declared",
    "loan_amount_requested", "loan_tenure_months", "loan_purpose", "emi_to_income",
]
BUREAU_FEATURES = [
    "is_new_to_credit", "bureau_score", "credit_history_months",
    "num_existing_loans", "enquiries_6m",
]
ALTERNATIVE_FEATURES = [
    # Account Aggregator: banking and UPI
    "upi_txn_count_3m", "upi_inflow_median", "upi_inflow_cv",
    "upi_merchant_diversity", "avg_balance_3m", "days_balance_below_500",
    "salary_regularity",
    # Telecom and utility punctuality
    "mobile_tenure_months", "recharge_regularity", "utility_ontime_ratio",
    "sim_changes_12m",
]
TRADITIONAL_FEATURES = APPLICATION_FEATURES + BUREAU_FEATURES
INCLUSIVE_FEATURES = APPLICATION_FEATURES + BUREAU_FEATURES + ALTERNATIVE_FEATURES
IDENTIFIER_COLUMNS = ["applicant_id"]
TARGET_COLUMN = "default_12m"

EMPLOYMENT_TYPES = ["salaried_formal", "salaried_informal", "self_employed", "gig_worker", "agri"]
LOAN_PURPOSES = [
    "consumer_durable", "education", "medical", "business_working_capital", "two_wheeler",
]
EDUCATION_LEVELS = ["upto_secondary", "higher_secondary", "graduate", "postgraduate"]
REGION_TIERS = ["metro", "tier2", "tier3", "rural"]


@dataclass(frozen=True)
class GeneratorConfig:
    n_applicants: int = 30_000
    seed: int = 20260921
    target_default_rate: float = 0.12

    # Strength of the two bias mechanisms described above. Set both to 0.0 to
    # generate a counterfactual "fair world" population, which the tests use to
    # confirm the audit reports no disparity when none exists.
    availability_bias: float = 1.0
    income_declaration_bias: float = 1.0


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _zscore(x: np.ndarray) -> np.ndarray:
    return (x - np.mean(x)) / (np.std(x) + 1e-9)


def generate_population(config: GeneratorConfig | None = None) -> pd.DataFrame:
    """Generate the applicant population as a tidy DataFrame."""
    cfg = config or GeneratorConfig()
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_applicants

    # ------------------------------------------------------------------
    # 1. Demographics. These are drawn independently of creditworthiness.
    # ------------------------------------------------------------------
    gender = rng.choice(["female", "male"], size=n, p=[0.42, 0.58])
    is_female = gender == "female"
    region_tier = rng.choice(REGION_TIERS, size=n, p=[0.28, 0.24, 0.26, 0.22])
    is_rural = np.isin(region_tier, ["tier3", "rural"])

    # Thin-file / NTC borrowers skew young: first formal credit is typically
    # sought in the twenties and thirties. Median lands near 33.
    age = np.clip(rng.gamma(shape=4.2, scale=3.6, size=n) + 20, 21, 68).round().astype(int)
    education = rng.choice(EDUCATION_LEVELS, size=n, p=[0.30, 0.31, 0.30, 0.09])
    employment_type = rng.choice(EMPLOYMENT_TYPES, size=n, p=[0.22, 0.24, 0.21, 0.19, 0.14])

    # ------------------------------------------------------------------
    # 2. The two latents. Everything causal flows from here.
    #    Neither depends on gender or region - that is the whole point.
    # ------------------------------------------------------------------
    formality = np.select(
        [employment_type == "salaried_formal", employment_type == "salaried_informal",
         employment_type == "self_employed", employment_type == "gig_worker"],
        [1.0, 0.55, 0.45, 0.35], default=0.25,
    )
    capacity = (
        rng.normal(0.0, 1.0, n)
        + 0.45 * _zscore(formality)
        + 0.22 * _zscore(age.astype(float))
    )
    willingness = rng.normal(0.0, 1.0, n) + 0.18 * _zscore(
        np.searchsorted(EDUCATION_LEVELS, education).astype(float)
    )

    # True monthly income is driven by capacity and formality, NOT by gender.
    true_income = np.exp(9.4 + 0.42 * capacity + 0.30 * _zscore(formality) + rng.normal(0, 0.28, n))
    true_income = np.clip(true_income, 6_500, 250_000)

    # ------------------------------------------------------------------
    # 3. Observable banking / UPI behaviour - noisy functions of the latents.
    # ------------------------------------------------------------------
    salary_regularity = np.clip(
        _sigmoid(1.5 * capacity + 1.8 * (formality - 0.5)) + rng.normal(0, 0.19, n), 0, 1
    )
    upi_inflow_cv = np.clip(0.62 - 0.17 * capacity + rng.normal(0, 0.25, n), 0.05, 1.6)
    avg_balance_3m = np.clip(
        true_income * (0.10 + 0.13 * _sigmoid(capacity)) * np.exp(rng.normal(0, 0.42, n)),
        120, None,
    )
    days_balance_below_500 = np.clip(
        rng.binomial(90, np.clip(_sigmoid(-0.95 * capacity - 0.4) * 0.55, 0.01, 0.95)), 0, 90
    )
    upi_txn_count_3m = np.clip(rng.poisson(np.clip(46 + 26 * _sigmoid(capacity), 5, None)), 0, None)
    upi_merchant_diversity = np.clip(
        rng.poisson(np.clip(8 + 7 * _sigmoid(capacity), 1, None)), 0, None
    )
    upi_inflow_median = np.clip(true_income * rng.uniform(0.35, 0.85, n) / 3.0, 200, None)

    # ------------------------------------------------------------------
    # 4. Telecom / utility punctuality - mostly a willingness signal.
    # ------------------------------------------------------------------
    utility_ontime_ratio = np.clip(
        _sigmoid(1.35 * willingness + 0.45) + rng.normal(0, 0.17, n), 0, 1
    )
    recharge_regularity = np.clip(
        _sigmoid(1.15 * willingness + 0.30 * capacity) + rng.normal(0, 0.20, n), 0, 1
    )
    mobile_tenure_months = np.clip(
        rng.gamma(3.1, 13.0, n) * (0.75 + 0.5 * _sigmoid(willingness)), 1, 240
    ).round()
    sim_changes_12m = rng.poisson(np.clip(0.75 - 0.42 * _sigmoid(willingness), 0.03, None))

    # ------------------------------------------------------------------
    # 5. Loan request and resulting EMI burden.
    # ------------------------------------------------------------------
    loan_purpose = rng.choice(LOAN_PURPOSES, size=n, p=[0.28, 0.14, 0.16, 0.24, 0.18])
    loan_tenure_months = rng.choice([6, 12, 18, 24, 36], size=n, p=[0.14, 0.32, 0.20, 0.22, 0.12])
    loan_amount_requested = np.clip(
        true_income * rng.uniform(1.1, 6.5, n) * np.exp(rng.normal(0, 0.22, n)), 5_000, 900_000
    ).round(-2)
    monthly_emi = loan_amount_requested * 1.17 / loan_tenure_months
    # The *true* burden drives repayment. The lender cannot see true income, so
    # the observable feature is computed further below from declared income.
    true_emi_burden = np.clip(monthly_emi / np.maximum(true_income, 1), 0.01, 3.5)

    # ------------------------------------------------------------------
    # 6. Default. Depends ONLY on capacity, willingness and EMI burden.
    #    No gender term. No region term. This is enforced by a test.
    # ------------------------------------------------------------------
    # Default is a function of the two latents and the true EMI burden, plus a
    # large idiosyncratic shock. The shock is deliberately dominant: most real
    # defaults are caused by events no application-time feature can observe -
    # job loss, illness, a failed harvest. Without it the observable features
    # would reconstruct the label almost exactly and the model would report an
    # AUC near 0.99, which no real credit scorecard achieves. Observed features
    # carry signal only through their correlation with the latents.
    logit = (
        -0.95 * capacity
        - 0.72 * willingness
        + 0.85 * _zscore(np.log(true_emi_burden))
        + rng.normal(0, 2.05, n)
    )
    # Shift the intercept so the realised default rate matches the target.
    intercept = np.quantile(logit, 1 - cfg.target_default_rate)
    default_12m = (logit > intercept).astype(int)

    # ------------------------------------------------------------------
    # 7. Bias mechanism 1: who is new-to-credit (bureau data missing).
    #    Women and rural applicants are more often NTC, for reasons that have
    #    nothing to do with how they repay.
    # ------------------------------------------------------------------
    ntc_logit = (
        -0.35
        - 0.55 * capacity
        + cfg.availability_bias * 0.95 * is_female.astype(float)
        + cfg.availability_bias * 0.80 * is_rural.astype(float)
        + rng.normal(0, 0.45, n)
    )
    is_ntc = rng.random(n) < _sigmoid(ntc_logit)

    bureau_score = np.clip(
        620 + 62 * capacity + 30 * willingness + rng.normal(0, 62, n), 300, 900
    ).round()
    credit_history_months = np.clip(rng.gamma(2.6, 17.0, n), 0, 340).round()
    num_existing_loans = rng.poisson(np.clip(1.15 + 0.55 * _sigmoid(capacity), 0.05, None))
    enquiries_6m = rng.poisson(np.clip(1.5 - 0.45 * _sigmoid(capacity), 0.05, None))

    # New-to-credit applicants genuinely have no bureau record.
    bureau_score_obs = np.where(is_ntc, np.nan, bureau_score)
    credit_history_obs = np.where(is_ntc, np.nan, credit_history_months)
    existing_loans_obs = np.where(is_ntc, 0, num_existing_loans)

    # ------------------------------------------------------------------
    # 8. Bias mechanism 2: declared income is depressed for women, while
    #    true repayment capacity is identical.
    # ------------------------------------------------------------------
    declaration_factor = np.where(
        is_female, 1.0 - cfg.income_declaration_bias * 0.18, 1.0
    ) * np.exp(rng.normal(0, 0.12, n))
    monthly_income_declared = np.clip(true_income * declaration_factor, 5_000, None).round(-2)

    age_band = pd.cut(age, bins=[20, 30, 40, 50, 70], labels=["21-30", "31-40", "41-50", "51+"])

    frame = pd.DataFrame(
        {
            "applicant_id": [f"APP{i:07d}" for i in range(n)],
            # --- protected: audit only, never a model input ---
            "gender": gender,
            "region_tier": region_tier,
            "age_band": age_band,
            # --- application ---
            "age": age,
            "education": education,
            "employment_type": employment_type,
            "monthly_income_declared": monthly_income_declared,
            "loan_amount_requested": loan_amount_requested,
            "loan_tenure_months": loan_tenure_months,
            "loan_purpose": loan_purpose,
            # What the underwriter can actually compute: EMI against *declared*
            # income. For women this is inflated relative to the true burden,
            # because declared income is depressed - one of the two seeded
            # bias mechanisms.
            "emi_to_income": np.clip(
                monthly_emi / np.maximum(monthly_income_declared, 1), 0.01, 5.0
            ).round(4),
            # --- bureau (absent for new-to-credit) ---
            "is_new_to_credit": is_ntc.astype(int),
            "bureau_score": bureau_score_obs,
            "credit_history_months": credit_history_obs,
            "num_existing_loans": existing_loans_obs,
            "enquiries_6m": enquiries_6m,
            # --- Account Aggregator: banking and UPI ---
            "upi_txn_count_3m": upi_txn_count_3m,
            "upi_inflow_median": upi_inflow_median.round(2),
            "upi_inflow_cv": upi_inflow_cv.round(4),
            "upi_merchant_diversity": upi_merchant_diversity,
            "avg_balance_3m": avg_balance_3m.round(2),
            "days_balance_below_500": days_balance_below_500,
            "salary_regularity": salary_regularity.round(4),
            # --- telecom and utility ---
            "mobile_tenure_months": mobile_tenure_months,
            "recharge_regularity": recharge_regularity.round(4),
            "utility_ontime_ratio": utility_ontime_ratio.round(4),
            "sim_changes_12m": sim_changes_12m,
            # --- outcome ---
            TARGET_COLUMN: default_12m,
        }
    )
    return frame


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Columns the model is permitted to train on.

    Protected attributes and identifiers are excluded here rather than dropped
    later, so that it is structurally impossible for them to reach the model.
    """
    banned = set(PROTECTED_ATTRIBUTES) | set(IDENTIFIER_COLUMNS) | {TARGET_COLUMN}
    return [c for c in frame.columns if c not in banned]

# Data

Three kinds of thing live here, and they are not equivalent.

## `policy/` — committed, and read at runtime

The regulatory corpus: 37 provisions across five Indian instruments, embedded
into pgvector and cited on every decision. **These are labelled paraphrases, not
verbatim legal text** — see [`policy/README.md`](policy/README.md) for why that
was the deliberate choice rather than a shortcut.

## `sample_applications.csv` — committed, for reading

A 320-row slice of the generated population, so the shape of the data is
visible without running anything. It takes 40 rows from each combination of
gender, new-to-credit status and realised outcome, which guarantees every case
appears rather than leaving the rare ones to chance.

**Two rates in this file are therefore not the population's.** Sampling evenly
across the outcome makes the default rate here 50%, against 12% in the full
population; and evenly across new-to-credit status makes that 50% here against
59%. Read the file for the *shape* of the data — which columns exist, what they
contain, where the gaps are. For rates, run `python scripts/train.py` and read
`data/processed/applications.csv`, or `eval/reports/inclusion_experiment.json`.

What to look at in it:

- **`bureau_score` is empty for a majority of rows.** That is the project, not a
  data-quality problem. Those applicants are new-to-credit and genuinely have no
  bureau record; the model consumes that absence as `NaN` rather than having a
  median imputed into it.
- **`gender`, `region_tier` and `age_band` are present but are never model
  inputs.** They exist so fairness can be measured. Exclusion is enforced in
  `ml/data/generator.feature_columns` and asserted by a test.
- **The alternative-data columns** — `upi_*`, `avg_balance_3m`,
  `days_balance_below_500`, `utility_ontime_ratio`, `recharge_regularity`,
  `mobile_tenure_months` — are what a thin-file applicant is assessed on instead.

## `raw/` and `processed/` — generated, git-ignored

Build outputs, not source. `python scripts/train.py` writes the full 30,000-row
population to `processed/applications.csv` from a fixed seed, so it is
reproducible rather than stored.

The population is synthetic, and openly so: no public dataset joins Account
Aggregator-style alternative data to realised loan outcomes for Indian
borrowers. The generator's causal structure and its two deliberate bias
mechanisms are documented in `ml/data/generator.py`, and the modelling pipeline
is separately validated against two real public credit datasets — see
`scripts/validate_on_real_data.py`.

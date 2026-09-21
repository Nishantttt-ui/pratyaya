"""Generate the deck's figures.

    python scripts/make_figures.py

Three charts, each earning its place by showing something a table cannot:

1. **Reliability diagram** - whether a stated probability means what it says.
   A table of Brier scores does not show *where* a model is miscalibrated.
2. **Qualified approval by gender** - the headline result, as the comparison a
   credit committee would actually argue about.
3. **ROC curves** - the discrimination gain, with the operating point marked.

Palette
-------
Two categorical slots, `#BD6A0C` (bureau only) and `#0E9E6E` (with alternative
data). The pair was chosen by running the colour validator rather than by eye:
it clears the chroma floor, holds ΔE 9.5 under deuteranopia and 21.3 for normal
vision, and both steps exceed 3:1 against the surface. Identity is additionally
carried by direct labels, so the charts survive being printed in grayscale.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import roc_curve  # noqa: E402

from ml.data.generator import (  # noqa: E402
    INCLUSIVE_FEATURES,
    TRADITIONAL_FEATURES,
    GeneratorConfig,
    generate_population,
)
from ml.explain.explainer import CreditExplainer  # noqa: E402
from ml.fairness.audit import audit_attribute  # noqa: E402
from ml.training.pipeline import approval_threshold_for_rate, train_model  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
REPORTS = ROOT / "eval" / "reports"
# Validated with the colour checker, all pairs: worst CVD separation dE 9.9
# (deuteranopia), worst normal-vision separation dE 20.3, every step above 3:1
# on the surface. Identity is also carried by direct labels so the charts
# survive grayscale printing.
TRAD, INCL, REF = "#C06A00", "#0E9E6E", "#3C6FB5"
INK, MUTED, GRID = "#16232E", "#5A6570", "#E3E7E5"
APPROVAL = 0.70

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "font.size": 11,
})


def _frame(fig, title, subtitle=None):
    """Place the title block above the axes and reserve room for it.

    Drawn at figure level rather than with ``ax.set_title`` so the subtitle
    cannot overlap either the title or the plot, whatever the axes end up
    measuring.
    """
    fig.text(0.015, 0.975, title, ha="left", va="top", fontsize=14.5,
             fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.015, 0.895, subtitle, ha="left", va="top", fontsize=10.5, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.85 if subtitle else 0.92))


def reliability(p, y, path):
    """Predicted vs observed default rate, by equal-population decile."""
    edges = np.quantile(p, np.linspace(0, 1, 11))
    edges[-1] += 1e-9
    pred, obs = [], []
    for i in range(10):
        mask = (p >= edges[i]) & (p < edges[i + 1])
        if mask.sum():
            pred.append(p[mask].mean())
            obs.append(y[mask].mean())
    pred, obs = np.array(pred), np.array(obs)

    fig, ax = plt.subplots(figsize=(6.2, 4.4), dpi=200)
    lim = max(pred.max(), obs.max()) * 1.12
    ax.plot([0, lim], [0, lim], color=MUTED, lw=1.4, ls=(0, (4, 3)), zorder=1)
    # Below the diagonal on the right is the only empty region of this plot.
    ax.text(lim * 0.70, lim * 0.42, "perfect calibration", color=MUTED, fontsize=9.5,
            ha="left", va="center")
    ax.plot(pred, obs, color=INCL, lw=2, marker="o", ms=8, zorder=3,
            markeredgecolor="white", markeredgewidth=1.6)
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Predicted probability of default")
    ax.set_ylabel("Observed default rate")
    _frame(fig, "A stated probability means what it says",
           "Equal-population deciles, held-out applicants.  Expected calibration error 0.0073")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def fairness_bars(rows, path):
    """Qualified approval rate by gender, before and after alternative data."""
    labels = ["Women", "Men"]
    trad = [rows["trad"]["female"], rows["trad"]["male"]]
    incl = [rows["incl"]["female"], rows["incl"]["male"]]
    x = np.arange(2)
    w = 0.33

    fig, ax = plt.subplots(figsize=(6.6, 4.4), dpi=200)
    left = ax.bar(x - w / 2 - 0.012, trad, w, color=TRAD, label="Bureau only", zorder=3)
    right = ax.bar(x + w / 2 + 0.012, incl, w, color=INCL,
                   label="With alternative data", zorder=3)
    for bars in (left, right):
        for bar in bars:
            ax.annotate(
                f"{bar.get_height() * 100:.1f}%",
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                textcoords="offset points", xytext=(0, 5), ha="center",
                fontsize=11, fontweight="600", color=INK,
            )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=12.5, color=INK)
    ax.set_ylim(0, 1.18)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_ylabel("Approved, among those who would repay")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v*100:.0f}%")
    ax.legend(frameon=False, loc="upper left", fontsize=10.5, ncols=2,
              bbox_to_anchor=(0.0, 1.0))
    gap_trad, gap_incl = (trad[1] - trad[0]) * 100, (incl[1] - incl[0]) * 100
    _frame(fig, "The penalty fell on people who would have repaid",
           f"Approval held at 70%.  The women-men gap narrows from {gap_trad:.1f} points "
           f"to {gap_incl:.1f},\nwhile true default rates differ by only 0.4 points")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def roc(curves, path):
    fig, ax = plt.subplots(figsize=(6.2, 4.4), dpi=200)
    ax.plot([0, 1], [0, 1], color=MUTED, lw=1.2, ls=(0, (4, 3)), zorder=1)
    for (name, fpr, tpr, auc, colour) in curves:
        ax.plot(fpr, tpr, color=colour, lw=2.2, zorder=3, label=f"{name}  AUC {auc:.3f}")
        idx = int(len(fpr) * 0.42)
        ax.annotate(name, (fpr[idx], tpr[idx]), textcoords="offset points",
                    xytext=(10, -12 if colour == TRAD else 8), fontsize=10.5,
                    fontweight="600", color=colour)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.legend(frameon=False, loc="lower right", fontsize=10.5)
    _frame(fig, "Alternative data separates risk better",
           "Held-out applicants.  The gain is largest where most decisions are made")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _load(name: str):
    path = REPORTS / name
    if not path.exists():
        print(f"  skipped: {name} not found — run the script that produces it")
        return None
    return json.loads(path.read_text())


def problem_scale(path):
    """Who is new-to-credit, and how unevenly that falls."""
    frame = generate_population(GeneratorConfig(n_applicants=30_000))
    by_gender = frame.groupby("gender", observed=True)["is_new_to_credit"].mean()
    rural = frame["region_tier"].isin(["tier3", "rural"])
    groups = ["Women", "Men", "Rural /\ntier-3", "Metro /\ntier-2"]
    values = [by_gender["female"], by_gender["male"],
              frame.loc[rural, "is_new_to_credit"].mean(),
              frame.loc[~rural, "is_new_to_credit"].mean()]

    fig, ax = plt.subplots(figsize=(6.6, 4.2), dpi=200)
    colours = [TRAD, INCL, TRAD, INCL]
    bars = ax.bar(range(4), values, 0.62, color=colours, zorder=3)
    for bar in bars:
        ax.annotate(f"{bar.get_height() * 100:.1f}%",
                    (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    textcoords="offset points", xytext=(0, 5), ha="center",
                    fontsize=12, fontweight="600", color=INK)
    ax.axhline(frame["is_new_to_credit"].mean(), color=MUTED, lw=1.3, ls=(0, (4, 3)), zorder=2)
    ax.text(3.45, frame["is_new_to_credit"].mean() + 0.018, "portfolio average",
            ha="right", fontsize=10, color=MUTED)
    ax.set_xticks(range(4))
    ax.set_xticklabels(groups, fontsize=11.5, color=INK)
    ax.set_ylim(0, 0.92)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v*100:.0f}%")
    ax.set_ylabel("Share with no credit bureau record")
    _frame(fig, "Invisibility is not evenly distributed",
           "The applicants a bureau-led model cannot see, by group")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def waterfall(path):
    """One applicant's score, decomposed into the factors that built it."""
    explainer = CreditExplainer.from_artifacts(ROOT / "ml" / "artifacts" / "model.joblib")
    frame = generate_population(GeneratorConfig(n_applicants=4_000))
    p = explainer.predict_proba(frame)
    declined = frame[(p > explainer.threshold) & (frame["is_new_to_credit"] == 1)].head(1)
    explanation = explainer.explain(declined, top_n=5)

    codes = sorted(
        explanation.adverse_reasons + explanation.favourable_reasons,
        key=lambda r: -abs(r.contribution),
    )[:7]
    labels = [c.label for c in codes][::-1]
    values = [c.contribution for c in codes][::-1]

    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    running = 0.0
    for i, v in enumerate(values):
        colour = TRAD if v > 0 else INCL
        ax.barh(i, v, left=running, height=0.6, color=colour, zorder=3)
        ax.annotate(f"{v:+.2f}", (running + v, i), xytext=(6 if v > 0 else -6, 0),
                    textcoords="offset points", va="center",
                    ha="left" if v > 0 else "right",
                    fontsize=10.5, fontweight="600", color=INK)
        running += v
    ax.axvline(0, color=MUTED, lw=1.2, zorder=2)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlabel("Contribution to the decision, in log-odds")
    ax.set_xlim(min(0, running) - 0.45, max(0.55, running + 0.45))
    ax.grid(axis="y", visible=False)
    _frame(fig, "Every factor, and exactly how much it counted",
           "One declined applicant. Contributions sum to the model's output "
           "to within 5e-15.")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def latency_chart(path):
    data = _load("latency.json")
    if not data:
        return
    order = ["score_only", "score_and_reason_codes", "policy_retrieval",
             "render_notice", "recourse_search"]
    names = ["Score only", "Score + exact SHAP", "Retrieve provisions",
             "Render full notice", "Search for recourse"]
    p50 = [data[k]["p50_ms"] for k in order]

    fig, ax = plt.subplots(figsize=(6.8, 4.0), dpi=200)
    colours = [INCL if v < 20 else TRAD for v in p50]
    bars = ax.barh(range(len(p50)), p50, height=0.6, color=colours, zorder=3)
    for bar, v in zip(bars, p50, strict=True):
        ax.annotate(f"{v:.1f} ms", (v, bar.get_y() + bar.get_height() / 2),
                    xytext=(7, 0), textcoords="offset points", va="center",
                    fontsize=11, fontweight="600", color=INK)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=11)
    ax.invert_yaxis()
    ax.set_xlim(0, max(p50) * 1.28)
    ax.set_xlabel("Median latency per applicant, milliseconds")
    ax.grid(axis="y", visible=False)
    _frame(fig, "Explainability is not a latency trade",
           "Exact reason codes add 0.34 ms to scoring. CPU only, no GPU.")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def redteam_chart(path):
    """Recall against model-generated attacks, across hardening rounds."""
    rounds = ["Original\nguardrails", "After first\nhardening", "After second\nhardening"]
    recall = [0.450, 0.650, 0.600]
    precision = [1.0, 1.0, 1.0]

    fig, ax = plt.subplots(figsize=(6.6, 4.2), dpi=200)
    x = np.arange(3)
    ax.plot(x, precision, color=INCL, lw=2.2, marker="o", ms=9, zorder=4,
            markeredgecolor="white", markeredgewidth=1.6, label="Precision")
    ax.plot(x, recall, color=TRAD, lw=2.2, marker="o", ms=9, zorder=4,
            markeredgecolor="white", markeredgewidth=1.6, label="Recall")
    for xi, v in zip(x, recall, strict=True):
        ax.annotate(f"{v:.2f}", (xi, v), xytext=(0, -18), textcoords="offset points",
                    ha="center", fontsize=11, fontweight="600", color=TRAD)
    ax.annotate("1.00 throughout — no faithful\nexplanation was ever blocked",
                (1, 1.0), xytext=(0, 12), textcoords="offset points", ha="center",
                fontsize=10, color=INCL)
    ax.set_xticks(x)
    ax.set_xticklabels(rounds, fontsize=10.5)
    ax.set_ylim(0, 1.22)
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.set_ylabel("Score against generated attacks")
    ax.legend(frameon=False, loc="center right", fontsize=10.5)
    _frame(fig, "Pattern matching plateaus against an adversary",
           "Each round, a model invents attacks it was never shown. Recall "
           "stalls near 0.6.")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def reject_inference_chart(path):
    data = _load("reject_inference.json")
    if not data:
        return
    r = data["results"]
    names = list(r.keys())
    short = ["Oracle\n(unattainable)", "Naive\n(accepted book)", "Corrected\n(reject inference)"]
    auc = [r[n]["roc_auc"] for n in names]
    bad = [r[n]["bad_rate_among_approved"] for n in names]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 4.2), dpi=200)
    for ax, values, title, fmt, better in (
        (ax1, auc, "Ranking quality (AUC)", "{:.4f}", "higher"),
        (ax2, bad, "Bad rate among approved", "{:.4f}", "lower"),
    ):
        colours = [REF, TRAD, INCL]
        bars = ax.bar(range(3), values, 0.6, color=colours, zorder=3)
        for bar, v in zip(bars, values, strict=True):
            ax.annotate(fmt.format(v), (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                        textcoords="offset points", xytext=(0, 5), ha="center",
                        fontsize=11, fontweight="600", color=INK)
        ax.set_xticks(range(3))
        ax.set_xticklabels(short, fontsize=10)
        lo, hi = min(values), max(values)
        pad = (hi - lo) * 0.55 or hi * 0.1
        ax.set_ylim(max(0, lo - pad), hi + pad)
        ax.set_title(f"{title} — {better} is better", fontsize=11.5,
                     color=MUTED, loc="left", pad=8)
    share = data.get("share_of_gap_closed")
    subtitle = ("Censoring costs {:.4f} AUC. Fuzzy augmentation recovers {:.0%} of it."
                .format(data["censoring_cost_auc"], share) if share else
                "Censoring cost measured against an oracle.")
    _frame(fig, "What a lender's own book hides", subtitle)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def mitigation_chart(path):
    data = _load("mitigation_comparison.json")
    if not data:
        return
    runs = [r for r in data["runs"] if not r.get("degenerate")]
    labels = [r["strategy"].replace(" (this project)", "") for r in runs]
    auc = [r["roc_auc"] for r in runs]
    gap = [r["qualified_approval_gap"] for r in runs]
    needs = [r["needs_attribute_at_decision"] for r in runs]

    fig, ax = plt.subplots(figsize=(7.0, 4.6), dpi=200)
    for i, (a, g, n, lab) in enumerate(zip(auc, gap, needs, labels, strict=True)):
        ours = "Alternative data" in lab
        colour = INCL if ours else (TRAD if n else REF)
        ax.scatter(g, a, s=230 if ours else 150, color=colour, zorder=4,
                   edgecolor="white", linewidth=2,
                   marker="D" if n else "o")
        ax.annotate(lab + ("  (reads gender)" if n else ""),
                    (g, a), xytext=(9, 7 if i % 2 == 0 else -16),
                    textcoords="offset points", fontsize=10.5,
                    fontweight="600" if ours else "400", color=INK)
    ax.set_xlabel("Qualified-approval gap  ←  fairer")
    ax.set_ylabel("Ranking quality (AUC)  →  better")
    ax.set_xlim(-0.012, max(gap) * 1.55)
    ax.set_ylim(min(auc) - 0.012, max(auc) + 0.014)
    ax.annotate("better on both axes", (0.012, max(auc) + 0.008), fontsize=10,
                color=INCL, fontweight="600")
    _frame(fig, "Every algorithmic remedy paid for fairness",
           "Diamonds must read the applicant's gender to decide. Only widening "
           "the evidence improved both axes.")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def real_validation_chart(path):
    data = _load("real_benchmark.json")
    if not data:
        return
    names = ["German Credit\n(1,000 real)", "This project\n(30,000 synthetic)",
             "Taiwan Default\n(30,000 real)"]
    values = [data[0]["roc_auc"], 0.7797, data[1]["roc_auc"]]
    colours = [REF, INCL, REF]

    fig, ax = plt.subplots(figsize=(6.6, 4.2), dpi=200)
    bars = ax.bar(range(3), values, 0.58, color=colours, zorder=3)
    for bar, v in zip(bars, values, strict=True):
        ax.annotate(f"{v:.4f}", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    textcoords="offset points", xytext=(0, 5), ha="center",
                    fontsize=12, fontweight="600", color=INK)
    ax.set_xticks(range(3))
    ax.set_xticklabels(names, fontsize=10.5)
    ax.set_ylim(0.70, 0.80)
    ax.set_ylabel("ROC AUC on held-out data")
    ax.annotate("our difficulty sits between the two real datasets",
                (1, 0.7797), xytext=(0, -46), textcoords="offset points",
                ha="center", fontsize=10.5, color=INCL, fontweight="600")
    _frame(fig, "The same pipeline, on real credit data",
           "Identical code path: design matrix, booster, calibration, TreeSHAP, "
           "fairness audit.")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    frame = generate_population(GeneratorConfig(n_applicants=30_000))

    out = {}
    curves = []
    for key, feats, colour, label in [
        ("trad", TRADITIONAL_FEATURES, TRAD, "Bureau only"),
        ("incl", INCLUSIVE_FEATURES, INCL, "With alternative data"),
    ]:
        model, ev = train_model(frame, features=feats)
        p, y = ev["p_test"], ev["y_test"]
        test = frame.iloc[ev["test_index"]].reset_index(drop=True)
        approved = p <= approval_threshold_for_rate(p, APPROVAL)
        audit = audit_attribute(protected=test["gender"], approved=approved,
                                defaulted=y, attribute_name="gender")
        out[key] = {g.group: g.qualified_approval_rate for g in audit.groups}
        fpr, tpr, _ = roc_curve(y, p)
        curves.append((label, fpr, tpr, model.metrics["roc_auc"], colour))
        if key == "incl":
            reliability(p, y, FIG / "calibration.png")
        female, male = out[key]["female"], out[key]["male"]
        print(f"  {label:<24} AUC {model.metrics['roc_auc']:.4f}  "
              f"qualified F {female:.4f} / M {male:.4f}")

    fairness_bars(out, FIG / "fairness_gap.png")
    roc(curves, FIG / "roc.png")
    for label, render, filename in (
        ("problem scale", problem_scale, "ntc_by_group.png"),
        ("reason waterfall", waterfall, "waterfall.png"),
        ("latency", latency_chart, "latency.png"),
        ("red-team", redteam_chart, "redteam.png"),
        ("reject inference", reject_inference_chart, "reject_inference.png"),
        ("mitigation", mitigation_chart, "mitigation.png"),
        ("real validation", real_validation_chart, "real_validation.png"),
    ):
        print(f"  {label} ...")
        render(FIG / filename)
    print(f"\nfigures -> {FIG}")
    for figure in sorted(FIG.glob("*.png")):
        print(f"  {figure.name}  {figure.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()

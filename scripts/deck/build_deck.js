const pptxgen = require("pptxgenjs");
const path = require("path");
const FIG = path.join(__dirname, "..", "..", "docs", "figures");

// ---- palette: deep forest green (trust, money) dominant, ink navy support,
// ---- warm amber reserved exclusively for the disparity/penalty numbers.
const INK = "16232E", GREEN = "0E6B4F", GREEN_DEEP = "0A5741";
const GREEN_PALE = "E3F0E9", GREEN_TEXT = "8FD7B8", GREEN_CARD = "12594250";
const AMBER = "B2701A", AMBER_PALE = "FBEFDC", RED = "A3302C";
const WHITE = "FFFFFF", NEUTRAL = "F1F4F2", MUTED = "5A6570", BORDER = "DEE4E0";
const INK_CARD = "22333F", INK_TEXT = "C2CDD6";

const HEAD = "Cambria", BODY = "Calibri";
const M = 0.55, W = 12.2;            // margin, usable width
const shadow = () => ({ type: "outer", color: "9AA5AE", blur: 8, offset: 2, angle: 90, opacity: 0.22 });

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";          // 13.3 x 7.5
pres.author = "Swaraj";
pres.title = "Pratyaya - Explainable Credit Risk";

// ---------- helpers ----------
function title(s, text, y = 0.5, color = INK, size = 34) {
  s.addText(text, { x: M, y, w: W, h: 1.15, isTextBox: true, margin: 0,
    fontFace: HEAD, fontSize: size, bold: false, color, valign: "top" });
}
function lede(s, text, y, color = MUTED, w = W, size = 14.5) {
  s.addText(text, { x: M, y, w, h: 0.75, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: size, color, lineSpacing: 20, valign: "top" });
}
// a tinted rounded card; returns nothing, caller places text
function card(s, x, y, w, h, fill, line) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.09,
    fill: { color: fill }, line: line ? { color: line, width: 0.75 } : { type: "none" },
    shadow: shadow() });
}
function badge(s, x, y, label, fill, txt) {
  s.addShape(pres.ShapeType.ellipse, { x, y, w: 0.42, h: 0.42, fill: { color: fill }, line: { type: "none" } });
  s.addText(label, { x, y, w: 0.42, h: 0.42, isTextBox: true, margin: 0, align: "center", valign: "middle",
    fontFace: BODY, fontSize: 13, bold: true, color: txt });
}
// three/four/five column card row with heading + body
function cardRow(s, y, h, items, opts = {}) {
  const n = items.length, gap = 0.3;
  const cw = (W - gap * (n - 1)) / n;
  items.forEach((it, i) => {
    const x = M + i * (cw + gap);
    card(s, x, y, cw, h, it.fill || WHITE, it.line || BORDER);
    let cy = y + 0.28;
    if (it.stat) {
      s.addText(it.stat, { x: x + 0.28, y: cy, w: cw - 0.56, h: 0.8, isTextBox: true, margin: 0,
        fontFace: HEAD, fontSize: it.statSize || 40, bold: true, color: it.statColor || GREEN, valign: "top" });
      cy += 0.86;
    }
    if (it.num) { badge(s, x + 0.28, cy, it.num, it.numFill || GREEN, WHITE); cy += 0.6; }
    s.addText(it.h, { x: x + 0.28, y: cy, w: cw - 0.56, h: opts.headH || 0.5, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: opts.headSize || 14.5, bold: true, color: it.headColor || INK, valign: "top" });
    s.addText(it.b, { x: x + 0.28, y: cy + (opts.headH || 0.5), w: cw - 0.56, h: h - (cy - y) - (opts.headH || 0.5) - 0.2,
      isTextBox: true, margin: 0, fontFace: BODY, fontSize: opts.bodySize || 12, color: it.bodyColor || MUTED,
      lineSpacing: 16, valign: "top" });
  });
}
// --- diagram primitives ---------------------------------------------------
// Drawn as native shapes rather than imported images so they stay crisp at any
// zoom and remain editable in PowerPoint.
function node(s, x, y, w, h, title, sub, opts = {}) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.07,
    fill: { color: opts.fill || WHITE },
    line: { color: opts.line || BORDER, width: opts.lw || 0.75 },
    shadow: opts.flat ? undefined : shadow(),
  });
  const pad = 0.16;
  const reserve = opts.reserveRight || 0;   // room for a corner badge
  s.addText(title, {
    x: x + pad, y: y + (sub ? 0.06 : 0), w: w - pad * 2 - reserve, h: sub ? 0.28 : h,
    isTextBox: true, margin: 0, valign: sub ? "top" : "middle",
    align: opts.align || "left",
    fontFace: BODY, fontSize: opts.titleSize || 12.5, bold: true,
    color: opts.titleColor || INK,
  });
  if (sub) {
    s.addText(sub, {
      x: x + pad, y: y + 0.33, w: w - pad * 2, h: h - 0.38, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: opts.subSize || 10.5, color: opts.subColor || MUTED,
      lineSpacing: 12, valign: "top",
    });
  }
}

function arrow(s, x1, y1, x2, y2, color = "9AA7AE", width = 1.5) {
  s.addShape(pres.ShapeType.line, {
    x: Math.min(x1, x2), y: Math.min(y1, y2),
    w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    line: { color, width, endArrowType: "triangle" },
    flipH: x2 < x1, flipV: y2 < y1,
  });
}

function bandLabel(s, x, y, w, text, color) {
  s.addText(text, {
    x, y, w, h: 0.26, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 9.5, bold: true, color,
    charSpacing: 1.6,
  });
}

// A slide whose argument is a chart: heading, one line of context, the figure
// sized to its true aspect so it cannot distort, and a conclusion beneath.
function chartSlide(file, aspect, heading, lede_, conclusion, opts = {}) {
  const sl = pres.addSlide();
  sl.background = { color: opts.bg || WHITE };
  title(sl, heading, 0.45, INK, 30);
  lede(sl, lede_, 0.98, MUTED, 11.9, 12.5);
  const bottom = conclusion ? 5.62 : 6.7;
  const maxH = bottom - 1.62, maxW = opts.maxW || 9.4;
  let h = maxH, w = h * aspect;
  if (w > maxW) { w = maxW; h = w / aspect; }
  sl.addImage({ path: path.join(FIG, file), x: M + (W - w) / 2, y: 1.62, w, h });
  if (conclusion) callout(sl, bottom + 0.12, conclusion, opts.calloutFill || GREEN_PALE,
                          opts.calloutBar || GREEN, INK, opts.calloutH || 0.86);
  sl.addNotes(opts.notes || conclusion || lede_);
  return sl;
}

function footnote(s, text, color = "8A949C") {
  s.addText(text, { x: M, y: 6.92, w: W, h: 0.33, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 10.5, italic: true, color, valign: "top" });
}
function callout(s, y, text, fill, bar, textColor = INK, h = 0.82) {
  card(s, M, y, W, h, fill, null);
  s.addText(text, { x: M + 0.3, y: y + 0.13, w: W - 0.6, h: h - 0.26, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 12.5, color: textColor, lineSpacing: 17, valign: "middle" });
}

// ================= 1. COVER =================
let s = pres.addSlide();
s.background = { color: INK };
s.addText("SYNCHRONY HACKATHON  ·  PROBLEM STATEMENT 2", { x: M, y: 0.62, w: W, h: 0.3, isTextBox: true, margin: 0,
  fontFace: BODY, fontSize: 11.5, bold: true, color: GREEN_TEXT, charSpacing: 2.5 });
s.addText("Pratyaya", { x: M, y: 1.5, w: W, h: 1.35, isTextBox: true, margin: 0,
  fontFace: HEAD, fontSize: 64, color: WHITE, valign: "top" });
s.addText("Explainable, fairness-audited credit assessment for thin-file and new-to-credit borrowers",
  { x: M, y: 2.95, w: 9.4, h: 0.95, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 19, color: INK_TEXT, lineSpacing: 27 });
["Deterministic decisions", "Cited reasons", "Actionable recourse"].forEach((t, i) => {
  const w = 2.6, x = M + i * (w + 0.22);
  s.addShape(pres.ShapeType.roundRect, { x, y: 4.15, w, h: 0.5, rectRadius: 0.25, fill: { color: INK_CARD }, line: { type: "none" } });
  s.addText(t, { x, y: 4.15, w, h: 0.5, isTextBox: true, margin: 0, align: "center", valign: "middle",
    fontFace: BODY, fontSize: 12, bold: true, color: GREEN_TEXT });
});
s.addShape(pres.ShapeType.line, { x: M, y: 5.35, w: 4.2, h: 0, line: { color: "3A4B57", width: 1 } });
s.addText([
  { text: "Pratyaya", options: { italic: true, color: WHITE } },
  { text: " (प्रत्यय) — Sanskrit for trust. The word ", options: {} },
  { text: "credit", options: { italic: true, color: WHITE } },
  { text: " descends from Latin ", options: {} },
  { text: "credere", options: { italic: true, color: WHITE } },
  { text: ", to believe.\nBoth name the same thing: a lender's belief that a borrower will repay.", options: {} },
], { x: M, y: 5.6, w: 10.5, h: 0.9, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, color: "93A0AA", lineSpacing: 19 });
s.addNotes("Open here. The name is the argument in miniature: credit is belief, and for a thin-file borrower the problem is not that the belief is misplaced, it is that nobody has ever looked.");

// ================= 2. PROBLEM =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "Underwriting reads a file that does not exist");
lede(s, "An applicant who has never borrowed formally has no bureau record. They are declined not for being risky, but for being unobserved — and because they are declined, they never generate the history that would let them be seen next time.", 1.45, MUTED, 11.6);
cardRow(s, 2.7, 3.05, [
  { stat: "59%", h: "of the portfolio is new-to-credit", b: "No bureau score, no credit history length. Nothing for a traditional model to read." },
  { stat: "70.6 / 51.0", statSize: 32, statColor: AMBER, h: "women vs men, new-to-credit", b: "Absence of evidence is not evenly distributed, so a bureau-led model inherits the skew wholesale." },
  { stat: "67.5 / 51.8", statSize: 32, statColor: AMBER, h: "rural vs metro, new-to-credit", b: "The same mechanism on a second axis. The exclusion is self-sealing." },
]);
footnote(s, "Figures from the project's reference population of 30,000 applicants");
s.addNotes("The key word is unobserved. This is a measurement failure that looks like a risk judgement.");

chartSlide("ntc_by_group.png", 1.582,
  "The people a bureau-led model cannot see",
  "Share of applicants with no credit bureau record at all, by group. Nothing here is about repayment \u2014 it is about visibility.",
  "Women are new-to-credit 70.6% of the time against 51.0% for men; rural and tier-3 applicants 67.5% against 51.8% in metros. A model leaning on the bureau record inherits that gap wholesale, before it has learned anything about risk.",
  { maxW: 8.4 });

// ================= 3. INSIGHT =================
s = pres.addSlide(); s.background = { color: GREEN };
s.addText("THE INSIGHT THE WHOLE BUILD RESTS ON", { x: M, y: 1.35, w: W, h: 0.3, isTextBox: true, margin: 0,
  fontFace: BODY, fontSize: 11.5, bold: true, color: "A9E3C6", charSpacing: 2.5 });
s.addText("The bias is not in the algorithm.\nIt is in the evidence.", { x: M, y: 2.0, w: 11.4, h: 1.9, isTextBox: true, margin: 0,
  fontFace: HEAD, fontSize: 46, color: WHITE, lineSpacing: 56, valign: "top" });
s.addText("Women and rural applicants in this population repay at the same rate as everyone else — 11.8% against 12.2%. What differs is how much of their financial life the lender can see. Fix the evidence and you fix the disparity, without ever touching the decision rule.",
  { x: M, y: 4.25, w: 11.4, h: 1.5, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 17, color: "D3EFE1", lineSpacing: 26 });
s.addNotes("This reframes the whole problem. Most fairness work treats bias as a property of the model and reaches for a constrained optimiser. Here the model is behaving reasonably on the data it has. The data is the problem.");

// ================= 4. THESIS =================
s = pres.addSlide(); s.background = { color: WHITE };
s.addText("THE ARCHITECTURAL DECISION", { x: M, y: 0.5, w: W, h: 0.28, isTextBox: true, margin: 0,
  fontFace: BODY, fontSize: 11, bold: true, color: GREEN, charSpacing: 2.2 });
title(s, "The language model sits on the explanation path, never the decision path", 0.82, INK, 30);
cardRow(s, 2.35, 2.55, [
  { num: "1", h: "What decides", headColor: GREEN, fill: GREEN_PALE, line: null,
    b: "A calibrated gradient-boosted model. Deterministic, auditable, reproducible. Its output is final before any language model is called." },
  { num: "2", numFill: AMBER, h: "What narrates", headColor: AMBER, fill: AMBER_PALE, line: null,
    b: "A language model rewrites the finished notice more warmly, grounded in retrieved regulation, and only if its output passes a guardrail." },
  { num: "3", numFill: INK, h: "What this buys", headColor: INK, fill: WHITE, line: BORDER,
    b: "A hallucination, an outage, an exhausted quota or a change of vendor can alter how a decision is described. None can alter what it is." },
]);
callout(s, 5.25, "The system returns a complete, compliant decision with reasons, recourse and citations even with no API key configured at all. That is not a fallback bolted on late; it is the ordering of the pipeline.", GREEN_PALE, GREEN, INK, 0.95);
s.addNotes("If they remember one slide, it should be this one. In regulated lending, a model that cannot be held to its output cannot be on the decision path.");

// ================= 5. ARCHITECTURE =================
s = pres.addSlide(); s.background = { color: NEUTRAL };
title(s, "System architecture", 0.45, INK, 30);
s.addText("Green components are load-bearing: the decision and the compliant notice depend only on them. Amber is optional and can fail without consequence.",
  { x: M, y: 1.0, w: 11.9, h: 0.42, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 12.5, color: MUTED });

const LX = M, LW = 1.45, CX = M + 1.58, CW = W - 1.58, RH = 0.72, RG = 0.08;
const rowY = (i) => 1.42 + i * (RH + RG);

// row 0 — client
bandLabel(s, LX, rowY(0) + 0.22, LW, "CLIENT", MUTED);
node(s, CX, rowY(0), CW / 2 - 0.08, RH, "React + TypeScript — applicant view", "decision, reasons, recourse, citations", { subSize: 9.5 });
node(s, CX + CW / 2 + 0.08, rowY(0), CW / 2 - 0.08, RH, "React + TypeScript — underwriter view", "adds probability, SHAP contributions, provenance", { subSize: 9.5 });

// row 1 — api
bandLabel(s, LX, rowY(1) + 0.22, LW, "API", MUTED);
["JWT auth\n+ roles", "Pydantic\nvalidation", "Rate\nlimiting", "Role\nprojection", "Structured\nlogging"].forEach((t, i) => {
  const w = (CW - 4 * 0.1) / 5;
  node(s, CX + i * (w + 0.1), rowY(1), w, RH, t.replace("\n", " "), null, { titleSize: 11, align: "center" });
});

// row 2 — orchestration
bandLabel(s, LX, rowY(2) + 0.22, LW, "SERVICE", MUTED);
node(s, CX, rowY(2), CW, RH, "DecisionService — decide, explain, retrieve, render, then optionally narrate", "the ordering is the architecture: a complete compliant answer exists before any model is called", { subSize: 9.5 });

// row 3 — decision core (load-bearing)
bandLabel(s, LX, rowY(3) + 0.22, LW, "DECISION", GREEN);
[["HistGradientBoosting", "calibrated, handles NaN natively"],
 ["TreeSHAP", "exact reason codes, error 5e-15"],
 ["Counterfactual search", "recourse re-scored by the model"]].forEach((b, i) => {
  const w = (CW - 2 * 0.1) / 3;
  node(s, CX + i * (w + 0.1), rowY(3), w, RH, b[0], b[1], { fill: GREEN_PALE, line: GREEN, lw: 1.25, titleColor: GREEN, subColor: "2F4A40", subSize: 9.5 });
});

// row 4 — knowledge
bandLabel(s, LX, rowY(4) + 0.22, LW, "KNOWLEDGE", MUTED);
[["PostgreSQL + pgvector", "Neon, Singapore · HNSW index · 37 provisions"],
 ["bge-small-en-v1.5 (ONNX)", "embeddings computed locally, no text leaves the host"]].forEach((b, i) => {
  const w = (CW - 0.1) / 2;
  node(s, CX + i * (w + 0.1), rowY(4), w, RH, b[0], b[1], { subSize: 9.5 });
});

// row 5 — ai layer (optional)
bandLabel(s, LX, rowY(5) + 0.22, LW, "AI LAYER", AMBER);
node(s, CX, rowY(5), CW * 0.3, RH, "Guardrails", "PII · injection · contradiction", { fill: "F7E5E4", line: RED, lw: 1.25, titleColor: RED, subColor: "4A2A28", subSize: 9.5 });
node(s, CX + CW * 0.3 + 0.1, rowY(5), CW * 0.7 - 0.1, RH, "Provider abstraction — Gemini · Groq · Ollama · Bedrock", "selected by one environment variable; rejected output falls back to the deterministic notice", { fill: AMBER_PALE, line: "D8B478", lw: 1.25, titleColor: AMBER, subColor: "4A3A22", subSize: 9.5 });

// row 6 — data
bandLabel(s, LX, rowY(6) + 0.22, LW, "DATA", MUTED);
[["Applicant population", "generated, documented causal structure"],
 ["Regulatory corpus", "5 instruments, paraphrased and cited"],
 ["Model artifacts", "calibrated model, SHAP background"]].forEach((b, i) => {
  const w = (CW - 2 * 0.1) / 3;
  node(s, CX + i * (w + 0.1), rowY(6), w, RH, b[0], b[1], { subSize: 9.5 });
});

// flow arrows down the left gutter of the content column
for (let i = 0; i < 6; i++) arrow(s, CX - 0.14, rowY(i) + RH, CX - 0.14, rowY(i + 1), "A8B4BC", 1.25);

s.addText("Every layer shown is running: /health reports model ready, 37 provisions, vector_store pgvector, llm_provider gemini",
  { x: M, y: 7.02, w: W, h: 0.3, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 10.5, italic: true, color: "8A949C" });
s.addNotes("Walk down the bands. The point to land: everything green completes before anything amber is called, so the amber row can fail entirely and the applicant still receives a correct, compliant, cited decision.");

// ================= 5b. DECISION FLOW =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "What happens when an application arrives", 0.45, INK, 30);
lede(s, "Ten steps. The first six are deterministic and complete in about ten milliseconds. Only then is a language model consulted, and only about wording.", 0.98, MUTED, 11.9, 12.5);

s.addShape(pres.ShapeType.roundRect, { x: M, y: 1.62, w: W, h: 1.74, rectRadius: 0.1, fill: { color: GREEN_PALE }, line: { type: "none" } });
bandLabel(s, M + 0.26, 1.76, 6.0, "DETERMINISTIC  ·  COMPLETES IN ~10 MS  ·  NO MODEL INVOLVED", GREEN);
[["1", "Validate", "422 on out-of-range\nor identifier fields"],
 ["2", "Score", "calibrated PD\n3.2 ms"],
 ["3", "Reason codes", "exact TreeSHAP\n+0.34 ms"],
 ["4", "Recourse", "counterfactuals\nre-scored"],
 ["5", "Retrieve", "pgvector\nprovisions"],
 ["6", "Render notice", "complete and\ncompliant"]].forEach((b, i) => {
  const w = (W - 0.52 - 5 * 0.12) / 6, x = M + 0.26 + i * (w + 0.12);
  node(s, x, 2.1, w, 1.06, b[1], b[2].replace("\\n", " "), { fill: WHITE, line: GREEN, lw: 1, titleSize: 11.5, subSize: 9.5, titleColor: GREEN, reserveRight: 0.46 });
  badge(s, x + w - 0.38, 2.16, b[0], GREEN, WHITE);
  if (i < 5) arrow(s, x + w + 0.005, 2.63, x + w + 0.115, 2.63, "7FAF9B", 1.2);
});

s.addShape(pres.ShapeType.roundRect, { x: M, y: 3.52, w: W, h: 0.5, rectRadius: 0.08, fill: { color: INK }, line: { type: "none" } });
s.addText("THE DECISION, THE REASONS, THE RECOURSE AND THE CITATIONS ARE NOW FINAL", { x: M, y: 3.52, w: W, h: 0.5, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: BODY, fontSize: 12.5, bold: true, color: "9FE0C4", charSpacing: 1.2 });

s.addShape(pres.ShapeType.roundRect, { x: M, y: 4.18, w: W, h: 1.74, rectRadius: 0.1, fill: { color: AMBER_PALE }, line: { type: "none" } });
bandLabel(s, M + 0.26, 4.32, 7.0, "OPTIONAL  ·  WORDING ONLY  ·  ~2 S  ·  MAY FAIL WITHOUT CONSEQUENCE", AMBER);
[["7", "Guardrail in", "scan the assembled\nprompt"],
 ["8", "Narrate", "the model rewrites\nthe notice"],
 ["9", "Guardrail out", "contradiction, PII,\nguarantees"],
 ["10", "Project by role", "underwriter sees more\nthan the applicant"]].forEach((b, i) => {
  const w = (W - 0.52 - 3 * 0.12) / 4, x = M + 0.26 + i * (w + 0.12);
  node(s, x, 4.66, w, 1.06, b[1], b[2].replace("\\n", " "), { fill: WHITE, line: "D8B478", lw: 1, titleSize: 11.5, subSize: 9.5, titleColor: AMBER, reserveRight: 0.46 });
  badge(s, x + w - 0.38, 4.72, b[0], AMBER, WHITE);
  if (i < 3) arrow(s, x + w + 0.005, 5.19, x + w + 0.115, 5.19, "C8A46E", 1.2);
});

callout(s, 6.08, "If steps 7 to 9 fail for any reason \u2014 outage, rate limit, a guardrail firing \u2014 the applicant receives the notice rendered at step 6. Measured on a flaky free tier, that happened to half of all requests, and every one of them was still correct.", GREEN_PALE, GREEN, INK, 0.8);
s.addNotes("The black bar is the slide. Everything above it is finished before anything below it runs.");

// ================= 6. DATA =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "The data, and why it is synthetic");
lede(s, "No public dataset joins Account Aggregator-style alternative data to realised loan outcomes for Indian borrowers — that data is personal financial information and is not published. So the population is generated openly, with its assumptions written down and tested, rather than sourced from a proxy dataset and quietly relabelled.", 1.45, MUTED, 11.9);
cardRow(s, 2.85, 2.6, [
  { num: "A", h: "Causal, not correlational", b: "Default is driven by latent repayment capacity and willingness plus a large idiosyncratic shock. Observable features are noisy consequences of those latents — never rescaled copies of the label." },
  { num: "B", h: "Two seeded biases", b: "Bureau records go missing more often for women and rural applicants; declared income is depressed for women. Neither touches true repayment." },
  { num: "C", h: "Guarded by tests", b: "Maximum feature-to-label correlation 0.49. Equal true default rates across groups. Both asserted in the suite, so they fail loudly rather than drifting silently." },
]);
callout(s, 5.7, "Knowing the ground truth is what makes the result provable. On a real portfolio a rejected applicant's counterfactual repayment is never observed, so the central claim could be argued but not measured.", AMBER_PALE, AMBER, INK, 0.8);
s.addNotes("Expect to be challenged on synthetic data. The answer is that the alternative is not real data, it is a US or Czech dataset relabelled as Indian. And ground truth is what lets us prove the mechanism.");

// ================= 6b. VALIDATION ON REAL DATA =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "The same pipeline, run on real credit data");
lede(s, "The obvious objection to a synthetic population is that the result could be an artefact of the generator. So the identical code path - design matrix, booster, calibration, TreeSHAP, fairness audit - was run over two real public datasets with genuinely observed defaults.", 1.45, MUTED, 11.9);
const vrows = [
  [{ text: "Dataset", options: { bold: true, color: WHITE, align: "left" } },
   { text: "Rows", options: { bold: true, color: WHITE } },
   { text: "AUC", options: { bold: true, color: WHITE } },
   { text: "KS", options: { bold: true, color: WHITE } },
   { text: "Calibration err", options: { bold: true, color: WHITE } },
   { text: "TreeSHAP error", options: { bold: true, color: WHITE } }],
  ["German Credit (Statlog)", "1,000", "0.7464", "0.3752", "0.0772", "2.7e-15"],
  ["Taiwan Default of Credit Card Clients", "30,000", "0.7829", "0.4391", "0.0222", "4.0e-15"],
  [{ text: "This project, synthetic", options: { bold: true } }, { text: "30,000", options: { bold: true } },
   { text: "0.7797", options: { bold: true, color: GREEN } }, { text: "0.4127", options: { bold: true, color: GREEN } },
   { text: "0.0073", options: { bold: true, color: GREEN } }, { text: "5.2e-15", options: { bold: true, color: GREEN } }],
];
s.addTable(vrows, { x: M, y: 2.75, w: W, colW: [4.3, 1.3, 1.5, 1.5, 1.9, 1.7], rowH: 0.42,
  fontFace: BODY, fontSize: 12.5, color: INK, valign: "middle", align: "center",
  border: { type: "solid", color: BORDER, pt: 0.5 }, fill: { color: WHITE }, autoPage: false });
s.addShape(pres.ShapeType.rect, { x: M, y: 2.75, w: W, h: 0.42, fill: { color: INK }, line: { type: "none" } });
[["Dataset", 4.3, "left"], ["Rows", 1.3, "center"], ["AUC", 1.5, "center"], ["KS", 1.5, "center"],
 ["Calibration err", 1.9, "center"], ["TreeSHAP error", 1.7, "center"]].reduce((x, c) => {
  s.addText(c[0], { x: c[2] === "left" ? x + 0.15 : x, y: 2.75, w: c[2] === "left" ? c[1] - 0.2 : c[1], h: 0.42, isTextBox: true, margin: 0,
    align: c[2], valign: "middle", fontFace: BODY, fontSize: 12, bold: true, color: WHITE });
  return x + c[1];
}, M);
callout(s, 4.6, "Our synthetic population's difficulty sits between the two real datasets, which is the answer to \u201Cyou tuned it to a flattering level\u201D. TreeSHAP stays exact on real data. The audit also found a genuine violation rather than rubber-stamping: age band on German Credit fails the 80% rule at 0.783.", GREEN_PALE, GREEN, INK, 1.0);
callout(s, 5.75, "What this does NOT establish: neither dataset carries alternative data, so the inclusion finding cannot be reproduced on them. That claim rests on the synthetic population, and this deck says so.", AMBER_PALE, AMBER, INK, 0.85);
s.addNotes("Lead with this when challenged on synthetic data. The machinery is validated on real defaults; only the inclusion comparison needs the generator. Note we report the scope limit ourselves.");

chartSlide("real_validation.png", 1.582,
  "Our difficulty sits between two real datasets",
  "The identical pipeline \u2014 design matrix, booster, calibration, TreeSHAP, fairness audit \u2014 run over real credit data with observed defaults.",
  "This is the answer to \u201Cyou tuned the generator to a flattering level\u201D. A synthetic population easier than reality would score above both; one built to flatter would not calibrate to 0.0073 either.",
  { maxW: 8.4 });

// ================= 7. EXPERIMENT =================
s = pres.addSlide(); s.background = { color: INK };
s.addText("THE EXPERIMENT", { x: M, y: 1.15, w: W, h: 0.3, isTextBox: true, margin: 0,
  fontFace: BODY, fontSize: 11.5, bold: true, color: GREEN_TEXT, charSpacing: 2.5 });
s.addText("Two models. Same data, same splits, same approval rate.", { x: M, y: 1.7, w: 11.4, h: 1.5, isTextBox: true, margin: 0,
  fontFace: HEAD, fontSize: 38, color: WHITE, lineSpacing: 46, valign: "top" });
[["Traditional", "Application details and the credit bureau record only — the information a conventional underwriter sees.", INK_CARD, INK_TEXT],
 ["Inclusive", "The same, plus consented alternative data: UPI cash-flow behaviour, utility punctuality, telecom tenure.", "134034", "A9E3C6"]].forEach((b, i) => {
  const cw = (W - 0.35) / 2, x = M + i * (cw + 0.35);
  s.addShape(pres.ShapeType.roundRect, { x, y: 3.3, w: cw, h: 1.75, rectRadius: 0.09, fill: { color: b[2] }, line: { type: "none" } });
  s.addText(b[0], { x: x + 0.32, y: 3.52, w: cw - 0.64, h: 0.42, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 17, bold: true, color: i ? GREEN_TEXT : "C2CDD6" });
  s.addText(b[1], { x: x + 0.32, y: 3.96, w: cw - 0.64, h: 0.95, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, color: b[3], lineSpacing: 19 });
});
s.addText("Approval rate is pinned at 70% for both, so the comparison is like-for-like. Any difference is the information, not the risk appetite.",
  { x: M, y: 5.45, w: 11.4, h: 0.7, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 14, color: INK_TEXT, lineSpacing: 20 });
s.addNotes("Holding approval rate constant matters. Otherwise a model could look fairer simply by approving more people.");

// ================= 8. RESULT =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "Accuracy, risk and fairness moved together");
const rows = [
  [{ text: "Measured on held-out data, approval rate pinned at 70%", options: { bold: true, color: WHITE, align: "left" } },
   { text: "Bureau only", options: { bold: true, color: WHITE } },
   { text: "+ Alternative data", options: { bold: true, color: WHITE } },
   { text: "Change", options: { bold: true, color: WHITE } }],
  ["ROC AUC", "0.7314", { text: "0.7797", options: { color: GREEN, bold: true } }, { text: "+0.048", options: { color: GREEN } }],
  ["KS statistic", "0.3365", { text: "0.4127", options: { color: GREEN, bold: true } }, { text: "+0.076", options: { color: GREEN } }],
  ["Bad rate among approved", "0.0746", { text: "0.0623", options: { color: GREEN, bold: true } }, { text: "− 0.012", options: { color: GREEN } }],
  ["Creditworthy NTC approved", "0.7189", { text: "0.7361", options: { color: GREEN, bold: true } }, { text: "+0.017", options: { color: GREEN } }],
  ["Disparate impact, gender", "0.869", { text: "0.964", options: { color: GREEN, bold: true } }, { text: "+0.095", options: { color: GREEN } }],
  [{ text: "Qualified-approval gap", options: { bold: true } }, { text: "0.1083", options: { bold: true } },
   { text: "0.0341", options: { color: GREEN, bold: true } }, { text: "− 0.074", options: { color: GREEN, bold: true } }],
];
s.addTable(rows, { x: M, y: 1.5, w: 7.6, colW: [3.3, 1.35, 1.65, 1.3], rowH: 0.44,
  fontFace: BODY, fontSize: 13, color: INK, valign: "middle", align: "center",
  border: { type: "solid", color: BORDER, pt: 0.5 },
  fill: { color: WHITE },
  autoPage: false });
s.addShape(pres.ShapeType.rect, { x: M, y: 1.5, w: 7.6, h: 0.44, fill: { color: INK }, line: { type: "none" } });
s.addText("Held out, approval pinned at 70%", { x: M + 0.12, y: 1.5, w: 3.18, h: 0.44, isTextBox: true, margin: 0, valign: "middle", fontFace: BODY, fontSize: 11, bold: true, color: WHITE });
["Bureau only", "+ Alt data", "Change"].forEach((t, i) => {
  const xs = [M + 3.3, M + 4.65, M + 6.3], ws = [1.35, 1.65, 1.3];
  s.addText(t, { x: xs[i], y: 1.5, w: ws[i], h: 0.44, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: BODY, fontSize: 11, bold: true, color: WHITE });
});
s.addImage({ path: path.join(FIG, "roc.png"), x: M + 7.95, y: 1.45, w: 4.25, h: 2.99 });
callout(s, 5.45, "There is no accuracy-versus-fairness trade-off here — which is the point. The disparity was never a property of the algorithm, so it did not have to be bought back with accuracy.", GREEN_PALE, GREEN, INK, 0.8);
s.addNotes("Note the bad rate falling. The inclusive model approves a fairer mix and takes on less risk doing it, because it is seeing more.");

chartSlide("roc.png", 1.420,
  "Where the extra evidence actually pays",
  "ROC curves on held-out applicants. The gain is largest in the region where most lending decisions are actually made.",
  null, { maxW: 7.6 });

// ================= 9. PEOPLE =================
s = pres.addSlide(); s.background = { color: GREEN };
s.addText("THE SAME RESULT, STATED AS PEOPLE", { x: M, y: 0.62, w: W, h: 0.3, isTextBox: true, margin: 0,
  fontFace: BODY, fontSize: 11.5, bold: true, color: "A9E3C6", charSpacing: 2.5 });
s.addText("Among applicants who would have repaid", { x: M, y: 1.05, w: 11.4, h: 0.8, isTextBox: true, margin: 0,
  fontFace: HEAD, fontSize: 34, color: WHITE, valign: "top" });
s.addShape(pres.ShapeType.roundRect, { x: M, y: 2.05, w: 6.6, h: 4.37, rectRadius: 0.1, fill: { color: WHITE }, line: { type: "none" } });
s.addImage({ path: path.join(FIG, "fairness_gap.png"), x: M + 0.12, y: 2.17, w: 6.36, h: 4.21 });
const pw = W - 6.6 - 0.35, px = M + 6.6 + 0.35;
s.addShape(pres.ShapeType.roundRect, { x: px, y: 2.05, w: pw, h: 2.05, rectRadius: 0.1, fill: { color: GREEN_DEEP }, line: { type: "none" } });
s.addText("10.8 \u2192 3.4", { x: px + 0.3, y: 2.25, w: pw - 0.6, h: 0.75, isTextBox: true, margin: 0, fontFace: HEAD, fontSize: 44, bold: true, color: WHITE });
s.addText("percentage-point gap between creditworthy women and men. A 69% reduction.", { x: px + 0.3, y: 3.0, w: pw - 0.6, h: 0.95, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 15, color: "A9E3C6", lineSpacing: 21 });
s.addShape(pres.ShapeType.roundRect, { x: px, y: 4.32, w: pw, h: 2.1, rectRadius: 0.1, fill: { color: GREEN_DEEP }, line: { type: "none" } });
s.addText("More creditworthy women approved. Fewer defaults among those approved. The people the old model missed were not bad risks \u2014 they were invisible ones.",
  { x: px + 0.3, y: 4.55, w: pw - 0.6, h: 1.65, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 15, color: "D3EFE1", lineSpacing: 22 });

s.addNotes("This is the slide to slow down on. It converts a fairness metric into a sentence about people, which is what a credit committee actually decides on.");

// ================= 9b. MITIGATION COMPARED =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "We tried the algorithmic remedies too");
lede(s, "Claiming the disparity lives in the evidence rather than the algorithm is only worth something if the standard algorithmic fixes were actually run. They were, at an identical approval rate.", 1.45, MUTED, 11.9);
const mrows = [
  [{ text: "Strategy", options: { bold: true, color: WHITE, align: "left" } },
   { text: "AUC", options: { bold: true, color: WHITE } },
   { text: "Bad rate", options: { bold: true, color: WHITE } },
   { text: "Disparate impact", options: { bold: true, color: WHITE } },
   { text: "Reads gender to decide?", options: { bold: true, color: WHITE } }],
  ["Baseline, bureau only", "0.731", "0.0698", "0.879", { text: "no", options: { color: GREEN } }],
  [{ text: "Alternative data (this project)", options: { bold: true } },
   { text: "0.765", options: { bold: true, color: GREEN } },
   { text: "0.0616", options: { bold: true, color: GREEN } },
   { text: "0.957", options: { bold: true, color: GREEN } },
   { text: "no", options: { bold: true, color: GREEN } }],
  ["CorrelationRemover", "0.727", "0.0708", "0.990", { text: "YES", options: { color: RED, bold: true } }],
  ["ThresholdOptimizer", "0.677", { text: "0.1200", options: { color: RED } }, "1.000", { text: "YES", options: { color: RED, bold: true } }],
  ["ExponentiatedGradient", { text: "degenerate", options: { color: RED, italic: true } }, { text: "0.1191", options: { color: RED } }, "0.996", { text: "no", options: { color: MUTED } }],
];
s.addTable(mrows, { x: M, y: 2.6, w: W, colW: [4.1, 1.5, 1.7, 2.4, 2.5], rowH: 0.42,
  fontFace: BODY, fontSize: 12.5, color: INK, valign: "middle", align: "center",
  border: { type: "solid", color: BORDER, pt: 0.5 }, fill: { color: WHITE }, autoPage: false });
s.addShape(pres.ShapeType.rect, { x: M, y: 2.6, w: W, h: 0.42, fill: { color: INK }, line: { type: "none" } });
[["Strategy", 4.1, "left"], ["AUC", 1.5, "center"], ["Bad rate", 1.7, "center"],
 ["Disparate impact", 2.4, "center"], ["Reads gender to decide?", 2.5, "center"]].reduce((x, c) => {
  s.addText(c[0], { x: c[2] === "left" ? x + 0.15 : x, y: 2.6, w: c[2] === "left" ? c[1] - 0.2 : c[1], h: 0.42, isTextBox: true, margin: 0,
    align: c[2], valign: "middle", fontFace: BODY, fontSize: 11.5, bold: true, color: WHITE });
  return x + c[1];
}, M);
callout(s, 5.0, "Every algorithmic remedy bought fairness with accuracy or with risk. Widening the evidence was the only one that improved discrimination, risk and fairness together \u2014 and the only one needing the protected attribute at neither training nor decision time.", GREEN_PALE, GREEN, INK, 0.95);
callout(s, 6.1, "Two failures recorded rather than smoothed over: CorrelationRemover cannot accept a missing bureau score, the very signal that defines a thin-file applicant. ExponentiatedGradient collapsed to approving 99% of everyone across five constraint tightnesses and three constraint types \u2014 at a 12% base rate, approving everyone satisfies parity exactly.", AMBER_PALE, AMBER, INK, 0.95);
s.addNotes("The 'reads gender to decide' column is the point a fair-lending reviewer will care about. A remedy that applies a different threshold by group is disparate treatment, not a cure for it.");

chartSlide("mitigation.png", 1.538,
  "Only one intervention improved both axes",
  "Every strategy at an identical approval rate. Up is a better model; left is a fairer one. Diamonds must read the applicant\u2019s gender to decide.",
  "The algorithmic remedies sit down and to the left: they buy fairness with accuracy. Widening the evidence is the only point that moved up and left together, and the only one that never reads a protected attribute.",
  { maxW: 7.8 });

chartSlide("reject_inference.png", 2.247,
  "What a lender\u2019s own book hides",
  "Repayment is observed only for applicants a previous policy approved, so the training data is censored. On a real book the damage is unmeasurable. Here it is not.",
  "The accepted book shows a 5.77% bad rate against a true pool rate of 12.00% \u2014 a lender reading their own data sees a portfolio six points safer than the one they are underwriting. Fuzzy augmentation recovers 73% of the lost ranking quality.",
  { maxW: 11.0, calloutH: 0.92 });

// ================= 10. EXPLAIN =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "Reason codes that faithfully decompose the model");
lede(s, "A real decline. Contributions in log-odds, aggregated back to features a person recognises.", 1.42, MUTED, 6.2, 13);
card(s, M, 2.05, 6.2, 3.35, WHITE, BORDER);
const bars = [
  ["1.  Days with very low balance", "40 of 90", 4.45, RED],
  ["2.  Utility bill punctuality", "35%", 1.34, RED],
  ["3.  Income regularity", "26%", 0.59, RED],
  ["In favour  ·  declared income", "₹5,000", 1.11, GREEN],
];
bars.forEach((b, i) => {
  const y = 2.32 + i * 0.78;
  s.addText([{ text: b[0], options: { bold: true, color: b[3] === GREEN ? GREEN : INK } },
             { text: "   " + b[1], options: { color: MUTED } }],
    { x: M + 0.3, y, w: 5.6, h: 0.3, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 12.5, valign: "middle" });
  s.addShape(pres.ShapeType.roundRect, { x: M + 0.3, y: y + 0.33, w: 5.6, h: 0.14, rectRadius: 0.07, fill: { color: "EDF0EE" }, line: { type: "none" } });
  s.addShape(pres.ShapeType.roundRect, { x: M + 0.3, y: y + 0.33, w: b[2], h: 0.14, rectRadius: 0.07, fill: { color: b[3] }, line: { type: "none" } });
});
card(s, M + 6.5, 2.05, W - 6.5, 1.5, GREEN_PALE, null);
s.addText("5.2 × 10⁻¹⁵", { x: M + 6.8, y: 2.22, w: W - 7.1, h: 0.6, isTextBox: true, margin: 0, fontFace: HEAD, fontSize: 34, bold: true, color: GREEN });
s.addText("TreeSHAP additivity error", { x: M + 6.8, y: 2.82, w: W - 7.1, h: 0.3, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13.5, bold: true, color: INK });
s.addText("The reason codes sum exactly to the model's output. They are the decomposition, not an approximation of it.", { x: M + 6.8, y: 3.12, w: W - 7.1, h: 0.4, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 11.5, color: "3C4E58", lineSpacing: 15 });
card(s, M + 6.5, 3.75, W - 6.5, 1.65, AMBER_PALE, null);
s.addText("An earlier build let the booster split categoricals natively. TreeSHAP mis-attributed those splits by up to 0.24 log-odds — enough to reorder an applicant's reasons. One-hot encoding every split cost 0.001 AUC and made the attribution exact. Under the Fair Practices Code an unfaithful reason is a compliance failure, not a cosmetic one.",
  { x: M + 6.8, y: 3.92, w: W - 7.1, h: 1.3, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 11.5, color: "3C4E58", lineSpacing: 16 });
s.addNotes("The 0.24 story is worth telling. It shows the difference between a system that displays an explanation and one that can defend it.");

chartSlide("waterfall.png", 1.576,
  "Every factor, and exactly how much it counted",
  "One declined applicant, decomposed. Bars to the right pushed toward decline; bars to the left pushed toward approval.",
  "These are not importances or approximations. They are the model\u2019s output taken apart and put back together, summing to within 5\u00d710\u207b\u00b9\u2075 of the score itself.",
  { maxW: 8.2 });

// ================= 11. RECOURSE =================
s = pres.addSlide(); s.background = { color: NEUTRAL };
title(s, "A decline that comes with a plan");
lede(s, "Every option below is a genuine counterfactual: the feature is moved, the applicant is re-scored by the same model, and only changes that actually flip the decision are shown.", 1.42, MUTED, 11.7);
cardRow(s, 2.45, 2.65, [
  { num: "₹", h: "Requested amount\n₹97,300  →  ₹43,100", b: "Requesting less lowers the monthly instalment." },
  { num: "⏱", h: "Tenure\n6 months  →  14 months", b: "A longer term reduces each instalment." },
  { num: "↑", numFill: AMBER, h: "Recharge regularity\n34%  →  40%", b: "A consistent recharge schedule builds this signal. Takes one to three months." },
], { headH: 0.7, headSize: 13.5 });
[["Only what they can move.", "Age, education and employment sector are never suggested. Advising someone to be older is not recourse."],
 ["Only what they can reach.", "Targets are capped at the 85th percentile of the population, and “no attainable change” is reported honestly rather than padded."]].forEach((b, i) => {
  const cw = (W - 0.3) / 2, x = M + i * (cw + 0.3);
  card(s, x, 5.3, cw, 1.05, GREEN_PALE, null);
  s.addText([{ text: b[0] + "  ", options: { bold: true, color: GREEN } }, { text: b[1], options: { color: INK } }],
    { x: x + 0.28, y: 5.42, w: cw - 0.56, h: 0.82, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 12, lineSpacing: 16, valign: "top" });
});
footnote(s, "Derived features are excluded deliberately: “lower your instalment-to-income ratio” is not an action; borrow less and repay over longer are, and both are offered");
s.addNotes("Derived features are excluded deliberately. Lower your instalment-to-income ratio is not an action; borrow less and repay over longer are, and both are offered.");

// ================= 12. COMPLIANCE =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "The regulation demanded the feature anyway");
lede(s, "37 provisions from five Indian instruments, embedded locally and retrieved per decision, so every notice cites the rule that governs it.", 1.42, MUTED, 11.7);
[["RBI Fair Practices", "Reasons for rejection must be conveyed — automated or not"],
 ["RBI Digital Lending", "Need-based data, Key Fact Statement, explainable models"],
 ["DPDP Act 2023", "Consent, purpose limitation, minimisation, erasure"],
 ["Account Aggregator", "The consented rail alternative data legally travels on"],
 ["CIC Act 2005", "Absence of a bureau record is not adverse history"]].forEach((b, i) => {
  const cw = (W - 4 * 0.25) / 5, x = M + i * (cw + 0.25);
  card(s, x, 2.4, cw, 1.95, WHITE, BORDER);
  badge(s, x + 0.22, 2.6, String(i + 1), GREEN, WHITE);
  s.addText(b[0], { x: x + 0.22, y: 3.12, w: cw - 0.44, h: 0.5, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 12.5, bold: true, color: GREEN, lineSpacing: 15 });
  s.addText(b[1], { x: x + 0.22, y: 3.6, w: cw - 0.44, h: 0.68, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 10.5, color: MUTED, lineSpacing: 13 });
});
card(s, M, 4.65, W, 1.25, GREEN_PALE, null);
s.addText("RETRIEVED FOR A LIVE DECLINE", { x: M + 0.3, y: 4.8, w: W - 0.6, h: 0.28, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 10, bold: true, color: GREEN, charSpacing: 2 });
s.addText([{ text: "[FPC-01] ", options: { bold: true, color: GREEN } }, { text: "Reasons for rejection must be communicated    ", options: { color: INK } },
           { text: "[DL-04] ", options: { bold: true, color: GREEN } }, { text: "Borrower's right to reject data collection    ", options: { color: INK } },
           { text: "[CIC-04] ", options: { bold: true, color: GREEN } }, { text: "Absence of a bureau record is not evidence of poor credit conduct", options: { color: INK } }],
  { x: M + 0.3, y: 5.1, w: W - 0.6, h: 0.7, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 12, lineSpacing: 17, valign: "top" });
footnote(s, "Provisions are labelled paraphrases citing the real instrument — seeding a corpus with invented quotations would be the hallucination this design prevents");
s.addNotes("CIC-04 is the one to point at: the regulation itself says absence of history is not adverse history. The architecture is enforcing something the law already asserts.");

// ================= 12b. WHAT THE APPLICANT READS =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "What the applicant actually reads");
lede(s, "Produced live by Gemini from the finished decision. Every figure in it comes from the facts block; the model added no numbers of its own.", 1.42, MUTED, 11.7);
card(s, M, 2.15, 7.9, 4.3, NEUTRAL, null);
s.addText([
 { text: "We are writing to inform you that your loan application has been declined. As you are new to formal credit, we assessed your application based on your financial habits rather than a credit bureau record ", options: { color: INK } },
 { text: "[CIC-04]", options: { color: GREEN, bold: true } },
 { text: ".\n\nOur assessment identified a few areas that prevented approval. Your monthly instalment amount is currently too high relative to your income of ", options: { color: INK } },
 { text: "Rs 19,600", options: { bold: true } },
 { text: ". Additionally, we noted that your utility bills are often paid late and your mobile recharge pattern is irregular.\n\nTo improve your chances for future applications, you could request a smaller loan amount, such as ", options: { color: INK } },
 { text: "Rs 43,098", options: { bold: true } },
 { text: ", or choose a longer repayment period of approximately ", options: { color: INK } },
 { text: "14 months", options: { bold: true } },
 { text: ". Both steps would lower your monthly instalment.\n\nIn accordance with the RBI Fair Practices Code, we are providing these reasons for your application's decline in writing ", options: { color: INK } },
 { text: "[FPC-01]", options: { color: GREEN, bold: true } },
 { text: ".", options: { color: INK } },
], { x: M + 0.35, y: 2.42, w: 7.2, h: 3.8, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, lineSpacing: 19, valign: "top" });
const nx = M + 8.25, nw = W - 8.25;
[["Narrated by", "gemini-3.1-flash-lite"], ["End to end", "3.7 seconds"], ["Guardrails", "passed"],
 ["Citations", "CIC-04 · FPC-01 · DL-04"], ["Invented facts", "none"]].forEach((r, i) => {
  const y = 2.15 + i * 0.88;
  card(s, nx, y, nw, 0.76, WHITE, BORDER);
  s.addText(r[0], { x: nx + 0.22, y: y + 0.1, w: nw - 0.44, h: 0.26, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 10.5, color: MUTED, charSpacing: 1.2 });
  s.addText(r[1], { x: nx + 0.22, y: y + 0.36, w: nw - 0.44, h: 0.32, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13.5, bold: true, color: i === 4 ? GREEN : INK });
});
footnote(s, "Rs 43,098 and 14 months are the recourse targets the model computed, re-scored against the real decision boundary \u2014 not figures the language model chose");
s.addNotes("Point at the two bracketed citations and the two rupee figures. The citations come from retrieval; the figures come from counterfactual search. The language model supplied only the sentences around them.");

// ================= 13. GUARDRAILS =================
s = pres.addSlide(); s.background = { color: INK };
s.addText("What the guardrails actually stop", { x: M, y: 0.5, w: W, h: 0.85, isTextBox: true, margin: 0, fontFace: HEAD, fontSize: 34, color: WHITE, valign: "top" });
[["Decision contradiction", "If the model declined and the generated text congratulates the applicant, the lender has mis-communicated a credit decision. Rejected, and the deterministic notice is served instead."],
 ["Prompt injection", "Applicant-influenced values reach the prompt. The system prompt states that the facts block is data, never instruction, and the assembled prompt is scanned before it is sent."],
 ["Personal data leaving", "Aadhaar, PAN, phone and email patterns are detected inbound and outbound — and the guardrail's own log records the kind found, never the value."]].forEach((b, i) => {
  const cw = (W - 0.6) / 3, x = M + i * (cw + 0.3);
  s.addShape(pres.ShapeType.roundRect, { x, y: 1.6, w: cw, h: 2.5, rectRadius: 0.09, fill: { color: INK_CARD }, line: { type: "none" } });
  badge(s, x + 0.28, 1.85, String(i + 1), RED, WHITE);
  s.addText(b[0], { x: x + 0.28, y: 2.42, w: cw - 0.56, h: 0.38, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 14.5, bold: true, color: "FF9F98" });
  s.addText(b[1], { x: x + 0.28, y: 2.82, w: cw - 0.56, h: 1.15, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 11.5, color: INK_TEXT, lineSpacing: 16 });
});
s.addShape(pres.ShapeType.roundRect, { x: M, y: 4.45, w: W, h: 1.55, rectRadius: 0.09, fill: { color: "134034" }, line: { type: "none" } });
s.addText("The stronger guarantee is structural", { x: M + 0.35, y: 4.65, w: W - 0.7, h: 0.35, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 15, bold: true, color: GREEN_TEXT });
s.addText("The prompt is assembled only from the decision object, never from the applicant record. There is no code path by which a name, PAN or Aadhaar could reach a third-party model — and the API refuses a request carrying one with a 422. Data minimisation by construction, not by promise.",
  { x: M + 0.35, y: 5.02, w: W - 0.7, h: 0.85, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, color: "A9E3C6", lineSpacing: 19 });
s.addNotes("Detection is defence in depth. The real guarantee is that the sensitive data is never in the room.");

// ================= 13b. GUARDRAILS DEMONSTRATED =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "Guardrails, demonstrated against the live model");
lede(s, "Five scenarios run against the real service. In every blocked case the applicant still received the decision, the reasons, the recourse and the citations \u2014 the guardrail removes the wording, never the substance.", 1.42, MUTED, 11.8);
[["1", "Normal decline", "Gemini narrates. Nothing blocked.", "allowed", GREEN, GREEN_PALE],
 ["2", "Injection in a field that is not a top reason", "The prompt carries only the top reason codes, so the poisoned value never reaches the model.", "never reached it", GREEN, GREEN_PALE],
 ["3", "Injection in a field that IS a top reason", "The value reaches the prompt and the inbound guardrail rejects it.", "blocked", RED, "F7E5E4"],
 ["4", "Model contradicts the decision", "A provider congratulates an applicant the model declined.", "blocked", RED, "F7E5E4"],
 ["5", "Model leaks a phone number", "A provider puts an identifier into applicant-facing text.", "blocked", RED, "F7E5E4"]].forEach((r, i) => {
  const y = 2.42 + i * 0.83;
  card(s, M, y, W, 0.72, r[5], null);
  badge(s, M + 0.22, y + 0.15, r[0], r[4], WHITE);
  s.addText(r[1], { x: M + 0.85, y: y + 0.08, w: 5.0, h: 0.3, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, bold: true, color: INK });
  s.addText(r[2], { x: M + 0.85, y: y + 0.37, w: 7.9, h: 0.3, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 11.5, color: MUTED });
  s.addText(r[3], { x: M + 9.0, y: y + 0.08, w: 3.0, h: 0.56, isTextBox: true, margin: 0, align: "right", valign: "middle", fontFace: BODY, fontSize: 13.5, bold: true, color: r[4] });
});
callout(s, 6.62, "Writing this demonstration corrected a claim we had wrong: scenario 2 was first recorded as a guardrail failure. It is not \u2014 nothing needed blocking, because nothing got through.", AMBER_PALE, AMBER, INK, 0.66);
s.addNotes("Scenario 2 is the interesting one. Data minimisation is the primary defence and the guardrail is the backstop. Say that we found this by testing rather than by assuming.");

chartSlide("redteam.png", 1.579,
  "We asked a model to attack the guardrails",
  "Each round, a language model invents attacks it has never been shown, and is not told what the detectors look for. The guardrails are then hardened and tested again on fresh attacks.",
  "Recall does not climb toward 1.0 \u2014 it plateaus near 0.6. Patching catches that round\u2019s phrasings; the next round finds new categories. Pattern matching is an arms race a regular expression does not win, and the honest score is 0.6, not the 1.000 our own test set reports.",
  { maxW: 8.2, calloutFill: AMBER_PALE, calloutBar: AMBER, calloutH: 0.92 });

// ================= 14. EVALUATION =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "Measured, not asserted");
lede(s, "An evaluation harness turns the system's claims into numbers, regenerable in one command, with no API key or database required.", 1.42, MUTED, 11.7);
cardRow(s, 2.38, 2.92, [
  { stat: "100%", statSize: 34, h: "Relevant provision in top 3", b: "Across 28 golden queries. 92.9% at rank 1, MRR 0.958. The two rank-1 misses are listed in the report." },
  { stat: "1.000", statSize: 34, h: "Guardrail F1", b: "Over 23 adversarial and benign cases. Benign cases count equally — a guardrail that blocks valid explanations breaks the duty to give reasons." },
  { stat: "0.0073", statSize: 34, h: "Expected calibration error", b: "A stated 8% risk lands within 0.7 points of the observed rate, so the probability is usable for pricing, not just ranking." },
  { stat: "103", statSize: 34, h: "Tests, 89% coverage", b: "Defending the invariants that were expensive to get right, not asserting that code runs." },
], { headSize: 13, bodySize: 11 });
callout(s, 5.5, "Stated plainly: that guardrail F1 is on 23 cases I wrote myself. It shows the guardrails catch the attacks I anticipated — not that they catch all attacks.", AMBER_PALE, AMBER, INK, 0.8);
s.addNotes("Volunteer the caveat before anyone asks. A candidate who marks their own homework and says so is more trustworthy than one reporting a perfect score.");

// ================= 14b. LATENCY =================
s = pres.addSlide(); s.background = { color: INK };
s.addText("Explainability is not a latency trade", { x: M, y: 0.5, w: W, h: 0.85, isTextBox: true, margin: 0, fontFace: HEAD, fontSize: 34, color: WHITE, valign: "top" });
s.addText("A decision is made while an applicant waits, so the cost of every guarantee is a product constraint rather than a footnote. Measured per applicant on CPU, p50.", { x: M, y: 1.4, w: 11.6, h: 0.7, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 14, color: INK_TEXT, lineSpacing: 20 });
[["Score only", "3.18 ms", "C2CDD6"], ["Score + exact SHAP reason codes", "3.52 ms", GREEN_TEXT],
 ["Retrieve the governing provisions", "2.93 ms", "C2CDD6"], ["Render the full compliant notice", "3.68 ms", "C2CDD6"],
 ["Search for actionable recourse", "75.92 ms", "E0A758"]].forEach((r, i) => {
  const y = 2.35 + i * 0.62;
  s.addShape(pres.ShapeType.roundRect, { x: M, y, w: 11.6, h: 0.52, rectRadius: 0.08, fill: { color: INK_CARD }, line: { type: "none" } });
  s.addText(r[0], { x: M + 0.3, y, w: 7.6, h: 0.52, isTextBox: true, margin: 0, valign: "middle", fontFace: BODY, fontSize: 14, color: "E4EAEF" });
  s.addText(r[1], { x: M + 8.2, y, w: 3.1, h: 0.52, isTextBox: true, margin: 0, valign: "middle", align: "right", fontFace: BODY, fontSize: 15, bold: true, color: r[2] });
});
s.addShape(pres.ShapeType.roundRect, { x: M, y: 5.48, w: 5.65, h: 1.3, rectRadius: 0.09, fill: { color: "134034" }, line: { type: "none" } });
s.addText([{ text: "Exact reason codes cost 0.34 ms. ", options: { bold: true, color: GREEN_TEXT } },
           { text: "A complete, explained, cited decision lands in about 10 ms \u2014 about 86 ms when it also computes recourse.", options: { color: "A9E3C6" } }],
  { x: M + 0.3, y: 5.66, w: 5.05, h: 0.95, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, lineSpacing: 18, valign: "top" });
s.addShape(pres.ShapeType.roundRect, { x: M + 5.95, y: 5.48, w: 5.65, h: 1.3, rectRadius: 0.09, fill: { color: INK_CARD }, line: { type: "none" } });
s.addText([{ text: "The language model is excluded. ", options: { bold: true, color: "E0A758" } },
           { text: "It is off the decision path and its latency belongs to a third-party API. Measured separately: 2.8 s mean, 10 of 10 live calls.", options: { color: INK_TEXT } }],
  { x: M + 6.25, y: 5.66, w: 5.05, h: 0.95, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, lineSpacing: 18, valign: "top" });
s.addNotes("The 0.34 ms number is the one to say out loud. It kills the assumption that a lender trades latency for explainability.");

// ================= 15. ENGINEERING =================
s = pres.addSlide(); s.background = { color: NEUTRAL };
title(s, "Engineering decisions worth defending");
cardRow(s, 1.42, 2.5, [
  { num: "→", h: "FastAPI, under “or equivalent”", b: "Same layered shape as Spring Boot: router → service → repository, Pydantic DTOs, generated OpenAPI. Chosen to be defensible in review, not to avoid Java." },
  { num: "✕", numFill: AMBER, h: "No compiled system dependency", b: "LightGBM and XGBoost link libomp on macOS and fail without Homebrew — for us and for a grader. scikit-learn installs anywhere." },
  { num: "∅", h: "Missingness is signal", b: "An absent bureau score is not a data defect to impute away — it is the defining fact about a thin-file applicant. It reaches the model as NaN." },
], { headSize: 13.5, bodySize: 11 });
cardRow(s, 4.12, 2.5, [
  { num: "☁", h: "Bedrock-ready, honestly labelled", b: "Four providers behind one interface, selected by env var. The Bedrock adapter is wired but never run live — we had no AWS access, and this deck says so." },
  { num: "⚿", numFill: RED, h: "Security posture", b: "No secret has a default; a placeholder JWT secret fails startup. Role-scoped responses omit internals rather than nulling them." },
  { num: "◉", h: "Embeddings run locally", b: "ONNX on CPU: no text leaves the machine, no per-query cost, and deterministic vectors so an audited retrieval can be reproduced later." },
], { headSize: 13.5, bodySize: 11 });
s.addNotes("Each of these is a trade-off with a reason attached. That is what separates a considered build from a generated one.");

// ================= 15b. CONSENT AND DATA FLOW =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "How alternative data legally reaches a lender in India", 0.45, INK, 29);
lede(s, "The Account Aggregator framework is the consented rail this data travels on. Modelling it properly is what separates \u201cwe use alternative data\u201d from a system a regulator would recognise.", 0.98, MUTED, 11.9, 12.5);

const FY = 1.72, FH = 1.15;
[["Applicant", "grants consent, and may revoke it at any time", GREEN_PALE, GREEN],
 ["Account Aggregator", "moves the data and may not read, store or resell it", WHITE, BORDER],
 ["Banks and FIPs", "release only what the consent artefact names", WHITE, BORDER],
 ["Lender (FIU)", "may use it only for the purpose recorded", GREEN_PALE, GREEN]].forEach((b, i) => {
  const w = (W - 3 * 0.42) / 4, x = M + i * (w + 0.42);
  node(s, x, FY, w, FH, b[0], b[2], { fill: b[2], line: b[3], lw: b[3] === GREEN ? 1.25 : 0.75, titleColor: b[3] === GREEN ? GREEN : INK, subSize: 10 });
  s.addText(b[1], { x: x + 0.16, y: FY + 0.44, w: w - 0.32, h: 0.62, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 10.5, color: MUTED, lineSpacing: 13 });
  if (i < 3) arrow(s, x + w + 0.04, FY + FH / 2, x + w + 0.38, FY + FH / 2, "A8B4BC", 1.5);
});

s.addText("THE CONSENT ARTEFACT RECORDS", { x: M, y: 3.18, w: W, h: 0.28, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 10, bold: true, color: GREEN, charSpacing: 1.8 });
[["Purpose", "credit assessment, and nothing else"],
 ["Data types", "only the accounts named"],
 ["Duration", "an expiry, not indefinite"],
 ["Frequency", "how often it may be pulled"],
 ["Revocation", "withdrawable at any time"]].forEach((b, i) => {
  const w = (W - 4 * 0.14) / 5, x = M + i * (w + 0.14);
  node(s, x, 3.52, w, 0.82, b[0], b[1], { titleSize: 11.5, subSize: 9.5 });
});

[["DL-02", "Data collection must be need-based and consented"],
 ["AA-05", "Purpose limitation binds the recipient"],
 ["DPDP-04", "Only the personal data necessary may be collected"],
 ["DPDP-05", "Consent is freely revocable"]].forEach((b, i) => {
  const y = 4.62 + i * 0.5;
  s.addText([{ text: `[${b[0]}]  `, options: { bold: true, color: GREEN, fontFace: BODY } },
             { text: b[1], options: { color: INK } }],
    { x: M, y, w: W, h: 0.44, isTextBox: true, margin: 0, valign: "middle", fontFace: BODY, fontSize: 12.5 });
  s.addShape(pres.ShapeType.line, { x: M, y: y + 0.46, w: W, h: 0, line: { color: BORDER, width: 0.75 } });
});
footnote(s, "The system never receives an identifier: no name, PAN, Aadhaar or phone number, and the API refuses a request that carries one");
s.addNotes("This slide is the India domain knowledge. Most submissions will say they use alternative data; almost none will name the rail it legally travels on or model the consent artefact.");

// ================= 15c. SECURITY AND PRIVACY =================
s = pres.addSlide(); s.background = { color: INK };
s.addText("Security and privacy, by construction", { x: M, y: 0.45, w: W, h: 0.8, isTextBox: true, margin: 0, fontFace: HEAD, fontSize: 32, color: WHITE, valign: "top" });
s.addText("Each of these is a structural property rather than a policy someone has to remember.", { x: M, y: 1.22, w: 11.9, h: 0.32, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, color: INK_TEXT });
[["No identifier can reach a third party", "The prompt is assembled only from the decision object, never the applicant record. There is no code path by which a name, PAN or Aadhaar could be sent to a provider."],
 ["The API refuses data it does not need", "extra=\"forbid\" on the request schema, so an application carrying a PAN is rejected with a 422 rather than quietly accepted and ignored."],
 ["No secret has a usable default", "A placeholder JWT secret fails startup. Demo passwords absent from the environment are generated per run and printed once."],
 ["Roles omit rather than blank", "An applicant response carries no trace of the probability, threshold, contributions or provenance \u2014 the fields are absent, not nulled."],
 ["Failures do not leak internals", "Unhandled exceptions are logged in full and returned as a bare 500. Stack traces and file paths never cross the HTTP boundary."],
 ["Embeddings never leave the host", "Applicant-facing text is embedded locally through ONNX, so retrieval involves no third-party call at all."]].forEach((b, i) => {
  const col = i % 2, row = Math.floor(i / 2);
  const w = (W - 0.3) / 2, x = M + col * (w + 0.3), y = 1.78 + row * 1.62;
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h: 1.42, rectRadius: 0.09, fill: { color: INK_CARD }, line: { type: "none" } });
  badge(s, x + 0.26, y + 0.22, String(i + 1), GREEN, WHITE);
  s.addText(b[0], { x: x + 0.86, y: y + 0.22, w: w - 1.12, h: 0.4, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13.5, bold: true, color: GREEN_TEXT, valign: "middle" });
  s.addText(b[1], { x: x + 0.26, y: y + 0.68, w: w - 0.52, h: 0.62, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 11, color: INK_TEXT, lineSpacing: 14 });
});
s.addNotes("The phrase that matters is by construction. Every one of these is enforced by the shape of the code, not by a rule someone has to follow.");

// ================= 16. LIMITS =================
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "What this is not");
[["The population is synthetic", "Absolute figures describe this population, not the Indian credit market. The direction of the result follows from a mechanism — bureau absence correlates with gender and region while true risk does not — that is well documented in the real world."],
 ["The regulatory corpus is paraphrased", "Plain-language summaries citing real instruments, labelled as such. Production would ingest the official texts with per-clause identifiers; the retrieval machinery is unchanged by that substitution."],
 ["The cloud layer is designed, not provisioned", "No live deployment, and the Bedrock adapter has never run against a real endpoint. Both are stated in the README rather than implied away."]].forEach((b, i) => {
  const y = 1.55 + i * 1.62;
  card(s, M, y, W, 1.35, NEUTRAL, null);
  badge(s, M + 0.3, y + 0.22, String(i + 1), AMBER, WHITE);
  s.addText(b[0], { x: M + 0.95, y: y + 0.22, w: W - 1.3, h: 0.38, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 15, bold: true, color: INK });
  s.addText(b[1], { x: M + 0.95, y: y + 0.62, w: W - 1.3, h: 0.62, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 12, color: MUTED, lineSpacing: 16 });
});
s.addNotes("Saying this out loud is a strength. Every limitation here is one a reviewer would find in ten minutes anyway.");

// ================= 17. NEXT =================
s = pres.addSlide(); s.background = { color: INK };
s.addText("WHERE THIS GOES NEXT", { x: M, y: 0.55, w: W, h: 0.3, isTextBox: true, margin: 0,
  fontFace: BODY, fontSize: 11.5, bold: true, color: GREEN_TEXT, charSpacing: 2.5 });
s.addText("Five things I would do with a real portfolio", { x: M, y: 1.0, w: 11.4, h: 0.8, isTextBox: true, margin: 0,
  fontFace: HEAD, fontSize: 34, color: WHITE, valign: "top" });
[["Re-run the inclusion experiment on real data.", "The finding is a hypothesis with supporting evidence, not a measurement of the market."],
 ["Handle reject inference.", "Repayment is only observed for those past policy approved, so the training population is censored."],
 ["Monitor alternative-data drift.", "UPI behaviour shifts within a quarter; bureau data does not."],
 ["Champion/challenger against a WOE scorecard.", "The format Indian credit teams actually review and sign off."],
 ["Ingest official regulatory texts.", "With per-clause identifiers and effective dates, so citations carry versions."]].forEach((b, i) => {
  const y = 2.05 + i * 0.66;
  badge(s, M, y, String(i + 1), GREEN, WHITE);
  s.addText([{ text: b[0] + "  ", options: { bold: true, color: WHITE } }, { text: b[1], options: { color: INK_TEXT } }],
    { x: M + 0.62, y: y + 0.02, w: 11.2, h: 0.55, isTextBox: true, margin: 0, fontFace: BODY, fontSize: 13, lineSpacing: 18, valign: "top" });
});
["The decision is auditable", "The reasons are exact", "The applicant gets a plan"].forEach((t, i) => {
  const w = 3.2, x = M + i * (w + 0.25);
  s.addShape(pres.ShapeType.roundRect, { x, y: 5.7, w, h: 0.55, rectRadius: 0.27, fill: { color: "134034" }, line: { type: "none" } });
  s.addText(t, { x, y: 5.7, w, h: 0.55, isTextBox: true, margin: 0, align: "center", valign: "middle",
    fontFace: BODY, fontSize: 13, bold: true, color: GREEN_TEXT });
});
s.addNotes("Close on the three chips. They are the promise of the system in nine words.");

pres.writeFile({ fileName: "/Users/apple/pratyaya/docs/Pratyaya-Synchrony-Hackathon.pptx" })
  .then(f => console.log("written:", f));

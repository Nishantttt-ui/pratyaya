import type { Assessment } from "../types";

/**
 * How this decision was produced.
 *
 * Only facts this response actually carries are shown. The deterministic
 * stages are labelled by what they are rather than given an invented
 * per-request duration, and the one real measurement — how long the language
 * model took — comes from the provenance block. Making the ordering visible is
 * the point: everything to the left of the last cell completed before any model
 * was called.
 */
export function Pipeline({ result }: { result: Assessment }) {
  const p = result.provenance;
  if (!p) return null;
  const generated = p.narrative_source === "llm";

  return (
    <div className="pipeline">
      <div className="step det">
        <div className="label">Decision</div>
        <div className="val">deterministic</div>
      </div>
      <div className="step det">
        <div className="label">Reason codes</div>
        <div className="val">exact SHAP</div>
      </div>
      <div className="step det">
        <div className="label">Provisions</div>
        <div className="val">{result.citations.length} retrieved</div>
      </div>
      <div className={generated ? "step llm" : "step det"}>
        <div className="label">Wording</div>
        <div className="val">
          {generated ? `${p.provider} · ${(p.latency_ms ?? 0) / 1000}s` : "deterministic notice"}
        </div>
      </div>
    </div>
  );
}

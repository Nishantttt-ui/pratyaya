import type { Assessment } from "../types";
import { ReasonBars } from "./ReasonBars";
import { RecourseList } from "./RecourseList";
import { Citations } from "./Citations";

/**
 * Risk gauge.
 *
 * Shown only to underwriters. An applicant is deliberately never shown a raw
 * probability: it invites argument with a number they cannot audit, while the
 * reason codes and recourse tell them everything they can actually act on.
 */
function RiskGauge({ pd, threshold }: { pd: number; threshold: number }) {
  const scale = Math.max(pd, threshold) * 1.6;
  return (
    <div className="gauge">
      <div className="track">
        <div className="fill" style={{ width: `${Math.min(100, (pd / scale) * 100)}%`, background: pd > threshold ? "var(--warn)" : "var(--accent)" }} />
        <div className="marker" style={{ left: `${Math.min(100, (threshold / scale) * 100)}%` }} title="approval threshold" />
      </div>
      <div className="legend">
        <span>probability of default <strong>{(pd * 100).toFixed(2)}%</strong></span>
        <span>cut-off {(threshold * 100).toFixed(2)}%</span>
      </div>
    </div>
  );
}

export function DecisionPanel({ result }: { result: Assessment }) {
  const approved = result.decision === "APPROVE";
  const underwriter = result.probability_of_default !== null;

  return (
    <div>
      <div className="card">
        <div className="verdict">
          <span className={`badge ${approved ? "approve" : "decline"}`}>
            {approved ? "Approved" : "Not approved"}
          </span>
          <span className="muted">{result.applicant_id}</span>
          {result.is_new_to_credit && <span className="chip warn">assessed without a bureau record</span>}
          {result.provenance && (
            <span className="chip" title={result.provenance.fallback_reason ?? ""}>
              {result.provenance.narrative_source === "llm"
                ? `narrated by ${result.provenance.provider}`
                : "deterministic notice"}
            </span>
          )}
        </div>

        {underwriter && (
          <RiskGauge pd={result.probability_of_default!} threshold={result.threshold!} />
        )}

        <div className="narrative" style={{ marginTop: 14 }}>{result.narrative}</div>
      </div>

      <ReasonBars reasons={result.adverse_reasons} title="Counted against this application" />
      <ReasonBars reasons={result.favourable_reasons} title="Counted in favour" />
      <RecourseList options={result.recourse} />
      <Citations citations={result.citations} />

      {result.provenance && !result.provenance.guardrail_passed && (
        <div className="card">
          <h3>Guardrail intervened</h3>
          <p style={{ marginTop: 0 }}>
            The generated wording was rejected and the deterministic notice was
            served instead.
          </p>
          <div className="row">
            {result.provenance.guardrail_violations.map((violation) => (
              <span key={violation} className="chip warn">{violation.replace(/_/g, " ")}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

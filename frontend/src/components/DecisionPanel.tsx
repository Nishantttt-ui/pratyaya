import type { Assessment } from "../types";
import { Letter } from "./Letter";
import { Pipeline } from "./Pipeline";
import { ReasonBars } from "./ReasonBars";
import { RecourseList } from "./RecourseList";
import { Citations } from "./Citations";

/**
 * Risk gauge — underwriter only.
 *
 * An applicant is deliberately never shown a raw probability. It invites an
 * argument with a number they have no way to audit, while the reason codes and
 * the recourse tell them everything they can actually act on.
 */
function RiskGauge({ pd, threshold }: { pd: number; threshold: number }) {
  const scale = Math.max(pd, threshold) * 1.7;
  const over = pd > threshold;
  return (
    <div className="gauge">
      <div className="readout">
        <span className={`pd ${over ? "over" : "under"}`}>{(pd * 100).toFixed(2)}%</span>
        <span className="cut">probability of default</span>
      </div>
      <div className="track">
        <div
          className="fill"
          style={{
            width: `${Math.min(100, (pd / scale) * 100)}%`,
            background: over ? "var(--warn)" : "var(--favourable)",
          }}
        />
        <div className="marker" style={{ left: `${Math.min(100, (threshold / scale) * 100)}%` }} />
      </div>
      <div className="scale">
        <span>0%</span>
        <span>cut-off {(threshold * 100).toFixed(2)}%</span>
      </div>
    </div>
  );
}

export function DecisionPanel({ result }: { result: Assessment }) {
  const approved = result.decision === "APPROVE";
  const underwriter = result.probability_of_default !== null;

  return (
    <div className="fade-in">
      <div className="card">
        <div className="verdict">
          <div className="outcome">
            <div className="eyebrow">{result.applicant_id}</div>
            <h2 className={approved ? "approve" : "decline"}>
              {approved ? "Approved" : "Not approved at this time"}
            </h2>
            <div className="tags">
              {result.is_new_to_credit && (
                <span className="chip warn">assessed without a bureau record</span>
              )}
              {result.provenance && (
                <span className="chip">
                  {result.provenance.narrative_source === "llm"
                    ? `narrated by ${result.provenance.provider}`
                    : "deterministic notice"}
                </span>
              )}
            </div>
          </div>
          {underwriter && (
            <RiskGauge pd={result.probability_of_default!} threshold={result.threshold!} />
          )}
        </div>

        <Letter text={result.narrative} />
        <Pipeline result={result} />
      </div>

      <ReasonBars reasons={result.adverse_reasons} title="Counted against this application" />
      <ReasonBars reasons={result.favourable_reasons} title="Counted in favour" />
      <RecourseList options={result.recourse} />
      <Citations citations={result.citations} />

      {result.provenance && !result.provenance.guardrail_passed && (
        <div className="card">
          <h3>A guardrail intervened</h3>
          <p style={{ marginTop: 0, fontSize: 14 }}>
            The generated wording was rejected and the deterministic notice was served
            instead. The decision, the reasons, the recourse and the citations are
            unaffected — a guardrail removes the wording, never the substance.
          </p>
          <div className="row">
            {result.provenance.guardrail_violations.map((v) => (
              <span key={v} className="chip warn">{v.replace(/_/g, " ")}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

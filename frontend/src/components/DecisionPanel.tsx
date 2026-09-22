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
/**
 * Isotonic calibration maps its lowest bin to the default rate observed in
 * that bin, which is exactly zero when none of those applicants defaulted.
 * Printing "0.00%" would overclaim: the rate is below what the calibration
 * set can resolve, not known to be nil. The same holds at the top of the
 * range. Both ends are reported as bounds instead.
 */
function formatPd(pd: number): string {
  const pct = pd * 100;
  if (pct < 0.01) return "<0.01%";
  if (pct > 99.99) return ">99.99%";
  return `${pct.toFixed(2)}%`;
}

function RiskGauge({ pd, threshold }: { pd: number; threshold: number }) {
  const scale = Math.max(pd, threshold) * 1.7;
  const over = pd > threshold;
  return (
    <div className="gauge">
      <div className="readout">
        <span className={`pd ${over ? "over" : "under"}`}>{formatPd(pd)}</span>
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
  // Absent, not null, for an applicant - so test the type rather than
  // comparing to null, which `undefined` passes.
  const underwriter = typeof result.probability_of_default === "number";

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

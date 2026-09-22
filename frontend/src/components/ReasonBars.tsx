import type { ReasonCode } from "../types";
import { formatValue } from "../format";

/**
 * Reason codes as proportional bars.
 *
 * Bar width is scaled against the largest absolute contribution in the set, so
 * the visual ranking matches the model's real attribution rather than
 * flattening every factor to look equally important. An applicant is not shown
 * the signed contribution — it is a log-odds figure they cannot audit — so for
 * that view the bars fall back to rank order, which is the same ordering.
 */
export function ReasonBars({ reasons, title }: { reasons: ReasonCode[]; title: string }) {
  if (reasons.length === 0) return null;
  const scale = Math.max(...reasons.map((r) => Math.abs(r.contribution ?? 0)), 1e-9);
  // Absent for an applicant, so test the type: `undefined !== null` is true,
  // which would scale every bar off a missing contribution and collapse
  // them all to the 3% floor instead of using the rank ladder below.
  const hasContributions = reasons.some((r) => typeof r.contribution === "number");

  return (
    <div className="card">
      <h3>{title}</h3>
      {reasons.map((reason) => {
        const width = hasContributions
          ? `${Math.max(3, (Math.abs(reason.contribution ?? 0) / scale) * 100)}%`
          : `${100 - (reason.rank - 1) * 18}%`;
        return (
          <div key={reason.feature} className={`reason ${reason.direction}`}>
            <div className="top">
              <span className="rank">{reason.rank}</span>
              <span className="name">{reason.label}</span>
              <span className="val">{formatValue(reason.feature, reason.value)}</span>
              {typeof reason.contribution === "number" && (
                <span className="contrib">
                  {reason.contribution > 0 ? "+" : ""}{reason.contribution.toFixed(3)}
                </span>
              )}
            </div>
            <div className="bar"><span style={{ width }} /></div>
          </div>
        );
      })}
    </div>
  );
}

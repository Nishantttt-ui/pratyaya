import type { ReasonCode } from "../types";
import { formatValue } from "../format";

/**
 * Reason codes as proportional bars.
 *
 * Bar width is scaled against the largest absolute contribution in the set, so
 * the visual ranking matches the model's actual attribution rather than
 * flattening every factor to look equally important.
 */
export function ReasonBars({ reasons, title }: { reasons: ReasonCode[]; title: string }) {
  if (reasons.length === 0) return null;
  const scale = Math.max(...reasons.map((r) => Math.abs(r.contribution ?? 1)), 1e-9);

  return (
    <div className="card">
      <h3>{title}</h3>
      {reasons.map((reason) => {
        const width = reason.contribution === null
          ? `${100 - (reason.rank - 1) * 16}%`
          : `${Math.max(4, (Math.abs(reason.contribution) / scale) * 100)}%`;
        return (
          <div key={reason.feature} className={`reason ${reason.direction}`}>
            <div>
              <div className="name">{reason.rank}. {reason.label}</div>
              <div className="val">{formatValue(reason.feature, reason.value)}</div>
            </div>
            {reason.contribution !== null && (
              <div className="contrib">{reason.contribution > 0 ? "+" : ""}{reason.contribution.toFixed(3)}</div>
            )}
            <div className="bar"><span style={{ width }} /></div>
          </div>
        );
      })}
    </div>
  );
}

import type { RecourseOption } from "../types";
import { EFFORT_LABEL, formatValue } from "../format";

export function RecourseList({ options }: { options: RecourseOption[] }) {
  if (options.length === 0) return null;
  return (
    <div className="card">
      <h3>What would change this decision</h3>
      <p className="muted" style={{ marginTop: -6, marginBottom: 14, fontSize: 13.5 }}>
        Each of these on its own would have been enough. They are counterfactuals
        re-scored by the same model that made the decision — not a promise of approval.
      </p>
      {options.map((option) => (
        <div key={option.feature} className="recourse">
          <div className="move">
            <span className="label">{option.label}</span>
            <span className="from">{formatValue(option.feature, option.current_value)}</span>
            <span className="arrow">→</span>
            <span className="to">{formatValue(option.feature, option.target_value)}</span>
          </div>
          {option.hint && <div className="hint">{option.hint}</div>}
          <div className="row">
            <span className="chip">{EFFORT_LABEL[option.effort] ?? option.effort}</span>
            {typeof option.projected_pd === "number" && (
              <span className="chip mono">projected PD {(option.projected_pd * 100).toFixed(1)}%</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

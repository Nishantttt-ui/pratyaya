import type { Applicant } from "../types";
import { formatValue } from "../format";

export function ApplicantList({
  applicants, selected, onSelect,
}: {
  applicants: Applicant[];
  selected: number | null;
  onSelect: (index: number) => void;
}) {
  return (
    <div className="stack">
      {applicants.map((applicant, index) => {
        const ntc = applicant.is_new_to_credit === 1;
        return (
          <button
            key={String(applicant.applicant_id ?? index)}
            className={`applicant ${selected === index ? "selected" : ""}`}
            onClick={() => onSelect(index)}
            aria-pressed={selected === index}
          >
            <div className="who">
              {String(applicant.applicant_id)} · {String(applicant.age)}y ·{" "}
              {String(applicant.employment_type).replace(/_/g, " ")}
            </div>
            <div className="meta">
              wants {formatValue("loan_amount_requested", applicant.loan_amount_requested as number)}
              {" · earns "}
              {formatValue("monthly_income_declared", applicant.monthly_income_declared as number)}/mo
            </div>
            <div style={{ marginTop: 6 }}>
              <span className={`chip ${ntc ? "warn" : ""}`}>
                {ntc ? "no bureau record" : `bureau ${Math.round(applicant.bureau_score as number)}`}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

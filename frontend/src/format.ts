const RUPEES = new Set([
  "monthly_income_declared", "loan_amount_requested", "avg_balance_3m", "upi_inflow_median",
]);
const PERCENT = new Set([
  "utility_ontime_ratio", "recharge_regularity", "salary_regularity", "emi_to_income",
]);
const MONTHS = new Set(["loan_tenure_months", "mobile_tenure_months", "credit_history_months"]);

export function formatValue(feature: string, value: number | string | null): string {
  if (value === null || value === undefined) return "not available";
  if (typeof value === "string") return value.replace(/_/g, " ");
  if (RUPEES.has(feature)) return `₹${Math.round(value).toLocaleString("en-IN")}`;
  if (PERCENT.has(feature)) return `${Math.round(value * 100)}%`;
  if (MONTHS.has(feature)) return `${Math.round(value)} months`;
  if (feature === "days_balance_below_500") return `${Math.round(value)} of 90 days`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export const EFFORT_LABEL: Record<string, string> = {
  immediate: "change this application",
  short_term: "1–3 months",
  long_term: "6+ months",
};

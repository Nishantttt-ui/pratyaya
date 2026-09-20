export type Decision = "APPROVE" | "DECLINE";
export type Role = "applicant" | "underwriter";

export interface ReasonCode {
  rank: number;
  feature: string;
  label: string;
  phrase: string;
  value: number | string | null;
  direction: "adverse" | "favourable";
  actionability: string;
  /** Underwriter view only; null for applicants. */
  contribution: number | null;
}

export interface RecourseOption {
  feature: string;
  label: string;
  current_value: number;
  target_value: number;
  direction: string;
  effort: string;
  hint: string | null;
  projected_pd: number | null;
}

export interface Citation {
  chunk_id: string;
  heading: string;
  instrument: string;
  citation: string;
  text: string;
  score: number | null;
}

export interface Provenance {
  narrative_source: string;
  provider: string | null;
  model: string | null;
  latency_ms: number | null;
  guardrail_passed: boolean;
  guardrail_violations: string[];
  fallback_reason: string | null;
}

export interface Assessment {
  applicant_id: string;
  decision: Decision;
  is_new_to_credit: boolean;
  adverse_reasons: ReasonCode[];
  favourable_reasons: ReasonCode[];
  recourse: RecourseOption[];
  citations: Citation[];
  narrative: string;
  probability_of_default: number | null;
  threshold: number | null;
  deterministic_notice: string | null;
  provenance: Provenance | null;
}

/** A row from the sample endpoint: raw applicant features. */
export type Applicant = Record<string, number | string | null>;

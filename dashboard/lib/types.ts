// ---------------------------------------------------------------------------
// Ninja Code Guard – shared TypeScript types
// Mirror the Pydantic models in app/models/findings.py
// ---------------------------------------------------------------------------

export type Severity = "critical" | "high" | "medium" | "low";
export type AgentKind = "security" | "performance" | "style";
export type Recommendation = "approve" | "request_changes" | "block";

/** A single finding produced by a domain agent. */
export interface Finding {
  agent: AgentKind;
  file_path: string;
  line_start: number;
  line_end: number;
  severity: Severity;
  category: string;
  title: string;
  description: string;
  suggested_fix: string;
  cwe_id: string | null;
  confidence: number; // 0.0 – 1.0
}

/** Final synthesized review output from the Synthesizer Agent. */
export interface SynthesizedReview {
  health_score: number; // 0 – 100
  executive_summary: string;
  recommendation: Recommendation;
  findings: Finding[];
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  duration_ms: number;
}

/** Database record for a completed PR review. */
export interface PRReviewRecord {
  id: string; // UUID
  repo_full_name: string;
  pr_number: number;
  commit_sha: string;
  health_score: number; // 0 – 100
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  summary: string;
  findings: Finding[];
  duration_ms: number;
  created_at?: string; // ISO date
}

/** Aggregate statistics for a repository. */
export interface RepoStats {
  repo_full_name: string;
  total_reviews: number;
  average_health_score: number;
  total_findings: number;
  recent_scores: number[]; // chronological, most-recent last
  top_categories: { category: string; count: number }[];
}

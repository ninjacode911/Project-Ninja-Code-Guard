// ---------------------------------------------------------------------------
// Ninja Code Guard – API client + mock data for development
// ---------------------------------------------------------------------------

import type {
  Finding,
  PRReviewRecord,
  RepoStats,
  SynthesizedReview,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// ---------------------------------------------------------------------------
// Generic fetcher
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string): Promise<T> {
  if (!API_URL) return null as unknown as T; // fall through to mock
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Mock findings
// ---------------------------------------------------------------------------

const MOCK_FINDINGS: Finding[] = [
  {
    agent: "security",
    file_path: "src/auth/login.ts",
    line_start: 42,
    line_end: 48,
    severity: "critical",
    category: "SQL Injection",
    title: "Unsanitized user input in SQL query",
    description:
      "User-supplied `username` is interpolated directly into a SQL query string without parameterisation. An attacker can inject arbitrary SQL to bypass authentication or exfiltrate data.",
    suggested_fix:
      'Use parameterised queries: `db.query("SELECT * FROM users WHERE username = $1", [username])`',
    cwe_id: "CWE-89",
    confidence: 0.95,
  },
  {
    agent: "security",
    file_path: "src/api/middleware.ts",
    line_start: 15,
    line_end: 22,
    severity: "high",
    category: "Authentication",
    title: "Missing JWT expiry validation",
    description:
      "The JWT verification step does not check the `exp` claim, allowing expired tokens to grant access indefinitely.",
    suggested_fix:
      "Pass `{ algorithms: ['HS256'], ignoreExpiration: false }` to `jwt.verify()`.",
    cwe_id: "CWE-613",
    confidence: 0.88,
  },
  {
    agent: "performance",
    file_path: "src/services/dataLoader.ts",
    line_start: 78,
    line_end: 95,
    severity: "high",
    category: "N+1 Query",
    title: "Sequential database queries inside loop",
    description:
      "Each iteration of the `for` loop executes a separate `SELECT` query. For 1 000 records this produces 1 001 queries instead of a single batch query.",
    suggested_fix:
      "Collect IDs first, then fetch all records in a single `WHERE id IN (...)` query.",
    cwe_id: null,
    confidence: 0.92,
  },
  {
    agent: "performance",
    file_path: "src/utils/imageProcessor.ts",
    line_start: 12,
    line_end: 30,
    severity: "medium",
    category: "Memory",
    title: "Large buffer allocated synchronously",
    description:
      "A 50 MB buffer is allocated on the main thread for image processing. This can cause the event loop to stall and trigger OOM errors under load.",
    suggested_fix:
      "Stream the image in chunks or offload processing to a worker thread.",
    cwe_id: null,
    confidence: 0.78,
  },
  {
    agent: "style",
    file_path: "src/components/Dashboard.tsx",
    line_start: 5,
    line_end: 5,
    severity: "low",
    category: "Naming",
    title: "Component file uses default export without matching name",
    description:
      "The file exports `export default function Dash()` which does not match the filename `Dashboard.tsx`. This hurts discoverability in IDEs and stack traces.",
    suggested_fix:
      "Rename the function to `Dashboard` or rename the file to `Dash.tsx`.",
    cwe_id: null,
    confidence: 0.99,
  },
  {
    agent: "style",
    file_path: "src/hooks/useData.ts",
    line_start: 18,
    line_end: 45,
    severity: "low",
    category: "Complexity",
    title: "Function exceeds recommended cyclomatic complexity",
    description:
      "The `transformPayload` function has a cyclomatic complexity of 14. Consider extracting branches into helper functions for readability.",
    suggested_fix:
      "Extract the nested conditionals into separate pure functions (e.g. `normaliseDate`, `mapStatus`).",
    cwe_id: null,
    confidence: 0.85,
  },
  {
    agent: "security",
    file_path: "src/config/cors.ts",
    line_start: 3,
    line_end: 8,
    severity: "medium",
    category: "CORS",
    title: "Wildcard CORS origin in production config",
    description:
      "The CORS configuration uses `origin: '*'` which allows any website to make credentialed requests to the API.",
    suggested_fix:
      "Restrict the origin to your frontend domain(s): `origin: ['https://app.example.com']`.",
    cwe_id: "CWE-942",
    confidence: 0.91,
  },
];

// ---------------------------------------------------------------------------
// Mock PR review records
// ---------------------------------------------------------------------------

function makeMockReviews(
  repo: string,
  count: number
): PRReviewRecord[] {
  const base = Date.now();
  return Array.from({ length: count }, (_, i) => {
    const score = Math.min(100, Math.max(35, 72 + Math.round(Math.sin(i) * 18)));
    const crit = score < 50 ? 2 : score < 70 ? 1 : 0;
    const high = Math.max(0, 3 - Math.floor(score / 30));
    const med = Math.max(0, 4 - Math.floor(score / 25));
    const low = 2;
    return {
      id: `pr-${repo}-${i}`,
      repo_full_name: repo,
      pr_number: 100 + count - i,
      commit_sha: `abc${String(i).padStart(4, "0")}`,
      health_score: score,
      critical_count: crit,
      high_count: high,
      medium_count: med,
      low_count: low,
      summary: `Automated review for PR #${100 + count - i}`,
      findings: MOCK_FINDINGS.slice(0, 3 + (i % 4)),
      duration_ms: 1200 + i * 300,
      created_at: new Date(base - i * 86_400_000).toISOString(),
    };
  });
}

// ---------------------------------------------------------------------------
// Mock repos
// ---------------------------------------------------------------------------

export interface MockRepo {
  owner: string;
  repo: string;
  full_name: string;
  health_score: number;
  open_prs: number;
  last_review: string;
}

export const MOCK_REPOS: MockRepo[] = [
  {
    owner: "acme",
    repo: "web-app",
    full_name: "acme/web-app",
    health_score: 87,
    open_prs: 4,
    last_review: "2 hours ago",
  },
  {
    owner: "acme",
    repo: "api-server",
    full_name: "acme/api-server",
    health_score: 64,
    open_prs: 7,
    last_review: "35 minutes ago",
  },
  {
    owner: "acme",
    repo: "mobile-sdk",
    full_name: "acme/mobile-sdk",
    health_score: 93,
    open_prs: 2,
    last_review: "1 day ago",
  },
  {
    owner: "acme",
    repo: "infra-tools",
    full_name: "acme/infra-tools",
    health_score: 51,
    open_prs: 11,
    last_review: "10 minutes ago",
  },
];

// ---------------------------------------------------------------------------
// Mock synthesized review
// ---------------------------------------------------------------------------

const MOCK_SYNTH_REVIEW: SynthesizedReview = {
  health_score: 64,
  executive_summary:
    "This PR introduces several new API endpoints and a database migration. While the feature logic is sound, there are critical security issues — most notably an SQL injection vulnerability in the login flow — and performance concerns around N+1 queries in the data-loading layer. Style issues are minor but should be addressed for long-term maintainability.",
  recommendation: "request_changes",
  findings: MOCK_FINDINGS,
  critical_count: 1,
  high_count: 2,
  medium_count: 2,
  low_count: 2,
  duration_ms: 3420,
};

// ---------------------------------------------------------------------------
// Public API functions
// ---------------------------------------------------------------------------

export async function getRepoReviews(
  owner: string,
  repo: string
): Promise<PRReviewRecord[]> {
  try {
    if (API_URL) return await apiFetch(`/repos/${owner}/${repo}/reviews`);
  } catch {
    /* fall through to mock */
  }
  return makeMockReviews(`${owner}/${repo}`, 10);
}

export async function getReviewDetail(
  owner: string,
  repo: string,
  prNumber: number
): Promise<{ review: SynthesizedReview; record: PRReviewRecord }> {
  try {
    if (API_URL)
      return await apiFetch(`/repos/${owner}/${repo}/prs/${prNumber}`);
  } catch {
    /* fall through to mock */
  }
  const records = makeMockReviews(`${owner}/${repo}`, 10);
  const record =
    records.find((r) => r.pr_number === prNumber) ?? records[0];
  return {
    review: { ...MOCK_SYNTH_REVIEW, health_score: record.health_score },
    record,
  };
}

export async function getRepoStats(
  owner: string,
  repo: string
): Promise<RepoStats> {
  try {
    if (API_URL) return await apiFetch(`/repos/${owner}/${repo}/stats`);
  } catch {
    /* fall through to mock */
  }
  const reviews = makeMockReviews(`${owner}/${repo}`, 10);
  const scores = reviews.map((r) => r.health_score).reverse();
  return {
    repo_full_name: `${owner}/${repo}`,
    total_reviews: reviews.length,
    average_health_score: Math.round(
      scores.reduce((a, b) => a + b, 0) / scores.length
    ),
    total_findings: reviews.reduce((s, r) => s + r.findings.length, 0),
    recent_scores: scores,
    top_categories: [
      { category: "SQL Injection", count: 4 },
      { category: "N+1 Query", count: 3 },
      { category: "Naming", count: 6 },
      { category: "Authentication", count: 2 },
      { category: "Complexity", count: 5 },
    ],
  };
}

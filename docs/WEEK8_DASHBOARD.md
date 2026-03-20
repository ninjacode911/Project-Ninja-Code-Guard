# Week 8: Next.js Dashboard — Detailed Documentation

> **Goal:** Build a dark-themed analytics dashboard for Ninja Code Guard with Health Score visualizations, findings tables, trend charts, and agent breakdowns.
> **Status:** Complete — Running locally with mock data, ready for Vercel deployment
> **Date:** 2026-03-20
> **Stack:** Next.js App Router, TypeScript, Tailwind CSS, Recharts
> **Pages:** Home (repo overview), Repo detail (trends + PR list), PR detail (findings)

---

## What We Built

Week 8 creates the frontend analytics dashboard — a Next.js application that gives developers
and team leads a visual overview of code quality across all monitored repositories.

The dashboard is a separate deployment from the FastAPI backend. The backend runs on Render
and handles webhooks + reviews. The dashboard runs on Vercel and reads review data via API
calls to the backend. In development, it uses realistic mock data so we can build and style
components without needing a live database.

```
                          ┌─────────────────────────────┐
                          │      Vercel (Dashboard)      │
                          │  Next.js App Router          │
                          │  ┌──────────────────────┐    │
  Developer's ──────────▶ │  │ /                    │    │
  Browser                 │  │  Repo overview cards │    │
                          │  │  Health score pills  │    │
                          │  ├──────────────────────┤    │
                          │  │ /repos/:owner/:repo  │    │
                          │  │  Trend chart         │    │
                          │  │  Agent breakdown     │    │
                          │  │  PR review table     │    │
                          │  ├──────────────────────┤    │
                          │  │ /repos/.../prs/:num  │    │
                          │  │  Health score ring   │    │
                          │  │  Executive summary   │    │
                          │  │  Findings table      │    │
                          │  └──────────┬───────────┘    │
                          │             │ API calls      │
                          └─────────────┼────────────────┘
                                        │
                                        ▼
                          ┌─────────────────────────────┐
                          │     Render (Backend)         │
                          │  FastAPI                     │
                          │  /api/repos/.../reviews      │
                          │  /api/repos/.../stats        │
                          │         │                    │
                          │         ▼                    │
                          │  Neon Postgres               │
                          │  (pr_reviews table)          │
                          └─────────────────────────────┘
```

---

## Step-by-Step Implementation Log

### Step 1: Initialize the Next.js Project

**What we did:** Created a new Next.js application inside the `dashboard/` directory.

```bash
cd dashboard
npx create-next-app@latest . --typescript --tailwind --app --src-dir=false
```

**Configuration choices:**
| Option | Choice | Reason |
|--------|--------|--------|
| TypeScript | Yes | Type safety matching Python Pydantic models |
| Tailwind CSS | Yes | Utility-first CSS, perfect for dark themes |
| App Router | Yes | Server components by default, async data fetching |
| `src/` directory | No | Simpler structure for a small project |

**App Router vs Pages Router:**
We chose the App Router (introduced in Next.js 13) because it offers:
- **Server Components by default** — pages fetch data on the server, ship zero JS for static content
- **Async components** — `async function RepoPage()` can `await` data directly
- **Layout nesting** — shared header/footer defined once in `layout.tsx`
- **File-based routing** — `app/repos/[owner]/[repo]/page.tsx` creates `/repos/:owner/:repo`

**Interview talking point:** "We use the Next.js App Router with Server Components. The repo
detail page is an async server component that fetches data at request time — no `useEffect`,
no loading spinners for the initial render. Client components like the findings table and
health score ring are explicitly marked with `'use client'` because they need browser APIs
(state, animation, click handlers)."

### Step 2: Define TypeScript Types (dashboard/lib/types.ts)

**What we did:** Created TypeScript interfaces that mirror the Python Pydantic models exactly.

```typescript
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
  id: string;
  repo_full_name: string;
  pr_number: number;
  commit_sha: string;
  health_score: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  summary: string;
  findings: Finding[];
  duration_ms: number;
  created_at?: string;
}

/** Aggregate statistics for a repository. */
export interface RepoStats {
  repo_full_name: string;
  total_reviews: number;
  average_health_score: number;
  total_findings: number;
  recent_scores: number[];
  top_categories: { category: string; count: number }[];
}
```

**Why mirror the Python models?**
- **Type safety across the full stack** — if a field name changes in Python, TypeScript catches it
- **IDE autocomplete** — `finding.severity` auto-suggests valid values
- **Documentation** — the types ARE the API contract

**Key design decision: `cwe_id: string | null`**
In Python, this is `Optional[str]`. In TypeScript, we use `string | null` rather than
`string | undefined` because JSON serialization distinguishes between `null` (explicit
absence) and `undefined` (missing key). The API always returns `null` for findings
without a CWE ID, never omits the key.

**Interview talking point:** "We maintain parallel type definitions in Python (Pydantic)
and TypeScript. This is a deliberate trade-off — we could auto-generate TypeScript types
from the Pydantic schemas using tools like `datamodel-code-generator`, but manual
mirroring keeps both sides readable and avoids a build-time code generation step. For a
team project, we'd add a CI check that validates the types match."

### Step 3: Build the API Client with Mock Fallback (dashboard/lib/api.ts)

**What we did:** Created an API client that fetches from the backend when available, or
falls back to realistic mock data for development.

**The generic fetcher:**
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

async function apiFetch<T>(path: string): Promise<T> {
  if (!API_URL) return null as unknown as T; // fall through to mock
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json() as Promise<T>;
}
```

**Key design decisions:**

1. **`{ next: { revalidate: 60 } }`** — Next.js ISR (Incremental Static Regeneration).
   The first request fetches from the API, then the result is cached for 60 seconds.
   Subsequent requests within that window return the cached version instantly. This
   reduces API load while keeping data reasonably fresh.

2. **Mock fallback pattern:**
```typescript
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
```

This pattern means:
- In development (no `NEXT_PUBLIC_API_URL`): always returns mock data
- In production with API down: gracefully falls back to mock data
- In production with API up: returns real data with 60-second caching

3. **Mock data is realistic, not lorem ipsum:**
```typescript
const MOCK_FINDINGS: Finding[] = [
  {
    agent: "security",
    file_path: "src/auth/login.ts",
    line_start: 42,
    line_end: 48,
    severity: "critical",
    category: "SQL Injection",
    title: "Unsanitized user input in SQL query",
    description: "User-supplied `username` is interpolated directly...",
    suggested_fix: 'Use parameterised queries: `db.query("SELECT...")`',
    cwe_id: "CWE-89",
    confidence: 0.95,
  },
  // ... 6 more realistic findings covering all agents and severities
];
```

**Why realistic mock data?**
- Components look correct with real-world content lengths
- Edge cases are visible (long file paths, multi-line descriptions)
- Designers and PMs can review the UI without a backend
- Screenshots in documentation show representative data

**Mock repos provide the home page data:**
```typescript
export const MOCK_REPOS: MockRepo[] = [
  { owner: "acme", repo: "web-app", full_name: "acme/web-app",
    health_score: 87, open_prs: 4, last_review: "2 hours ago" },
  { owner: "acme", repo: "api-server", full_name: "acme/api-server",
    health_score: 64, open_prs: 7, last_review: "35 minutes ago" },
  { owner: "acme", repo: "mobile-sdk", full_name: "acme/mobile-sdk",
    health_score: 93, open_prs: 2, last_review: "1 day ago" },
  { owner: "acme", repo: "infra-tools", full_name: "acme/infra-tools",
    health_score: 51, open_prs: 11, last_review: "10 minutes ago" },
];
```

These four repos span the full score range: excellent (93), good (87), needs attention (64),
and poor (51). This ensures the color-coded UI elements (green/yellow/red) are all visible.

**Interview talking point:** "The API client uses a try/catch fallback to mock data. In
development, `NEXT_PUBLIC_API_URL` is unset, so we always get mock data — no backend
needed. In production, if the API fails, we degrade gracefully instead of showing an
error page. This is a fail-open pattern — the dashboard always renders something useful."

### Step 4: Create the Root Layout (dashboard/app/layout.tsx)

**What we did:** Built a dark-themed layout with sticky navigation header and footer.

```typescript
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}>
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-100">
        <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-md">
          {/* Navigation */}
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-zinc-800 py-6">
          {/* Footer */}
        </footer>
      </body>
    </html>
  );
}
```

**Dark theme design system:**
| Element | Tailwind Classes | Purpose |
|---------|-----------------|---------|
| Page background | `bg-zinc-950` | Near-black base (#09090b) |
| Primary text | `text-zinc-100` | Off-white for readability |
| Secondary text | `text-zinc-400` | Muted labels and descriptions |
| Card backgrounds | `bg-zinc-900/50` | Slightly lighter, semi-transparent |
| Borders | `border-zinc-800` | Subtle separation lines |
| Header | `bg-zinc-950/80 backdrop-blur-md` | Frosted glass effect |

**Fonts:** Geist Sans for body text, Geist Mono for code and numbers. Both loaded via
`next/font/google` for zero layout shift (no FOUT).

**The `tabular-nums` class:** Used on all numeric displays (health scores, finding counts).
This makes digits fixed-width so numbers don't jitter when they change — essential for the
animated health score ring.

**The layout uses `flex flex-col` with `flex-1` on `<main>`:**
This ensures the footer always sits at the bottom of the viewport, even on short pages.
Without this, a page with little content would have the footer floating in the middle.

### Step 5: Build the HealthScoreRing Component

**What we did:** Created an animated SVG ring that visualizes the 0-100 health score.

This is a `"use client"` component because it uses React state and `requestAnimationFrame`
for smooth animation.

```typescript
export default function HealthScoreRing({
  score,
  size = 180,
  strokeWidth = 12,
  previousScore,
  label,
}: HealthScoreRingProps) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    let raf: number;
    const start = performance.now();
    const duration = 900; // 900ms animation
    const from = 0;
    const to = score;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setAnimatedScore(Math.round(from + (to - from) * ease));
      if (progress < 1) raf = requestAnimationFrame(tick);
    }

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [score]);
```

**How the SVG ring works:**

1. **Two concentric circles:** A background track (dark gray) and a score arc (colored).

2. **`strokeDasharray` + `strokeDashoffset`:** The score arc uses CSS stroke-dash properties
   to draw a partial circle. The circumference is `2 * PI * radius`. Setting
   `strokeDasharray` to the full circumference and `strokeDashoffset` to
   `circumference - (score/100) * circumference` draws exactly `score%` of the circle.

3. **Animation:** The score counts up from 0 to the target using `requestAnimationFrame`
   with an ease-out cubic curve. This creates a satisfying "filling up" animation.

4. **Color coding:**
   ```typescript
   function scoreColor(score: number): string {
     if (score >= 80) return "#22c55e"; // green
     if (score >= 60) return "#eab308"; // yellow
     return "#ef4444";                   // red
   }
   ```

5. **Glow effect:** `filter: drop-shadow(0 0 12px rgba(color, 0.25))` adds a subtle
   colored glow around the ring, reinforcing the score sentiment.

6. **Delta display:** If `previousScore` is provided, shows "+5 pts" or "-3 pts" below
   the score, colored green (improvement) or red (regression).

**Interview talking point:** "The HealthScoreRing is a pure SVG component with a
requestAnimationFrame-based animation. We use strokeDasharray and strokeDashoffset to
draw a partial arc — the same technique used in progress bars and circular gauges. The
ease-out cubic easing makes the animation feel natural: fast start, gentle stop. We
considered using a library like Framer Motion, but for a single animation,
requestAnimationFrame is lighter and gives us precise control."

### Step 6: Build the FindingsTable Component

**What we did:** Created a sortable, expandable table that displays all findings with
inline detail panels.

**Key features:**

1. **Sortable columns:** Click any column header to sort. Click again to reverse.
   ```typescript
   const [sortKey, setSortKey] = useState<SortKey>("severity");
   const [sortAsc, setSortAsc] = useState(true);
   ```
   Default sort is by severity (critical first).

2. **Expand/collapse rows:** Click any row to expand its detail panel showing the full
   description, suggested fix (syntax-highlighted), CWE ID, confidence percentage, and
   line range.
   ```typescript
   const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
   ```
   Only one row can be expanded at a time. Clicking an expanded row collapses it.

3. **Severity sorting uses a numeric lookup:**
   ```typescript
   const SEVERITY_ORDER: Record<Severity, number> = {
     critical: 0, high: 1, medium: 2, low: 3,
   };
   ```
   This ensures "critical" sorts before "high" even though alphabetically "c" < "h".

4. **Agent icons:** Each agent is represented by an icon in the table:
   ```typescript
   const AGENT_ICON: Record<string, string> = {
     security: "lock",
     performance: "lightning",
     style: "pencil",
   };
   ```

5. **CSS grid layout for the expanded row:**
   The main row uses `grid-cols-[100px_70px_1fr_140px_1fr]` for pixel-precise column
   widths. The expanded detail panel spans all 5 columns with `colSpan={5}`.

**Interview talking point:** "The FindingsTable uses a `useMemo`-based sort that recomputes
only when the findings array, sort key, or sort direction changes. The expanded row is a
conditional render inside the same `<tr>` — we use `colSpan={5}` to span the full table
width. This avoids the accessibility issues of injecting extra `<tr>` elements between
data rows."

### Step 7: Build the TrendChart Component

**What we did:** Created a line chart showing health score trends over time using Recharts.

```typescript
export default function TrendChart({ scores, height = 280 }: TrendChartProps) {
  const data = scores.map((score, i) => ({
    review: `#${i + 1}`,
    score,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="review" tick={{ fill: "#71717a", fontSize: 12 }} />
        <YAxis domain={[0, 100]} tick={{ fill: "#71717a", fontSize: 12 }} />
        <Tooltip contentStyle={{ backgroundColor: "#18181b", ... }} />
        <ReferenceLine y={80} stroke="#22c55e" strokeDasharray="6 4"
          label={{ value: "Healthy", fill: "#22c55e" }} />
        <Line type="monotone" dataKey="score" stroke="#a78bfa"
          strokeWidth={2.5} dot={{ r: 4, fill: "#a78bfa" }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

**Design decisions:**

1. **ReferenceLine at y=80:** A dashed green line labeled "Healthy" shows the threshold
   for a good health score. Scores above this line are green; below is yellow/red territory.
   This gives developers a visual target.

2. **Violet accent color (`#a78bfa`):** The line and dots use Tailwind's violet-400. This
   provides visual contrast against the dark background and doesn't clash with the
   red/yellow/green semantic colors used elsewhere.

3. **Dark-themed tooltip:** Custom-styled to match the zinc-based dark theme, not the
   default Recharts white tooltip that would look jarring.

4. **Y-axis domain `[0, 100]`:** Fixed domain ensures scores are always shown in context.
   A PR with score 90 looks different from a PR with score 10, even without other data
   points for comparison.

5. **ResponsiveContainer:** Recharts component that makes the chart fill its parent's width.
   This ensures the chart works on mobile, tablet, and desktop without manual breakpoints.

### Step 8: Build the AgentBreakdown Component

**What we did:** Created three summary cards — one per agent — showing finding counts
and top categories.

```typescript
export default function AgentBreakdown({ findings }: AgentBreakdownProps) {
  const agents: AgentKind[] = ["security", "performance", "style"];

  const stats = agents.map((agent) => {
    const agentFindings = findings.filter((f) => f.agent === agent);
    const catCounts: Record<string, number> = {};
    agentFindings.forEach((f) => {
      catCounts[f.category] = (catCounts[f.category] ?? 0) + 1;
    });
    const topCategory =
      Object.entries(catCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";
    return { agent, count: agentFindings.length, topCategory, meta: AGENT_META[agent] };
  });
```

Each card has:
- **Agent-specific gradient background:** Security (red), Performance (amber), Style (blue)
- **Finding count** in large bold text
- **Top category** — the most frequently flagged issue type for that agent
- **Subtle border** matching the agent's theme color

**The cards use a 3-column responsive grid:**
```
sm:grid-cols-3  →  3 cards side-by-side on tablet+
grid-cols-1     →  stacked vertically on mobile
```

### Step 9: Build the SeverityBadge Component

**What we did:** Created a reusable pill/badge component for severity labels.

```typescript
const CONFIG: Record<Severity, { bg: string; text: string; label: string }> = {
  critical: { bg: "bg-red-500/15", text: "text-red-400", label: "Critical" },
  high: { bg: "bg-orange-500/15", text: "text-orange-400", label: "High" },
  medium: { bg: "bg-yellow-500/15", text: "text-yellow-400", label: "Medium" },
  low: { bg: "bg-zinc-500/15", text: "text-zinc-400", label: "Low" },
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  const c = CONFIG[severity];
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5
      text-xs font-semibold tracking-wide uppercase ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}
```

**Design note:** The background uses 15% opacity of the text color (`/15` modifier in
Tailwind). This creates a subtle tint that's visible on the dark background without
being overwhelming. The badge is `rounded-full` (pill shape) with uppercase text —
a common design pattern for status indicators.

### Step 10: Build the Page Routes

**Three pages were created using Next.js file-based routing:**

#### Page 1: Home — `dashboard/app/page.tsx` (route: `/`)

**What it shows:**
- Hero section with project description
- Stats pills (repos monitored, avg health score, PRs reviewed, issues found)
- Repository cards in a 4-column grid with health score, open PR count, last review time
- "How It Works" section with agent descriptions

**Data source:** `MOCK_REPOS` exported from `api.ts` — no API call needed since repo
list is static in the current implementation.

**Each repo card links to its detail page:**
```typescript
<Link href={`/repos/${repo.owner}/${repo.repo}`}>
```

**Score-based styling:** Cards have colored borders and hover glows based on health score.
A repo with score 93 gets green borders; score 51 gets red borders. The `scoreColor`,
`scoreBorder`, and `scoreGlow` helper functions encapsulate this logic.

#### Page 2: Repo Detail — `dashboard/app/repos/[owner]/[repo]/page.tsx` (route: `/repos/:owner/:repo`)

**What it shows:**
- Breadcrumb navigation (Dashboard / owner/repo)
- Title row with repo name, total reviews, total findings, average score
- Health Score Ring (latest score with delta from previous)
- Trend Chart (health scores over time)
- Agent Breakdown cards (findings per agent)
- Recent PR Reviews table with links to individual PRs

**This is an async Server Component:**
```typescript
export default async function RepoPage({
  params,
}: {
  params: Promise<{ owner: string; repo: string }>;
}) {
  const { owner, repo } = await params;
  const [reviews, stats] = await Promise.all([
    getRepoReviews(owner, repo),
    getRepoStats(owner, repo),
  ]);
```

**Key pattern:** `Promise.all` fetches reviews and stats concurrently. This halves the
data-loading time compared to sequential `await` calls.

#### Page 3: PR Detail — `dashboard/app/repos/[owner]/[repo]/prs/[number]/page.tsx`

**What it shows:**
- Breadcrumb navigation (Dashboard / owner/repo / PR #N)
- PR header with recommendation badge (Approve/Request Changes/Block)
- Health Score Ring
- Executive Summary card
- Severity count cards (Critical/High/Medium/Low)
- Agent Breakdown cards
- Full FindingsTable with expand/collapse

**Recommendation styling:**
```typescript
const RECOMMENDATION_STYLE: Record<Recommendation, { bg: string; text: string; label: string }> = {
  approve:         { bg: "bg-green-500/15",  text: "text-green-400",  label: "Approve" },
  request_changes: { bg: "bg-yellow-500/15", text: "text-yellow-400", label: "Request Changes" },
  block:           { bg: "bg-red-500/15",    text: "text-red-400",    label: "Block" },
};
```

This mirrors the SeverityBadge pattern — a config object maps enum values to visual styles.

---

## Architecture Patterns Used

| Pattern | Where | Why |
|---------|-------|-----|
| **Server Components** | RepoPage, PRReviewPage | Data fetched on server, zero client JS for layout |
| **Client Components** | HealthScoreRing, FindingsTable, TrendChart | Need browser APIs (state, animation, events) |
| **Mock Fallback** | `api.ts` | Develop UI without backend; graceful production degradation |
| **Type Mirroring** | `types.ts` mirrors Python models | Full-stack type safety without code generation |
| **File-Based Routing** | `app/repos/[owner]/[repo]/page.tsx` | URL structure maps to directory structure |
| **Composition** | Pages compose components | Each page assembles pre-built components with different props |
| **Config-driven styling** | SeverityBadge, RECOMMENDATION_STYLE | Visual config in one place, not scattered across JSX |

---

## Responsive Design

The dashboard is fully responsive using Tailwind's breakpoint system:

| Breakpoint | Behavior |
|------------|----------|
| Mobile (< 640px) | Cards stack vertically, table scrolls horizontally, ring centered |
| Tablet (640-1024px) | 2-column grids, side-by-side stats |
| Desktop (> 1024px) | 4-column repo grid, side-by-side ring + chart, full table |

Key responsive patterns:
- `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4` — progressive column count
- `overflow-x-auto` on tables — horizontal scroll on mobile
- `flex flex-col sm:flex-row` — stack-to-row on wider screens
- `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8` — centered content with increasing padding

---

## Files Created in Week 8

| File | Purpose |
|------|---------|
| `dashboard/lib/types.ts` | TypeScript interfaces mirroring Python Pydantic models |
| `dashboard/lib/api.ts` | API client with mock data fallback |
| `dashboard/app/layout.tsx` | Root layout: dark theme, navigation, footer |
| `dashboard/app/page.tsx` | Home page: repo overview cards |
| `dashboard/app/globals.css` | Tailwind base styles |
| `dashboard/app/repos/[owner]/[repo]/page.tsx` | Repo detail: trends, agent breakdown, PR list |
| `dashboard/app/repos/[owner]/[repo]/prs/[number]/page.tsx` | PR detail: findings table, executive summary |
| `dashboard/components/HealthScoreRing.tsx` | Animated SVG ring for health score |
| `dashboard/components/FindingsTable.tsx` | Sortable, expandable findings table |
| `dashboard/components/TrendChart.tsx` | Recharts line chart for score trends |
| `dashboard/components/AgentBreakdown.tsx` | Per-agent summary cards |
| `dashboard/components/SeverityBadge.tsx` | Color-coded severity pill badge |

---

## Interview Talking Points Summary

1. **"Why Next.js and not React + Vite?"**
   "The dashboard needs server-side data fetching (API calls to the backend) and SEO for
   shareable PR review URLs. Next.js App Router gives us server components that fetch data
   at request time without client-side loading spinners. Vite + React would require
   client-side fetching, which means a flash of empty content on every page load."

2. **"How do you handle the backend being down?"**
   "Every API function has a try/catch that falls back to mock data. In development, the
   `NEXT_PUBLIC_API_URL` env var is unset, so we always use mocks. In production, if the
   API returns an error, we degrade gracefully rather than showing an error page. The mock
   data is realistic enough that the dashboard still looks useful."

3. **"Explain the HealthScoreRing animation."**
   "It uses SVG strokeDasharray and strokeDashoffset to draw a partial circle. The animated
   score counts from 0 to the target using requestAnimationFrame with ease-out cubic
   easing — fast start, gentle stop. We track the animated value in React state and update
   the dashoffset on each frame. The color transitions from red to yellow to green at
   threshold boundaries."

4. **"Why TypeScript types instead of auto-generating from the API?"**
   "For a small project, manual type mirroring is simpler and keeps both sides readable.
   For a larger team, we'd use OpenAPI schema generation or a shared protobuf definition.
   The key insight is that the types exist at all — many projects use `any` or untyped
   fetch calls, which means bugs only surface at runtime."

5. **"How does the data flow from backend to dashboard?"**
   "The backend saves reviews to Neon Postgres. The dashboard calls
   `/api/repos/:owner/:repo/reviews` which queries Postgres and returns JSON. Next.js
   caches the response for 60 seconds via ISR (`revalidate: 60`). Components receive
   typed data as props — no prop drilling beyond one level."

---

*Documentation written 2026-03-20 as part of Week 8 completion.*

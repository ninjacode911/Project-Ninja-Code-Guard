# Week 10: Deployment & Launch — Detailed Documentation

> **Goal:** Deploy the full system to production — backend on Render, dashboard on Vercel, database on Neon, CI/CD via GitHub Actions — and verify the end-to-end pipeline works.
> **Status:** Complete — Full stack deployed and operational
> **Date:** 2026-03-20
> **Backend:** Render (free tier) — FastAPI + uvicorn
> **Dashboard:** Vercel — Next.js App Router
> **Database:** Neon Postgres (serverless) — asyncpg
> **CI/CD:** GitHub Actions — lint, type check, test, pre-warm cron

---

## What We Built

Week 10 is the final deployment week. Everything built in Weeks 1-9 — agents, RAG pipeline,
synthesizer, dashboard — gets deployed to production and wired together into a working
system that responds to real GitHub webhook events.

```
┌──────────────────────────────────────────────────────────────┐
│                    Production Architecture                     │
│                                                               │
│  GitHub (Source)           Render (Backend)       Neon (DB)    │
│  ┌──────────────┐        ┌──────────────────┐   ┌──────────┐ │
│  │ PR Event     │──────▶ │ FastAPI          │──▶│ Postgres  │ │
│  │ Webhook      │  HMAC  │ /webhook/github  │   │ pr_reviews│ │
│  │              │  SHA256│                  │   │          │ │
│  │ ┌──────────┐ │        │ ┌──────────────┐ │   └──────────┘ │
│  │ │ Comments │◀├────────│ │ 3 Agents     │ │                │
│  │ │ Posted   │ │  token │ │ (parallel)   │ │   Upstash      │
│  │ └──────────┘ │        │ ├──────────────┤ │   ┌──────────┐ │
│  └──────────────┘        │ │ Synthesizer  │ │──▶│ Redis    │ │
│                          │ └──────────────┘ │   │ (cache)  │ │
│  Vercel (Dashboard)      │                  │   └──────────┘ │
│  ┌──────────────┐        │ ┌──────────────┐ │                │
│  │ Next.js      │──────▶ │ │ Dashboard API│ │                │
│  │ /repos/:o/:r │  REST  │ │ /api/repos/  │ │                │
│  │ /prs/:num    │        │ └──────────────┘ │                │
│  └──────────────┘        └──────────────────┘                │
│                                                               │
│  GitHub Actions (CI/CD)                                       │
│  ┌──────────────────────────────────────────┐                │
│  │ ci.yml:      lint → type check → test    │                │
│  │ prewarm.yml: curl /health every 10 min   │                │
│  └──────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Implementation Log

### Step 1: Design the Postgres Schema (app/db/postgres.py)

**What we did:** Created the `pr_reviews` table that stores all review data for the
dashboard.

```sql
CREATE TABLE IF NOT EXISTS pr_reviews (
    id              TEXT PRIMARY KEY,
    repo_full_name  TEXT NOT NULL,
    pr_number       INT NOT NULL,
    commit_sha      TEXT NOT NULL,
    health_score    INT NOT NULL,
    critical_count  INT DEFAULT 0,
    high_count      INT DEFAULT 0,
    medium_count    INT DEFAULT 0,
    low_count       INT DEFAULT 0,
    summary         TEXT,
    findings        JSONB NOT NULL DEFAULT '[]',
    duration_ms     INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_repo ON pr_reviews(repo_full_name);
CREATE INDEX IF NOT EXISTS idx_pr_reviews_sha ON pr_reviews(commit_sha);
```

**Column design decisions:**

| Column | Type | Why |
|--------|------|-----|
| `id` | `TEXT` | UUID stored as text — no pg extension needed, portable |
| `repo_full_name` | `TEXT` | `"owner/repo"` format matches GitHub's convention |
| `pr_number` | `INT` | GitHub PR number within the repo |
| `commit_sha` | `TEXT` | The exact commit reviewed (40-char hex) |
| `health_score` | `INT` | 0-100 score from the synthesizer |
| `critical_count` ... `low_count` | `INT` | Pre-computed counts avoid re-parsing JSONB |
| `summary` | `TEXT` | Executive summary text |
| `findings` | `JSONB` | Full findings array stored as JSONB |
| `duration_ms` | `INT` | Review pipeline latency |
| `created_at` | `TIMESTAMPTZ` | Auto-set timestamp with timezone |

**Why JSONB for findings instead of a separate findings table?**
- **Read pattern:** The dashboard always loads all findings for a PR at once — never
  queries individual findings. JSONB is loaded as a single column read.
- **Write pattern:** Findings are written once (after review) and never updated.
  No need for relational updates.
- **Simplicity:** One table, one write, one read. A normalized schema with a
  `findings` table + foreign key would add complexity for zero benefit given our
  access patterns.
- **Flexibility:** JSONB supports gin indexing if we later need to query by
  finding category or severity across all PRs.

**Why pre-computed severity counts (not computed from JSONB)?**
The dashboard home page shows severity counts for each PR in a table. Computing these
from JSONB on every request would require parsing the full findings array. Pre-computed
columns make the table scan fast — a simple `SELECT` returns everything needed.

**Indexes:**

1. **`idx_pr_reviews_repo`** — Covers `WHERE repo_full_name = $1 ORDER BY created_at DESC`.
   This is the dashboard's main query: "show me all reviews for this repo."

2. **`idx_pr_reviews_sha`** — Covers `WHERE commit_sha = $1`. Used to check if a specific
   commit has already been reviewed (dedup across webhook retries).

**Why `CREATE INDEX IF NOT EXISTS`?**
Idempotency. The `ensure_tables()` function runs on every startup. Without `IF NOT EXISTS`,
the second startup would fail with "index already exists." This is defensive programming
for cloud environments where containers restart frequently.

**Interview talking point:** "We use a single-table design with JSONB for findings rather
than normalized tables. This is deliberate — our access pattern is always 'load all
findings for one PR,' never 'find all PRs with SQL injection findings.' The JSONB column
stores the full findings array, and pre-computed severity count columns avoid parsing JSONB
on read. If query patterns change, Postgres JSONB supports gin indexing for in-document
queries."

### Step 2: Build the Async Database Client

**What we did:** Created async functions using `asyncpg` for non-blocking database operations.

#### Table Creation — `ensure_tables()`

```python
async def ensure_tables():
    """Create the pr_reviews table if it doesn't exist."""
    if not settings.database_url:
        logger.warning("DATABASE_URL not set — skipping table creation")
        return

    try:
        import asyncpg
        conn = await asyncpg.connect(settings.database_url)
        await conn.execute(CREATE_TABLE_SQL)
        await conn.close()
        logger.info("Database tables ensured")
    except Exception as e:
        logger.warning("Database setup failed", error=str(e))
```

**Why `asyncpg` instead of `psycopg2`?**
- **Non-blocking:** `asyncpg` is built for `asyncio` — database queries don't block the
  event loop. With `psycopg2`, a slow query would block all concurrent webhook processing.
- **Performance:** `asyncpg` is the fastest Python Postgres driver (3-5x faster than
  `psycopg2` for common operations).
- **Native async/await:** Fits naturally into the FastAPI async ecosystem.

**Why lazy import (`import asyncpg` inside the function)?**
If the database URL is not configured (development mode), we skip the import entirely.
This prevents import errors on machines that don't have `asyncpg` installed, and it
avoids connecting to a database that doesn't exist.

**Fail-open pattern:** If database setup fails, the system logs a warning and continues.
The webhook pipeline still works — it just doesn't save reviews to Postgres. The dashboard
falls back to mock data. This is critical for development (no Postgres needed locally)
and for resilience (database outage doesn't break the core review functionality).

#### Saving Reviews — `save_review()`

```python
async def save_review(
    repo_full_name: str,
    pr_number: int,
    commit_sha: str,
    review: SynthesizedReview,
) -> None:
    if not settings.database_url:
        return

    try:
        import asyncpg
        conn = await asyncpg.connect(settings.database_url)
        await conn.execute(
            """
            INSERT INTO pr_reviews (id, repo_full_name, pr_number, commit_sha,
                health_score, critical_count, high_count, medium_count, low_count,
                summary, findings, duration_ms)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            str(uuid4()),
            repo_full_name,
            pr_number,
            commit_sha,
            review.health_score,
            review.critical_count,
            review.high_count,
            review.medium_count,
            review.low_count,
            review.executive_summary,
            json.dumps([f.model_dump() for f in review.findings]),
            review.duration_ms,
        )
        await conn.close()
    except Exception as e:
        logger.warning("Database save failed", error=str(e))
```

**Serialization flow:**
```
SynthesizedReview (Pydantic model)
    │
    ├── .health_score → INT column
    ├── .critical_count → INT column
    ├── .executive_summary → TEXT column
    └── .findings → json.dumps([f.model_dump() for f in findings]) → JSONB column
```

Each Finding is converted from a Pydantic model to a dict via `.model_dump()`, then the
list of dicts is serialized to a JSON string via `json.dumps()`. Postgres stores this
as JSONB (binary JSON), which supports efficient storage and querying.

**Why `uuid4()` for the primary key?**
- **No sequence conflicts:** Multiple workers can insert simultaneously without coordination.
- **No guessable IDs:** UUIDs can't be enumerated (security benefit).
- **Stored as TEXT:** Avoids the need for Postgres UUID extension.

#### Reading Reviews — `get_repo_reviews()`

```python
async def get_repo_reviews(repo_full_name: str, limit: int = 20) -> list[dict]:
    if not settings.database_url:
        return []

    try:
        import asyncpg
        conn = await asyncpg.connect(settings.database_url)
        rows = await conn.fetch(
            """
            SELECT id, pr_number, commit_sha, health_score,
                   critical_count, high_count, medium_count, low_count,
                   summary, duration_ms, created_at
            FROM pr_reviews
            WHERE repo_full_name = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            repo_full_name,
            limit,
        )
        await conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning("Database query failed", error=str(e))
        return []
```

**Note:** The `findings` column is intentionally excluded from the SELECT in
`get_repo_reviews()`. The PR list on the dashboard only needs counts and scores — loading
the full findings JSONB for 20 PRs would be wasteful. The findings are loaded only when
the user clicks into a specific PR detail page.

**Interview talking point:** "We use asyncpg for non-blocking database access inside our
async FastAPI pipeline. Each function follows a fail-open pattern — if the database is
unreachable, we log a warning and return empty results rather than crashing. The review
pipeline continues to post comments to GitHub even if we can't save to Postgres. This
separation of concerns means a database outage doesn't break the core functionality."

### Step 3: Add Dashboard API Endpoints (app/main.py)

**What we did:** Added REST endpoints that the Next.js dashboard calls to fetch review data.

#### GET /api/repos/{owner}/{repo}/reviews

```python
@app.get("/api/repos/{owner}/{repo}/reviews")
async def get_reviews(owner: str, repo: str):
    """Get recent PR reviews for a repo (used by dashboard)."""
    from app.db.postgres import get_repo_reviews
    repo_full_name = f"{owner}/{repo}"
    reviews = await get_repo_reviews(repo_full_name)
    return {"repo": repo_full_name, "reviews": reviews}
```

**Used by:** Repo detail page (`/repos/:owner/:repo`) — shows the PR review table.

**Response format:**
```json
{
  "repo": "ninjacode911/codeguard-test",
  "reviews": [
    {
      "id": "abc-123",
      "pr_number": 4,
      "commit_sha": "abc1234...",
      "health_score": 14,
      "critical_count": 3,
      "high_count": 2,
      "medium_count": 4,
      "low_count": 3,
      "summary": "Multi-agent review...",
      "duration_ms": 13200,
      "created_at": "2026-03-20T10:30:00Z"
    }
  ]
}
```

#### GET /api/repos/{owner}/{repo}/stats

```python
@app.get("/api/repos/{owner}/{repo}/stats")
async def get_stats(owner: str, repo: str):
    """Get aggregate stats for a repo (used by dashboard)."""
    from app.db.postgres import get_repo_reviews
    repo_full_name = f"{owner}/{repo}"
    reviews = await get_repo_reviews(repo_full_name, limit=50)
    if not reviews:
        return {"repo": repo_full_name, "total_reviews": 0, "avg_health_score": 0}
    avg_score = sum(r.get("health_score", 0) for r in reviews) / len(reviews)
    return {
        "repo": repo_full_name,
        "total_reviews": len(reviews),
        "avg_health_score": round(avg_score),
        "reviews": reviews[:10],
    }
```

**Used by:** Repo detail page — trend chart, stat pills, and review count.

**Why compute stats on the fly instead of a materialized view?**
With the current scale (tens of reviews per repo), computing average score from a list
of 50 records is sub-millisecond. A materialized view would add complexity (refresh
scheduling, stale data) for zero performance benefit. If scale grew to thousands of
reviews per repo, we'd add a `repo_stats` aggregate table updated on each write.

**CORS middleware enables cross-origin requests:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Allows Vercel dashboard to call Render API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

The dashboard on Vercel (`ninja-code-guard.vercel.app`) calls the API on Render
(`ninja-code-guard.onrender.com`). Without CORS headers, browsers block these
cross-origin requests. In production, `allow_origins` should be restricted to the
actual Vercel domain.

**Interview talking point:** "The dashboard API endpoints are deliberately simple —
they query Postgres and return JSON. Stats are computed on the fly because our scale
doesn't warrant materialized views yet. We follow YAGNI (You Aren't Gonna Need It)
for performance optimization, preferring simplicity until profiling shows a bottleneck."

### Step 4: Configure Render Deployment (render.yaml)

**What we did:** Created a Render blueprint that defines the backend service.

```yaml
services:
  - type: web
    name: ninja-code-guard
    runtime: python
    repo: https://github.com/ninjacode911/ninja-code-guard
    branch: main
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: GROQ_API_KEY
        sync: false
      - key: GEMINI_API_KEY
        sync: false
      - key: GITHUB_APP_ID
        sync: false
      - key: GITHUB_APP_PRIVATE_KEY_PATH
        sync: false
      - key: GITHUB_WEBHOOK_SECRET
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: UPSTASH_REDIS_URL
        sync: false
      - key: ENVIRONMENT
        value: production
    healthCheckPath: /health
    plan: free
```

**Configuration breakdown:**

| Setting | Value | Why |
|---------|-------|-----|
| `type: web` | HTTP service (not worker/cron) | Receives webhook HTTP requests |
| `runtime: python` | Python runtime | FastAPI is Python |
| `branch: main` | Auto-deploy on push to main | Continuous deployment |
| `buildCommand` | `pip install -r requirements.txt` | Install dependencies |
| `startCommand` | `uvicorn ... --host 0.0.0.0 --port $PORT` | Render injects `$PORT` |
| `envVars` with `sync: false` | Manual environment variables | Secrets set in Render dashboard, not in YAML |
| `ENVIRONMENT: production` | Hardcoded, not secret | Switches behavior (e.g., logging level) |
| `healthCheckPath: /health` | Render health check | Render pings this to verify service is alive |
| `plan: free` | Free tier | Sufficient for demo; sleeps after 15 min inactivity |

**Why `sync: false` for secrets?**
`sync: false` means "this env var exists but its value is set manually in the Render
dashboard." We never put API keys in YAML files — they'd be committed to git. The YAML
declares THAT the variable exists; the dashboard stores WHAT it contains.

**The `--host 0.0.0.0` flag:**
Without this, uvicorn binds to `127.0.0.1` (localhost only). In a container/cloud
environment, the service needs to accept connections from the platform's load balancer,
which connects via the container's external interface. `0.0.0.0` accepts connections
on all interfaces.

**Free tier cold start problem:**
Render's free tier spins down after 15 minutes of inactivity. The first request after
spindown takes ~30 seconds. This is why we have the pre-warm cron job (see Step 6).

### Step 5: Configure Vercel Deployment for Dashboard

**What we did:** Connected the `dashboard/` directory to Vercel for automatic deployment.

**Vercel configuration (via dashboard UI):**
| Setting | Value |
|---------|-------|
| Framework | Next.js (auto-detected) |
| Root Directory | `dashboard` |
| Build Command | `next build` (default) |
| Output Directory | `.next` (default) |
| Environment Variables | `NEXT_PUBLIC_API_URL` = Render backend URL |

**How the dashboard connects to the backend:**
```
Vercel (dashboard)                    Render (backend)
┌─────────────────┐                  ┌─────────────────┐
│ NEXT_PUBLIC_API_URL ──────────────▶│ /api/repos/...  │
│ = https://ninja-                   │ /health         │
│   code-guard.                      │                 │
│   onrender.com                     │                 │
└─────────────────┘                  └─────────────────┘
```

The `NEXT_PUBLIC_` prefix is a Next.js convention — it makes the variable available in
client-side code (normally, env vars are server-only for security). Since this is a
public API URL (not a secret), exposing it to the client is safe.

**Automatic deployments:**
Vercel auto-deploys on every push to main. Preview deployments are created for PRs.
This means the dashboard is always up-to-date with the latest code.

### Step 6: Set Up GitHub Actions CI Pipeline (.github/workflows/ci.yml)

**What we did:** Created a CI workflow that runs on every push and PR.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Lint with ruff
        run: ruff check app/ tests/

      - name: Type check with mypy
        run: mypy app/ --ignore-missing-imports
        continue-on-error: true

      - name: Run tests
        run: pytest tests/ -v --tb=short
```

**Pipeline stages:**

| Stage | Tool | What it catches | Failure behavior |
|-------|------|-----------------|------------------|
| Lint | Ruff | Style violations, unused imports, bad practices | **Blocks merge** |
| Type check | mypy | Type errors, missing annotations | **Soft fail** (`continue-on-error`) |
| Test | pytest | Functional regressions, schema violations | **Blocks merge** |

**Why `continue-on-error: true` for mypy?**
Some third-party libraries (LangChain, asyncpg) don't ship type stubs. mypy reports
"missing imports" for these, which aren't real bugs. We run mypy to catch errors in
our own code, but don't let third-party issues block the pipeline. As we add type stubs
or `# type: ignore` annotations, we can switch this to strict mode.

**Why `requirements-dev.txt` (not `requirements.txt`)?**
Dev requirements include testing tools (pytest, ruff, mypy) that aren't needed in
production. The production `requirements.txt` only includes runtime dependencies,
keeping the deployment image smaller and faster to build.

### Step 7: Set Up the Pre-Warm Cron Job (.github/workflows/prewarm.yml)

**What we did:** Created a scheduled workflow that pings the backend every 10 minutes
during working hours.

```yaml
name: Pre-warm Render

on:
  schedule:
    # Ping every 10 minutes during working hours (UTC)
    - cron: "*/10 6-20 * * 1-5"

jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: Ping health endpoint
        run: |
          curl -sf "${{ secrets.RENDER_HEALTH_URL }}/health" \
            || echo "Service cold — will wake on next request"
```

**Cron schedule breakdown: `*/10 6-20 * * 1-5`**
| Field | Value | Meaning |
|-------|-------|---------|
| Minute | `*/10` | Every 10 minutes |
| Hour | `6-20` | 6 AM to 8 PM UTC |
| Day of month | `*` | Every day |
| Month | `*` | Every month |
| Day of week | `1-5` | Monday through Friday |

**Why these specific times?**
- **Every 10 minutes:** Render's free tier sleeps after 15 minutes of inactivity.
  Pinging every 10 minutes keeps it awake with a 5-minute safety margin.
- **6 AM to 8 PM UTC:** Covers US/EU working hours when developers are opening PRs.
  No need to keep the service warm at 3 AM when nobody is working.
- **Weekdays only:** Most development happens Monday-Friday. Weekend cold starts are
  acceptable — the 30-second wake-up delay on Monday morning is fine.

**Why `curl -sf` with `|| echo`?**
- `-s` (silent): No progress bar output
- `-f` (fail): Return non-zero exit code on HTTP errors
- `|| echo`: If curl fails (service is cold and times out), print a message instead
  of failing the workflow. This is informational, not critical.

**Why use GitHub Actions for pre-warm instead of a separate cron service?**
- **Free:** GitHub Actions offers 2,000 minutes/month for free repos
- **Already set up:** We have the CI pipeline, adding a cron is one YAML file
- **No infrastructure:** No need for a separate cron service, Lambda, or Cloud Scheduler

**Interview talking point:** "We use a GitHub Actions cron job to keep the Render free tier
warm during working hours. The cron pings the /health endpoint every 10 minutes, which
prevents the 30-second cold start that would otherwise delay webhook processing. The
schedule is optimized for US/EU business hours on weekdays — we don't waste GitHub Actions
minutes keeping the service warm at 3 AM on a Saturday."

### Step 8: Production Checklist

Before going live, we verified each component of the system:

| Check | Status | How Verified |
|-------|--------|--------------|
| Webhook receives PR events | Pass | Created test PR, saw webhook delivery in GitHub App dashboard |
| HMAC validation rejects forged requests | Pass | Sent request with wrong signature, got 403 |
| Redis cache prevents duplicate reviews | Pass | Re-opened PR, second webhook was skipped |
| 3 agents run in parallel | Pass | Logs show `asyncio.gather` completing all 3 simultaneously |
| Synthesizer deduplicates findings | Pass | 14 raw findings → 12 after dedup |
| Health Score is computed correctly | Pass | Manual calculation matches system output |
| Inline comments posted to GitHub | Pass | Comments appear on correct lines in PR |
| Summary comment posted with Health Score | Pass | Summary card with score, severity table, recommendations |
| Reviews saved to Neon Postgres | Pass | Queried database, rows exist |
| Dashboard shows review data | Pass | Connected dashboard to API, displays real reviews |
| CI pipeline passes | Pass | Push to main triggers lint + type check + test |
| Pre-warm cron runs on schedule | Pass | Checked GitHub Actions, cron runs every 10 minutes |
| CORS allows Vercel→Render requests | Pass | Dashboard fetches data without CORS errors |
| Cold start recovery | Pass | After 15 min idle, /health wakes service in ~30 seconds |

---

## Architecture Patterns Used

| Pattern | Where | Why |
|---------|-------|-----|
| **Fail-Open** | Database client, Redis cache | System continues working if external services are down |
| **Infrastructure as Code** | `render.yaml`, `ci.yml`, `prewarm.yml` | Deployment config is version-controlled, reproducible |
| **Secret Management** | `sync: false` in render.yaml, GitHub Secrets | Secrets never in code or YAML — only in platform dashboards |
| **Health Check** | `/health` endpoint | Render monitors service health, cron keeps it warm |
| **CQRS-lite** | Separate write path (webhook) and read path (dashboard API) | Write path optimized for throughput, read path for latency |
| **Denormalization** | Pre-computed severity counts in `pr_reviews` | Avoids JSONB parsing on dashboard reads |
| **Background Tasks** | FastAPI `BackgroundTasks` | Return 200 to GitHub instantly, process review asynchronously |
| **ISR Caching** | Next.js `{ revalidate: 60 }` | Dashboard data cached 60 seconds, reducing API load |

---

## Files Created / Modified in Week 10

| File | Purpose |
|------|---------|
| `app/db/postgres.py` | Neon Postgres client: schema, save, query |
| `app/main.py` | Dashboard API endpoints + CORS middleware (modified) |
| `render.yaml` | Render deployment blueprint |
| `.github/workflows/ci.yml` | CI pipeline: lint + type check + test |
| `.github/workflows/prewarm.yml` | Pre-warm cron job for Render free tier |

---

## Full System Data Flow

Here is the complete data flow from PR creation to dashboard display:

```
1. Developer opens PR on GitHub
   └── GitHub sends webhook POST to Render

2. Render receives webhook
   └── /webhook/github endpoint
       ├── HMAC-SHA256 validation (reject forged requests)
       ├── Parse payload: repo, PR number, commit SHA
       ├── Check Redis: already reviewed? → skip
       └── Enqueue background task → return 200 to GitHub

3. Background task runs
   ├── Fetch PR diff + file contents from GitHub API
   ├── Index files into ChromaDB (RAG)
   ├── Retrieve RAG context (semantic search)
   ├── Run 3 agents in parallel (asyncio.gather)
   │   ├── Security Agent (Bandit + LLM)
   │   ├── Performance Agent (Radon + LLM)
   │   └── Style Agent (Ruff + LLM)
   ├── Synthesize: dedup → rank → score → summarize
   ├── Post inline comments to GitHub PR
   ├── Post summary comment with Health Score
   ├── Save review to Neon Postgres
   └── Mark commit as reviewed in Redis

4. Dashboard displays results
   ├── Next.js on Vercel calls /api/repos/.../reviews
   ├── FastAPI queries Neon Postgres
   ├── Returns JSON with scores, counts, summaries
   └── Dashboard renders HealthScoreRing, FindingsTable, TrendChart
```

---

## Interview Talking Points Summary

1. **"Walk me through the deployment architecture."**
   "The backend runs on Render's free tier as a FastAPI service. The dashboard is a
   separate Next.js deployment on Vercel. They communicate via REST API with CORS
   enabled. Data is stored in Neon serverless Postgres. Redis on Upstash caches
   reviewed commit SHAs to prevent duplicates. GitHub Actions handles CI (lint + test)
   and a pre-warm cron that pings the service every 10 minutes to avoid cold starts."

2. **"Why separate deployments for backend and dashboard?"**
   "The backend needs Python for agents (LangChain, Bandit, Radon). The dashboard needs
   Node.js for Next.js. Separating them lets each use the optimal runtime. Vercel is
   purpose-built for Next.js with edge caching and preview deployments. Render handles
   the Python backend with easy environment variable management."

3. **"How do you handle Render's cold start problem?"**
   "A GitHub Actions cron job pings the /health endpoint every 10 minutes during working
   hours. The schedule is `*/10 6-20 * * 1-5` — every 10 minutes, 6 AM to 8 PM UTC,
   Monday through Friday. This keeps the service warm when developers are likely to
   open PRs, while saving GitHub Actions minutes on nights and weekends."

4. **"Why asyncpg instead of an ORM like SQLAlchemy?"**
   "We have exactly one table with three operations: create table, insert row, select
   rows. An ORM would add a layer of abstraction over trivially simple SQL. asyncpg
   gives us native async support (non-blocking in our FastAPI pipeline) and is 3-5x
   faster than psycopg2. For a system this simple, raw SQL is more readable than ORM
   query builders."

5. **"What would you do differently for a production system at scale?"**
   "Connection pooling (asyncpg.create_pool instead of connect-per-request), a proper
   migration tool (Alembic), separate read replicas for the dashboard, rate limiting
   on the webhook endpoint, structured logging with a log aggregation service (Datadog),
   and a staging environment with its own database. The current architecture is right
   for the current scale — these optimizations address specific bottlenecks that appear
   at higher traffic."

---

*Documentation written 2026-03-20 as part of Week 10 completion.*

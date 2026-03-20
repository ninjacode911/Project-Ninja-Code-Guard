# Week 1: Foundation & Setup — Detailed Documentation

> **Goal:** Project skeleton running locally, all external services provisioned.
> **Status:** Complete
> **Date:** 2026-03-19

---

## What We Accomplished

Week 1 established the entire project foundation: directory structure, configuration system,
data models, external service accounts, CI/CD pipeline, and the initial deployment config.

---

## Step-by-Step Log

### Step 1: Initialize the Project

**What we did:** Created the project directory structure following a modular Python backend
architecture with clear separation of concerns.

**Why this structure matters:**
```
app/                    ← All backend application code lives here
  agents/               ← One file per agent (security, performance, style, synthesizer)
  tools/                ← LangChain tool wrappers (semgrep, bandit, radon, etc.)
  context/              ← RAG pipeline (embedder → indexer → retriever)
  github/               ← All GitHub API interaction (webhook, auth, client, formatter)
  models/               ← Pydantic data models (Finding, PRReview, webhook payloads)
  db/                   ← Database & cache (Postgres, Redis)
  services/             ← Business logic (orchestrator, health score calculator)
dashboard/              ← Next.js frontend (deployed separately to Vercel)
tests/                  ← Mirrors the app/ structure (unit/, integration/, eval/)
prompts/                ← Agent system prompts as Markdown files
knowledge/              ← RAG knowledge bases (OWASP, DDIA, style guides)
docs/                   ← Project documentation (this file)
```

**Key principle:** Each directory has a single responsibility. The `agents/` folder doesn't
know about GitHub. The `github/` folder doesn't know about LangChain. The `services/`
folder orchestrates between them. This is called **separation of concerns** — it makes the
code testable, maintainable, and easy to explain in interviews.

**Commands run:**
```bash
# Create all directories
mkdir -p app/{agents,tools,context,github,models,db,services}
mkdir -p dashboard/{app/{repos,api},components,lib}
mkdir -p tests/{unit,integration,eval/dataset}
mkdir -p prompts knowledge/style_guides

# Create __init__.py files (makes directories Python packages)
touch app/__init__.py app/agents/__init__.py app/tools/__init__.py ...

# Initialize git
git init && git branch -m main
```

### Step 2: Create Configuration System (app/config.py)

**What we did:** Created a centralized configuration file using `pydantic-settings`.

**How it works:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str = ""
    github_app_id: str = ""
    # ... all config vars

    model_config = {"env_file": ".env"}

settings = Settings()  # Singleton — imported everywhere
```

**Why pydantic-settings instead of plain os.environ?**
1. **Type safety** — `confidence_threshold: float = 0.6` ensures it's a float, not a string
2. **Validation** — pydantic raises clear errors if required vars are missing
3. **Defaults** — each setting has a sensible default for development
4. **Auto-loads .env** — reads from `.env` file automatically (via `model_config`)
5. **IDE autocomplete** — `settings.groq_api_key` instead of `os.environ.get("GROQ_API_KEY")`

**Interview talking point:** "We use pydantic-settings for type-safe configuration management
following the 12-factor app methodology — config lives in environment variables, not in code.
This makes the same codebase work in development, staging, and production with zero code changes."

### Step 3: Define Data Models (app/models/findings.py)

**What we did:** Created Pydantic models that define the exact shape of data flowing through
the system.

**Three core models:**

#### Finding — Output of each domain agent
```python
class Finding(BaseModel):
    agent: Literal["security", "performance", "style"]  # Which agent found this
    file_path: str              # e.g. "src/auth/login.py"
    line_start: int             # Where the issue starts
    line_end: int               # Where the issue ends
    severity: Literal["critical", "high", "medium", "low"]  # How bad is it
    category: str               # e.g. "sql_injection", "n+1_query"
    title: str                  # One-liner for the inline comment header
    description: str            # Full explanation
    suggested_fix: str          # Corrected code snippet
    cwe_id: Optional[str]       # CWE ID for security findings (e.g. "CWE-89")
    confidence: float           # 0.0–1.0, how sure the agent is
```

#### SynthesizedReview — Output of the Synthesizer Agent
```python
class SynthesizedReview(BaseModel):
    health_score: int           # 0-100 (the headline metric)
    executive_summary: str      # 3-5 sentences for PR description
    recommendation: Literal["approve", "request_changes", "block"]
    findings: list[Finding]     # Deduplicated, re-ranked findings
    critical_count: int         # Counts by severity
    # ...
```

#### PRReviewRecord — What gets stored in Postgres
```python
class PRReviewRecord(BaseModel):
    id: UUID                    # Primary key
    repo_full_name: str         # "ninjacode911/myapp"
    pr_number: int
    commit_sha: str
    health_score: int
    findings: list[Finding]     # Full findings as JSONB
    duration_ms: int            # How long the review took
```

**Why Pydantic models instead of plain dicts?**
1. **Validation** — `severity: Literal["critical", "high", "medium", "low"]` rejects invalid values
2. **Serialization** — `.model_dump()` converts to dict, `.model_dump_json()` to JSON
3. **Documentation** — the schema IS the documentation
4. **Type checking** — mypy catches bugs at development time, not production

**Interview talking point:** "Every data boundary in the system uses Pydantic models — agent
outputs, API responses, database records. This gives us runtime validation, IDE autocomplete,
and auto-generated OpenAPI docs. If an agent returns malformed JSON, Pydantic catches it
immediately instead of letting bad data propagate through the pipeline."

### Step 4: Define Webhook Payload Models (app/models/webhook_payloads.py)

**What we did:** Created typed models for GitHub's webhook JSON payloads.

**Why type the webhook payload?**
GitHub sends complex nested JSON. Without types, you'd write:
```python
sha = payload["pull_request"]["head"]["sha"]  # Easy to typo, no autocomplete
```
With Pydantic models:
```python
event = PullRequestEvent(**payload)
sha = event.pull_request.head.sha  # Autocomplete, type-checked
```

We didn't use these models in the final webhook handler (we used raw dict access for
simplicity), but they're available for stricter validation later.

### Step 5: Create FastAPI Skeleton (app/main.py)

**What we did:** Created the FastAPI application with a `/health` endpoint.

```python
app = FastAPI(title="Ninja Code Guard", version="0.1.0")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Ninja Code Guard", "version": "0.1.0"}
```

**Why a /health endpoint?**
- **Render.com** uses it to know if your service is alive (configured in render.yaml)
- **GitHub Actions cron** pings it every 10 minutes to prevent cold starts
- **The dashboard** calls it to show service status
- **Load balancers** (if you scale up) use it to route traffic only to healthy instances

### Step 6: Provision External Services

**What we did:** Created accounts and obtained credentials for all external services.

#### 6a. GitHub App — "Ninja's Code Guard"

**Where:** github.com/settings/apps/new

**What we configured:**
| Setting | Value | Reason |
|---------|-------|--------|
| Name | Ninja Code Guard | Bot identity: `ninjas-code-guard[bot]` |
| Homepage URL | github.com/ninjacode911/codeprobe | Points to our repo |
| Webhook Active | Yes | We need to receive PR events |
| Webhook Secret | (generated with `python -c "import secrets; print(secrets.token_hex(32))"`) | HMAC authentication |
| Contents | Read | Fetch full file source code for RAG context |
| Pull requests | Read & Write | Read diffs, post review comments |
| Commit statuses | Write | Show health score as commit status check |
| Metadata | Read | Required — basic repo info |
| Events | pull_request, pull_request_review_comment | Our trigger events |
| Install target | Only this account | Dev-mode only for now |

**What we got:**
- App ID: 3133457
- Private Key: `.pem` file saved to `keys/ninja-s-code-guard.2026-03-19.private-key.pem`
- Webhook Secret: saved to `.env`

**How GitHub App authentication works (important concept):**
```
Step 1: Sign a JWT with our private key (.pem)
        JWT payload = {iss: APP_ID, iat: now, exp: now+9min}
        Signed with RS256 (RSA + SHA-256)
        This proves: "I am the Ninja Code Guard app"

Step 2: Exchange JWT for an installation access token
        POST /app/installations/{id}/access_tokens
        Headers: Authorization: Bearer <JWT>
        Returns: token valid for 1 hour, scoped to installed repos
        This proves: "I can access ninjacode911's repos"

Step 3: Use installation token for all API calls
        GET /repos/ninjacode911/codeguard-test/pulls/1
        Headers: Authorization: token <installation_token>
```

#### 6b. Groq API

**Where:** console.groq.com
**What:** API key for Llama-3.1-70B inference (14,400 free requests/day)
**Saved as:** `GROQ_API_KEY` in `.env`

#### 6c. Neon.tech Postgres

**Where:** console.neon.tech
**What:** Serverless Postgres database (512MB free tier)
**Saved as:** `DATABASE_URL` in `.env`
**Used for:** Storing PR review history, health score trends, finding details

#### 6d. Upstash Redis

**Where:** console.upstash.com
**What:** Serverless Redis (10K requests/day free tier)
**Saved as:** `UPSTASH_REDIS_URL` in `.env`
**Used for:** Caching reviewed commit SHAs to prevent duplicate analysis

### Step 7: Create Configuration Files

#### .env.example
Template showing all required environment variables without actual values.
Committed to git so new developers know what to configure.

#### .gitignore
Prevents sensitive files from being committed:
- `.env` (contains API keys)
- `keys/` (contains private key .pem)
- `__pycache__/`, `.venv/` (generated files)
- `chroma_data/` (vector store data)
- `dashboard/node_modules/`, `dashboard/.next/` (Node.js generated)

#### pyproject.toml
Project metadata + tool configuration:
- `[tool.ruff]` — Python linter settings
- `[tool.pytest]` — Test configuration (asyncio mode, test paths)
- `[tool.mypy]` — Type checker settings

#### render.yaml
Render.com deployment configuration:
```yaml
services:
  - type: web
    name: ninja-code-guard
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    plan: free
```

#### sentinel.yml.example
Per-repo configuration template that users place in their repo root:
```yaml
agents:
  security: true
  performance: true
  style: true
min_severity: low
min_confidence: 0.6
exclude:
  - "vendor/"
  - "node_modules/"
```

### Step 8: Set Up CI/CD (GitHub Actions)

**Created two workflows:**

#### ci.yml — Runs on every push/PR
```yaml
steps:
  - Lint with ruff (catches style/import issues)
  - Type check with mypy (catches type errors)
  - Run tests with pytest
```

#### prewarm.yml — Cron job every 10 minutes on weekdays
```yaml
schedule: "*/10 6-20 * * 1-5"  # Every 10min, 6am-8pm UTC, Mon-Fri
steps:
  - curl the /health endpoint to prevent Render cold starts
```

**Why pre-warm?** Render's free tier spins down after 15 minutes of inactivity. The first
request after spindown takes ~30 seconds (cold start). By pinging /health every 10 minutes
during working hours, the service stays warm and responds instantly to webhooks.

### Step 9: Write Initial Tests

**Created:** `tests/unit/test_findings_schema.py` — 8 tests for data model validation

These tests verify:
- Valid Finding objects are accepted
- Invalid agent types are rejected
- Invalid severity levels are rejected
- Confidence must be between 0.0 and 1.0
- CWE ID is optional (None allowed)
- Health score must be 0-100
- Invalid recommendation values are rejected

---

## Files Created in Week 1

| File | Purpose |
|------|---------|
| `app/__init__.py` | Makes app a Python package |
| `app/config.py` | Centralized configuration via environment variables |
| `app/main.py` | FastAPI app with /health endpoint (expanded in Week 2) |
| `app/models/__init__.py` | Models package |
| `app/models/findings.py` | Finding, SynthesizedReview, PRReviewRecord schemas |
| `app/models/webhook_payloads.py` | GitHub webhook event payload types |
| `tests/conftest.py` | Shared test fixtures (sample finding data) |
| `tests/unit/test_findings_schema.py` | 8 schema validation tests |
| `.env` | Environment variables (gitignored — contains secrets) |
| `.env.example` | Template for .env (committed — no secrets) |
| `.gitignore` | Files to exclude from git |
| `pyproject.toml` | Project metadata + tool configs |
| `requirements.txt` | Python production dependencies |
| `requirements-dev.txt` | Dev/test dependencies |
| `render.yaml` | Render.com deployment config |
| `sentinel.yml.example` | Per-repo config template |
| `.github/workflows/ci.yml` | CI pipeline (lint + test) |
| `.github/workflows/prewarm.yml` | Render pre-warm cron |
| `keys/.gitignore` | Prevents .pem files from being committed |
| `PROJECT_PLAN.md` | Master project plan + progress tracker |

---

## Key Decisions Made

| Decision | Rationale |
|----------|-----------|
| Pydantic for all data models | Runtime validation + IDE autocomplete + auto-docs |
| pydantic-settings for config | Type-safe env vars, auto-loads .env, 12-factor pattern |
| FastAPI (not Flask/Django) | Async-native (needed for parallel agents), auto OpenAPI docs, modern Python |
| GitHub App (not Action) | One deployment serves all repos, webhook-driven, own bot identity |
| Upstash Redis (not in-memory cache) | Persists across Render restarts, shared across workers |
| Neon.tech (not SQLite) | Serverless, accessible from dashboard, persistent storage |

---

*Documentation written 2026-03-19 as part of Week 1 completion.*

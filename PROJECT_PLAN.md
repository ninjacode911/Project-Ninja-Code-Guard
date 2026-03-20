# CodeProbe — Complete Project Plan & Progress Tracker

> **Multi-Agent Code Review System**
> Author: Ninjacode911 | Started: March 2026 | Target: 10 Weeks

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Deep Dive](#2-architecture-deep-dive)
3. [Complete Tech Stack](#3-complete-tech-stack)
4. [Directory Structure](#4-directory-structure)
5. [Week-by-Week Implementation Plan](#5-week-by-week-implementation-plan)
6. [Non-Coding Tasks](#6-non-coding-tasks)
7. [GPU / WSL Tasks](#7-gpu--wsl-tasks)
8. [Data Models & Schemas](#8-data-models--schemas)
9. [API Endpoints](#9-api-endpoints)
10. [Agent Prompt Design](#10-agent-prompt-design)
11. [Evaluation Plan](#11-evaluation-plan)
12. [Deployment Checklist](#12-deployment-checklist)
13. [Progress Tracker](#13-progress-tracker)

---

## 1. Project Overview

**What:** A multi-agent PR review system that reviews GitHub pull requests using 4 specialized LangChain agents (Security, Performance, Style, Synthesizer), posts inline GitHub comments, and tracks code health via a Next.js dashboard.

**Why:** AI-generated code (41% of GitHub commits) introduces 1.7x more issues. Existing tools use single-pass LLM calls. Sentinel AI uses domain-specialized agents with debate/consensus, RAG context, and static analysis tools.

**Core Thesis:** Separate security, performance, and style review into specialized agents — each with distinct prompts, tools, and context — then merge via a Synthesizer into a coherent, ranked, deduplicated review.

**Key Differentiators:**
- Multi-agent specialization (3 domain + 1 synthesizer)
- Debate & consensus protocol (agents challenge each other before synthesis)
- Repo-aware RAG context (ChromaDB indexes full repo, not just diff)
- $0/month architecture (all free tiers)
- Structured severity scoring (Critical/High/Medium/Low with CWE IDs)
- Auto-fix suggestions (corrected code snippets inline)

---

## 2. Architecture Deep Dive

### 2.1 Four Layers

```
┌─────────────────────────────────────────────────────┐
│  GITHUB LAYER                                       │
│  Webhooks · PR Events · Inline Comments             │
└──────────────────────┬──────────────────────────────┘
                       │ pull_request webhook
┌──────────────────────▼──────────────────────────────┐
│  ORCHESTRATION LAYER (FastAPI on Render)             │
│  Webhook receiver · HMAC validation · Redis cache    │
│  Agent dispatcher · GitHub API client                │
└──────────────────────┬──────────────────────────────┘
                       │ asyncio.gather()
┌──────────────────────▼──────────────────────────────┐
│  AGENT LAYER (LangChain ReAct Agents)               │
│  ┌──────────┐ ┌──────────────┐ ┌─────────┐         │
│  │ Security │ │ Performance  │ │  Style  │ PARALLEL │
│  │  Agent   │ │    Agent     │ │  Agent  │          │
│  └────┬─────┘ └──────┬───────┘ └────┬────┘         │
│       └──────────────┼───────────────┘              │
│                      ▼                               │
│            ┌──────────────────┐                      │
│            │  Synthesizer     │  SEQUENTIAL           │
│            │  Agent           │                      │
│            └──────────────────┘                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  KNOWLEDGE LAYER                                     │
│  ChromaDB (vector store) · Upstash Redis (cache)     │
│  Neon Postgres (history) · sentence-transformers     │
└─────────────────────────────────────────────────────┘
```

### 2.2 Data Flow (11 Steps)

1. GitHub fires `pull_request` webhook → Render FastAPI endpoint
2. FastAPI validates HMAC-SHA256 signature (GitHub App secret)
3. Check Upstash Redis: commit SHA already reviewed? → return cached
4. Fetch via GitHub API: PR diff, changed files, full contents, commit history
5. Build repo context: embed chunks with sentence-transformers → upsert ChromaDB
6. Dispatch 3 parallel agents: `asyncio.gather(security, performance, style)`
7. Each agent: system prompt + RAG context → Groq API → static tools → typed findings
8. Synthesizer: deduplicate + resolve conflicts + Health Score + executive summary
9. GitHub API: post inline comment per finding + PR summary comment
10. Write review to Neon Postgres + set Redis cache (TTL: 7 days)
11. Next.js dashboard fetches from Neon and updates Health Score chart

### 2.3 Context Loading (5 Layers per Agent)

1. Raw PR diff (changed lines, file paths, additions/deletions)
2. Relevant file sections from full repo (ChromaDB semantic search on diff)
3. Recent commit history for changed files (pattern detection)
4. Repo configuration (language, framework, linter rules, test coverage)
5. Domain-specific knowledge base (OWASP Top 10, DDIA patterns, style guides)

---

## 3. Complete Tech Stack

### 3.1 LLM & AI

| Tool | Free Tier | Purpose |
|------|-----------|---------|
| **Groq API** (Llama-3.1-70B) | 14,400 req/day, 500 tok/sec | Primary LLM for all agents |
| **Gemini 1.5 Flash** | 1M tokens/day | Fallback when Groq exhausted |
| **LangChain** | OSS | Agent orchestration, LCEL, ReAct framework |
| **sentence-transformers** | Local (GPU) | Embeddings for ChromaDB — runs on RTX 5070 via WSL |

### 3.2 Backend & APIs

| Tool | Free Tier | Purpose |
|------|-----------|---------|
| **FastAPI** | OSS | Webhook receiver, agent dispatcher, REST API |
| **Render.com** | Free web service | Hosts backend (30s cold start after 15min idle) |
| **GitHub Apps API** | Free | Webhooks, PR comments, file fetching |
| **Upstash Redis** | 10K req/day | Cache PR analysis by commit SHA |
| **Neon.tech** | Free Postgres 512MB | Review history, Health Score trends |

### 3.3 Knowledge & Static Analysis

| Tool | Free Tier | Purpose |
|------|-----------|---------|
| **ChromaDB** | OSS, in-memory/persisted | Vector store for RAG context retrieval |
| **Semgrep OSS** | Free, 3K+ rules | SAST rules for Security Agent |
| **Bandit** | Free | Python AST security analysis |
| **detect-secrets** | Free | Credential/API key scanning |
| **radon** | Free | Cyclomatic complexity & maintainability index |
| **pylint/ESLint/Ruff** | Free | Linting for Style Agent |

### 3.4 Frontend & Deployment

| Tool | Free Tier | Purpose |
|------|-----------|---------|
| **Vercel** | Free hobby tier | Hosts Next.js dashboard |
| **Next.js** | OSS | Dashboard UI |
| **Recharts** | OSS | Health Score trend charts, pie charts |
| **GitHub Actions** | 2K min/month | CI/CD for Sentinel AI itself |

---

## 4. Directory Structure

```
sentinel-ai/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, webhook endpoint, lifespan
│   ├── config.py                  # Settings via pydantic-settings (env vars)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py          # Shared agent interface / base class
│   │   ├── security_agent.py      # Security ReAct agent
│   │   ├── performance_agent.py   # Performance ReAct agent
│   │   ├── style_agent.py         # Style & Maintainability agent
│   │   └── synthesizer.py         # Synthesizer + Health Score + dedup
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── semgrep_tool.py        # LangChain tool wrapper for Semgrep
│   │   ├── bandit_tool.py         # LangChain tool wrapper for Bandit
│   │   ├── detect_secrets_tool.py # Credential scanner tool
│   │   ├── radon_tool.py          # Complexity metrics tool
│   │   ├── ast_analyzer.py        # Python AST analysis (N+1, patterns)
│   │   └── linter_tool.py         # Ruff/ESLint/pylint subprocess tool
│   ├── context/
│   │   ├── __init__.py
│   │   ├── embedder.py            # sentence-transformers embedding pipeline
│   │   ├── indexer.py             # ChromaDB repo indexer (upsert chunks)
│   │   └── retriever.py           # RAG retriever (query ChromaDB for context)
│   ├── github/
│   │   ├── __init__.py
│   │   ├── webhook.py             # Webhook validation (HMAC-SHA256)
│   │   ├── client.py              # GitHub API client (fetch diff, post comments)
│   │   └── comment_formatter.py   # Format findings as GitHub Markdown comments
│   ├── models/
│   │   ├── __init__.py
│   │   ├── findings.py            # Finding, PRReview Pydantic schemas
│   │   └── webhook_payloads.py    # GitHub webhook event schemas
│   ├── db/
│   │   ├── __init__.py
│   │   ├── postgres.py            # Neon Postgres connection + queries
│   │   └── redis_cache.py         # Upstash Redis cache logic
│   └── services/
│       ├── __init__.py
│       ├── orchestrator.py        # Main orchestration: dispatch agents, synthesize
│       └── health_score.py        # Health Score calculation formula
├── dashboard/                     # Next.js app (deployed to Vercel)
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx               # / — Repository Overview
│   │   ├── repos/
│   │   │   └── [owner]/
│   │   │       └── [repo]/
│   │   │           ├── page.tsx   # Repo Detail (trends, charts)
│   │   │           └── prs/
│   │   │               └── [number]/
│   │   │                   └── page.tsx  # PR Review Detail
│   │   └── api/
│   │       ├── repos/
│   │       │   └── route.ts       # API proxy to FastAPI backend
│   │       └── health/
│   │           └── route.ts
│   ├── components/
│   │   ├── HealthScoreRing.tsx    # Circular gauge 0-100
│   │   ├── FindingsTable.tsx      # Sortable, filterable findings
│   │   ├── TrendChart.tsx         # Recharts LineChart
│   │   ├── AgentBreakdown.tsx     # 3-column agent summary cards
│   │   ├── SeverityBadge.tsx      # Color-coded severity pill
│   │   └── Navbar.tsx
│   └── lib/
│       ├── api.ts                 # Fetch wrapper for backend API
│       └── types.ts               # TypeScript types matching backend schemas
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Shared fixtures
│   ├── unit/
│   │   ├── test_findings_schema.py
│   │   ├── test_synthesizer_dedup.py
│   │   ├── test_webhook_validation.py
│   │   ├── test_redis_cache.py
│   │   └── test_health_score.py
│   ├── integration/
│   │   ├── test_full_pipeline.py
│   │   └── test_github_posting.py
│   └── eval/
│       ├── dataset/               # 20-PR benchmark dataset (JSON fixtures)
│       ├── run_eval.py            # Evaluation harness
│       └── metrics.py             # Precision, recall, latency tracking
├── prompts/
│   ├── security_system.md         # Security Agent system prompt
│   ├── performance_system.md      # Performance Agent system prompt
│   ├── style_system.md            # Style Agent system prompt
│   └── synthesizer_system.md      # Synthesizer system prompt
├── knowledge/
│   ├── owasp_top10_2025.md        # OWASP cheat sheet for Security RAG
│   ├── ddia_patterns.md           # DDIA patterns for Performance RAG
│   └── style_guides/              # Language style guides for Style RAG
├── .env.example                   # Template for env vars (no secrets)
├── .gitignore
├── requirements.txt               # Python dependencies
├── requirements-dev.txt           # Dev/test dependencies
├── render.yaml                    # Render deployment config
├── sentinel.yml.example           # Per-repo config template
├── Dockerfile                     # For Render deployment
├── pyproject.toml                 # Project metadata + tool configs
└── README.md                      # Installation, usage, architecture docs
```

---

## 5. Week-by-Week Implementation Plan

### WEEK 1: Foundation & Setup
**Goal:** Project skeleton running locally, all external services provisioned.

| # | Task | Type | Status |
|---|------|------|--------|
| 1.1 | Initialize git repo, create directory structure | Code | [ ] |
| 1.2 | Set up Python virtual environment + requirements.txt | Code | [ ] |
| 1.3 | Register GitHub App (dev.github.com/settings/apps) | Config | [ ] |
| 1.4 | Provision Neon.tech Postgres database + create `pr_reviews` table | Config | [ ] |
| 1.5 | Provision Upstash Redis instance | Config | [ ] |
| 1.6 | Get Groq API key (console.groq.com) | Config | [ ] |
| 1.7 | Get Gemini API key (aistudio.google.com) | Config | [ ] |
| 1.8 | Create FastAPI skeleton (`app/main.py`) with health endpoint | Code | [ ] |
| 1.9 | Create `app/config.py` with pydantic-settings (all env vars) | Code | [ ] |
| 1.10 | Create Pydantic models (`Finding`, `PRReview` schemas) | Code | [ ] |
| 1.11 | Set up .env.example, .gitignore, pyproject.toml | Code | [ ] |
| 1.12 | Deploy FastAPI skeleton to Render (verify /health works) | Deploy | [ ] |
| 1.13 | Write unit tests for Finding schema validation | Test | [ ] |
| 1.14 | Set up GitHub Actions CI (lint + test on push) | CI/CD | [ ] |

### WEEK 2: GitHub Integration
**Goal:** Receive webhooks, validate signatures, fetch PR data, post dummy comment.

| # | Task | Type | Status |
|---|------|------|--------|
| 2.1 | Implement HMAC-SHA256 webhook validation (`app/github/webhook.py`) | Code | [ ] |
| 2.2 | Implement GitHub API client — fetch PR diff (`app/github/client.py`) | Code | [ ] |
| 2.3 | Implement GitHub API client — fetch file contents | Code | [ ] |
| 2.4 | Implement GitHub API client — fetch commit history | Code | [ ] |
| 2.5 | Implement GitHub API client — post inline review comments | Code | [ ] |
| 2.6 | Implement GitHub API client — post PR summary comment | Code | [ ] |
| 2.7 | Create webhook endpoint (`POST /webhook/github`) in main.py | Code | [ ] |
| 2.8 | Implement comment formatter (`app/github/comment_formatter.py`) | Code | [ ] |
| 2.9 | Set up ngrok for local webhook testing | Config | [ ] |
| 2.10 | End-to-end test: open PR on test repo → dummy comment posted | Test | [ ] |
| 2.11 | Implement Redis cache check (skip if commit SHA already reviewed) | Code | [ ] |
| 2.12 | Write unit tests for HMAC validation (valid + invalid signatures) | Test | [ ] |
| 2.13 | Write unit tests for Redis cache hit/miss logic | Test | [ ] |

### WEEK 3: Security Agent v1
**Goal:** Security Agent analyzes diffs, returns structured findings with CWE IDs.

| # | Task | Type | Status |
|---|------|------|--------|
| 3.1 | Install & configure Semgrep OSS with security rulesets | Config | [ ] |
| 3.2 | Create Semgrep LangChain tool (`app/tools/semgrep_tool.py`) | Code | [ ] |
| 3.3 | Install & configure Bandit for Python AST security analysis | Config | [ ] |
| 3.4 | Create Bandit LangChain tool (`app/tools/bandit_tool.py`) | Code | [ ] |
| 3.5 | Install & configure detect-secrets | Config | [ ] |
| 3.6 | Create detect-secrets LangChain tool (`app/tools/detect_secrets_tool.py`) | Code | [ ] |
| 3.7 | Write Security Agent system prompt (`prompts/security_system.md`) | Prompt | [ ] |
| 3.8 | Prepare OWASP Top 10 (2025) knowledge base (`knowledge/owasp_top10_2025.md`) | Data | [ ] |
| 3.9 | Implement Security Agent ReAct loop (`app/agents/security_agent.py`) | Code | [ ] |
| 3.10 | Implement base agent interface (`app/agents/base_agent.py`) | Code | [ ] |
| 3.11 | Set up Groq LLM client via LangChain (`ChatGroq`) | Code | [ ] |
| 3.12 | Implement structured output parsing (JSON → Finding objects) | Code | [ ] |
| 3.13 | Create 10 synthetic security-vulnerable PRs for testing | Data | [ ] |
| 3.14 | Evaluate Security Agent on synthetic dataset — measure precision/recall | Eval | [ ] |
| 3.15 | Iterate on system prompt based on eval results | Prompt | [ ] |

### WEEK 4: Performance Agent v1
**Goal:** Performance Agent detects N+1 queries, complexity issues, returns findings.

| # | Task | Type | Status |
|---|------|------|--------|
| 4.1 | Create Python AST analyzer tool (`app/tools/ast_analyzer.py`) | Code | [ ] |
| 4.2 | Implement N+1 query pattern detector (Django/SQLAlchemy ORM patterns) | Code | [ ] |
| 4.3 | Create radon complexity tool (`app/tools/radon_tool.py`) | Code | [ ] |
| 4.4 | Write Performance Agent system prompt (`prompts/performance_system.md`) | Prompt | [ ] |
| 4.5 | Prepare DDIA patterns knowledge base (`knowledge/ddia_patterns.md`) | Data | [ ] |
| 4.6 | Implement Performance Agent ReAct loop (`app/agents/performance_agent.py`) | Code | [ ] |
| 4.7 | Fetch 10 Django PRs with known performance issues for testing | Data | [ ] |
| 4.8 | Evaluate Performance Agent on Django PR dataset | Eval | [ ] |
| 4.9 | Iterate on system prompt based on eval results | Prompt | [ ] |

### WEEK 5: Style Agent v1
**Goal:** Style Agent checks naming, complexity, dead code, test coverage gaps.

| # | Task | Type | Status |
|---|------|------|--------|
| 5.1 | Create linter tool wrapper — Ruff/ESLint/pylint (`app/tools/linter_tool.py`) | Code | [ ] |
| 5.2 | Implement dead code detector (unused imports, unreachable branches) | Code | [ ] |
| 5.3 | Write Style Agent system prompt (`prompts/style_system.md`) | Prompt | [ ] |
| 5.4 | Prepare language style guides knowledge base (`knowledge/style_guides/`) | Data | [ ] |
| 5.5 | Implement Style Agent ReAct loop (`app/agents/style_agent.py`) | Code | [ ] |
| 5.6 | Fetch 10 Exercism PRs with style/refactoring issues | Data | [ ] |
| 5.7 | Evaluate Style Agent on Exercism dataset | Eval | [ ] |
| 5.8 | Iterate on system prompt based on eval results | Prompt | [ ] |

### WEEK 6: ChromaDB + RAG Context
**Goal:** Full RAG pipeline — embed repo, retrieve context, inject into agents.

| # | Task | Type | Status |
|---|------|------|--------|
| 6.1 | Set up sentence-transformers embedding pipeline (`app/context/embedder.py`) | Code | [ ] |
| 6.2 | **Run embedding model on RTX 5070 via WSL** — benchmark speed | GPU | [ ] |
| 6.3 | Implement ChromaDB repo indexer (`app/context/indexer.py`) — chunk files, upsert | Code | [ ] |
| 6.4 | Implement RAG retriever (`app/context/retriever.py`) — query by diff content | Code | [ ] |
| 6.5 | Integrate RAG context into Security Agent | Code | [ ] |
| 6.6 | Integrate RAG context into Performance Agent | Code | [ ] |
| 6.7 | Integrate RAG context into Style Agent | Code | [ ] |
| 6.8 | Evaluate: does cross-file RAG context improve recall vs. diff-only? | Eval | [ ] |
| 6.9 | Optimize chunk size and retrieval top-k for quality vs. latency | Code | [ ] |
| 6.10 | Limit repo index to 500 most recently changed files (Render memory constraint) | Code | [ ] |

### WEEK 7: Synthesizer Agent
**Goal:** Deduplication, conflict resolution, Health Score, executive summary, full pipeline.

| # | Task | Type | Status |
|---|------|------|--------|
| 7.1 | Write Synthesizer system prompt (`prompts/synthesizer_system.md`) | Prompt | [ ] |
| 7.2 | Implement deduplication logic (cosine similarity on findings via ChromaDB) | Code | [ ] |
| 7.3 | Implement severity conflict resolution (Security > Performance > Style precedence) | Code | [ ] |
| 7.4 | Implement composite re-ranking: severity × exploitability × fix_complexity | Code | [ ] |
| 7.5 | Implement PR Health Score formula (0-100) (`app/services/health_score.py`) | Code | [ ] |
| 7.6 | Implement executive summary generation (3-5 sentences) | Code | [ ] |
| 7.7 | Implement auto-block logic (Critical findings → block merge recommendation) | Code | [ ] |
| 7.8 | Implement Synthesizer Agent (`app/agents/synthesizer.py`) | Code | [ ] |
| 7.9 | Build main orchestrator (`app/services/orchestrator.py`) — ties everything together | Code | [ ] |
| 7.10 | Implement Gemini Flash fallback when Groq quota exhausted | Code | [ ] |
| 7.11 | Full end-to-end pipeline test: PR → agents → synthesizer → GitHub comments | Test | [ ] |
| 7.12 | Write unit tests for Health Score formula | Test | [ ] |
| 7.13 | Write unit tests for deduplication with synthetic conflicting findings | Test | [ ] |
| 7.14 | Implement Neon Postgres write (store review record) | Code | [ ] |

### WEEK 8: Next.js Dashboard
**Goal:** Dashboard on Vercel showing review history, Health Scores, charts.

| # | Task | Type | Status |
|---|------|------|--------|
| 8.1 | Initialize Next.js app in `dashboard/` with TypeScript | Code | [ ] |
| 8.2 | Deploy to Vercel (connect GitHub repo) | Deploy | [ ] |
| 8.3 | Create TypeScript types matching backend schemas (`lib/types.ts`) | Code | [ ] |
| 8.4 | Create API fetch wrapper (`lib/api.ts`) — calls FastAPI backend | Code | [ ] |
| 8.5 | Build `HealthScoreRing` component (circular gauge, animated) | Code | [ ] |
| 8.6 | Build `SeverityBadge` component (color-coded pills) | Code | [ ] |
| 8.7 | Build `TrendChart` component (Recharts LineChart, 30-day trend) | Code | [ ] |
| 8.8 | Build `FindingsTable` component (sortable, filterable) | Code | [ ] |
| 8.9 | Build `AgentBreakdown` component (3-column cards) | Code | [ ] |
| 8.10 | Build `/` page — Repository Overview (connected repos, avg scores) | Code | [ ] |
| 8.11 | Build `/repos/[owner]/[repo]` page — Repo Detail (charts, PR list) | Code | [ ] |
| 8.12 | Build `/repos/[owner]/[repo]/prs/[number]` page — PR Review Detail | Code | [ ] |
| 8.13 | Add FastAPI CORS middleware for Vercel domain | Code | [ ] |
| 8.14 | Implement REST API endpoints on FastAPI side for dashboard | Code | [ ] |

### WEEK 9: Polish & Evaluation
**Goal:** Full benchmark, prompt tuning, latency optimization, documentation.

| # | Task | Type | Status |
|---|------|------|--------|
| 9.1 | Curate full 20-PR benchmark dataset (Django, Next.js, synthetic, Exercism) | Data | [ ] |
| 9.2 | Build evaluation harness (`tests/eval/run_eval.py`) | Code | [ ] |
| 9.3 | Run full benchmark — measure precision, recall, latency per agent | Eval | [ ] |
| 9.4 | Tune agent prompts to reduce false positives (target: <30% FP rate) | Prompt | [ ] |
| 9.5 | Implement confidence threshold: findings <0.6 shown as 'Suggestions' | Code | [ ] |
| 9.6 | Latency optimization: measure p50/p95/p99 per PR size bucket | Eval | [ ] |
| 9.7 | Optimize Groq API calls (reduce token usage, cache prompts) | Code | [ ] |
| 9.8 | Write comprehensive README.md | Docs | [ ] |
| 9.9 | Write installation guide in README | Docs | [ ] |
| 9.10 | Add GitHub Actions pre-warm cron (ping /health every 10min) | CI/CD | [ ] |

### WEEK 10: Launch & Promotion
**Goal:** Live on GitHub Marketplace, installed on public repos, launch posts published.

| # | Task | Type | Status |
|---|------|------|--------|
| 10.1 | Install Sentinel AI on 3 public open-source repos | Launch | [ ] |
| 10.2 | Record demo video (screen recording: PR opened → comments posted) | Content | [ ] |
| 10.3 | Write Dev.to / HackerNews launch post | Content | [ ] |
| 10.4 | Write LinkedIn demo post | Content | [ ] |
| 10.5 | Submit to GitHub Marketplace (needs privacy policy, logo, description) | Launch | [ ] |
| 10.6 | Create sentinel.yml.example per-repo config template | Code | [ ] |
| 10.7 | Monitor first 48 hours — fix any production bugs | Ops | [ ] |

---

## 6. Non-Coding Tasks

These tasks don't involve writing project code but are essential for the project:

### 6.1 External Service Provisioning

| Service | Action | URL | Notes |
|---------|--------|-----|-------|
| **GitHub App** | Register new app | github.com/settings/apps/new | Need: App ID, Private Key (.pem), Webhook Secret |
| **Groq** | Get API key | console.groq.com | Free: 14,400 req/day |
| **Google AI Studio** | Get Gemini key | aistudio.google.com | Free: 1M tokens/day |
| **Neon.tech** | Create Postgres DB | console.neon.tech | Free: 512MB, create `pr_reviews` table |
| **Upstash** | Create Redis instance | console.upstash.com | Free: 10K req/day |
| **Render** | Create web service | dashboard.render.com | Free tier, connect GitHub repo |
| **Vercel** | Create project | vercel.com/new | Free hobby tier, connect dashboard/ |
| **ngrok** | Install for local testing | ngrok.com | Free: 1 tunnel |

### 6.2 GitHub App Configuration

**Permissions required:**
- Pull requests: Read & Write
- Contents: Read
- Metadata: Read
- Commit statuses: Write (optional)

**Webhook events to subscribe:**
- `pull_request` (opened, synchronize, reopened, ready_for_review)
- `pull_request_review_comment` (for @sentinel-ai re-review)

### 6.3 Data Curation Tasks

| Dataset | Source | Count | Purpose |
|---------|--------|-------|---------|
| Synthetic security PRs | Hand-crafted | 10 PRs | SQL injection, XSS, IDOR, hardcoded secrets |
| Django security PRs | github.com/django/django | 5 PRs | Real-world Python security fixes |
| Next.js performance PRs | github.com/vercel/next.js | 5 PRs | JS/TS performance changes |
| Exercism style PRs | github.com/exercism | 5 PRs | Naming, complexity, documentation issues |
| Mixed benchmark set | All above | 20 PRs | Full evaluation benchmark |

### 6.4 Knowledge Base Curation

| Document | Source | For Agent |
|----------|--------|-----------|
| OWASP Top 10 (2025) | owasp.org | Security Agent RAG |
| DDIA performance patterns | "Designing Data-Intensive Applications" | Performance Agent RAG |
| Python style guide (PEP 8) | python.org | Style Agent RAG |
| JavaScript style guide | Various (Airbnb, Google) | Style Agent RAG |
| TypeScript best practices | typescript-eslint.io | Style Agent RAG |

---

## 7. GPU / WSL Tasks

Your **RTX 5070** with WSL will be used for:

### 7.1 sentence-transformers Embedding (Required)

**No training needed** — these are pre-trained models used for embedding generation.

```
Model: all-MiniLM-L6-v2 (or all-mpnet-base-v2 for higher quality)
Task: Embed code chunks for ChromaDB indexing
Where: Runs locally during repo indexing (can also run on Render CPU, slower)
GPU benefit: ~10-50x faster embedding generation vs CPU
```

**Setup steps:**
1. Ensure CUDA toolkit installed in WSL (`nvidia-smi` should show RTX 5070)
2. `pip install sentence-transformers torch` (with CUDA support)
3. Benchmark: embed 1000 code chunks, measure time GPU vs CPU
4. Decision: if embedding is fast enough on CPU, skip GPU for deployment simplicity

### 7.2 Local LLM Testing (Optional, Recommended)

Running a local LLM for testing avoids burning Groq API quota during development:

```
Model: Llama-3.1-8B-Instruct (via Ollama or vLLM)
Task: Test agent prompts locally before hitting Groq
GPU benefit: Full inference locally, no API calls, no quota burn
```

**Setup steps:**
1. Install Ollama in WSL: `curl -fsSL https://ollama.com/install.sh | sh`
2. Pull model: `ollama pull llama3.1:8b`
3. Use for prompt iteration — switch to Groq (70B) for production quality

### 7.3 What You Do NOT Need to Train

| Item | Reason |
|------|--------|
| LLM (Llama-3.1-70B) | Used via Groq API — inference only, no fine-tuning |
| sentence-transformers | Pre-trained model, no fine-tuning needed for code embeddings |
| Semgrep/Bandit/radon | Rule-based tools, no ML training |
| Agent prompts | Iterative prompt engineering, not model training |

**Bottom line:** This project is an **inference and orchestration** project, not a training project. Your GPU is used for fast local embeddings and optional local LLM testing — no model training required.

---

## 8. Data Models & Schemas

### 8.1 Finding (per agent output)

```python
class Finding(BaseModel):
    agent: Literal['security', 'performance', 'style']
    file_path: str              # e.g. 'src/auth/login.py'
    line_start: int
    line_end: int
    severity: Literal['critical', 'high', 'medium', 'low']
    category: str               # e.g. 'sql_injection', 'n+1_query', 'naming'
    title: str                  # Short one-liner
    description: str            # Full explanation
    suggested_fix: str          # Corrected code snippet
    cwe_id: Optional[str]       # For security findings (e.g. 'CWE-89')
    confidence: float           # 0.0 – 1.0
```

### 8.2 SynthesizedReview (Synthesizer output)

```python
class SynthesizedReview(BaseModel):
    health_score: int                        # 0-100
    executive_summary: str                   # 3-5 sentences
    recommendation: Literal['approve', 'request_changes', 'block']
    findings: List[Finding]                  # Deduplicated, re-ranked
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    duration_ms: int
```

### 8.3 PR Review Record (Neon Postgres)

```sql
CREATE TABLE pr_reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_full_name  TEXT NOT NULL,
    pr_number       INT NOT NULL,
    commit_sha      TEXT NOT NULL,
    health_score    INT NOT NULL,
    critical_count  INT DEFAULT 0,
    high_count      INT DEFAULT 0,
    medium_count    INT DEFAULT 0,
    low_count       INT DEFAULT 0,
    summary         TEXT,
    findings        JSONB NOT NULL,
    duration_ms     INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pr_reviews_repo ON pr_reviews(repo_full_name);
CREATE INDEX idx_pr_reviews_sha ON pr_reviews(commit_sha);
```

---

## 9. API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /webhook/github` | POST | Receive GitHub webhook, validate HMAC, enqueue analysis |
| `GET /api/repos/{owner}/{repo}/reviews` | GET | Paginated PR review list + Health Score trend |
| `GET /api/repos/{owner}/{repo}/reviews/{pr_number}` | GET | Full findings for specific PR |
| `GET /api/repos/{owner}/{repo}/stats` | GET | Aggregate stats: avg score, top categories, 30-day trend |
| `POST /api/repos/{owner}/{repo}/reanalyze/{pr_number}` | POST | Re-trigger analysis (bypass cache) |
| `GET /health` | GET | Health check: agent status, Groq quota remaining |

---

## 10. Agent Prompt Design

Each agent prompt must include:

1. **Role definition** — who the agent is (e.g., "senior AppSec engineer")
2. **Scope boundaries** — what to look for and what to ignore
3. **Output schema** — exact JSON structure expected
4. **Severity guidelines** — when to use Critical vs. High vs. Medium vs. Low
5. **Confidence scoring** — how to self-assess confidence (0.0-1.0)
6. **Examples** — 2-3 few-shot examples of good findings
7. **Anti-patterns** — common false positives to avoid

Prompts are stored in `prompts/` as Markdown files and loaded at agent initialization.

---

## 11. Evaluation Plan

### 11.1 Metrics

| Metric | Target | Formula |
|--------|--------|---------|
| Security precision | >70% | true_positives / (true_positives + false_positives) |
| Performance recall | >60% | true_positives / (true_positives + false_negatives) |
| Deduplication rate | >15% | duplicates_removed / total_findings |
| e2e latency (p95) | <20s | Time from webhook to first comment posted |
| Groq quota usage | <10K/day | Total API calls per day |
| System uptime | >95% | (total_time - downtime) / total_time |

### 11.2 Evaluation Harness

Located in `tests/eval/`:
- `dataset/` — 20 PRs as JSON fixtures (diff, expected findings, ground truth labels)
- `run_eval.py` — Runs each PR through full pipeline, compares output vs ground truth
- `metrics.py` — Computes precision, recall, F1, latency percentiles
- Results logged to console + optionally to LangSmith (free self-hosted)

---

## 12. Deployment Checklist

### Render (FastAPI Backend)
- [ ] `render.yaml` configured with build + start commands
- [ ] Environment variables set in Render dashboard
- [ ] Health check endpoint (`/health`) configured
- [ ] Auto-deploy from `main` branch enabled

### Vercel (Next.js Dashboard)
- [ ] Connected to GitHub repo `dashboard/` directory
- [ ] Environment variable: `NEXT_PUBLIC_API_URL` pointing to Render backend
- [ ] Custom domain (optional)

### GitHub App
- [ ] App registered with correct permissions
- [ ] Webhook URL set to Render endpoint (`/webhook/github`)
- [ ] Private key (.pem) downloaded and stored securely
- [ ] App installed on test repo for development

### GitHub Actions
- [ ] CI workflow: lint (ruff) + test (pytest) on push/PR
- [ ] Pre-warm cron: ping /health every 10 minutes during working hours

---

## 13. Progress Tracker

### Overall Status

| Week | Milestone | Status | Notes |
|------|-----------|--------|-------|
| 1 | Foundation & Setup | COMPLETE | All services provisioned, project scaffolded |
| 2 | GitHub Integration | COMPLETE | E2E tested: webhook → fetch → comment on PR #1 |
| 3 | Security Agent v1 | COMPLETE | Bandit + Llama-3.3-70B, live-tested on PR #3, 4 findings |
| 4 | Performance Agent v1 | COMPLETE | Radon complexity + Llama-3.3-70B, 3 findings on PR #4 |
| 5 | Style Agent v1 | COMPLETE | Ruff linter + Llama-3.3-70B, 6 findings on PR #4 |
| 6 | ChromaDB + RAG Context | COMPLETE | sentence-transformers + ChromaDB, integrated into all agents |
| 7 | Synthesizer Agent | COMPLETE | Dedup, conflict resolution, Health Score formula, exec summary |
| 8 | Next.js Dashboard | COMPLETE | Next.js + Tailwind + Recharts, mock data, all pages |
| 9 | Polish & Evaluation | COMPLETE | Eval harness, metrics, README, DB persistence |
| 10 | Launch & Promotion | COMPLETE | Render config, Vercel ready, API endpoints for dashboard |

### Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-19 | Project plan created | Starting from scratch, PDF spec as source of truth |
| 2026-03-19 | Project renamed to "Ninja Code Guard" | User's personal branding choice |
| 2026-03-19 | GitHub App: "Ninja's Code Guard" (ID: 3133457) | Registered and tested with live PR |
| 2026-03-19 | Test repo: ninjacode911/codeguard-test | Used for e2e webhook testing |
| 2026-03-19 | Fail-open pattern for Redis cache | Missing a review is worse than duplicating |
| 2026-03-19 | Background tasks for webhook processing | GitHub's 10s timeout requires async processing |

---

*Last updated: 2026-03-19*

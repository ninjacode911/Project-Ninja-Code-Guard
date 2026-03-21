<div align="center">

# Ninja Code Guard

**Multi-Agent AI Code Review — Security, Performance, and Style in Parallel**

*Reviews your pull requests the way a senior engineering team would.*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=flat&logo=next.js&logoColor=white)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-Source%20Available-blue.svg)](LICENSE)
[![Vercel](https://img.shields.io/badge/%E2%96%B2%20Vercel-Live%20Demo-000000?style=flat&logo=vercel&logoColor=white)](https://projectninjacodeguard.vercel.app/)

[**Live Demo →**](https://projectninjacodeguard.vercel.app/)&nbsp;&nbsp;|&nbsp;&nbsp;[**Project Plan →**](PROJECT_PLAN.md)

</div>

---

## Overview

Ninja Code Guard listens for GitHub pull request webhooks and deploys three specialized AI agents — Security, Performance, and Style — in parallel via `asyncio.gather()`. Each agent combines deterministic static analysis (Bandit, Radon, Ruff) with Llama-3.3-70B reasoning to produce domain-specific findings.

A Synthesizer agent then deduplicates overlapping findings using cosine similarity, resolves severity conflicts, computes a Health Score (0–100), and posts a single prioritized review directly to the PR as inline GitHub comments. A Next.js dashboard provides real-time visibility into Health Score trends across all connected repositories.

**What makes this different from typical linting tools:**
- **3 agents run in parallel** — total latency is `max(agent_latencies)` not `sum(agent_latencies)`, cutting review time from ~15s to ~5s.
- **Static tools + LLM reasoning** — Bandit/Radon/Ruff catch mechanical patterns; the LLM understands context, intent, and cross-function data flow.
- **RAG context pipeline** — files are embedded into ChromaDB so agents retrieve semantically related code when analyzing a change.
- **Cosine similarity dedup** — the Synthesizer avoids posting duplicate findings when multiple agents flag the same line.
- **Inline GitHub comments** — findings are anchored to specific line numbers in the diff, not dumped in a wall of text.

---

## Architecture

```
PR opened on GitHub
      |
      v
Webhook received  ->  HMAC-SHA256 validated (prevents fake triggers)
      |
      v
Redis cache check  ->  skip if already reviewed (prevents duplicate reviews)
      |
      v
GitHub API  ->  fetch PR diff + full file contents + commit history
      |
      v
RAG Context  ->  embed files  ->  ChromaDB  ->  retrieve related code chunks
      |
      v
+---------------------------------------------+
|        3 Agents — asyncio.gather()           |
|                                              |
|  Security Agent    Performance Agent  Style  |
|  Bandit + LLM      Radon + LLM        Ruff   |
|  ~3-5s             ~3-5s              + LLM  |
+--------------------+------------------------+
                     |
                     v
Synthesizer Agent
  -> cosine similarity dedup across agent findings
  -> severity conflict resolution
  -> rank by importance
  -> Health Score computation (0-100)
  -> executive summary generation
      |
      v
GitHub API  ->  inline PR comments + summary comment with Health Score
      |
      v
Dashboard   ->  Health Score trends + per-repo + per-PR breakdown
```

---

## What Each Agent Does

| Agent | Static Tools | What It Catches |
|-------|-------------|----------------|
| **Security** | Bandit, detect-secrets | SQL injection (CWE-89), command injection (CWE-78), hardcoded secrets (CWE-798), weak crypto, SSRF, XSS |
| **Performance** | Radon (cyclomatic complexity) | N+1 query patterns, O(n2) nested loops, blocking I/O in async context, missing caching, inefficient data structures |
| **Style** | Ruff (Rust-based linter) | Unused imports, dead code, non-descriptive naming, missing error handling, code duplication, magic numbers |
| **Synthesizer** | Cosine similarity dedup | Cross-agent deduplication, severity resolution, composite Health Score (0-100), executive summary |

---

## Features

| Feature | Detail |
|---------|--------|
| **Parallel agents** | `asyncio.gather()` — latency is max not sum (~5s vs ~15s sequential) |
| **HMAC-SHA256 validation** | Webhook signature verified before any processing begins |
| **Redis deduplication** | Prevents duplicate reviews on rapid-fire commit pushes |
| **RAG context** | ChromaDB retrieval provides agents with related code for better cross-function reasoning |
| **Inline comments** | Findings anchored to specific line numbers in the PR diff |
| **Health Score** | 0-100 composite metric posted as a badge with every review |
| **Dashboard** | Next.js: repo overview, Health Score trends, per-PR review history table |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.11+, FastAPI, Uvicorn | Webhook server and agent orchestration |
| **Frontend** | Next.js 15, React 19, TypeScript | Health Score dashboard and PR review history |
| **LLM** | Groq Llama-3.3-70B | Agent reasoning for all 3 domain agents + Synthesizer |
| **RAG** | ChromaDB, sentence-transformers | File embedding and semantic context retrieval |
| **Cache** | Redis | PR deduplication and review state caching |
| **Static Analysis** | Bandit, detect-secrets, Radon, Ruff | Fast deterministic pattern detection |
| **GitHub** | PyGitHub, GitHub App | Webhook handling, diff fetch, inline comment posting |
| **Deployment** | Render (backend), Vercel (dashboard) | Cloud hosting for API and Next.js dashboard |

---

## Project Structure

```
app/
├── main.py                  # FastAPI webhook server entry point
├── agents/
│   ├── base_agent.py        # Shared agent interface and LLM client
│   ├── security_agent.py    # Bandit + detect-secrets + Llama reasoning
│   ├── performance_agent.py # Radon cyclomatic complexity + Llama reasoning
│   ├── style_agent.py       # Ruff + Llama reasoning
│   └── synthesizer.py       # Dedup, rank, Health Score, executive summary
├── context/                 # RAG pipeline (ChromaDB + sentence-transformers)
├── github/                  # GitHub API client + inline comment posting
├── models/                  # Pydantic request/response models
├── services/                # Agent orchestration, Health Score computation
└── tools/                   # Bandit, Radon, Ruff, detect-secrets wrappers

dashboard/
├── app/
│   ├── page.tsx             # Repository overview + Health Score cards
│   ├── repos/[id]/page.tsx  # Repo detail: Health Score trends + PR table
│   └── layout.tsx           # App shell with navigation
├── components/              # Health Score chart, PR review table, stat cards
└── lib/                     # API client, TypeScript interfaces

prompts/                     # System prompts for each agent and Synthesizer
tests/                       # pytest test suite
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Redis running locally (`redis-server`)
- A GitHub App ([create one here](https://github.com/settings/apps/new)) with webhook and PR read/write permissions
- A Groq API key ([free at console.groq.com](https://console.groq.com))

### 1. Clone and install

```bash
git clone https://github.com/ninjacode911/Project-Ninja-Code-Guard.git
cd Project-Ninja-Code-Guard
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
# Edit .env and add:
# GITHUB_APP_ID=your_app_id
# GITHUB_PRIVATE_KEY_PATH=./keys/private-key.pem
# GITHUB_WEBHOOK_SECRET=your_webhook_secret
# GROQ_API_KEY=your_groq_key
# REDIS_URL=redis://localhost:6379
```

### 3. Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. Expose webhook (local dev)

```bash
ngrok http 8000
# Set the ngrok URL as your GitHub App's webhook URL
```

---

## Screenshots

### PR Review Comment
*Ninja Code Guard posts a Health Score badge, severity breakdown, and inline findings directly to the PR.*

![PR Review Comment](assets/pr-review-comment.png)

---

### Dashboard — Repository Overview
*Monitor all connected repos at a glance — Health Score, PRs reviewed, and issues found.*

![Dashboard Home](assets/dashboard-home.png)

---

### Repo Detail — Health Score Trends
*Track code quality over time with Health Score trend charts and per-PR review history.*

![Repo Detail](assets/repo-detail.png)

---

### PR Review Table
*Drill into any repo to see every PR reviewed with severity counts and scores.*

![PR Review Table](assets/pr-review-table.png)

---

## License

**Source Available — All Rights Reserved.** See [LICENSE](LICENSE) for full terms.

The source code is publicly visible for viewing and educational purposes. Any use in personal, commercial, or academic projects requires explicit written permission from the author.

To request permission: navnitamrutharaj1234@gmail.com

**Author:** Navnit Amrutharaj

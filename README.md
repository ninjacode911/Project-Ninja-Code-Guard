<div align="center">

# Ninja Code Guard

**Multi-agent AI code review system that reviews GitHub pull requests the way a senior engineering team would**

[![Live Demo](https://img.shields.io/badge/Live_Demo-projectninjacodeguard.vercel.app-8b5cf6?style=for-the-badge&logo=vercel)](https://projectninjacodeguard.vercel.app/)
[![License](https://img.shields.io/badge/License-Source_Available-f59e0b?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?style=for-the-badge&logo=python)](app/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=for-the-badge&logo=next.js)](dashboard/)

3 agents in parallel. One prioritized review posted directly to your PR.

</div>

---

## Overview

Ninja Code Guard listens for GitHub pull request webhooks and deploys three specialized AI agents — Security, Performance, and Style — in parallel. Each agent combines deterministic static analysis tools with Llama-3.3-70B reasoning to produce domain-specific findings.

A Synthesizer agent then deduplicates overlapping findings, resolves severity conflicts, computes a Health Score (0–100), and posts a single prioritized review directly to the PR as inline GitHub comments. A Next.js dashboard provides real-time visibility into Health Score trends across all connected repositories.

---

## Pipeline

```
PR opened on GitHub
        |
        v
   Webhook received  ->  HMAC-SHA256 validated
        |
        v
   Redis cache check  ->  skip if already reviewed
        |
        v
   GitHub API  ->  fetch diff + full file contents
        |
        v
   RAG context  ->  embed files  ->  ChromaDB  ->  retrieve related code
        |
        v
+-------------------------------------------+
|      3 Agents — asyncio.gather()          |
|  Security       Performance      Style    |
|  Bandit+LLM     Radon+LLM        Ruff+LLM|
+--------------------+----------------------+
                     |
                     v
   Synthesizer  ->  deduplicate  ->  rank  ->  Health Score
        |
        v
   GitHub  ->  inline comments + summary comment
```

---

## What Each Agent Does

| Agent | Static Tools | What It Catches |
|-------|-------------|----------------|
| **Security** | Bandit, detect-secrets | SQL injection, command injection, hardcoded secrets, weak crypto, SSRF, XSS |
| **Performance** | Radon (cyclomatic complexity) | N+1 queries, O(n2) loops, blocking I/O in async, missing cache, inefficient structures |
| **Style** | Ruff (Rust-based linter) | Unused imports, dead code, bad naming, missing error handling, magic numbers |
| **Synthesizer** | Cosine similarity dedup | Cross-agent dedup, severity resolution, composite Health Score (0-100), executive summary |

---

## Features

| Capability | Details |
|-----------|---------|
| **Parallel review** | All 3 agents run via `asyncio.gather()` — latency is max not sum (~5s vs ~15s) |
| **HMAC validation** | Webhook signature verified before any processing |
| **Redis dedup** | Prevents duplicate reviews on rapid commit pushes |
| **RAG context** | ChromaDB retrieval gives agents related code for better cross-function reasoning |
| **Inline comments** | Findings anchored to specific line numbers in the PR diff |
| **Health Score** | 0-100 composite metric posted with every review |
| **Dashboard** | Next.js: repo overview, Health Score trends, per-PR review history |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Frontend | Next.js 15, React 19, TypeScript |
| LLM | Groq Llama-3.3-70B |
| RAG | ChromaDB, sentence-transformers |
| Cache | Redis |
| Static Analysis | Bandit, detect-secrets, Radon, Ruff |
| GitHub | PyGitHub (webhooks, inline comments, PR API) |
| Deployment | Render (backend), Vercel (dashboard) |

---

## Project Structure

```
app/
├── main.py             # FastAPI webhook server
├── agents/
│   ├── security_agent.py    # Bandit + Llama security review
│   ├── performance_agent.py # Radon + Llama performance review
│   ├── style_agent.py       # Ruff + Llama style review
│   ├── synthesizer.py       # Dedup, rank, Health Score
│   └── base_agent.py        # Shared agent interface
├── context/            # RAG pipeline (ChromaDB + sentence-transformers)
├── github/             # GitHub API client + comment posting
├── models/             # Pydantic models
├── services/           # Orchestration, Health Score
├── tools/              # Bandit, Radon, Ruff, detect-secrets wrappers
└── prompts/            # Agent system prompts

dashboard/
├── app/                # Next.js pages (overview, repo detail, PR table)
├── components/         # UI components
└── lib/                # API client, TypeScript types
```

---

## Quick Start

```bash
git clone https://github.com/ninjacode911/Project-Ninja-Code-Guard.git
cd Project-Ninja-Code-Guard
pip install -r requirements.txt
```

Create a `.env` file:

```
GITHUB_APP_ID=your_app_id
GITHUB_PRIVATE_KEY_PATH=./keys/private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret
GROQ_API_KEY=your_groq_key
REDIS_URL=redis://localhost:6379
```

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Expose via ngrok for local development:

```bash
ngrok http 8000
```

---

## License

Source Available — All Rights Reserved. See [LICENSE](LICENSE) for details.

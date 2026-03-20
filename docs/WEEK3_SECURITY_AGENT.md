# Week 3: Security Agent v1 — Detailed Documentation

> **Goal:** Build the Security Agent — LLM + static analysis tools that find real vulnerabilities.
> **Status:** Complete — Live-tested on PR #3 with SQL injection code
> **Date:** 2026-03-19
> **Test PR:** github.com/ninjacode911/codeguard-test/pull/3
> **Result:** 4 findings (3 critical SQL injections, 1 medium hardcoded key), Health Score 20/100

---

## What We Built

The Security Agent is the first AI-powered domain agent. It combines **static analysis tools**
(Bandit, detect-secrets) with **LLM reasoning** (Groq Llama-3.3-70B) to find security
vulnerabilities in PR code changes.

```
PR Diff + File Contents
        │
        ▼
┌───────────────────────────────┐
│     Static Analysis           │  Bandit: 3 findings (SQL injection patterns)
│  Bandit (Python AST rules)    │  detect-secrets: 0 findings
│  detect-secrets (credentials) │  Time: ~1 second
└───────────┬───────────────────┘
            │ tool output as text
            ▼
┌───────────────────────────────┐
│     Groq LLM                  │  Model: llama-3.3-70b-versatile
│  System prompt: AppSec expert │  Input: diff + files + Bandit results
│  Structured output: JSON      │  Output: 4 Finding objects
│  Temperature: 0.1             │  Time: ~2.2 seconds
└───────────┬───────────────────┘
            │ Finding[]
            ▼
┌───────────────────────────────┐
│     Comment Formatter         │  Health Score: 20/100
│  Summary + inline comments    │  Recommendation: Block Merge
│  Posted to GitHub PR          │  Severity table + details
└───────────────────────────────┘
```

---

## Step-by-Step Implementation Log

### Step 1: Install Dependencies

```bash
pip install langchain langchain-groq langchain-core bandit detect-secrets
```

| Package | Purpose |
|---------|---------|
| `langchain` | Agent orchestration framework |
| `langchain-groq` | Groq API integration (ChatGroq class) |
| `langchain-core` | Prompt templates, structured output |
| `bandit` | Python AST security linter |
| `detect-secrets` | Credential/API key scanner |

---

### Step 2: Base Agent Interface (app/agents/base_agent.py)

**Design Pattern: Template Method**

All three domain agents (Security, Performance, Style) follow the same flow:
1. Run static analysis tools
2. Build a prompt with diff + files + tool output
3. Call the LLM with structured output
4. Convert LLM output to Finding objects

The base class implements this algorithm skeleton. Subclasses only override what's different:
- `agent_name` — identifies the agent
- `system_prompt` — the LLM persona and instructions
- `run_static_analysis()` — which tools to run

```python
class BaseAgent(ABC):
    def __init__(self):
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.1,     # Nearly deterministic
            max_tokens=4096,
        )

    async def review(self, pr_data: PRData) -> list[Finding]:
        static_results = await self.run_static_analysis(pr_data)  # Subclass
        prompt = self._build_prompt()
        structured_llm = self.llm.with_structured_output(AgentFindings)
        chain = prompt | structured_llm  # LangChain LCEL pipe
        result = await chain.ainvoke({...})
        return self._convert_to_findings(result)
```

**Key concepts:**

#### ChatGroq Configuration
- **model="llama-3.3-70b-versatile"**: Groq runs Meta's Llama 3.3 70B parameter model at 500+ tokens/sec. Originally we used `llama-3.1-70b-versatile` but it was decommissioned.
- **temperature=0.1**: Near-deterministic output. Code review should be consistent — the same code should get the same findings. Not exactly 0 to allow slight variation.
- **max_tokens=4096**: Enough for ~20 detailed findings. Each finding is ~200 tokens.

#### Structured Output (with_structured_output)
Instead of asking the LLM to return JSON and parsing it ourselves (error-prone), LangChain's
`with_structured_output()` constrains the LLM:
1. Adds the JSON schema to the system prompt automatically
2. Enables JSON mode in the model's response format
3. Validates the response against our Pydantic schema
4. If validation fails, it can retry

This eliminates an entire class of bugs (malformed JSON, missing fields, wrong types).

#### LCEL Pipe Operator (prompt | structured_llm)
LangChain Expression Language (LCEL) uses Python's `|` operator to chain components:
```python
chain = prompt | structured_llm
# Equivalent to: result = structured_llm(prompt.format(...))
```
This is a functional programming pattern called "composition" — small, testable units
combined into a pipeline.

#### Error Handling — Graceful Degradation
```python
async def review(self, pr_data):
    try:
        # ... run agents ...
        return findings
    except Exception as e:
        logger.error("Agent review failed", ...)
        return []  # Don't crash — other agents can still contribute
```
If the Security Agent fails (Groq API down, rate limited), the pipeline continues.
The Performance and Style agents can still post their findings.

**Interview talking point:** "Each agent is implemented using the Template Method pattern
with a shared base class. The LLM is configured with near-zero temperature for consistency
and uses structured output to guarantee valid JSON. If any single agent fails, the others
continue independently — following the principle of graceful degradation."

---

### Step 3: Security System Prompt (prompts/security_system.md)

**Why the prompt matters more than the code:**
The system prompt IS the agent's expertise. A 1-line code change might not matter,
but a 1-line prompt change can dramatically affect precision and recall.

**Prompt structure (8 sections):**

1. **Role definition:** "You are a senior application security engineer (AppSec)"
   - Sets the LLM's persona and expertise level
   - More specific roles produce better output than generic "you are helpful"

2. **Scope boundaries:** "Security vulnerabilities ONLY"
   - Prevents overlap with Performance and Style agents
   - Without this, the Security Agent would comment on naming conventions

3. **Severity guidelines with examples:**
   - Critical: SQL injection, command injection, RCE
   - High: XSS, path traversal, SSRF
   - Medium: Hardcoded secrets, weak crypto
   - Low: Missing logging, permissive CORS

4. **CWE IDs for each category:**
   - CWE-89 (SQL Injection), CWE-78 (Command Injection), etc.
   - These are industry-standard vulnerability identifiers
   - Including them in the prompt teaches the LLM to output them

5. **Rules (critical for reducing false positives):**
   - "ONLY report findings in CHANGED code" (not pre-existing issues)
   - "Check if input is already sanitized upstream"
   - "If no issues found, return empty list" (don't invent issues)

6. **Output format:** Exact JSON schema the LLM must follow

**Why prompts are stored as Markdown files (not inline strings):**
- They're long (60+ lines) — inline strings clutter the code
- They change frequently during prompt tuning (Week 9)
- Git diff shows prompt changes clearly
- Non-engineers can review/edit them

**Interview talking point:** "The system prompt is structured with explicit role definition,
scope boundaries, severity guidelines with CWE IDs, and strict rules to minimize false
positives. We store prompts as external files for independent version control and
iteration — prompt engineering is the most impactful lever for review quality."

---

### Step 4: Bandit Tool (app/tools/bandit_tool.py)

**What Bandit is:**
An open-source Python security linter that parses code into an Abstract Syntax Tree (AST)
and checks each node against ~40 security rules.

**How we integrate it:**
```
Changed Python files → Write to temp directory → Run `bandit -r <dir> -f json`
→ Parse JSON output → Format as text summary → Include in LLM prompt
```

**Why write to temp files?**
Bandit operates on the filesystem — it reads `.py` files and parses them. We have the
file contents in memory (from GitHub API), so we write them to a temp directory,
run Bandit, then clean up.

**What Bandit caught in our test:**
```
1. [HIGH/HIGH] Possible SQL injection via string-based query construction
   File: app.py, Line: 5
   Test: B608

2. [HIGH/HIGH] Possible SQL injection via string-based query construction
   File: app.py, Line: 9
   Test: B608

3. [HIGH/HIGH] Possible SQL injection via string-based query construction
   File: app.py, Line: 13
   Test: B608
```

All three SQL injection patterns in our test code — correctly identified!

**Error handling:**
- If Bandit isn't installed → log warning, return empty string (LLM-only analysis)
- If Bandit times out (>30s) → kill process, return empty string
- If file write fails → skip that file, continue with others

**Interview talking point:** "We combine Bandit's deterministic pattern matching with LLM
reasoning. Bandit catches mechanical patterns (string formatting in SQL) with zero false
negatives for known rules, while the LLM catches semantic issues (missing auth checks)
that no static tool can detect. The Bandit output is injected into the LLM prompt as
additional context — high-confidence anchors that guide the LLM's analysis."

---

### Step 5: detect-secrets Tool (app/tools/detect_secrets_tool.py)

**What detect-secrets is:**
A tool that scans code for hardcoded credentials using two techniques:
1. **Pattern matching:** Regex patterns for known key formats (AWS keys start with `AKIA`, Stripe keys start with `sk_live_`)
2. **Shannon entropy analysis:** Measures randomness of strings — high entropy = likely a secret

**Shannon entropy explained:**
- `"hello"` → entropy ~2.8 bits/char → predictable, not a secret
- `"a3f8Kx9m2Q"` → entropy ~3.9 bits/char → random, probably a secret
- Threshold is configurable (default ~3.5 bits)

**How it integrates:** Same pattern as Bandit — write files to temp dir, run tool, parse output.

---

### Step 6: Security Agent (app/agents/security_agent.py)

**The simplest file in the project** — only 30 lines of actual code. This is the power of
the Template Method pattern: the base class handles all the complexity.

```python
class SecurityAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "security"

    @property
    def system_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parent.parent.parent / "prompts" / "security_system.md"
        return prompt_path.read_text(encoding="utf-8")

    async def run_static_analysis(self, pr_data: PRData) -> str:
        results = []
        bandit_output = await run_bandit(pr_data.file_contents)
        if bandit_output:
            results.append(bandit_output)
        secrets_output = await run_detect_secrets(pr_data.file_contents)
        if secrets_output:
            results.append(secrets_output)
        return "\n\n".join(results) if results else ""
```

**Interview talking point:** "The Security Agent is 30 lines because all the orchestration
logic lives in the base class. Adding a new agent (Performance, Style) requires implementing
only three things: a name, a prompt, and a static analysis method. This is the Template
Method pattern — the algorithm is fixed, the steps are customizable."

---

### Step 7: Pipeline Integration (app/main.py)

**What changed:** Replaced the dummy comment from Week 2 with real Security Agent output.

**The updated pipeline:**
```python
async def _process_pr_review(...):
    client = GitHubClient(installation_id)
    pr_data = await client.fetch_pr_data(repo_full_name, pr_number)

    # Run Security Agent (Week 4-5: add Performance + Style in parallel)
    security_agent = SecurityAgent()
    findings = await security_agent.review(pr_data)

    # Build temporary review (Week 7: real Synthesizer)
    health_score = 100 - (critical * 25) - (high * 10) - (medium * 5) - (low * 2)
    review = SynthesizedReview(health_score=health_score, findings=findings, ...)

    # Post to GitHub (with inline comment fallback)
    try:
        await client.post_review(repo, pr, sha, body=summary, comments=inline_comments)
    except:
        await client.post_comment(repo, pr, summary)  # Fallback
```

**Inline comment fallback:**
GitHub's review API requires line numbers to be exactly within the diff hunk. The LLM
sometimes returns line numbers from the full file. When this happens (422 error), we
fall back to a summary comment that includes all findings in expandable `<details>` blocks.

---

### Step 8: Live Test Results

**Test PR:** github.com/ninjacode911/codeguard-test/pull/3

**Test code (intentionally vulnerable):**
```python
import sqlite3

def get_user(user_id):
    conn = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE id = {user_id}"  # SQL injection
    return conn.execute(query).fetchone()

def delete_user(name):
    conn = sqlite3.connect("users.db")
    conn.execute(f"DELETE FROM users WHERE name = '{name}'")  # SQL injection

def search_users(query):
    conn = sqlite3.connect("users.db")
    conn.execute(f"SELECT * FROM users WHERE name LIKE '%{query}%'")  # SQL injection

API_KEY = "sk_live_51ABC123secretkey456"  # Hardcoded secret
```

**Pipeline execution (from server logs):**
```
22:36:30  Webhook received — PR #3, sha=18c9758f
22:36:33  Fetched PR data — 1 file, 1 with content
22:36:34  Bandit found 3 issues (SQL injection patterns)
22:36:36  LLM returned 4 findings in 2.2 seconds
22:36:38  Inline comments failed (422) — line numbers not in diff
22:36:39  Fallback summary comment posted
22:36:39  Cached in Redis (7-day TTL)
```

**Result posted to PR:**
- Health Score: 20/100
- 3 Critical (SQL injection in get_user, delete_user, search_users)
- 1 Medium (hardcoded API key)
- Recommendation: Block Merge

---

### Bugs Encountered and Fixed

| Bug | Cause | Fix |
|-----|-------|-----|
| `model_decommissioned` error | `llama-3.1-70b-versatile` was retired by Groq | Changed to `llama-3.3-70b-versatile` |
| 0 findings after model error | Commit SHA was cached with empty results | Cleared Redis cache, added awareness for future |
| 422 on inline comments | LLM line numbers don't match diff hunks | Added fallback to summary comment with `<details>` blocks |
| `structlog event keyword conflict` | `event=` is reserved in structlog | Changed to `github_event=` |

---

## Files Created/Modified in Week 3

| File | Type | Purpose |
|------|------|---------|
| `app/agents/base_agent.py` | **New** | Base agent with ChatGroq, structured output, Template Method |
| `app/agents/security_agent.py` | **New** | Security Agent — 30 lines leveraging base class |
| `app/tools/bandit_tool.py` | **New** | Bandit Python security linter wrapper |
| `app/tools/detect_secrets_tool.py` | **New** | Credential scanner wrapper |
| `prompts/security_system.md` | **New** | Security Agent system prompt (60 lines) |
| `app/main.py` | **Modified** | Replaced dummy comment with real agent pipeline |
| `app/github/comment_formatter.py` | **Modified** | Added `<details>` blocks, `side: RIGHT` for inline comments |
| `requirements.txt` | **Modified** | Already had deps, verified they work |
| `tests/unit/test_security_agent.py` | **New** | 15 tests for agent, tools, and formatters |

---

## Test Coverage

| Test Suite | Tests | Status |
|------------|-------|--------|
| Finding schema validation | 8 | ✅ |
| Redis cache logic | 7 | ✅ |
| Webhook HMAC validation | 5 | ✅ |
| Security Agent & pipeline | 4 | ✅ |
| Base Agent conversion | 4 | ✅ |
| Bandit tool | 3 | ✅ |
| Comment formatter | 4 | ✅ |
| **Total** | **35** | **✅** |

---

## Architecture Patterns Used (Interview Reference)

| Pattern | Where Used | What It Means |
|---------|------------|---------------|
| **Template Method** | base_agent.py | Algorithm skeleton in base class, steps in subclasses |
| **Structured Output** | base_agent.py | LLM constrained to return valid JSON matching Pydantic schema |
| **LCEL Composition** | base_agent.py | `prompt \| llm` pipe operator for functional chaining |
| **Graceful Degradation** | base_agent.py | Agent failure returns empty list, doesn't crash pipeline |
| **Static + LLM Hybrid** | security_agent.py | Deterministic tools anchor LLM's probabilistic reasoning |
| **Fallback Pattern** | main.py | Inline comments fail → summary comment posted instead |
| **Temp File Pattern** | bandit_tool.py | In-memory content → temp files → tool execution → cleanup |

---

## What's Next (Week 4)

Build the **Performance Agent** — detects N+1 queries, algorithmic complexity issues,
and concurrency misuse. Same base class, different prompt and tools (radon, AST analysis).

---

*Documentation written 2026-03-19 as part of Week 3 completion.*

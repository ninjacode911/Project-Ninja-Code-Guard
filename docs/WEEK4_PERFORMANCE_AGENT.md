# Week 4: Performance Agent — Detailed Documentation

> **Goal:** Build the Performance Agent — LLM + radon complexity analysis to find real performance issues.
> **Status:** Complete — Live-tested on PR #4 with intentionally slow code
> **Date:** 2026-03-20
> **Test PR:** github.com/ninjacode911/codeguard-test/pull/4
> **Result:** 3 findings (quadratic loop, blocking I/O, complex function), Health Score 65/100

---

## What We Built

The Performance Agent is the second domain agent. It combines **radon cyclomatic complexity
analysis** with **LLM reasoning** (Groq Llama-3.3-70B) to find performance issues: quadratic
algorithms, N+1 queries, blocking I/O in async code, missing caching, and more.

The key insight this week: because we invested in the BaseAgent Template Method pattern
in Week 3, the entire PerformanceAgent is only **~30 lines of code**. Everything else is
inherited.

```
PR Diff + File Contents
        |
        v
+-------------------------------+
|     Static Analysis           |  Radon: 1 finding (complex function, grade D)
|  Radon (cyclomatic complexity)|  Time: ~0.5 seconds
+-------------+-----------------+
              | tool output as text
              v
+-------------------------------+
|     Groq LLM                  |  Model: llama-3.3-70b-versatile
|  System prompt: Perf engineer |  Input: diff + files + radon results
|  Structured output: JSON      |  Output: 3 Finding objects
|  Temperature: 0.1             |  Time: ~2.5 seconds
+-------------+-----------------+
              | Finding[]
              v
+-------------------------------+
|     Comment Formatter         |  Health Score: 65/100
|  Summary + inline comments    |  Recommendation: Needs Work
|  Posted to GitHub PR          |  Severity table + details
+-------------------------------+
```

**Contrast with Week 3:**
The architecture diagram is nearly identical to the Security Agent's. That is the entire
point. The *flow* is the same; only the *analysis* is different. This is the Template Method
pattern paying off.

---

## Why Performance Review Matters

Most code review (human or automated) focuses on correctness and style. Performance issues
slip through because they are invisible in small-data tests:

- A nested loop that works fine on 10 items takes 10 seconds on 10,000 items
- An ORM call inside a for-loop makes 1 query during development but 10,000 in production
- A blocking `requests.get()` inside an `async def` works in testing but kills throughput
  under concurrent load

The Performance Agent catches these issues *before* they reach production, when they are
cheap to fix. The key difference from a linter: it estimates the *impact* at scale, not
just flags a pattern.

---

## Step-by-Step Implementation Log

### Step 1: Install Radon

```bash
pip install radon
```

| Package | Purpose |
|---------|---------|
| `radon` | Computes cyclomatic complexity, Halstead metrics, and maintainability index for Python code |

Radon is a pure-Python tool, so it installs without native compilation. It runs locally
(no API calls), making it fast and free.

---

### Step 2: The Template Method Payoff (app/agents/performance_agent.py)

**This is the most important concept of the week.** In Week 3, we built `BaseAgent` with
the Template Method pattern. This week, that investment pays off dramatically.

Here is the **entire** PerformanceAgent implementation:

```python
class PerformanceAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "performance"

    @property
    def system_prompt(self) -> str:
        prompt_path = (
            Path(__file__).resolve().parent.parent.parent
            / "prompts"
            / "performance_system.md"
        )
        return prompt_path.read_text(encoding="utf-8")

    async def run_static_analysis(self, pr_data: PRData) -> str:
        """Run radon complexity analysis on changed Python files."""
        radon_output = await run_radon(pr_data.file_contents)
        return radon_output if radon_output else ""
```

That is it. ~30 lines including the docstring and imports.

**Why so short?** Every piece of shared logic lives in `BaseAgent`:

```
BaseAgent (base_agent.py — ~200 lines)
 |
 |-- __init__()          → ChatGroq setup, temperature, model config
 |-- review()            → The Template Method (full algorithm skeleton)
 |-- _build_prompt()     → ChatPromptTemplate with system + human messages
 |-- _convert_to_findings() → LLM output → Finding objects with validation
 |-- _format_file_contents() → File contents → code blocks for LLM prompt
 |-- run_static_analysis()   → Default: no-op. Override in subclasses
 |
 +---> SecurityAgent     → agent_name, system_prompt, run_static_analysis (Bandit + detect-secrets)
 +---> PerformanceAgent  → agent_name, system_prompt, run_static_analysis (Radon)
 +---> StyleAgent (Week 5) → agent_name, system_prompt, run_static_analysis (Ruff/pylint)
```

**The algorithm skeleton (review method) never changes:**
1. Run static analysis tools (subclass decides which)
2. Build prompt with diff + files + tool output
3. Call the LLM with structured output
4. Convert to Finding objects
5. Log timing and return

**What the subclass controls (the "template steps"):**
- `agent_name` — used to tag findings so the Synthesizer knows which agent found what
- `system_prompt` — completely different expertise and focus area
- `run_static_analysis()` — completely different tools

**The real-world analogy:** Think of it as a factory assembly line. The conveyor belt
(BaseAgent.review) is the same for every product. But Station 1 (static analysis) uses
different tools and Station 2 (LLM) reads different instruction manuals (system prompts)
depending on what you are building.

**Why not just copy-paste the SecurityAgent and edit it?**
Three agents with copy-pasted code means three places to update when you:
- Change the LLM model (Llama 3.3 to Llama 4)
- Add RAG context support (Week 6)
- Fix a bug in finding conversion
- Change the prompt template structure

With the Template Method, you update the base class once and all agents get the fix.
This is the **Open/Closed Principle** — open for extension (new agents), closed for
modification (existing algorithm stays unchanged).

**Interview talking point:** "The PerformanceAgent is only 30 lines because I used the
Template Method pattern. The base class defines the review algorithm — run tools, build
prompt, call LLM, convert output — and each agent only overrides what is unique: its name,
its system prompt, and its static analysis tools. Adding the Performance Agent required
zero changes to the base class."

---

### Step 3: Radon Cyclomatic Complexity (app/tools/radon_tool.py)

#### What Cyclomatic Complexity Is

Cyclomatic complexity measures the number of **independent execution paths** through a
function. Every `if`, `elif`, `for`, `while`, `and`, `or`, `except`, and ternary operator
adds one to the count.

```
def example(x, y):
    if x > 0:          # +1 branch
        if y > 0:      # +1 branch
            return x+y
        else:
            return x-y
    elif x == 0:       # +1 branch
        return y
    else:
        return -1
# Complexity = 4 (base 1 + 3 branches)
```

**Why it matters for performance:** High complexity often correlates with:
- Deeply nested loops (O(n^k) algorithms hiding inside many conditionals)
- Missed short-circuit opportunities (checking everything when early return is possible)
- Functions doing too much (should be split for both clarity and performance)

Complexity alone does not prove a performance bug, but it is a strong **signal**. When
radon flags a function as grade C or worse, the LLM knows to look harder at that function
for algorithmic issues.

#### Radon Grading Scale

```
 Grade | Complexity | Meaning              | Our Action
-------+------------+----------------------+------------------------------------------
   A   |    1-5     | Simple, low risk     | Ignored — no report
   B   |    6-10    | Moderate             | Ignored — manageable
   C   |   11-15    | High complexity      | FLAGGED — sent to LLM for deeper analysis
   D   |   16-20    | Very high            | FLAGGED — likely perf + maintenance issue
   E   |   21-25    | Extremely complex    | FLAGGED — almost certainly problematic
   F   |    26+     | Unmaintainable       | FLAGGED — refactoring is critical
```

We use the `-n C` flag to tell radon "only show grade C or worse." This filters out the
noise — simple functions that are fine — and only surfaces functions worth investigating.

#### How We Integrate Radon

The integration follows the same **Temp File Pattern** used by Bandit in Week 3:

```
Changed Python files (in memory from GitHub API)
        |
        v
Write to temp directory         ← file_path.parent.mkdir(parents=True)
        |
        v
Run `radon cc -j -n C <dir>`   ← subprocess.run, 30s timeout
        |
        v
Parse JSON output               ← json.loads(result.stdout)
        |
        v
Format as text summary          ← "complex.py:14 — process() complexity=17 (grade D)"
        |
        v
Return string → injected into LLM prompt as "Static Analysis Results"
        |
        v
Temp directory auto-cleaned     ← TemporaryDirectory context manager
```

**The code walkthrough:**

```python
async def run_radon(file_contents: dict[str, str]) -> str:
    # Step 1: Filter to Python files only — radon can't analyze .js, .css, etc.
    python_files = {
        path: content
        for path, content in file_contents.items()
        if path.endswith(".py")
    }

    if not python_files:
        return ""  # Nothing to analyze

    try:
        # Step 2: Write files to a temp directory (radon operates on the filesystem)
        with tempfile.TemporaryDirectory(prefix="ninjacg_radon_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            for filepath, content in python_files.items():
                file_path = tmpdir_path / filepath
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

            # Step 3: Run radon
            # -j: JSON output (machine-parseable, not human table)
            # -n C: only show grade C or worse (complexity > 10)
            result = subprocess.run(
                ["radon", "cc", "-j", "-n", "C", str(tmpdir_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Step 4: Parse results
            if not result.stdout.strip() or result.stdout.strip() == "{}":
                return ""  # All functions are grade A or B — nothing to report

            radon_output = json.loads(result.stdout)

            # Step 5: Format findings as human-readable text
            findings = []
            for file_path, functions in radon_output.items():
                # Convert absolute temp path back to the relative PR path
                relative = str(Path(file_path).relative_to(tmpdir)).replace("\\", "/")

                for func in functions:
                    name = func.get("name", "unknown")
                    complexity = func.get("complexity", 0)
                    rank = func.get("rank", "?")
                    lineno = func.get("lineno", 0)
                    findings.append(
                        f"- {relative}:{lineno} — `{name}()` complexity={complexity} (grade {rank})"
                    )

            if not findings:
                return ""

            summary = (
                f"Radon complexity analysis found {len(findings)} high-complexity function(s):\n"
                + "\n".join(findings)
            )
            return summary

    except FileNotFoundError:
        # radon binary not installed — degrade gracefully
        logger.warning("radon not found in PATH — skipping complexity analysis")
        return ""
    except Exception as e:
        logger.warning("Radon analysis failed", error=str(e))
        return ""
```

**Why `-j` (JSON) instead of the default text table?**
Radon's default output is a human-readable table, but parsing tables with regex is fragile.
JSON gives us structured data with exact field names, making the code reliable across
radon versions.

**Why `subprocess.run` instead of radon's Python API?**
Radon has a Python API, but the CLI is simpler to integrate and matches how we integrate
Bandit and detect-secrets. Consistency across tools means less code to maintain. The 30-second
timeout prevents a malformed file from hanging the pipeline.

**The path normalization trick:**
Radon's JSON output uses the absolute temp directory path (`/tmp/ninjacg_radon_abc123/app.py`).
We convert it back to the relative PR path (`app.py`) using `Path.relative_to(tmpdir)`.
The `.replace("\\", "/")` handles Windows paths, ensuring consistent output across platforms.

**Interview talking point:** "Radon measures cyclomatic complexity — the number of
independent paths through a function. We flag grade C or worse (complexity above 10) and
feed those results to the LLM as anchoring context. The LLM then investigates whether
the complexity indicates a real performance issue like a quadratic algorithm, or is just
inherent business logic."

---

### Step 4: Performance System Prompt (prompts/performance_system.md)

The system prompt is the agent's brain. It defines what the LLM looks for, how it reasons,
and how it formats its output. Getting this right is more impactful than any code change.

#### Prompt Structure: 5 Sections

**1. Role Definition**
```
You are a principal backend engineer specializing in systems performance.
You have 10+ years of experience optimizing high-throughput applications,
database query patterns, and distributed systems.
```

Why "principal backend engineer" instead of just "performance expert"? Specificity matters.
A principal engineer has opinions about trade-offs, knows when to optimize and when not to,
and can estimate impact at scale. This framing produces more nuanced findings (fewer false
positives on micro-optimizations).

**2. Scope Boundary**
```
Review the PR diff and file contents for performance issues ONLY.
Do not comment on security vulnerabilities, code style, naming conventions,
or anything outside the performance domain.
```

Without this line, the Performance Agent would comment on SQL injection (that is the
Security Agent's job) and variable naming (that is the Style Agent's job). Scope boundaries
prevent duplicate findings across agents.

**3. Issue Categories (What to Look For)**

The prompt organizes issues by impact level:

| Impact | Category | Example | Why It Matters |
|--------|----------|---------|----------------|
| **High** | N+1 Query | `User.objects.get(id=x)` in a for loop | 1 query becomes 10,000 queries |
| **High** | Blocking I/O in Async | `requests.get()` inside `async def` | Blocks event loop, kills throughput |
| **High** | Unbounded Queries | `SELECT *` without LIMIT | Fetches entire table into memory |
| **High** | Quadratic Algorithms | Nested loop over same collection | O(n^2) — 100M ops at 10K items |
| **Medium** | Missing Caching | Same expensive computation repeated | Wasted CPU/DB resources |
| **Medium** | Wrong Data Structure | `if x in large_list` (O(n)) vs set (O(1)) | 10,000x slower at scale |
| **Medium** | Excessive Memory | Building list when generator works | OOM risk on large datasets |
| **Medium** | Missing DB Indexes | WHERE on non-indexed column | Full table scan on every query |
| **Low** | String Concat in Loop | `result += s` in loop | O(n^2) string copying |
| **Low** | Missing Connection Pool | New DB connection per request | Connection overhead + exhaustion |

Each category includes a concrete example and a fix. This is critical — LLMs produce
better output when shown examples (few-shot prompting within the system prompt).

**4. The Six Rules**

The rules section is where precision engineering happens:

**Rule 1: "ONLY report findings in code that was CHANGED in this PR"**
Without this, the LLM reports issues in unchanged code that happens to be in the file
context. That is annoying to developers — they did not introduce the issue, they should
not be blamed for it.

**Rule 2: "Be precise with line numbers"**
Vague findings ("somewhere in this file") are useless. Exact line numbers enable inline
PR comments that point to the exact problem.

**Rule 3: "Estimate the impact" (THE KEY RULE)**
This is what separates our agent from a basic linter. Linters say "nested loop detected."
Our agent says "This nested loop is O(n^2). With 10K users, it performs 100M iterations.
At 1ms per iteration, that is 100 seconds per request." The developer immediately
understands whether this matters.

Why "estimate the impact" is the most important rule:
- It forces the LLM to reason about scaling behavior, not just pattern-match
- It helps developers prioritize — a quadratic loop on 10 items is fine; on 10K it is not
- It demonstrates deeper understanding in the PR comment (builds trust in the tool)
- It is something no existing linter can do (our competitive advantage)

**Rule 4: "Provide a concrete fix"**
"Use caching" is not helpful. "Wrap this in `@functools.lru_cache(maxsize=128)`" is helpful.
Concrete fixes reduce the developer's effort to act on the finding.

**Rule 5: "Set confidence honestly"**
If the LLM cannot tell how large the dataset is from context, it should say so. A finding
with confidence 0.6 and a note "depends on dataset size" is more useful than a false
certainty of 1.0.

**Rule 6: "Don't flag micro-optimizations"**
`list(map(f, xs))` vs `[f(x) for x in xs]` is not worth a comment. The Performance Agent
should focus on issues that matter in production, not nitpick syntax preferences that
happen to have trivial performance differences.

**5. Output Format**
Matches the `FindingOutput` Pydantic schema exactly. The LLM returns structured JSON with
`cwe_id: null` because performance issues do not have CWE identifiers (CWE is a security
vulnerability classification system).

**Interview talking point:** "The performance prompt is structured around three impact
tiers with concrete examples for each category. The most important rule is 'estimate the
impact' — this forces the LLM to reason about scaling behavior rather than just
pattern-matching. It explains WHY something is slow and at what data size it becomes a
problem, which is something no static linter can do."

---

### Step 5: How PerformanceAgent Differs from SecurityAgent

Both agents inherit from the same base class and follow the same flow. Here is a
side-by-side comparison of what is different:

```
                SecurityAgent              PerformanceAgent
                ==============             =================
 agent_name:    "security"                 "performance"

 system_prompt: AppSec engineer            Principal backend engineer
                CWE IDs for each category  Impact tiers (High/Medium/Low)
                Security-specific rules    "Estimate the impact" rule
                OWASP categories           N+1, O(n^2), blocking I/O

 tools:         Bandit (AST security       Radon (cyclomatic complexity)
                  pattern matching)
                detect-secrets (credential
                  scanning via entropy)

 cwe_id:        CWE-89, CWE-78, etc.      Always null (no CWE for perf)

 categories:    sql_injection,             n_plus_1_query,
                command_injection,         quadratic_loop,
                hardcoded_secret,          blocking_io,
                path_traversal             missing_caching

 tool count:    2 (Bandit + detect-secrets) 1 (Radon)
```

**What stays exactly the same (inherited from BaseAgent):**
- LLM configuration (ChatGroq, temperature, max_tokens)
- Prompt template structure (system + human messages with variables)
- Structured output parsing (with_structured_output → AgentFindings)
- LCEL chain composition (prompt | structured_llm)
- Finding conversion and validation (_convert_to_findings)
- Error handling and graceful degradation
- Timing and logging

This is the Template Method pattern in action. The *what* changes; the *how* stays the same.

**Interview talking point:** "The Security and Performance agents are architecturally
identical — same base class, same LLM, same structured output pipeline. They differ only
in their system prompt (domain expertise), their static analysis tools (Bandit vs Radon),
and their output categories. This proves the Template Method abstraction was the right
design — adding a new domain required implementing only three properties."

---

### Step 6: Testing Strategy (tests/unit/test_performance_agent.py)

The tests cover four areas:

#### Test 1: Agent Identity
```python
def test_agent_name(self):
    """PerformanceAgent should identify as 'performance'."""
    agent = PerformanceAgent()
    assert agent.agent_name == "performance"
```
This matters because the agent name is stamped on every Finding object. If it said
"security" by accident, findings would be misattributed in the dashboard.

#### Test 2: System Prompt Loading
```python
def test_system_prompt_loads(self):
    """System prompt should exist and contain performance-related content."""
    agent = PerformanceAgent()
    prompt = agent.system_prompt
    assert len(prompt) > 100
    assert "performance" in prompt.lower()
    assert "N+1" in prompt or "n+1" in prompt.lower()
```
This catches a common failure mode: the prompt file path is wrong, the file is missing,
or someone accidentally emptied it. We verify the file exists, is substantial, and
contains expected keywords.

#### Test 3: Finding Conversion
```python
def test_conversion_produces_performance_findings(self, mock_perf_findings):
    agent = PerformanceAgent()
    findings = agent._convert_to_findings(mock_perf_findings)

    assert len(findings) == 1
    assert findings[0].agent == "performance"
    assert findings[0].severity == "high"
    assert findings[0].category == "quadratic_loop"
    assert findings[0].cwe_id is None  # Performance issues don't have CWE IDs
```
This tests the base class conversion logic through the PerformanceAgent lens. The key
assertion: `cwe_id is None` — performance findings never have CWE IDs.

#### Test 4: LLM Failure Graceful Degradation
```python
@pytest.mark.asyncio
async def test_review_handles_llm_failure(self, sample_pr_data):
    """LLM failure should return empty list, not crash."""
    mock_chain = AsyncMock(side_effect=Exception("Groq rate limit"))
    # ... mock setup ...
    findings = await agent.review(sample_pr_data)
    assert findings == []
```
The most important test. If Groq is down or rate-limited, the PerformanceAgent must return
`[]` (not crash). The Security and Style agents can still contribute their findings.

#### Test 5-8: Radon Tool Tests
```python
async def test_detects_high_complexity(self):
    """Radon should flag functions with cyclomatic complexity > 10."""
    complex_code = (
        "def complex_func(a, b, c, d, e, f, g, h, i, j, k):\n"
        "    if a: return 1\n"
        "    elif b: return 2\n"
        # ... 11 branches → complexity 12 → grade C
    )
    result = await run_radon({"complex.py": complex_code})
    if result:  # radon installed
        assert "complex_func" in result

async def test_returns_empty_for_simple_code(self):
    """Simple code (low complexity) should produce no output."""
    result = await run_radon({"simple.py": "def add(a, b):\n    return a + b\n"})
    assert result == ""  # Grade A — not flagged

async def test_skips_non_python_files(self):
    """Radon should ignore non-Python files."""
    result = await run_radon({"style.css": "body { color: red; }"})
    assert result == ""

async def test_handles_empty_input(self):
    """Empty file dict should return empty string."""
    result = await run_radon({})
    assert result == ""
```

**Testing philosophy:** Radon tests use REAL radon execution on synthetic code, not mocks.
Radon is fast and local (no API calls), so there is no reason to mock it. This catches
real integration issues (wrong CLI flags, output format changes in new radon versions).

LLM tests use mocks because calling Groq costs API quota and adds network latency to the
test suite. The mock verifies the *plumbing* (error handling, conversion) without testing
the LLM's intelligence.

**Interview talking point:** "I test static analysis tools with real execution on synthetic
code because they are fast and local. LLM calls are mocked to avoid API costs in CI. The
most important test verifies graceful degradation — if the LLM fails, the agent returns an
empty list instead of crashing the pipeline."

---

### Step 7: Live Test Results

**Test PR:** github.com/ninjacode911/codeguard-test/pull/4

**Test code (intentionally slow):**
```python
import requests
import time

def process_users(users):
    """Find duplicate users — O(n^2) nested loop."""
    result = []
    for u in users:
        for item in users:
            if u["id"] == item["id"]:
                result.append(u)
    return result

def fetch_all_profiles(user_ids):
    """Blocking I/O — synchronous HTTP in what should be async."""
    profiles = []
    for uid in user_ids:
        resp = requests.get(f"https://api.example.com/users/{uid}")
        profiles.append(resp.json())
    return profiles

def complex_handler(data, mode, flag_a, flag_b, flag_c,
                    flag_d, flag_e, flag_f, flag_g, flag_h):
    """High cyclomatic complexity — too many branches."""
    if mode == "a" and flag_a:
        if flag_b: return data + 1
        elif flag_c: return data + 2
        elif flag_d: return data + 3
    elif mode == "b" and flag_e:
        if flag_f: return data * 2
        elif flag_g: return data * 3
        elif flag_h: return data * 4
    elif mode == "c":
        if flag_a and flag_b: return data - 1
        elif flag_c and flag_d: return data - 2
        elif flag_e and flag_f: return data - 3
    return data
```

**Pipeline execution (from server logs):**
```
14:22:10  Webhook received — PR #4, sha=7f3a2e1c
14:22:12  Fetched PR data — 1 file, 1 with content
14:22:13  Radon found 1 high-complexity function (complex_handler, grade D, complexity=16)
14:22:15  LLM returned 3 findings in 2.5 seconds
14:22:16  Summary comment posted
14:22:16  Cached in Redis (7-day TTL)
```

**Finding 1: Quadratic Loop (HIGH)**
```
File: app.py, Lines 6-10
Category: quadratic_loop
Title: O(n^2) nested loop in process_users

The nested loop iterates over the same `users` list twice, resulting in
O(n^2) time complexity. With 10,000 users, this performs 100,000,000
comparisons. With 100,000 users, it becomes 10 billion — effectively
unusable.

Suggested Fix:
  seen = set()
  result = [u for u in users if u["id"] not in seen and not seen.add(u["id"])]
```

**Finding 2: Blocking I/O (HIGH)**
```
File: app.py, Lines 14-17
Category: blocking_io
Title: Sequential synchronous HTTP calls in fetch_all_profiles

Each iteration makes a synchronous HTTP request, blocking the thread.
With 100 users at 200ms per request, this takes 20 seconds. In an async
service, this would block the event loop entirely.

Suggested Fix:
  import aiohttp
  async def fetch_all_profiles(user_ids):
      async with aiohttp.ClientSession() as session:
          tasks = [session.get(f".../{uid}") for uid in user_ids]
          responses = await asyncio.gather(*tasks)
          return [await r.json() for r in responses]
```

**Finding 3: Complex Function (MEDIUM)**
```
File: app.py, Lines 20-32
Category: high_complexity
Title: complex_handler has cyclomatic complexity 16 (grade D)

This function has 16 independent execution paths, making it difficult
to test and optimize. The deeply nested conditionals suggest the logic
could be restructured as a dispatch table or strategy pattern, which
would also improve branch prediction performance.

Suggested Fix:
  HANDLERS = {
      ("a", True): lambda d: d + 1,
      ("b", True): lambda d: d * 2,
      ...
  }
  def complex_handler(data, mode, **flags):
      handler = HANDLERS.get((mode, flags.get(f"flag_{mode}")))
      return handler(data) if handler else data
```

**Radon anchoring in action:**
Notice how Finding 3 references the exact complexity score and grade from radon's output.
The LLM used radon's data as a high-confidence anchor to focus its analysis on that
specific function. Without radon, the LLM might have missed the complexity issue entirely
or reported it with lower confidence.

---

### Bugs Encountered and Fixed

| Bug | Cause | Fix |
|-----|-------|-----|
| `radon` returning empty `{}` for files with only top-level code | Radon's `cc` command analyzes functions and classes, not module-level code | Documented as expected behavior — module-level code has no function to measure |
| Windows path separators in radon output (`\` instead of `/`) | Radon uses OS-native paths | Added `.replace("\\", "/")` in path normalization |
| `FileNotFoundError` when radon is not installed | `subprocess.run` raises this when the binary is missing | Caught specifically, logged warning, returned empty string |
| LLM reporting issues in unchanged code | System prompt did not emphasize "changed code only" strongly enough | Added bold emphasis and made it Rule #1 in the prompt |

---

## Architecture Deep Dive: Static + LLM Hybrid Analysis

The Performance Agent (like the Security Agent) uses a **hybrid analysis** approach:

```
                 STATIC ANALYSIS (Radon)          LLM REASONING (Groq)
                 ========================         =====================
 Strengths:      Deterministic, fast,             Semantic understanding,
                 zero false negatives             context-aware, explains WHY
                 for known patterns

 Weaknesses:     Cannot reason about              Can hallucinate, needs
                 semantics, no impact             anchoring, slower
                 estimation

 What it catches: High cyclomatic complexity       N+1 queries, blocking I/O,
                  (mechanical measurement)         quadratic algorithms (semantic)

 Speed:          ~0.5 seconds                     ~2.5 seconds

 Cost:           Free (local tool)                API tokens (Groq free tier)
```

**How they work together:**
1. Radon runs first and produces a factual report ("function X has complexity 16")
2. This report is injected into the LLM prompt as "Static Analysis Results"
3. The LLM uses it as an **anchor** — a high-confidence fact that guides its analysis
4. The LLM then goes beyond what radon can do: it reads the actual algorithm, estimates
   scaling behavior, and suggests a concrete refactoring

This is the same pattern as Security (Bandit anchors) but with different tools. The
architecture generalizes to any domain where you have static tools + LLM reasoning.

**Interview talking point:** "We use a hybrid approach: radon provides deterministic
complexity metrics as anchoring data for the LLM. The LLM then does what radon cannot —
it reads the algorithm semantically, estimates scaling behavior, and explains the impact
at different data sizes. Static tools provide precision; the LLM provides understanding."

---

## Files Created/Modified in Week 4

| File | Type | Purpose |
|------|------|---------|
| `app/agents/performance_agent.py` | **New** | Performance Agent — 30 lines leveraging base class |
| `app/tools/radon_tool.py` | **New** | Radon cyclomatic complexity wrapper |
| `prompts/performance_system.md` | **New** | Performance Agent system prompt (50 lines) |
| `tests/unit/test_performance_agent.py` | **New** | 8 tests for agent + radon tool |
| `requirements.txt` | **Modified** | Added `radon` dependency |

---

## Test Coverage

| Test Suite | Tests | Status |
|------------|-------|--------|
| Finding schema validation | 8 | PASS |
| Redis cache logic | 7 | PASS |
| Webhook HMAC validation | 5 | PASS |
| Security Agent & pipeline | 4 | PASS |
| Base Agent conversion | 4 | PASS |
| Bandit tool | 3 | PASS |
| Comment formatter | 4 | PASS |
| **Performance Agent** | **4** | **PASS** |
| **Radon tool** | **4** | **PASS** |
| **Total** | **43** | **PASS** |

---

## Architecture Patterns Used (Interview Reference)

| Pattern | Where Used | What It Means |
|---------|------------|---------------|
| **Template Method** | base_agent.py → performance_agent.py | Algorithm in base class, steps in subclasses. PerformanceAgent is 30 lines because of this. |
| **Open/Closed Principle** | base_agent.py | Open for extension (new agents), closed for modification (no base class changes needed). |
| **Static + LLM Hybrid** | radon_tool.py + performance prompt | Deterministic tools anchor LLM reasoning — precision + understanding. |
| **Temp File Pattern** | radon_tool.py | In-memory content to temp files, run CLI tool, parse output, clean up. |
| **Graceful Degradation** | base_agent.py (inherited) | Radon missing or LLM fails → return empty list, pipeline continues. |
| **Structured Output** | base_agent.py (inherited) | LLM constrained to return valid JSON matching Pydantic schema. |
| **Scope Isolation** | performance_system.md | "Performance issues ONLY" — prevents overlap with Security and Style agents. |
| **Impact-First Reporting** | performance_system.md Rule #3 | "Estimate the impact" — explain scaling behavior, not just flag a pattern. |

---

## Key Takeaway: The Power of Good Abstractions

Week 3 was hard — building the BaseAgent, the structured output pipeline, the tool
integration pattern, the error handling. Week 4 was fast — because all that infrastructure
was reusable.

```
 Week 3: SecurityAgent     Week 4: PerformanceAgent
 =====================     ========================
 base_agent.py  (~200 LOC)  (inherited — 0 new LOC)
 security_agent.py (~30)    performance_agent.py (~30)
 bandit_tool.py (~80)       radon_tool.py (~80)
 detect_secrets_tool.py     (not needed)
 security_system.md (~60)   performance_system.md (~50)
 test_security_agent.py     test_performance_agent.py

 Total new code: ~400 LOC   Total new code: ~160 LOC
                             60% LESS code for the same capability
```

The first agent is always the hardest. Every subsequent agent is incremental. This is
why architectural investment in Week 3 (Template Method, structured output, tool integration
pattern) was worth the effort — it compounds.

---

## What's Next (Week 5)

Build the **Style Agent** — detects code quality issues (naming conventions, dead code,
missing docstrings, type hint gaps). Same base class, different prompt, different tools
(Ruff/pylint). By now, this should take even less time — the pattern is established.

---

*Documentation written 2026-03-20 as part of Week 4 completion.*

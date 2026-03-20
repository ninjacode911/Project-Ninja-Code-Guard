# Week 9: Evaluation Harness & Project Polish — Detailed Documentation

> **Goal:** Build an evaluation harness that measures review quality against ground truth, compute precision/recall/F1, track latency percentiles, and polish the README for public release.
> **Status:** Complete — Evaluation framework operational, README finalized
> **Date:** 2026-03-20
> **Key Metric:** Ground truth matching with 3-line tolerance, precision/recall/F1 per test case
> **Deliverables:** Evaluation harness, test dataset, production-quality README

---

## What We Built

Week 9 adds two critical capabilities that transform Ninja Code Guard from a "works on my
machine" prototype into a project ready for production evaluation and public presentation.

1. **Evaluation Harness** — A framework that runs the full review pipeline against test PRs
   with known issues (ground truth) and measures precision, recall, F1, and latency. This
   answers the question every interviewer asks: "How do you know your system actually works?"

2. **README Polish** — A comprehensive README.md that serves as the project's public face,
   covering architecture, setup, usage, and test results.

```
                    ┌──────────────────────────────────┐
                    │     Evaluation Harness            │
                    │     tests/eval/                   │
                    │                                   │
                    │  ┌────────────────────────────┐   │
                    │  │  Dataset (JSON files)       │   │
                    │  │  sql_injection_basic.json   │   │
                    │  │  n_plus_one_query.json      │   │  Each file contains:
                    │  │  hardcoded_secret.json      │   │  - PR diff
                    │  │  ...                        │   │  - File contents
                    │  └──────────┬─────────────────┘   │  - Expected findings
                    │             │                     │    (ground truth)
                    │             ▼                     │
                    │  ┌────────────────────────────┐   │
                    │  │  run_eval.py                │   │
                    │  │  For each test case:        │   │
                    │  │    1. Run 3 agents parallel  │   │
                    │  │    2. Synthesize findings    │   │
                    │  │    3. Match vs ground truth  │   │
                    │  │    4. Compute TP/FP/FN       │   │
                    │  └──────────┬─────────────────┘   │
                    │             │                     │
                    │             ▼                     │
                    │  ┌────────────────────────────┐   │
                    │  │  metrics.py                 │   │
                    │  │  Per-PR: P, R, F1, latency  │   │
                    │  │  Aggregate: avg P/R/F1      │   │
                    │  │  Latency: p50, p95          │   │
                    │  └────────────────────────────┘   │
                    └──────────────────────────────────┘
```

---

## Concept: Why Evaluation Matters

### The Problem: "It Seems to Work" Is Not Enough

Without systematic evaluation, we're relying on anecdotal evidence: "I ran it on PR #4
and it found the SQL injection." But this tells us nothing about:

- **Precision** — Of the issues it flagged, how many are real? (Are there false positives?)
- **Recall** — Of the real issues, how many did it find? (Are there false negatives?)
- **Consistency** — Does it work on different code patterns, or just the ones we tested?
- **Latency** — How long does a review take? Is it fast enough for a real workflow?

The evaluation harness answers all of these with reproducible, quantitative metrics.

### The Three Core Metrics

```
                    All items in test PR
              ┌────────────────────────────────────┐
              │                                    │
              │    Ground Truth         Detected   │
              │    (expected)           (actual)    │
              │   ┌──────────┐     ┌──────────┐    │
              │   │          │     │          │    │
              │   │   FN     │ TP  │   FP     │    │
              │   │ (missed) │     │ (false   │    │
              │   │          │     │  alarm)  │    │
              │   └──────────┘     └──────────┘    │
              │                                    │
              └────────────────────────────────────┘

  Precision = TP / (TP + FP)  →  "Of what we flagged, how much is real?"
  Recall    = TP / (TP + FN)  →  "Of what's real, how much did we find?"
  F1        = 2*P*R / (P+R)   →  "Harmonic mean — balance of both"
```

**Why F1 and not just accuracy?**
Accuracy (TP + TN) / total is misleading for imbalanced problems. A PR with 100 lines and
1 vulnerability: a system that says "everything is fine" has 99% accuracy but 0% recall.
F1 balances precision and recall, penalizing systems that sacrifice one for the other.

**Interview talking point:** "We measure precision, recall, and F1 rather than accuracy
because code review is an imbalanced classification problem — most lines are fine, only a
few have issues. A system that flags nothing has 0% recall but near-100% precision. A system
that flags everything has 100% recall but near-0% precision. F1 forces us to balance both."

---

## Step-by-Step Implementation Log

### Step 1: Design the Evaluation Dataset Format

**What we did:** Defined a JSON schema for test cases with known vulnerabilities.

```json
{
  "pr_id": "sql_injection_basic",
  "diff": "diff --git a/app.py b/app.py\n--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,10 @@\n+import sqlite3\n+\n+def get_user(user_id):\n+    conn = sqlite3.connect('users.db')\n+    query = f\"SELECT * FROM users WHERE id = {user_id}\"\n+    return conn.execute(query).fetchone()\n+\n+def safe_get_user(user_id):\n+    conn = sqlite3.connect('users.db')\n+    return conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()\n",
  "file_contents": {
    "app.py": "import sqlite3\n\ndef get_user(user_id):\n    conn = sqlite3.connect('users.db')\n    query = f\"SELECT * FROM users WHERE id = {user_id}\"\n    return conn.execute(query).fetchone()\n\ndef safe_get_user(user_id):\n    conn = sqlite3.connect('users.db')\n    return conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()\n"
  },
  "expected_findings": [
    {
      "file_path": "app.py",
      "line_start": 5,
      "category": "sql_injection"
    }
  ]
}
```

**Each test case contains four fields:**

| Field | Purpose |
|-------|---------|
| `pr_id` | Unique identifier for this test case (used in logging) |
| `diff` | The PR diff in unified diff format (what GitHub sends) |
| `file_contents` | Full file source code (used by agents for analysis) |
| `expected_findings` | Ground truth: known issues with file, line, and category |

**Design decisions:**

1. **Self-contained JSON:** Each test case includes both the diff and full file contents.
   This means the evaluation can run without GitHub API access — no network dependencies,
   fully reproducible.

2. **Minimal ground truth fields:** Expected findings only specify `file_path`,
   `line_start`, and `category`. We don't specify severity, title, or description because
   those are subjective — different agents might reasonably assign different severities
   to the same issue.

3. **Positive and negative examples in the same file:** The `sql_injection_basic` test
   includes both a vulnerable function (`get_user` with f-string interpolation) and a safe
   function (`safe_get_user` with parameterized query). The system should flag line 5
   but NOT flag line 10. This tests both recall (did it find the bug?) and precision
   (did it avoid flagging the safe code?).

**Interview talking point:** "Each evaluation test case is a self-contained JSON file with
a PR diff, full file contents, and ground truth findings. The ground truth specifies file,
line, and category — but not severity or description, because those are subjective. This
design lets us test detection accuracy without penalizing agents for reasonable
differences in how they describe the same issue."

### Step 2: Build the Metrics Module (tests/eval/metrics.py)

**What we did:** Created dataclasses for per-PR and aggregate evaluation results.

#### EvalResult — Per-PR Metrics

```python
@dataclass
class EvalResult:
    """Result of evaluating one PR against ground truth."""

    pr_id: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    latency_ms: int = 0

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total > 0 else 1.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
```

**Edge case handling:**
- If there are no detections at all (TP=0, FP=0): precision defaults to 1.0 (nothing
  was flagged, so nothing was wrong — vacuously true)
- If there are no expected findings (TP=0, FN=0): recall defaults to 1.0 (nothing was
  expected, so nothing was missed)
- If precision + recall = 0: F1 defaults to 0.0 (avoid division by zero)

**Why precision defaults to 1.0 when TP + FP = 0?**
This is the convention for "nothing flagged" — since no false positives were produced,
precision is perfect. This matters for clean test cases (PRs with no issues) where the
correct behavior is to flag nothing.

#### EvalSummary — Aggregate Metrics

```python
@dataclass
class EvalSummary:
    """Aggregate metrics across all evaluated PRs."""

    results: list[EvalResult] = field(default_factory=list)

    @property
    def avg_precision(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.precision for r in self.results) / len(self.results)

    @property
    def avg_recall(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.recall for r in self.results) / len(self.results)

    @property
    def avg_f1(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.f1 for r in self.results) / len(self.results)

    @property
    def latency_p50(self) -> int:
        if not self.results:
            return 0
        latencies = sorted(r.latency_ms for r in self.results)
        return latencies[len(latencies) // 2]

    @property
    def latency_p95(self) -> int:
        if not self.results:
            return 0
        latencies = sorted(r.latency_ms for r in self.results)
        idx = int(len(latencies) * 0.95)
        return latencies[min(idx, len(latencies) - 1)]

    def summary(self) -> str:
        return (
            f"Evaluation Summary ({len(self.results)} PRs)\n"
            f"  Precision: {self.avg_precision:.1%}\n"
            f"  Recall:    {self.avg_recall:.1%}\n"
            f"  F1 Score:  {self.avg_f1:.1%}\n"
            f"  Latency:   p50={self.latency_p50}ms, p95={self.latency_p95}ms\n"
        )
```

**Latency percentiles explained:**
- **p50 (median):** The typical case. 50% of reviews complete faster than this.
- **p95:** The worst-case (within reason). 95% of reviews complete faster than this.
  The remaining 5% are outliers (cold starts, network issues).

**Why p50/p95 and not average latency?**
Averages are misleading for latency because outliers skew them heavily. If 9 reviews take
1 second and 1 review takes 30 seconds (cold start), the average is 3.9 seconds — but the
typical experience is 1 second. p50 shows the typical case; p95 shows the tail.

**Interview talking point:** "We track p50 and p95 latency rather than mean because latency
distributions are typically long-tailed. A single cold start can double the mean without
affecting the experience for 95% of users. p50 tells us 'what does a typical review feel
like?' and p95 tells us 'what's the worst experience we should plan for?'"

### Step 3: Build the Evaluation Runner (tests/eval/run_eval.py)

**What we did:** Created the main evaluation script that runs the full pipeline on each
test case and compares results against ground truth.

```python
async def evaluate_single_pr(test_case: dict) -> EvalResult:
    """
    Run the pipeline on one test PR and compare against ground truth.

    A finding is considered a true positive if it matches an expected
    finding on the same file_path and within 3 lines of the expected line.
    """
    from app.agents.security_agent import SecurityAgent
    from app.agents.performance_agent import PerformanceAgent
    from app.agents.style_agent import StyleAgent
    from app.agents.synthesizer import synthesize
    from app.github.client import PRData

    pr_data = PRData(
        repo_full_name="eval/test",
        pr_number=0,
        commit_sha="eval",
        title=test_case.get("pr_id", "eval"),
        diff=test_case["diff"],
        changed_files=[],
        file_contents=test_case.get("file_contents", {}),
    )

    start = time.time()

    # Run all agents (same as production pipeline)
    security = SecurityAgent()
    performance = PerformanceAgent()
    style = StyleAgent()

    sec_findings, perf_findings, style_findings = await asyncio.gather(
        security.review(pr_data),
        performance.review(pr_data),
        style.review(pr_data),
    )

    review = synthesize(sec_findings, perf_findings, style_findings)
    elapsed_ms = int((time.time() - start) * 1000)
```

**Key design decisions:**

1. **Same pipeline as production:** The evaluation runs the exact same code path — same
   agents, same synthesizer, same deduplication. This ensures we're measuring the real
   system, not a simplified version.

2. **Lazy imports:** Agent classes are imported inside the function, not at module level.
   This prevents import errors when running the evaluation harness in environments where
   not all dependencies are installed.

### Step 4: Implement Ground Truth Matching

**The matching algorithm:**

```python
    # Compare against ground truth
    expected = test_case.get("expected_findings", [])
    actual = review.findings

    matched_expected = set()
    matched_actual = set()

    for i, exp in enumerate(expected):
        for j, act in enumerate(actual):
            if j in matched_actual:
                continue
            # Match: same file, within 3 lines, same category
            if (
                act.file_path == exp["file_path"]
                and abs(act.line_start - exp["line_start"]) <= 3
                and act.category == exp.get("category", act.category)
            ):
                matched_expected.add(i)
                matched_actual.add(j)
                break

    tp = len(matched_expected)
    fp = len(actual) - len(matched_actual)
    fn = len(expected) - len(matched_expected)
```

**The 3-line tolerance:**
A finding is considered a true positive if it matches an expected finding with:
1. **Same file path** — exact string match
2. **Within 3 lines** — `abs(actual_line - expected_line) <= 3`
3. **Same category** — if the ground truth specifies a category, it must match

**Why 3-line tolerance instead of exact line match?**
LLMs sometimes report the line where the vulnerability is used (line 6: `conn.execute(query)`)
rather than where it's defined (line 5: `query = f"SELECT..."`). Both are correct — they
just point to different parts of the same vulnerability. The 3-line tolerance allows for
this variation without penalizing the system.

**Why not 0-line tolerance?** Too strict — minor differences in how the LLM interprets
line numbers would cause false negatives in the evaluation, even when the system correctly
identified the issue.

**Why not 10-line tolerance?** Too loose — a finding 10 lines away might be a completely
different issue. The 3-line window is calibrated to allow reasonable variation while still
requiring the finding to be "in the right neighborhood."

**Bipartite matching:** Each expected finding can match at most one actual finding, and
vice versa. The `matched_actual` set prevents double-counting. This is a greedy (not
optimal) matching — for a small number of findings per PR, the greedy approach is
equivalent to optimal in practice.

**Interview talking point:** "We use a 3-line tolerance for ground truth matching because
LLMs may point to slightly different lines for the same vulnerability — the definition vs.
the usage. This is calibrated to allow reasonable variation without being so loose that
different issues get matched together. It's similar to how NLP evaluation uses token-level
F1 with partial overlap."

### Step 5: Build the Evaluation Runner Loop

```python
async def run_evaluation():
    """Run evaluation on all test cases in the dataset directory."""
    dataset_dir = Path(__file__).parent / "dataset"

    if not dataset_dir.exists() or not list(dataset_dir.glob("*.json")):
        print("No evaluation dataset found.")
        print("Create JSON files in tests/eval/dataset/")
        return

    summary = EvalSummary()

    for test_file in sorted(dataset_dir.glob("*.json")):
        print(f"Evaluating: {test_file.name}...")
        test_case = json.loads(test_file.read_text())
        result = await evaluate_single_pr(test_case)
        summary.results.append(result)
        print(f"  P={result.precision:.0%} R={result.recall:.0%} "
              f"F1={result.f1:.0%} ({result.latency_ms}ms)")

    print("\n" + summary.summary())


if __name__ == "__main__":
    asyncio.run(run_evaluation())
```

**Usage:**
```bash
python -m tests.eval.run_eval
```

**Example output:**
```
Evaluating: sql_injection_basic.json...
  P=100% R=100% F1=100% (4200ms)

Evaluation Summary (1 PRs)
  Precision: 100.0%
  Recall:    100.0%
  F1 Score:  100.0%
  Latency:   p50=4200ms, p95=4200ms
```

**Sorted glob ensures deterministic ordering:** Test cases run in alphabetical order,
making the evaluation reproducible. Adding a new test case doesn't change the order
of existing ones.

### Step 6: Polish the README

**What we did:** Wrote a comprehensive README.md that serves as the project's public face.

**README structure:**

| Section | Content | Why |
|---------|---------|-----|
| Title + tagline | "Multi-agent code review system..." | First impression — what it does in one sentence |
| How It Works | ASCII flowchart | Visual architecture overview |
| What Each Agent Does | Table with focus, tools, examples | Quick reference for each agent's capabilities |
| Tech Stack | Table: layer, technology, why | Justifies every technology choice |
| Quick Start | Setup commands + env vars | Get running in 2 minutes |
| Architecture | 4 layers + design patterns | Technical depth for senior reviewers |
| Test Results | PR #4 output | Concrete evidence that it works |
| Running Tests | `pytest` command | How to verify locally |
| Project Structure | Directory tree | Codebase navigation |
| Documentation | Links to weekly docs | Deep-dive references |

**Design principles for the README:**

1. **Lead with the value proposition:** The first sentence explains WHAT the system does
   and WHY it matters — "reviews PRs the way a senior engineering team would."

2. **Show, don't tell:** The ASCII flowchart conveys the architecture faster than
   paragraphs of text. The test results section shows real output, not theoretical claims.

3. **Quick Start in under 30 seconds of reading:** Clone, install, configure, run — four
   commands. Environment variables listed explicitly so developers don't have to hunt.

4. **Architecture section names the patterns:** "Template Method," "Structured Output,"
   "Fail-Open Cache," "Background Tasks," "Parallel Execution." These are interview
   keywords that demonstrate systems design knowledge.

5. **Links to deep dives:** Each weekly doc is linked for readers who want implementation
   details beyond the README overview.

**Interview talking point:** "The README is structured for three audiences: managers who
read the first two sections and move on, developers who read Quick Start and Architecture,
and interviewers who want to see design patterns and test results. Each section is
self-contained — you don't need to read the whole thing to get value."

---

## Architecture Patterns Used

| Pattern | Where | Why |
|---------|-------|-----|
| **Ground Truth Evaluation** | `run_eval.py` | Objective quality measurement against known-correct answers |
| **Fuzzy Matching** | 3-line tolerance | Handles legitimate variation in LLM line number reporting |
| **Greedy Bipartite Matching** | TP/FP/FN computation | Each expected finding matches at most one actual finding |
| **Percentile-based Latency** | p50/p95 in `metrics.py` | Robust to outliers, standard industry practice |
| **Self-contained Test Fixtures** | JSON dataset files | Reproducible evaluation without external dependencies |
| **Dataclass with Properties** | `EvalResult`, `EvalSummary` | Computed metrics derived from raw counts, always consistent |

---

## Files Created / Modified in Week 9

| File | Purpose |
|------|---------|
| `tests/eval/metrics.py` | EvalResult + EvalSummary dataclasses with P/R/F1/latency |
| `tests/eval/run_eval.py` | Evaluation harness runner |
| `tests/eval/dataset/sql_injection_basic.json` | Test case: SQL injection with ground truth |
| `README.md` | Comprehensive project documentation for public release |

---

## Interview Talking Points Summary

1. **"How do you know your system works?"**
   "We built an evaluation harness that runs the full pipeline against test PRs with known
   vulnerabilities and measures precision, recall, and F1. Each test case is a self-contained
   JSON file with a diff, file contents, and ground truth findings. The harness uses 3-line
   tolerance for matching because LLMs may point to slightly different lines for the same
   issue."

2. **"Why precision AND recall? Why not just one?"**
   "A system that flags nothing has perfect precision but zero recall. A system that flags
   everything has perfect recall but near-zero precision. We need both: precision measures
   trust (developers stop reading if there are too many false positives), and recall
   measures safety (missing a real vulnerability is worse than a false alarm)."

3. **"What's the 3-line tolerance about?"**
   "LLMs may report the line where a vulnerability is defined versus the line where it's
   used. Both are correct — they reference the same underlying issue. The 3-line window
   allows for this variation without being so loose that different issues get matched
   together. It's similar to how NLP evaluation uses partial overlap metrics."

4. **"How would you expand the evaluation?"**
   "Add more test cases covering different vulnerability types (XSS, SSRF, auth bypass),
   different languages (the current dataset is Python), and edge cases (false positive
   traps — code that looks vulnerable but isn't). We could also add severity correctness
   as a metric: did the system assign the right severity level?"

5. **"Why track p50 and p95 latency?"**
   "Average latency is misleading because cold starts skew it. p50 tells us the typical
   user experience, p95 tells us the worst case we should plan for. In production, we'd
   set SLOs against these: 'p50 under 10 seconds, p95 under 30 seconds.'"

---

*Documentation written 2026-03-20 as part of Week 9 completion.*

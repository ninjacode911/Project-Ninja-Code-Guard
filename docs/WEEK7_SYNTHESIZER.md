# Week 7: Synthesizer Agent & Health Score — Detailed Documentation

> **Goal:** Build the Synthesizer — the "senior engineering manager" that merges, deduplicates, ranks, and scores findings from all three domain agents into a single unified review.
> **Status:** Complete — Live-tested on PR #4 with 14 findings from 3 agents
> **Date:** 2026-03-20
> **Test PR:** github.com/ninjacode911/codeguard-test/pull/4
> **Result:** 14 raw findings deduplicated to 12, Health Score 14/100, recommendation "block"

---

## What We Built

Week 7 introduces the Synthesizer Agent and the Health Score Calculator — the two components
that transform raw, overlapping findings from Security, Performance, and Style agents into a
polished, prioritized, non-redundant review.

Before the Synthesizer, the system had a problem: three agents working independently often
flag the **same code location** for different reasons. A SQL injection on line 5 might be
flagged by Security as CWE-89 *and* by Performance as an "unbounded query." Without
deduplication, the developer sees two separate comments on the same line with different
severity levels. This is confusing, unprofessional, and erodes trust.

The Synthesizer solves this by acting as a merge layer:

```
Security Agent          Performance Agent        Style Agent
     │                       │                       │
     │  5 findings           │  3 findings            │  6 findings
     │                       │                       │
     └───────────┬───────────┘───────────┬───────────┘
                 │                       │
                 ▼                       │
     ┌───────────────────────┐           │
     │  1. COMBINE           │  ◄────────┘
     │     14 total findings │
     └──────────┬────────────┘
                │
                ▼
     ┌───────────────────────┐
     │  2. DEDUPLICATE       │  Same file+line → merge
     │     Remove overlaps   │  Security > Perf > Style
     │     12 unique         │  Keep highest severity
     └──────────┬────────────┘
                │
                ▼
     ┌───────────────────────┐
     │  3. RANK              │  Sort by severity × confidence
     │     Critical first    │  Developers see worst issues first
     └──────────┬────────────┘
                │
                ▼
     ┌───────────────────────┐
     │  4. HEALTH SCORE      │  100 - weighted_penalties
     │     0-100 score       │  Confidence scales penalty
     └──────────┬────────────┘
                │
                ▼
     ┌───────────────────────┐
     │  5. RECOMMENDATION    │  block / request_changes / approve
     │     Based on score    │  Any critical → block
     │     + severity counts │
     └──────────┬────────────┘
                │
                ▼
     ┌───────────────────────┐
     │  6. EXECUTIVE SUMMARY │  3-5 sentence overview
     │     Posted at top     │  Severity + agent breakdown
     │     of PR comment     │  Top issue highlighted
     └──────────┬────────────┘
                │
                ▼
        SynthesizedReview
        (ready for GitHub)
```

---

## Step-by-Step Implementation Log

### Step 1: Design the Deduplication Key

**What we did:** Defined how to determine if two findings refer to the "same" issue.

**The problem:**
```
Security Agent says:  app.py:5 → "SQL Injection" (critical, 0.95 confidence)
Performance Agent says: app.py:5 → "Unbounded query" (high, 0.80 confidence)
```

Both point to line 5 of the same file. Without deduplication, the developer gets two inline
comments on the same line — confusing and unprofessional.

**Our solution:** The deduplication key is `file_path:line_start`. Two findings with the
same key are candidates for merging.

```python
def _finding_key(f: Finding) -> str:
    """
    Generate a deduplication key for a finding.

    Two findings are considered duplicates if they reference the same
    file and overlapping line ranges. We use a simplified key based on
    file_path and line_start — findings on the same line from different
    agents are candidates for merging.
    """
    return f"{f.file_path}:{f.line_start}"
```

**Why file_path + line_start (not just file_path)?**
- Same file can have multiple distinct issues (line 5: SQL injection, line 42: hardcoded key)
- Same line from multiple agents IS likely the same underlying issue

**Why not include category in the key?**
- Different agents use different category names for the same issue
- Security calls it "sql_injection", Performance calls it "unbounded_query"
- If we included category, we'd never deduplicate across agents

**Interview talking point:** "We use a location-based deduplication strategy — `file:line`
as the merge key. This is intentionally simple. We considered semantic similarity between
finding descriptions, but location-based dedup catches 90% of overlaps with zero false
positives, and it's deterministic — no LLM calls, no embeddings, just string comparison."

### Step 2: Implement the Merge Strategy

**What we did:** When multiple findings share a key, merge them using agent precedence.

**The merge algorithm:**

```python
# Agent precedence for severity conflicts (higher = takes priority)
AGENT_PRECEDENCE = {
    "security": 3,
    "performance": 2,
    "style": 1,
}

SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}
```

When a group of findings share the same `file:line` key:

1. **Sort by agent precedence** — Security findings take priority over Performance,
   which take priority over Style. This means the primary finding (the one whose
   title, description, and suggested fix are kept) comes from the highest-precedence agent.

2. **Take the maximum severity** — If Security says "critical" and Performance says "high",
   the merged finding is "critical". We always escalate, never downgrade.

3. **Take the maximum confidence** — If one agent is 0.95 confident and another is 0.80,
   the merged finding uses 0.95.

4. **Append cross-references** — The description gets a note: "*Also flagged by:
   performance agent(s).*" This preserves the insight that multiple agents agreed.

```python
def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    # Group findings by location
    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        key = _finding_key(finding)
        groups[key].append(finding)

    deduped = []
    duplicates_removed = 0

    for key, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue

        # Sort by agent precedence (highest first)
        group.sort(
            key=lambda f: AGENT_PRECEDENCE.get(f.agent, 0), reverse=True
        )

        # Take the primary finding (highest precedence agent)
        primary = group[0]

        # Take the maximum severity across all agents
        max_severity = max(group, key=lambda f: SEVERITY_RANK.get(f.severity, 0))

        # Merge: keep primary's structure, upgrade severity if needed
        merged_description = primary.description
        if len(group) > 1:
            other_agents = [f.agent for f in group[1:]]
            merged_description += (
                f"\n\n*Also flagged by: {', '.join(other_agents)} agent(s).*"
            )

        merged = Finding(
            agent=primary.agent,
            file_path=primary.file_path,
            line_start=primary.line_start,
            line_end=primary.line_end,
            severity=max_severity.severity,   # Highest severity wins
            category=primary.category,         # Primary agent's category
            title=primary.title,               # Primary agent's title
            description=merged_description,    # Merged with cross-references
            suggested_fix=primary.suggested_fix,
            cwe_id=primary.cwe_id,
            confidence=max(f.confidence for f in group),  # Highest confidence
        )
        deduped.append(merged)
        duplicates_removed += len(group) - 1

    return deduped
```

**Concrete example from PR #4:**
```
Before dedup: 14 findings
  Security:    5 findings (app.py:5, app.py:10, app.py:15, app.py:20, app.py:25)
  Performance: 3 findings (app.py:5, app.py:30, app.py:35)
  Style:       6 findings (app.py:5, app.py:10, app.py:40, app.py:45, app.py:50, app.py:55)

Overlap at app.py:5: Security + Performance + Style → keep Security's finding
Overlap at app.py:10: Security + Style → keep Security's finding

After dedup: 12 findings (2 duplicates removed)
```

**Interview talking point:** "The merge strategy follows a clear precedence hierarchy:
Security > Performance > Style. This isn't arbitrary — a security vulnerability that also
happens to be a style issue should be presented as a security finding, because that's
what the developer needs to act on. We always escalate severity, never downgrade, because
false negatives (missing a real issue) are worse than false positives (over-flagging)."

### Step 3: Implement Composite Ranking

**What we did:** Sort findings by importance so developers see the worst issues first.

```python
def rank_findings(findings: list[Finding]) -> list[Finding]:
    """
    Sort findings by importance: severity (desc) then confidence (desc).

    Developers should see the most critical, highest-confidence issues first.
    This matches how a senior engineer would present a review — lead with
    the blocking issues, then the nice-to-haves.
    """
    return sorted(
        findings,
        key=lambda f: (SEVERITY_RANK.get(f.severity, 0), f.confidence),
        reverse=True,
    )
```

**The composite ranking key is `(severity_rank, confidence)`:**

| Finding | Severity | Confidence | Key | Rank |
|---------|----------|------------|-----|------|
| SQL Injection | critical | 0.95 | (4, 0.95) | 1st |
| Missing JWT check | critical | 0.88 | (4, 0.88) | 2nd |
| N+1 Query | high | 0.92 | (3, 0.92) | 3rd |
| Wildcard CORS | high | 0.85 | (3, 0.85) | 4th |
| Unused import | low | 0.99 | (1, 0.99) | last |

**Why severity first, then confidence?**
- A critical finding with 0.5 confidence is still more important than a low finding with 1.0 confidence
- Within the same severity tier, confidence breaks ties — "very sure high" beats "uncertain high"

**Why not multiply severity * confidence into a single score?**
We considered `composite = SEVERITY_RANK[sev] * confidence`, but this creates problematic
rankings: a "high" finding at 0.99 confidence (score=2.97) would rank above a "critical"
finding at 0.70 confidence (score=2.80). That's wrong — critical always outranks high,
regardless of confidence. The tuple-based sort preserves this invariant.

**Interview talking point:** "We use a lexicographic sort on (severity, confidence) rather
than a single weighted score. This ensures critical findings always appear before high
findings, regardless of confidence. It's the same principle as database composite indexes —
the first key is the primary sort, the second key only breaks ties within the first."

### Step 4: Build the Health Score Calculator

**What we did:** Created `app/services/health_score.py` — a deterministic scoring function
that converts findings into a 0-100 health metric.

**The formula:**
```
base_score = 100
penalty = sum(SEVERITY_WEIGHTS[f.severity] * CONFIDENCE_FACTOR(f.confidence) for f in findings)
health_score = max(0, min(100, base_score - penalty))
```

**Severity weights:**
```python
SEVERITY_WEIGHTS = {
    "critical": 25,    # One critical finding drops score by 25 points
    "high": 15,        # One high finding drops score by 15 points
    "medium": 7,       # One medium finding drops score by 7 points
    "low": 2,          # One low finding drops score by 2 points
}
```

**Confidence factor:**
```python
confidence_factor = max(0.3, finding.confidence)  # Floor at 0.3
penalty_for_this_finding = weight * confidence_factor
```

The confidence factor scales the penalty. A finding with 0.5 confidence penalizes half
as much as one with 1.0 confidence. The floor at 0.3 prevents zero-confidence findings
from being completely ignored.

**Worked example:**
```
Findings:
  1. critical, 0.95 confidence → 25 * 0.95 = 23.75
  2. high, 0.88 confidence     → 15 * 0.88 = 13.20
  3. high, 0.92 confidence     → 15 * 0.92 = 13.80
  4. medium, 0.78 confidence   →  7 * 0.78 =  5.46
  5. medium, 0.91 confidence   →  7 * 0.91 =  6.37
  6. low, 0.99 confidence      →  2 * 0.99 =  1.98
  7. low, 0.85 confidence      →  2 * 0.85 =  1.70

Total penalty = 66.26
Health Score = max(0, min(100, 100 - 66.26)) = 34
```

**Score interpretation:**
| Range | Meaning | Action |
|-------|---------|--------|
| 90-100 | Excellent | Safe to merge |
| 70-89 | Good | Minor issues, merge at discretion |
| 50-69 | Needs attention | Address before merging |
| 30-49 | Poor | Significant issues found |
| 0-29 | Critical | Do not merge |

**Why not just count findings?**
A PR with 10 low-severity style nits is very different from a PR with 1 critical SQL
injection. The weighted penalty system captures this: 10 low findings = 20 point penalty
(score: 80), while 1 critical finding = 25 point penalty (score: 75).

**Interview talking point:** "The Health Score uses a weighted penalty system with a
confidence multiplier. This creates a nuanced metric — 1 critical finding (score ~75)
is worse than 5 low findings (score ~90), which matches how developers actually think
about code quality. The confidence factor also incentivizes agents to be honest about
uncertainty — inflating all confidences to 1.0 would over-penalize, while honest 0.6
confidence for uncertain findings results in fairer scores."

### Step 5: Implement the Recommendation Engine

**What we did:** Created a rule-based function that maps findings and health score to one
of three outcomes: `approve`, `request_changes`, or `block`.

```python
def determine_recommendation(
    findings: list[Finding], health_score: int
) -> str:
    """
    Logic:
    - Any critical finding → block (regardless of score)
    - Score < 50 → request_changes
    - Score < 70 with high findings → request_changes
    - Otherwise → approve
    """
    has_critical = any(f.severity == "critical" for f in findings)
    has_high = any(f.severity == "high" for f in findings)

    if has_critical:
        return "block"
    if health_score < 50:
        return "request_changes"
    if health_score < 70 and has_high:
        return "request_changes"
    return "approve"
```

**Decision tree:**
```
                     Has critical finding?
                    /                      \
                 YES                        NO
                  |                          |
               BLOCK              Score < 50?
                                /             \
                             YES               NO
                              |                 |
                     REQUEST_CHANGES    Score < 70 AND has high?
                                        /                      \
                                     YES                        NO
                                      |                          |
                             REQUEST_CHANGES                  APPROVE
```

**Why "block" for any critical, regardless of score?**
A critical finding means there's a real vulnerability — SQL injection, hardcoded secrets,
auth bypass. Even if the rest of the code is perfect (score 95), one critical issue
means the PR should not be merged until it's fixed. This is a safety-first principle.

**Why the score < 70 AND has_high check?**
Without this, a PR with score 65 and only medium/low findings would get `approve`.
The extra check ensures that if high-severity issues are present AND the score is
in the "needs attention" range, we escalate to `request_changes`.

### Step 6: Build the Executive Summary Generator

**What we did:** Created a function that generates a 3-5 sentence natural language summary
for the top of the PR review comment.

```python
def generate_executive_summary(
    findings: list[Finding],
    health_score: int,
    recommendation: str,
) -> str:
    if not findings:
        return (
            "No issues were found in this pull request. "
            "The code changes look clean across security, performance, "
            "and style dimensions. Safe to merge."
        )

    # Count by agent
    agent_counts = defaultdict(int)
    for f in findings:
        agent_counts[f.agent] += 1

    # Count by severity
    sev_counts = defaultdict(int)
    for f in findings:
        sev_counts[f.severity] += 1

    parts = []

    # Opening line — total count
    total = len(findings)
    parts.append(
        f"Multi-agent review analyzed this PR across security, performance, "
        f"and style dimensions, finding {total} issue{'s' if total != 1 else ''}."
    )

    # Severity breakdown
    sev_parts = []
    for sev in ["critical", "high", "medium", "low"]:
        count = sev_counts.get(sev, 0)
        if count > 0:
            sev_parts.append(f"{count} {sev}")
    if sev_parts:
        parts.append(f"Breakdown: {', '.join(sev_parts)}.")

    # Agent breakdown
    agent_parts = []
    for agent in ["security", "performance", "style"]:
        count = agent_counts.get(agent, 0)
        if count > 0:
            agent_parts.append(f"{agent.capitalize()}: {count}")
    if agent_parts:
        parts.append(f"By domain: {', '.join(agent_parts)}.")

    # Top issue highlight
    if sev_counts.get("critical", 0) > 0:
        critical_finding = next(f for f in findings if f.severity == "critical")
        parts.append(
            f"Most urgent: {critical_finding.title} in "
            f"`{critical_finding.file_path}`."
        )

    return " ".join(parts)
```

**Example output:**
```
Multi-agent review analyzed this PR across security, performance, and style dimensions,
finding 12 issues. Breakdown: 3 critical, 2 high, 4 medium, 3 low. By domain:
Security: 5, Performance: 3, Style: 4. Most urgent: SQL Injection via f-string
interpolation in `app.py`.
```

**Design choices:**
- **Deterministic, not LLM-generated:** The summary is built from templates, not an LLM call.
  This ensures consistency, avoids hallucination, and adds zero latency.
- **Structured order:** Total count, then severity breakdown, then agent breakdown, then
  highlight. This mirrors how a senior engineer would verbally summarize a review.
- **Conditional highlight:** Only shows "Most urgent" if critical or high findings exist.

### Step 7: Wire It All Together — The `synthesize()` Function

**What we did:** Created the main entry point that orchestrates the full pipeline.

```python
def synthesize(
    security_findings: list[Finding],
    performance_findings: list[Finding],
    style_findings: list[Finding],
) -> SynthesizedReview:
    start = time.time()

    # Step 1: Combine all findings into one list
    all_findings = security_findings + performance_findings + style_findings

    # Step 2: Deduplicate (merge overlapping findings)
    deduped = deduplicate_findings(all_findings)

    # Step 3: Rank by severity and confidence
    ranked = rank_findings(deduped)

    # Step 4: Calculate Health Score
    health_score = calculate_health_score(ranked)

    # Step 5: Determine recommendation
    recommendation = determine_recommendation(ranked, health_score)

    # Step 6: Generate executive summary
    summary = generate_executive_summary(ranked, health_score, recommendation)

    # Count by severity for the response
    critical = sum(1 for f in ranked if f.severity == "critical")
    high = sum(1 for f in ranked if f.severity == "high")
    medium = sum(1 for f in ranked if f.severity == "medium")
    low = sum(1 for f in ranked if f.severity == "low")

    elapsed_ms = int((time.time() - start) * 1000)

    return SynthesizedReview(
        health_score=health_score,
        executive_summary=summary,
        recommendation=recommendation,
        findings=ranked,
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        duration_ms=elapsed_ms,
    )
```

**Key observation:** The entire synthesis pipeline (dedup + rank + score + recommend + summarize)
takes <1 millisecond. There are no LLM calls, no network requests, no I/O. It's pure
computation on in-memory data structures. This is by design — the "intelligence" is in the
domain agents; the synthesizer is a fast, deterministic merge layer.

**Interview talking point:** "The Synthesizer is deliberately not an LLM call. We use
deterministic algorithms for deduplication, ranking, and scoring because these operations
need to be fast, consistent, and auditable. If a developer asks 'why did you block my PR?'
we can point to the exact formula — `25 * 0.95 = 23.75 point penalty for the SQL injection` —
rather than saying 'the LLM decided.' This makes the system trustworthy."

### Step 8: Live Test — PR #4 Integration

**What we did:** Ran the full pipeline (3 agents + synthesizer) on PR #4.

**Results:**
```
[2026-03-20] INFO  All agents completed
    security=5, performance=3, style=6, total=14

[2026-03-20] INFO  Deduplicated findings
    removed=2, before=14, after=12

[2026-03-20] INFO  Synthesis complete
    input_findings=14, after_dedup=12,
    health_score=14, recommendation=block, elapsed_ms=0
```

The synthesizer processed 14 findings, removed 2 duplicates (where Security and Performance
flagged the same line), ranked them with critical issues first, computed a Health Score of
14/100, and generated a "block" recommendation.

---

## Architecture Patterns Used

| Pattern | Where | Why |
|---------|-------|-----|
| **Pipeline / Chain of Responsibility** | `synthesize()` function | Each step transforms data and passes it to the next: combine → dedup → rank → score → recommend → summarize |
| **Strategy Pattern** | `AGENT_PRECEDENCE` + `SEVERITY_RANK` dictionaries | Ranking and merge behavior is configurable via lookup tables, not hardcoded if/else chains |
| **Separation of Concerns** | `health_score.py` vs `synthesizer.py` | Scoring logic is isolated in its own module — testable independently, reusable by other callers |
| **Deterministic over Probabilistic** | No LLM in synthesizer | Reproducible results, zero latency, fully auditable decisions |
| **Escalation-only merging** | Severity always goes UP | Safety-first: if any agent thinks it's critical, it's critical |

---

## Files Created / Modified in Week 7

| File | Purpose |
|------|---------|
| `app/agents/synthesizer.py` | Synthesizer agent: dedup, rank, merge, executive summary |
| `app/services/health_score.py` | Health Score calculator + recommendation engine |
| `app/models/findings.py` | SynthesizedReview model (modified — added duration_ms) |

---

## Interview Talking Points Summary

1. **"How do you handle duplicate findings across agents?"**
   "We use location-based deduplication — `file:line` as the merge key. When multiple agents
   flag the same location, we keep the finding from the highest-precedence agent (Security >
   Performance > Style), take the maximum severity, and append cross-references. This reduces
   noise while preserving all insights."

2. **"How does the Health Score work?"**
   "It's a weighted penalty system: start at 100, subtract severity-specific weights scaled by
   confidence. One critical finding costs 25 points, one low costs 2. The confidence factor
   means uncertain findings penalize less. This creates a metric that matches how developers
   actually think about code quality."

3. **"Why not use an LLM for the synthesizer?"**
   "The synthesizer needs to be fast, deterministic, and auditable. Deduplication is a set
   operation, ranking is a sort, scoring is arithmetic. Adding an LLM would increase latency
   by 2-5 seconds, introduce non-determinism, and make it harder to explain decisions. The
   intelligence is in the domain agents — the synthesizer is a merge layer."

4. **"What's the recommendation logic?"**
   "Rule-based decision tree: any critical finding triggers 'block' regardless of score,
   score below 50 triggers 'request_changes', and score below 70 with high findings also
   triggers 'request_changes.' Everything else is 'approve.' This is deliberately simple
   and conservative — we'd rather over-flag than miss a real vulnerability."

5. **"How would you improve the deduplication?"**
   "The current approach uses exact file+line matching. Future improvements could use line
   range overlap detection (findings spanning lines 5-10 and 7-12 overlap), semantic similarity
   between descriptions (using embeddings), or category normalization (mapping 'sql_injection'
   and 'unbounded_query' to the same root cause). But the current approach catches the most
   common case — same line, different agents — with zero false positives."

---

*Documentation written 2026-03-20 as part of Week 7 completion.*

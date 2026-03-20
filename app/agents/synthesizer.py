"""
Synthesizer Agent
==================

The Synthesizer is the "senior engineering manager" of Ninja Code Guard.
It takes findings from all three domain agents (Security, Performance, Style)
and produces a unified, non-redundant review.

Responsibilities:
1. **Deduplicate** — If Security and Performance flag the same line for
   different reasons, merge them into one finding with both perspectives.
2. **Resolve conflicts** — If agents disagree on severity, use a precedence
   hierarchy: Security > Performance > Style.
3. **Re-rank** — Sort findings by composite score: severity × confidence.
4. **Compute Health Score** — 0-100 based on weighted finding density.
5. **Generate executive summary** — 3-5 sentences summarizing the review.
6. **Determine recommendation** — approve / request_changes / block.

Why a Synthesizer instead of just concatenating findings?
- Without dedup: the same SQL injection might be flagged by both Security
  (as CWE-89) and Performance (as "unbounded query") — confusing for devs.
- Without conflict resolution: Security says "critical", Style says "medium"
  for the same issue — which severity should the comment show?
- Without re-ranking: findings appear in arbitrary order — devs should see
  the most important issues first.
"""

from __future__ import annotations

import time
from collections import defaultdict

import structlog

from app.models.findings import Finding, SynthesizedReview
from app.services.health_score import calculate_health_score, determine_recommendation

logger = structlog.get_logger()

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


def _finding_key(f: Finding) -> str:
    """
    Generate a deduplication key for a finding.

    Two findings are considered duplicates if they reference the same
    file and overlapping line ranges. We use a simplified key based on
    file_path and line_start — findings on the same line from different
    agents are candidates for merging.
    """
    return f"{f.file_path}:{f.line_start}:{f.category}"


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """
    Remove duplicate findings that reference the same code location.

    When multiple agents flag the same file+line, we keep the finding from
    the highest-precedence agent (Security > Performance > Style) and take
    the maximum severity between them.

    Example:
        Security flags app.py:5 as "critical" (SQL injection)
        Performance flags app.py:5 as "high" (unbounded query)
        → Keep Security's finding with "critical" severity
        → Append Performance's insight to the description
    """
    # Group findings by location
    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        key = _finding_key(finding)
        groups[key].append(finding)

    deduped = []
    duplicates_removed = 0

    for _key, group in groups.items():
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
            severity=max_severity.severity,
            category=primary.category,
            title=primary.title,
            description=merged_description,
            suggested_fix=primary.suggested_fix,
            cwe_id=primary.cwe_id,
            confidence=max(f.confidence for f in group),
        )
        deduped.append(merged)
        duplicates_removed += len(group) - 1

    if duplicates_removed > 0:
        logger.info(
            "Deduplicated findings",
            removed=duplicates_removed,
            before=len(findings),
            after=len(deduped),
        )

    return deduped


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


def generate_executive_summary(
    findings: list[Finding],
    health_score: int,
    recommendation: str,
) -> str:
    """
    Generate a 3-5 sentence executive summary of the review.

    This appears at the top of the PR comment, giving the author a quick
    overview without needing to read every finding.
    """
    if not findings:
        return (
            "No issues were found in this pull request. "
            "The code changes look clean across security, performance, and style dimensions. "
            "Safe to merge."
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

    # Opening line
    total = len(findings)
    parts.append(
        f"Multi-agent review analyzed this PR across security, performance, and style dimensions, "
        f"finding {total} issue{'s' if total != 1 else ''}."
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
            f"Most urgent: {critical_finding.title} in `{critical_finding.file_path}`."
        )
    elif sev_counts.get("high", 0) > 0:
        high_finding = next(f for f in findings if f.severity == "high")
        parts.append(
            f"Top priority: {high_finding.title} in `{high_finding.file_path}`."
        )

    return " ".join(parts)


def synthesize(
    security_findings: list[Finding],
    performance_findings: list[Finding],
    style_findings: list[Finding],
) -> SynthesizedReview:
    """
    Main entry point: synthesize findings from all agents into a unified review.

    Pipeline:
    1. Combine all findings
    2. Deduplicate (merge overlapping findings)
    3. Rank by severity and confidence
    4. Calculate Health Score
    5. Determine recommendation
    6. Generate executive summary

    Returns a SynthesizedReview ready for posting to GitHub.
    """
    start = time.time()

    # Step 1: Combine
    all_findings = security_findings + performance_findings + style_findings

    # Step 2: Deduplicate
    deduped = deduplicate_findings(all_findings)

    # Step 3: Rank
    ranked = rank_findings(deduped)

    # Step 4: Health Score
    health_score = calculate_health_score(ranked)

    # Step 5: Recommendation
    recommendation = determine_recommendation(ranked, health_score)

    # Step 6: Executive summary
    summary = generate_executive_summary(ranked, health_score, recommendation)

    # Count by severity
    critical = sum(1 for f in ranked if f.severity == "critical")
    high = sum(1 for f in ranked if f.severity == "high")
    medium = sum(1 for f in ranked if f.severity == "medium")
    low = sum(1 for f in ranked if f.severity == "low")

    elapsed_ms = int((time.time() - start) * 1000)

    logger.info(
        "Synthesis complete",
        input_findings=len(all_findings),
        after_dedup=len(ranked),
        health_score=health_score,
        recommendation=recommendation,
        elapsed_ms=elapsed_ms,
    )

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

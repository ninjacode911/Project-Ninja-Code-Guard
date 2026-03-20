"""
PR Health Score Calculator
===========================

Computes a 0-100 health score for a PR based on finding density and severity.

Formula:
    base_score = 100
    penalty = sum(SEVERITY_WEIGHTS[f.severity] * CONFIDENCE_FACTOR(f.confidence) for f in findings)
    health_score = max(0, min(100, base_score - penalty))

Severity weights are calibrated so that:
- 1 critical finding drops the score by 25 points (one critical = action required)
- 1 high finding drops by 15 points
- 1 medium finding drops by 7 points
- 1 low finding drops by 2 points

Confidence factor scales the penalty — a finding with 0.5 confidence penalizes
half as much as one with 1.0 confidence. This rewards agents for being honest
about uncertainty.

Score interpretation:
    90-100: Excellent — safe to merge
    70-89:  Good — minor issues, merge at discretion
    50-69:  Needs attention — address before merging
    30-49:  Poor — significant issues found
    0-29:   Critical — do not merge
"""

from __future__ import annotations

from app.models.findings import Finding

SEVERITY_WEIGHTS = {
    "critical": 25,
    "high": 15,
    "medium": 7,
    "low": 2,
}


def calculate_health_score(findings: list[Finding]) -> int:
    """
    Calculate the PR Health Score from 0-100.

    Higher confidence findings penalize more heavily. This incentivizes
    agents to set confidence honestly — flagging everything as 1.0
    confidence would over-penalize, while honest 0.6 confidence
    for uncertain findings results in fairer scores.
    """
    if not findings:
        return 100

    total_penalty = 0.0
    for finding in findings:
        weight = SEVERITY_WEIGHTS.get(finding.severity, 5)
        confidence_factor = max(0.3, finding.confidence)  # Minimum 0.3 floor
        total_penalty += weight * confidence_factor

    score = 100 - total_penalty
    return max(0, min(100, round(score)))


def determine_recommendation(
    findings: list[Finding], health_score: int
) -> str:
    """
    Determine the PR recommendation based on findings and score.

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

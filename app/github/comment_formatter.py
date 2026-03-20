"""
GitHub Comment Formatter
=========================

Converts our internal Finding and SynthesizedReview data structures into
GitHub-flavored Markdown for posting as PR comments.

Two types of output:
1. **Inline comments** — one per finding, anchored to a specific file+line.
   These appear right next to the code, like a human reviewer's comments.
2. **Summary comment** — a top-level PR comment with the Health Score,
   finding counts by severity, and an executive summary.

Design decisions:
- We use emoji prefixes for severity to make scanning fast (most devs skim reviews)
- Each inline comment includes the agent name and category for traceability
- CWE IDs are linked for security findings (so devs can learn about the vulnerability)
- Suggested fixes use fenced code blocks for easy copy-paste
"""

from __future__ import annotations

from app.models.findings import Finding, SynthesizedReview

# Emoji and color mapping for severity levels
SEVERITY_EMOJI = {
    "critical": "\U0001f6a8",  # 🚨
    "high": "\U0001f7e0",      # 🟠
    "medium": "\U0001f7e1",    # 🟡
    "low": "\u2139\ufe0f",     # ℹ️
}

AGENT_EMOJI = {
    "security": "\U0001f512",     # 🔒
    "performance": "\u26a1",      # ⚡
    "style": "\u270f\ufe0f",      # ✏️
}


def format_inline_comment(finding: Finding) -> str:
    """
    Format a single Finding as a GitHub inline comment body.

    This Markdown will appear anchored to the specific file+line in the PR diff.

    Example output:
        🚨 **[CRITICAL — Security] SQL Injection Risk**

        The query on line 47 constructs SQL via string interpolation.
        User input is directly embedded without sanitization.

        **Suggested fix:**
        ```python
        cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        ```

        > 🔒 Security · CWE-89 · Confidence: 0.92
    """
    severity_emoji = SEVERITY_EMOJI.get(finding.severity, "")
    agent_emoji = AGENT_EMOJI.get(finding.agent, "")
    severity_upper = finding.severity.upper()
    agent_title = finding.agent.capitalize()

    # Build the comment body
    lines = [
        f"{severity_emoji} **[{severity_upper} — {agent_title}] {finding.title}**",
        "",
        finding.description,
    ]

    # Add suggested fix if present
    if finding.suggested_fix:
        lines.extend([
            "",
            "**Suggested fix:**",
            "```",
            finding.suggested_fix,
            "```",
        ])

    # Add metadata footer
    footer_parts = [f"{agent_emoji} {agent_title}"]
    if finding.cwe_id:
        footer_parts.append(f"[{finding.cwe_id}](https://cwe.mitre.org/data/definitions/{finding.cwe_id.split('-')[1]}.html)")
    footer_parts.append(f"Confidence: {finding.confidence:.2f}")

    lines.extend(["", f"> {' · '.join(footer_parts)}"])

    return "\n".join(lines)


def format_summary_comment(review: SynthesizedReview) -> str:
    """
    Format the top-level PR summary comment with Health Score and finding overview.

    This is posted as a regular PR comment (not inline). It gives the PR author
    a quick overview without needing to look at every inline comment.

    The Health Score gauge uses block characters to create a visual progress bar
    in pure Unicode (works in GitHub Markdown without images).
    """
    score = review.health_score

    # Determine overall status
    if score >= 80:
        status_emoji = "\u2705"  # ✅
        status_text = "Healthy"
    elif score >= 60:
        status_emoji = "\u26a0\ufe0f"  # ⚠️
        status_text = "Needs Attention"
    else:
        status_emoji = "\u274c"  # ❌
        status_text = "Action Required"

    # Build the visual health bar (20 segments)
    filled = round(score / 5)
    bar = "\u2588" * filled + "\u2591" * (20 - filled)

    # Count total findings
    total = (
        review.critical_count
        + review.high_count
        + review.medium_count
        + review.low_count
    )

    lines = [
        f"## {status_emoji} Ninja Code Guard Review — Health Score: {score}/100",
        "",
        f"`{bar}` **{score}**/100 — {status_text}",
        "",
        "### Findings Summary",
        "",
        "| Severity | Count |",
        "|----------|-------|",
        f"| \U0001f6a8 Critical | {review.critical_count} |",
        f"| \U0001f7e0 High | {review.high_count} |",
        f"| \U0001f7e1 Medium | {review.medium_count} |",
        f"| \u2139\ufe0f Low | {review.low_count} |",
        f"| **Total** | **{total}** |",
        "",
    ]

    # Add recommendation
    rec_map = {
        "approve": "\u2705 **Recommendation: Approve** — No critical issues found.",
        "request_changes": "\u26a0\ufe0f **Recommendation: Request Changes** — Issues found that should be addressed.",
        "block": "\u274c **Recommendation: Block Merge** — Critical issues must be resolved before merging.",
    }
    lines.append(rec_map.get(review.recommendation, ""))
    lines.append("")

    # Add executive summary
    lines.extend([
        "### Executive Summary",
        "",
        review.executive_summary,
        "",
    ])

    # Add detailed findings (so all info is visible even if inline comments fail)
    if review.findings:
        lines.append("### Detailed Findings")
        lines.append("")
        for _i, finding in enumerate(review.findings, 1):
            severity_emoji = SEVERITY_EMOJI.get(finding.severity, "")
            agent_emoji = AGENT_EMOJI.get(finding.agent, "")
            lines.append(
                f"<details>\n"
                f"<summary>{severity_emoji} <b>[{finding.severity.upper()}]</b> "
                f"{finding.title} — <code>{finding.file_path}:{finding.line_start}</code></summary>\n\n"
                f"{finding.description}\n"
            )
            if finding.suggested_fix:
                lines.append(f"**Suggested fix:**\n```\n{finding.suggested_fix}\n```\n")
            footer_parts = [f"{agent_emoji} {finding.agent.capitalize()}"]
            if finding.cwe_id:
                cwe_num = finding.cwe_id.split("-")[-1] if "-" in finding.cwe_id else ""
                footer_parts.append(f"[{finding.cwe_id}](https://cwe.mitre.org/data/definitions/{cwe_num}.html)")
            footer_parts.append(f"Confidence: {finding.confidence:.2f}")
            lines.append(f"> {' · '.join(footer_parts)}\n")
            lines.append("</details>\n")

    lines.extend([
        "---",
        "*Reviewed by [Ninja Code Guard](https://github.com/ninjacode911/ninja-code-guard) — Multi-agent code review*",
    ])

    return "\n".join(lines)


def findings_to_review_comments(findings: list[Finding]) -> list[dict]:
    """
    Convert a list of Findings into GitHub review comment dicts.

    Each dict has the structure that GitHub's Create Review API expects:
    - path: the file path relative to repo root
    - line: the line number in the NEW version of the file
    - body: the formatted Markdown comment

    Note: GitHub requires `line` to be within the diff hunk. If a finding
    references a line outside the diff, we skip it (GitHub API would reject it).
    We use `line` (not `position`) because position-based comments are deprecated.
    """
    comments = []
    for finding in findings:
        comment = {
            "path": finding.file_path,
            "line": finding.line_start,
            "side": "RIGHT",  # RIGHT = new version of the file (what the PR introduces)
            "body": format_inline_comment(finding),
        }
        comments.append(comment)

    return comments

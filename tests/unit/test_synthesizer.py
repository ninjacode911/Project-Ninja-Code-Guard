"""
Tests for the Synthesizer Agent and Health Score calculator.

These tests verify:
1. Deduplication merges findings on the same file+line
2. Security agent takes precedence in severity conflicts
3. Health Score formula applies correct penalties
4. Recommendation logic (block/request_changes/approve)
5. Executive summary generation
6. Ranking puts critical findings first
"""


from app.agents.synthesizer import (
    deduplicate_findings,
    generate_executive_summary,
    rank_findings,
    synthesize,
)
from app.models.findings import Finding
from app.services.health_score import calculate_health_score, determine_recommendation


def _make_finding(agent="security", severity="high", file_path="app.py",
                  line_start=5, category="test", confidence=0.9, **kwargs):
    """Helper to create Finding objects with sensible defaults."""
    return Finding(
        agent=agent,
        file_path=file_path,
        line_start=line_start,
        line_end=kwargs.get("line_end", line_start),
        severity=severity,
        category=category,
        title=kwargs.get("title", f"Test {category}"),
        description=kwargs.get("description", "Test finding description."),
        suggested_fix=kwargs.get("suggested_fix", ""),
        cwe_id=kwargs.get("cwe_id"),
        confidence=confidence,
    )


class TestDeduplication:
    def test_no_duplicates_unchanged(self):
        """Findings on different lines should not be deduplicated."""
        findings = [
            _make_finding(line_start=5, category="sql_injection"),
            _make_finding(line_start=10, category="xss"),
        ]
        result = deduplicate_findings(findings)
        assert len(result) == 2

    def test_same_line_same_category_merged(self):
        """Two agents flagging same line+category should produce one finding."""
        findings = [
            _make_finding(agent="security", line_start=5, severity="critical", category="sql_injection"),
            _make_finding(agent="performance", line_start=5, severity="high", category="sql_injection"),
        ]
        result = deduplicate_findings(findings)
        assert len(result) == 1

    def test_same_line_different_category_kept(self):
        """Two agents flagging same line but different categories should both be kept."""
        findings = [
            _make_finding(agent="security", line_start=5, category="sql_injection"),
            _make_finding(agent="style", line_start=5, category="naming"),
        ]
        result = deduplicate_findings(findings)
        assert len(result) == 2

    def test_security_takes_precedence(self):
        """When merging same category, security agent's finding should be kept as primary."""
        findings = [
            _make_finding(agent="style", line_start=5, category="sql_injection"),
            _make_finding(agent="security", line_start=5, category="sql_injection"),
        ]
        result = deduplicate_findings(findings)
        assert len(result) == 1
        assert result[0].agent == "security"

    def test_max_severity_wins(self):
        """Merged finding should use the maximum severity from all agents."""
        findings = [
            _make_finding(agent="security", line_start=5, severity="medium"),
            _make_finding(agent="performance", line_start=5, severity="critical"),
        ]
        result = deduplicate_findings(findings)
        assert result[0].severity == "critical"

    def test_merged_description_mentions_other_agents(self):
        """Merged finding should note which other agents also flagged it."""
        findings = [
            _make_finding(agent="security", line_start=5),
            _make_finding(agent="performance", line_start=5),
        ]
        result = deduplicate_findings(findings)
        assert "performance" in result[0].description.lower()


class TestRanking:
    def test_critical_before_low(self):
        """Critical findings should appear before low findings."""
        findings = [
            _make_finding(severity="low", line_start=1),
            _make_finding(severity="critical", line_start=2),
            _make_finding(severity="medium", line_start=3),
        ]
        ranked = rank_findings(findings)
        assert ranked[0].severity == "critical"
        assert ranked[-1].severity == "low"

    def test_same_severity_sorted_by_confidence(self):
        """Within same severity, higher confidence comes first."""
        findings = [
            _make_finding(severity="high", confidence=0.5, line_start=1),
            _make_finding(severity="high", confidence=0.95, line_start=2),
        ]
        ranked = rank_findings(findings)
        assert ranked[0].confidence == 0.95


class TestHealthScore:
    def test_no_findings_returns_100(self):
        """Empty findings should give perfect score."""
        assert calculate_health_score([]) == 100

    def test_one_critical_drops_significantly(self):
        """One critical finding should drop score by ~25 points."""
        findings = [_make_finding(severity="critical", confidence=1.0)]
        score = calculate_health_score(findings)
        assert 70 <= score <= 80  # 100 - 25*1.0 = 75

    def test_low_confidence_penalizes_less(self):
        """Low-confidence findings should penalize less."""
        high_conf = [_make_finding(severity="high", confidence=1.0)]
        low_conf = [_make_finding(severity="high", confidence=0.3)]
        assert calculate_health_score(low_conf) > calculate_health_score(high_conf)

    def test_score_never_below_zero(self):
        """Score should be clamped to 0 minimum."""
        findings = [_make_finding(severity="critical") for _ in range(10)]
        assert calculate_health_score(findings) == 0

    def test_score_never_above_100(self):
        """Score should be clamped to 100 maximum."""
        assert calculate_health_score([]) == 100


class TestRecommendation:
    def test_critical_finding_blocks(self):
        """Any critical finding should result in 'block'."""
        findings = [_make_finding(severity="critical")]
        assert determine_recommendation(findings, 50) == "block"

    def test_low_score_requests_changes(self):
        """Score below 50 should request changes."""
        findings = [_make_finding(severity="medium")]
        assert determine_recommendation(findings, 30) == "request_changes"

    def test_healthy_pr_approves(self):
        """High score with no critical/high findings should approve."""
        findings = [_make_finding(severity="low")]
        assert determine_recommendation(findings, 90) == "approve"

    def test_no_findings_approves(self):
        """No findings should approve."""
        assert determine_recommendation([], 100) == "approve"


class TestExecutiveSummary:
    def test_no_findings_positive_summary(self):
        """Empty findings should produce a positive summary."""
        summary = generate_executive_summary([], 100, "approve")
        assert "no issues" in summary.lower() or "clean" in summary.lower()

    def test_summary_includes_counts(self):
        """Summary should mention finding counts."""
        findings = [
            _make_finding(severity="critical"),
            _make_finding(severity="high", line_start=10),
        ]
        summary = generate_executive_summary(findings, 50, "block")
        assert "2" in summary
        assert "critical" in summary.lower()


class TestSynthesize:
    def test_full_synthesis_pipeline(self):
        """Full synthesize() should return a valid SynthesizedReview."""
        sec = [_make_finding(agent="security", severity="critical", line_start=5)]
        perf = [_make_finding(agent="performance", severity="high", line_start=10)]
        style = [_make_finding(agent="style", severity="low", line_start=15)]

        review = synthesize(sec, perf, style)

        assert review.health_score >= 0
        assert review.health_score <= 100
        assert review.critical_count == 1
        assert review.high_count == 1
        assert review.low_count == 1
        assert review.recommendation == "block"  # Has critical
        assert len(review.findings) == 3
        assert len(review.executive_summary) > 0

    def test_synthesis_with_duplicates(self):
        """Synthesis should deduplicate findings on same line+category."""
        sec = [_make_finding(agent="security", line_start=5, category="sql_injection")]
        perf = [_make_finding(agent="performance", line_start=5, category="sql_injection")]
        style = []

        review = synthesize(sec, perf, style)
        assert len(review.findings) == 1  # Deduplicated (same line + category)

    def test_synthesis_empty_input(self):
        """Empty input from all agents should produce clean review."""
        review = synthesize([], [], [])
        assert review.health_score == 100
        assert review.recommendation == "approve"
        assert len(review.findings) == 0

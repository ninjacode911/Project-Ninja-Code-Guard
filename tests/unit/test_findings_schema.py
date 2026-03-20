"""Tests for Finding and SynthesizedReview schema validation."""

import pytest
from pydantic import ValidationError

from app.models.findings import Finding, SynthesizedReview


class TestFindingSchema:
    def test_valid_finding(self, sample_finding_data):
        finding = Finding(**sample_finding_data)
        assert finding.agent == "security"
        assert finding.severity == "critical"
        assert finding.confidence == 0.92

    def test_finding_rejects_invalid_agent(self, sample_finding_data):
        sample_finding_data["agent"] = "invalid_agent"
        with pytest.raises(ValidationError):
            Finding(**sample_finding_data)

    def test_finding_rejects_invalid_severity(self, sample_finding_data):
        sample_finding_data["severity"] = "urgent"
        with pytest.raises(ValidationError):
            Finding(**sample_finding_data)

    def test_finding_confidence_bounds(self, sample_finding_data):
        sample_finding_data["confidence"] = 1.5
        with pytest.raises(ValidationError):
            Finding(**sample_finding_data)

        sample_finding_data["confidence"] = -0.1
        with pytest.raises(ValidationError):
            Finding(**sample_finding_data)

    def test_finding_optional_cwe_id(self, sample_finding_data):
        sample_finding_data["cwe_id"] = None
        finding = Finding(**sample_finding_data)
        assert finding.cwe_id is None


class TestSynthesizedReviewSchema:
    def test_valid_review(self, sample_review_data):
        review = SynthesizedReview(**sample_review_data)
        assert review.health_score == 65
        assert review.recommendation == "block"
        assert len(review.findings) == 1

    def test_review_health_score_bounds(self, sample_review_data):
        sample_review_data["health_score"] = 101
        with pytest.raises(ValidationError):
            SynthesizedReview(**sample_review_data)

        sample_review_data["health_score"] = -1
        with pytest.raises(ValidationError):
            SynthesizedReview(**sample_review_data)

    def test_review_rejects_invalid_recommendation(self, sample_review_data):
        sample_review_data["recommendation"] = "maybe"
        with pytest.raises(ValidationError):
            SynthesizedReview(**sample_review_data)

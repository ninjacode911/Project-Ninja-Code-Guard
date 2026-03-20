"""Shared test fixtures for Sentinel AI."""

import pytest


@pytest.fixture
def sample_finding_data():
    """A valid Finding dict for testing schema validation."""
    return {
        "agent": "security",
        "file_path": "src/auth/login.py",
        "line_start": 47,
        "line_end": 47,
        "severity": "critical",
        "category": "sql_injection",
        "title": "SQL Injection Risk",
        "description": "Query constructed via string interpolation with unsanitized user input.",
        "suggested_fix": "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
        "cwe_id": "CWE-89",
        "confidence": 0.92,
    }


@pytest.fixture
def sample_review_data(sample_finding_data):
    """A valid SynthesizedReview dict for testing."""
    return {
        "health_score": 65,
        "executive_summary": "This PR introduces a critical SQL injection vulnerability in the login endpoint.",
        "recommendation": "block",
        "findings": [sample_finding_data],
        "critical_count": 1,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "duration_ms": 12500,
    }

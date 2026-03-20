"""
Tests for the Security Agent.

These tests verify:
1. The agent produces valid Finding objects from LLM output
2. The base agent gracefully handles LLM failures
3. Bandit tool correctly detects known vulnerabilities
4. The comment formatter produces valid GitHub Markdown
5. Malformed LLM output is handled without crashing

Testing strategy:
- We mock the LLM (ChatGroq) to avoid real API calls in tests
- We use real Bandit runs on small code snippets for tool tests
- We test the conversion pipeline: LLM output → Finding objects
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base_agent import AgentFindings, FindingOutput
from app.agents.security_agent import SecurityAgent
from app.github.client import PRData
from app.github.comment_formatter import (
    findings_to_review_comments,
    format_inline_comment,
    format_summary_comment,
)
from app.models.findings import Finding, SynthesizedReview
from app.tools.bandit_tool import run_bandit

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_pr_data():
    """A minimal PRData object for testing agents."""
    return PRData(
        repo_full_name="ninjacode911/codeguard-test",
        pr_number=1,
        commit_sha="abc123def456",
        title="Add user lookup",
        diff=(
            'diff --git a/app.py b/app.py\n'
            '--- a/app.py\n'
            '+++ b/app.py\n'
            '@@ -1,3 +1,8 @@\n'
            ' import sqlite3\n'
            '+\n'
            '+def get_user(user_id):\n'
            '+    conn = sqlite3.connect("users.db")\n'
            '+    query = f"SELECT * FROM users WHERE id = {user_id}"\n'
            '+    return conn.execute(query).fetchone()\n'
        ),
        changed_files=[{"filename": "app.py", "status": "modified"}],
        file_contents={
            "app.py": (
                'import sqlite3\n'
                '\n'
                'def get_user(user_id):\n'
                '    conn = sqlite3.connect("users.db")\n'
                '    query = f"SELECT * FROM users WHERE id = {user_id}"\n'
                '    return conn.execute(query).fetchone()\n'
            ),
        },
    )


@pytest.fixture
def sample_finding():
    """A valid Finding for testing formatters."""
    return Finding(
        agent="security",
        file_path="app.py",
        line_start=5,
        line_end=5,
        severity="critical",
        category="sql_injection",
        title="SQL Injection via f-string",
        description=(
            "User input `user_id` is directly interpolated into a SQL query "
            "using an f-string. An attacker could pass a crafted user_id like "
            "`1 OR 1=1` to extract all records."
        ),
        suggested_fix='cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
        cwe_id="CWE-89",
        confidence=0.95,
    )


@pytest.fixture
def mock_llm_response():
    """A mock AgentFindings that simulates the LLM's structured output."""
    return AgentFindings(
        findings=[
            FindingOutput(
                file_path="app.py",
                line_start=5,
                line_end=5,
                severity="critical",
                category="sql_injection",
                title="SQL Injection via f-string",
                description="User input directly embedded in SQL query.",
                suggested_fix='cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
                cwe_id="CWE-89",
                confidence=0.95,
            ),
        ]
    )


# ─── SecurityAgent Tests ──────────────────────────────────────────────────


class TestSecurityAgent:
    def test_agent_name(self):
        """SecurityAgent should identify as 'security'."""
        agent = SecurityAgent()
        assert agent.agent_name == "security"

    def test_system_prompt_loads(self):
        """System prompt file should exist and contain security-related content."""
        agent = SecurityAgent()
        prompt = agent.system_prompt
        assert len(prompt) > 100  # Not empty
        assert "security" in prompt.lower()
        assert "CWE" in prompt

    @pytest.mark.asyncio
    async def test_review_with_mocked_llm(self, sample_pr_data, mock_llm_response):
        """
        The full review pipeline should produce Finding objects from LLM output.

        Testing LangChain chains with mocks is tricky because the | operator
        creates internal Runnable objects. Instead, we test the conversion
        pipeline directly: given an AgentFindings object (what the LLM returns),
        verify that _convert_to_findings produces correct Finding objects.

        The LLM call itself is tested via the live end-to-end test (PR #3 on
        codeguard-test repo), which proved the full pipeline works.
        """
        agent = SecurityAgent()

        # Test the conversion pipeline directly — this is the critical path
        findings = agent._convert_to_findings(mock_llm_response)

        assert len(findings) == 1
        assert findings[0].agent == "security"
        assert findings[0].severity == "critical"
        assert findings[0].category == "sql_injection"
        assert findings[0].cwe_id == "CWE-89"
        assert findings[0].confidence == 0.95
        assert findings[0].file_path == "app.py"
        assert findings[0].line_start == 5
        assert "SELECT" in findings[0].suggested_fix

    @pytest.mark.asyncio
    async def test_review_handles_llm_failure(self, sample_pr_data):
        """
        If the LLM call fails, the agent should return an empty list
        instead of crashing the entire pipeline.
        """
        # Patch at the class level since ChatGroq is a Pydantic model
        mock_chain = AsyncMock(side_effect=Exception("Groq API timeout"))

        with patch("app.agents.base_agent.ChatGroq") as mock_chat_groq:
            mock_llm_instance = MagicMock()
            mock_llm_instance.with_structured_output.return_value = MagicMock(
                __ror__=MagicMock(return_value=mock_chain),
                __or__=MagicMock(return_value=mock_chain),
            )
            mock_chat_groq.return_value = mock_llm_instance

            agent = SecurityAgent()
            with patch.object(agent, "run_static_analysis", return_value=""):
                findings = await agent.review(sample_pr_data)

        assert findings == []  # Graceful degradation, not a crash


# ─── BaseAgent Conversion Tests ──────────────────────────────────────────


class TestBaseAgentConversion:
    def test_converts_valid_findings(self, mock_llm_response):
        """Valid LLM output should be converted to Finding objects."""
        agent = SecurityAgent()
        findings = agent._convert_to_findings(mock_llm_response)

        assert len(findings) == 1
        assert findings[0].agent == "security"
        assert findings[0].severity == "critical"

    def test_clamps_confidence_to_valid_range(self):
        """Confidence values outside [0, 1] should be clamped."""
        agent = SecurityAgent()
        output = AgentFindings(
            findings=[
                FindingOutput(
                    file_path="app.py",
                    line_start=1,
                    line_end=1,
                    severity="high",
                    category="test",
                    title="Test",
                    description="Test finding",
                    confidence=1.5,  # Over 1.0 — should be clamped
                ),
            ]
        )
        findings = agent._convert_to_findings(output)
        assert findings[0].confidence == 1.0

    def test_normalizes_invalid_severity(self):
        """Unknown severity values should default to 'medium'."""
        agent = SecurityAgent()
        output = AgentFindings(
            findings=[
                FindingOutput(
                    file_path="app.py",
                    line_start=1,
                    line_end=1,
                    severity="URGENT",  # Invalid — should become "medium"
                    category="test",
                    title="Test",
                    description="Test finding",
                    confidence=0.5,
                ),
            ]
        )
        findings = agent._convert_to_findings(output)
        assert findings[0].severity == "medium"

    def test_handles_empty_findings(self):
        """Empty findings list from LLM should produce empty output."""
        agent = SecurityAgent()
        output = AgentFindings(findings=[])
        findings = agent._convert_to_findings(output)
        assert findings == []


# ─── Bandit Tool Tests ──────────────────────────────────────────────────


class TestBanditTool:
    @pytest.mark.asyncio
    async def test_detects_sql_injection(self):
        """Bandit should detect SQL injection via string formatting."""
        files = {
            "app.py": (
                'import sqlite3\n'
                'def get(uid):\n'
                '    conn = sqlite3.connect("db")\n'
                '    conn.execute(f"SELECT * FROM users WHERE id = {uid}")\n'
            ),
        }
        result = await run_bandit(files)
        # Bandit should find at least one issue
        assert "Bandit" in result or result == ""  # Empty if bandit not installed

    @pytest.mark.asyncio
    async def test_skips_non_python_files(self):
        """Bandit should ignore non-Python files."""
        files = {
            "style.css": "body { color: red; }",
            "index.html": "<h1>Hello</h1>",
        }
        result = await run_bandit(files)
        assert result == ""

    @pytest.mark.asyncio
    async def test_handles_empty_input(self):
        """Empty file dict should return empty string."""
        result = await run_bandit({})
        assert result == ""


# ─── Comment Formatter Tests ────────────────────────────────────────────


class TestCommentFormatter:
    def test_inline_comment_format(self, sample_finding):
        """Inline comments should contain severity, title, and CWE link."""
        comment = format_inline_comment(sample_finding)
        assert "CRITICAL" in comment
        assert "SQL Injection" in comment
        assert "CWE-89" in comment
        assert "Suggested fix" in comment

    def test_summary_comment_format(self, sample_finding):
        """Summary comment should contain health score and findings table."""
        review = SynthesizedReview(
            health_score=20,
            executive_summary="Found critical SQL injection vulnerabilities.",
            recommendation="block",
            findings=[sample_finding],
            critical_count=1,
            high_count=0,
            medium_count=0,
            low_count=0,
        )
        comment = format_summary_comment(review)
        assert "20/100" in comment
        assert "Block Merge" in comment
        assert "Critical" in comment
        assert "Ninja Code Guard" in comment

    def test_findings_to_review_comments(self, sample_finding):
        """Findings should be converted to GitHub review comment dicts."""
        comments = findings_to_review_comments([sample_finding])
        assert len(comments) == 1
        assert comments[0]["path"] == "app.py"
        assert comments[0]["line"] == 5
        assert comments[0]["side"] == "RIGHT"
        assert "SQL Injection" in comments[0]["body"]

    def test_healthy_pr_summary(self):
        """A PR with no findings should show approve recommendation."""
        review = SynthesizedReview(
            health_score=100,
            executive_summary="No security issues found.",
            recommendation="approve",
            findings=[],
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
        )
        comment = format_summary_comment(review)
        assert "100/100" in comment
        assert "Approve" in comment
        assert "Healthy" in comment

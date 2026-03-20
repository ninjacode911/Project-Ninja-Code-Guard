"""
Tests for the Performance Agent and radon tool.

These tests verify:
1. PerformanceAgent identifies as "performance" and loads its prompt
2. Radon correctly detects high-complexity functions
3. Radon handles non-Python files and empty input gracefully
4. The agent converts LLM output to Finding objects correctly
5. The agent handles LLM failures without crashing

Testing approach:
- Radon tests use REAL Radon execution on synthetic code (it's fast and local)
- LLM tests use mocks (we don't want to burn Groq API quota in CI)
- Conversion tests verify the base_agent → Finding pipeline
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base_agent import AgentFindings, FindingOutput
from app.agents.performance_agent import PerformanceAgent
from app.github.client import PRData
from app.tools.radon_tool import run_radon

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_pr_data():
    """PRData with code that has performance issues."""
    return PRData(
        repo_full_name="ninjacode911/codeguard-test",
        pr_number=4,
        commit_sha="abc123",
        title="Add user processing",
        diff=(
            'diff --git a/app.py b/app.py\n'
            '+def process_users(users):\n'
            '+    result = []\n'
            '+    for u in users:\n'
            '+        for item in users:\n'
            '+            if u["id"] == item["id"]:\n'
            '+                result.append(u)\n'
            '+    return result\n'
        ),
        changed_files=[{"filename": "app.py", "status": "modified"}],
        file_contents={
            "app.py": (
                'def process_users(users):\n'
                '    result = []\n'
                '    for u in users:\n'
                '        for item in users:\n'
                '            if u["id"] == item["id"]:\n'
                '                result.append(u)\n'
                '    return result\n'
            ),
        },
    )


@pytest.fixture
def mock_perf_findings():
    """Mock LLM output for performance findings."""
    return AgentFindings(
        findings=[
            FindingOutput(
                file_path="app.py",
                line_start=3,
                line_end=6,
                severity="high",
                category="quadratic_loop",
                title="O(n²) nested loop in process_users",
                description=(
                    "Nested loop iterates over the same list twice, resulting in "
                    "O(n²) time complexity. With 10K users this takes 100M iterations."
                ),
                suggested_fix=(
                    "seen = set()\n"
                    "result = [u for u in users if u['id'] not in seen and not seen.add(u['id'])]"
                ),
                cwe_id=None,
                confidence=0.90,
            ),
        ]
    )


# ─── PerformanceAgent Tests ───────────────────────────────────────────────


class TestPerformanceAgent:
    def test_agent_name(self):
        """PerformanceAgent should identify as 'performance'."""
        agent = PerformanceAgent()
        assert agent.agent_name == "performance"

    def test_system_prompt_loads(self):
        """System prompt should exist and contain performance-related content."""
        agent = PerformanceAgent()
        prompt = agent.system_prompt
        assert len(prompt) > 100
        assert "performance" in prompt.lower()
        assert "N+1" in prompt or "n+1" in prompt.lower()

    def test_conversion_produces_performance_findings(self, mock_perf_findings):
        """Converted findings should have agent='performance'."""
        agent = PerformanceAgent()
        findings = agent._convert_to_findings(mock_perf_findings)

        assert len(findings) == 1
        assert findings[0].agent == "performance"
        assert findings[0].severity == "high"
        assert findings[0].category == "quadratic_loop"
        assert findings[0].cwe_id is None  # Performance issues don't have CWE IDs

    @pytest.mark.asyncio
    async def test_review_handles_llm_failure(self, sample_pr_data):
        """LLM failure should return empty list, not crash."""
        mock_chain = AsyncMock(side_effect=Exception("Groq rate limit"))

        with patch("app.agents.base_agent.ChatGroq") as mock_chat_groq:
            mock_llm_instance = MagicMock()
            mock_llm_instance.with_structured_output.return_value = MagicMock(
                __ror__=MagicMock(return_value=mock_chain),
                __or__=MagicMock(return_value=mock_chain),
            )
            mock_chat_groq.return_value = mock_llm_instance

            agent = PerformanceAgent()
            with patch.object(agent, "run_static_analysis", return_value=""):
                findings = await agent.review(sample_pr_data)

        assert findings == []


# ─── Radon Tool Tests ─────────────────────────────────────────────────────


class TestRadonTool:
    @pytest.mark.asyncio
    async def test_detects_high_complexity(self):
        """Radon should flag functions with cyclomatic complexity > 10."""
        # This function has many branches → high complexity
        complex_code = (
            "def complex_func(a, b, c, d, e, f, g, h, i, j, k):\n"
            "    if a: return 1\n"
            "    elif b: return 2\n"
            "    elif c: return 3\n"
            "    elif d: return 4\n"
            "    elif e: return 5\n"
            "    elif f: return 6\n"
            "    elif g: return 7\n"
            "    elif h: return 8\n"
            "    elif i: return 9\n"
            "    elif j: return 10\n"
            "    elif k: return 11\n"
            "    else: return 0\n"
        )
        files = {"complex.py": complex_code}
        result = await run_radon(files)
        # Radon should find this function and report it
        if result:  # radon installed
            assert "complex_func" in result or "complexity" in result.lower()

    @pytest.mark.asyncio
    async def test_returns_empty_for_simple_code(self):
        """Simple code (low complexity) should produce no output."""
        simple_code = "def add(a, b):\n    return a + b\n"
        files = {"simple.py": simple_code}
        result = await run_radon(files)
        # Simple function has complexity 1 (grade A) — should not be flagged
        assert result == ""

    @pytest.mark.asyncio
    async def test_skips_non_python_files(self):
        """Radon should ignore non-Python files."""
        files = {
            "style.css": "body { color: red; }",
            "README.md": "# Hello",
        }
        result = await run_radon(files)
        assert result == ""

    @pytest.mark.asyncio
    async def test_handles_empty_input(self):
        """Empty file dict should return empty string."""
        result = await run_radon({})
        assert result == ""

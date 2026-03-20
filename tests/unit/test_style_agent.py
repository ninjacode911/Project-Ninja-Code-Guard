"""
Tests for the Style Agent and Ruff linter tool.

These tests verify:
1. StyleAgent identifies as "style" and loads its prompt
2. Ruff correctly detects lint issues (unused imports, etc.)
3. Ruff handles non-Python files and empty input gracefully
4. The agent converts LLM output to Finding objects correctly
5. The agent handles LLM failures without crashing

Ruff is an extremely fast Python linter written in Rust. It replaces
flake8, isort, pycodestyle, and dozens of other tools. Tests use REAL
Ruff execution on synthetic code — it runs in milliseconds.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base_agent import AgentFindings, FindingOutput
from app.agents.style_agent import StyleAgent
from app.github.client import PRData
from app.tools.linter_tool import run_ruff

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_pr_data():
    """PRData with code that has style issues."""
    return PRData(
        repo_full_name="ninjacode911/codeguard-test",
        pr_number=4,
        commit_sha="abc123",
        title="Add utility function",
        diff=(
            'diff --git a/util.py b/util.py\n'
            '+import os\n'
            '+import json\n'
            '+\n'
            '+def x(a, b):\n'
            '+    t = []\n'
            '+    for i in a:\n'
            '+        if i in b:\n'
            '+            t.append(i)\n'
            '+    return t\n'
        ),
        changed_files=[{"filename": "util.py", "status": "added"}],
        file_contents={
            "util.py": (
                'import os\n'
                'import json\n'
                '\n'
                'def x(a, b):\n'
                '    t = []\n'
                '    for i in a:\n'
                '        if i in b:\n'
                '            t.append(i)\n'
                '    return t\n'
            ),
        },
    )


@pytest.fixture
def mock_style_findings():
    """Mock LLM output for style findings."""
    return AgentFindings(
        findings=[
            FindingOutput(
                file_path="util.py",
                line_start=1,
                line_end=1,
                severity="low",
                category="unused_import",
                title="Unused import 'os'",
                description="The 'os' module is imported but never used in the file.",
                suggested_fix="Remove the import: delete 'import os'",
                cwe_id=None,
                confidence=0.95,
            ),
            FindingOutput(
                file_path="util.py",
                line_start=4,
                line_end=9,
                severity="medium",
                category="naming",
                title="Non-descriptive function name 'x'",
                description=(
                    "Function name 'x' doesn't describe what the function does. "
                    "It computes the intersection of two lists."
                ),
                suggested_fix="def find_common_elements(list_a, list_b):",
                cwe_id=None,
                confidence=0.85,
            ),
        ]
    )


# ─── StyleAgent Tests ─────────────────────────────────────────────────────


class TestStyleAgent:
    def test_agent_name(self):
        """StyleAgent should identify as 'style'."""
        agent = StyleAgent()
        assert agent.agent_name == "style"

    def test_system_prompt_loads(self):
        """System prompt should exist and contain style-related content."""
        agent = StyleAgent()
        prompt = agent.system_prompt
        assert len(prompt) > 100
        assert "style" in prompt.lower() or "maintainability" in prompt.lower()
        assert "naming" in prompt.lower()

    def test_conversion_produces_style_findings(self, mock_style_findings):
        """Converted findings should have agent='style'."""
        agent = StyleAgent()
        findings = agent._convert_to_findings(mock_style_findings)

        assert len(findings) == 2
        assert all(f.agent == "style" for f in findings)
        assert findings[0].severity == "low"
        assert findings[0].category == "unused_import"
        assert findings[1].severity == "medium"
        assert findings[1].category == "naming"
        assert findings[0].cwe_id is None  # Style issues don't have CWE IDs
        assert findings[1].cwe_id is None

    @pytest.mark.asyncio
    async def test_review_handles_llm_failure(self, sample_pr_data):
        """LLM failure should return empty list, not crash."""
        mock_chain = AsyncMock(side_effect=Exception("Groq API timeout"))

        with patch("app.agents.base_agent.ChatGroq") as mock_chat_groq:
            mock_llm_instance = MagicMock()
            mock_llm_instance.with_structured_output.return_value = MagicMock(
                __ror__=MagicMock(return_value=mock_chain),
                __or__=MagicMock(return_value=mock_chain),
            )
            mock_chat_groq.return_value = mock_llm_instance

            agent = StyleAgent()
            with patch.object(agent, "run_static_analysis", return_value=""):
                findings = await agent.review(sample_pr_data)

        assert findings == []


# ─── Ruff Tool Tests ──────────────────────────────────────────────────────


class TestRuffTool:
    @pytest.mark.asyncio
    async def test_detects_unused_imports(self):
        """Ruff should detect unused imports (F401)."""
        code_with_unused = (
            "import os\n"
            "import json\n"
            "\n"
            "def hello():\n"
            "    return 'world'\n"
        )
        files = {"app.py": code_with_unused}
        result = await run_ruff(files)
        if result:  # ruff installed
            assert "F401" in result  # Unused import rule code
            assert "os" in result or "json" in result

    @pytest.mark.asyncio
    async def test_clean_code_returns_empty(self):
        """Code with no lint issues should return empty string."""
        clean_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        files = {"clean.py": clean_code}
        result = await run_ruff(files)
        assert result == ""

    @pytest.mark.asyncio
    async def test_skips_non_python_files(self):
        """Ruff should ignore non-Python files."""
        files = {
            "index.html": "<h1>Hello</h1>",
            "style.css": "body { color: red; }",
        }
        result = await run_ruff(files)
        assert result == ""

    @pytest.mark.asyncio
    async def test_handles_empty_input(self):
        """Empty file dict should return empty string."""
        result = await run_ruff({})
        assert result == ""

    @pytest.mark.asyncio
    async def test_caps_output_at_20_issues(self):
        """Output should cap at 20 issues to avoid prompt bloat."""
        # Generate code with many unused imports
        many_imports = "\n".join(f"import module_{i}" for i in range(30))
        code = many_imports + "\n\ndef main():\n    pass\n"
        files = {"many_imports.py": code}
        result = await run_ruff(files)
        if result:
            # Should mention capping
            lines = result.strip().split("\n")
            # The output should not have more than ~22 lines (header + 20 issues + "and X more")
            assert len(lines) <= 25

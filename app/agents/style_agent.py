"""
Style & Maintainability Agent
===============================

Reviews code for readability, naming quality, documentation, test coverage,
and architectural consistency. Uses Ruff for mechanical lint checks and the
LLM for deeper maintainability analysis.

Same architecture as SecurityAgent and PerformanceAgent.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from app.agents.base_agent import BaseAgent
from app.github.client import PRData
from app.tools.linter_tool import run_ruff

logger = structlog.get_logger()


class StyleAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "style"

    @property
    def system_prompt(self) -> str:
        prompt_path = (
            Path(__file__).resolve().parent.parent.parent
            / "prompts"
            / "style_system.md"
        )
        return prompt_path.read_text(encoding="utf-8")

    async def run_static_analysis(self, pr_data: PRData) -> str:
        """Run Ruff linter on changed Python files."""
        ruff_output = await run_ruff(pr_data.file_contents)
        return ruff_output if ruff_output else ""

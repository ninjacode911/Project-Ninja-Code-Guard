"""
Performance Agent
==================

Evaluates code for computational efficiency, memory usage, and scalability.
Uses radon for complexity metrics and the LLM for semantic analysis of
query patterns, I/O operations, and algorithmic efficiency.

Same architecture as SecurityAgent — inherits from BaseAgent, overrides
only agent_name, system_prompt, and run_static_analysis().
"""

from __future__ import annotations

from pathlib import Path

import structlog

from app.agents.base_agent import BaseAgent
from app.github.client import PRData
from app.tools.radon_tool import run_radon

logger = structlog.get_logger()


class PerformanceAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "performance"

    @property
    def system_prompt(self) -> str:
        prompt_path = (
            Path(__file__).resolve().parent.parent.parent
            / "prompts"
            / "performance_system.md"
        )
        return prompt_path.read_text(encoding="utf-8")

    async def run_static_analysis(self, pr_data: PRData) -> str:
        """Run radon complexity analysis on changed Python files."""
        radon_output = await run_radon(pr_data.file_contents)
        return radon_output if radon_output else ""

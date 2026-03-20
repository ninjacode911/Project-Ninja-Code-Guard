"""
Security Agent
===============

The Security Agent acts as a senior application security engineer (AppSec).
It reviews every changed line through the lens of exploitability, data exposure,
and authentication integrity.

Architecture:
1. Run static analysis tools (Bandit + detect-secrets) on changed files
2. Combine static results with PR diff and full file contents
3. Send everything to Groq's Llama-3.1-70B with a security-focused system prompt
4. LLM produces structured JSON findings with CWE IDs and suggested fixes

Why both static tools AND an LLM?

Static tools (Bandit):
  ✅ Fast, deterministic, zero false negatives for known patterns
  ✅ Free — no API cost
  ❌ Can't understand context (doesn't know if input is already sanitized)
  ❌ Only catches patterns it has rules for

LLM (Llama-3.1-70B):
  ✅ Understands context, intent, data flow between functions
  ✅ Can catch novel vulnerability patterns
  ✅ Provides natural language explanations and fixes
  ❌ Can hallucinate findings (false positives)
  ❌ Costs API calls (though Groq's free tier is generous)

Together: static tools provide HIGH-CONFIDENCE anchors, the LLM provides DEPTH.
The Synthesizer (Week 7) will merge and deduplicate their outputs.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from app.agents.base_agent import BaseAgent
from app.github.client import PRData
from app.tools.bandit_tool import run_bandit
from app.tools.detect_secrets_tool import run_detect_secrets

logger = structlog.get_logger()


class SecurityAgent(BaseAgent):
    """
    Security-focused code review agent.

    Inherits from BaseAgent which provides:
    - Groq LLM client (ChatGroq with Llama-3.1-70B)
    - Structured output parsing (with_structured_output)
    - Error handling and timing
    - The review() method that orchestrates the flow

    This class only needs to provide:
    - agent_name: "security"
    - system_prompt: loaded from prompts/security_system.md
    - run_static_analysis(): runs Bandit + detect-secrets
    """

    @property
    def agent_name(self) -> str:
        return "security"

    @property
    def system_prompt(self) -> str:
        """
        Load the system prompt from the Markdown file.

        We store prompts as separate files (not inline strings) because:
        1. They're long (50+ lines) — inline strings clutter the code
        2. They change frequently during prompt tuning (Week 9)
        3. Non-engineers (product managers) can review/edit them
        4. Git diff shows prompt changes clearly
        """
        prompt_path = Path(__file__).resolve().parent.parent.parent / "prompts" / "security_system.md"
        return prompt_path.read_text(encoding="utf-8")

    async def run_static_analysis(self, pr_data: PRData) -> str:
        """
        Run security-specific static analysis tools.

        We run Bandit and detect-secrets in sequence (not parallel) because:
        1. Each takes <5 seconds — parallelism gains are minimal
        2. They both write to temp dirs — simpler to keep sequential
        3. If one fails, the other still runs (independent try/except in each tool)

        The results are concatenated into a single string that gets injected
        into the LLM prompt. The LLM uses these as high-confidence signals
        to anchor its own analysis.
        """
        results = []

        # Run Bandit (Python security linter)
        bandit_output = await run_bandit(pr_data.file_contents)
        if bandit_output:
            results.append(bandit_output)

        # Run detect-secrets (credential scanner)
        secrets_output = await run_detect_secrets(pr_data.file_contents)
        if secrets_output:
            results.append(secrets_output)

        return "\n\n".join(results) if results else ""

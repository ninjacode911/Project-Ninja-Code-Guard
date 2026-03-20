"""
Base Agent Interface
=====================

All domain agents (Security, Performance, Style) inherit from this base class.
It provides shared infrastructure:

1. **Groq LLM client** — ChatGroq configured with Llama-3.1-70B
2. **Structured output** — LLM returns typed Finding objects, not raw text
3. **Error handling** — graceful fallback if the LLM call fails
4. **Timing** — measures how long each agent takes (for latency metrics)

Design pattern: Template Method
- The base class defines the algorithm skeleton (receive diff → run tools → call LLM → return findings)
- Subclasses override specific steps (system_prompt, run_static_tools)
- This prevents code duplication across 3 agents that follow the same flow

Why LangChain?
- Provides a unified interface across LLM providers (Groq, Gemini, OpenAI)
- If Groq goes down, we swap to Gemini by changing one line
- Structured output parsing is built in (with_structured_output)
- Prompt templates with variable substitution
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from app.config import settings
from app.github.client import PRData
from app.models.findings import Finding

logger = structlog.get_logger()


class AgentFindings(BaseModel):
    """
    Schema for the LLM's structured output.

    By wrapping findings in a Pydantic model, we can use LangChain's
    `with_structured_output()` which constrains the LLM to return
    valid JSON matching this exact schema. No more parsing raw text!

    How with_structured_output() works under the hood:
    1. It adds the JSON schema to the system prompt
    2. It sets response_format to JSON mode (if the model supports it)
    3. It validates the response against the schema
    4. If validation fails, it retries (configurable)
    """

    findings: list[FindingOutput] = Field(
        default_factory=list,
        description="List of security/performance/style findings",
    )


class FindingOutput(BaseModel):
    """
    The schema we ask the LLM to produce for each finding.

    This is slightly different from our internal Finding model because:
    - The LLM doesn't know which agent it is (we add that after)
    - We give the LLM freedom on field names that match its training
    - We validate and convert to our Finding model post-LLM

    Note: This class is defined BEFORE AgentFindings because Python
    needs it to exist when AgentFindings references it. But Pydantic
    handles forward references with model_rebuild().
    """

    file_path: str = Field(description="Path to the file (e.g., 'app.py')")
    line_start: int = Field(description="Starting line number of the issue")
    line_end: int = Field(description="Ending line number of the issue")
    severity: str = Field(description="One of: critical, high, medium, low")
    category: str = Field(description="Issue category (e.g., 'sql_injection', 'hardcoded_secret')")
    title: str = Field(description="Short one-line title of the finding")
    description: str = Field(description="Detailed explanation of the issue and its impact")
    suggested_fix: str = Field(default="", description="Corrected code snippet")
    cwe_id: str | None = Field(default=None, description="CWE ID if applicable (e.g., 'CWE-89')")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")


# Rebuild the model to resolve the forward reference
AgentFindings.model_rebuild()


class BaseAgent(ABC):
    """
    Abstract base class for all domain agents.

    Subclasses must implement:
    - agent_name: which agent this is ("security", "performance", "style")
    - system_prompt: the detailed system prompt for the LLM
    - run_static_analysis(): optional static tools (Bandit, Semgrep, etc.)

    Usage:
        agent = SecurityAgent()
        findings = await agent.review(pr_data)
    """

    def __init__(self):
        """
        Initialize the LLM client.

        ChatGroq connects to Groq's API which runs Llama-3.1-70B at
        500+ tokens/sec — the fastest open-source LLM inference available.
        This speed is critical: we need each agent to complete in 3-8 seconds
        so the full review stays under 15 seconds.

        Temperature=0.1: We want nearly deterministic output. Code review
        should be consistent — the same code should get the same findings.
        A small temperature (not 0) allows slight variation to avoid
        getting stuck in repetitive patterns.
        """
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=settings.groq_api_key,
            temperature=0.1,
            max_tokens=4096,
        )

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """The agent identifier: 'security', 'performance', or 'style'."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The full system prompt for this agent."""
        ...

    async def run_static_analysis(self, pr_data: PRData) -> str:
        """
        Run static analysis tools on the PR files.

        Override in subclasses to run agent-specific tools:
        - SecurityAgent: Bandit + detect-secrets
        - PerformanceAgent: radon + AST analysis
        - StyleAgent: Ruff/pylint

        Returns a string summary of tool findings to include in the LLM prompt.
        Default: no static analysis (LLM-only review).
        """
        return ""

    def _build_prompt(self) -> ChatPromptTemplate:
        """
        Build the LangChain prompt template.

        ChatPromptTemplate.from_messages() creates a multi-turn prompt:
        - ("system", ...) → the system message (agent persona + instructions)
        - ("human", ...) → the user message (the actual PR data to review)

        Variables in {curly_braces} are substituted at runtime with .ainvoke().
        """
        return ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", (
                "## PR Diff\n"
                "```diff\n{diff}\n```\n\n"
                "## Changed File Contents\n"
                "{file_contents}\n\n"
                "## Static Analysis Results\n"
                "{static_analysis}\n\n"
                "{rag_context}\n\n"
                "Analyze this PR and return your findings as structured JSON."
            )),
        ])

    def _convert_to_findings(self, agent_output: AgentFindings) -> list[Finding]:
        """
        Convert the LLM's output to our internal Finding model.

        This adds the agent_name field and validates/clamps values:
        - Severity is lowercased and validated
        - Confidence is clamped to [0.0, 1.0]
        - Invalid findings are skipped (not crashed on)
        """
        findings = []
        for f in agent_output.findings:
            try:
                severity = f.severity.lower().strip()
                if severity not in ("critical", "high", "medium", "low"):
                    severity = "medium"  # Default for ambiguous severity

                confidence = max(0.0, min(1.0, f.confidence))

                finding = Finding(
                    agent=self.agent_name,
                    file_path=f.file_path,
                    line_start=f.line_start,
                    line_end=f.line_end,
                    severity=severity,
                    category=f.category,
                    title=f.title,
                    description=f.description,
                    suggested_fix=f.suggested_fix,
                    cwe_id=f.cwe_id,
                    confidence=confidence,
                )
                findings.append(finding)
            except Exception as e:
                logger.warning(
                    "Skipping malformed finding",
                    agent=self.agent_name,
                    error=str(e),
                )
        return findings

    def _format_file_contents(self, file_contents: dict[str, str]) -> str:
        """
        Format file contents for the LLM prompt.

        Each file is wrapped in a code block with its path as a header.
        We truncate very long files to stay within LLM context limits.
        Groq's Llama-3.1-70B has 128K context, so we have plenty of room
        for typical PRs, but we cap each file at 500 lines to be safe.
        """
        parts = []
        for filepath, content in file_contents.items():
            lines = content.split("\n")
            if len(lines) > 500:
                content = "\n".join(lines[:500]) + "\n... (truncated)"
            parts.append(f"### {filepath}\n```\n{content}\n```")
        return "\n\n".join(parts) if parts else "No file contents available."

    async def review(self, pr_data: PRData, rag_context: str = "") -> list[Finding]:
        """
        Main entry point: review a PR and return findings.

        This is the Template Method:
        1. Run static analysis tools (subclass-specific)
        2. Build the prompt with diff + files + tool output + RAG context
        3. Call the LLM with structured output
        4. Convert to Finding objects
        5. Log timing and return

        If the LLM call fails, we return an empty list rather than crashing
        the entire pipeline. The other agents can still contribute findings.

        Args:
            pr_data: The PR diff, file contents, and metadata
            rag_context: Optional RAG context from ChromaDB (related code chunks)
        """
        start_time = time.time()

        try:
            # Step 1: Run static analysis tools
            static_results = await self.run_static_analysis(pr_data)

            # Step 2: Build the prompt
            prompt = self._build_prompt()

            # Step 3: Create the structured output chain
            structured_llm = self.llm.with_structured_output(AgentFindings)
            chain = prompt | structured_llm

            # Step 4: Call the LLM
            result = await chain.ainvoke({
                "diff": pr_data.diff[:15000],  # Cap diff size for token limits
                "file_contents": self._format_file_contents(pr_data.file_contents),
                "static_analysis": static_results or "No static analysis results.",
                "rag_context": rag_context or "",
            })

            # Step 5: Convert to Finding objects
            findings = self._convert_to_findings(result)

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Agent review completed",
                agent=self.agent_name,
                findings_count=len(findings),
                elapsed_ms=elapsed_ms,
            )

            return findings

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Agent review failed",
                agent=self.agent_name,
                error=str(e),
                elapsed_ms=elapsed_ms,
            )
            return []  # Don't crash the pipeline — other agents can still work

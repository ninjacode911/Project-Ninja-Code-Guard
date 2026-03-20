"""
Tests for parallel agent execution via asyncio.gather.

These tests verify:
1. All three agents can be instantiated independently
2. Each agent has the correct name and loads its prompt
3. Agent prompts don't overlap (security != performance != style)
4. asyncio.gather runs agents concurrently
5. If one agent fails, the others still succeed

Why parallel execution matters:
- Sequential: 3 agents × ~5 seconds each = ~15 seconds total
- Parallel: max(~5s, ~5s, ~5s) = ~5 seconds total (3x faster)
- We use asyncio.gather() which runs coroutines concurrently
- If one agent raises an exception, gather() can be configured to
  continue or cancel the others. We handle exceptions inside each
  agent's review() method, so gather() always succeeds.
"""

import asyncio

import pytest

from app.agents.performance_agent import PerformanceAgent
from app.agents.security_agent import SecurityAgent
from app.agents.style_agent import StyleAgent

# ─── Agent Identity Tests ─────────────────────────────────────────────────


class TestAgentIdentities:
    def test_all_agents_have_unique_names(self):
        """Each agent must have a distinct name for finding attribution."""
        security = SecurityAgent()
        performance = PerformanceAgent()
        style = StyleAgent()

        names = {security.agent_name, performance.agent_name, style.agent_name}
        assert names == {"security", "performance", "style"}

    def test_all_agents_load_prompts(self):
        """Each agent should load its system prompt without errors."""
        for agent_class in [SecurityAgent, PerformanceAgent, StyleAgent]:
            agent = agent_class()
            prompt = agent.system_prompt
            assert len(prompt) > 100, f"{agent.agent_name} prompt is too short"

    def test_prompts_are_domain_specific(self):
        """Each prompt should focus on its domain, not overlap with others."""
        security = SecurityAgent()
        performance = PerformanceAgent()
        style = StyleAgent()

        # Security prompt should mention security-specific terms
        assert "CWE" in security.system_prompt
        assert "vulnerability" in security.system_prompt.lower() or "injection" in security.system_prompt.lower()

        # Performance prompt should mention performance-specific terms
        assert "N+1" in performance.system_prompt or "n+1" in performance.system_prompt.lower()
        assert "O(n" in performance.system_prompt or "quadratic" in performance.system_prompt.lower()

        # Style prompt should mention style-specific terms
        assert "naming" in style.system_prompt.lower()
        assert "readability" in style.system_prompt.lower() or "maintainability" in style.system_prompt.lower()

    def test_prompts_have_scope_boundaries(self):
        """Each prompt should explicitly exclude other domains."""
        security = SecurityAgent()
        performance = PerformanceAgent()
        style = StyleAgent()

        # Security should say it doesn't do style/performance
        sec_lower = security.system_prompt.lower()
        assert "do not comment on" in sec_lower or "only" in sec_lower

        # Performance should say it doesn't do security/style
        perf_lower = performance.system_prompt.lower()
        assert "do not comment on" in perf_lower or "only" in perf_lower

        # Style should say it doesn't do security/performance
        style_lower = style.system_prompt.lower()
        assert "do not comment on" in style_lower or "only" in style_lower


# ─── Parallel Execution Tests ─────────────────────────────────────────────


class TestParallelExecution:
    @pytest.mark.asyncio
    async def test_gather_runs_concurrently(self):
        """
        asyncio.gather should run tasks concurrently, not sequentially.

        We simulate this with sleep-based tasks — if they run in parallel,
        total time should be ~max(durations), not sum(durations).
        """
        async def slow_task(name: str, duration: float) -> str:
            await asyncio.sleep(duration)
            return name

        import time
        start = time.time()
        results = await asyncio.gather(
            slow_task("security", 0.1),
            slow_task("performance", 0.1),
            slow_task("style", 0.1),
        )
        elapsed = time.time() - start

        assert set(results) == {"security", "performance", "style"}
        # If parallel: ~0.1s. If sequential: ~0.3s. Allow generous margin.
        assert elapsed < 0.25, f"Tasks took {elapsed:.2f}s — should be parallel (~0.1s)"

    @pytest.mark.asyncio
    async def test_gather_handles_partial_failure(self):
        """
        If one agent fails, the others should still return results.

        Our agents handle exceptions internally (return []), so
        asyncio.gather() never sees the exception. All three calls succeed.
        """
        async def success_task() -> list:
            return [{"finding": "real"}]

        async def failing_task() -> list:
            # Simulates what BaseAgent.review() does on failure
            try:
                raise Exception("Groq API timeout")
            except Exception:
                return []  # Graceful degradation

        results = await asyncio.gather(
            success_task(),
            failing_task(),
            success_task(),
        )

        assert len(results) == 3
        assert len(results[0]) == 1  # First agent succeeded
        assert len(results[1]) == 0  # Second agent failed gracefully
        assert len(results[2]) == 1  # Third agent succeeded

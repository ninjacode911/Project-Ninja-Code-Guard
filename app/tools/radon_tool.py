"""
Radon Complexity Analysis Tool
================================

Radon measures cyclomatic complexity — the number of independent execution paths
through a function. Higher complexity = more branches = harder to test and maintain,
AND often correlates with performance issues (deeply nested conditionals often
indicate O(n²) or worse algorithms).

Complexity grades:
  A (1-5):   Simple, low risk
  B (6-10):  Moderate complexity
  C (11-15): High complexity — consider refactoring
  D (16-20): Very high — likely performance and maintenance issues
  E (21-25): Extremely complex
  F (26+):   Unmaintainable

We report functions with complexity grade C or worse (>10) to the Performance Agent.
The agent uses this as a signal to look deeper at those functions for algorithmic issues.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()


async def run_radon(file_contents: dict[str, str]) -> str:
    """
    Run radon cyclomatic complexity analysis on Python files.

    Returns a formatted string summarizing high-complexity functions.
    """
    python_files = {
        path: content
        for path, content in file_contents.items()
        if path.endswith(".py")
    }

    if not python_files:
        return ""

    try:
        with tempfile.TemporaryDirectory(prefix="ninjacg_radon_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            for filepath, content in python_files.items():
                file_path = tmpdir_path / filepath
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

            # Run radon cc (cyclomatic complexity) with JSON output
            # -j: JSON output
            # -n C: only show grade C or worse (complexity > 10)
            result = subprocess.run(
                ["radon", "cc", "-j", "-n", "C", str(tmpdir_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if not result.stdout.strip() or result.stdout.strip() == "{}":
                return ""

            radon_output = json.loads(result.stdout)

            # Collect high-complexity functions
            findings = []
            for file_path, functions in radon_output.items():
                try:
                    relative = str(Path(file_path).relative_to(tmpdir)).replace("\\", "/")
                except ValueError:
                    relative = Path(file_path).name

                for func in functions:
                    if not isinstance(func, dict):
                        continue
                    name = func.get("name", "unknown")
                    complexity = func.get("complexity", 0)
                    rank = func.get("rank", "?")
                    lineno = func.get("lineno", 0)
                    findings.append(
                        f"- {relative}:{lineno} — `{name}()` complexity={complexity} (grade {rank})"
                    )

            if not findings:
                return ""

            summary = (
                f"Radon complexity analysis found {len(findings)} high-complexity function(s):\n"
                + "\n".join(findings)
            )
            logger.info("Radon analysis complete", high_complexity_count=len(findings))
            return summary

    except FileNotFoundError:
        logger.warning("radon not found in PATH — skipping complexity analysis")
        return ""
    except Exception as e:
        logger.warning("Radon analysis failed", error=str(e))
        return ""

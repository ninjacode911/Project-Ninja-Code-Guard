"""
Linter Tool (Ruff)
===================

Ruff is an extremely fast Python linter written in Rust. It replaces
flake8, isort, pycodestyle, and dozens of other tools in a single binary.
It runs 10-100x faster than traditional Python linters.

What Ruff catches:
- Unused imports (F401)
- Undefined names (F821)
- Unused variables (F841)
- Import ordering issues (I001)
- Unnecessary f-strings (F541)
- Bare except clauses (E722)
- And 800+ other rules

We run Ruff on the changed files and feed the output to the Style Agent
as additional context. The LLM then combines Ruff's mechanical findings
with its own understanding of readability and maintainability.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()


async def run_ruff(file_contents: dict[str, str]) -> str:
    """
    Run Ruff linter on Python files.

    Returns a formatted string of linting issues.
    """
    python_files = {
        path: content
        for path, content in file_contents.items()
        if path.endswith(".py")
    }

    if not python_files:
        return ""

    try:
        with tempfile.TemporaryDirectory(prefix="ninjacg_ruff_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            for filepath, content in python_files.items():
                file_path = tmpdir_path / filepath
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

            # Run ruff check with JSON output
            # --output-format json: machine-parseable output
            # --select ALL: enable all rules (we want comprehensive feedback)
            # --ignore E501: skip line-length (too noisy, not actionable)
            result = subprocess.run(
                [
                    "ruff", "check",
                    str(tmpdir_path),
                    "--output-format", "json",
                    "--select", "F,E,W,I,N,UP,B,A,SIM,RET,ARG",
                    "--ignore", "E501,E402",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Ruff exit code 1 means issues found (not an error)
            if not result.stdout.strip() or result.stdout.strip() == "[]":
                return ""

            issues = json.loads(result.stdout)

            if not issues:
                return ""

            # Format findings
            summary_lines = [f"Ruff linter found {len(issues)} issue(s):\n"]

            for issue in issues[:20]:  # Cap at 20 to avoid prompt bloat
                code = issue.get("code", "?")
                message = issue.get("message", "")
                filename = issue.get("filename", "")
                line = issue.get("location", {}).get("row", 0)

                try:
                    relative = str(Path(filename).relative_to(tmpdir)).replace("\\", "/")
                except ValueError:
                    relative = Path(filename).name

                summary_lines.append(f"- [{code}] {relative}:{line} — {message}")

            if len(issues) > 20:
                summary_lines.append(f"  ... and {len(issues) - 20} more issues")

            summary = "\n".join(summary_lines)
            logger.info("Ruff analysis complete", issues_count=len(issues))
            return summary

    except FileNotFoundError:
        logger.warning("ruff not found in PATH — skipping lint analysis")
        return ""
    except Exception as e:
        logger.warning("Ruff analysis failed", error=str(e))
        return ""

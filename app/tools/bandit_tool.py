"""
Bandit Static Analysis Tool
=============================

Bandit is an open-source Python security linter. It parses Python code into an
Abstract Syntax Tree (AST) and checks each node against a set of security rules.

What Bandit catches:
- SQL injection patterns (string formatting in SQL calls)
- Use of eval(), exec(), os.system() (command injection risk)
- Hardcoded passwords and bind addresses
- Use of insecure hash functions (MD5, SHA1)
- Insecure temp file creation
- SSL/TLS verification disabled (requests.get(verify=False))
- Use of pickle (deserialization attacks)

What Bandit CANNOT catch:
- Business logic flaws
- Missing authentication/authorization
- Cross-file data flow (it analyzes one file at a time)
- Vulnerabilities in non-Python code

That's why we combine Bandit (mechanical pattern matching) with the LLM (semantic
understanding). Bandit provides high-confidence, low-noise signals that anchor the
LLM's analysis.

How it works:
1. We write the changed Python files to a temp directory
2. Run `bandit -r <dir> -f json` as a subprocess
3. Parse the JSON output into a human-readable summary
4. Feed this summary into the LLM's prompt as additional context
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()


async def run_bandit(file_contents: dict[str, str]) -> str:
    """
    Run Bandit security analysis on Python files.

    Args:
        file_contents: dict of {filepath: source_code} for changed files

    Returns:
        A formatted string summarizing Bandit's findings, suitable for
        including in an LLM prompt. Returns empty string if no Python
        files or no findings.
    """
    # Filter to only Python files — Bandit only understands Python
    python_files = {
        path: content
        for path, content in file_contents.items()
        if path.endswith(".py")
    }

    if not python_files:
        return ""

    try:
        # Create a temp directory and write the Python files there.
        # We need files on disk because Bandit operates on the filesystem.
        # tempfile.mkdtemp() creates a secure temp dir that only we can access.
        with tempfile.TemporaryDirectory(prefix="ninjacg_bandit_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            for filepath, content in python_files.items():
                # Recreate the directory structure (e.g., src/auth/login.py)
                file_path = tmpdir_path / filepath
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

            # Run Bandit as a subprocess
            # -r: recursive (scan all files in directory)
            # -f json: output as JSON (machine-parseable)
            # -ll: only report medium severity and above
            # --quiet: suppress progress bar
            result = subprocess.run(
                [
                    "bandit",
                    "-r", str(tmpdir_path),
                    "-f", "json",
                    "-ll",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=30,  # Kill if it takes too long
            )

            # Bandit exit codes:
            # 0 = no issues found
            # 1 = issues found (this is NOT an error)
            # 2+ = actual error
            if result.returncode > 1:
                logger.warning("Bandit returned error", stderr=result.stderr[:500])
                return ""

            if not result.stdout.strip():
                return ""

            # Parse the JSON output
            bandit_output = json.loads(result.stdout)
            findings = bandit_output.get("results", [])

            if not findings:
                return "Bandit static analysis: No security issues detected."

            # Format findings as a human-readable summary for the LLM
            summary_lines = [
                f"Bandit static analysis found {len(findings)} issue(s):\n"
            ]

            for i, finding in enumerate(findings, 1):
                # Map the temp file path back to the original file path
                temp_path = finding.get("filename", "")
                original_path = _map_temp_to_original(temp_path, tmpdir, python_files)

                severity = finding.get("issue_severity", "UNKNOWN")
                confidence = finding.get("issue_confidence", "UNKNOWN")
                text = finding.get("issue_text", "")
                test_id = finding.get("test_id", "")
                line_no = finding.get("line_number", 0)
                code = finding.get("code", "").strip()

                summary_lines.append(
                    f"{i}. [{severity}/{confidence}] {text}\n"
                    f"   File: {original_path}, Line: {line_no}\n"
                    f"   Test: {test_id}\n"
                    f"   Code: {code}\n"
                )

            summary = "\n".join(summary_lines)
            logger.info("Bandit analysis complete", findings_count=len(findings))
            return summary

    except subprocess.TimeoutExpired:
        logger.warning("Bandit timed out after 30 seconds")
        return ""
    except FileNotFoundError:
        # Bandit not installed — this is OK, the LLM can still analyze
        logger.warning("Bandit not found in PATH — skipping static analysis")
        return ""
    except Exception as e:
        logger.warning("Bandit analysis failed", error=str(e))
        return ""


def _map_temp_to_original(
    temp_path: str, tmpdir: str, original_files: dict[str, str]
) -> str:
    """Map a temp directory path back to the original file path."""
    try:
        # The temp path looks like: /tmp/ninjacg_bandit_xxx/src/auth/login.py
        # We need to strip the tmpdir prefix to get: src/auth/login.py
        relative = str(Path(temp_path).relative_to(tmpdir))
        # Normalize path separators
        relative = relative.replace("\\", "/")
        # Verify it's one of our original files
        if relative in original_files:
            return relative
    except (ValueError, Exception):
        pass
    # Fallback: return the filename only
    return Path(temp_path).name

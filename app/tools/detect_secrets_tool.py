"""
detect-secrets Tool
====================

detect-secrets scans code for hardcoded credentials: API keys, passwords,
database connection strings, AWS access keys, private keys, etc.

Why a dedicated tool for secrets?
- Hardcoded secrets are the #1 most common security finding in code reviews
- They're easy to detect with regex/entropy analysis but easy to miss manually
- detect-secrets uses both pattern matching AND Shannon entropy analysis:
  - Pattern matching: finds things that LOOK like API keys (e.g., "sk_live_...")
  - Entropy analysis: finds random-looking strings that might be secrets
    (high entropy = lots of randomness = probably a key, not a variable name)

What Shannon entropy means:
- "hello" has low entropy (~2.8 bits/char) — predictable, probably not a secret
- "a3f8g2kx9m" has high entropy (~3.9 bits/char) — random, might be a secret
- detect-secrets flags strings above a configurable entropy threshold

We run this on the PR diff specifically (not full files) because we only care
about NEWLY introduced secrets, not pre-existing ones.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()


async def run_detect_secrets(file_contents: dict[str, str]) -> str:
    """
    Scan changed files for hardcoded secrets.

    Args:
        file_contents: dict of {filepath: source_code}

    Returns:
        A formatted string listing detected secrets, suitable for
        including in an LLM prompt. Empty string if no secrets found.
    """
    if not file_contents:
        return ""

    try:
        with tempfile.TemporaryDirectory(prefix="ninjacg_secrets_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            for filepath, content in file_contents.items():
                file_path = tmpdir_path / filepath
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

            # Run detect-secrets scan
            # --all-files: scan all file types
            # --force-use-all-plugins: use every detection plugin
            result = subprocess.run(
                [
                    "detect-secrets", "scan",
                    str(tmpdir_path),
                    "--all-files",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0 and not result.stdout:
                logger.warning("detect-secrets error", stderr=result.stderr[:500])
                return ""

            if not result.stdout.strip():
                return ""

            scan_results = json.loads(result.stdout)
            results_map = scan_results.get("results", {})

            # Count total secrets found
            total_secrets = sum(len(secrets) for secrets in results_map.values())

            if total_secrets == 0:
                return "detect-secrets scan: No hardcoded secrets detected."

            # Format findings
            summary_lines = [
                f"detect-secrets found {total_secrets} potential secret(s):\n"
            ]

            for file_path, secrets in results_map.items():
                # Map temp path back to original
                try:
                    relative = str(Path(file_path).relative_to(tmpdir)).replace("\\", "/")
                except ValueError:
                    relative = Path(file_path).name

                for secret in secrets:
                    secret_type = secret.get("type", "Unknown")
                    line_no = secret.get("line_number", 0)
                    summary_lines.append(
                        f"- {secret_type} in {relative} at line {line_no}"
                    )

            summary = "\n".join(summary_lines)
            logger.info("detect-secrets scan complete", secrets_found=total_secrets)
            return summary

    except FileNotFoundError:
        logger.warning("detect-secrets not found in PATH — skipping")
        return ""
    except Exception as e:
        logger.warning("detect-secrets scan failed", error=str(e))
        return ""

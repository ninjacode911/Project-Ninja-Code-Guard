"""
Evaluation Harness
===================

Runs the Ninja Code Guard pipeline against a set of test PRs with
known issues (ground truth) and measures precision, recall, and latency.

Usage:
    python -m tests.eval.run_eval

Dataset format (JSON files in tests/eval/dataset/):
    {
        "pr_id": "sql_injection_basic",
        "diff": "...",
        "file_contents": {"app.py": "..."},
        "expected_findings": [
            {"file_path": "app.py", "line_start": 5, "category": "sql_injection"},
        ]
    }
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from tests.eval.metrics import EvalResult, EvalSummary


async def evaluate_single_pr(test_case: dict) -> EvalResult:
    """
    Run the pipeline on one test PR and compare against ground truth.

    A finding is considered a true positive if it matches an expected
    finding on the same file_path and within 3 lines of the expected line.
    """
    from app.agents.performance_agent import PerformanceAgent
    from app.agents.security_agent import SecurityAgent
    from app.agents.style_agent import StyleAgent
    from app.agents.synthesizer import synthesize
    from app.github.client import PRData

    pr_data = PRData(
        repo_full_name="eval/test",
        pr_number=0,
        commit_sha="eval",
        title=test_case.get("pr_id", "eval"),
        diff=test_case["diff"],
        changed_files=[],
        file_contents=test_case.get("file_contents", {}),
    )

    start = time.time()

    # Run all agents
    security = SecurityAgent()
    performance = PerformanceAgent()
    style = StyleAgent()

    sec_findings, perf_findings, style_findings = await asyncio.gather(
        security.review(pr_data),
        performance.review(pr_data),
        style.review(pr_data),
    )

    review = synthesize(sec_findings, perf_findings, style_findings)
    elapsed_ms = int((time.time() - start) * 1000)

    # Compare against ground truth
    expected = test_case.get("expected_findings", [])
    actual = review.findings

    matched_expected = set()
    matched_actual = set()

    for i, exp in enumerate(expected):
        for j, act in enumerate(actual):
            if j in matched_actual:
                continue
            # Match: same file, within 3 lines, same category
            if (
                act.file_path == exp["file_path"]
                and abs(act.line_start - exp["line_start"]) <= 3
                and act.category == exp.get("category", act.category)
            ):
                matched_expected.add(i)
                matched_actual.add(j)
                break

    tp = len(matched_expected)
    fp = len(actual) - len(matched_actual)
    fn = len(expected) - len(matched_expected)

    return EvalResult(
        pr_id=test_case.get("pr_id", "unknown"),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        latency_ms=elapsed_ms,
    )


async def run_evaluation():
    """Run evaluation on all test cases in the dataset directory."""
    dataset_dir = Path(__file__).parent / "dataset"

    if not dataset_dir.exists() or not list(dataset_dir.glob("*.json")):
        print("No evaluation dataset found. Create JSON files in tests/eval/dataset/")
        print("See tests/eval/run_eval.py docstring for format.")
        return

    summary = EvalSummary()

    for test_file in sorted(dataset_dir.glob("*.json")):
        print(f"Evaluating: {test_file.name}...")
        test_case = json.loads(test_file.read_text())
        result = await evaluate_single_pr(test_case)
        summary.results.append(result)
        print(f"  P={result.precision:.0%} R={result.recall:.0%} F1={result.f1:.0%} ({result.latency_ms}ms)")

    print("\n" + summary.summary())


if __name__ == "__main__":
    asyncio.run(run_evaluation())

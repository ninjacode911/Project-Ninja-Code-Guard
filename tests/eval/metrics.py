"""
Evaluation Metrics
===================

Measures the quality of Ninja Code Guard's reviews against ground truth labels.

Metrics tracked:
- Precision: % of flagged findings that are genuine issues (not false positives)
- Recall: % of known issues that were detected
- F1 Score: Harmonic mean of precision and recall
- Latency: Time from webhook to review posted (p50, p95, p99)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalResult:
    """Result of evaluating one PR against ground truth."""

    pr_id: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    latency_ms: int = 0

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total > 0 else 1.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


@dataclass
class EvalSummary:
    """Aggregate metrics across all evaluated PRs."""

    results: list[EvalResult] = field(default_factory=list)

    @property
    def avg_precision(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.precision for r in self.results) / len(self.results)

    @property
    def avg_recall(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.recall for r in self.results) / len(self.results)

    @property
    def avg_f1(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.f1 for r in self.results) / len(self.results)

    @property
    def latency_p50(self) -> int:
        if not self.results:
            return 0
        latencies = sorted(r.latency_ms for r in self.results)
        return latencies[len(latencies) // 2]

    @property
    def latency_p95(self) -> int:
        if not self.results:
            return 0
        latencies = sorted(r.latency_ms for r in self.results)
        idx = int(len(latencies) * 0.95)
        return latencies[min(idx, len(latencies) - 1)]

    def summary(self) -> str:
        return (
            f"Evaluation Summary ({len(self.results)} PRs)\n"
            f"  Precision: {self.avg_precision:.1%}\n"
            f"  Recall:    {self.avg_recall:.1%}\n"
            f"  F1 Score:  {self.avg_f1:.1%}\n"
            f"  Latency:   p50={self.latency_p50}ms, p95={self.latency_p95}ms\n"
        )

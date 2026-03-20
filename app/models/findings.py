"""Core data models for agent findings and PR reviews."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """A single finding produced by a domain agent."""

    agent: Literal["security", "performance", "style"]
    file_path: str
    line_start: int
    line_end: int
    severity: Literal["critical", "high", "medium", "low"]
    category: str
    title: str
    description: str
    suggested_fix: str = ""
    cwe_id: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class SynthesizedReview(BaseModel):
    """Final synthesized review output from the Synthesizer Agent."""

    health_score: int = Field(ge=0, le=100)
    executive_summary: str
    recommendation: Literal["approve", "request_changes", "block"]
    findings: list[Finding]
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    duration_ms: int = 0


class PRReviewRecord(BaseModel):
    """Database record for a completed PR review."""

    id: UUID = Field(default_factory=uuid4)
    repo_full_name: str
    pr_number: int
    commit_sha: str
    health_score: int = Field(ge=0, le=100)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    summary: str = ""
    findings: list[Finding] = []
    duration_ms: int = 0

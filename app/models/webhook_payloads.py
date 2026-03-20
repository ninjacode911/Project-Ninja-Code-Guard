"""GitHub webhook event payload schemas."""

from __future__ import annotations

from pydantic import BaseModel


class GitHubUser(BaseModel):
    login: str
    id: int


class GitHubRepo(BaseModel):
    id: int
    full_name: str
    private: bool
    default_branch: str = "main"


class PullRequestHead(BaseModel):
    sha: str
    ref: str


class PullRequest(BaseModel):
    number: int
    title: str
    state: str
    head: PullRequestHead
    draft: bool = False
    changed_files: int | None = None
    additions: int | None = None
    deletions: int | None = None


class PullRequestEvent(BaseModel):
    """GitHub pull_request webhook event."""

    action: str  # opened, synchronize, reopened, ready_for_review
    number: int
    pull_request: PullRequest
    repository: GitHubRepo
    sender: GitHubUser


class Installation(BaseModel):
    id: int


class PullRequestEventWithInstallation(PullRequestEvent):
    """Pull request event with GitHub App installation context."""

    installation: Installation | None = None

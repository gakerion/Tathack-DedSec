import json
from typing import Any
import git
import math

# Removed get_repo_diff from this import list
from driver import (
    create_commit,
    get_commit_diff,
    get_history,
    get_repo,
    get_repo_status,
    stage_all,
    stage_files,
    repo_hard_reset,
)

READ_ONLY_TOOLS = {
    "get_repo_status",
    "get_history",
    "get_commit_diff",
}

MUTATING_TOOLS = {
    "stage_files",
    "stage_all",
    "create_commit",
    "repo_hard_reset",
}


def should_commit(imp: float) -> bool:
    if not isinstance(imp, (float, int)):
        raise ValueError("imp must be a numeric value")
    if imp > 0.4:
        return True
    return False


def commit_changes(imp: float, repo: git.Repo, commit_message: str) -> Any:
    stage_all(repo)
    commit_hash = create_commit(repo, commit_message)
    return commit_hash

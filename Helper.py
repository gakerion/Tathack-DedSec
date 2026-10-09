import json
import git
import math

from driver import (
    create_scoped_commit,
    get_commit_diff,
    get_history,
    get_repo,
    get_repo_status,
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


def commit_changes(
    repo: git.Repo,
    affected_paths: list[str],
    commit_message: str,
) -> str:
    return create_scoped_commit(repo, affected_paths, commit_message)

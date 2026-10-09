import json
from typing import Any
import git


from driver import (
    create_commit,
    get_commit_diff,
    get_history,
    get_repo,
    get_repo_diff,
    get_repo_status,
    stage_all,
    stage_files,
    repo_hard_reset
)

READ_ONLY_TOOLS = {
    "get_repo_status",
    "get_repo_diff",
    "get_history",
    "get_commit_diff",
}

MUTATING_TOOLS = {
    "stage_files",
    "stage_all",
    "create_commit",
    "repo_hard_reset",
}

def should_commit(imp: float,) -> bool:
    if isinstance(imp, float):
        return ValueError["imp must be a float and wrt must be a boolean"]
    if imp > 0.4:
        return True
    return "Nothing to commit. Importance is low and write flag is not set."

def commit_changes(imp: float, repo: git.Repo, commit_message: str) -> Any:
    stage_all(repo)
    commit_hash = create_commit(repo, commit_message)
    return commit_hash
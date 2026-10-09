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

def should_commit(imp: float, wrt: bool) -> bool:
    if isinstance(imp, float) or isinstance(wrt, bool):
        return ValueError["imp must be a float and wrt must be a boolean"]
    
    if imp > 0.4 or wrt:
        return True
    return False

def commit_changes(imp: float, wrt: bool, repo: git.Repo, commit_message: str) -> Any:
    if (should_commit(imp, wrt)):
        stage_all(repo)
        commit_hash = create_commit(repo, commit_message)
        return commit_hash
    else:
        return "Nothing to commit. Importance is low and no write request was made."
import json
from typing import Any

from driver import (
    create_commit,
    get_commit_diff,
    get_history,
    get_repo,
    get_repo_diff,
    get_repo_status,
    stage_all,
    stage_files,
)

TOOL_DEFINITIONS = [
    {
        "name": "get_repo_status",
        "description": "Show the current branch and changed files.",
        "arguments": ["repo_path"],
    },
    {
        "name": "get_repo_diff",
        "description": "Show unstaged or staged changes.",
        "arguments": ["repo_path", "staged"],
    },
    {
        "name": "stage_files",
        "description": "Stage selected files.",
        "arguments": ["repo_path", "file_paths"],
    },
    {
        "name": "stage_all",
        "description": "Stage all changes.",
        "arguments": ["repo_path"],
    },
    {
        "name": "create_commit",
        "description": "Create a commit with a message.",
        "arguments": ["repo_path", "message"],
    },
    {
        "name": "get_history",
        "description": "Show recent commits.",
        "arguments": ["repo_path", "limit"],
    },
    {
        "name": "get_commit_diff",
        "description": "Compare two commits.",
        "arguments": ["repo_path", "first_commit", "second_commit"],
    },
]
from pathlib import Path

import git
from git import InvalidGitRepositoryError, NoSuchPathError


def init_repo(repo_path: str) -> git.Repo:
    path = Path(repo_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {path}")

    if not path.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {path}")

    return git.Repo.init(path)


def get_repo(repo_path: str) -> git.Repo:
    path = Path(repo_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {path}")

    if not path.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {path}")

    try:
        return git.Repo(path)
    except InvalidGitRepositoryError as error:
        raise ValueError(f"Not a Git repository: {path}") from error
    except NoSuchPathError as error:
        raise FileNotFoundError(
            f"Repository path does not exist: {path}"
        ) from error


def get_repo_status(repo: git.Repo) -> str:
    return repo.git.status("--short", "--branch")


def get_repo_diff(repo: git.Repo, staged: bool = False) -> str:
    if staged:
        return repo.git.diff("--cached")

    return repo.git.diff()


def stage_files(repo: git.Repo, file_paths: list[str]) -> None:
    if not file_paths:
        raise ValueError("At least one file path is required.")

    repo.index.add(file_paths)


def stage_all(repo: git.Repo) -> None:
    repo.index.add(all=True)
    return None


def stage_all(repo: git.Repo) -> None:
    repo.git.add("--all")


def create_commit(repo: git.Repo, message: str) -> str:
    if not message.strip():
        raise ValueError("Commit message cannot be empty.")

    commit = repo.index.commit(message.strip())
    return commit.hexsha


def get_history(repo: git.Repo, limit: int = 20) -> list[dict[str, str]]:
    if limit < 1:
        raise ValueError("History limit must be positive.")

    return [
        {
            "hash": commit.hexsha,
            "message": commit.message.strip(),
        }
        for commit in repo.iter_commits(max_count=limit)
    ]
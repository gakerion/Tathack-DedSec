from pathlib import Path

import git
from git import InvalidGitRepositoryError, NoSuchPathError

from azure.core.exceptions import AzureError, ResourceExistsError
from azure.storage.blob import BlobServiceClient
DEFAULT_CONTAINER = "git-backup"

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


def get_commit_diff(
    repo: git.Repo,
    first_commit: str,
    second_commit: str,
) -> str:
    if not first_commit.strip() or not second_commit.strip():
        raise ValueError("Both commit references are required.")

    try:
        first = repo.commit(first_commit.strip())
        second = repo.commit(second_commit.strip())
    except (git.BadName, git.BadObject) as error:
        raise ValueError("One or both commit references are invalid.") from error

    return repo.git.diff(
        "--no-ext-diff",
        "--no-color",
        first.hexsha,
        second.hexsha,
    )


def stage_files(repo: git.Repo, file_paths: list[str]) -> None:
    if not file_paths:
        raise ValueError("At least one file path is required.")

    repo.index.add(file_paths)


def stage_all(repo: git.Repo) -> None:
    repo.git.add("--all")


def create_commit(repo: git.Repo, message: str) -> str:
    if not message.strip():
        raise ValueError("Commit message cannot be empty.")

    commit = repo.index.commit(message.strip())
    return commit.hexsha


def repo_hard_reset(repo: git.Repo, commit_hash: str) -> None: 
    if not commit_hash.strip():
        raise ValueError("Commit hash cannot be empty.")

    try:
        repo.git.reset("--hard", commit_hash.strip())
    except git.GitCommandError as error:
        raise ValueError(f"Failed to reset to commit {commit_hash}: {error}") from error


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

def get_changed_lines_from_last_commit_and_unstaged(
    repo: git.Repo,
) -> int:
    
    def count_numstat_lines(numstat_output: str) -> int:
        total = 0

        for line in numstat_output.splitlines():
            parts = line.split("\t")

            if len(parts) < 2:
                continue

            additions, deletions = parts[0], parts[1]

            if additions.isdigit():
                total += int(additions)

            if deletions.isdigit():
                total += int(deletions)

        return total

    try:
        last_commit_changes = repo.git.show(
            "--numstat",
            "--format=",
            "HEAD",
        )

        unstaged_changes = repo.git.diff(
            "--numstat",
        )
    except git.GitCommandError as error:
        raise ValueError(
            f"Unable to calculate changed lines: {error}"
        ) from error

    return (
        count_numstat_lines(last_commit_changes)
        + count_numstat_lines(unstaged_changes)
    )

def push_git(
    repo_path: str,
    connection_string: str,
    key: str,
    container_name: str = DEFAULT_CONTAINER,
    ) -> int:
    """
    Upload the target repository's .git folder to Azure Blob Storage.

    Args:
        repo_path: Path to the target Git repository.
        connection_string: Azure Storage connection string.
        key: Prefix used to identify this repository in blob storage.
        container_name: Azure Blob container name.

    Returns:
        Number of uploaded files.
    """
    if not connection_string.strip():
        raise ValueError("Azure connection string cannot be empty.")

    if not key.strip():
        raise ValueError("Azure storage key cannot be empty.")

    repo = Path(repo_path).resolve()
    git_directory = repo / ".git"

    if not repo.exists() or not repo.is_dir():
        raise FileNotFoundError(f"Repository path does not exist: {repo}")

    if not git_directory.exists() or not git_directory.is_dir():
        raise ValueError(f"Git directory does not exist: {git_directory}")

    blob_service = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service.get_container_client(container_name)
    try:
        container_client.create_container()
    except ResourceExistsError:
        # The container already exists, so it is ready for blob uploads.
        pass

    blob_prefix = key.strip("/")

    uploaded_files = 0

    for file_path in git_directory.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(git_directory).as_posix()
        blob_name = f"{blob_prefix}/{relative_path}"

        with file_path.open("rb") as file_data:
            container_client.upload_blob(
                name=blob_name,
                data=file_data,
                overwrite=True,
            )

        uploaded_files += 1

    return uploaded_files


def get_git(
    repo_path: str,
    connection_string: str,
    key: str,
    container_name: str = DEFAULT_CONTAINER,
) -> bool:

    repo = Path(repo_path).resolve()

    git_directory = repo / ".git"
    blob_service = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service.get_container_client(container_name)

    blob_prefix = key.strip("/") + "/"
    blobs = list(container_client.list_blobs(name_starts_with=blob_prefix))

    if not blobs:
        raise FileNotFoundError(
            f"No Git data found in container '{container_name}' "
            f"with key '{key}'."
        )

    for blob in blobs:
        relative_path = blob.name[len(blob_prefix):]

        if not relative_path:
            continue

        destination = (git_directory / relative_path).resolve()

        try:
            destination.relative_to(git_directory.resolve())
        except ValueError as error:
            raise ValueError(
                f"Unsafe blob path received from Azure: {blob.name}"
            ) from error

        destination.parent.mkdir(parents=True, exist_ok=True)

        with destination.open("wb") as file_data:
            download_stream = container_client.download_blob(blob.name)
            file_data.write(download_stream.readall())

    return True
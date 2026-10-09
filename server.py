from contextlib import asynccontextmanager
from copy import deepcopy
import re
from threading import Lock

import ollama
import git
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from checkpoint_helper import AGENT_MODEL, WORKSPACE, get_helper, run_ollama_test
from driver import get_history, get_repo, repo_hard_reset


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load the AI models when the FastAPI application starts.
    The application will not finish starting if model initialization fails.
    """
    try:
        # Load the Hugging Face checkpoint helper.
        get_helper()

        # Load the Ollama agent model into memory.
        ollama.chat(
            model=AGENT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "Initialize the model.",
                }
            ],
            keep_alive="10m",
            options={
                "num_ctx": 4096,
            },
        )
    except Exception as error:
        raise RuntimeError(
            f"Failed to initialize AI models during application startup: {error}"
        ) from error

    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


checkpoints = []
model_lock = Lock()
history_lock = Lock()


@app.get("/checkpoints")
def get_checkpoints():
    with history_lock:
        print(checkpoints)
        return {"checkpoints": deepcopy(checkpoints), "history_persistent": False}


@app.get("/git-history")
def get_git_history():
    try:
        repository = get_repo(str(WORKSPACE))
        history = get_history(repository, limit=100)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail=f"Git history is unavailable: {error}",
        ) from error

    return {
        "commits": [
            {
                "task": item["message"],
                "commit_hash": item["hash"],
                "message": item["message"],
                "checkpoint_id": None,
                "importance": None,
                "restore_supported": True,
            }
            for item in history
        ],
        "history_persistent": True,
    }


@app.post("/chat")
def prompt(
    prompt: str = Form(...),
    file: UploadFile | None = File(None),
):
    if file is not None:
        raise HTTPException(
            status_code=422,
            detail="File attachments are not implemented.",
        )

    file_content = None
    file_name = None

    if file is not None:
        try:
            raw = file.file.read(12_001)
        finally:
            file.file.close()

        if len(raw) > 12_000:
            raise HTTPException(
                status_code=413,
                detail="Text attachment must be 12 KB or smaller.",
            )

        try:
            file_content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=422,
                detail="Only UTF-8 text files are supported.",
            )

        file_name = file.filename or "attachment.txt"

    if not prompt.strip():
        raise HTTPException(
            status_code=422,
            detail="Prompt must not be blank.",
        )
    with model_lock:
        packet = run_ollama_test(
            prompt,
            file_content=file_content,
            file_name=file_name,
        )
        group = {"prompt": prompt, "commits": [], "actions": packet["actions"]}
        for action in packet["actions"]:
            if (
                action["status"] == "executed"
                and "checkpoint_id" in action
                and "git_commit_hash" in action
            ):
                group["commits"].append(
                    {
                        "task": f"{action['operation'].capitalize()} {action['target']}"
                        + (
                            f" -> {action['destination']}"
                            if "destination" in action
                            else ""
                        ),
                        "commit_hash": action["git_commit_hash"],
                        "checkpoint_id": action["checkpoint_id"],
                        "importance": action["importance"],
                        "restore_supported": True,
                    }
                )
        with history_lock:
            checkpoints.append(group)

    return {**packet, "result": packet["output"]}


@app.post("/restore")
def restore_checkpoint(commit_hash: str):
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_hash or ""):
        raise HTTPException(
            status_code=422,
            detail="commit_hash must be a 40-character Git commit hash.",
        )

    with model_lock:
        try:
            repository = get_repo(str(WORKSPACE))
            commit = repository.commit(commit_hash)
        except (FileNotFoundError, ValueError, git.BadName, git.BadObject) as error:
            raise HTTPException(
                status_code=404,
                detail=f"Git commit was not found: {commit_hash}",
            ) from error

        if repository.is_dirty(untracked_files=True):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Workspace has uncommitted changes. Commit or remove them "
                    "before restoring an earlier commit."
                ),
            )

        try:
            repo_hard_reset(repository, commit.hexsha)
        except ValueError as error:
            raise HTTPException(
                status_code=500,
                detail=f"Could not restore commit {commit.hexsha}: {error}",
            ) from error

    return {
        "message": f"Workspace restored to {commit.hexsha}.",
        "commit_hash": commit.hexsha,
        "task": commit.message.strip(),
    }

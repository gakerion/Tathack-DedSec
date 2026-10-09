from contextlib import asynccontextmanager
from copy import deepcopy
from threading import Lock

import ollama
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from checkpoint_helper import AGENT_MODEL, WORKSPACE, get_helper, run_ollama_test
from driver import get_repo, repo_hard_reset

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
    
@app.post("/chat")
def prompt(
    prompt: str = Form(...),
    file: UploadFile | None = File(None),
):
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
            if action["status"] == "executed" and "checkpoint_id" in action:
                group["commits"].append({
                    "task": f"{action['operation'].capitalize()} {action['target']}"
                            + (f" -> {action['destination']}" if "destination" in action else ""),
                    "commit_hash": action.get("git_commit_hash", action["checkpoint_id"]),
                    "checkpoint_id": action["checkpoint_id"],
                    "importance": action["importance"], 
                    "restore_supported": False,
                })
        with history_lock:
            checkpoints.append(group)
    
    return {**packet, "result": packet["output"]}

@app.post("/restore")
def restore_checkpoint(commit_hash: str):
    try:
        # Load the workspace repository
        repo = get_repo(str(WORKSPACE))
        
        # Perform the hard reset to the specific Git commit
        repo_hard_reset(repo, commit_hash)
        
        return {"message": f"Successfully restored to commit {commit_hash[:7]}"}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to restore: {str(error)}")
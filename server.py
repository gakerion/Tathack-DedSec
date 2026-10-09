"""Local prototype API. Run one worker to share its in-memory history."""
from copy import deepcopy
from threading import Lock
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from checkpoint_helper import run_ollama_test
from driver import get_repo, repo_hard_reset
from checkpoint_helper import WORKSPACE

app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
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
def prompt(prompt: str = Form(...), file: UploadFile | None = File(None)):
    if file is not None:
        file.file.close()
        raise HTTPException(status_code=422, detail="File attachments are not supported yet.")
    if not prompt.strip():
        raise HTTPException(status_code=422, detail="Prompt must not be blank.")
    
    with model_lock:
        packet = run_ollama_test(prompt)
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
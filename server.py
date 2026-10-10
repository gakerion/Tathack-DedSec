"""Local HoneyGate API. Run one worker to serialize agent tasks and undo."""
from threading import Lock

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import action_history as history
from azure_backup import BackupError
from checkpoint_helper import run_ollama_test, undo_latest_action, restore_file_stage

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)
model_lock = Lock()


class RestoreRequest(BaseModel):
    action_id: int = Field(gt=0, strict=True)
    keep_stage: bool = False


@app.get("/checkpoints")
def get_checkpoints():
    try:
        return history.history_payload()
    except BackupError as error:
        raise HTTPException(503, str(error))


@app.post("/chat")
def prompt(prompt: str = Form(...), file: UploadFile | None = File(None)):
    if not prompt.strip():
        raise HTTPException(422, "Prompt must not be blank.")
    content, filename = None, None
    if file is not None:
        try:
            raw = file.file.read(12_001)
        finally:
            file.file.close()
        if len(raw) > 12_000:
            raise HTTPException(413, "Text attachment must be 12 KB or smaller.")
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(422, "Only UTF-8 text attachments are supported.")
        filename = file.filename or "attachment.txt"
    with model_lock:
        try:
            packet = run_ollama_test(prompt, file_content=content, file_name=filename)
        except BackupError as error:
            raise HTTPException(503, str(error))
    return {**packet, "result": packet["output"]}


@app.post("/restore")
def restore_checkpoint(request: RestoreRequest):
    with model_lock:
        try:
            if request.keep_stage:
                return restore_file_stage(request.action_id)
            return undo_latest_action(request.action_id)
        except (ValueError, RuntimeError) as error:
            raise HTTPException(409, str(error))
        except OSError:
            raise HTTPException(500, "Could not access checkpoint or workspace storage.")

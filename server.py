from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import time
from checkpoint_helper import run_ollama_test



checkpoints = [
    {
        "prompt": "Prompt 1",
        "commits": [
            {
                    "task": "Make background black",
                    "commit_hash": "1abcde",
                    "importance" : 0.5
                },
                {
                    "task": "Make bird orange",
                    "commit_hash": "2abcde",
                    "importance" : 0.7
                },
                {
                    "task": "Make score to top left",
                    "commit-hash": "3abcde",
                    "importance" : 0.2
                }
        ]
    },
    {
        "prompt": "Prompt 2",
        "commits": [
            {
                    "task": "Make some noise",
                    "commit_hash": "56abcd",
                    "importance" : 0.1
                },
                {
                    "task": "Make me crazy",
                    "commit_hash": "484dace",
                    "importance" : 0.6
                },
                {
                    "task": "Make score",
                    "commit-hash": "885fde",
                    "importance" : 0.8
                }
        ]
    },
    
]


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# @app.get("/")
# def startModel():
#     return {"message": "HoneyGate API is running"}


@app.get("/checkpoints")
def get_checkpoints():
    return {"checkpoints": checkpoints}

@app.post("/chat")
def prompt(
    prompt: str = Form(...),
    file: UploadFile | None = File(None),
):
    file_content = None

    if file is not None:
        file_content = file.file.read()
        file.file.close()

    return {"result": run_ollama_test(prompt)["output"]}


@app.post("/restore")
def restore_checkpoint(commit_hash: str):
    return restore_commit(commit_hash)
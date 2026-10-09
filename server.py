from fastapi import FastAPI, File, Form, UploadFile
import time


def aiModel(prompt: str, file_content: bytes | None = None):
    time.sleep(1)

    file_text = ""
    if file_content is not None:
        file_text = "\n" + file_content.decode("utf-8")

    return "Bro here is your response " + prompt + file_text

app = FastAPI()


@app.get("/")
def startModel():
    return {"message": "HoneyGate API is running"}


@app.post("/")
def prompt(
    prompt: str = Form(...),
    file: UploadFile | None = File(None),
):
    file_content = None

    if file is not None:
        file_content = file.file.read()
        file.file.close()

    return {"result": aiModel(prompt, file_content)}
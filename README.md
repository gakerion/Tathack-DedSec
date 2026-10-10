# HoneyGate local MVP

HoneyGate saves a verified checkpoint before each supported agent file change,
records actual actions, and lets users undo changes in reverse order.

## Run locally

Use Python 3.12 or newer, with Ollama running. From the project folder:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-test.txt
ollama pull qwen3.5:9b-q4_K_M
ollama pull qwen3:4b-instruct-2507-q4_K_M
.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Run exactly one backend worker. Both current models use Ollama. Model names,
options, and the 20-turn limit are in [checkpoint_helper.py](./checkpoint_helper.py).
Transformers is no longer part of the active helper path.

In a second terminal, run `cd frontend`, `npm install`, and `npm run dev`.
Open the Vite URL (normally http://localhost:5173).

## Supported actions

Create new UTF-8 text files, read/list/search files, append a section, and edit a unique text match.
Only plain filenames inside `workspace/` are accepted. Files are limited to 1 MiB;
reads return at most 12,000 characters and report truncation. Reference attachments
are limited to 12 KB and are not automatically saved.

The main agent is instructed to split a task into small logical changes. The backend
rejects batches and asks for one tool call per turn. New valid Python files containing functions/classes are saved in real stages:
setup, each top-level function or class method, then remaining code/entry point.
[file_stages.py](./file_stages.py) uses Python's AST parser and never executes generated code.
Each write has its own verified checkpoint. Intermediate files may not yet be runnable.
Invalid Python and other file types keep ordinary per-tool checkpoints; their logical
edit size still partly depends on the model. Overwrite, delete, move, and bulk replacement tools are disabled
for the create/edit MVP; their previous implementation remains in the source.

Click **Undo latest change** to reverse a completed create/edit action. Repeat to
reach an earlier point. Undo checks the current content and blocks if a file was
changed manually or is missing. Expand a filename and use **File version** to restore an earlier stage. This keeps
the selected stage and undoes all later changes to that file, including changes from
later tasks. Other files are unchanged; cross-file dependencies are not automatically
repaired. All affected checkpoints are checked before restoration begins. An I/O failure
during restoration can still leave a partially restored file and is reported in history.
There is no redo operation. Existing single-checkpoint files cannot acquire historical
function stages retroactively: generate a new file to see automatic function stages.

## Code and data flow

- [checkpoint_helper.py](./checkpoint_helper.py): model calls, validation, snapshots,
  controlled execution, helper analysis, and undo.
- [action_history.py](./action_history.py): SQLite intent/outcome records, task groups,
  and eligibility for undo. No additional database dependency is required.
- [server.py](./server.py): HTTP endpoints and a lock serializing agent tasks and undo.
- [importance.py](./importance.py): deterministic scoring. Existing weights remain
  C=0.457, R=0.301, S=0.158, E=0.084, renormalized over C/R/S for local impact.
  Successful supported changes report verified programmatic restore capability.
  Scores describe execution-time facts, not probabilities or guarantees against later edits.

Helper descriptions are separate from actual actions. One invalid suggestion does
not erase valid suggestions; invalid JSON or model failures appear as helper errors.
Exposed reasoning never executes tools or creates extra recovery points.

## API

- `POST /chat`: multipart `prompt` and optional `file`. Returns `thinking`, `output`,
  `result` (alias of output), `task_id`, `actions`, `checkpoint_marks`, `helper_error`,
  and `agent_error`. Inspect errors even when HTTP status is 200.
- `GET /checkpoints`: task groups with `actions`, `history_persistent: true`, and
  `history_error`. Only the latest eligible action has `restore_supported: true`.
- `POST /restore`: JSON body `{"action_id": 123}`. Conflicts return HTTP 409.
  Add `"keep_stage": true` to restore the selected file stage instead of undoing one action.
  Git commit hashes are no longer accepted.

History is stored in `honeygate-history.sqlite3`, snapshots in `checkpoints/`, and
agent files in `workspace/`. Keep the database and checkpoints together. History
survives restarts. Existing files are preserved; old checkpoints are not imported
because a checkpoint alone does not prove that execution completed. No text report
is generated. The UI shows history immediately, including after a reload.

## Limits and interrupted operations

A partial or interrupted modifying action blocks more modifications and undo until
someone inspects and repairs the file/checkpoint/history. Reads remain available.
There is no automatic crash-repair UI. Do not delete history just to bypass this check.

This is a single-process local prototype, not protection against an adversarial
external process racing file operations or tampering with storage. Timestamps and
all platform-specific metadata are not restored. Effects outside controlled tools
are outside the undo scope.

The active path no longer commits or uploads to Azure. Separate legacy utilities
in [driver.py](./driver.py) and [helper.py](./helper.py) remain available. Embedded
Azure credentials were removed from the active module; rotate credentials exposed
earlier, including in repository history.

## Verification

```powershell
.venv\Scripts\python -B -m unittest -v test_backend
cd frontend
npm run build
npm run lint
```

Backend tests use mocked model replies and isolated temporary files. Coverage includes
create/edit/edit/undo, a fresh process reading history, manual-edit conflicts, storage
failures, malformed helper suggestions, and HTTP routes. Live inference is not covered.

Manual demo: create a note, change its heading, add a paragraph, restart the backend,
then undo the paragraph, heading, and creation. Also try a manual edit before undo.

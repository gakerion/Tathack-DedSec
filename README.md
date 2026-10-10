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
agent files in `workspace/`. Keep the database and checkpoints together. Stored history survives restarts, but the API shows only the current server session. Existing files are preserved; old checkpoints are not imported
because a checkpoint alone does not prove that execution completed. No text report
is generated. A browser reload keeps current-session history; restarting the backend starts an empty history panel.

## Limits and interrupted operations

A partial or interrupted modifying action blocks more modifications and undo until
someone inspects and repairs the file/checkpoint/history. Reads remain available.
There is no automatic crash-repair UI. Do not delete history just to bypass this check.

This is a single-process local prototype, not protection against an adversarial
external process racing file operations or tampering with storage. Timestamps and
all platform-specific metadata are not restored. Effects outside controlled tools
are outside the undo scope.

The active path does not commit or upload Git repositories. Azure checkpoint backup is described below. Separate legacy utilities
in [driver.py](./driver.py) and [helper.py](./helper.py) remain available. Embedded
Azure credentials were removed from the active module; rotate credentials exposed
earlier, including in repository history.

## Verification

```powershell
.venv\Scripts\python -B -m unittest -v test_backend test_azure_backup test_task_titles
cd frontend
npm run build
npm run lint
```

Backend tests use mocked model replies and isolated temporary files. Coverage includes
create/edit/edit/undo, a fresh process reading history, manual-edit conflicts, storage
failures, malformed helper suggestions, and HTTP routes. Live inference is not covered.

Manual demo: create a note, change its heading, add a paragraph, restart the backend,
then undo the paragraph, heading, and creation. Also try a manual edit before undo.


## Simple Azure backup setup

The backend uploads checkpoint JSON and action history directly to Azure Blob Storage
using [azure_backup.py](./azure_backup.py). There is no separate service or Docker.
The agent has no credential, shell, or Azure tools. This assumes it cannot read the
backend configuration or process environment. This setup does not provide immutable/WORM protection.

1. In your Azure storage account, create a **private** Blob container named
   `honeygate`. The code does not create containers for you.
2. Use a current connection string with read/write permission for that container.
   Do not reuse the credentials previously exposed in source code.
3. Open [azure_config.json](./azure_config.json) in the project root. It is already
   created locally and excluded from Git. For a new checkout, copy
   [azure_config.example.json](./azure_config.example.json) to that filename.
4. Paste your connection string between the empty quotes for `connection_string`.
   The container is prefilled as `honeygate`; change it if your existing container
   has a different name. Keep the prefix stable and unique to this workspace.
5. Save the file and restart your backend normally. No PowerShell environment
   variables or extra configuration libraries are needed. Do not edit these settings
   while a task is running. Never paste your credential into chat or commit it to Git.

The backend reads this file automatically using a path relative to the Python module,
so it also works when started from a different working directory. A nonempty connection
string enables Azure. An empty string leaves the app in local mode, visibly labeled
in the sidebar. To explicitly require Azure even when the credential is absent, add
`"mode": "azure"`; missing credentials then block modifying actions. Invalid configuration
also produces an error rather than silently falling back to local backups.

For a one-time upload of existing checkpoints, or retry after an outage, stop the
backend and run this command (the VS Code Run Python File action on that module works too):

```powershell
.venv\Scripts\python azure_backup.py
```

Then start the backend normally. New checkpoints are uploaded automatically as tasks
run; this separate command is only needed for older checkpoints or retrying failed
backups. Use one backend and one stable prefix per workspace/database.

Environment variables remain optional overrides: `AZURE_STORAGE_CONNECTION_STRING`,
`HONEYGATE_BACKUP_CONTAINER`, `HONEYGATE_BACKUP_PREFIX`, and `HONEYGATE_BACKUP_MODE`.
Existing values take priority over the file. No `.env` loader is used.
The local config contains a plaintext secret, not an encrypted or hashed one. It is
outside the agent's controlled workspace, under the agreed restricted-agent assumption.

Each new checkpoint is uploaded under `<prefix>/checkpoints/<id>.json` and downloaded
again for byte-for-byte verification before the file change. Existing checkpoint blobs
are never overwritten; identical re-uploads are accepted. Action intent, results, and
undo status are saved locally and synchronized to `<prefix>/history/latest.json`.
That history snapshot is overwritten, deliberately keeping this MVP simple. It is not
an immutable audit trail. Full history uploads add latency and suit small demo histories.

If a post-action upload fails, the file may already have changed. The actual result
remains in local history, the error is shown, and a pending-backup marker blocks further
modifications until synchronization succeeds. An interruption can leave the remote
history with a running/undoing action, which requires inspection rather than automatic
retry. Remote checkpoints alone never prove that an action completed.

If the local database is missing, the next history load restores it from the remote
history snapshot using the same container and prefix. Missing local checkpoint files
are downloaded on demand during undo and validated before use. Existing local history
is not replaced or merged with remote history. Do not delete local history after a failed
upload; first retry synchronization so the remote copy has the newest outcomes.

Backups save previous file states, not a complete latest copy of the workspace. Undo
still requires the current target file to match its expected post-action content; a
missing or manually changed workspace file is blocked. This is checkpoint recovery,
not a full disaster-recovery filesystem restore.

Azure tests use the real SDK exception types with an in-memory fake blob service.
They make no real Azure requests. A live check still requires your credentials/container.
SDK reference: [Azure Blob Python quickstart](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python).


## Short task headings

Task headings use a 4-7 word summary generated from the user's request, with no
sample titles in the summarization prompt. The full prompt remains available under
**View original request**. Titles are saved with history and included in Azure backups.
Existing databases migrate automatically; older tasks/backups display a shortened prompt.

Summarization runs after execution and adds one helper-model request (20-second HTTP
client timeout). Invalid or unavailable output falls back to a shortened original prompt.
Title generation/save errors do not change action results or undo behavior. A failed
upload of a cosmetic title alone does not block future file operations; a subsequent
history sync includes it. Pending backups of actual actions keep their existing blocking
behavior. Live title quality depends on the configured helper model.


## Fresh history on server restart

Every backend startup starts a new visible history session. The `/checkpoints` endpoint
shows only tasks created after that startup, and `/restore` rejects older-session action
IDs. Refresh the frontend after restarting the backend. A browser refresh by itself does
not reset history. Auto-reloading the backend during development also starts a fresh session.

This resets the displayed history, not the stored backups: SQLite history, checkpoint
files, Azure backups, and workspace contents remain intact. Previous interrupted actions
or pending backups still require resolution; restarting must not bypass those checks.
The response reports `history_scope: current_server_session`; `history_persistent` still
refers to the retained underlying storage.

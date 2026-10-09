# HoneyGate backend update

This update was based on the executable backend in
`C:\Users\aksha\Downloads\HACKATHON\Tathack-DedSec`.
The supplied checkpoint-restore ZIP contained an earlier planning-only helper and
Git utilities; it did not contain server.py or the executable create-file tool.

## Run locally

Use Python 3.12 or newer (the tests were run with Python 3.14).
From the project folder:

```powershell
python -m pip install -r requirements.txt
ollama pull qwen3.5:9b-q4_K_M
ollama pull qwen3:4b
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Ollama must be running. The Hugging Face helper loads on the first request that
includes reasoning, and may download model weights. Run one server worker;
model calls are serialized to avoid overlapping access to the shared helper.
GitPython is retained for the project's existing, separate Git utilities. Those
utilities are not exposed as agent tools and were not changed by this update.

## Returned JSON

`run_ollama_test(prompt)` returns a Python dictionary. FastAPI serializes it once.
`POST /chat` still accepts the `prompt` form field, and returns:

```json
{
  "thinking": "Exposed reasoning, if the agent returned it",
  "output": "The normal model answer",
  "actions": [],
  "checkpoint_marks": [],
  "helper_error": null,
  "agent_error": null,
  "result": "The normal model answer"
}
```

`result` is an alias for `output` to keep the existing frontend working.
`checkpoint_marks` contains descriptive helper suggestions, not saved checkpoints
or confirmed actions. A suggestion contains operation, title, target,
supporting_text, evidence_verified, reason, and agent_id. Titles must have
16-20 characters; invalid helper output appears in helper_error without erasing
actions. Extra helper-generated score, count and recovery fields are discarded.

Only `actions` describes actual tool outcomes. Check status (`executed`,
`blocked`, or `failed`) and state_changed. A write or flush failure after opening
a file can leave an empty or partial file; that outcome is reported as failed
with state_changed=true. Do not automatically retry a failed task: previous
actions may already have executed. agent_error and helper_error can be present
in an otherwise successful HTTP response, so inspect them in the frontend.

Only create_text_file is executable. It accepts a plain filename and UTF-8 text,
rejects existing files and invalid Windows filenames, and records the prior
absence of the target. The checkpoint is flushed and read back before exclusive
file creation. A checkpoint record alone does not prove an action completed:
creation may fail after the checkpoint is saved.

No report text file is written. Workspace files and checkpoint JSON records
remain on disk. Old report files are preserved but are no longer updated.

## Importance and restoration

Python scores successful actions using backend facts. The helper supplies no
inputs to scoring. Defaults remain M x (0.35C + 0.30R + 0.20S + 0.15E), with
logarithmic scope scaling capped at the configured threshold. Adjust the
constants in importance.py or use calculate_importance's scope_threshold and
weights arguments. These are policy estimates, not failure probabilities.

A verified pre-creation checkpoint does not imply restoration exists. File
checkpoint recovery remains unsupported, recovery difficulty remains 1.0, and
scores are provisional. Git commit restoration is supported through
`POST /restore`.

GET /checkpoints returns real completed Git commits from this server process,
grouped by prompt, rather than sample data. Read and search operations do not
create Git commits. Each successful mutation tool call creates exactly one
commit, and separate mutation calls create separate commits. Mutation commits
stage only their affected paths; move operations stage both the source and
destination. Existing unrelated staged and unstaged files are not included.

To prevent monolithic commits for large generated files, each write section is
limited to 4 KiB: `create_text_file` rejects an oversized initial file, and
`edit_text_file` and `overwrite_text_file` reject oversized sections. The agent
must create a small scaffold first and then use separate `edit_text_file` calls
for each logical section. Each successful mutation call creates one additional
Git commit. The agent has a bounded twelve-turn tool loop so it can recover from
an oversized section and continue adding later sections without allowing an
unbounded run.

The `checkpoint_id` and `git_commit_hash` fields are separate. The former
identifies the verified checkpoint record, while the latter is an actual Git
commit hash. Importance scores remain available for risk and UI display but do
not control whether a successful mutation is committed. If the file mutation
succeeds but Git fails, the mutation remains successful and `git_error` reports
the failure without substituting a checkpoint ID for a Git hash. History is in
memory and resets at server restart. Failed and blocked results remain in each
group's actions. This is not yet persistent action-history reconstruction from
stored checkpoints.

GET /git-history reads the workspace repository directly and returns the
persistent Git commit history, including commits created before the current
server process started. The frontend commit sidebar uses this endpoint, so it
shows repository history rather than only the current process's in-memory
checkpoint groups.

File attachments return HTTP 422 because attachment processing is not implemented.

This local prototype does not protect checkpoint storage against other programs,
arbitrary shell access, or an adversarial process replacing directories during
execution. It is not a whole-drive sandbox. `POST /restore?commit_hash=<40-character-hash>` restores the workspace to an
existing commit with `git reset --hard`. The endpoint refuses to run when the
workspace has uncommitted or untracked changes, preventing accidental data
loss. It returns HTTP 404 for an unknown commit, HTTP 409 for a dirty
workspace, and HTTP 422 for an invalid hash.

## Troubleshooting and test errors

The backend test suite uses temporary workspaces and mocked model responses; it
must not require a live Ollama server or Azure Storage. The following failures
were diagnosed and fixed:

- `HFValidationError` for `qwen3:4b-instruct-2507-q4_K_M`: an Ollama tag was
  passed to Hugging Face Transformers. The providers now use separate model IDs.
- All file actions returned `blocked` with `ambiguous argument 'HEAD'`: scoring
  incorrectly inspected an unborn Git repository. Scope scoring now uses the
  affected-file count as intended.
- Importance-score mismatch: local scores now use the documented
  `0.35C + 0.30R + 0.20S + 0.15E` weights without renormalization.
- Invalid scoring inputs were silently accepted: invalid operations, impacts,
  non-finite values, flags, and unsupported weight overrides now raise
  `ValueError`.
- `/restore` now validates the commit hash and refuses to reset a dirty
  workspace, returning HTTP 404, 409, or 422 for the corresponding errors.
  File attachments likewise return the documented HTTP 422.

## Verification

```powershell
python -m pip install -r requirements-test.txt
python -m unittest -v test_backend
```

The suite passes all 16 tests with mocked model responses, real temporary files,
and FastAPI's
HTTP test client. They cover checkpoint ordering/verification, failed checkpoint
writes, exclusive creation and races, path validation, partial failures, scoring,
helper trust boundaries, error preservation, JSON returns and HTTP routes.
Live Ollama and Hugging Face inference were not run.

The archive contains replacement backend files, tests, and these notes. It does
not contain the frontend, model weights, or existing workspace/checkpoint data.

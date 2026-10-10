"""Persistent action history for the local HoneyGate MVP."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import azure_backup as backup

DATABASE = Path(__file__).with_name("honeygate-history.sqlite3")
MODIFYING_OPERATIONS = {"create", "edit"}


@contextmanager
def database():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                data TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        with connection:
            if not connection.execute("SELECT 1 FROM metadata WHERE key = 'initialized'").fetchone():
                # A missing local database can rebuild its task/action history from Azure.
                if backup.enabled() and not connection.execute("SELECT 1 FROM tasks LIMIT 1").fetchone():
                    saved = backup.download_json("history/latest.json", missing_ok=True)
                    if saved is not None:
                        _import_history(connection, saved)
                connection.execute("INSERT INTO metadata VALUES ('initialized', 'yes')")
            yield connection
    finally:
        connection.close()


def _import_history(connection, saved):
    if not isinstance(saved, dict) or saved.get("schema_version") != 1 or not isinstance(saved.get("tasks"), list):
        raise backup.BackupError("Unsupported Azure history backup.")
    try:
        for task in saved["tasks"]:
            if type(task["task_id"]) is not int or not isinstance(task["prompt"], str):
                raise ValueError("Invalid task")
            connection.execute("INSERT INTO tasks (id, prompt) VALUES (?, ?)", (task["task_id"], task["prompt"]))
            for action in task["actions"]:
                if type(action["action_id"]) is not int or not isinstance(action["status"], str):
                    raise ValueError("Invalid action")
                connection.execute("INSERT INTO actions (id, task_id, data) VALUES (?, ?, ?)",
                                   (action["action_id"], task["task_id"], json.dumps(action)))
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        raise backup.BackupError("Azure history is invalid; no history was imported.") from None


def _mark_pending(connection):
    if backup.enabled():
        connection.execute("INSERT OR REPLACE INTO metadata VALUES ('backup_pending', 'yes')")


def sync_backup():
    """Retry this after an outage; local results are preserved even if upload fails."""
    if not backup.enabled():
        return
    saved = {"schema_version": 1, "tasks": groups()}
    backup.upload_json("history/latest.json", saved, overwrite=True)
    with database() as connection:
        connection.execute("DELETE FROM metadata WHERE key = 'backup_pending'")


def backup_pending():
    with database() as connection:
        return connection.execute("SELECT 1 FROM metadata WHERE key = 'backup_pending'").fetchone() is not None


def start_task(prompt):
    with database() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (prompt) VALUES (?)",
            (prompt,),
        )
        task_id = cursor.lastrowid
        _mark_pending(connection)
    sync_backup()
    return task_id


def begin_action(task_id, tool, operation):
    # Persist intent before execution. A crash leaves a visible running action.
    data = {
        "tool": tool,
        "operation": operation,
        "status": "running",
        "state_changed": False,
    }

    with database() as connection:
        cursor = connection.execute(
            "INSERT INTO actions (task_id, data) VALUES (?, ?)",
            (task_id, json.dumps(data)),
        )
        action_id = cursor.lastrowid
        _mark_pending(connection)
    try:
        sync_backup()
    except backup.BackupError:
        # No tool has executed yet. Do not leave a misleading running action.
        data.update(status="blocked", reason="Azure history upload failed before execution.")
        with database() as connection:
            connection.execute("UPDATE actions SET data = ? WHERE id = ?", (json.dumps(data), action_id))
        raise
    return action_id


def save_action(action_id, result):
    data = dict(result)
    data["action_id"] = action_id

    with database() as connection:
        previous = connection.execute("SELECT data FROM actions WHERE id = ?", (action_id,)).fetchone()
        cursor = connection.execute(
            "UPDATE actions SET data = ? WHERE id = ?",
            (json.dumps(data), action_id),
        )

        if cursor.rowcount != 1:
            raise ValueError("Action history record was not found.")
        _mark_pending(connection)
    try:
        sync_backup()
    except backup.BackupError:
        if data["status"] == "undoing" and previous is not None:
            # Undo has not started if its intent backup failed.
            with database() as connection:
                connection.execute("UPDATE actions SET data = ? WHERE id = ?", (previous["data"], action_id))
        raise


def groups():
    with database() as connection:
        if not connection.in_transaction:
            connection.execute("BEGIN")
        tasks = connection.execute(
            "SELECT id, prompt FROM tasks ORDER BY id"
        ).fetchall()

        rows = connection.execute(
            "SELECT id, task_id, data FROM actions ORDER BY id"
        ).fetchall()

    grouped = {
        task["id"]: {
            "task_id": task["id"],
            "prompt": task["prompt"],
            "actions": [],
        }
        for task in tasks
    }

    for row in rows:
        action = json.loads(row["data"])
        action["action_id"] = row["id"]
        grouped[row["task_id"]]["actions"].append(action)

    return list(grouped.values())


def all_actions():
    return sorted(
        [
            action
            for group in groups()
            for action in group["actions"]
        ],
        key=lambda action: action["action_id"],
    )


def recovery_blocker(actions):
    for action in actions:
        if action.get("operation") not in MODIFYING_OPERATIONS:
            continue

        status = action["status"]

        if status in {"running", "undoing", "undo_failed"}:
            return (
                f"Action {action['action_id']} has an unresolved state "
                f"({status}). Inspect the workspace and checkpoint "
                "before making more changes."
            )

        if status == "failed" and action.get("state_changed"):
            return (
                f"Action {action['action_id']} partially changed a file. "
                "Manual inspection is required."
            )

    return None


def require_safe_history():
    if backup_pending():
        raise backup.BackupError("History backup is pending. Run python azure_backup.py before more changes.")
    blocker = recovery_blocker(all_actions())
    if blocker:
        raise RuntimeError(blocker)


def latest_modification(actions=None):
    if actions is None:
        actions = all_actions()

    candidates = [
        action
        for action in actions
        if action["status"] == "executed"
        and action.get("state_changed")
        and action.get("checkpoint_id")
        and action.get("operation") in MODIFYING_OPERATIONS
    ]

    return max(
        candidates,
        key=lambda action: action["action_id"],
        default=None,
    )


def history_payload():
    result = groups()
    actions = [
        action
        for group in result
        for action in group["actions"]
    ]

    blocker = recovery_blocker(actions)
    if backup_pending():
        blocker = "History backup is pending. Run python azure_backup.py before more changes."
    latest = latest_modification(actions)
    latest_id = latest["action_id"] if latest else None
    latest_by_file = {}
    for action in sorted(actions, key=lambda item: item["action_id"]):
        if action["status"] == "executed" and action.get("state_changed") and action.get("checkpoint_id"):
            latest_by_file[action["target"]] = action["action_id"]

    for action in actions:
        # Only the newest applied modification can be undone.
        action["restore_supported"] = (
            blocker is None
            and latest_id is not None
            and action["action_id"] == latest_id
        )
        action["stage_restore_supported"] = (
            blocker is None and action["status"] == "executed"
            and bool(action.get("checkpoint_id")) and bool(action.get("state_changed"))
            and action["action_id"] < latest_by_file.get(action.get("target"), 0)
        )
        action["is_current_stage"] = action["action_id"] == latest_by_file.get(action.get("target"))

    return {
        "checkpoints": result,
        "history_persistent": True,
        "history_error": blocker,
        "backup": backup.status(),
    }

"""Persistent action history for the local HoneyGate MVP."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

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
        """)

        with connection:
            yield connection
    finally:
        connection.close()


def start_task(prompt):
    with database() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (prompt) VALUES (?)",
            (prompt,),
        )
        return cursor.lastrowid


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
        return cursor.lastrowid


def save_action(action_id, result):
    data = dict(result)
    data["action_id"] = action_id

    with database() as connection:
        cursor = connection.execute(
            "UPDATE actions SET data = ? WHERE id = ?",
            (json.dumps(data), action_id),
        )

        if cursor.rowcount != 1:
            raise ValueError("Action history record was not found.")


def groups():
    with database() as connection:
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
    latest = latest_modification(actions)
    latest_id = latest["action_id"] if latest else None

    for action in actions:
        # Only the newest applied modification can be undone.
        action["restore_supported"] = (
            blocker is None
            and latest_id is not None
            and action["action_id"] == latest_id
        )

    return {
        "checkpoints": result,
        "history_persistent": True,
        "history_error": blocker,
    }

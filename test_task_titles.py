import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import action_history as history
import azure_backup as backup
import checkpoint_helper as hg
from test_backend import response, create_call


class TaskTitleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for change in (
            patch.dict(os.environ, {"HONEYGATE_BACKUP_MODE": "local"}),
            patch.object(history, "DATABASE", root / "history.sqlite3"),
            patch.object(hg, "WORKSPACE", root / "workspace"),
            patch.object(hg, "CHECKPOINTS", root / "checkpoints"),
        ):
            change.start()
            self.addCleanup(change.stop)

    def test_old_database_migrates_without_losing_prompt(self):
        prompt = "Please create a program with several useful functions for my project"
        with sqlite3.connect(history.DATABASE) as connection:
            connection.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, prompt TEXT NOT NULL)")
            connection.execute("INSERT INTO tasks (prompt) VALUES (?)", (prompt,))
        connection.close()
        group = history.groups()[0]
        self.assertEqual(group["prompt"], prompt)
        self.assertEqual(group["title"], history.short_title(prompt))
        self.assertEqual(history.groups()[0], group)

    def test_generated_title_uses_only_request_without_examples(self):
        prompt = "Organize these notes into a readable outline"
        with patch("ollama.Client") as client:
            client.return_value.chat.return_value = response(content="Organize notes into readable outline")
            title = hg.summarize_task_title(prompt)
        self.assertEqual(title, "Organize notes into readable outline")
        messages = client.return_value.chat.call_args.kwargs["messages"]
        self.assertEqual(messages[1]["content"], prompt)
        self.assertNotIn("example", messages[0]["content"].lower())

    def test_invalid_and_truncated_model_titles_use_prompt_fallback(self):
        prompt = "Review the supplied text and produce a clear summary for readers"
        for title, reason in (("", "stop"), ("Too short", "stop"),
                              ("a b c\nd e", "stop"), ("word " * 8, "stop"),
                              ("A reasonable four word heading", "length")):
            with self.subTest(title=title), patch("ollama.Client") as client:
                client.return_value.chat.return_value = SimpleNamespace(
                    message=SimpleNamespace(content=title), done_reason=reason)
                self.assertEqual(hg.summarize_task_title(prompt), history.short_title(prompt))

    def test_fallback_limits_long_words_and_preserves_short_request(self):
        self.assertEqual(history.short_title("Hello there"), "Hello there")
        for prompt in ("a" * 150, "abcdefghi " * 20, "a " * 20):
            self.assertLessEqual(len(history.short_title(prompt)), 60)

    def test_model_outage_does_not_change_task_execution(self):
        with patch("ollama.chat", side_effect=[response(calls=[create_call()]), response(content="Created")]), \
             patch("ollama.Client", side_effect=RuntimeError("offline")):
            packet = hg.run_ollama_test("Create a note with the requested content")
        self.assertIsNone(packet["agent_error"])
        self.assertEqual(packet["output"], "Created")
        self.assertEqual(packet["actions"][0]["status"], "executed")
        self.assertEqual(packet["title"], history.groups()[0]["title"])

    def test_saved_title_preserves_prompt_and_actions(self):
        task = history.start_task("A longer original user request")
        action = hg.execute_tool("create_text_file", {"filename": "note.txt", "content": "text"}, task)
        history.set_task_title(task, "Create the requested note")
        group = history.groups()[0]
        self.assertEqual(group["title"], "Create the requested note")
        self.assertEqual(group["prompt"], "A longer original user request")
        self.assertEqual(group["actions"][0], action)
        hg.undo_latest_action(action["action_id"])
        self.assertFalse((hg.WORKSPACE / "note.txt").exists())

    def test_cosmetic_backup_failure_does_not_block_future_actions(self):
        task = history.start_task("Create the requested note")
        with patch.object(history, "sync_backup", side_effect=backup.BackupError("offline")):
            with self.assertRaises(backup.BackupError):
                history.set_task_title(task, "Create the requested note")
        self.assertFalse(history.backup_pending())
        history.require_safe_history()

    def test_title_does_not_clear_existing_pending_action_backup(self):
        task = history.start_task("Create the requested note")
        with history.database() as connection:
            connection.execute("INSERT INTO metadata VALUES ('backup_pending', 'yes')")
        with patch.object(history, "sync_backup") as sync:
            history.set_task_title(task, "Create the requested note")
            sync.assert_not_called()
        self.assertTrue(history.backup_pending())


if __name__ == "__main__":
    unittest.main()

import json
import sqlite3
import subprocess
import sys
import math
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import checkpoint_helper as hg
from importance import calculate_importance
from fastapi.testclient import TestClient
import server
import action_history as history


def response(thinking="", content="", calls=None):
    message = Mock()
    message.thinking = thinking
    message.content = content
    message.tool_calls = calls or []
    message.model_dump.return_value = {"role": "assistant", "content": content}
    return SimpleNamespace(message=message)


def create_call(filename="note.txt", content="hello"):
    return SimpleNamespace(function=SimpleNamespace(
        name="create_text_file", arguments={"filename": filename, "content": content}))


class BackendTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"HONEYGATE_BACKUP_MODE": "local"})
        environment.start()
        self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.storage = self.root / "checkpoints"
        for name, value in (("WORKSPACE", self.workspace), ("CHECKPOINTS", self.storage)):
            change = patch.object(hg, name, value)
            change.start()
            self.addCleanup(change.stop)
        database_patch = patch.object(history, "DATABASE", self.root / "history.sqlite3")
        database_patch.start()
        self.addCleanup(database_patch.stop)

    def create(self, filename="note.txt"):
        return hg.execute_tool("create_text_file", {"filename": filename, "content": "hello"})

    def test_checkpoint_is_verified_before_target_creation(self):
        original = Path.open
        def checked_open(path, mode="r", *args, **kwargs):
            if mode == "xb":
                records = list(self.storage.glob("*.json"))
                self.assertEqual(len(records), 1)
                record = json.loads(records[0].read_text())
                self.assertFalse(record["existed_before"])
                self.assertFalse(path.exists())
            return original(path, mode, *args, **kwargs)
        with patch.object(Path, "open", checked_open):
            result = self.create()
        self.assertEqual(result["status"], "executed")
        self.assertEqual((self.workspace / "note.txt").read_text(), "hello")
        self.assertEqual(result["affected_count"], 1)
        self.assertTrue(result["restore_supported"])
        self.assertEqual(result["constants"]["R"], 0.0)

    def test_failed_checkpoint_blocks_creation(self):
        for error in (OSError("disk full"), ValueError("verification failed")):
            with self.subTest(error=error), patch.object(hg, "_write_checkpoint", side_effect=error):
                result = self.create()
            self.assertEqual(result["status"], "blocked")
            self.assertFalse((self.workspace / "note.txt").exists())

    def test_corrupt_checkpoint_readback_blocks_creation(self):
        with patch.object(Path, "read_text", return_value='{}'):
            result = self.create()
        self.assertEqual(result["status"], "blocked")
        self.assertFalse((self.workspace / "note.txt").exists())

    def test_existing_file_is_not_overwritten(self):
        self.workspace.mkdir()
        target = self.workspace / "note.txt"
        target.write_text("original")
        self.assertEqual(self.create()["status"], "blocked")
        self.assertEqual(target.read_text(), "original")
        self.assertEqual(list(self.storage.glob("*.json")), [])

    def test_race_does_not_overwrite(self):
        original = hg._write_checkpoint
        def race(path, checkpoint):
            original(path, checkpoint)
            (self.workspace / "note.txt").write_text("other process")
        with patch.object(hg, "_write_checkpoint", side_effect=race):
            result = self.create()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual((self.workspace / "note.txt").read_text(), "other process")

    def test_failed_file_flush_is_reported_as_partial_change(self):
        with patch.object(hg.os, "fsync", side_effect=[None, OSError("flush failed")]):
            result = self.create()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["state_changed"])
        self.assertTrue(result["checkpoint_verified"])
        self.assertTrue((self.workspace / "note.txt").exists())

    def test_invalid_paths_and_windows_names(self):
        for name in ("../escape.txt", "C:\\escape.txt", "a/b", "a:b", "NUL.txt", "COM1",
                     "LPT¹.txt", "bad.", "bad ", "", ".", "..", "bad\x00.txt"):
            with self.subTest(name=name):
                self.assertEqual(self.create(name)["status"], "blocked")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_unknown_tools_and_invalid_arguments(self):
        self.assertEqual(hg.execute_tool("delete", {})["status"], "blocked")
        for args in ({}, {"filename": "x", "content": 4},
                     {"filename": "x", "content": "ok", "shell": "anything"}):
            self.assertEqual(hg.execute_tool("create_text_file", args)["status"], "blocked")

    def test_overlapping_storage_blocked(self):
        with patch.object(hg, "CHECKPOINTS", self.workspace):
            self.assertEqual(self.create()["status"], "blocked")

    def test_helper_descriptions_ignore_invented_facts(self):
        item = {"operation": "create", "title": "Create notes file", "target": "note.txt",
                "supporting_text": "create note.txt", "reason": "Save the note",
                "importance": 0.001, "affected_count": 9000, "backup_verified": True,
                "automatic_restore_supported": True}
        marks = hg.normalize_checkpoint_json(json.dumps([item]), "agent", "I will create  note.txt")
        self.assertIsInstance(marks, list)
        self.assertTrue(marks[0]["evidence_verified"])
        self.assertNotIn("importance", marks[0])
        self.assertNotIn("affected_count", marks[0])
        self.assertNotIn("backup_verified", marks[0])
        item["supporting_text"] = "invented quote"
        self.assertFalse(hg.normalize_checkpoint_json(json.dumps([item]), "agent", "other")[0]["evidence_verified"])
        item["title"] = "Short"
        with self.assertRaises(ValueError):
            hg.normalize_checkpoint_json(json.dumps([item]), "agent", "other")

    def test_no_tool_calls_means_no_actions_even_with_reasoning(self):
        with patch("ollama.chat", return_value=response("I will create note.txt", "A plan")), \
             patch.object(hg, "suggest_checkpoint_marks", return_value=([], [])):
            packet = hg.run_ollama_test("Plan a file")
        self.assertEqual(packet["actions"], [])
        self.assertFalse(self.workspace.exists())

    def test_dict_return_preserves_actions_after_helper_failure_without_report(self):
        old_cwd = Path.cwd()
        os.chdir(self.root)
        try:
            with patch("ollama.chat", side_effect=[
                response("I will create note.txt", calls=[create_call()]), response(content="Created")
            ]), patch.object(hg, "suggest_checkpoint_marks", side_effect=ValueError("bad helper JSON")):
                packet = hg.run_ollama_test("Create note.txt")
            self.assertIsInstance(packet, dict)
            self.assertEqual(packet["actions"][0]["status"], "executed")
            self.assertEqual(packet["helper_error"], "bad helper JSON")
            self.assertEqual(packet["checkpoint_marks"], [])
            self.assertEqual(packet["output"], "Created")
            self.assertEqual({p.name for p in self.root.iterdir()}, {"workspace", "checkpoints", "history.sqlite3"})
            json.dumps(packet, allow_nan=False)
        finally:
            os.chdir(old_cwd)

    def test_later_agent_error_keeps_executed_actions(self):
        with patch("ollama.chat", side_effect=[response(calls=[create_call()]), RuntimeError("offline")]):
            packet = hg.run_ollama_test("Create note.txt")
        self.assertEqual(packet["actions"][0]["status"], "executed")
        self.assertEqual(packet["agent_error"], "offline")

    def test_turn_limit_returns_prior_actions(self):
        with patch("ollama.chat", return_value=response(calls=[create_call()])):
            packet = hg.run_ollama_test("Create note.txt")
        self.assertEqual(len(packet["actions"]), hg.MAX_AGENT_TURNS)
        self.assertEqual(packet["actions"][0]["status"], "executed")
        self.assertEqual(packet["agent_error"], "Agent turn limit reached.")

    def test_http_payload_persistent_history_and_restore(self):
        client = TestClient(server.app)
        self.assertEqual(client.get("/checkpoints").json()["checkpoints"], [])
        with patch("ollama.chat", side_effect=[
            response(calls=[create_call()]), response(content="Created")
        ]):
            reply = client.post("/chat", data={"prompt": "Create note.txt"})
        self.assertEqual(reply.status_code, 200)
        data = reply.json()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["result"], data["output"])
        self.assertEqual(data["actions"][0]["status"], "executed")
        self.assertIn("helper_error", data)
        history = client.get("/checkpoints").json()
        self.assertTrue(history["history_persistent"])
        self.assertEqual(history["checkpoints"][0]["actions"][0]["checkpoint_id"],
                         data["actions"][0]["checkpoint_id"])
        restored = client.post("/restore", json={"action_id": data["actions"][0]["action_id"]})
        self.assertEqual(restored.status_code, 200)
        self.assertFalse((self.workspace / "note.txt").exists())
        self.assertEqual(client.post("/restore?commit_hash=anything").status_code, 422)
        self.assertEqual(client.post("/chat", data={"prompt": " "}).status_code, 422)
        with patch("ollama.chat", return_value=response(content="Hello")):
            attached = client.post("/chat", data={"prompt": "Hi"},
                                   files={"file": ("x.txt", b"hello")})
        self.assertEqual(attached.status_code, 200)
        self.assertFalse((self.workspace / "x.txt").exists())
        self.assertEqual(client.post("/chat", data={"prompt": "Hi"},
                         files={"file": ("x.txt", b"x" * 12001)}).status_code, 413)
        self.assertEqual(client.post("/chat", data={"prompt": "Hi"},
                         files={"file": ("x.txt", b"\xff")} ).status_code, 422)

    def test_importance_formula_and_validation(self):
        score = calculate_importance("create", 1, impact="local", backup_verified=True)
        expected = round((0.457 * 0.25 + 0.301 + 0.158 * math.log1p(1) / math.log1p(10)) / 0.916, 3)
        self.assertEqual(score["importance"], expected)
        self.assertEqual(calculate_importance("read", 100)["importance"], 0)
        self.assertEqual(calculate_importance("delete", 0)["importance"], 0)
        self.assertEqual(calculate_importance("delete", 100)["constants"]["S"], 1)
        self.assertEqual(calculate_importance("create", 1, backup_verified=True,
                         automatic_restore_supported=True)["constants"]["R"], 0)
        for kwargs in ({"operation": "unknown"}, {"impact": "bad"}, {"affected_count": True},
                       {"scope_threshold": 0}, {"backup_verified": "true"},
                       {"affected_count": float("nan")}):
            values = {"operation": "create", "affected_count": 1, **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                calculate_importance(**values)


    def edit(self, old, new):
        read = hg.execute_tool("read_text_file", {"filename": "note.txt"})
        return hg.execute_tool("edit_text_file", {
            "filename": "note.txt", "old_text": old, "new_text": new,
            "expected_sha256": read["sha256"],
        })

    def test_create_edit_edit_persist_and_undo(self):
        created = self.create()
        first = self.edit("hello", "Heading")
        second = self.edit("Heading", "Heading\nParagraph")
        # A fresh Python process reads the same durable history.
        code = ("from pathlib import Path; import action_history as h; "
                "import sys; h.DATABASE = Path(sys.argv[1]); "
                "print(len(h.all_actions()))")
        output = subprocess.check_output(
            [sys.executable, "-B", "-c", code, str(history.DATABASE)], text=True)
        self.assertEqual(output.strip(), "5")
        with self.assertRaisesRegex(ValueError, "latest"):
            hg.undo_latest_action(created["action_id"])
        hg.undo_latest_action(second["action_id"])
        self.assertEqual((self.workspace / "note.txt").read_text(), "Heading")
        hg.undo_latest_action(first["action_id"])
        self.assertEqual((self.workspace / "note.txt").read_text(), "hello")
        hg.undo_latest_action(created["action_id"])
        self.assertFalse((self.workspace / "note.txt").exists())
        self.assertIsNone(history.latest_modification())

    def test_manual_edit_blocks_undo(self):
        action = self.create()
        (self.workspace / "note.txt").write_text("Manual change")
        with self.assertRaisesRegex(ValueError, "changed"):
            hg.undo_latest_action(action["action_id"])
        self.assertEqual((self.workspace / "note.txt").read_text(), "Manual change")
        self.assertEqual(history.latest_modification()["status"], "executed")

    def test_partial_failure_blocks_later_writes_and_undo(self):
        with patch.object(hg.os, "fsync", side_effect=[None, OSError("disk full")]):
            self.create()
        with self.assertRaisesRegex(RuntimeError, "partially changed"):
            self.create("another.txt")
        self.assertFalse((self.workspace / "another.txt").exists())
        self.assertTrue(history.history_payload()["history_error"])

    def test_unexpected_failure_retains_checkpoint_link(self):
        with patch.object(hg, "_assert_unchanged", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                self.create()
        action = history.all_actions()[0]
        self.assertEqual(action["status"], "running")
        self.assertIn("checkpoint_id", action)
        self.assertFalse((self.workspace / "note.txt").exists())
        with self.assertRaises(RuntimeError):
            self.create("later.txt")

    def test_failed_history_write_prevents_execution(self):
        with patch.object(history, "begin_action", side_effect=sqlite3.OperationalError("full")):
            with self.assertRaises(sqlite3.OperationalError):
                self.create()
        self.assertFalse(self.workspace.exists())

    def test_failed_outcome_save_leaves_running_record(self):
        original = history.save_action
        def save(action_id, result):
            if result["status"] == "executed":
                raise sqlite3.OperationalError("disk full")
            original(action_id, result)
        with patch.object(history, "save_action", side_effect=save):
            with self.assertRaises(sqlite3.OperationalError):
                self.create()
        self.assertTrue((self.workspace / "note.txt").exists())
        self.assertEqual(history.all_actions()[0]["status"], "running")
        with self.assertRaises(RuntimeError):
            self.create("later.txt")

    def test_undo_failure_blocks_future_modifications(self):
        self.create()
        action = self.edit("hello", "updated")
        with patch.object(hg, "_replace_text", side_effect=OSError("disk full")):
            with self.assertRaises(RuntimeError):
                hg.undo_latest_action(action["action_id"])
        self.assertEqual(history.all_actions()[-1]["status"], "undo_failed")
        with self.assertRaises(RuntimeError):
            self.create("later.txt")

    def test_corrupt_checkpoint_does_not_modify_file(self):
        self.create()
        action = self.edit("hello", "updated")
        path = self.storage / (action["checkpoint_id"] + ".json")
        checkpoint = json.loads(path.read_text())
        checkpoint["files"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(checkpoint))
        with self.assertRaisesRegex(ValueError, "verification"):
            hg.undo_latest_action(action["action_id"])
        self.assertEqual((self.workspace / "note.txt").read_text(), "updated")

    def test_disabled_tools_and_bulk_edits(self):
        for tool in ("overwrite_text_file", "delete_file", "move_file"):
            self.assertEqual(hg.execute_tool(tool, {})["status"], "blocked")
        self.create()
        result = hg.execute_tool("edit_text_file", {
            "filename": "note.txt", "old_text": "hello", "new_text": "bye",
            "replace_all": True,
        })
        self.assertEqual(result["status"], "blocked")
        self.assertEqual((self.workspace / "note.txt").read_text(), "hello")

    def test_batch_calls_are_blocked_then_single_calls_execute(self):
        with patch("ollama.chat", side_effect=[
            response(calls=[create_call("a.txt"), create_call("b.txt")]),
            response(calls=[create_call("a.txt")]),
            response(calls=[create_call("b.txt")]),
            response(content="Created both"),
        ]):
            packet = hg.run_ollama_test("Create two files")
        self.assertEqual([a["status"] for a in packet["actions"]],
                         ["blocked", "blocked", "executed", "executed"])
        self.assertEqual(len(history.groups()), 1)
        self.assertEqual(len(list(self.storage.glob("*.json"))), 2)

    def test_partial_helper_validation_keeps_good_suggestions(self):
        good = {"operation": "create", "title": "Create notes file", "target": "note.txt",
                "supporting_text": "create note.txt", "reason": "Save a note"}
        marks, errors = hg.normalize_checkpoint_json_partial(
            json.dumps([good, {**good, "title": "bad"}]), "agent", "create note.txt")
        self.assertEqual(len(marks), 1)
        self.assertEqual(len(errors), 1)
        self.assertTrue(marks[0]["evidence_verified"])

    def test_read_search_and_stale_hash(self):
        self.create()
        read = hg.execute_tool("read_text_file", {"filename": "note.txt"})
        matches = hg.execute_tool("search_text_files", {"query": "hello"})
        self.assertEqual(matches["matches"][0]["filename"], "note.txt")
        (self.workspace / "note.txt").write_text("manual")
        result = hg.execute_tool("edit_text_file", {
            "filename": "note.txt", "old_text": "manual", "new_text": "changed",
            "expected_sha256": read["sha256"],
        })
        self.assertEqual(result["status"], "blocked")
        self.assertEqual((self.workspace / "note.txt").read_text(), "manual")



    def staged_file(self, filename="game.py"):
        content = ("import math\n\ndef jump():\n    return 1\n\n"
                   "def update():\n    return jump() + 1\n\n"
                   "if __name__ == '__main__':\n    print(update())\n")
        result = hg.execute_tool("create_text_file", {"filename": filename, "content": content})
        return content, result

    def test_python_creation_has_real_function_checkpoints(self):
        content, result = self.staged_file()
        self.assertEqual(result["status"], "executed")
        self.assertEqual([a["stage_title"] for a in result["actions"]],
                         ["Create file and setup", "Add jump()", "Add update()", "Finish file and entry point"])
        self.assertEqual((self.workspace / "game.py").read_text(), content)
        self.assertEqual(len(list(self.storage.glob("*.json"))), 4)
        jump = result["actions"][1]
        restored = hg.restore_file_stage(jump["action_id"])
        text = (self.workspace / "game.py").read_text()
        self.assertIn("def jump():", text)
        self.assertNotIn("def update():", text)
        self.assertEqual(len(restored["undone_action_ids"]), 2)
        self.assertTrue(history.history_payload()["checkpoints"][0]["actions"][0]["stage_restore_supported"])

    def test_staged_model_result_is_flattened_into_actions(self):
        code = "def a():\n    return 1\n\ndef b():\n    return 2\n"
        with patch("ollama.chat", side_effect=[
            response(calls=[create_call("code.py", code)]), response(content="Saved"),
        ]):
            packet = hg.run_ollama_test("Create functions a and b")
        self.assertEqual(len(packet["actions"]), 3)
        self.assertTrue(all("checkpoint_id" in action for action in packet["actions"]))
        self.assertEqual(len(history.groups()), 1)

    def test_stage_restore_leaves_other_files_untouched(self):
        _, result = self.staged_file()
        self.create("other.txt")
        hg.restore_file_stage(result["actions"][1]["action_id"])
        self.assertEqual((self.workspace / "other.txt").read_text(), "hello")
        self.assertEqual(history.latest_modification()["target"], "other.txt")

    def test_stage_restore_includes_later_tasks_for_same_file(self):
        _, result = self.staged_file()
        read = hg.execute_tool("read_text_file", {"filename": "game.py"})
        hg.execute_tool("append_text_file", {"filename": "game.py", "content": "# later task\n",
                                             "expected_sha256": read["sha256"]})
        restored = hg.restore_file_stage(result["actions"][1]["action_id"])
        self.assertEqual(len(restored["undone_action_ids"]), 3)
        self.assertNotIn("later task", (self.workspace / "game.py").read_text())

    def test_stage_restore_preflights_entire_chain(self):
        content, result = self.staged_file()
        checkpoint = self.storage / (result["actions"][2]["checkpoint_id"] + ".json")
        record = json.loads(checkpoint.read_text())
        record["files"][0]["sha256"] = "0" * 64
        checkpoint.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            hg.restore_file_stage(result["actions"][0]["action_id"])
        self.assertEqual((self.workspace / "game.py").read_text(), content)
        self.assertTrue(all(a["status"] == "executed" for a in history.all_actions()))

    def test_stage_restore_conflicts_and_http_contract(self):
        _, result = self.staged_file()
        client = TestClient(server.app)
        selected = result["actions"][1]["action_id"]
        response = client.post("/restore", json={"action_id": selected, "keep_stage": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post("/restore", json={"action_id": selected, "keep_stage": True}).status_code, 409)
        (self.workspace / "game.py").write_text("# manual change")
        response = client.post("/restore", json={"action_id": result["actions"][0]["action_id"], "keep_stage": True})
        self.assertEqual(response.status_code, 409)
        self.assertEqual((self.workspace / "game.py").read_text(), "# manual change")

    def test_python_methods_decorators_and_non_python_fallback(self):
        import ast
        code = ("class Bird:\n    @staticmethod\n    def jump():\n        return 1\n\n"
                "    async def update(self):\n        return 2\n")
        stages = hg.python_stages("bird.py", code)
        self.assertEqual([title for title, _ in stages],
                         ["Create file and setup", "Add Bird.jump()", "Add Bird.update()"])
        for _, prefix in stages:
            ast.parse(prefix)
        self.assertEqual(stages[-1][1], code)
        self.assertEqual(hg.python_stages("notes.txt", code), [])
        self.assertEqual(hg.python_stages("broken.py", "def invalid("), [])

    def test_stage_failure_stops_later_writes(self):
        original = hg._write_checkpoint
        count = 0
        def write(path, checkpoint):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError("disk full")
            original(path, checkpoint)
        with patch.object(hg, "_write_checkpoint", side_effect=write):
            _, result = self.staged_file()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["actions"]), 3)
        self.assertIn("def jump", (self.workspace / "game.py").read_text())
        self.assertNotIn("def update", (self.workspace / "game.py").read_text())


if __name__ == "__main__":
    unittest.main()

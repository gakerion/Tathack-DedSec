import json
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


def response(thinking="", content="", calls=None):
    message = Mock()
    message.thinking = thinking
    message.content = content
    message.tool_calls = calls or []
    message.model_dump.return_value = {"role": "assistant", "content": content}
    return SimpleNamespace(message=message)


def create_call(filename="note.txt", content="hello"):
    return SimpleNamespace(
        function=SimpleNamespace(
            name="create_text_file",
            arguments={"filename": filename, "content": content},
        )
    )


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.storage = self.root / "checkpoints"
        for name, value in (
            ("WORKSPACE", self.workspace),
            ("CHECKPOINTS", self.storage),
        ):
            change = patch.object(hg, name, value)
            change.start()
            self.addCleanup(change.stop)
        server.checkpoints.clear()

    def create(self, filename="note.txt"):
        return hg.execute_tool(
            "create_text_file", {"filename": filename, "content": "hello"}
        )

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
        self.assertFalse(result["restore_supported"])
        self.assertEqual(result["constants"]["R"], 1.0)

    def test_failed_checkpoint_blocks_creation(self):
        for error in (OSError("disk full"), ValueError("verification failed")):
            with self.subTest(error=error), patch.object(
                hg, "_write_checkpoint", side_effect=error
            ):
                result = self.create()
            self.assertEqual(result["status"], "blocked")
            self.assertFalse((self.workspace / "note.txt").exists())

    def test_corrupt_checkpoint_readback_blocks_creation(self):
        with patch.object(Path, "read_text", return_value="{}"):
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
        for name in (
            "../escape.txt",
            "C:\\escape.txt",
            "a/b",
            "a:b",
            "NUL.txt",
            "COM1",
            "LPT¹.txt",
            "bad.",
            "bad ",
            "",
            ".",
            "..",
            "bad\x00.txt",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.create(name)["status"], "blocked")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_unknown_tools_and_invalid_arguments(self):
        self.assertEqual(hg.execute_tool("delete", {})["status"], "blocked")
        for args in (
            {},
            {"filename": "x", "content": 4},
            {"filename": "x", "content": "ok", "shell": "anything"},
        ):
            self.assertEqual(
                hg.execute_tool("create_text_file", args)["status"], "blocked"
            )

    def test_overlapping_storage_blocked(self):
        with patch.object(hg, "CHECKPOINTS", self.workspace):
            self.assertEqual(self.create()["status"], "blocked")

    def test_helper_descriptions_ignore_invented_facts(self):
        item = {
            "operation": "create",
            "title": "Create notes file",
            "target": "note.txt",
            "supporting_text": "create note.txt",
            "reason": "Save the note",
            "importance": 0.001,
            "affected_count": 9000,
            "backup_verified": True,
            "automatic_restore_supported": True,
        }
        marks = hg.normalize_checkpoint_json(
            json.dumps([item]), "agent", "I will create  note.txt"
        )
        self.assertIsInstance(marks, list)
        self.assertTrue(marks[0]["evidence_verified"])
        self.assertNotIn("importance", marks[0])
        self.assertNotIn("affected_count", marks[0])
        self.assertNotIn("backup_verified", marks[0])
        item["supporting_text"] = "invented quote"
        self.assertFalse(
            hg.normalize_checkpoint_json(json.dumps([item]), "agent", "other")[0][
                "evidence_verified"
            ]
        )
        item["title"] = "Short"
        with self.assertRaises(ValueError):
            hg.normalize_checkpoint_json(json.dumps([item]), "agent", "other")

    def test_no_tool_calls_means_no_actions_even_with_reasoning(self):
        with patch(
            "ollama.chat", return_value=response("I will create note.txt", "A plan")
        ), patch.object(hg, "suggest_checkpoint_marks", return_value=[]):
            packet = hg.run_ollama_test("Plan a file")
        self.assertEqual(packet["actions"], [])
        self.assertFalse(self.workspace.exists())

    def test_dict_return_preserves_actions_after_helper_failure_without_report(self):
        old_cwd = Path.cwd()
        os.chdir(self.root)
        try:
            with patch(
                "ollama.chat",
                side_effect=[
                    response("I will create note.txt", calls=[create_call()]),
                    response(content="Created"),
                ],
            ), patch.object(
                hg,
                "suggest_checkpoint_marks",
                side_effect=ValueError("bad helper JSON"),
            ):
                packet = hg.run_ollama_test("Create note.txt")
            self.assertIsInstance(packet, dict)
            self.assertEqual(packet["actions"][0]["status"], "executed")
            self.assertEqual(packet["helper_error"], "bad helper JSON")
            self.assertEqual(packet["checkpoint_marks"], [])
            self.assertEqual(packet["output"], "Created")
            self.assertEqual(
                {p.name for p in self.root.iterdir()}, {"workspace", "checkpoints"}
            )
            json.dumps(packet, allow_nan=False)
        finally:
            os.chdir(old_cwd)

    def test_later_agent_error_keeps_executed_actions(self):
        with patch(
            "ollama.chat",
            side_effect=[response(calls=[create_call()]), RuntimeError("offline")],
        ):
            packet = hg.run_ollama_test("Create note.txt")
        self.assertEqual(packet["actions"][0]["status"], "executed")
        self.assertEqual(packet["agent_error"], "offline")

    def test_turn_limit_returns_prior_actions(self):
        with patch("ollama.chat", return_value=response(calls=[create_call()])):
            packet = hg.run_ollama_test("Create note.txt")
        self.assertEqual(len(packet["actions"]), 6)
        self.assertEqual(packet["actions"][0]["status"], "executed")
        self.assertEqual(packet["agent_error"], "Agent turn limit reached.")

    def test_http_payload_history_and_unsupported_restore(self):
        client = TestClient(server.app)
        self.assertEqual(client.get("/checkpoints").json()["checkpoints"], [])
        with patch(
            "ollama.chat",
            side_effect=[response(calls=[create_call()]), response(content="Created")],
        ):
            reply = client.post("/chat", data={"prompt": "Create note.txt"})
        self.assertEqual(reply.status_code, 200)
        data = reply.json()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["result"], data["output"])
        self.assertEqual(data["actions"][0]["status"], "executed")
        self.assertIn("helper_error", data)
        history = client.get("/checkpoints").json()
        self.assertFalse(history["history_persistent"])
        self.assertEqual(
            history["checkpoints"][0]["commits"][0]["checkpoint_id"],
            data["actions"][0]["checkpoint_id"],
        )
        self.assertEqual(client.post("/restore?commit_hash=anything").status_code, 501)
        self.assertEqual(client.post("/chat", data={"prompt": " "}).status_code, 422)
        self.assertEqual(
            client.post(
                "/chat", data={"prompt": "Hi"}, files={"file": ("x.txt", b"hello")}
            ).status_code,
            422,
        )

    def test_importance_formula_and_validation(self):
        score = calculate_importance("create", 1, impact="local", backup_verified=True)
        expected = round(0.35 * 0.25 + 0.30 + 0.20 * math.log1p(1) / math.log1p(10), 3)
        self.assertEqual(score["importance"], expected)
        self.assertEqual(calculate_importance("read", 100)["importance"], 0)
        self.assertEqual(calculate_importance("delete", 0)["importance"], 0)
        self.assertEqual(calculate_importance("delete", 100)["constants"]["S"], 1)
        self.assertEqual(
            calculate_importance(
                "create", 1, backup_verified=True, automatic_restore_supported=True
            )["constants"]["R"],
            0,
        )
        for kwargs in (
            {"operation": "unknown"},
            {"impact": "bad"},
            {"affected_count": True},
            {"scope_threshold": 0},
            {"backup_verified": "true"},
            {"weights": {"C": float("nan"), "R": 0, "S": 0, "E": 0}},
        ):
            values = {"operation": "create", "affected_count": 1, **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                calculate_importance(**values)


if __name__ == "__main__":
    unittest.main()

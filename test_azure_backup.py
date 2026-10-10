"""Exercise Azure failure/recovery paths with an in-memory blob store, never real credentials."""
import json
import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

import action_history as history
import azure_backup as backup
import checkpoint_helper as hg


class FakeBlob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def upload_blob(self, data, overwrite=False):
        if self.name in self.store and not overwrite:
            raise ResourceExistsError("Already exists")
        self.store[self.name] = data

    def download_blob(self):
        return self

    def readall(self):
        if self.name not in self.store:
            error = ResourceNotFoundError("Missing blob")
            error.error_code = "BlobNotFound"
            raise error
        return self.store[self.name]


class AzureBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = {}
        patches = [
            patch.dict(os.environ, {"HONEYGATE_BACKUP_MODE": "azure",
                                   "AZURE_STORAGE_CONNECTION_STRING": "test-secret"}),
            patch.object(history, "DATABASE", self.root / "history.sqlite3"),
            patch.object(hg, "WORKSPACE", self.root / "workspace"),
            patch.object(hg, "CHECKPOINTS", self.root / "checkpoints"),
            patch.object(backup, "_blob", side_effect=lambda name: FakeBlob(self.store, name)),
        ]
        for change in patches:
            change.start()
            self.addCleanup(change.stop)

    def create(self):
        return hg.execute_tool("create_text_file", {"filename": "note.txt", "content": "hello"})

    def test_initial_backup_contains_existing_workspace_before_first_change(self):
        (hg.WORKSPACE / ".git").mkdir(parents=True)
        (hg.WORKSPACE / ".git" / "index").write_bytes(b"\x00\xff")
        (hg.WORKSPACE / "existing.txt").write_text("original")
        original = backup.upload_json

        def upload(name, data, overwrite=False):
            if name == "workspace/initial.json":
                self.assertFalse((hg.WORKSPACE / "note.txt").exists())
            return original(name, data, overwrite)

        with patch.object(backup, "upload_json", side_effect=upload):
            first = self.create()
        self.assertEqual(first["status"], "executed")
        baseline = backup.download_json("workspace/initial.json")
        self.assertIn(".git", baseline["directories"])
        self.assertEqual(base64.b64decode(baseline["files"][".git/index"]["content_base64"]), b"\x00\xff")
        self.assertEqual(base64.b64decode(baseline["files"]["existing.txt"]["content_base64"]), b"original")
        self.assertNotIn("note.txt", baseline["files"])
        second = hg.execute_tool("create_text_file", {"filename": "later.txt", "content": "later"})
        self.assertEqual(second["status"], "executed")
        self.assertEqual(backup.download_json("workspace/initial.json"), baseline)

    def test_initial_backup_failure_blocks_first_change(self):
        self.store["history/latest.json"] = json.dumps({"schema_version": 1, "tasks": []}).encode()
        with patch.object(backup, "upload_json", side_effect=backup.BackupError("Offline")):
            with self.assertRaises(backup.BackupError):
                self.create()
        self.assertFalse((hg.WORKSPACE / "note.txt").exists())
        self.assertEqual(history.all_actions(), [])

    def test_initial_backup_rejects_linked_workspace_content(self):
        hg.WORKSPACE.mkdir()
        target = self.root / "outside.txt"
        target.write_text("outside")
        try:
            (hg.WORKSPACE / "linked.txt").symlink_to(target)
        except OSError:
            self.skipTest("Windows account cannot create symlinks")
        with self.assertRaises(backup.BackupError):
            self.create()
        self.assertFalse((hg.WORKSPACE / "note.txt").exists())

    def test_checkpoint_verified_before_creation(self):
        original = backup.upload_json
        verified = []
        def upload(name, data, overwrite=False):
            if name.startswith("checkpoints/"):
                self.assertFalse((hg.WORKSPACE / "note.txt").exists())
            result = original(name, data, overwrite)
            verified.append(name)
            return result
        with patch.object(backup, "upload_json", side_effect=upload):
            action = self.create()
        self.assertIn(f"checkpoints/{action['checkpoint_id']}.json", verified)
        remote = json.loads(self.store["history/latest.json"])
        self.assertEqual(remote["tasks"][0]["actions"][0]["status"], "executed")

    def test_checkpoint_upload_failure_blocks_file_write(self):
        original = backup.upload_json
        def upload(name, data, overwrite=False):
            if name.startswith("checkpoints/"):
                raise backup.BackupError("Offline")
            return original(name, data, overwrite)
        with patch.object(backup, "upload_json", side_effect=upload):
            result = self.create()
        self.assertEqual(result["status"], "blocked")
        self.assertFalse((hg.WORKSPACE / "note.txt").exists())

    def test_upload_readback_mismatch_blocks_creation(self):
        original = FakeBlob.readall
        def download(blob):
            if blob.name.startswith("checkpoints/"):
                return b"corrupt"
            return original(blob)
        with patch.object(FakeBlob, "readall", download):
            result = self.create()
        self.assertEqual(result["status"], "blocked")
        self.assertFalse((hg.WORKSPACE / "note.txt").exists())

    def test_rebuild_missing_database_and_download_checkpoint_for_undo(self):
        action = self.create()
        history.DATABASE.unlink()
        (hg.CHECKPOINTS / f"{action['checkpoint_id']}.json").unlink()
        payload = history.history_payload()
        self.assertEqual(payload["checkpoints"][0]["actions"][0]["action_id"], action["action_id"])
        hg.undo_latest_action(action["action_id"])
        self.assertFalse((hg.WORKSPACE / "note.txt").exists())
        self.assertEqual(json.loads(self.store["history/latest.json"])["tasks"][0]["actions"][0]["status"], "undone")

    def test_history_outage_preserves_real_result_and_can_be_retried(self):
        original = backup.upload_json
        def upload(name, data, overwrite=False):
            if name == "history/latest.json" and any(
                a["status"] == "executed" for task in data["tasks"] for a in task["actions"]
            ):
                raise backup.BackupError("Offline")
            return original(name, data, overwrite)
        with patch.object(backup, "upload_json", side_effect=upload):
            with self.assertRaises(backup.BackupError):
                self.create()
        self.assertEqual(history.all_actions()[0]["status"], "executed")
        self.assertTrue((hg.WORKSPACE / "note.txt").exists())
        with self.assertRaises(backup.BackupError):
            history.require_safe_history()
        history.sync_backup()
        history.require_safe_history()
        self.assertFalse(history.backup_pending())

    def test_failed_intent_upload_does_not_leave_running_action(self):
        original = backup.upload_json
        def upload(name, data, overwrite=False):
            if name == "history/latest.json" and any(task["actions"] for task in data["tasks"]):
                raise backup.BackupError("Offline")
            return original(name, data, overwrite)
        with patch.object(backup, "upload_json", side_effect=upload):
            with self.assertRaises(backup.BackupError):
                self.create()
        self.assertFalse(hg.WORKSPACE.exists())
        self.assertEqual(history.all_actions()[0]["status"], "blocked")
        history.sync_backup()
        history.require_safe_history()

    def test_failed_undo_intent_upload_does_not_change_file(self):
        action = self.create()
        original = backup.upload_json
        def upload(name, data, overwrite=False):
            if name == "history/latest.json" and any(
                a["status"] == "undoing" for task in data["tasks"] for a in task["actions"]
            ):
                raise backup.BackupError("Offline")
            return original(name, data, overwrite)
        with patch.object(backup, "upload_json", side_effect=upload):
            with self.assertRaises(backup.BackupError):
                hg.undo_latest_action(action["action_id"])
        self.assertEqual((hg.WORKSPACE / "note.txt").read_text(), "hello")
        self.assertEqual(history.all_actions()[0]["status"], "executed")
        history.sync_backup()
        hg.undo_latest_action(action["action_id"])

    def test_existing_checkpoint_is_never_overwritten(self):
        backup.upload_json("checkpoints/example.json", {"old": "content"})
        backup.upload_json("checkpoints/example.json", {"old": "content"})
        with self.assertRaises(backup.BackupError):
            backup.upload_json("checkpoints/example.json", {"new": "content"})
        self.assertEqual(backup.download_json("checkpoints/example.json"), {"old": "content"})

    def test_sdk_error_does_not_expose_credentials(self):
        with patch.object(backup, "_blob", side_effect=ValueError("test-secret")):
            with self.assertRaises(backup.BackupError) as error:
                backup.upload_json("example.json", {})
        self.assertNotIn("test-secret", str(error.exception))

    def test_corrupt_history_does_not_initialize_empty_database(self):
        self.store["history/latest.json"] = b'{"schema_version":999}'
        for _ in range(2):
            with self.assertRaises(backup.BackupError):
                history.groups()
        self.assertEqual(self.store["history/latest.json"], b'{"schema_version":999}')

    def test_upload_existing_local_checkpoints(self):
        with patch.dict(os.environ, {"HONEYGATE_BACKUP_MODE": "local"}):
            action = self.create()
        backup.backup_existing_checkpoints(hg.CHECKPOINTS)
        history.sync_backup()
        self.assertIn(f"checkpoints/{action['checkpoint_id']}.json", self.store)

    def test_titles_survive_azure_recovery(self):
        task = history.start_task("A long original request for a new file")
        history.set_task_title(task, "Create the requested file")
        history.DATABASE.unlink()
        group = history.groups()[0]
        self.assertEqual(group["title"], "Create the requested file")
        self.assertEqual(group["prompt"], "A long original request for a new file")

    def test_old_azure_history_without_titles_still_loads(self):
        prompt = "An original request from before short headings were added"
        self.store["history/latest.json"] = json.dumps({"schema_version": 1,
            "tasks": [{"task_id": 1, "prompt": prompt, "actions": []}]}).encode()
        self.assertEqual(history.groups()[0]["title"], history.short_title(prompt))

    def test_failed_undo_outcome_upload_preserves_completed_undo(self):
        action = self.create()
        original = backup.upload_json
        def upload(name, data, overwrite=False):
            if name == "history/latest.json" and any(
                a["status"] == "undone" for task in data["tasks"] for a in task["actions"]
            ):
                raise backup.BackupError("Offline")
            return original(name, data, overwrite)
        with patch.object(backup, "upload_json", side_effect=upload):
            with self.assertRaises(backup.BackupError):
                hg.undo_latest_action(action["action_id"])
        self.assertFalse((hg.WORKSPACE / "note.txt").exists())
        self.assertEqual(history.all_actions()[0]["status"], "undone")
        history.sync_backup()
        history.require_safe_history()


class SettingsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = Path(directory.name) / "azure_config.json"
        for change in (patch.object(backup, "CONFIG_FILE", self.config),
                       patch.dict(os.environ, {}, clear=True)):
            change.start()
            self.addCleanup(change.stop)

    def test_saved_settings_enable_azure_and_configure_client(self):
        self.config.write_text(json.dumps({"connection_string": "test-only-secret",
                                          "container": "honeygate", "prefix": "demo"}))
        self.assertTrue(backup.enabled())
        with patch("azure.storage.blob.BlobClient.from_connection_string") as factory:
            backup._blob("history/latest.json")
        self.assertEqual(factory.call_args.args[0], "test-only-secret")
        self.assertEqual(factory.call_args.kwargs["container_name"], "honeygate")
        self.assertEqual(factory.call_args.kwargs["blob_name"], "demo/history/latest.json")
        self.assertNotIn("test-only-secret", str(backup.status()))

    def test_blank_or_missing_config_keeps_local_mode(self):
        self.assertFalse(backup.enabled())
        self.config.write_text('{"connection_string":""}')
        self.assertFalse(backup.enabled())

    def test_environment_can_override_saved_settings(self):
        self.config.write_text('{"connection_string":"test-only-secret"}')
        with patch.dict(os.environ, {"HONEYGATE_BACKUP_MODE": "local"}):
            self.assertFalse(backup.enabled())

    def test_invalid_settings_do_not_leak_contents_or_fall_back(self):
        for text in ('test-only-secret', '[]', '{"connection_string":123}'):
            self.config.write_text(text)
            with self.assertRaises(backup.BackupError) as error:
                backup.enabled()
            self.assertNotIn("test-only-secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()

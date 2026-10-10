import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import git

import checkpoint_helper as hg


class GitCommitBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.workspace = root / "workspace"
        self.checkpoints = root / "checkpoints"
        self.workspace.mkdir()

        self.repository = git.Repo.init(self.workspace)
        with self.repository.config_writer() as config:
            config.set_value("user", "name", "HoneyGate Tests")
            config.set_value("user", "email", "tests@example.com")

        self.workspace_patch = patch.object(hg, "WORKSPACE", self.workspace)
        self.checkpoints_patch = patch.object(hg, "CHECKPOINTS", self.checkpoints)
        self.push_patch = patch.object(hg, "push_git")
        self.workspace_patch.start()
        self.checkpoints_patch.start()
        self.push_patch.start()
        self.addCleanup(self.workspace_patch.stop)
        self.addCleanup(self.checkpoints_patch.stop)
        self.addCleanup(self.push_patch.stop)

    def tearDown(self):
        self.repository.close()

    def repo(self):
        return self.repository

    def commits(self):
        repo = self.repo()
        if not repo.head.is_valid():
            return []
        return list(repo.iter_commits())

    def execute(self, name, arguments):
        return hg.execute_tool(name, arguments)

    def create(self, filename="note.txt", content="hello"):
        return self.execute(
            "create_text_file",
            {"filename": filename, "content": content},
        )

    def test_read_and_search_operations_do_not_create_commits(self):
        (self.workspace / "note.txt").write_text("hello", encoding="utf-8")

        read_result = self.execute(
            "read_text_file",
            {"filename": "note.txt"},
        )
        list_result = self.execute("list_workspace_files", {})
        search_result = self.execute(
            "search_text_files",
            {"query": "hello"},
        )

        self.assertEqual(read_result["status"], "executed")
        self.assertEqual(list_result["status"], "executed")
        self.assertEqual(search_result["status"], "executed")
        self.assertEqual(self.commits(), [])

    def test_each_successful_mutation_creates_one_commit(self):
        create_result = self.create()
        self.assertEqual(create_result["status"], "executed")
        self.assertEqual(len(self.commits()), 1)

        edit_result = self.execute(
            "edit_text_file",
            {
                "filename": "note.txt",
                "old_text": "hello",
                "new_text": "updated",
            },
        )
        self.assertEqual(edit_result["status"], "executed")
        self.assertEqual(len(self.commits()), 2)

        overwrite_result = self.execute(
            "overwrite_text_file",
            {"filename": "note.txt", "content": "overwritten"},
        )
        self.assertEqual(overwrite_result["status"], "executed")
        self.assertEqual(len(self.commits()), 3)

        move_result = self.execute(
            "move_file",
            {"source": "note.txt", "destination": "moved.txt"},
        )
        self.assertEqual(move_result["status"], "executed")
        self.assertEqual(len(self.commits()), 4)

        delete_result = self.execute(
            "delete_file",
            {"filename": "moved.txt"},
        )
        self.assertEqual(delete_result["status"], "executed")
        self.assertEqual(len(self.commits()), 5)

    def test_multiple_mutations_create_separate_commits(self):
        first = self.create("first.txt", "one")
        second = self.create("second.txt", "two")

        self.assertEqual(first["status"], "executed")
        self.assertEqual(second["status"], "executed")
        self.assertEqual(len(self.commits()), 2)
        self.assertNotEqual(
            first["git_commit_hash"],
            second["git_commit_hash"],
        )

    def test_large_creation_requires_incremental_mutations(self):
        result = self.create(content="x" * (hg.MAX_INCREMENTAL_CREATE_BYTES + 1))

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["incremental_required"])
        self.assertEqual(result["max_initial_bytes"], 4096)
        self.assertEqual(self.commits(), [])
        self.assertFalse((self.workspace / "note.txt").exists())

    def test_large_edits_require_incremental_mutations(self):
        self.create("note.txt", "scaffold")
        before = (self.workspace / "note.txt").read_text(encoding="utf-8")

        result = self.execute(
            "edit_text_file",
            {
                "filename": "note.txt",
                "old_text": before,
                "new_text": "x" * (hg.MAX_INCREMENTAL_WRITE_BYTES + 1),
            },
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["incremental_required"])
        self.assertEqual(result["max_write_bytes"], hg.MAX_INCREMENTAL_WRITE_BYTES)
        self.assertEqual(len(self.commits()), 1)
        self.assertEqual(
            (self.workspace / "note.txt").read_text(encoding="utf-8"),
            before,
        )

    def test_large_overwrites_require_incremental_mutations(self):
        self.create("note.txt", "scaffold")

        result = self.execute(
            "overwrite_text_file",
            {
                "filename": "note.txt",
                "content": "x" * (hg.MAX_INCREMENTAL_WRITE_BYTES + 1),
            },
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["incremental_required"])
        self.assertEqual(len(self.commits()), 1)

    def test_move_commit_contains_both_paths(self):
        source = self.workspace / "source.txt"
        source.write_text("content", encoding="utf-8")
        repo = self.repo()
        repo.index.add(["source.txt"])
        repo.index.commit("Seed source")

        result = self.execute(
            "move_file",
            {"source": "source.txt", "destination": "destination.txt"},
        )

        self.assertEqual(result["status"], "executed")
        commit = self.repo().commit(result["git_commit_hash"])
        self.assertEqual(
            [entry.path for entry in commit.tree],
            ["destination.txt"],
        )
        self.assertEqual(commit.stats.total["files"], 2)
        self.assertEqual(commit.message.strip(), "Move source.txt to destination.txt")
        diff_summary = self.repo().git.show(
            "--name-status",
            "--format=",
            commit.hexsha,
        )
        self.assertIn("source.txt", diff_summary)
        self.assertIn("destination.txt", diff_summary)

    def test_unrelated_files_are_not_included(self):
        unrelated = self.workspace / "unrelated.txt"
        unrelated.write_text("unrelated", encoding="utf-8")
        repo = self.repo()
        repo.index.add(["unrelated.txt"])

        result = self.create("target.txt", "target")

        self.assertEqual(result["status"], "executed")
        commit = self.repo().commit(result["git_commit_hash"])
        self.assertEqual([entry.path for entry in commit.tree], ["target.txt"])
        self.assertTrue(unrelated.exists())
        self.assertIn("unrelated.txt", self.repo().git.diff("--cached", "--name-only"))

    def test_app_startup_is_tolerant_of_unavailable_ai_models(self):
        from fastapi.testclient import TestClient

        import server as app_module

        with patch.object(app_module, "get_helper", side_effect=RuntimeError("offline")):
            with patch.object(app_module.ollama, "chat", side_effect=RuntimeError("offline")):
                with TestClient(app_module.app):
                    pass

    def test_low_importance_mutation_still_creates_commit(self):
        low_importance_facts = {
            "affected_count": 1,
            "impact": "local",
            "checkpoint_verified": True,
            "backup_verified": True,
            "automatic_restore_supported": False,
            "manual_restore_supported": False,
            "reversible": True,
            "restore_supported": False,
            "importance": 0.1,
            "constants": {},
            "weights_used": {},
            "recovery_status": "unknown",
            "provisional": True,
        }
        with patch.object(hg, "_facts", return_value=low_importance_facts):
            result = self.create()

        self.assertLess(result["importance"], 0.4)
        self.assertEqual(result["status"], "executed")
        self.assertEqual(len(self.commits()), 1)

    def test_blocked_and_failed_mutations_do_not_create_commits(self):
        self.assertEqual(self.create()["status"], "executed")
        blocked = self.create()
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(len(self.commits()), 1)

        with patch.object(hg, "_write_checkpoint", side_effect=OSError("disk full")):
            failed = self.create("failed.txt")
        self.assertEqual(failed["status"], "blocked")
        self.assertEqual(len(self.commits()), 1)

    def test_git_commit_error_is_explicit_and_preserves_mutation(self):
        with patch.object(hg, "commit_changes", side_effect=RuntimeError("git failed")):
            result = self.create()

        self.assertEqual(result["status"], "executed")
        self.assertTrue(result["state_changed"])
        self.assertTrue((self.workspace / "note.txt").exists())
        self.assertEqual(result["git_error"], "git failed")
        self.assertNotIn("git_commit_hash", result)
        self.assertEqual(self.commits(), [])

    def test_returned_hash_is_a_git_hash_not_a_checkpoint_id(self):
        result = self.create()

        commit = self.repo().commit(result["git_commit_hash"])
        self.assertEqual(result["git_commit_hash"], commit.hexsha)
        self.assertNotEqual(result["git_commit_hash"], result["checkpoint_id"])
        self.assertEqual(commit.message.strip(), "Create note.txt")


if __name__ == "__main__":
    unittest.main()

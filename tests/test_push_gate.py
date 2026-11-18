"""The push gate hook and the stamp written by the full check."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import check as verify
import pre_push_gate


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


class IsGuardedTests(unittest.TestCase):
    def test_push_and_pr_commands_are_guarded(self):
        for command in (
            "git push",
            "git -C . push origin main",
            "git -c k=v push",
            "gh pr create --fill",
            "gh  pr  create",
            "gh -R o/r pr create",
            "gh api -X POST repos/o/r/pulls",
            "FOO=1 git push",
            "make && git push",
            "echo hi; git push",
            "sudo git push",
            "env FOO=1 git push",
            "/usr/bin/git push",
            "gh pr merge 12 --admin",
            "true & git push",
            "(git push)",
        ):
            with self.subTest(command=command):
                self.assertTrue(pre_push_gate.is_guarded("Bash", {"command": command}))

    def test_other_commands_are_not_guarded(self):
        for command in (
            "ls",
            "git status",
            "grep 'git push' AGENTS.md",
            "echo git push",
            "git commit -m push",
            "git branch push-fix",
            "git --no-pager branch push-fix",
        ):
            with self.subTest(command=command):
                self.assertFalse(pre_push_gate.is_guarded("Bash", {"command": command}))

    def test_many_options_do_not_backtrack(self):
        command = "git " + " ".join(f"--option-{i}" for i in range(40)) + " log"
        started = time.monotonic()
        self.assertFalse(pre_push_gate.is_guarded("Bash", {"command": command}))
        self.assertLess(time.monotonic() - started, 1.0)

    def test_remote_writing_tools_are_guarded(self):
        for tool in (
            "mcp__github__create_pull_request",
            "mcp__github__push_files",
            "mcp__github__create_or_update_file",
            "mcp__github__merge_pull_request",
        ):
            self.assertTrue(pre_push_gate.is_guarded(tool, {}))
        self.assertFalse(pre_push_gate.is_guarded("Read", {}))

    def test_odd_payloads_do_not_crash(self):
        self.assertFalse(pre_push_gate.is_guarded("Bash", None))
        self.assertFalse(pre_push_gate.is_guarded("Bash", {"command": None}))
        self.assertFalse(pre_push_gate.is_guarded("Bash", "git push"))
        self.assertFalse(pre_push_gate.is_guarded("Bash", ["git", "push"]))


class StampTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q")
        (self.root / "a.txt").write_text("a")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "init")

    def test_stamp_written_on_clean_head_and_gate_accepts_it(self):
        self.assertTrue(verify._stamp_head(self.root))
        self.assertTrue(pre_push_gate.stamp_matches_head(self.root))

    def test_new_commit_makes_the_stamp_stale(self):
        verify._stamp_head(self.root)
        (self.root / "b.txt").write_text("b")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "second")
        self.assertFalse(pre_push_gate.stamp_matches_head(self.root))

    def test_dirty_tree_is_not_stamped(self):
        (self.root / "a.txt").write_text("changed")
        self.assertFalse(verify._stamp_head(self.root))
        self.assertFalse(pre_push_gate.stamp_matches_head(self.root))

    def test_head_that_moved_during_the_checks_is_not_stamped(self):
        self.assertFalse(verify._stamp_head(self.root, expected_head="0" * 40))

    def test_not_a_git_checkout_is_not_stamped(self):
        with tempfile.TemporaryDirectory() as other:
            self.assertFalse(verify._stamp_head(Path(other)))

    def test_worktree_uses_its_own_stamp(self):
        wt = self.root.parent / (self.root.name + "-wt")
        _git(self.root, "worktree", "add", "-q", "-b", "wt", str(wt))
        self.addCleanup(
            lambda: subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=self.root)
        )
        self.assertTrue(verify._stamp_head(wt))
        self.assertTrue(pre_push_gate.stamp_matches_head(wt))


class MainExitCodeTests(unittest.TestCase):
    """main() decides the exit code: only 2 blocks, so every error must end in 2."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q")
        (self.root / "a.txt").write_text("a")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "init")

    def _run(self, stdin: str) -> int:
        script = Path(pre_push_gate.__file__)
        return subprocess.run(
            [sys.executable, str(script)],
            input=stdin,
            cwd=self.root,
            capture_output=True,
            text=True,
        ).returncode

    @staticmethod
    def _push() -> str:
        return json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push"}})

    def test_malformed_and_non_object_payloads_block(self):
        self.assertEqual(self._run("{bad"), 2)
        self.assertEqual(self._run("[]"), 2)
        self.assertEqual(self._run(""), 2)

    def test_unguarded_call_passes(self):
        self.assertEqual(
            self._run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})), 0
        )

    def test_guarded_call_without_stamp_blocks(self):
        self.assertEqual(self._run(self._push()), 2)

    def test_guarded_call_with_stamp_passes_until_the_next_commit(self):
        self.assertTrue(verify._stamp_head(self.root))
        self.assertEqual(self._run(self._push()), 0)
        (self.root / "b.txt").write_text("b")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "second")
        self.assertEqual(self._run(self._push()), 2)

    def test_outside_a_git_checkout_a_guarded_call_blocks(self):
        with tempfile.TemporaryDirectory() as other:
            script = Path(pre_push_gate.__file__)
            done = subprocess.run(
                [sys.executable, str(script)],
                input=self._push(),
                cwd=other,
                capture_output=True,
                text=True,
            )
            self.assertEqual(done.returncode, 2)

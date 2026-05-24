import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "codex_skill.py"
SESSION_FILENAME = "codex_session.json"
HISTORY_FILENAME = "codex_session_history.json"

FAKE_CODEX_SOURCE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json
    import os
    import sys
    from pathlib import Path

    args = sys.argv[1:]
    reply = os.environ["FAKE_CODEX_REPLY"]
    forced_error = os.environ.get("FAKE_CODEX_ERROR")
    capture_path = os.environ.get("FAKE_CODEX_CAPTURE")
    stdin_text = sys.stdin.read()

    if capture_path:
        Path(capture_path).write_text(
            json.dumps({"argv": args, "stdin": stdin_text}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    out_path = None
    for index, arg in enumerate(args):
        if arg == "--output-last-message":
            out_path = args[index + 1]
            break

    if out_path is None:
        print("missing --output-last-message", file=sys.stderr)
        sys.exit(2)

    if forced_error:
        print(forced_error, file=sys.stderr)
        sys.exit(1)

    Path(out_path).write_text(reply, encoding="utf-8")
    print(json.dumps({"type": "session_meta", "payload": {"id": "test-session", "originator": "codex_exec", "source": "exec"}}))
    """
)


class CodexSkillIntegrationTests(unittest.TestCase):
    maxDiff = None

    def run_skill(
        self,
        cmd: str,
        payload: str,
        reply: str = "",
        *,
        session_id: Optional[str] = None,
        history_ids: Optional[list[str]] = None,
        error: Optional[str] = None,
    ) -> Tuple[subprocess.CompletedProcess[str], Optional[dict], dict]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            workspace = tmp / "workspace"
            claude_dir = workspace / ".claude"
            claude_dir.mkdir(parents=True)

            if session_id is not None:
                (claude_dir / SESSION_FILENAME).write_text(
                    json.dumps({"session_id": session_id}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            if history_ids is not None:
                (claude_dir / HISTORY_FILENAME).write_text(
                    json.dumps(
                        {
                            "previous_session_ids": history_ids,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            fake_codex = tmp / "fake-codex.py"
            fake_codex.write_text(FAKE_CODEX_SOURCE, encoding="utf-8")
            fake_codex.chmod(0o755)

            home_dir = tmp / "home"
            trash_dir = home_dir / ".Trash"
            trash_dir.mkdir(parents=True)

            capture_path = tmp / "capture.json"
            env = os.environ.copy()
            env["CODEX_BIN"] = str(fake_codex)
            env["CODEX_HOME"] = str(tmp / "codex-home")
            env["FAKE_CODEX_REPLY"] = reply
            env["FAKE_CODEX_CAPTURE"] = str(capture_path)
            env["HOME"] = str(home_dir)
            if error is not None:
                env["FAKE_CODEX_ERROR"] = error

            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--cwd", str(workspace), cmd],
                input=payload,
                text=True,
                capture_output=True,
                env=env,
                cwd=str(ROOT),
            )

            capture = None
            if capture_path.exists():
                capture = json.loads(capture_path.read_text(encoding="utf-8"))

            state = {
                "session_exists": (claude_dir / SESSION_FILENAME).exists(),
                "session_payload": (
                    json.loads((claude_dir / SESSION_FILENAME).read_text(encoding="utf-8"))
                    if (claude_dir / SESSION_FILENAME).exists()
                    else None
                ),
                "history_exists": (claude_dir / HISTORY_FILENAME).exists(),
                "history_payload": (
                    json.loads((claude_dir / HISTORY_FILENAME).read_text(encoding="utf-8"))
                    if (claude_dir / HISTORY_FILENAME).exists()
                    else None
                ),
            }
            return proc, capture, state

    @staticmethod
    def sandbox_from_argv(argv: list[str]) -> str:
        index = argv.index("--sandbox")
        return argv[index + 1]

    def test_existing_session_is_resumed_by_default(self) -> None:
        proc, capture, _state = self.run_skill(
            "review-my-plan",
            '{"plan_for_review":"Change only the prompt parser and update tests."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nBoundary is acceptable.",
            session_id="resume-me",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("resume", capture["argv"])
        self.assertIn("resume-me", capture["argv"])

    def test_init_without_managed_session_creates_new_persistent_session(self) -> None:
        proc, capture, state = self.run_skill(
            "init",
            '{"task_background":"Current task brief","mutation_owner":"claude"}',
            "## Task Understanding Reply\n\nLooks consistent.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertNotIn("resume", capture["argv"])
        self.assertTrue(state["session_exists"])
        self.assertEqual(state["session_payload"]["session_id"], "test-session")

    def test_dangerous_new_session_replaces_current_session_and_records_history(self) -> None:
        proc, capture, state = self.run_skill(
            "dangerous-new-session",
            '{"user_permission":"The user explicitly asked to abandon the old Codex continuity and start fresh."}',
            "fresh managed session ready.",
            session_id="old-session",
            history_ids=["older-session", "oldest-session"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertNotIn("resume", capture["argv"])
        self.assertTrue(state["session_exists"])
        self.assertEqual(state["session_payload"]["session_id"], "test-session")
        self.assertTrue(state["history_exists"])
        self.assertEqual(
            state["history_payload"]["previous_session_ids"],
            ["old-session", "older-session"],
        )
        self.assertIn("dangerous-new-session authorized", proc.stdout)
        self.assertIn("test-session", proc.stdout)

    def test_dangerous_new_session_can_switch_to_target_session_id(self) -> None:
        proc, capture, state = self.run_skill(
            "dangerous-new-session",
            '{"user_permission":"The user explicitly asked to switch back to a specific prior Codex session.","target_session_id":"restored-session"}',
            session_id="current-session",
            history_ids=["older-session", "oldest-session"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsNone(capture)
        self.assertTrue(state["session_exists"])
        self.assertEqual(state["session_payload"]["session_id"], "restored-session")
        self.assertTrue(state["history_exists"])
        self.assertEqual(
            state["history_payload"]["previous_session_ids"],
            ["current-session", "older-session"],
        )
        self.assertIn("target session id: restored-session", proc.stdout)

    def test_dangerous_new_session_without_prior_session_still_writes_current_session(self) -> None:
        proc, capture, state = self.run_skill(
            "dangerous-new-session",
            '{"user_permission":"The user explicitly wants a fresh session."}',
            "fresh managed session ready.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertNotIn("resume", capture["argv"])
        self.assertTrue(state["session_exists"])
        self.assertFalse(state["history_exists"])

    def test_init_task_codex_uses_role_specific_prompt_when_new_session_is_created(self) -> None:
        proc, capture, _state = self.run_skill(
            "init",
            '{"task_background":"Current task brief","mutation_owner":"codex"}',
            "## Task Understanding Reply\n\nSwitch to Codex-owned execution.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertIn("fresh task brief on the Codex-mutates path", capture["stdin"])
        self.assertIn("Codex owns state-changing work on this path", capture["stdin"])

    def test_work_sync_uses_read_only_and_accepts_markdown_sections(self) -> None:
        proc, capture, _state = self.run_skill(
            "work-sync",
            '{"sync_message":"Please respond to the current review feedback."}',
            "## Discussion Reply\n\nI agree with the concern.\n\n## Plan\n\nRepair the parser first.",
            session_id="existing-session",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("Sync message from Claude:", capture["stdin"])
        self.assertIn("## Plan", proc.stdout)

    def test_request_mutation_defaults_to_workspace_write(self) -> None:
        proc, capture, _state = self.run_skill(
            "request-mutation",
            '{"approved_mutation":"Implement the approved parser fix and stop."}',
            "Updated parser, ran validation, stopped for review.",
            session_id="existing-session",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "workspace-write")
        self.assertIn("workspace-write (default mutation sandbox)", capture["stdin"])
        self.assertIn("Approved mutation from Claude:", capture["stdin"])

    def test_request_mutation_full_access_escalates_to_danger_full_access(self) -> None:
        proc, capture, _state = self.run_skill(
            "request-mutation",
            '{"approved_mutation":"Run the approved repair step.","sandbox_mode":"full-access"}',
            "Ran the approved repair under full access and stopped.",
            session_id="existing-session",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "danger-full-access")
        self.assertIn("danger-full-access (explicit full-access escalation approved by Claude)", capture["stdin"])

    def test_missing_thread_error_requires_explicit_dangerous_reset(self) -> None:
        proc, _capture, _state = self.run_skill(
            "review-my-work",
            '{"work_for_review":"Please review the completed work."}',
            session_id="stale-session",
            error="thread stale-session not found",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("could not resume", proc.stderr)
        self.assertIn("dangerous-new-session", proc.stderr)
        self.assertIn("Do not manually delete or replace the session file", proc.stderr)

    def test_review_my_plan_rejects_legacy_json_reply(self) -> None:
        proc, _capture, _state = self.run_skill(
            "review-my-plan",
            '{"plan_for_review":"Change only the prompt parser and update tests."}',
            '{"approved_to_mutate":true,"plan_review_reply":"legacy json"}',
            session_id="existing-session",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("approved_to_mutate must be the first non-empty line", proc.stderr)


if __name__ == "__main__":
    unittest.main()

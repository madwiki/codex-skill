import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "codex_skill.py"

FAKE_CODEX_SOURCE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json
    import os
    import sys
    from pathlib import Path

    args = sys.argv[1:]
    reply = os.environ["FAKE_CODEX_REPLY"]
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

    Path(out_path).write_text(reply, encoding="utf-8")
    print(json.dumps({"type": "session_meta", "payload": {"id": "test-session", "originator": "codex_exec", "source": "exec"}}))
    """
)


class CodexSkillIntegrationTests(unittest.TestCase):
    maxDiff = None

    def run_skill(self, cmd: str, payload: str, reply: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            workspace = tmp / "workspace"
            workspace.mkdir()
            (workspace / ".claude").mkdir()

            fake_codex = tmp / "fake-codex.py"
            fake_codex.write_text(FAKE_CODEX_SOURCE, encoding="utf-8")
            fake_codex.chmod(0o755)

            capture_path = tmp / "capture.json"
            env = os.environ.copy()
            env["CODEX_BIN"] = str(fake_codex)
            env["CODEX_HOME"] = str(tmp / "codex-home")
            env["FAKE_CODEX_REPLY"] = reply
            env["FAKE_CODEX_CAPTURE"] = str(capture_path)

            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--cwd", str(workspace), "--new-session", cmd],
                input=payload,
                text=True,
                capture_output=True,
                env=env,
                cwd=str(ROOT),
            )

            capture = json.loads(capture_path.read_text(encoding="utf-8"))
            return proc, capture

    @staticmethod
    def sandbox_from_argv(argv: list[str]) -> str:
        index = argv.index("--sandbox")
        return argv[index + 1]

    def test_init_task_claude_uses_read_only_and_role_specific_prompt(self) -> None:
        proc, capture = self.run_skill(
            "init",
            '{"task_background":"Current task brief","mutation_owner":"claude"}',
            "## Task Understanding Reply\n\nLooks consistent.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("fresh task brief on the Claude-mutates path", capture["stdin"])
        self.assertIn("Claude owns state-changing work on this path.", capture["stdin"])
        self.assertIn("## Task Understanding Reply", proc.stdout)

    def test_init_task_codex_uses_read_only_and_role_specific_prompt(self) -> None:
        proc, capture = self.run_skill(
            "init",
            '{"task_background":"Current task brief","mutation_owner":"codex"}',
            "## Task Understanding Reply\n\nSwitch to Codex-owned execution.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("fresh task brief on the Codex-mutates path", capture["stdin"])
        self.assertIn("Codex owns state-changing work on this path", capture["stdin"])
        self.assertIn("## Task Understanding Reply", proc.stdout)

    def test_work_sync_uses_read_only_and_accepts_markdown_sections(self) -> None:
        proc, capture = self.run_skill(
            "work-sync",
            '{"sync_message":"Please respond to the current review feedback."}',
            "## Discussion Reply\n\nI agree with the concern.\n\n## Plan\n\nRepair the parser first.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("Sync message from Claude:", capture["stdin"])
        self.assertIn("## Plan", proc.stdout)

    def test_request_mutation_defaults_to_workspace_write(self) -> None:
        proc, capture = self.run_skill(
            "request-mutation",
            '{"approved_mutation":"Implement the approved parser fix and stop."}',
            "Updated parser, ran validation, stopped for review.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "workspace-write")
        self.assertIn("workspace-write (default mutation sandbox)", capture["stdin"])
        self.assertIn("Approved mutation from Claude:", capture["stdin"])

    def test_request_mutation_full_access_escalates_to_danger_full_access(self) -> None:
        proc, capture = self.run_skill(
            "request-mutation",
            '{"approved_mutation":"Run the approved repair step.","sandbox_mode":"full-access"}',
            "Ran the approved repair under full access and stopped.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "danger-full-access")
        self.assertIn("danger-full-access (explicit full-access escalation approved by Claude)", capture["stdin"])

    def test_review_my_plan_accepts_markdown_gate(self) -> None:
        proc, capture = self.run_skill(
            "review-my-plan",
            '{"plan_for_review":"Change only the prompt parser and update tests."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nBoundary is acceptable.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("Plan for review from Claude:", capture["stdin"])
        self.assertIn("approved_to_mutate: true", proc.stdout)

    def test_review_my_plan_rejects_legacy_json_reply(self) -> None:
        proc, _capture = self.run_skill(
            "review-my-plan",
            '{"plan_for_review":"Change only the prompt parser and update tests."}',
            '{"approved_to_mutate":true,"plan_review_reply":"legacy json"}',
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("approved_to_mutate must be the first non-empty line", proc.stderr)


if __name__ == "__main__":
    unittest.main()

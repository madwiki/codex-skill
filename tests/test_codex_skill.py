import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "mad_agent_mesh.py"
CHANNELS_FILENAME = "mams_channels.json"
MANAGED_DIRNAME = ".mad-agent-mesh"

FAKE_CODEX_SOURCE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json
    import os
    import sys
    import time
    from pathlib import Path

    args = sys.argv[1:]
    default_reply = os.environ["FAKE_CHANNEL_REPLY"]
    reply_map = json.loads(os.environ.get("FAKE_CHANNEL_REPLY_MAP", "{}"))
    error_map = json.loads(os.environ.get("FAKE_CODEX_ERROR_MAP", "{}"))
    session_map = json.loads(os.environ.get("FAKE_CODEX_SESSION_MAP", "{}"))
    sleep_s = float(os.environ.get("FAKE_CODEX_SLEEP_S", "0"))
    capture_dir = os.environ.get("FAKE_CODEX_CAPTURE_DIR")
    stdin_text = sys.stdin.read()

    reply = default_reply
    forced_error = os.environ.get("FAKE_CODEX_ERROR")
    for key, mapped_reply in reply_map.items():
        if key in stdin_text:
            reply = mapped_reply
            break
    for key, mapped_error in error_map.items():
        if key in stdin_text:
            forced_error = mapped_error
            break

    if capture_dir:
        capture_path = Path(capture_dir) / (f"{time.time_ns()}.json")
        capture_path.write_text(
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

    if sleep_s > 0:
        time.sleep(sleep_s)

    session_id = "test-session"
    if "resume" in args:
        try:
            session_id = args[args.index("resume") + 1]
        except Exception:
            session_id = "test-session"
    else:
        for key, mapped_session_id in session_map.items():
            if key in stdin_text:
                session_id = mapped_session_id
                break

    Path(out_path).write_text(reply, encoding="utf-8")
    print(json.dumps({"type": "session_meta", "payload": {"id": session_id, "originator": "codex_exec", "source": "exec"}}))
    """
)


class MadAgentMeshIntegrationTests(unittest.TestCase):
    maxDiff = None

    def build_channel(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        focus: Optional[str] = None,
        baseline: Optional[str] = None,
        extra_context: Optional[str] = None,
        plan_baseline: Optional[str] = None,
        execution_baseline: Optional[str] = None,
        can_mutate: bool = True,
        runner: str = "codex",
        runner_config: Optional[dict] = None,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        previous_session_ids: Optional[list[str]] = None,
        last_stage_context: Optional[str] = None,
        stage_reminder_turn_count: int = 0,
    ) -> dict:
        return {
            "name": name,
            "prompt_profile": {
                "public": {
                    "description": description,
                    "focus": focus,
                    "baseline": baseline,
                    "extra_context": extra_context,
                },
                "plan_stage": {
                    "baseline": plan_baseline,
                },
                "execution_stage": {
                    "baseline": execution_baseline,
                },
            },
            "can_mutate": can_mutate,
            "runner": runner,
            "runner_config": runner_config or {},
            "session_id": session_id,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "previous_session_ids": previous_session_ids or [],
            "last_stage_context": last_stage_context,
            "stage_reminder_turn_count": stage_reminder_turn_count,
            "updated_at": "2026-06-03T00:00:00Z",
        }

    def build_config(self, channels: list[dict]) -> dict:
        return {
            "version": 5,
            "mams_channels": channels,
            "invoker_reminder_turn_count": 0,
            "updated_at": "2026-06-03T00:00:00Z",
        }

    def create_workspace(
        self,
        *,
        initial_config: Optional[dict] = None,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmpdir = tempfile.TemporaryDirectory()
        workspace = Path(tmpdir.name) / "workspace"
        managed_dir = workspace / MANAGED_DIRNAME
        managed_dir.mkdir(parents=True)
        (managed_dir / "refs").mkdir(parents=True, exist_ok=True)
        if initial_config is not None:
            (managed_dir / CHANNELS_FILENAME).write_text(
                json.dumps(initial_config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return tmpdir, workspace

    def run_in_workspace(
        self,
        workspace: Path,
        cmd: str,
        payload: str,
        reply: str = "",
        *,
        mams_channel_name: str = "default",
        error: Optional[str] = None,
        env_extra: Optional[dict[str, str]] = None,
    ) -> tuple[subprocess.CompletedProcess[str], list[dict], dict]:
        tmp = workspace.parent
        fake_codex = tmp / "fake-codex.py"
        fake_codex.write_text(FAKE_CODEX_SOURCE, encoding="utf-8")
        fake_codex.chmod(0o755)
        capture_dir = tmp / "captures"
        capture_dir.mkdir(exist_ok=True)

        env = os.environ.copy()
        env["CODEX_BIN"] = str(fake_codex)
        env["CODEX_HOME"] = str(tmp / "codex-home")
        env["FAKE_CHANNEL_REPLY"] = reply
        env["FAKE_CODEX_CAPTURE_DIR"] = str(capture_dir)
        if error is not None:
            env["FAKE_CODEX_ERROR"] = error
        if env_extra:
            env.update(env_extra)

        argv = [
            sys.executable,
            str(SCRIPT),
            "--cwd",
            str(workspace),
            "--mams-channel",
            mams_channel_name,
            cmd,
        ]
        proc = subprocess.run(
            argv,
            input=payload,
            text=True,
            capture_output=True,
            env=env,
            cwd=str(ROOT),
        )

        captures = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(capture_dir.glob("*.json"))
        ]
        config_path = workspace / MANAGED_DIRNAME / CHANNELS_FILENAME
        state = {
            "config": json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else None,
            "diagnostics": [
                {
                    "path": str(path.relative_to(workspace)),
                    "content": path.read_text(encoding="utf-8"),
                }
                for path in sorted((workspace / MANAGED_DIRNAME / "diagnostics").glob("*.md"))
            ],
        }
        return proc, captures, state

    @staticmethod
    def find_channel(state: dict, name: str) -> dict:
        payload = state["config"] or {}
        for item in payload.get("mams_channels", []):
            if item["name"] == name:
                return item
        raise AssertionError(f"Channel not found: {name}")

    @staticmethod
    def sandbox_from_argv(argv: list[str]) -> str:
        idx = argv.index("--sandbox")
        return argv[idx + 1]

    def test_active_wrapper_command_surface_exists_and_legacy_commands_are_absent(self) -> None:
        expected_bins = {
            "configure",
            "dangerous-new-session",
            "execute-this-plan",
            "execute-this-plan-part",
            "invoke",
            "review-this-plan",
            "review-this-work",
            "sync",
        }
        actual_bins = {
            path.name
            for path in (ROOT / "bin").iterdir()
            if path.is_file() and path.name != "mad_agent_mesh.py"
        }
        self.assertEqual(actual_bins, expected_bins)
        self.assertFalse((ROOT / "bin" / "init").exists())
        self.assertFalse((ROOT / "bin" / "update-config").exists())
        self.assertFalse((ROOT / "init.md").exists())
        self.assertFalse((ROOT / "update-config.md").exists())

    def test_governor_escalation_prompt_asset_exists(self) -> None:
        prompt_path = ROOT / "prompts" / "governor-user-escalation.md"
        self.assertTrue(prompt_path.is_file(), prompt_path)
        contents = prompt_path.read_text(encoding="utf-8")
        self.assertIn("escalate_to_user: true", contents)
        self.assertIn("## Governor Review Reply", contents)

    def test_first_turn_creates_default_channel_and_persists_session(self) -> None:
        tempdir, workspace = self.create_workspace()
        self.addCleanup(tempdir.cleanup)

        proc, captures, state = self.run_in_workspace(
            workspace,
            "review-this-plan",
            '{"plan_for_review":"Review the initial plan draft."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks coherent.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(captures), 1)
        self.assertNotIn("resume", captures[0]["argv"])
        channel = self.find_channel(state, "default")
        self.assertEqual(channel["session_id"], "test-session")
        self.assertEqual(channel["last_stage_context"], "plan")
        self.assertEqual(channel["stage_reminder_turn_count"], 1)

    def test_existing_session_is_resumed(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config(
                [self.build_channel("default", session_id="resume-me")]
            )
        )
        self.addCleanup(tempdir.cleanup)

        proc, captures, _state = self.run_in_workspace(
            workspace,
            "review-this-plan",
            '{"plan_for_review":"Review the current plan."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nBoundary is acceptable.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(captures), 1)
        self.assertIn("resume", captures[0]["argv"])
        self.assertIn("resume-me", captures[0]["argv"])

    def test_configure_updates_channel_only(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config([self.build_channel("default", session_id="existing")])
        )
        self.addCleanup(tempdir.cleanup)

        proc, _captures, state = self.run_in_workspace(
            workspace,
            "configure",
            json.dumps(
                {
                    "mams_channels": [
                        {
                            "name": "reviewer-a",
                            "prompt_profile": {
                                "public": {
                                    "focus": "Watch for architectural drift.",
                                    "baseline": "Keep the original task constraints stable.",
                                },
                                "plan_stage": {
                                    "baseline": "Push back on weak plans."
                                },
                                "execution_stage": {
                                    "baseline": "Review actual work, not intent."
                                },
                            },
                            "can_mutate": False,
                            "runner": "codex",
                            "model": "gpt-review",
                            "reasoning_effort": "high",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        reviewer = self.find_channel(state, "reviewer-a")
        self.assertEqual(reviewer["prompt_profile"]["public"]["focus"], "Watch for architectural drift.")
        self.assertFalse(reviewer["can_mutate"])
        self.assertEqual(reviewer["model"], "gpt-review")
        self.assertNotIn("mams_invoker", state["config"])
        self.assertNotIn("shared_stages", state["config"])

    def test_plan_stage_reminder_uses_full_then_brief_and_resets_on_stage_switch(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config(
                [
                    self.build_channel(
                        "default",
                        session_id="existing",
                        description="Planner role.",
                        baseline="Always preserve user intent.",
                        plan_baseline="Design the plan carefully.",
                        execution_baseline="When consulted during execution, optimize for forward progress.",
                    )
                ]
            )
        )
        self.addCleanup(tempdir.cleanup)

        plan_reply = "approved_to_mutate: true\n\n## Plan Review Reply\n\nReady."
        work_reply = "approved_work: true\n\n## Work Review Reply\n\nLooks good."

        proc1, captures1, state1 = self.run_in_workspace(
            workspace,
            "review-this-plan",
            '{"plan_for_review":"Plan v1"}',
            plan_reply,
        )
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        self.assertIn("<<<CHANNEL_STAGE_REMINDER_FULL.BEGIN>>>", captures1[-1]["stdin"])
        self.assertIn("Design the plan carefully.", captures1[-1]["stdin"])
        self.assertEqual(self.find_channel(state1, "default")["stage_reminder_turn_count"], 1)

        proc2, captures2, state2 = self.run_in_workspace(
            workspace,
            "review-this-plan",
            '{"plan_for_review":"Plan v2"}',
            plan_reply,
        )
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertIn("<<<CHANNEL_STAGE_REMINDER_BRIEF.BEGIN>>>", captures2[-1]["stdin"])
        self.assertNotIn("Design the plan carefully.", captures2[-1]["stdin"])
        self.assertEqual(self.find_channel(state2, "default")["stage_reminder_turn_count"], 2)

        proc3, captures3, state3 = self.run_in_workspace(
            workspace,
            "review-this-work",
            '{"work_for_review":"Work v1"}',
            work_reply,
        )
        self.assertEqual(proc3.returncode, 0, proc3.stderr)
        self.assertIn("<<<CHANNEL_STAGE_REMINDER_FULL.BEGIN>>>", captures3[-1]["stdin"])
        self.assertIn("When consulted during execution, optimize for forward progress.", captures3[-1]["stdin"])
        channel = self.find_channel(state3, "default")
        self.assertEqual(channel["last_stage_context"], "execution")
        self.assertEqual(channel["stage_reminder_turn_count"], 1)

    def test_channel_prompt_uses_workflow_prompt_tag_and_not_invoker_user_reminder(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config(
                [self.build_channel("default", session_id="existing", baseline="Keep scope tight.")]
            )
        )
        self.addCleanup(tempdir.cleanup)

        proc, captures, _state = self.run_in_workspace(
            workspace,
            "sync",
            '{"sync_message":"Discuss the current blocker.","stage_context":"plan"}',
            "## Discussion Reply\n\nContinue with the current approach.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        prompt = captures[-1]["stdin"]
        self.assertIn("<<<MAMS_WORKFLOW_PROMPT.BEGIN>>>", prompt)
        self.assertIn("<<<CHANNEL_STAGE_REMINDER_FULL.BEGIN>>>", prompt)
        self.assertNotIn("<<<MAMS_REMINDER_FULL.BEGIN>>>", prompt)
        self.assertNotIn("<<<USER_REMINDER.BEGIN>>>", prompt)

    def test_invoker_skill_usage_reminder_uses_full_then_brief_cadence(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config([self.build_channel("default", session_id="existing")])
        )
        self.addCleanup(tempdir.cleanup)

        payload = '{"plan_for_review":"Plan v1"}'
        reply = "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks coherent."

        proc1, _captures1, state1 = self.run_in_workspace(workspace, "review-this-plan", payload, reply)
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        self.assertIn("<<<INVOKER_SKILL_USAGE_FULL.BEGIN>>>", proc1.stdout)
        self.assertIn("Do not modify code directly.", proc1.stdout)
        self.assertEqual(state1["config"]["invoker_reminder_turn_count"], 1)

        proc2, _captures2, state2 = self.run_in_workspace(workspace, "review-this-plan", payload, reply)
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertIn("<<<INVOKER_SKILL_USAGE_BRIEF.BEGIN>>>", proc2.stdout)
        self.assertIn("INVOKER_SKILL_USAGE_FULL still applies in full.", proc2.stdout)
        self.assertEqual(state2["config"]["invoker_reminder_turn_count"], 2)

        proc3, _captures3, state3 = self.run_in_workspace(workspace, "review-this-plan", payload, reply)
        self.assertEqual(proc3.returncode, 0, proc3.stderr)
        self.assertIn("<<<INVOKER_SKILL_USAGE_BRIEF.BEGIN>>>", proc3.stdout)
        self.assertEqual(state3["config"]["invoker_reminder_turn_count"], 3)

        proc4, _captures4, state4 = self.run_in_workspace(workspace, "review-this-plan", payload, reply)
        self.assertEqual(proc4.returncode, 0, proc4.stderr)
        self.assertIn("<<<INVOKER_SKILL_USAGE_FULL.BEGIN>>>", proc4.stdout)
        self.assertEqual(state4["config"]["invoker_reminder_turn_count"], 4)

    def test_invoker_skill_usage_reminder_cadence_is_global_across_wrapper_commands(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config([self.build_channel("default", session_id="existing")])
        )
        self.addCleanup(tempdir.cleanup)

        configure_proc, _captures1, state1 = self.run_in_workspace(
            workspace,
            "configure",
            json.dumps(
                {
                    "mams_channels": [
                        {
                            "name": "reviewer-a",
                            "can_mutate": False,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        )
        self.assertEqual(configure_proc.returncode, 0, configure_proc.stderr)
        self.assertIn("<<<INVOKER_SKILL_USAGE_FULL.BEGIN>>>", configure_proc.stdout)
        self.assertEqual(state1["config"]["invoker_reminder_turn_count"], 1)

        invoke_proc, _captures2, state2 = self.run_in_workspace(
            workspace,
            "invoke",
            json.dumps(
                {
                    "requests": [
                        {
                            "command": "review-this-plan",
                            "mams_channel": "default",
                            "input": {"plan_for_review": "Plan v1"},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks coherent.",
        )
        self.assertEqual(invoke_proc.returncode, 0, invoke_proc.stderr)
        self.assertIn("<<<INVOKER_SKILL_USAGE_BRIEF.BEGIN>>>", invoke_proc.stdout)
        self.assertEqual(state2["config"]["invoker_reminder_turn_count"], 2)

    def test_nonstandard_stop_retries_once_and_writes_diagnostic_on_second_failure(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config([self.build_channel("default", session_id="existing")])
        )
        self.addCleanup(tempdir.cleanup)

        proc, captures, state = self.run_in_workspace(
            workspace,
            "review-this-plan",
            '{"plan_for_review":"Plan v1"}',
            "Unstructured stop.",
            env_extra={
                "FAKE_CHANNEL_REPLY_MAP": json.dumps(
                    {
                        "WORKFLOW_PROTOCOL_NOTICE": "Still invalid.",
                    },
                    ensure_ascii=False,
                )
            },
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(captures), 2)
        self.assertIn("WORKFLOW_PROTOCOL_NOTICE", captures[-1]["stdin"])
        self.assertEqual(len(state["diagnostics"]), 1)
        self.assertIn("Managed mams_channel 'default' stopped twice", proc.stderr)

    def test_governor_can_suppress_user_escalation(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config(
                [
                    self.build_channel("default", session_id="executor-session"),
                    self.build_channel("governor", session_id="governor-session"),
                ]
            )
        )
        self.addCleanup(tempdir.cleanup)

        proc, _captures, _state = self.run_in_workspace(
            workspace,
            "execute-this-plan",
            '{"approved_plan":"Execute the plan."}',
            "## Work Report\n\nDid the work.\n\n## User Escalation Request\n\nblocking: false\nquestion: Ask the user?\nreason: Unsure.\n",
            env_extra={
                "FAKE_CHANNEL_REPLY_MAP": json.dumps(
                    {
                        "Originating managed channel:": "escalate_to_user: false\n\n## Governor Review Reply\n\nHandle it internally.",
                    },
                    ensure_ascii=False,
                )
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("<<<USER_ESCALATION_REQUEST.BEGIN>>>", proc.stdout)
        self.assertIn("<<<GOVERNOR_REVIEW.BEGIN>>>", proc.stdout)

    def test_governor_can_approve_user_escalation(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config(
                [
                    self.build_channel("default", session_id="executor-session"),
                    self.build_channel("governor", session_id="governor-session"),
                ]
            )
        )
        self.addCleanup(tempdir.cleanup)

        proc, _captures, _state = self.run_in_workspace(
            workspace,
            "execute-this-plan",
            '{"approved_plan":"Execute the plan."}',
            "## Work Report\n\nDid the work.\n\n## User Escalation Request\n\nblocking: false\nquestion: Ask the user?\nreason: Unsure.\n",
            env_extra={
                "FAKE_CHANNEL_REPLY_MAP": json.dumps(
                    {
                        "Originating managed channel:": "escalate_to_user: true\n\n## Governor Review Reply\n\nSurface it.",
                    },
                    ensure_ascii=False,
                )
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<<<USER_ESCALATION_REQUEST.BEGIN>>>", proc.stdout)
        self.assertIn("question: Ask the user?", proc.stdout)

    def test_invoke_uses_concurrent_mode_for_read_only_requests(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config(
                [
                    self.build_channel("reviewer-a", session_id="a"),
                    self.build_channel("reviewer-b", session_id="b"),
                ]
            )
        )
        self.addCleanup(tempdir.cleanup)

        proc, _captures, _state = self.run_in_workspace(
            workspace,
            "invoke",
            json.dumps(
                {
                    "requests": [
                        {
                            "command": "review-this-plan",
                            "mams_channel": "reviewer-a",
                            "input": {"plan_for_review": "Plan A"},
                        },
                        {
                            "command": "review-this-plan",
                            "mams_channel": "reviewer-b",
                            "input": {"plan_for_review": "Plan B"},
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks good.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Execution mode: concurrent read-only fanout", proc.stdout)

    def test_invoke_uses_sequential_mode_for_mutating_requests(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config(
                [
                    self.build_channel("executor-a", session_id="a", can_mutate=True),
                    self.build_channel("executor-b", session_id="b", can_mutate=True),
                ]
            )
        )
        self.addCleanup(tempdir.cleanup)

        proc, _captures, _state = self.run_in_workspace(
            workspace,
            "invoke",
            json.dumps(
                {
                    "requests": [
                        {
                            "command": "execute-this-plan",
                            "mams_channel": "executor-a",
                            "input": {"approved_plan": "Plan A"},
                        },
                        {
                            "command": "execute-this-plan",
                            "mams_channel": "executor-b",
                            "input": {"approved_plan": "Plan B"},
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            "## Work Report\n\nCompleted the approved scope.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Execution mode: sequential invoke", proc.stdout)

    def test_dangerous_new_session_resets_stage_reminder_state(self) -> None:
        tempdir, workspace = self.create_workspace(
            initial_config=self.build_config(
                [
                    self.build_channel(
                        "default",
                        session_id="old-session",
                        last_stage_context="execution",
                        stage_reminder_turn_count=3,
                    )
                ]
            )
        )
        self.addCleanup(tempdir.cleanup)

        proc, _captures, state = self.run_in_workspace(
            workspace,
            "dangerous-new-session",
            json.dumps(
                {
                    "user_permission": "The user explicitly authorized replacing this managed session.",
                    "target_session_id": "fresh-session",
                },
                ensure_ascii=False,
            ),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        channel = self.find_channel(state, "default")
        self.assertEqual(channel["session_id"], "fresh-session")
        self.assertIsNone(channel["last_stage_context"])
        self.assertEqual(channel["stage_reminder_turn_count"], 0)


if __name__ == "__main__":
    unittest.main()

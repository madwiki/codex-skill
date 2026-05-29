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
SCRIPT = ROOT / "bin" / "mad_agent_mesh.py"
CHANNELS_FILENAME = "mams_channels.json"
LEGACY_SESSION_FILENAME = "codex_session.json"
LEGACY_HISTORY_FILENAME = "codex_session_history.json"
MANAGED_DIRNAME = ".mad-agent-mesh"
LEGACY_DIRNAME = ".claude"

FAKE_CODEX_SOURCE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json
    import os
    import time
    import sys
    from pathlib import Path

    args = sys.argv[1:]
    reply = os.environ["FAKE_CHANNEL_REPLY"]
    forced_error = os.environ.get("FAKE_CODEX_ERROR")
    reply_map = json.loads(os.environ.get("FAKE_CHANNEL_REPLY_MAP", "{}"))
    error_map = json.loads(os.environ.get("FAKE_CODEX_ERROR_MAP", "{}"))
    session_map = json.loads(os.environ.get("FAKE_CODEX_SESSION_MAP", "{}"))
    sleep_s = float(os.environ.get("FAKE_CODEX_SLEEP_S", "0"))
    capture_path = os.environ.get("FAKE_CODEX_CAPTURE")
    stdin_text = sys.stdin.read()

    for key, mapped_reply in reply_map.items():
        if key in stdin_text:
            reply = mapped_reply
            break

    for key, mapped_error in error_map.items():
        if key in stdin_text:
            forced_error = mapped_error
            break

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

FAKE_CLAUDE_SOURCE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json
    import os
    import time
    import sys
    from pathlib import Path

    args = sys.argv[1:]
    reply = os.environ["FAKE_CHANNEL_REPLY"]
    forced_error = os.environ.get("FAKE_CODEX_ERROR")
    reply_map = json.loads(os.environ.get("FAKE_CHANNEL_REPLY_MAP", "{}"))
    error_map = json.loads(os.environ.get("FAKE_CODEX_ERROR_MAP", "{}"))
    session_map = json.loads(os.environ.get("FAKE_CODEX_SESSION_MAP", "{}"))
    sleep_s = float(os.environ.get("FAKE_CODEX_SLEEP_S", "0"))
    capture_path = os.environ.get("FAKE_CODEX_CAPTURE")
    stdin_text = sys.stdin.read()

    for key, mapped_reply in reply_map.items():
        if key in stdin_text:
            reply = mapped_reply
            break

    for key, mapped_error in error_map.items():
        if key in stdin_text:
            forced_error = mapped_error
            break

    if capture_path:
        Path(capture_path).write_text(
            json.dumps({"argv": args, "stdin": stdin_text, "runner": "claude-code"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if forced_error:
        print(forced_error, file=sys.stderr)
        sys.exit(1)

    if sleep_s > 0:
        time.sleep(sleep_s)

    session_id = "claude-session"
    if "--resume" in args:
        try:
            session_id = args[args.index("--resume") + 1]
        except Exception:
            session_id = "claude-session"
    else:
        for key, mapped_session_id in session_map.items():
            if key in stdin_text:
                session_id = mapped_session_id
                break

    output_format = "json"
    if "--output-format" in args:
        try:
            output_format = args[args.index("--output-format") + 1]
        except Exception:
            output_format = "json"

    if output_format == "stream-json":
        print(json.dumps({"type": "system", "subtype": "init", "session_id": session_id}), flush=True)
        print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}}), flush=True)
        print(json.dumps({"type": "result", "session_id": session_id, "result": reply}), flush=True)
    else:
        print(json.dumps({"session_id": session_id, "result": reply}), flush=True)
    """
)


class MadAgentMeshIntegrationTests(unittest.TestCase):
    maxDiff = None

    def build_mams_channel(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        focus: Optional[str] = None,
        baseline: Optional[str] = None,
        extra_context: Optional[str] = None,
        stage_guidance: Optional[dict[str, str]] = None,
        can_mutate: bool = True,
        runner: str = "codex",
        runner_config: Optional[dict] = None,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        previous_session_ids: Optional[list[str]] = None,
        reminder_turn_count: int = 0,
    ) -> dict:
        return {
            "name": name,
            "description": description or f"Managed MAMS channel '{name}'.",
            "focus": focus,
            "baseline": baseline,
            "extra_context": extra_context,
            "stage_guidance": stage_guidance or {},
            "can_mutate": can_mutate,
            "runner": runner,
            "runner_config": runner_config or {},
            "session_id": session_id,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "previous_session_ids": previous_session_ids or [],
            "reminder_turn_count": reminder_turn_count,
            "updated_at": "2026-05-26T00:00:00Z",
        }

    def build_config(
        self,
        mams_channels: list[dict],
        *,
        mams_invoker: Optional[dict] = None,
        shared_stages: Optional[dict[str, str]] = None,
    ) -> dict:
        return {
            "version": 5,
            "mams_invoker": mams_invoker or {
                "baseline": None,
                "working_style": None,
                "extra_context": None,
                "stage_guidance": {},
                "can_mutate": True,
            },
            "shared_stages": shared_stages or {},
            "mams_channels": mams_channels,
            "updated_at": "2026-05-26T00:00:00Z",
        }

    def run_skill(
        self,
        cmd: str,
        payload: str,
        reply: str = "",
        *,
        mams_channel_name: str = "default",
        initial_config: Optional[dict] = None,
        initial_legacy_config: Optional[dict] = None,
        initial_mams_channels: Optional[list[dict]] = None,
        legacy_session_id: Optional[str] = None,
        legacy_history_ids: Optional[list[str]] = None,
        error: Optional[str] = None,
        extra_args: Optional[list[str]] = None,
        env_extra: Optional[dict[str, str]] = None,
        ref_files: Optional[dict[str, str]] = None,
    ) -> Tuple[subprocess.CompletedProcess[str], Optional[dict], dict]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            workspace = tmp / "workspace"
            managed_dir = workspace / MANAGED_DIRNAME
            legacy_dir = workspace / LEGACY_DIRNAME
            managed_dir.mkdir(parents=True)
            legacy_dir.mkdir(parents=True)
            (managed_dir / "refs").mkdir(parents=True, exist_ok=True)

            if ref_files:
                for rel_path, content in ref_files.items():
                    path = workspace / rel_path
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")

            if initial_config is not None:
                (managed_dir / CHANNELS_FILENAME).write_text(
                    json.dumps(initial_config, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            if initial_legacy_config is not None:
                (legacy_dir / CHANNELS_FILENAME).write_text(
                    json.dumps(initial_legacy_config, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            elif initial_mams_channels is not None:
                (managed_dir / CHANNELS_FILENAME).write_text(
                    json.dumps(self.build_config(initial_mams_channels), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            if legacy_session_id is not None:
                (legacy_dir / LEGACY_SESSION_FILENAME).write_text(
                    json.dumps({"session_id": legacy_session_id}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            if legacy_history_ids is not None:
                (legacy_dir / LEGACY_HISTORY_FILENAME).write_text(
                    json.dumps({"previous_session_ids": legacy_history_ids}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            fake_codex = tmp / "fake-codex.py"
            fake_codex.write_text(FAKE_CODEX_SOURCE, encoding="utf-8")
            fake_codex.chmod(0o755)
            fake_claude = tmp / "fake-claude.py"
            fake_claude.write_text(FAKE_CLAUDE_SOURCE, encoding="utf-8")
            fake_claude.chmod(0o755)

            env = os.environ.copy()
            env["CODEX_BIN"] = str(fake_codex)
            env["CLAUDE_BIN"] = str(fake_claude)
            env["CODEX_HOME"] = str(tmp / "codex-home")
            env["FAKE_CHANNEL_REPLY"] = reply
            capture_path = tmp / "capture.json"
            env["FAKE_CODEX_CAPTURE"] = str(capture_path)
            if error is not None:
                env["FAKE_CODEX_ERROR"] = error
            if env_extra:
                env.update(env_extra)

            argv = [sys.executable, str(SCRIPT), "--cwd", str(workspace), "--mams-channel", mams_channel_name]
            if extra_args:
                argv.extend(extra_args)
            argv.append(cmd)

            proc = subprocess.run(
                argv,
                input=payload,
                text=True,
                capture_output=True,
                env=env,
                cwd=str(ROOT),
            )

            capture = None
            if capture_path.exists():
                capture = json.loads(capture_path.read_text(encoding="utf-8"))

            agents_path = managed_dir / CHANNELS_FILENAME
            state = {
                "mams_channels_exists": agents_path.exists(),
                "mams_channels_payload": (
                    json.loads(agents_path.read_text(encoding="utf-8")) if agents_path.exists() else None
                ),
                "legacy_session_exists": (legacy_dir / LEGACY_SESSION_FILENAME).exists(),
                "legacy_history_exists": (legacy_dir / LEGACY_HISTORY_FILENAME).exists(),
            }
            return proc, capture, state

    @staticmethod
    def sandbox_from_argv(argv: list[str]) -> str:
        index = argv.index("--sandbox")
        return argv[index + 1]

    @staticmethod
    def find_mams_channel(state: dict, name: str) -> dict:
        mams_channels_payload = state["mams_channels_payload"] or {}
        mams_channels = mams_channels_payload.get("mams_channels", [])
        for mams_channel in mams_channels:
            if mams_channel["name"] == name:
                return mams_channel
        raise AssertionError(f"MAMS channel not found in state: {name}")

    def test_existing_agent_session_is_resumed_by_default(self) -> None:
        proc, capture, _state = self.run_skill(
            "review-this-plan",
            '{"plan_for_review":"Change only the prompt parser and update tests."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nBoundary is acceptable.",
            initial_mams_channels=[self.build_mams_channel("default", session_id="resume-me")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("resume", capture["argv"])
        self.assertIn("resume-me", capture["argv"])

    def test_init_without_agent_config_creates_new_persistent_default_agent(self) -> None:
        proc, capture, state = self.run_skill(
            "init",
            '{"task_background":"Current task brief"}',
            "## Task Understanding Reply\n\nLooks consistent.",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertNotIn("resume", capture["argv"])
        self.assertTrue(state["mams_channels_exists"])
        mams_channel = self.find_mams_channel(state, "default")
        self.assertEqual(mams_channel["session_id"], "test-session")
        self.assertEqual(mams_channel["name"], "default")

    def test_legacy_single_session_is_migrated_once_before_resume(self) -> None:
        proc, capture, state = self.run_skill(
            "review-this-plan",
            '{"plan_for_review":"Review the current plan."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLegacy migration looks fine.",
            legacy_session_id="legacy-session",
            legacy_history_ids=["older-session", "oldest-session"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertIn("resume", capture["argv"])
        self.assertIn("legacy-session", capture["argv"])
        self.assertIn("Migration notice:", proc.stdout)
        self.assertIn("Legacy session continuity files were read, normalized, and rewritten into the canonical config", proc.stdout)
        mams_channel = self.find_mams_channel(state, "default")
        self.assertEqual(mams_channel["session_id"], "legacy-session")
        self.assertEqual(mams_channel["previous_session_ids"], ["older-session", "oldest-session"])

    def test_legacy_structured_config_is_migrated_to_version_5(self) -> None:
        legacy_config = {
            "version": 2,
            "claude": {
                "baseline": "Keep the original task stable.",
                "working_style": "Discuss before mutating.",
                "extra_context": None,
                "stage_guidance": {
                    "review-my-plan": "Require concrete scope."
                },
            },
            "shared_stages": {
                "chat": "Discussion only."
            },
            "work_modes": {
                "claude_mutates": {
                    "stages": {
                        "review-my-plan": "Still a hard gate."
                    }
                },
                "codex_mutates": {
                    "stages": {}
                },
            },
            "mams_channels": [
                self.build_mams_channel("default", session_id="legacy-structured-session"),
            ],
        }
        proc, capture, state = self.run_skill(
            "review-this-plan",
            '{"plan_for_review":"Review the current plan."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks acceptable.",
            initial_legacy_config=legacy_config,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertIn("resume", capture["argv"])
        self.assertIn("legacy-structured-session", capture["argv"])
        self.assertIn("Migration notice:", proc.stdout)
        self.assertIn("was read, normalized, and rewritten into the canonical config", proc.stdout)
        self.assertIn("User-authored reminder text was left unchanged.", proc.stdout)
        payload = state["mams_channels_payload"]
        assert payload is not None
        self.assertEqual(payload["version"], 5)
        self.assertIn("mams_invoker", payload)
        self.assertNotIn("claude", payload)
        self.assertEqual(payload["mams_invoker"]["baseline"], "Keep the original task stable.")
        self.assertEqual(payload["mams_invoker"]["stage_guidance"]["review-this-plan"], "Require concrete scope.")
        self.assertEqual(payload["shared_stages"]["sync"], "Discussion only.")
        self.assertTrue(payload["mams_invoker"]["can_mutate"])
        self.assertNotIn("work_modes", payload)

    def test_named_mams_channel_is_created_when_selected(self) -> None:
        proc, _capture, state = self.run_skill(
            "init",
            '{"task_background":"Current task brief"}',
            "## Task Understanding Reply\n\nSwitch to managed execution.",
            mams_channel_name="reviewer-a",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        mams_channel = self.find_mams_channel(state, "reviewer-a")
        self.assertEqual(mams_channel["session_id"], "test-session")
        self.assertEqual(mams_channel["description"], "Managed MAMS channel 'reviewer-a'.")

    def test_effective_defaults_are_persisted_for_new_mams_channel(self) -> None:
        proc, _capture, state = self.run_skill(
            "init",
            '{"task_background":"Current task brief"}',
            "## Task Understanding Reply\n\nLooks consistent.",
            mams_channel_name="baseline",
            env_extra={
                "CODEX_MODEL": "gpt-test",
                "CODEX_REASONING_EFFORT": "high",
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        mams_channel = self.find_mams_channel(state, "baseline")
        self.assertEqual(mams_channel["model"], "gpt-test")
        self.assertEqual(mams_channel["reasoning_effort"], "high")

    def test_configure_updates_mams_invoker_and_mams_channel_fields(self) -> None:
        proc, _capture, state = self.run_skill(
            "configure",
            json.dumps(
                {
                    "mams_invoker": {
                    "baseline": "Keep original requirements stable.",
                    "working_style": "Discuss before mutating.",
                    "stage_guidance": {
                        "review-this-plan": "Challenge weak evidence first."
                    },
                    "can_mutate": False,
                },
                "shared_stages": {
                    "init": "Always re-check continuity assumptions."
                },
                    "mams_channels": [
                        {
                            "name": "reviewer-a",
                            "focus": "Watch for architectural drift.",
                            "baseline": "Do not let local convenience override the original task.",
                            "stage_guidance": {
                                "review-this-plan": "Push back on scope creep."
                            },
                            "can_mutate": False,
                            "model": "gpt-review",
                            "reasoning_effort": "high",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            initial_mams_channels=[self.build_mams_channel("default", session_id="existing-session")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = state["mams_channels_payload"]
        assert payload is not None
        self.assertEqual(payload["mams_invoker"]["baseline"], "Keep original requirements stable.")
        self.assertFalse(payload["mams_invoker"]["can_mutate"])
        self.assertEqual(payload["shared_stages"]["init"], "Always re-check continuity assumptions.")
        reviewer = self.find_mams_channel(state, "reviewer-a")
        self.assertEqual(reviewer["focus"], "Watch for architectural drift.")
        self.assertFalse(reviewer["can_mutate"])
        self.assertEqual(reviewer["model"], "gpt-review")

    def test_update_config_accepts_empty_stdin_and_creates_canonical_config(self) -> None:
        proc, _capture, state = self.run_skill(
            "update-config",
            "",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(state["mams_channels_exists"])
        payload = state["mams_channels_payload"]
        assert payload is not None
        self.assertEqual(payload["version"], 5)
        self.assertEqual(payload["mams_channels"], [])
        self.assertIn("update-config applied.", proc.stdout)
        self.assertIn("Created a canonical managed config because no prior managed config was present.", proc.stdout)

    def test_prompt_includes_config_sections_and_ref_notice(self) -> None:
        proc, capture, _state = self.run_skill(
            "review-this-plan",
            '{"plan_for_review":"Review the plan against [[REF:.mad-agent-mesh/refs/rules.md::Rule 5]]."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks acceptable.",
            initial_mams_channels=[
                self.build_mams_channel(
                    "default",
                    session_id="existing-session",
                    focus="Watch for drift against [[REF:.mad-agent-mesh/refs/rules.md::Rule 5]].",
                    baseline="Keep the original requirements stable.",
                    stage_guidance={"review-this-plan": "Use [[REF:.mad-agent-mesh/refs/rules.md::Rule 10]]."},
                )
            ],
            ref_files={
                ".mad-agent-mesh/refs/rules.md": "# Rules\n\nRule 5\nRule 10\n",
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertIn("<<<MAMS_REMINDER_FULL.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<MAMS_REMINDER_FULL.END>>>", capture["stdin"])
        self.assertIn("<<<USER_REMINDER.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<USER_REMINDER.END>>>", capture["stdin"])
        self.assertIn("<<<REFERENCE_NOTICE.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<REFERENCE_NOTICE.END>>>", capture["stdin"])
        self.assertIn("<<<PLAN_FOR_REVIEW.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<PLAN_FOR_REVIEW.END>>>", capture["stdin"])
        self.assertIn("## Mad Agent Mesh Reminder (Full)", capture["stdin"])
        self.assertIn("## User Reminder", capture["stdin"])
        self.assertIn("## Reference Handling Notice", capture["stdin"])
        self.assertIn("[[REF:.mad-agent-mesh/refs/rules.md::Rule 5]]", capture["stdin"])
        self.assertIn("### MAMS Channel Focus", capture["stdin"])
        self.assertIn("### MAMS Channel Stage Guidance", capture["stdin"])

    def test_caller_side_guidance_is_not_sent_to_codex_but_is_returned_to_caller(self) -> None:
        initial_config = self.build_config(
            [
                self.build_mams_channel(
                    "default",
                    session_id="existing-session",
                    focus="Watch for architectural drift.",
                    baseline="Keep the original requirements stable.",
                )
            ],
            mams_invoker={
                "baseline": "The mams_invoker must keep the original user constraints stable.",
                "working_style": "Use Mad Agent Mesh, not raw runner CLIs.",
                "extra_context": None,
                "stage_guidance": {
                    "review-this-plan": "Before execution, insist on a concrete plan."
                },
                "can_mutate": False,
            },
            shared_stages={
                "review-this-plan": "This is a shared hard-gate stage."
            },
        )
        proc, capture, _state = self.run_skill(
            "review-this-plan",
            '{"plan_for_review":"Review the concrete plan."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks acceptable.",
            initial_config=initial_config,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertNotIn("## MAMS Invoker Baseline", capture["stdin"])
        self.assertNotIn("## MAMS Invoker Working Style", capture["stdin"])
        self.assertNotIn("## MAMS Invoker Stage Guidance", capture["stdin"])
        self.assertIn("### Shared Stage Guidance", capture["stdin"])
        self.assertIn("<<<MAMS_REMINDER_FULL.BEGIN>>>", proc.stdout)
        self.assertIn("<<<USER_REMINDER.BEGIN>>>", proc.stdout)
        self.assertIn("<<<CHANNEL_REPLY.BEGIN>>>", proc.stdout)
        self.assertIn("<<<CHANNEL_REPLY.END>>>", proc.stdout)
        self.assertIn("## Mad Agent Mesh Reminder (Full)", proc.stdout)
        self.assertIn("## User Reminder", proc.stdout)
        self.assertIn("### MAMS Invoker Baseline", proc.stdout)
        self.assertIn("### MAMS Invoker Working Style", proc.stdout)
        self.assertIn("### MAMS Invoker Mutation Permission", proc.stdout)
        self.assertIn("### MAMS Invoker Stage Guidance", proc.stdout)
        self.assertIn("### Shared Stage Guidance", proc.stdout)
        self.assertIn("## Channel Reply", proc.stdout)

    def test_non_init_turns_use_full_then_brief_reminder_cadence(self) -> None:
        initial_config = self.build_config(
            [
                self.build_mams_channel(
                    "default",
                    session_id="existing-session",
                    focus="Watch for architectural drift.",
                    baseline="Keep the original requirements stable.",
                    reminder_turn_count=1,
                )
            ],
            mams_invoker={
                "baseline": "Caller baseline text.",
                "working_style": "Caller working style.",
                "extra_context": None,
                "stage_guidance": {},
                "can_mutate": False,
            },
        )
        proc, capture, state = self.run_skill(
            "sync",
            '{"sync_message":"Continue the discussion."}',
            "## Discussion Reply\n\nNormal discussion reply.",
            initial_config=initial_config,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertIn("<<<MAMS_REMINDER_BRIEF.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<USER_REMINDER.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<SYNC_MESSAGE.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<SYNC_MESSAGE.END>>>", capture["stdin"])
        self.assertIn("## Mad Agent Mesh Reminder (Brief)", capture["stdin"])
        self.assertIn("## User Reminder", capture["stdin"])
        self.assertIn("configured User Reminder still applies in full".lower(), capture["stdin"].lower())
        self.assertIn("### MAMS Channel Focus", capture["stdin"])
        self.assertIn("## Mad Agent Mesh Reminder (Brief)", proc.stdout)
        self.assertIn("## User Reminder", proc.stdout)
        self.assertIn("### MAMS Invoker Baseline", proc.stdout)
        mams_channel = self.find_mams_channel(state, "default")
        self.assertEqual(mams_channel["reminder_turn_count"], 2)

    def test_review_this_work_reminder_warns_not_to_stop_after_scope_pass(self) -> None:
        proc, _capture, _state = self.run_skill(
            "review-this-work",
            '{"work_for_review":"Changed one agreed sub-step and verified the relevant tests."}',
            "approved_work: true\n\n## Work Review Reply\n\nStep accepted; continue.\n",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("approved_work: true accepts only the reviewed execution scope", proc.stdout)
        self.assertIn("continue directly instead of stopping", proc.stdout)

    def test_missing_ref_file_fails_the_call(self) -> None:
        proc, _capture, _state = self.run_skill(
            "sync",
            '{"sync_message":"Please keep [[REF:.mad-agent-mesh/refs/missing.md::Rule 2]] in mind."}',
            initial_mams_channels=[self.build_mams_channel("default", session_id="existing-session")],
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Referenced file does not exist", proc.stderr)

    def test_dangerous_new_session_replaces_current_named_agent_and_records_previous_ids(self) -> None:
        proc, capture, state = self.run_skill(
            "dangerous-new-session",
            '{"user_permission":"The user explicitly asked to abandon the old managed continuity and start fresh."}',
            "fresh managed session ready.",
            mams_channel_name="reviewer-a",
            initial_mams_channels=[
                self.build_mams_channel("default", session_id="default-session", previous_session_ids=["older-default"]),
                self.build_mams_channel("reviewer-a", session_id="old-session", previous_session_ids=["older-session", "oldest-session"]),
            ],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertNotIn("resume", capture["argv"])
        reviewer = self.find_mams_channel(state, "reviewer-a")
        self.assertEqual(reviewer["session_id"], "test-session")
        self.assertEqual(reviewer["previous_session_ids"], ["old-session", "older-session"])
        default = self.find_mams_channel(state, "default")
        self.assertEqual(default["session_id"], "default-session")
        self.assertIn("Target mams_channel: reviewer-a", proc.stdout)

    def test_dangerous_new_session_can_switch_target_session_id_and_update_saved_settings(self) -> None:
        proc, capture, state = self.run_skill(
            "dangerous-new-session",
            '{"user_permission":"The user explicitly asked to switch back to a specific prior managed session.","target_session_id":"restored-session","mams_channel_description":"Reviewer A for plan gate.","model":"gpt-review","reasoning_effort":"medium"}',
            mams_channel_name="reviewer-a",
            initial_mams_channels=[
                self.build_mams_channel(
                    "reviewer-a",
                    description="Old description",
                    session_id="current-session",
                    model="old-model",
                    reasoning_effort="low",
                    previous_session_ids=["older-session", "oldest-session"],
                )
            ],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsNone(capture)
        reviewer = self.find_mams_channel(state, "reviewer-a")
        self.assertEqual(reviewer["session_id"], "restored-session")
        self.assertEqual(reviewer["description"], "Reviewer A for plan gate.")
        self.assertEqual(reviewer["model"], "gpt-review")
        self.assertEqual(reviewer["reasoning_effort"], "medium")
        self.assertEqual(reviewer["previous_session_ids"], ["current-session", "older-session"])

    def test_sync_uses_read_only_and_accepts_markdown_sections(self) -> None:
        proc, capture, _state = self.run_skill(
            "sync",
            '{"sync_message":"Please respond to the current review feedback."}',
            "## Discussion Reply\n\nI agree with the concern.\n\n## Plan\n\nRepair the parser first.",
            initial_mams_channels=[self.build_mams_channel("default", session_id="existing-session")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("<<<SYNC_MESSAGE.BEGIN>>>", capture["stdin"])
        self.assertIn("Sync message from the mams_invoker:", capture["stdin"])
        self.assertIn("## Plan", proc.stdout)

    def test_execute_this_plan_defaults_to_workspace_write(self) -> None:
        proc, capture, _state = self.run_skill(
            "execute-this-plan",
            '{"approved_plan":"Implement the approved parser fix and complete the approved plan."}',
            "Updated parser, ran validation, stopped for review.",
            initial_mams_channels=[self.build_mams_channel("default", session_id="existing-session")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "workspace-write")
        self.assertIn("<<<EXECUTION_SANDBOX.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<APPROVED_PLAN.BEGIN>>>", capture["stdin"])
        self.assertIn("workspace-write (default mutation sandbox)", capture["stdin"])
        self.assertIn("Approved plan from the mams_invoker:", capture["stdin"])

    def test_execute_this_plan_part_full_access_escalates_to_danger_full_access(self) -> None:
        proc, capture, _state = self.run_skill(
            "execute-this-plan-part",
            '{"approved_plan_part":"Run the approved large repair tranche.","sandbox_mode":"full-access"}',
            "Ran the approved repair under full access and stopped.",
            initial_mams_channels=[self.build_mams_channel("default", session_id="existing-session")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "danger-full-access")
        self.assertIn("<<<EXECUTION_SANDBOX.BEGIN>>>", capture["stdin"])
        self.assertIn("<<<APPROVED_PLAN_PART.BEGIN>>>", capture["stdin"])
        self.assertIn(
            "danger-full-access (explicit full-access escalation approved by the mams_invoker)",
            capture["stdin"],
        )
        self.assertIn("Approved plan part from the mams_invoker:", capture["stdin"])

    def test_claude_code_runner_creates_session_and_uses_plan_permission_for_review(self) -> None:
        proc, capture, state = self.run_skill(
            "review-this-plan",
            '{"plan_for_review":"Review the current plan."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks acceptable.",
            initial_mams_channels=[
                self.build_mams_channel("planner", runner="claude-code", can_mutate=False)
            ],
            mams_channel_name="planner",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(capture["runner"], "claude-code")
        self.assertIn("--permission-mode", capture["argv"])
        permission_mode = capture["argv"][capture["argv"].index("--permission-mode") + 1]
        self.assertEqual(permission_mode, "plan")
        self.assertNotIn("--resume", capture["argv"])
        planner = self.find_mams_channel(state, "planner")
        self.assertEqual(planner["session_id"], "claude-session")
        self.assertEqual(planner["runner"], "claude-code")

    def test_claude_code_runner_resumes_existing_session(self) -> None:
        proc, capture, _state = self.run_skill(
            "sync",
            '{"sync_message":"Continue the planning discussion."}',
            "## Discussion Reply\n\nContinue with the approved direction.",
            initial_mams_channels=[
                self.build_mams_channel(
                    "planner",
                    runner="claude-code",
                    can_mutate=False,
                    session_id="claude-existing-session",
                )
            ],
            mams_channel_name="planner",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(capture["runner"], "claude-code")
        self.assertIn("--resume", capture["argv"])
        self.assertIn("claude-existing-session", capture["argv"])

    def test_claude_code_runner_uses_accept_edits_for_execute(self) -> None:
        proc, capture, state = self.run_skill(
            "execute-this-plan",
            '{"approved_plan":"Implement the approved plan."}',
            "Implemented the approved plan and stopped for review.",
            initial_mams_channels=[
                self.build_mams_channel("executor", runner="claude-code", can_mutate=True)
            ],
            mams_channel_name="executor",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(capture["runner"], "claude-code")
        permission_mode = capture["argv"][capture["argv"].index("--permission-mode") + 1]
        self.assertEqual(permission_mode, "acceptEdits")
        executor = self.find_mams_channel(state, "executor")
        self.assertEqual(executor["session_id"], "claude-session")

    def test_invoke_supports_mixed_codex_and_claude_code_runners(self) -> None:
        payload = json.dumps(
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
        )
        proc, _capture, state = self.run_skill(
            "invoke",
            payload,
            initial_mams_channels=[
                self.build_mams_channel("reviewer-a", can_mutate=False, runner="codex"),
                self.build_mams_channel("reviewer-b", can_mutate=False, runner="claude-code"),
            ],
            env_extra={
                "FAKE_CHANNEL_REPLY_MAP": json.dumps(
                    {
                        "Plan A": "approved_to_mutate: true\n\n## Plan Review Reply\n\nReviewer A approves.",
                        "Plan B": "approved_to_mutate: false\n\n## Plan Review Reply\n\nReviewer B blocks.",
                    },
                    ensure_ascii=False,
                ),
                "FAKE_CODEX_SESSION_MAP": json.dumps(
                    {"Plan A": "codex-session-a", "Plan B": "claude-session-b"},
                    ensure_ascii=False,
                ),
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("reviewer-a · review-this-plan · ok", proc.stdout)
        self.assertIn("reviewer-b · review-this-plan · ok", proc.stdout)
        reviewer_a = self.find_mams_channel(state, "reviewer-a")
        reviewer_b = self.find_mams_channel(state, "reviewer-b")
        self.assertEqual(reviewer_a["session_id"], "codex-session-a")
        self.assertEqual(reviewer_b["session_id"], "claude-session-b")

    def test_execute_this_plan_rejects_non_mutating_mams_channel(self) -> None:
        proc, _capture, _state = self.run_skill(
            "execute-this-plan",
            '{"approved_plan":"Implement the approved parser fix and complete the approved plan."}',
            initial_mams_channels=[self.build_mams_channel("reviewer-a", session_id="existing-session", can_mutate=False)],
            mams_channel_name="reviewer-a",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("can_mutate: false", proc.stderr)
        self.assertIn("mutate-capable mams_channel", proc.stderr)

    def test_invoke_fanout_returns_settled_results_and_updates_channels(self) -> None:
        payload = json.dumps(
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
        )
        proc, _capture, state = self.run_skill(
            "invoke",
            payload,
            initial_mams_channels=[
                self.build_mams_channel("reviewer-a", can_mutate=False),
                self.build_mams_channel("reviewer-b", can_mutate=False),
            ],
            env_extra={
                "FAKE_CHANNEL_REPLY_MAP": json.dumps(
                    {
                        "Plan A": "approved_to_mutate: true\n\n## Plan Review Reply\n\nReviewer A approves.",
                        "Plan B": "approved_to_mutate: false\n\n## Plan Review Reply\n\nReviewer B blocks.",
                    },
                    ensure_ascii=False,
                ),
                "FAKE_CODEX_SESSION_MAP": json.dumps(
                    {"Plan A": "session-a", "Plan B": "session-b"},
                    ensure_ascii=False,
                ),
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<<<INVOKE_SUMMARY.BEGIN>>>", proc.stdout)
        self.assertIn("<<<INVOKE_RESULT.BEGIN>>>", proc.stdout)
        self.assertIn("## Invoke Summary", proc.stdout)
        self.assertIn("reviewer-a · review-this-plan · ok", proc.stdout)
        self.assertIn("reviewer-b · review-this-plan · ok", proc.stdout)
        self.assertIn("Execution mode: concurrent read-only fanout", proc.stdout)
        self.assertIn("do not wrap these calls in external polling", proc.stdout)
        reviewer_a = self.find_mams_channel(state, "reviewer-a")
        reviewer_b = self.find_mams_channel(state, "reviewer-b")
        self.assertEqual(reviewer_a["session_id"], "session-a")
        self.assertEqual(reviewer_b["session_id"], "session-b")
        self.assertEqual(reviewer_a["reminder_turn_count"], 1)
        self.assertEqual(reviewer_b["reminder_turn_count"], 1)

    def test_invoke_reports_partial_failures_without_failing_fast(self) -> None:
        payload = json.dumps(
            {
                "requests": [
                    {
                        "command": "sync",
                        "mams_channel": "planner",
                        "input": {"sync_message": "to planner"},
                    },
                    {
                        "command": "review-this-plan",
                        "mams_channel": "reviewer-a",
                        "input": {"plan_for_review": "Broken Plan"},
                    },
                ]
            },
            ensure_ascii=False,
        )
        proc, _capture, state = self.run_skill(
            "invoke",
            payload,
            initial_mams_channels=[
                self.build_mams_channel("planner", can_mutate=False),
                self.build_mams_channel("reviewer-a", can_mutate=False),
            ],
            env_extra={
                "FAKE_CHANNEL_REPLY_MAP": json.dumps(
                    {
                        "to planner": "## Discussion Reply\n\nPlanner sync succeeded.",
                    },
                    ensure_ascii=False,
                ),
                "FAKE_CODEX_ERROR_MAP": json.dumps(
                    {"Broken Plan": "synthetic reviewer failure"},
                    ensure_ascii=False,
                ),
                "FAKE_CODEX_SESSION_MAP": json.dumps(
                    {"to planner": "planner-session"},
                    ensure_ascii=False,
                ),
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<<<INVOKE_SUMMARY.BEGIN>>>", proc.stdout)
        self.assertIn("<<<INVOKE_RESULT.BEGIN>>>", proc.stdout)
        self.assertIn("- Succeeded: 1", proc.stdout)
        self.assertIn("- Failed: 1", proc.stdout)
        self.assertIn("planner · sync · ok", proc.stdout)
        self.assertIn("reviewer-a · review-this-plan · error", proc.stdout)
        self.assertIn("synthetic reviewer failure", proc.stdout)
        planner = self.find_mams_channel(state, "planner")
        reviewer = self.find_mams_channel(state, "reviewer-a")
        self.assertEqual(planner["session_id"], "planner-session")
        self.assertIsNone(reviewer["session_id"])

    def test_invoke_rejects_duplicate_channel_targets(self) -> None:
        payload = json.dumps(
            {
                "requests": [
                    {
                        "command": "sync",
                        "mams_channel": "planner",
                        "input": {"sync_message": "first"},
                    },
                    {
                        "command": "sync",
                        "mams_channel": "planner",
                        "input": {"sync_message": "second"},
                    },
                ]
            },
            ensure_ascii=False,
        )
        proc, _capture, _state = self.run_skill("invoke", payload)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("does not allow duplicate mams_channel targets", proc.stderr)

    def test_missing_thread_error_requires_explicit_dangerous_reset(self) -> None:
        proc, _capture, _state = self.run_skill(
            "review-this-work",
            '{"work_for_review":"Please review the completed work."}',
            initial_mams_channels=[self.build_mams_channel("default", session_id="stale-session")],
            error="thread stale-session not found",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("could not resume", proc.stderr)
        self.assertIn("dangerous-new-session", proc.stderr)
        self.assertIn("managed mams_channel 'default'", proc.stderr)

    def test_review_this_plan_rejects_legacy_json_reply(self) -> None:
        proc, _capture, _state = self.run_skill(
            "review-this-plan",
            '{"plan_for_review":"Change only the prompt parser and update tests."}',
            '{"approved_to_mutate":true,"plan_review_reply":"legacy json"}',
            initial_mams_channels=[self.build_mams_channel("default", session_id="existing-session")],
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("approved_to_mutate must be the first non-empty line", proc.stderr)


if __name__ == "__main__":
    unittest.main()

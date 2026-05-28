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
CHANNELS_FILENAME = "cxsk_channels.json"
LEGACY_SESSION_FILENAME = "codex_session.json"
LEGACY_HISTORY_FILENAME = "codex_session_history.json"
MANAGED_DIRNAME = ".codex-skill"
LEGACY_DIRNAME = ".claude"

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

    session_id = "test-session"
    if "resume" in args:
        try:
            session_id = args[args.index("resume") + 1]
        except Exception:
            session_id = "test-session"

    Path(out_path).write_text(reply, encoding="utf-8")
    print(json.dumps({"type": "session_meta", "payload": {"id": session_id, "originator": "codex_exec", "source": "exec"}}))
    """
)


class CodexSkillIntegrationTests(unittest.TestCase):
    maxDiff = None

    def build_cxsk_channel(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        focus: Optional[str] = None,
        baseline: Optional[str] = None,
        extra_context: Optional[str] = None,
        stage_guidance: Optional[dict[str, str]] = None,
        can_mutate: bool = True,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        previous_session_ids: Optional[list[str]] = None,
        reminder_turn_count: int = 0,
    ) -> dict:
        return {
            "name": name,
            "description": description or f"Managed CXSK channel '{name}'.",
            "focus": focus,
            "baseline": baseline,
            "extra_context": extra_context,
            "stage_guidance": stage_guidance or {},
            "can_mutate": can_mutate,
            "session_id": session_id,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "previous_session_ids": previous_session_ids or [],
            "reminder_turn_count": reminder_turn_count,
            "updated_at": "2026-05-26T00:00:00Z",
        }

    def build_config(
        self,
        cxsk_channels: list[dict],
        *,
        cxsk_invoker: Optional[dict] = None,
        shared_stages: Optional[dict[str, str]] = None,
    ) -> dict:
        return {
            "version": 5,
            "cxsk_invoker": cxsk_invoker or {
                "baseline": None,
                "working_style": None,
                "extra_context": None,
                "stage_guidance": {},
                "can_mutate": True,
            },
            "shared_stages": shared_stages or {},
            "cxsk_channels": cxsk_channels,
            "updated_at": "2026-05-26T00:00:00Z",
        }

    def run_skill(
        self,
        cmd: str,
        payload: str,
        reply: str = "",
        *,
        cxsk_channel_name: str = "default",
        initial_config: Optional[dict] = None,
        initial_legacy_config: Optional[dict] = None,
        initial_cxsk_channels: Optional[list[dict]] = None,
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
            elif initial_cxsk_channels is not None:
                (managed_dir / CHANNELS_FILENAME).write_text(
                    json.dumps(self.build_config(initial_cxsk_channels), ensure_ascii=False, indent=2) + "\n",
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

            env = os.environ.copy()
            env["CODEX_BIN"] = str(fake_codex)
            env["CODEX_HOME"] = str(tmp / "codex-home")
            env["FAKE_CODEX_REPLY"] = reply
            capture_path = tmp / "capture.json"
            env["FAKE_CODEX_CAPTURE"] = str(capture_path)
            if error is not None:
                env["FAKE_CODEX_ERROR"] = error
            if env_extra:
                env.update(env_extra)

            argv = [sys.executable, str(SCRIPT), "--cwd", str(workspace), "--cxsk-channel", cxsk_channel_name]
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
                "cxsk_channels_exists": agents_path.exists(),
                "cxsk_channels_payload": (
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
    def find_cxsk_channel(state: dict, name: str) -> dict:
        cxsk_channels_payload = state["cxsk_channels_payload"] or {}
        cxsk_channels = cxsk_channels_payload.get("cxsk_channels", [])
        for cxsk_channel in cxsk_channels:
            if cxsk_channel["name"] == name:
                return cxsk_channel
        raise AssertionError(f"CXSK channel not found in state: {name}")

    def test_existing_agent_session_is_resumed_by_default(self) -> None:
        proc, capture, _state = self.run_skill(
            "review-my-plan",
            '{"plan_for_review":"Change only the prompt parser and update tests."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nBoundary is acceptable.",
            initial_cxsk_channels=[self.build_cxsk_channel("default", session_id="resume-me")],
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
        self.assertTrue(state["cxsk_channels_exists"])
        cxsk_channel = self.find_cxsk_channel(state, "default")
        self.assertEqual(cxsk_channel["session_id"], "test-session")
        self.assertEqual(cxsk_channel["name"], "default")

    def test_legacy_single_session_is_migrated_once_before_resume(self) -> None:
        proc, capture, state = self.run_skill(
            "review-my-plan",
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
        cxsk_channel = self.find_cxsk_channel(state, "default")
        self.assertEqual(cxsk_channel["session_id"], "legacy-session")
        self.assertEqual(cxsk_channel["previous_session_ids"], ["older-session", "oldest-session"])

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
            "cxsk_channels": [
                self.build_cxsk_channel("default", session_id="legacy-structured-session"),
            ],
        }
        proc, capture, state = self.run_skill(
            "review-my-plan",
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
        payload = state["cxsk_channels_payload"]
        assert payload is not None
        self.assertEqual(payload["version"], 5)
        self.assertIn("cxsk_invoker", payload)
        self.assertNotIn("claude", payload)
        self.assertEqual(payload["cxsk_invoker"]["baseline"], "Keep the original task stable.")
        self.assertTrue(payload["cxsk_invoker"]["can_mutate"])
        self.assertNotIn("work_modes", payload)

    def test_named_cxsk_channel_is_created_when_selected(self) -> None:
        proc, _capture, state = self.run_skill(
            "init",
            '{"task_background":"Current task brief"}',
            "## Task Understanding Reply\n\nSwitch to Codex-owned execution.",
            cxsk_channel_name="reviewer-a",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        cxsk_channel = self.find_cxsk_channel(state, "reviewer-a")
        self.assertEqual(cxsk_channel["session_id"], "test-session")
        self.assertEqual(cxsk_channel["description"], "Managed CXSK channel 'reviewer-a'.")

    def test_effective_defaults_are_persisted_for_new_cxsk_channel(self) -> None:
        proc, _capture, state = self.run_skill(
            "init",
            '{"task_background":"Current task brief"}',
            "## Task Understanding Reply\n\nLooks consistent.",
            cxsk_channel_name="baseline",
            env_extra={
                "CODEX_MODEL": "gpt-test",
                "CODEX_REASONING_EFFORT": "high",
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        cxsk_channel = self.find_cxsk_channel(state, "baseline")
        self.assertEqual(cxsk_channel["model"], "gpt-test")
        self.assertEqual(cxsk_channel["reasoning_effort"], "high")

    def test_configure_updates_cxsk_invoker_and_cxsk_channel_fields(self) -> None:
        proc, _capture, state = self.run_skill(
            "configure",
            json.dumps(
                {
                    "cxsk_invoker": {
                        "baseline": "Keep original requirements stable.",
                    "working_style": "Discuss before mutating.",
                    "stage_guidance": {
                        "review-my-plan": "Challenge weak evidence first."
                    },
                    "can_mutate": False,
                },
                "shared_stages": {
                    "init": "Always re-check continuity assumptions."
                },
                    "cxsk_channels": [
                        {
                            "name": "reviewer-a",
                            "focus": "Watch for architectural drift.",
                            "baseline": "Do not let local convenience override the original task.",
                            "stage_guidance": {
                                "review-my-plan": "Push back on scope creep."
                            },
                            "can_mutate": False,
                            "model": "gpt-review",
                            "reasoning_effort": "high",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            initial_cxsk_channels=[self.build_cxsk_channel("default", session_id="existing-session")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = state["cxsk_channels_payload"]
        assert payload is not None
        self.assertEqual(payload["cxsk_invoker"]["baseline"], "Keep original requirements stable.")
        self.assertFalse(payload["cxsk_invoker"]["can_mutate"])
        self.assertEqual(payload["shared_stages"]["init"], "Always re-check continuity assumptions.")
        reviewer = self.find_cxsk_channel(state, "reviewer-a")
        self.assertEqual(reviewer["focus"], "Watch for architectural drift.")
        self.assertFalse(reviewer["can_mutate"])
        self.assertEqual(reviewer["model"], "gpt-review")

    def test_update_config_accepts_empty_stdin_and_creates_canonical_config(self) -> None:
        proc, _capture, state = self.run_skill(
            "update-config",
            "",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(state["cxsk_channels_exists"])
        payload = state["cxsk_channels_payload"]
        assert payload is not None
        self.assertEqual(payload["version"], 5)
        self.assertEqual(payload["cxsk_channels"], [])
        self.assertIn("update-config applied.", proc.stdout)
        self.assertIn("Created a canonical managed config because no prior managed config was present.", proc.stdout)

    def test_prompt_includes_config_sections_and_ref_notice(self) -> None:
        proc, capture, _state = self.run_skill(
            "review-my-plan",
            '{"plan_for_review":"Review the plan against [[REF:.codex-skill/refs/rules.md::Rule 5]]."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks acceptable.",
            initial_cxsk_channels=[
                self.build_cxsk_channel(
                    "default",
                    session_id="existing-session",
                    focus="Watch for drift against [[REF:.codex-skill/refs/rules.md::Rule 5]].",
                    baseline="Keep the original requirements stable.",
                    stage_guidance={"review-my-plan": "Use [[REF:.codex-skill/refs/rules.md::Rule 10]]."},
                )
            ],
            ref_files={
                ".codex-skill/refs/rules.md": "# Rules\n\nRule 5\nRule 10\n",
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertIn("## Codex Skill Reminder (Full)", capture["stdin"])
        self.assertIn("## User Reminder (Full)", capture["stdin"])
        self.assertIn("## Reference Handling Notice", capture["stdin"])
        self.assertIn("[[REF:.codex-skill/refs/rules.md::Rule 5]]", capture["stdin"])
        self.assertIn("### CXSK Channel Focus", capture["stdin"])
        self.assertIn("### CXSK Channel Stage Guidance", capture["stdin"])

    def test_caller_side_guidance_is_not_sent_to_codex_but_is_returned_to_caller(self) -> None:
        initial_config = self.build_config(
            [
                self.build_cxsk_channel(
                    "default",
                    session_id="existing-session",
                    focus="Watch for architectural drift.",
                    baseline="Keep the original requirements stable.",
                )
            ],
            cxsk_invoker={
                "baseline": "The cxsk_invoker must keep the original user constraints stable.",
                "working_style": "Use Codex Skill, not raw Codex.",
                "extra_context": None,
                "stage_guidance": {
                    "review-my-plan": "Before mutation, insist on a concrete plan."
                },
                "can_mutate": False,
            },
            shared_stages={
                "review-my-plan": "This is a shared hard-gate stage."
            },
        )
        proc, capture, _state = self.run_skill(
            "review-my-plan",
            '{"plan_for_review":"Review the concrete plan."}',
            "approved_to_mutate: true\n\n## Plan Review Reply\n\nLooks acceptable.",
            initial_config=initial_config,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertNotIn("## CXSK Invoker Baseline", capture["stdin"])
        self.assertNotIn("## CXSK Invoker Working Style", capture["stdin"])
        self.assertNotIn("## CXSK Invoker Stage Guidance", capture["stdin"])
        self.assertIn("### Shared Stage Guidance", capture["stdin"])
        self.assertIn("## Codex Skill Reminder (Full)", proc.stdout)
        self.assertIn("## User Reminder (Full)", proc.stdout)
        self.assertIn("### CXSK Invoker Baseline", proc.stdout)
        self.assertIn("### CXSK Invoker Working Style", proc.stdout)
        self.assertIn("### CXSK Invoker Mutation Permission", proc.stdout)
        self.assertIn("### CXSK Invoker Stage Guidance", proc.stdout)
        self.assertIn("### Shared Stage Guidance", proc.stdout)
        self.assertIn("## Codex Reply", proc.stdout)

    def test_non_init_turns_use_full_then_brief_reminder_cadence(self) -> None:
        initial_config = self.build_config(
            [
                self.build_cxsk_channel(
                    "default",
                    session_id="existing-session",
                    focus="Watch for architectural drift.",
                    baseline="Keep the original requirements stable.",
                    reminder_turn_count=1,
                )
            ],
            cxsk_invoker={
                "baseline": "Caller baseline text.",
                "working_style": "Caller working style.",
                "extra_context": None,
                "stage_guidance": {},
                "can_mutate": False,
            },
        )
        proc, capture, state = self.run_skill(
            "chat",
            '{"message_for_codex":"Continue the discussion."}',
            "Normal discussion reply.",
            initial_config=initial_config,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertIn("## Codex Skill Reminder (Brief)", capture["stdin"])
        self.assertIn("## User Reminder (Brief)", capture["stdin"])
        self.assertIn("configured User Reminder still applies".lower(), capture["stdin"].lower())
        self.assertNotIn("### CXSK Channel Focus", capture["stdin"])
        self.assertIn("## Codex Skill Reminder (Brief)", proc.stdout)
        self.assertIn("## User Reminder (Brief)", proc.stdout)
        self.assertNotIn("### CXSK Invoker Baseline", proc.stdout)
        cxsk_channel = self.find_cxsk_channel(state, "default")
        self.assertEqual(cxsk_channel["reminder_turn_count"], 2)

    def test_review_my_work_reminder_warns_not_to_stop_after_step_pass(self) -> None:
        proc, _capture, _state = self.run_skill(
            "review-my-work",
            '{"work_for_review":"Changed one agreed sub-step and verified the relevant tests."}',
            "approved_work: true\n\n## Work Review Reply\n\nStep accepted; continue.\n",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("approved_work: true accepts only the reviewed step", proc.stdout)
        self.assertIn("continue directly to the next step instead of stopping", proc.stdout)

    def test_missing_ref_file_fails_the_call(self) -> None:
        proc, _capture, _state = self.run_skill(
            "chat",
            '{"message_for_codex":"Please keep [[REF:.codex-skill/refs/missing.md::Rule 2]] in mind."}',
            initial_cxsk_channels=[self.build_cxsk_channel("default", session_id="existing-session")],
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Referenced file does not exist", proc.stderr)

    def test_dangerous_new_session_replaces_current_named_agent_and_records_previous_ids(self) -> None:
        proc, capture, state = self.run_skill(
            "dangerous-new-session",
            '{"user_permission":"The user explicitly asked to abandon the old Codex continuity and start fresh."}',
            "fresh managed session ready.",
            cxsk_channel_name="reviewer-a",
            initial_cxsk_channels=[
                self.build_cxsk_channel("default", session_id="default-session", previous_session_ids=["older-default"]),
                self.build_cxsk_channel("reviewer-a", session_id="old-session", previous_session_ids=["older-session", "oldest-session"]),
            ],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertNotIn("resume", capture["argv"])
        reviewer = self.find_cxsk_channel(state, "reviewer-a")
        self.assertEqual(reviewer["session_id"], "test-session")
        self.assertEqual(reviewer["previous_session_ids"], ["old-session", "older-session"])
        default = self.find_cxsk_channel(state, "default")
        self.assertEqual(default["session_id"], "default-session")
        self.assertIn("Target cxsk_channel: reviewer-a", proc.stdout)

    def test_dangerous_new_session_can_switch_target_session_id_and_update_saved_settings(self) -> None:
        proc, capture, state = self.run_skill(
            "dangerous-new-session",
            '{"user_permission":"The user explicitly asked to switch back to a specific prior Codex session.","target_session_id":"restored-session","cxsk_channel_description":"Reviewer A for plan gate.","model":"gpt-review","reasoning_effort":"medium"}',
            cxsk_channel_name="reviewer-a",
            initial_cxsk_channels=[
                self.build_cxsk_channel(
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
        reviewer = self.find_cxsk_channel(state, "reviewer-a")
        self.assertEqual(reviewer["session_id"], "restored-session")
        self.assertEqual(reviewer["description"], "Reviewer A for plan gate.")
        self.assertEqual(reviewer["model"], "gpt-review")
        self.assertEqual(reviewer["reasoning_effort"], "medium")
        self.assertEqual(reviewer["previous_session_ids"], ["current-session", "older-session"])

    def test_work_sync_uses_read_only_and_accepts_markdown_sections(self) -> None:
        proc, capture, _state = self.run_skill(
            "work-sync",
            '{"sync_message":"Please respond to the current review feedback."}',
            "## Discussion Reply\n\nI agree with the concern.\n\n## Plan\n\nRepair the parser first.",
            initial_cxsk_channels=[self.build_cxsk_channel("default", session_id="existing-session")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "read-only")
        self.assertIn("Sync message from the cxsk_invoker:", capture["stdin"])
        self.assertIn("## Plan", proc.stdout)

    def test_request_mutation_defaults_to_workspace_write(self) -> None:
        proc, capture, _state = self.run_skill(
            "request-mutation",
            '{"approved_mutation":"Implement the approved parser fix and stop."}',
            "Updated parser, ran validation, stopped for review.",
            initial_cxsk_channels=[self.build_cxsk_channel("default", session_id="existing-session")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "workspace-write")
        self.assertIn("workspace-write (default mutation sandbox)", capture["stdin"])
        self.assertIn("Approved mutation from the cxsk_invoker:", capture["stdin"])

    def test_request_mutation_full_access_escalates_to_danger_full_access(self) -> None:
        proc, capture, _state = self.run_skill(
            "request-mutation",
            '{"approved_mutation":"Run the approved repair step.","sandbox_mode":"full-access"}',
            "Ran the approved repair under full access and stopped.",
            initial_cxsk_channels=[self.build_cxsk_channel("default", session_id="existing-session")],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert capture is not None
        self.assertEqual(self.sandbox_from_argv(capture["argv"]), "danger-full-access")
        self.assertIn(
            "danger-full-access (explicit full-access escalation approved by the cxsk_invoker)",
            capture["stdin"],
        )

    def test_request_mutation_rejects_non_mutating_cxsk_channel(self) -> None:
        proc, _capture, _state = self.run_skill(
            "request-mutation",
            '{"approved_mutation":"Implement the approved parser fix and stop."}',
            initial_cxsk_channels=[self.build_cxsk_channel("reviewer-a", session_id="existing-session", can_mutate=False)],
            cxsk_channel_name="reviewer-a",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("can_mutate: false", proc.stderr)
        self.assertIn("mutate-capable cxsk_channel", proc.stderr)

    def test_missing_thread_error_requires_explicit_dangerous_reset(self) -> None:
        proc, _capture, _state = self.run_skill(
            "review-my-work",
            '{"work_for_review":"Please review the completed work."}',
            initial_cxsk_channels=[self.build_cxsk_channel("default", session_id="stale-session")],
            error="thread stale-session not found",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("could not resume", proc.stderr)
        self.assertIn("dangerous-new-session", proc.stderr)
        self.assertIn("managed cxsk_channel 'default'", proc.stderr)

    def test_review_my_plan_rejects_legacy_json_reply(self) -> None:
        proc, _capture, _state = self.run_skill(
            "review-my-plan",
            '{"plan_for_review":"Change only the prompt parser and update tests."}',
            '{"approved_to_mutate":true,"plan_review_reply":"legacy json"}',
            initial_cxsk_channels=[self.build_cxsk_channel("default", session_id="existing-session")],
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("approved_to_mutate must be the first non-empty line", proc.stderr)


if __name__ == "__main__":
    unittest.main()

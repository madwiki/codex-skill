#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional, Tuple


CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
DEFAULT_MODEL = os.environ.get("CODEX_MODEL")
DEFAULT_REASONING_EFFORT = os.environ.get("CODEX_REASONING_EFFORT")
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROMPTS_DIR = SKILL_ROOT / "prompts"

USER_MESSAGE_VERBATIM_TAG = "USER_MESSAGE_VERBATIM"
REVIEW_PLAN_FIELD = "plan_for_review"
REVIEW_PLAN_NEW_INFO_FIELD = "new_information"
REVIEW_PLAN_FRESH_USER_FIELD = "fresh_user_message"
REVIEW_PLAN_APPROVED_FIELD = "approved_to_mutate"
REVIEW_WORK_FIELD = "work_for_review"
REVIEW_WORK_NEW_INFO_FIELD = "new_information"
REVIEW_WORK_FRESH_USER_FIELD = "fresh_user_message"
REVIEW_WORK_APPROVED_FIELD = "approved_work"
SYNC_MESSAGE_FIELD = "sync_message"
SYNC_FRESH_USER_FIELD = "fresh_user_message"
SYNC_STAGE_CONTEXT_FIELD = "stage_context"
EXECUTE_PLAN_FIELD = "approved_plan"
EXECUTE_PLAN_PART_FIELD = "approved_plan_part"
EXECUTE_FRESH_USER_FIELD = "fresh_user_message"
EXECUTE_SANDBOX_MODE_FIELD = "sandbox_mode"
EXECUTE_SANDBOX_DEFAULT = "default"
EXECUTE_SANDBOX_FULL_ACCESS = "full-access"
DANGEROUS_NEW_SESSION_PERMISSION_FIELD = "user_permission"
DANGEROUS_NEW_SESSION_TARGET_FIELD = "target_session_id"
DANGEROUS_NEW_SESSION_MAMS_CHANNEL_DESCRIPTION_FIELD = "mams_channel_description"
DANGEROUS_NEW_SESSION_MODEL_FIELD = "model"
DANGEROUS_NEW_SESSION_REASONING_EFFORT_FIELD = "reasoning_effort"
CONFIGURE_MAMS_CHANNELS_FIELD = "mams_channels"
REVIEW_PLAN_REPLY_TITLE = "Plan Review Reply"
REVIEW_WORK_REPLY_TITLE = "Work Review Reply"
SYNC_REPLY_TITLE = "Discussion Reply"
SYNC_PLAN_TITLE = "Plan"
EXECUTE_WORK_REPORT_TITLE = "Work Report"
USER_ESCALATION_REQUEST_TITLE = "User Escalation Request"
GOVERNOR_ESCALATION_REVIEW_TOOL = "governor-user-escalation"
GOVERNOR_CHANNEL_NAME = "governor"
GOVERNOR_ESCALATE_FIELD = "escalate_to_user"
GOVERNOR_REVIEW_REPLY_TITLE = "Governor Review Reply"
SANDBOX_READ_ONLY = "read-only"
SANDBOX_WORKSPACE_WRITE = "workspace-write"
SANDBOX_DANGER_FULL_ACCESS = "danger-full-access"
PROCESS_POLL_INTERVAL_S = 20
PROCESS_IDLE_TIMEOUT_S = 600
MAMS_CHANNELS_FILENAME = "mams_channels.json"
MANAGED_DIRNAME = ".mad-agent-mesh"
DIAGNOSTICS_DIRNAME = "diagnostics"
DEFAULT_MAMS_CHANNEL_NAME = "default"
DEFAULT_MAMS_CHANNEL_DESCRIPTION = "Primary managed MAMS channel."
CONFIG_VERSION = 5
REF_DIRECTORY = f"{MANAGED_DIRNAME}/refs"
RUNNER_CODEX = "codex"
RUNNER_CLAUDE_CODE = "claude-code"
SUPPORTED_RUNNERS = {RUNNER_CODEX, RUNNER_CLAUDE_CODE}
REF_PATTERN = re.compile(r"\[\[REF:(?P<path>[^:\]]+?)(?:::(?P<locator>[^\]]+))?\]\]")
TOOL_HELP = {
    "invoke": "Invoke one or more mams_channel commands through one blocking wrapper call (reads JSON from stdin).",
    "sync": "Discussion / coordination / disagreement-resolution turn (reads JSON from stdin).",
    "review-this-plan": "Review the submitted plan on the targeted managed channel without mutating state (reads JSON from stdin).",
    "review-this-work": "Review submitted work on the targeted managed channel without mutating state (reads JSON from stdin).",
    "execute-this-plan": "Execute one approved plan on a mutate-capable managed channel (reads JSON from stdin).",
    "execute-this-plan-part": "Execute one approved plan part on a mutate-capable managed channel (reads JSON from stdin).",
    "dangerous-new-session": "Explicitly authorize discarding continuity and starting or switching a managed MAMS mams_channel session (reads JSON from stdin).",
    "configure": "Patch managed mams_channel metadata and prompt profiles (reads JSON from stdin).",
}

INVOKE_REQUESTS_FIELD = "requests"
INVOKE_COMMAND_FIELD = "command"
INVOKE_INPUT_FIELD = "input"
INVOKE_MAMS_CHANNEL_FIELD = "mams_channel"
INVOKE_ALLOWED_COMMANDS = {
    "sync",
    "review-this-plan",
    "review-this-work",
    "execute-this-plan",
    "execute-this-plan-part",
}
INVOKE_MUTATING_COMMANDS = {"execute-this-plan", "execute-this-plan-part"}


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


MANAGED_GLOBAL_DIR = (Path.home() / MANAGED_DIRNAME).resolve()


def is_global_managed_dir(directory: Path) -> bool:
    try:
        resolved = directory.resolve()
        return resolved == MANAGED_GLOBAL_DIR
    except Exception:
        return str(directory) == str(MANAGED_GLOBAL_DIR)


def iter_ancestors(start: Path) -> Iterator[Path]:
    cur = start.expanduser().resolve()
    while True:
        yield cur
        if cur.parent == cur:
            break
        cur = cur.parent


def find_session_root(start: Path) -> Optional[Path]:
    """
    Find the nearest ancestor directory that already owns a managed MAMS session
    file.

    IMPORTANT:
    - Never treat the global ~/.mad-agent-mesh directory as a project root.
    - `.mad-agent-mesh/mams_channels.json` is the only project session anchor.
    - `.mad-agent-mesh/` alone can exist at many levels for other purposes, so we do
      not auto-pick based on the directory alone.
    """
    for p in iter_ancestors(start):
        managed_dir = p / MANAGED_DIRNAME
        if is_global_managed_dir(managed_dir):
            continue
        if (managed_dir / MAMS_CHANNELS_FILENAME).is_file():
            return p
    return None


def candidate_roots_with_managed_dir(start: Path, limit: int = 5) -> list[Path]:
    candidates: list[Path] = []
    for p in iter_ancestors(start):
        managed_dir = p / MANAGED_DIRNAME
        if is_global_managed_dir(managed_dir):
            continue
        if managed_dir.is_dir():
            candidates.append(p)
            if len(candidates) >= limit:
                break
    return candidates


def mams_channels_file_path(repo_root: Path) -> Path:
    return repo_root / MANAGED_DIRNAME / MAMS_CHANNELS_FILENAME


def diagnostics_dir_path(repo_root: Path) -> Path:
    return repo_root / MANAGED_DIRNAME / DIAGNOSTICS_DIRNAME


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def diagnostic_timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def diagnostic_preview(text: str, *, max_lines: int = 8, max_chars: int = 600) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return "(empty)"
    lines = normalized.splitlines()
    preview = "\n".join(lines[:max_lines]).strip()
    if len(preview) > max_chars:
        preview = preview[: max_chars - 3].rstrip() + "..."
    if len(lines) > max_lines and len(preview) < max_chars:
        preview = preview.rstrip() + "\n..."
    return preview


@dataclass(frozen=True)
class MamsPromptProfileBlock:
    description: Optional[str]
    focus: Optional[str]
    baseline: Optional[str]
    extra_context: Optional[str]


@dataclass(frozen=True)
class MamsChannelPromptProfile:
    public: MamsPromptProfileBlock
    plan_stage: MamsPromptProfileBlock
    execution_stage: MamsPromptProfileBlock


@dataclass(frozen=True)
class MamsChannelConfig:
    name: str
    prompt_profile: MamsChannelPromptProfile
    can_mutate: bool
    runner: str
    runner_config: dict[str, object]
    session_id: Optional[str]
    model: Optional[str]
    reasoning_effort: Optional[str]
    previous_session_ids: tuple[str, ...]
    last_stage_context: Optional[str]
    stage_reminder_turn_count: int
    updated_at: str


@dataclass(frozen=True)
class MamsSkillConfig:
    version: int
    mams_channels: list[MamsChannelConfig]
    invoker_reminder_turn_count: int
    updated_at: str


def normalize_optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def merge_optional_texts(*values: Optional[str]) -> Optional[str]:
    parts = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not parts:
        return None
    return "\n\n".join(parts)


def normalize_previous_session_ids(items: object) -> tuple[str, ...]:
    if not isinstance(items, list):
        return ()
    result: list[str] = []
    for item in items:
        normalized = normalize_optional_string(item)
        if normalized and normalized not in result:
            result.append(normalized)
        if len(result) >= 2:
            break
    return tuple(result)


def normalize_string_map(value: object, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object when provided.")
    result: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = normalize_optional_string(raw_key)
        if not key:
            raise ValueError(f"{field_name} contains an empty key.")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"{field_name}.{key} must be a non-empty string.")
        result[key] = raw_value.strip()
    return result


def default_prompt_profile_block() -> MamsPromptProfileBlock:
    return MamsPromptProfileBlock(
        description=None,
        focus=None,
        baseline=None,
        extra_context=None,
    )


def normalize_prompt_profile_block(
    value: object,
    *,
    field_name: str,
) -> MamsPromptProfileBlock:
    if value is None:
        return default_prompt_profile_block()
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object when provided.")

    allowed_keys = {"description", "focus", "baseline", "extra_context"}
    unknown_keys = set(value.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(
            f"{field_name} has unsupported fields: {', '.join(sorted(unknown_keys))}."
        )

    return MamsPromptProfileBlock(
        description=normalize_optional_string(value.get("description")),
        focus=normalize_optional_string(value.get("focus")),
        baseline=normalize_optional_string(value.get("baseline")),
        extra_context=normalize_optional_string(value.get("extra_context")),
    )


def prompt_profile_block_to_json(block: MamsPromptProfileBlock) -> dict[str, object]:
    return {
        "description": block.description,
        "focus": block.focus,
        "baseline": block.baseline,
        "extra_context": block.extra_context,
    }


def default_channel_prompt_profile() -> MamsChannelPromptProfile:
    empty = default_prompt_profile_block()
    return MamsChannelPromptProfile(
        public=empty,
        plan_stage=empty,
        execution_stage=empty,
    )


def normalize_channel_prompt_profile(
    value: object,
    *,
    field_name: str,
) -> MamsChannelPromptProfile:
    if value is None:
        return default_channel_prompt_profile()
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object when provided.")

    allowed_keys = {"public", "plan_stage", "execution_stage"}
    unknown_keys = set(value.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(
            f"{field_name} has unsupported fields: {', '.join(sorted(unknown_keys))}."
        )

    return MamsChannelPromptProfile(
        public=normalize_prompt_profile_block(
            value.get("public"),
            field_name=f"{field_name}.public",
        ),
        plan_stage=normalize_prompt_profile_block(
            value.get("plan_stage"),
            field_name=f"{field_name}.plan_stage",
        ),
        execution_stage=normalize_prompt_profile_block(
            value.get("execution_stage"),
            field_name=f"{field_name}.execution_stage",
        ),
    )


def channel_prompt_profile_to_json(profile: MamsChannelPromptProfile) -> dict[str, object]:
    return {
        "public": prompt_profile_block_to_json(profile.public),
        "plan_stage": prompt_profile_block_to_json(profile.plan_stage),
        "execution_stage": prompt_profile_block_to_json(profile.execution_stage),
    }


def merge_prompt_profile_blocks(
    *blocks: MamsPromptProfileBlock,
) -> MamsPromptProfileBlock:
    return MamsPromptProfileBlock(
        description=merge_optional_texts(*(block.description for block in blocks)),
        focus=merge_optional_texts(*(block.focus for block in blocks)),
        baseline=merge_optional_texts(*(block.baseline for block in blocks)),
        extra_context=merge_optional_texts(*(block.extra_context for block in blocks)),
    )


def normalize_runner(value: object, *, field_name: str) -> str:
    runner = normalize_optional_string(value) or RUNNER_CODEX
    if runner not in SUPPORTED_RUNNERS:
        raise ValueError(
            f"{field_name} must be one of: {', '.join(sorted(SUPPORTED_RUNNERS))}."
        )
    return runner


def normalize_runner_config(value: object, *, field_name: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object when provided.")
    return dict(value)


def default_mams_channel_description(name: str) -> str:
    if name == DEFAULT_MAMS_CHANNEL_NAME:
        return DEFAULT_MAMS_CHANNEL_DESCRIPTION
    return f"Managed MAMS channel '{name}'."


def build_mams_channel_config(
    name: str,
    *,
    prompt_profile: Optional[MamsChannelPromptProfile] = None,
    can_mutate: bool = True,
    runner: str = RUNNER_CODEX,
    runner_config: Optional[dict[str, object]] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    previous_session_ids: tuple[str, ...] = (),
    last_stage_context: Optional[str] = None,
    stage_reminder_turn_count: int = 0,
) -> MamsChannelConfig:
    normalized_name = normalize_optional_string(name)
    if not normalized_name:
        raise ValueError("MAMS channel name must be a non-empty string.")
    return MamsChannelConfig(
        name=normalized_name,
        prompt_profile=prompt_profile or default_channel_prompt_profile(),
        can_mutate=bool(can_mutate),
        runner=normalize_runner(runner, field_name=f"mams_channels[{normalized_name}].runner"),
        runner_config=normalize_runner_config(runner_config, field_name=f"mams_channels[{normalized_name}].runner_config"),
        session_id=normalize_optional_string(session_id),
        model=normalize_optional_string(model),
        reasoning_effort=normalize_optional_string(reasoning_effort),
        previous_session_ids=normalize_previous_session_ids(list(previous_session_ids)),
        last_stage_context=normalize_optional_string(last_stage_context),
        stage_reminder_turn_count=max(0, int(stage_reminder_turn_count)),
        updated_at=iso_now(),
    )


def parse_mams_channel_config(obj: object) -> MamsChannelConfig:
    if not isinstance(obj, dict):
        raise ValueError("Each mams_channel entry must be a JSON object.")
    name = normalize_optional_string(obj.get("name"))
    if not name:
        raise ValueError("Each mams_channel entry requires a non-empty string field: name.")
    updated_at = normalize_optional_string(obj.get("updated_at")) or iso_now()
    raw_can_mutate = obj.get("can_mutate", True)
    if not isinstance(raw_can_mutate, bool):
        raise ValueError(f"mams_channels[{name}].can_mutate must be a boolean when provided.")
    return MamsChannelConfig(
        name=name,
        prompt_profile=normalize_channel_prompt_profile(
            obj.get("prompt_profile"),
            field_name=f"mams_channels[{name}].prompt_profile",
        ),
        can_mutate=raw_can_mutate,
        runner=normalize_runner(obj.get("runner"), field_name=f"mams_channels[{name}].runner"),
        runner_config=normalize_runner_config(obj.get("runner_config"), field_name=f"mams_channels[{name}].runner_config"),
        session_id=normalize_optional_string(obj.get("session_id")),
        model=normalize_optional_string(obj.get("model")),
        reasoning_effort=normalize_optional_string(obj.get("reasoning_effort")),
        previous_session_ids=normalize_previous_session_ids(obj.get("previous_session_ids")),
        last_stage_context=normalize_optional_string(obj.get("last_stage_context")),
        stage_reminder_turn_count=max(0, int(obj.get("stage_reminder_turn_count", 0) or 0)),
        updated_at=updated_at,
    )


def mams_channel_config_to_json(mams_channel: MamsChannelConfig) -> dict[str, object]:
    return {
        "name": mams_channel.name,
        "prompt_profile": channel_prompt_profile_to_json(mams_channel.prompt_profile),
        "can_mutate": mams_channel.can_mutate,
        "runner": mams_channel.runner,
        "runner_config": mams_channel.runner_config,
        "session_id": mams_channel.session_id,
        "model": mams_channel.model,
        "reasoning_effort": mams_channel.reasoning_effort,
        "previous_session_ids": list(mams_channel.previous_session_ids),
        "last_stage_context": mams_channel.last_stage_context,
        "stage_reminder_turn_count": mams_channel.stage_reminder_turn_count,
        "updated_at": mams_channel.updated_at,
    }


def default_mams_skill_config(mams_channels: Optional[list[MamsChannelConfig]] = None) -> MamsSkillConfig:
    return MamsSkillConfig(
        version=CONFIG_VERSION,
        mams_channels=list(mams_channels or []),
        invoker_reminder_turn_count=0,
        updated_at=iso_now(),
    )


def parse_skill_config_object(obj: object, *, path: Path) -> MamsSkillConfig:
    if not isinstance(obj, dict):
        raise RuntimeError(f"MAMS channel config file must contain a JSON object: {path}")
    mams_channels_value = obj.get("mams_channels")
    if mams_channels_value is None:
        raise RuntimeError(f"Config object must contain a 'mams_channels' array: {path}")
    if not isinstance(mams_channels_value, list):
        raise RuntimeError(f"Config field 'mams_channels' must be a JSON array: {path}")
    mams_channels: list[MamsChannelConfig] = []
    seen: set[str] = set()
    for raw in mams_channels_value:
        mams_channel = parse_mams_channel_config(raw)
        if mams_channel.name in seen:
            raise RuntimeError(f"Duplicate mams_channel name in {path}: {mams_channel.name}")
        seen.add(mams_channel.name)
        mams_channels.append(mams_channel)
    version = obj.get("version")
    if isinstance(version, int):
        normalized_version = version
    else:
        normalized_version = CONFIG_VERSION
    updated_at = normalize_optional_string(obj.get("updated_at")) or iso_now()
    return MamsSkillConfig(
        version=normalized_version,
        mams_channels=mams_channels,
        invoker_reminder_turn_count=max(0, int(obj.get("invoker_reminder_turn_count", 0) or 0)),
        updated_at=updated_at,
    )


def skill_config_to_json(config: MamsSkillConfig) -> dict[str, object]:
    return {
        "version": config.version,
        "mams_channels": [mams_channel_config_to_json(mams_channel) for mams_channel in config.mams_channels],
        "invoker_reminder_turn_count": config.invoker_reminder_turn_count,
        "updated_at": config.updated_at,
    }


def read_skill_config(repo_root: Path) -> MamsSkillConfig:
    path = mams_channels_file_path(repo_root)
    if not path.exists():
        return default_mams_skill_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid mams_channel config JSON in {path}: {exc.msg}") from exc
    return parse_skill_config_object(data, path=path)


def write_skill_config(repo_root: Path, config: MamsSkillConfig) -> None:
    path = mams_channels_file_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = skill_config_to_json(config)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def find_mams_channel(mams_channels: list[MamsChannelConfig], name: str) -> Optional[MamsChannelConfig]:
    for mams_channel in mams_channels:
        if mams_channel.name == name:
            return mams_channel
    return None


def upsert_mams_channel(
    mams_channels: list[MamsChannelConfig],
    updated_mams_channel: MamsChannelConfig,
) -> list[MamsChannelConfig]:
    next_mams_channels: list[MamsChannelConfig] = []
    replaced_existing = False
    for mams_channel in mams_channels:
        if mams_channel.name == updated_mams_channel.name:
            next_mams_channels.append(updated_mams_channel)
            replaced_existing = True
        else:
            next_mams_channels.append(mams_channel)
    if not replaced_existing:
        next_mams_channels.append(updated_mams_channel)
    return next_mams_channels


def apply_prompt_profile_block_patch(
    current: MamsPromptProfileBlock,
    patch: Optional[dict[str, object]],
) -> MamsPromptProfileBlock:
    if patch is None:
        return current
    updated = {
        "description": current.description,
        "focus": current.focus,
        "baseline": current.baseline,
        "extra_context": current.extra_context,
    }
    for field in ("description", "focus", "baseline", "extra_context"):
        if field in patch:
            value = patch[field]
            updated[field] = value if value is None else str(value).strip()
    return MamsPromptProfileBlock(
        description=updated["description"],
        focus=updated["focus"],
        baseline=updated["baseline"],
        extra_context=updated["extra_context"],
    )


def apply_channel_prompt_profile_patch(
    current: MamsChannelPromptProfile,
    patch: Optional[dict[str, object]],
) -> MamsChannelPromptProfile:
    if patch is None:
        return current
    return MamsChannelPromptProfile(
        public=apply_prompt_profile_block_patch(
            current.public,
            patch.get("public") if isinstance(patch.get("public"), dict) else None,
        ),
        plan_stage=apply_prompt_profile_block_patch(
            current.plan_stage,
            patch.get("plan_stage") if isinstance(patch.get("plan_stage"), dict) else None,
        ),
        execution_stage=apply_prompt_profile_block_patch(
            current.execution_stage,
            patch.get("execution_stage") if isinstance(patch.get("execution_stage"), dict) else None,
        ),
    )


def apply_configure_payload(
    config: MamsSkillConfig,
    payload: ConfigurePayload,
) -> MamsSkillConfig:
    mams_channels = list(config.mams_channels)
    if payload.mams_channels_patch:
        for patch in payload.mams_channels_patch:
            name = patch["name"]
            existing = find_mams_channel(mams_channels, name)
            if existing is None:
                updated_mams_channel = build_mams_channel_config(
                    name,
                    prompt_profile=apply_channel_prompt_profile_patch(
                        default_channel_prompt_profile(),
                        patch.get("prompt_profile") if isinstance(patch.get("prompt_profile"), dict) else None,
                    ),
                    can_mutate=patch.get("can_mutate", True),
                    runner=patch.get("runner", RUNNER_CODEX),
                    runner_config=patch.get("runner_config"),
                    model=patch.get("model"),
                    reasoning_effort=patch.get("reasoning_effort"),
                )
            else:
                updated_mams_channel = build_mams_channel_config(
                    name,
                    prompt_profile=apply_channel_prompt_profile_patch(
                        existing.prompt_profile,
                        patch.get("prompt_profile") if isinstance(patch.get("prompt_profile"), dict) else None,
                    ),
                    can_mutate=patch.get("can_mutate") if "can_mutate" in patch else existing.can_mutate,
                    runner=patch.get("runner") if "runner" in patch else existing.runner,
                    runner_config=patch.get("runner_config") if "runner_config" in patch else existing.runner_config,
                    session_id=existing.session_id,
                    model=patch.get("model") if "model" in patch else existing.model,
                    reasoning_effort=patch.get("reasoning_effort") if "reasoning_effort" in patch else existing.reasoning_effort,
                    previous_session_ids=existing.previous_session_ids,
                    last_stage_context=existing.last_stage_context,
                    stage_reminder_turn_count=existing.stage_reminder_turn_count,
                )
            mams_channels = upsert_mams_channel(mams_channels, updated_mams_channel)

    return MamsSkillConfig(
        version=CONFIG_VERSION,
        mams_channels=mams_channels,
        invoker_reminder_turn_count=config.invoker_reminder_turn_count,
        updated_at=iso_now(),
    )


@dataclass(frozen=True)
class ReviewThisPlanPayload:
    plan_for_review: str
    new_information: Optional[str]
    fresh_user_message: Optional[str]


@dataclass(frozen=True)
class SyncPayload:
    sync_message: str
    fresh_user_message: Optional[str]
    stage_context: str


@dataclass(frozen=True)
class ReviewThisWorkPayload:
    work_for_review: str
    new_information: Optional[str]
    fresh_user_message: Optional[str]


@dataclass(frozen=True)
class ExecutePayload:
    approved_scope: str
    fresh_user_message: Optional[str]
    sandbox_mode: str


@dataclass(frozen=True)
class DangerousNewSessionPayload:
    user_permission: str
    target_session_id: Optional[str]
    mams_channel_description: Optional[str]
    model: Optional[str]
    reasoning_effort: Optional[str]


@dataclass(frozen=True)
class ConfigurePayload:
    mams_channels_patch: Optional[list[dict[str, object]]]


@dataclass(frozen=True)
class InvokeRequest:
    command: str
    mams_channel_name: Optional[str]
    stdin_text: str


@dataclass(frozen=True)
class InvokePayload:
    requests: tuple[InvokeRequest, ...]


def parse_invoke_request_object(raw: object, *, index: int) -> InvokeRequest:
    if not isinstance(raw, dict):
        raise ValueError(f"invoke requests[{index}] must be a JSON object.")

    command = normalize_optional_string(raw.get(INVOKE_COMMAND_FIELD))
    if not command:
        raise ValueError(f"invoke requests[{index}].command must be a non-empty string.")
    if command not in INVOKE_ALLOWED_COMMANDS:
        raise ValueError(
            f"invoke requests[{index}].command must be one of: {', '.join(sorted(INVOKE_ALLOWED_COMMANDS))}."
        )

    payload = raw.get(INVOKE_INPUT_FIELD)
    if not isinstance(payload, dict):
        raise ValueError(f"invoke requests[{index}].input must be a JSON object.")

    return InvokeRequest(
        command=command,
        mams_channel_name=normalize_optional_string(raw.get(INVOKE_MAMS_CHANNEL_FIELD)),
        stdin_text=json.dumps(payload, ensure_ascii=False),
    )


def parse_invoke_payload(stdin_text: str) -> InvokePayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError(
            "invoke input is empty. Provide either a single request object or a {\"requests\": [...]} object."
        )

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invoke input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("invoke input must be a JSON object.")

    requests_raw = obj.get(INVOKE_REQUESTS_FIELD)
    if requests_raw is None:
        return InvokePayload(requests=(parse_invoke_request_object(obj, index=0),))

    if not isinstance(requests_raw, list) or not requests_raw:
        raise ValueError("invoke requests must be a non-empty JSON array.")

    requests = tuple(
        parse_invoke_request_object(item, index=index)
        for index, item in enumerate(requests_raw)
    )
    return InvokePayload(requests=requests)


def parse_review_this_plan_payload(stdin_text: str) -> ReviewThisPlanPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("review-this-plan input is empty. Provide JSON with plan_for_review.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"review-this-plan input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("review-this-plan input must be a JSON object.")

    allowed_keys = {
        REVIEW_PLAN_FIELD,
        REVIEW_PLAN_NEW_INFO_FIELD,
        REVIEW_PLAN_FRESH_USER_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"review-this-plan input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    plan_for_review = obj.get(REVIEW_PLAN_FIELD)
    if not isinstance(plan_for_review, str) or not plan_for_review.strip():
        raise ValueError("review-this-plan requires a non-empty string field: plan_for_review.")

    def parse_optional_string(field: str) -> Optional[str]:
        value = obj.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"review-this-plan field {field} must be a non-empty string when provided.")
        return value.strip()

    return ReviewThisPlanPayload(
        plan_for_review=plan_for_review.strip(),
        new_information=parse_optional_string(REVIEW_PLAN_NEW_INFO_FIELD),
        fresh_user_message=parse_optional_string(REVIEW_PLAN_FRESH_USER_FIELD),
    )


def parse_sync_payload(stdin_text: str) -> SyncPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("sync input is empty. Provide JSON with sync_message.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"sync input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("sync input must be a JSON object.")

    allowed_keys = {SYNC_MESSAGE_FIELD, SYNC_FRESH_USER_FIELD, SYNC_STAGE_CONTEXT_FIELD}
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"sync input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    sync_message = obj.get(SYNC_MESSAGE_FIELD)
    if not isinstance(sync_message, str) or not sync_message.strip():
        raise ValueError("sync requires a non-empty string field: sync_message.")

    fresh_user_message = obj.get(SYNC_FRESH_USER_FIELD)
    if fresh_user_message is not None:
        if not isinstance(fresh_user_message, str) or not fresh_user_message.strip():
            raise ValueError("sync field fresh_user_message must be a non-empty string when provided.")
        fresh_user_message = fresh_user_message.strip()

    stage_context = obj.get(SYNC_STAGE_CONTEXT_FIELD, "plan")
    if stage_context not in {"plan", "execution"}:
        raise ValueError("sync field stage_context must be exactly 'plan' or 'execution' when provided.")

    return SyncPayload(
        sync_message=sync_message.strip(),
        fresh_user_message=fresh_user_message,
        stage_context=stage_context,
    )


def parse_review_this_work_payload(stdin_text: str) -> ReviewThisWorkPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("review-this-work input is empty. Provide JSON with work_for_review.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"review-this-work input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("review-this-work input must be a JSON object.")

    allowed_keys = {
        REVIEW_WORK_FIELD,
        REVIEW_WORK_NEW_INFO_FIELD,
        REVIEW_WORK_FRESH_USER_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"review-this-work input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    work_for_review = obj.get(REVIEW_WORK_FIELD)
    if not isinstance(work_for_review, str) or not work_for_review.strip():
        raise ValueError("review-this-work requires a non-empty string field: work_for_review.")

    def parse_optional_string(field: str) -> Optional[str]:
        value = obj.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"review-this-work field {field} must be a non-empty string when provided.")
        return value.strip()

    return ReviewThisWorkPayload(
        work_for_review=work_for_review.strip(),
        new_information=parse_optional_string(REVIEW_WORK_NEW_INFO_FIELD),
        fresh_user_message=parse_optional_string(REVIEW_WORK_FRESH_USER_FIELD),
    )


def parse_execute_payload(stdin_text: str, *, mode: str) -> ExecutePayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError(f"{mode} input is empty. Provide JSON with the approved plan scope.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{mode} input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError(f"{mode} input must be a JSON object.")

    approved_field = EXECUTE_PLAN_FIELD if mode == "execute-this-plan" else EXECUTE_PLAN_PART_FIELD

    allowed_keys = {
        approved_field,
        EXECUTE_FRESH_USER_FIELD,
        EXECUTE_SANDBOX_MODE_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"{mode} input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    approved_scope = obj.get(approved_field)
    if not isinstance(approved_scope, str) or not approved_scope.strip():
        raise ValueError(f"{mode} requires a non-empty string field: {approved_field}.")

    fresh_user_message = obj.get(EXECUTE_FRESH_USER_FIELD)
    if fresh_user_message is not None:
        if not isinstance(fresh_user_message, str) or not fresh_user_message.strip():
            raise ValueError(f"{mode} field fresh_user_message must be a non-empty string when provided.")
        fresh_user_message = fresh_user_message.strip()

    sandbox_mode = obj.get(EXECUTE_SANDBOX_MODE_FIELD, EXECUTE_SANDBOX_DEFAULT)
    if sandbox_mode not in {EXECUTE_SANDBOX_DEFAULT, EXECUTE_SANDBOX_FULL_ACCESS}:
        raise ValueError(f"{mode} field sandbox_mode must be exactly 'default' or 'full-access' when provided.")

    return ExecutePayload(
        approved_scope=approved_scope.strip(),
        fresh_user_message=fresh_user_message,
        sandbox_mode=sandbox_mode,
    )


def parse_dangerous_new_session_payload(stdin_text: str) -> DangerousNewSessionPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError(
            "dangerous-new-session input is empty. Provide JSON with a non-empty user_permission string."
        )

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"dangerous-new-session input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("dangerous-new-session input must be a JSON object.")

    allowed_keys = {
        DANGEROUS_NEW_SESSION_PERMISSION_FIELD,
        DANGEROUS_NEW_SESSION_TARGET_FIELD,
        DANGEROUS_NEW_SESSION_MAMS_CHANNEL_DESCRIPTION_FIELD,
        DANGEROUS_NEW_SESSION_MODEL_FIELD,
        DANGEROUS_NEW_SESSION_REASONING_EFFORT_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(
            "dangerous-new-session input has unsupported fields: "
            + ", ".join(sorted(unknown_keys))
        )

    user_permission = obj.get(DANGEROUS_NEW_SESSION_PERMISSION_FIELD)
    if not isinstance(user_permission, str) or not user_permission.strip():
        raise ValueError(
            "dangerous-new-session requires a non-empty string field: user_permission."
        )

    target_session_id = obj.get(DANGEROUS_NEW_SESSION_TARGET_FIELD)
    if target_session_id is not None:
        if not isinstance(target_session_id, str) or not target_session_id.strip():
            raise ValueError(
                "dangerous-new-session field target_session_id must be a non-empty string when provided."
            )
        target_session_id = target_session_id.strip()

    def parse_optional_config_string(field: str) -> Optional[str]:
        value = obj.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"dangerous-new-session field {field} must be a non-empty string when provided."
            )
        return value.strip()

    return DangerousNewSessionPayload(
        user_permission=user_permission.strip(),
        target_session_id=target_session_id,
        mams_channel_description=parse_optional_config_string(
            DANGEROUS_NEW_SESSION_MAMS_CHANNEL_DESCRIPTION_FIELD
        ),
        model=parse_optional_config_string(DANGEROUS_NEW_SESSION_MODEL_FIELD),
        reasoning_effort=parse_optional_config_string(DANGEROUS_NEW_SESSION_REASONING_EFFORT_FIELD),
    )

def parse_nullable_prompt_profile_block_patch(
    value: object,
    *,
    field_name: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    allowed_keys = {"description", "focus", "baseline", "extra_context"}
    unknown_keys = set(value.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(
            f"{field_name} has unsupported fields: {', '.join(sorted(unknown_keys))}."
        )
    result: dict[str, object] = {}
    for field in allowed_keys:
        if field not in value:
            continue
        raw = value[field]
        if raw is None:
            result[field] = None
            continue
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                f"{field_name}.{field} must be a non-empty string or null."
            )
        result[field] = raw.strip()
    return result


def parse_nullable_prompt_profile_patch(
    value: object,
    *,
    field_name: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    allowed_keys = {"public", "plan_stage", "execution_stage"}
    unknown_keys = set(value.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(
            f"{field_name} has unsupported fields: {', '.join(sorted(unknown_keys))}."
        )

    result: dict[str, object] = {}
    for field in ("public", "plan_stage", "execution_stage"):
        if field not in value:
            continue
        raw_block = value[field]
        if raw_block is None:
            raise ValueError(f"{field_name}.{field} must be a JSON object when provided.")
        result[field] = parse_nullable_prompt_profile_block_patch(
            raw_block,
            field_name=f"{field_name}.{field}",
        )

    return result


def parse_configure_payload(stdin_text: str) -> ConfigurePayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError(
            "configure input is empty. Provide JSON with mams_channels."
        )
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"configure input must be valid JSON: {exc.msg}") from exc
    if not isinstance(obj, dict):
        raise ValueError("configure input must be a JSON object.")

    allowed_keys = {
        CONFIGURE_MAMS_CHANNELS_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"configure input has unsupported fields: {', '.join(sorted(unknown_keys))}")
    if not obj:
        raise ValueError("configure input must contain: mams_channels.")

    mams_channels_patch_value = obj.get(CONFIGURE_MAMS_CHANNELS_FIELD)
    mams_channels_patch: Optional[list[dict[str, object]]] = None
    if mams_channels_patch_value is not None:
        if not isinstance(mams_channels_patch_value, list):
            raise ValueError("configure field mams_channels must be a JSON array.")
        mams_channels_patch = []
        for index, raw_mams_channel in enumerate(mams_channels_patch_value):
            if not isinstance(raw_mams_channel, dict):
                raise ValueError(f"configure.mams_channels[{index}] must be a JSON object.")
            allowed_mams_channel_keys = {
                "name",
                "prompt_profile",
                "can_mutate",
                "runner",
                "runner_config",
                "model",
                "reasoning_effort",
            }
            unknown_mams_channel_keys = set(raw_mams_channel.keys()) - allowed_mams_channel_keys
            if unknown_mams_channel_keys:
                raise ValueError(
                    f"configure.mams_channels[{index}] has unsupported fields: {', '.join(sorted(unknown_mams_channel_keys))}"
                )
            name = normalize_optional_string(raw_mams_channel.get("name"))
            if not name:
                raise ValueError(f"configure.mams_channels[{index}] requires a non-empty string field: name.")
            normalized_mams_channel = dict(raw_mams_channel)
            normalized_mams_channel["name"] = name
            for field in ("model", "reasoning_effort", "runner"):
                if field in normalized_mams_channel:
                    value = normalized_mams_channel[field]
                    if value is not None and (not isinstance(value, str) or not value.strip()):
                        raise ValueError(
                            f"configure.mams_channels[{index}].{field} must be a non-empty string or null."
                        )
                    if isinstance(value, str):
                        normalized_mams_channel[field] = value.strip()
            if "runner" in normalized_mams_channel:
                normalized_mams_channel["runner"] = normalize_runner(
                    normalized_mams_channel["runner"],
                    field_name=f"configure.mams_channels[{index}].runner",
                )
            if "runner_config" in normalized_mams_channel:
                normalized_mams_channel["runner_config"] = normalize_runner_config(
                    normalized_mams_channel["runner_config"],
                    field_name=f"configure.mams_channels[{index}].runner_config",
                )
            if "prompt_profile" in normalized_mams_channel:
                normalized_mams_channel["prompt_profile"] = parse_nullable_prompt_profile_patch(
                    normalized_mams_channel["prompt_profile"],
                    field_name=f"configure.mams_channels[{index}].prompt_profile",
                )
            if "can_mutate" in normalized_mams_channel and not isinstance(normalized_mams_channel["can_mutate"], bool):
                raise ValueError(f"configure.mams_channels[{index}].can_mutate must be a boolean when provided.")
            mams_channels_patch.append(normalized_mams_channel)

    return ConfigurePayload(
        mams_channels_patch=mams_channels_patch,
    )


def load_prompt_asset(name: str) -> str:
    path = PROMPTS_DIR / name
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing prompt asset: {path}") from exc
    if not text:
        raise RuntimeError(f"Prompt asset is empty: {path}")
    return text


def normalize_ref_path(repo_root: Path, rel_path: str) -> Path:
    candidate = (repo_root / rel_path).resolve()
    root = repo_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"Reference path escapes the workspace root: {rel_path}") from exc
    return candidate


def collect_prompt_references(repo_root: Path, texts: list[str]) -> list[tuple[str, Optional[str]]]:
    seen: set[tuple[str, Optional[str]]] = set()
    ordered: list[tuple[str, Optional[str]]] = []
    for text in texts:
        for match in REF_PATTERN.finditer(text):
            rel_path = match.group("path").strip()
            locator = match.group("locator")
            locator = locator.strip() if locator else None
            ref = (rel_path, locator)
            if ref in seen:
                continue
            path = normalize_ref_path(repo_root, rel_path)
            if not path.exists():
                raise RuntimeError(f"Referenced file does not exist: {rel_path}")
            seen.add(ref)
            ordered.append(ref)
    return ordered


def build_reference_notice(repo_root: Path, texts: list[str]) -> list[str]:
    references = collect_prompt_references(repo_root, texts)
    if not references:
        return []
    lines = [
        "## Reference Handling Notice",
        "This prompt contains structured file references in the form `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]`.",
        "These references point to previously read or externally stored materials; they are not full inline content.",
        "If you cannot confidently identify the referenced source and its relevant content, you must re-read the referenced material before relying on it.",
        "Do not pretend a reference is understood if the source, location, or content is no longer clear.",
        "",
        "## Referenced Materials In This Call",
    ]
    for rel_path, locator in references:
        token = f"[[REF:{rel_path}]]" if locator is None else f"[[REF:{rel_path}::{locator}]]"
        lines.append(f"- {token}")
    return [wrap_tagged_block("REFERENCE_NOTICE", "\n".join(lines))]


def render_named_items(items: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"### {title}\n\n{body}" for title, body in items).strip()


def wrap_tagged_block(tag_name: str, body: str) -> str:
    normalized = body.strip()
    return f"<<<{tag_name}.BEGIN>>>\n{normalized}\n<<<{tag_name}.END>>>"


def build_labeled_content_block(tag_name: str, label: str, content: str) -> str:
    return wrap_tagged_block(tag_name, f"{label}\n{content.strip()}")


def build_mams_channel_user_items(
    mams_channel: MamsChannelConfig,
    *,
    stage_context: Optional[str],
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    profile = mams_channel.prompt_profile
    blocks = [profile.public]
    if stage_context == "plan":
        blocks.append(profile.plan_stage)
    elif stage_context == "execution":
        blocks.append(profile.execution_stage)
    merged_profile = merge_prompt_profile_blocks(*blocks)

    if merged_profile.description:
        items.append(("Configured Channel Description", merged_profile.description))
    if merged_profile.focus:
        items.append(("Configured Channel Focus", merged_profile.focus))
    if merged_profile.baseline:
        items.append(("Configured Channel Baseline", merged_profile.baseline))
    if merged_profile.extra_context:
        items.append(("Configured Channel Extra Context", merged_profile.extra_context))
    items.append(
        (
            "Configured Channel Mutation Permission",
            (
                "This mams_channel may mutate when the workflow explicitly reaches the mutation entrypoint."
                if mams_channel.can_mutate
                else "This mams_channel must not mutate files. It may discuss, review, or plan, but implementation must be routed elsewhere."
            ),
        )
    )

    return items


def is_stage_oriented_context(stage_context: Optional[str]) -> bool:
    return stage_context in {"plan", "execution"}


def should_use_full_stage_reminder(
    mams_channel: MamsChannelConfig,
    *,
    stage_context: Optional[str],
) -> bool:
    if not is_stage_oriented_context(stage_context):
        return True
    if mams_channel.last_stage_context != stage_context:
        return True
    next_turn_index = mams_channel.stage_reminder_turn_count + 1
    return (next_turn_index - 1) % 3 == 0


def advance_stage_reminder_state(
    mams_channel: MamsChannelConfig,
    *,
    stage_context: Optional[str],
) -> MamsChannelConfig:
    if not is_stage_oriented_context(stage_context):
        return mams_channel
    if mams_channel.last_stage_context != stage_context:
        next_count = 1
    else:
        next_count = mams_channel.stage_reminder_turn_count + 1
    return replace(
        mams_channel,
        last_stage_context=stage_context,
        stage_reminder_turn_count=next_count,
    )


def compose_prompt(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    *,
    base_parts: list[str],
    stage_context: Optional[str] = None,
) -> str:
    if not base_parts:
        raise RuntimeError("compose_prompt requires at least one base part.")
    agent_items = build_mams_channel_user_items(
        mams_channel,
        stage_context=stage_context,
    )
    full_stage_reminder = should_use_full_stage_reminder(
        mams_channel,
        stage_context=stage_context,
    )
    workflow_block = wrap_tagged_block(
        "MAMS_WORKFLOW_PROMPT",
        base_parts[0].strip(),
    )

    reminder_blocks: list[str] = [workflow_block]
    if agent_items:
        if full_stage_reminder:
            reminder_blocks.append(
                wrap_tagged_block(
                    "CHANNEL_STAGE_REMINDER_FULL",
                    "## Configured Channel Reminder\n\n{}".format(render_named_items(agent_items)),
                )
            )
        elif is_stage_oriented_context(stage_context):
            reminder_blocks.append(
                wrap_tagged_block(
                    "CHANNEL_STAGE_REMINDER_BRIEF",
                    (
                        "## Configured Channel Reminder (Brief)\n\n"
                        f"The configured {stage_context} stage reminder for this channel still applies in full."
                    ),
                )
            )

    ref_notice_sections = build_reference_notice(repo_root, [*reminder_blocks, *base_parts[1:]])
    prompt_parts = [*reminder_blocks, *ref_notice_sections]
    prompt_parts.extend(base_parts[1:])
    return "\n\n".join(part for part in prompt_parts if part).strip() + "\n"


def should_use_full_invoker_reminder(config: MamsSkillConfig) -> bool:
    return config.invoker_reminder_turn_count % 3 == 0


def advance_invoker_reminder_state(config: MamsSkillConfig) -> MamsSkillConfig:
    return replace(
        config,
        invoker_reminder_turn_count=config.invoker_reminder_turn_count + 1,
        updated_at=iso_now(),
    )


def build_invoker_skill_usage_block(config: MamsSkillConfig) -> str:
    if should_use_full_invoker_reminder(config):
        return wrap_tagged_block(
            "INVOKER_SKILL_USAGE_FULL",
            "\n".join(
                [
                    "## Invoker Skill Usage",
                    "",
                    "- You are acting only as the workflow caller and user-facing messenger for this skill.",
                    "- Do not modify code directly.",
                    "- Do not provide your own business, planning, review, or implementation judgment.",
                    "- Route all actual work through this workflow skill and its wrapper commands.",
                    "- Surface workflow and governor messages to the user, then relay the user's reply back through the workflow.",
                    "- If this Codex thread has been compacted, or you are unsure of the operating pattern, re-read SKILL.md before continuing.",
                ]
            ),
        )
    return wrap_tagged_block(
        "INVOKER_SKILL_USAGE_BRIEF",
        "\n".join(
            [
                "## Invoker Skill Usage (Brief)",
                "",
                "The guidance in INVOKER_SKILL_USAGE_FULL still applies in full.",
                "You are still only the workflow caller and user-facing messenger for this skill.",
                "Do not modify code directly; route all actual work through the workflow commands.",
                "If the thread was compacted or the operating pattern is unclear, re-read SKILL.md before continuing.",
            ]
        ),
    )


def format_wrapper_output(
    *,
    reply: str,
    user_escalation_request: Optional[UserEscalationRequest],
    governor_review_reply: Optional[str],
    invoker_reminder_block: Optional[str] = None,
) -> str:
    normalized_reply = reply.rstrip()
    parts = [
        invoker_reminder_block or "",
        (
            wrap_tagged_block(
                "GOVERNOR_REVIEW",
                governor_review_reply,
            )
            if governor_review_reply is not None
            else ""
        ),
        (
            wrap_tagged_block(
                "USER_ESCALATION_REQUEST",
                render_user_escalation_request_markdown(user_escalation_request),
            )
            if user_escalation_request is not None
            else ""
        ),
        wrap_tagged_block("CHANNEL_REPLY", f"## Channel Reply\n\n{normalized_reply}"),
    ]
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def format_invoker_facing_output(
    repo_root: Path,
    config: MamsSkillConfig,
    *,
    reply: str,
    user_escalation_request: Optional[UserEscalationRequest],
    governor_review_reply: Optional[str],
) -> str:
    invoker_reminder_block = build_invoker_skill_usage_block(config)
    write_skill_config(repo_root, advance_invoker_reminder_state(config))
    return format_wrapper_output(
        reply=reply,
        user_escalation_request=user_escalation_request,
        governor_review_reply=governor_review_reply,
        invoker_reminder_block=invoker_reminder_block,
    )


def format_invoke_summary(
    results: list[InvokeSettledResult],
    *,
    execution_mode: str,
) -> str:
    completed = sum(1 for item in results if item.status == "ok")
    failed = len(results) - completed
    summary_body = [
        "## Invoke Summary",
        "",
        f"- Requests: {len(results)}",
        f"- Succeeded: {completed}",
        f"- Failed: {failed}",
        f"- Execution mode: {execution_mode}",
    ]
    result_blocks: list[str] = []
    for item in results:
        governor_block = ""
        if item.governor_review_reply is not None:
            governor_block = wrap_tagged_block(
                "GOVERNOR_REVIEW",
                item.governor_review_reply,
            )
        escalation_block = ""
        if item.user_escalation_request is not None:
            escalation_block = wrap_tagged_block(
                "USER_ESCALATION_REQUEST",
                render_user_escalation_request_markdown(item.user_escalation_request),
            )
        result_body = "\n".join(
            [
                f"## {item.request.mams_channel_name or DEFAULT_MAMS_CHANNEL_NAME} · {item.request.command} · {item.status}",
                "",
                item.reply if item.status == "ok" and item.reply is not None else f"Error: {item.error}",
                governor_block,
                escalation_block,
            ]
        ).strip()
        result_blocks.append(wrap_tagged_block("INVOKE_RESULT", result_body))
    return wrap_tagged_block(
        "INVOKE_SUMMARY",
        "\n\n".join(["\n".join(summary_body).strip(), *result_blocks]).strip(),
    )


def build_review_this_plan_prompt(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
) -> str:
    payload = parse_review_this_plan_payload(stdin_text)
    parts = [
        load_prompt_asset("review-this-plan.md"),
        build_labeled_content_block("PLAN_FOR_REVIEW", "Submitted plan for review:", payload.plan_for_review),
    ]

    if payload.new_information:
        parts.extend(
            [
                build_labeled_content_block("NEW_INFORMATION", "Additional information:", payload.new_information),
            ]
        )

    if payload.fresh_user_message:
        parts.extend(
            [
                wrap_tagged_block(USER_MESSAGE_VERBATIM_TAG, payload.fresh_user_message),
            ]
        )

    return compose_prompt(
        repo_root,
        mams_channel,
        base_parts=parts,
        stage_context="plan",
    )


def build_sync_prompt(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
) -> str:
    payload = parse_sync_payload(stdin_text)
    parts = [
        load_prompt_asset("sync.md"),
        build_labeled_content_block("SYNC_MESSAGE", "Workflow discussion context:", payload.sync_message),
    ]

    if payload.fresh_user_message:
        parts.extend(
            [
                wrap_tagged_block(USER_MESSAGE_VERBATIM_TAG, payload.fresh_user_message),
            ]
        )

    return compose_prompt(
        repo_root,
        mams_channel,
        base_parts=parts,
        stage_context=payload.stage_context,
    )


def build_review_this_work_prompt(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
) -> str:
    payload = parse_review_this_work_payload(stdin_text)
    parts = [
        load_prompt_asset("review-this-work.md"),
        build_labeled_content_block("WORK_FOR_REVIEW", "Submitted work for review:", payload.work_for_review),
    ]

    if payload.new_information:
        parts.extend(
            [
                build_labeled_content_block("NEW_INFORMATION", "Additional information:", payload.new_information),
            ]
        )

    if payload.fresh_user_message:
        parts.extend(
            [
                wrap_tagged_block(USER_MESSAGE_VERBATIM_TAG, payload.fresh_user_message),
            ]
        )

    return compose_prompt(
        repo_root,
        mams_channel,
        base_parts=parts,
        stage_context="execution",
    )


def build_execute_prompt(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
    mode: str,
) -> str:
    payload = parse_execute_payload(stdin_text, mode=mode)
    parts = [
        load_prompt_asset("execute-this-plan.md" if mode == "execute-this-plan" else "execute-this-plan-part.md"),
        build_labeled_content_block(
            "EXECUTION_SANDBOX",
            "Execution sandbox for this turn:",
            (
                "workspace-write (default mutation sandbox)."
                if payload.sandbox_mode == EXECUTE_SANDBOX_DEFAULT
                else "danger-full-access (explicit full-access escalation approved by the workflow caller)."
            ),
        ),
        build_labeled_content_block(
            "APPROVED_PLAN" if mode == "execute-this-plan" else "APPROVED_PLAN_PART",
            (
                "Approved plan:"
                if mode == "execute-this-plan"
                else "Approved plan part:"
            ),
            payload.approved_scope,
        ),
    ]

    if payload.fresh_user_message:
        parts.extend(
            [
                wrap_tagged_block(USER_MESSAGE_VERBATIM_TAG, payload.fresh_user_message),
            ]
        )

    return compose_prompt(
        repo_root,
        mams_channel,
        base_parts=parts,
        stage_context="execution",
    )


def build_governor_escalation_review_prompt(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    *,
    origin_mams_channel: MamsChannelConfig,
    origin_command: str,
    origin_reply: str,
    user_escalation_request: UserEscalationRequest,
) -> str:
    parts = [
        load_prompt_asset("governor-user-escalation.md"),
        build_labeled_content_block(
            "ORIGIN_CHANNEL",
            "Originating managed channel:",
            f"{origin_mams_channel.name} ({origin_mams_channel.runner})",
        ),
        build_labeled_content_block(
            "ORIGIN_COMMAND",
            "Originating command:",
            origin_command,
        ),
        build_labeled_content_block(
            "ORIGIN_REPLY",
            "Structured reply from the originating managed channel:",
            origin_reply,
        ),
        wrap_tagged_block(
            "USER_ESCALATION_REQUEST",
            render_user_escalation_request_markdown(user_escalation_request),
        ),
    ]
    return compose_prompt(
        repo_root,
        mams_channel,
        base_parts=parts,
        stage_context=None,
    )


def command_stage_context(command: str, stdin_text: str) -> Optional[str]:
    if command == "sync":
        return parse_sync_payload(stdin_text).stage_context
    if command == "review-this-plan":
        return "plan"
    if command in {"review-this-work", "execute-this-plan", "execute-this-plan-part"}:
        return "execution"
    return None


def resolve_execution_sandbox(cmd: str, stdin_text: str) -> str:
    if cmd in {"execute-this-plan", "execute-this-plan-part"}:
        payload = parse_execute_payload(stdin_text, mode=cmd)
        if payload.sandbox_mode == EXECUTE_SANDBOX_FULL_ACCESS:
            return SANDBOX_DANGER_FULL_ACCESS
        return SANDBOX_WORKSPACE_WRITE
    return SANDBOX_READ_ONLY


def normalize_reply_text(reply: str) -> str:
    normalized = reply.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("Channel reply is empty.")
    return normalized


def parse_required_boolean_line(reply: str, key: str) -> bool:
    normalized = normalize_reply_text(reply)
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.fullmatch(rf"{re.escape(key)}\s*:\s*(true|false)", stripped, flags=re.IGNORECASE)
        if not match:
            raise ValueError(f"{key} must be the first non-empty line and must be exactly '{key}: true' or '{key}: false'.")
        return match.group(1).lower() == "true"
    raise ValueError(f"{key} must be the first non-empty line and must be exactly '{key}: true' or '{key}: false'.")


def find_markdown_heading(normalized_reply: str, title: str, start: int = 0) -> Optional[re.Match[str]]:
    pattern = re.compile(rf"(?im)^#{{1,6}}\s+{re.escape(title)}\s*$")
    return pattern.search(normalized_reply, pos=start)


def require_markdown_section(reply: str, title: str, stop_titles: Optional[list[str]] = None) -> str:
    normalized = normalize_reply_text(reply)
    heading = find_markdown_heading(normalized, title)
    if heading is None:
        raise ValueError(f"Reply must contain a markdown heading: ## {title}")

    content_start = heading.end()
    content_end = len(normalized)
    if stop_titles:
        stop_positions: list[int] = []
        for stop_title in stop_titles:
            stop_heading = find_markdown_heading(normalized, stop_title, start=content_start)
            if stop_heading is not None:
                stop_positions.append(stop_heading.start())
        if stop_positions:
            content_end = min(stop_positions)

    section_body = normalized[content_start:content_end].strip()
    if not section_body:
        raise ValueError(f"Section ## {title} must contain non-empty content.")

    return normalized


def validate_review_this_plan_reply(reply: str) -> str:
    parse_required_boolean_line(reply, REVIEW_PLAN_APPROVED_FIELD)
    return require_markdown_section(reply, REVIEW_PLAN_REPLY_TITLE)


def validate_review_this_work_reply(reply: str) -> str:
    parse_required_boolean_line(reply, REVIEW_WORK_APPROVED_FIELD)
    return require_markdown_section(reply, REVIEW_WORK_REPLY_TITLE)


def validate_sync_reply(reply: str) -> str:
    normalized = require_markdown_section(reply, SYNC_REPLY_TITLE, stop_titles=[SYNC_PLAN_TITLE])
    plan_heading = find_markdown_heading(normalized, SYNC_PLAN_TITLE)
    if plan_heading is not None:
        require_markdown_section(normalized, SYNC_PLAN_TITLE)
    return normalized


def validate_governor_escalation_review_reply(reply: str) -> GovernorEscalationReview:
    escalate_to_user = parse_required_boolean_line(reply, GOVERNOR_ESCALATE_FIELD)
    normalized = require_markdown_section(reply, GOVERNOR_REVIEW_REPLY_TITLE)
    return GovernorEscalationReview(
        escalate_to_user=escalate_to_user,
        review_reply=normalized,
    )


def parse_optional_user_escalation_request(reply: str) -> Optional[UserEscalationRequest]:
    normalized = normalize_reply_text(reply)
    heading = find_markdown_heading(normalized, USER_ESCALATION_REQUEST_TITLE)
    if heading is None:
        return None

    content_start = heading.end()
    next_heading = re.compile(r"(?im)^#{1,6}\s+.+$").search(normalized, pos=content_start)
    content_end = next_heading.start() if next_heading is not None else len(normalized)
    body = normalized[content_start:content_end].strip()
    if not body:
        raise ValueError(f"Section ## {USER_ESCALATION_REQUEST_TITLE} must contain non-empty content.")

    parsed: dict[str, str] = {}
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ":" not in stripped:
            raise ValueError(
                f"Section ## {USER_ESCALATION_REQUEST_TITLE} must use key: value lines."
            )
        key, value = stripped.split(":", 1)
        normalized_key = key.strip().lower().replace(" ", "_")
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError(
                f"Section ## {USER_ESCALATION_REQUEST_TITLE} field '{normalized_key}' must be non-empty."
            )
        parsed[normalized_key] = normalized_value

    raw_blocking = parsed.get("blocking")
    question = parsed.get("question")
    reason = parsed.get("reason")
    can_continue_without_answer = parsed.get("can_continue_without_answer")

    if raw_blocking is None or question is None or reason is None:
        raise ValueError(
            f"Section ## {USER_ESCALATION_REQUEST_TITLE} must include blocking, question, and reason."
        )
    lowered_blocking = raw_blocking.lower()
    if lowered_blocking not in {"true", "false"}:
        raise ValueError(
            f"Section ## {USER_ESCALATION_REQUEST_TITLE} field 'blocking' must be true or false."
        )

    return UserEscalationRequest(
        blocking=lowered_blocking == "true",
        question=question,
        reason=reason,
        can_continue_without_answer=can_continue_without_answer,
    )


def build_prompt(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    tool: str,
    stdin_text: str,
) -> str:
    if tool == "sync":
        return build_sync_prompt(repo_root, mams_channel, stdin_text)
    if tool == "review-this-plan":
        return build_review_this_plan_prompt(
            repo_root,
            mams_channel,
            stdin_text,
        )
    if tool == "review-this-work":
        return build_review_this_work_prompt(
            repo_root,
            mams_channel,
            stdin_text,
        )
    if tool in {"execute-this-plan", "execute-this-plan-part"}:
        return build_execute_prompt(
            repo_root,
            mams_channel,
            stdin_text,
            mode=tool,
        )
    if tool == GOVERNOR_ESCALATION_REVIEW_TOOL:
        raise ValueError(
            f"{GOVERNOR_ESCALATION_REVIEW_TOOL} is an internal workflow prompt and must be built explicitly."
        )
    raise ValueError(f"Unsupported tool: {tool}")


def safe_json_loads(line: str) -> Optional[dict]:
    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def detect_thread_id(event: dict) -> Optional[str]:
    thread_id = event.get("thread_id")
    if isinstance(thread_id, str) and thread_id:
        return thread_id

    if event.get("type") == "session_meta":
        payload = event.get("payload")
        if isinstance(payload, dict):
            sid = payload.get("id")
            if isinstance(sid, str) and sid:
                return sid

    if event.get("type") == "thread.started":
        tid = event.get("thread_id")
        if isinstance(tid, str) and tid:
            return tid

    return None


@dataclass
class RunnerRunResult:
    session_id: str
    reply: str


@dataclass(frozen=True)
class UserEscalationRequest:
    blocking: bool
    question: str
    reason: str
    can_continue_without_answer: Optional[str]


@dataclass(frozen=True)
class GovernorEscalationReview:
    escalate_to_user: bool
    review_reply: str


@dataclass(frozen=True)
class ValidatedCommandReply:
    normalized_reply: str
    user_escalation_request: Optional[UserEscalationRequest]


@dataclass(frozen=True)
class InvokeSettledResult:
    request: InvokeRequest
    status: str
    reply: Optional[str]
    user_escalation_request: Optional[UserEscalationRequest]
    governor_review_reply: Optional[str]
    error: Optional[str]
    updated_mams_channel: Optional[MamsChannelConfig]


def validate_command_reply(command: str, reply: str) -> ValidatedCommandReply:
    if command == "review-this-plan":
        normalized = validate_review_this_plan_reply(reply)
        return ValidatedCommandReply(
            normalized_reply=normalized,
            user_escalation_request=parse_optional_user_escalation_request(normalized),
        )
    if command == "review-this-work":
        normalized = validate_review_this_work_reply(reply)
        return ValidatedCommandReply(
            normalized_reply=normalized,
            user_escalation_request=parse_optional_user_escalation_request(normalized),
        )
    if command == "sync":
        normalized = validate_sync_reply(reply)
        return ValidatedCommandReply(
            normalized_reply=normalized,
            user_escalation_request=parse_optional_user_escalation_request(normalized),
        )
    if command in {"execute-this-plan", "execute-this-plan-part"}:
        normalized = require_markdown_section(reply, EXECUTE_WORK_REPORT_TITLE)
        return ValidatedCommandReply(
            normalized_reply=normalized,
            user_escalation_request=parse_optional_user_escalation_request(normalized),
        )
    if command == GOVERNOR_ESCALATION_REVIEW_TOOL:
        review = validate_governor_escalation_review_reply(reply)
        return ValidatedCommandReply(
            normalized_reply=review.review_reply,
            user_escalation_request=None,
        )
    normalized = reply.rstrip()
    return ValidatedCommandReply(
        normalized_reply=normalized,
        user_escalation_request=parse_optional_user_escalation_request(normalized),
    )


def build_protocol_notice(command: str, validation_error: str) -> str:
    lines = [
        "Your previous turn ended without a valid structured result for this workflow command.",
        f"Validation error: {validation_error}",
        "Continue from the current managed session state. Do not restart the task from scratch.",
    ]
    if command == "sync":
        lines.append(
            "You must return a valid `## Discussion Reply`, and include `## Plan` only when a real candidate plan is ready."
        )
    elif command == "review-this-plan":
        lines.append(
            "You must return `approved_to_mutate: true|false` as the first non-empty line, followed by `## Plan Review Reply`."
        )
    elif command == "review-this-work":
        lines.append(
            "You must return `approved_work: true|false` as the first non-empty line, followed by `## Work Review Reply`."
        )
    elif command in {"execute-this-plan", "execute-this-plan-part"}:
        lines.append(
            "You must either continue the approved execution scope or stop only with a valid `## Work Report`."
        )
    lines.extend(
        [
            "Do not ask the end user directly.",
            "If you genuinely need a user decision, include a structured `## User Escalation Request` section alongside an otherwise valid result.",
            "Do not end this turn with unstructured summary text.",
        ]
    )
    return "\n".join(lines)


def append_protocol_notice(prompt: str, notice: str) -> str:
    return prompt.rstrip() + "\n\n" + wrap_tagged_block("WORKFLOW_PROTOCOL_NOTICE", notice) + "\n"


def render_user_escalation_request_markdown(
    request: UserEscalationRequest,
) -> str:
    lines = [
        f"blocking: {'true' if request.blocking else 'false'}",
        f"question: {request.question}",
        f"reason: {request.reason}",
    ]
    if request.can_continue_without_answer:
        lines.append(f"can_continue_without_answer: {request.can_continue_without_answer}")
    return "## User Escalation Request\n\n" + "\n".join(lines)


def maybe_review_user_escalation_with_governor(
    repo_root: Path,
    config: MamsSkillConfig,
    *,
    origin_mams_channel: MamsChannelConfig,
    origin_command: str,
    origin_reply: str,
    user_escalation_request: Optional[UserEscalationRequest],
    timeout_s: int,
    model: Optional[str],
    reasoning_effort: Optional[str],
) -> tuple[Optional[UserEscalationRequest], Optional[str], Optional[MamsChannelConfig]]:
    if user_escalation_request is None:
        return None, None, None

    governor = find_mams_channel(config.mams_channels, GOVERNOR_CHANNEL_NAME)
    if governor is None or governor.name == origin_mams_channel.name:
        return user_escalation_request, None, None

    prompt = build_governor_escalation_review_prompt(
        repo_root,
        governor,
        origin_mams_channel=origin_mams_channel,
        origin_command=origin_command,
        origin_reply=origin_reply,
        user_escalation_request=user_escalation_request,
    )
    result = run_runner_for_mams_channel(
        repo_root=repo_root,
        mams_channel=governor,
        session_id=governor.session_id,
        prompt=prompt,
        sandbox_mode=SANDBOX_READ_ONLY,
        timeout_s=timeout_s,
        model=model or governor.model or DEFAULT_MODEL,
        reasoning_effort=reasoning_effort or governor.reasoning_effort or DEFAULT_REASONING_EFFORT,
    )
    review = validate_governor_escalation_review_reply(result.reply)
    updated_governor = replace(
        governor,
        session_id=result.session_id,
        model=governor.model or model,
        reasoning_effort=governor.reasoning_effort or reasoning_effort,
        updated_at=iso_now(),
    )
    approved_request = user_escalation_request if review.escalate_to_user else None
    return approved_request, review.review_reply, updated_governor


def write_invalid_reply_diagnostic(
    repo_root: Path,
    *,
    mams_channel: MamsChannelConfig,
    command: str,
    session_id: Optional[str],
    validation_error: str,
    raw_replies: list[tuple[str, str]],
) -> Path:
    diagnostics_dir = diagnostics_dir_path(repo_root)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{diagnostic_timestamp_slug()}__{mams_channel.name}__{command}__invalid-reply.md"
    )
    path = diagnostics_dir / filename
    session_label = session_id or "(none)"
    contents = "\n".join(
        [
            "# Invalid Managed Channel Reply",
            "",
            f"- channel: `{mams_channel.name}`",
            f"- command: `{command}`",
            f"- runner: `{mams_channel.runner}`",
            f"- session_id: `{session_label}`",
            f"- captured_at: `{iso_now()}`",
            "",
            "## Validation Error",
            "",
            validation_error,
            "",
        ]
    )
    for label, raw_reply in raw_replies:
        contents += "\n".join(
            [
                f"## {label}",
                "",
                "```text",
                raw_reply.rstrip(),
                "```",
                "",
            ]
        )
    path.write_text(contents, encoding="utf-8")
    return path


def build_dangerous_new_session_prompt(permission_text: str) -> str:
    return (
        "You are creating a fresh managed MAMS mams_channel session for future collaboration.\n"
        "This call exists only to establish a new session id.\n"
        "Do not ask questions. Do not assume prior task continuity.\n"
        "Reply with a short plain-text acknowledgment that the fresh managed channel session is ready.\n\n"
        "User permission for replacing the prior managed continuity:\n"
        f"{permission_text}\n"
    )


def update_previous_session_ids_for_replacement(
    previous_session_ids: tuple[str, ...],
    previous_session_id: Optional[str],
    current_session_id: str,
) -> tuple[str, ...]:
    updated: list[str] = []
    if (
        isinstance(previous_session_id, str)
        and previous_session_id
        and previous_session_id != current_session_id
    ):
        updated.append(previous_session_id)
    for item in previous_session_ids:
        if item not in updated and item != current_session_id:
            updated.append(item)
    return tuple(updated[:2])


def looks_like_missing_thread_error(message: str) -> bool:
    lowered = message.lower()
    return "thread" in lowered and "not found" in lowered


def is_mutating_command(command: str) -> bool:
    return command in INVOKE_MUTATING_COMMANDS


def resolve_claude_permission_mode(
    sandbox_mode: str,
    runner_config: dict[str, object],
) -> str:
    override = normalize_optional_string(runner_config.get("permission_mode"))
    if override:
        return override
    if sandbox_mode == SANDBOX_DANGER_FULL_ACCESS:
        return "bypassPermissions"
    if sandbox_mode == SANDBOX_WORKSPACE_WRITE:
        return "acceptEdits"
    return "plan"


def resolve_runner_extra_args(runner_config: dict[str, object]) -> list[str]:
    raw = runner_config.get("extra_args")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("runner_config.extra_args must be a JSON array of strings when provided.")
    extra_args: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"runner_config.extra_args[{index}] must be a non-empty string when provided."
            )
        extra_args.append(item.strip())
    return extra_args


def monitor_runner_process(
    *,
    proc: subprocess.Popen[str],
    timeout_s: int,
    idle_timeout_s: int,
    activity_paths: list[Path],
    on_stdout_line: Callable[[str], None],
    on_stderr_line: Callable[[str], None],
    timeout_label: str,
    inactivity_label: str,
) -> int:
    last_activity_at = time.monotonic()
    tracked_stats: dict[Path, tuple[int, int]] = {path: (-1, -1) for path in activity_paths}

    def mark_activity() -> None:
        nonlocal last_activity_at
        last_activity_at = time.monotonic()

    def drain_stdout() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if line:
                mark_activity()
            on_stdout_line(line)

    def drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            if line:
                mark_activity()
            on_stderr_line(line)

    stdout_thread = threading.Thread(target=drain_stdout, daemon=True)
    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    started_at = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - started_at
            if elapsed > timeout_s:
                proc.kill()
                raise RuntimeError(f"{timeout_label} timed out after {timeout_s}s")

            for path in activity_paths:
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                previous = tracked_stats[path]
                current = (stat.st_size, stat.st_mtime_ns)
                if current != previous:
                    tracked_stats[path] = current
                    mark_activity()

            if time.monotonic() - last_activity_at > idle_timeout_s:
                proc.kill()
                raise RuntimeError(
                    f"{inactivity_label} became inactive for too long while waiting "
                    f"(no observable activity for {idle_timeout_s}s)."
                )

            wait_timeout = max(0.1, min(PROCESS_POLL_INTERVAL_S, timeout_s - elapsed))
            try:
                rc = proc.wait(timeout=wait_timeout)
                break
            except subprocess.TimeoutExpired:
                continue
    except Exception:
        proc.kill()
        raise
    finally:
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

    return rc


def execute_command_for_mams_channel(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    *,
    command: str,
    stdin_text: str,
    timeout_s: int,
    model: Optional[str],
    reasoning_effort: Optional[str],
) -> tuple[str, Optional[UserEscalationRequest], MamsChannelConfig]:
    session_id = mams_channel.session_id

    if command in INVOKE_MUTATING_COMMANDS and not mams_channel.can_mutate:
        raise RuntimeError(
            "\n".join(
                [
                    f"MAMS channel '{mams_channel.name}' is configured with can_mutate: false.",
                    "execute-this-plan and execute-this-plan-part are only allowed for a mutate-capable mams_channel.",
                    "Choose a different mams_channel or update the mams_channel config through configure.",
                ]
            )
        )

    prompt = build_prompt(
        repo_root,
        mams_channel,
        command,
        stdin_text,
    )
    sandbox_mode = resolve_execution_sandbox(command, stdin_text)
    stage_context = command_stage_context(command, stdin_text)

    def run_once(current_session_id: Optional[str], current_prompt: str) -> RunnerRunResult:
        try:
            return run_runner_for_mams_channel(
                repo_root=repo_root,
                mams_channel=mams_channel,
                session_id=current_session_id,
                prompt=current_prompt,
                sandbox_mode=sandbox_mode,
                timeout_s=timeout_s,
                model=model,
                reasoning_effort=reasoning_effort,
            )
        except Exception as exc:
            if current_session_id and looks_like_missing_thread_error(str(exc)):
                raise RuntimeError(
                    "\n".join(
                        [
                            str(exc),
                            "",
                            f"The managed mams_channel '{mams_channel.name}' has a stored session id locally, but the configured runner could not resume it.",
                            "Do not manually delete or replace the managed mams_channel config and do not call raw runner CLIs directly.",
                            "If the user explicitly wants to abandon this continuity and start fresh, run "
                            "<skill_root>/bin/dangerous-new-session.",
                        ]
                    )
                ) from exc
            raise

    result = run_once(session_id, prompt)

    updated_mams_channel = replace(
        mams_channel,
        session_id=result.session_id,
        model=mams_channel.model or model,
        reasoning_effort=mams_channel.reasoning_effort or reasoning_effort,
        updated_at=iso_now(),
    )
    updated_mams_channel = advance_stage_reminder_state(
        updated_mams_channel,
        stage_context=stage_context,
    )

    try:
        validated = validate_command_reply(command, result.reply)
        result.reply = validated.normalized_reply
        user_escalation_request = validated.user_escalation_request
    except ValueError as exc:
        retry_notice = build_protocol_notice(command, str(exc))
        retry_prompt = append_protocol_notice(prompt, retry_notice)
        retry_result = run_once(result.session_id, retry_prompt)
        updated_mams_channel = replace(
            updated_mams_channel,
            session_id=retry_result.session_id,
            updated_at=iso_now(),
        )
        try:
            retry_validated = validate_command_reply(command, retry_result.reply)
            retry_result.reply = retry_validated.normalized_reply
            return retry_result.reply, retry_validated.user_escalation_request, updated_mams_channel
        except ValueError as retry_exc:
            combined_error = (
                "The managed channel ended twice without a valid structured result.\n"
                f"First validation error: {exc}\n"
                f"Second validation error: {retry_exc}"
            )
            first_preview = diagnostic_preview(result.reply)
            second_preview = diagnostic_preview(retry_result.reply)
            diagnostic_path = write_invalid_reply_diagnostic(
                repo_root,
                mams_channel=updated_mams_channel,
                command=command,
                session_id=retry_result.session_id,
                validation_error=combined_error,
                raw_replies=[
                    ("First Invalid Reply", result.reply),
                    ("Second Invalid Reply", retry_result.reply),
                ],
            )
            raise RuntimeError(
                "\n".join(
                    [
                        f"Managed mams_channel '{updated_mams_channel.name}' stopped twice without a valid structured result for command '{command}'.",
                        f"First validation error: {exc}",
                        f"Second validation error: {retry_exc}",
                        f"Diagnostic saved at: {diagnostic_path}",
                        "First reply preview:",
                        first_preview,
                        "Second reply preview:",
                        second_preview,
                    ]
                )
            ) from retry_exc

    return result.reply, user_escalation_request, updated_mams_channel


def resolve_mams_channels_for_command(
    repo_root: Path,
    mams_channel_name: str,
    *,
    default_model: Optional[str],
    default_reasoning_effort: Optional[str],
) -> tuple[MamsSkillConfig, MamsChannelConfig]:
    config = read_skill_config(repo_root)
    mams_channel = find_mams_channel(config.mams_channels, mams_channel_name)
    if mams_channel is None:
        mams_channel = build_mams_channel_config(
            mams_channel_name,
            model=default_model,
            reasoning_effort=default_reasoning_effort,
        )
    return config, mams_channel


def persist_mams_channels_for_command(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
) -> None:
    write_skill_config(
        repo_root,
        MamsSkillConfig(
            version=CONFIG_VERSION,
            mams_channels=upsert_mams_channel(config.mams_channels, replace(mams_channel, updated_at=iso_now())),
            invoker_reminder_turn_count=config.invoker_reminder_turn_count,
            updated_at=iso_now(),
        ),
    )


def persist_multiple_mams_channels(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channels: list[MamsChannelConfig],
) -> MamsSkillConfig:
    updated_channels = config.mams_channels
    for mams_channel in mams_channels:
        updated_channels = upsert_mams_channel(
            updated_channels,
            replace(mams_channel, updated_at=iso_now()),
        )
    updated_config = MamsSkillConfig(
        version=CONFIG_VERSION,
        mams_channels=updated_channels,
        invoker_reminder_turn_count=config.invoker_reminder_turn_count,
        updated_at=iso_now(),
    )
    write_skill_config(repo_root, updated_config)
    return updated_config


def run_invoke_command(
    repo_root: Path,
    stdin_text: str,
    *,
    default_mams_channel_name: str,
    timeout_s: int,
    override_model: Optional[str],
    override_reasoning_effort: Optional[str],
    effective_default_model: Optional[str],
    effective_default_reasoning_effort: Optional[str],
) -> str:
    payload = parse_invoke_payload(stdin_text)
    config = read_skill_config(repo_root)

    prepared: list[tuple[InvokeRequest, MamsChannelConfig, Optional[str], Optional[str]]] = []
    seen_channel_names: set[str] = set()
    for request in payload.requests:
        mams_channel_name = request.mams_channel_name or default_mams_channel_name
        if mams_channel_name in seen_channel_names:
            raise ValueError(
                f"invoke does not allow duplicate mams_channel targets in one call: {mams_channel_name}"
            )
        seen_channel_names.add(mams_channel_name)

        mams_channel = find_mams_channel(config.mams_channels, mams_channel_name)
        if mams_channel is None:
            mams_channel = build_mams_channel_config(
                mams_channel_name,
                model=effective_default_model,
                reasoning_effort=effective_default_reasoning_effort,
            )

        model = override_model or mams_channel.model or DEFAULT_MODEL
        reasoning_effort = (
            override_reasoning_effort
            or mams_channel.reasoning_effort
            or DEFAULT_REASONING_EFFORT
        )
        prepared.append(
            (
                replace(request, mams_channel_name=mams_channel_name),
                mams_channel,
                model,
                reasoning_effort,
            )
        )

    def perform(item: tuple[InvokeRequest, MamsChannelConfig, Optional[str], Optional[str]]) -> InvokeSettledResult:
        request, mams_channel, model, reasoning_effort = item
        try:
            reply, user_escalation_request, updated_mams_channel = execute_command_for_mams_channel(
                repo_root,
                mams_channel,
                command=request.command,
                stdin_text=request.stdin_text,
                timeout_s=timeout_s,
                model=model,
                reasoning_effort=reasoning_effort,
            )
            return InvokeSettledResult(
                request=request,
                status="ok",
                reply=reply,
                user_escalation_request=user_escalation_request,
                governor_review_reply=None,
                error=None,
                updated_mams_channel=updated_mams_channel,
            )
        except Exception as exc:
            return InvokeSettledResult(
                request=request,
                status="error",
                reply=None,
                user_escalation_request=None,
                governor_review_reply=None,
                error=str(exc),
                updated_mams_channel=None,
            )

    use_parallel = len(prepared) > 1 and all(not is_mutating_command(item[0].command) for item in prepared)
    if use_parallel:
        with ThreadPoolExecutor(max_workers=len(prepared)) as executor:
            settled = list(executor.map(perform, prepared))
        execution_mode = "concurrent read-only fanout"
    else:
        settled = [perform(item) for item in prepared]
        execution_mode = "sequential invoke"

    staged_config = config
    reviewed_results: list[InvokeSettledResult] = []
    reviewed_channels: list[MamsChannelConfig] = []
    for item in settled:
        if item.status != "ok" or item.updated_mams_channel is None:
            reviewed_results.append(item)
            continue
        approved_request, governor_review_reply, updated_governor = maybe_review_user_escalation_with_governor(
            repo_root,
            staged_config,
            origin_mams_channel=item.updated_mams_channel,
            origin_command=item.request.command,
            origin_reply=item.reply or "",
            user_escalation_request=item.user_escalation_request,
            timeout_s=timeout_s,
            model=override_model,
            reasoning_effort=override_reasoning_effort,
        )
        next_result = replace(
            item,
            user_escalation_request=approved_request,
            governor_review_reply=governor_review_reply,
        )
        reviewed_results.append(next_result)
        reviewed_channels.append(item.updated_mams_channel)
        if updated_governor is not None:
            reviewed_channels.append(updated_governor)
            staged_config = MamsSkillConfig(
                version=staged_config.version,
                mams_channels=upsert_mams_channel(staged_config.mams_channels, updated_governor),
                invoker_reminder_turn_count=staged_config.invoker_reminder_turn_count,
                updated_at=staged_config.updated_at,
            )

    updated_channels = reviewed_channels or [
        item.updated_mams_channel for item in settled if item.updated_mams_channel is not None
    ]
    updated_config = (
        persist_multiple_mams_channels(repo_root, config, updated_channels)
        if updated_channels
        else config
    )
    for updated_mams_channel in updated_channels:
        if updated_mams_channel.runner == RUNNER_CODEX:
            try_promote_exec_session_to_cli(updated_mams_channel.session_id)

    summary = format_invoke_summary(reviewed_results, execution_mode=execution_mode)
    return format_invoker_facing_output(
        repo_root,
        updated_config,
        reply=summary,
        user_escalation_request=None,
        governor_review_reply=None,
    )


def run_codex(
    repo_root: Path,
    session_id: Optional[str],
    prompt: str,
    sandbox_mode: str,
    timeout_s: int,
    model: Optional[str],
    reasoning_effort: Optional[str],
) -> RunnerRunResult:
    tmp_last = Path(tempfile.mkstemp(prefix="mad-agent-mesh-last-", suffix=".txt")[1])
    try:
        base_args = [
            "exec",
            "--skip-git-repo-check",
            "--json",
            "--sandbox",
            sandbox_mode,
            "--cd",
            str(repo_root),
            "--output-last-message",
            str(tmp_last),
        ]
        if model:
            base_args += ["--model", model]
        if reasoning_effort:
            base_args += ["--config", f'model_reasoning_effort="{reasoning_effort}"']

        if session_id:
            cmd = [CODEX_BIN, *base_args, "resume", session_id, "-"]
        else:
            cmd = [CODEX_BIN, *base_args, "-"]

        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        thread_id: Optional[str] = None
        stderr_lines: list[str] = []

        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception:
            proc.kill()
            raise

        def drain_stdout(line: str) -> None:
            nonlocal thread_id
            event = safe_json_loads(line.strip())
            if not event:
                return
            tid = detect_thread_id(event)
            if tid and not thread_id:
                thread_id = tid

        def drain_stderr(line: str) -> None:
            if line:
                stderr_lines.append(line.rstrip())

        rc = monitor_runner_process(
            proc=proc,
            timeout_s=timeout_s,
            idle_timeout_s=PROCESS_IDLE_TIMEOUT_S,
            activity_paths=[tmp_last],
            on_stdout_line=drain_stdout,
            on_stderr_line=drain_stderr,
            timeout_label="codex",
            inactivity_label="codex",
        )

        if rc != 0:
            stderr = "\n".join(line for line in stderr_lines if line).strip()
            raise RuntimeError(stderr or f"codex exited with code {rc}")

        if not thread_id:
            raise RuntimeError("Failed to detect Codex session_id from JSONL output.")

        reply = ""
        try:
            reply = tmp_last.read_text(encoding="utf-8").strip()
        except Exception:
            reply = ""
        if not reply:
            raise RuntimeError("Failed to read Codex final message output.")

        return RunnerRunResult(session_id=thread_id, reply=reply)
    finally:
        try:
            tmp_last.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            pass


def run_claude_code(
    repo_root: Path,
    session_id: Optional[str],
    prompt: str,
    sandbox_mode: str,
    timeout_s: int,
    model: Optional[str],
    reasoning_effort: Optional[str],
    runner_config: dict[str, object],
) -> RunnerRunResult:
    tmp_stream = Path(tempfile.mkstemp(prefix="mad-agent-mesh-claude-stream-", suffix=".jsonl")[1])
    try:
        permission_mode = resolve_claude_permission_mode(sandbox_mode, runner_config)
        extra_args = resolve_runner_extra_args(runner_config)
        cmd = [
            CLAUDE_BIN,
            "-p",
            "--verbose",
            "--output-format",
            "stream-json",
            "--permission-mode",
            permission_mode,
        ]
        if model:
            cmd += ["--model", model]
        if reasoning_effort:
            cmd += ["--effort", reasoning_effort]
        if session_id:
            cmd += ["--resume", session_id]
        cmd.extend(extra_args)

        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        detected_session_id: Optional[str] = None
        final_reply: Optional[str] = None
        stderr_lines: list[str] = []

        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception:
            proc.kill()
            raise

        def drain_stdout(line: str) -> None:
            nonlocal detected_session_id, final_reply
            with tmp_stream.open("a", encoding="utf-8") as handle:
                handle.write(line)

            event = safe_json_loads(line.strip())
            if not event:
                return

            sid = event.get("session_id")
            if isinstance(sid, str) and sid and not detected_session_id:
                detected_session_id = sid

            if event.get("type") == "system" and not detected_session_id:
                subtype = event.get("subtype")
                if subtype == "init":
                    raw_session_id = event.get("session_id")
                    if isinstance(raw_session_id, str) and raw_session_id:
                        detected_session_id = raw_session_id

            if event.get("type") == "result":
                result_text = event.get("result")
                if isinstance(result_text, str):
                    final_reply = result_text.strip()
                raw_session_id = event.get("session_id")
                if isinstance(raw_session_id, str) and raw_session_id:
                    detected_session_id = raw_session_id

        def drain_stderr(line: str) -> None:
            if line:
                stderr_lines.append(line.rstrip())

        rc = monitor_runner_process(
            proc=proc,
            timeout_s=timeout_s,
            idle_timeout_s=PROCESS_IDLE_TIMEOUT_S,
            activity_paths=[tmp_stream],
            on_stdout_line=drain_stdout,
            on_stderr_line=drain_stderr,
            timeout_label="claude-code",
            inactivity_label="claude-code",
        )

        if rc != 0:
            stderr = "\n".join(line for line in stderr_lines if line).strip()
            raise RuntimeError(stderr or f"claude-code exited with code {rc}")

        if not detected_session_id:
            raise RuntimeError("Failed to detect Claude Code session_id from stream-json output.")
        if not final_reply:
            raise RuntimeError("Failed to read Claude Code final result from stream-json output.")
        return RunnerRunResult(session_id=detected_session_id, reply=final_reply)
    finally:
        try:
            tmp_stream.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            pass


def run_runner_for_mams_channel(
    repo_root: Path,
    mams_channel: MamsChannelConfig,
    session_id: Optional[str],
    prompt: str,
    sandbox_mode: str,
    timeout_s: int,
    model: Optional[str],
    reasoning_effort: Optional[str],
) -> RunnerRunResult:
    if mams_channel.runner == RUNNER_CODEX:
        return run_codex(
            repo_root=repo_root,
            session_id=session_id,
            prompt=prompt,
            sandbox_mode=sandbox_mode,
            timeout_s=timeout_s,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    if mams_channel.runner == RUNNER_CLAUDE_CODE:
        return run_claude_code(
            repo_root=repo_root,
            session_id=session_id,
            prompt=prompt,
            sandbox_mode=sandbox_mode,
            timeout_s=timeout_s,
            model=model,
            reasoning_effort=reasoning_effort,
            runner_config=mams_channel.runner_config,
        )
    raise RuntimeError(f"Unsupported mams_channel runner: {mams_channel.runner}")


def find_rollout_for_session(session_id: str) -> Optional[Path]:
    sessions_root = CODEX_HOME / "sessions"
    if not sessions_root.exists():
        return None

    best: Optional[Tuple[float, Path]] = None
    for root, _dirs, files in os.walk(sessions_root):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            if session_id not in name:
                continue
            p = Path(root) / name
            try:
                mtime = p.stat().st_mtime
            except Exception:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, p)
    return best[1] if best else None


def try_promote_exec_session_to_cli(session_id: str) -> None:
    rollout = find_rollout_for_session(session_id)
    if rollout is None:
        return
    try:
        raw = rollout.read_text(encoding="utf-8")
        idx = raw.find("\n")
        if idx == -1:
            return
        first_line = raw[:idx].rstrip("\n\r")
        rest = raw[idx + 1 :]
        event = safe_json_loads(first_line)
        if not event:
            return
        if event.get("type") != "session_meta":
            return
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return
        if payload.get("id") != session_id:
            return
        if payload.get("originator") != "codex_exec":
            return
        if payload.get("source") != "exec":
            return

        payload = dict(payload)
        payload["originator"] = "codex_cli_rs"
        payload["source"] = "cli"
        event = dict(event)
        event["payload"] = payload

        new_first = json.dumps(event, ensure_ascii=False)
        if "\n" in new_first:
            return

        tmp = rollout.with_suffix(rollout.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(new_first + "\n" + rest, encoding="utf-8")
        tmp.replace(rollout)
    except Exception:
        return


def main() -> int:
    shared_options = argparse.ArgumentParser(add_help=False)
    shared_options.add_argument(
        "--cwd",
        default=None,
        help="Working directory used to locate the project session root.",
    )
    shared_options.add_argument(
        "--mams-channel",
        default=DEFAULT_MAMS_CHANNEL_NAME,
        dest="mams_channel",
        help=f"Target mams_channel name inside {MANAGED_DIRNAME}/{MAMS_CHANNELS_FILENAME} (default: default).",
    )
    shared_options.add_argument("--timeout-s", type=int, default=3600, help="Managed runner timeout in seconds.")
    shared_options.add_argument("--model", default=None, help="Optional model override for this call.")
    shared_options.add_argument("--reasoning-effort", default=None, help="Optional reasoning effort override for this call.")

    parser = argparse.ArgumentParser(prog="mad-agent-mesh", parents=[shared_options])

    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in TOOL_HELP:
        sub.add_parser(name, help=TOOL_HELP[name], parents=[shared_options], add_help=False)

    args = parser.parse_args()
    shared_args, _ = shared_options.parse_known_args(sys.argv[1:])
    args.cwd = shared_args.cwd
    args.mams_channel = shared_args.mams_channel
    args.timeout_s = shared_args.timeout_s
    args.model = shared_args.model
    args.reasoning_effort = shared_args.reasoning_effort
    mams_channel_name = normalize_optional_string(args.mams_channel)
    if not mams_channel_name:
        eprint("--mams-channel must be a non-empty string.")
        return 2

    cwd_explicit = args.cwd is not None
    start_cwd = Path(args.cwd).expanduser() if cwd_explicit else Path.cwd()

    repo_root = find_session_root(start_cwd)
    if repo_root is None and cwd_explicit:
        chosen = start_cwd.expanduser().resolve()
        chosen_managed_dir = chosen / MANAGED_DIRNAME
        if not is_global_managed_dir(chosen_managed_dir):
            repo_root = chosen

    if repo_root is None:
        candidates = candidate_roots_with_managed_dir(start_cwd)
        lines = [
            "No project Mad Agent Mesh session root is configured.",
            "Could not find an existing managed session anchor:",
            f"  - <dir>/{MANAGED_DIRNAME}/{MAMS_CHANNELS_FILENAME}",
            f"(excluding the global {MANAGED_GLOBAL_DIR} directory).",
            "",
            "Ask the user to choose a directory to store the managed session state for this workspace.",
        ]
        if candidates:
            lines.append(f"Candidate directories that already contain a {MANAGED_DIRNAME}/ directory (closest first):")
            for c in candidates:
                lines.append(f"  - {c}")
            lines.append("Then rerun this command with: --cwd <chosen_dir>")
        else:
            lines.append(f"No {MANAGED_DIRNAME}/ directory was found in parent directories (excluding the global one).")
            lines.append("Ask the user to choose a directory, then rerun this command with: --cwd <chosen_dir>.")
        raise RuntimeError("\n".join(lines))

    stdin_text = sys.stdin.read()
    if not stdin_text.strip():
        eprint("Empty input. Provide content via stdin.")
        return 2

    effective_default_model = args.model or DEFAULT_MODEL
    effective_default_reasoning_effort = args.reasoning_effort or DEFAULT_REASONING_EFFORT

    if args.cmd == "configure":
        try:
            payload = parse_configure_payload(stdin_text)
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / MANAGED_DIRNAME).mkdir(parents=True, exist_ok=True)
            config = read_skill_config(repo_root)
            updated_config = apply_configure_payload(config, payload)
            write_skill_config(repo_root, updated_config)
        except Exception as exc:
            eprint(str(exc))
            return 1

        lines = [
            "configure applied.",
            f"Config path: {mams_channels_file_path(repo_root)}",
        ]
        if payload.mams_channels_patch is not None:
            lines.append(
                "Updated mams_channels: " + ", ".join(patch["name"] for patch in payload.mams_channels_patch)
            )
        sys.stdout.write(
            format_invoker_facing_output(
                repo_root,
                updated_config,
                reply="\n".join(lines),
                user_escalation_request=None,
                governor_review_reply=None,
            )
        )
        return 0

    if args.cmd == "invoke":
        try:
            sys.stdout.write(
                run_invoke_command(
                    repo_root,
                    stdin_text,
                    default_mams_channel_name=mams_channel_name,
                    timeout_s=args.timeout_s,
                    override_model=args.model,
                    override_reasoning_effort=args.reasoning_effort,
                    effective_default_model=effective_default_model,
                    effective_default_reasoning_effort=effective_default_reasoning_effort,
                )
            )
        except Exception as exc:
            eprint(str(exc))
            return 1
        return 0

    if args.cmd == "dangerous-new-session":
        try:
            payload = parse_dangerous_new_session_payload(stdin_text)
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / MANAGED_DIRNAME).mkdir(parents=True, exist_ok=True)
            config, mams_channel = resolve_mams_channels_for_command(
                repo_root,
                mams_channel_name,
                default_model=effective_default_model,
                default_reasoning_effort=effective_default_reasoning_effort,
            )
            previous_session_id = mams_channel.session_id
            effective_model = payload.model or mams_channel.model or effective_default_model
            effective_reasoning_effort = (
                payload.reasoning_effort
                or mams_channel.reasoning_effort
                or effective_default_reasoning_effort
            )
            next_prompt_profile = mams_channel.prompt_profile
            if payload.mams_channel_description is not None:
                next_prompt_profile = replace(
                    next_prompt_profile,
                    public=replace(
                        next_prompt_profile.public,
                        description=payload.mams_channel_description,
                    ),
                )
            if payload.target_session_id:
                current_session_id = payload.target_session_id
                previous_session_ids = update_previous_session_ids_for_replacement(
                    mams_channel.previous_session_ids,
                    previous_session_id,
                    current_session_id,
                )
                switched_to_existing = True
            else:
                prompt = build_dangerous_new_session_prompt(payload.user_permission)
                result = run_runner_for_mams_channel(
                    repo_root=repo_root,
                    mams_channel=mams_channel,
                    session_id=None,
                    prompt=prompt,
                    sandbox_mode=SANDBOX_READ_ONLY,
                    timeout_s=args.timeout_s,
                    model=effective_model,
                    reasoning_effort=effective_reasoning_effort,
                )
                current_session_id = result.session_id
                if mams_channel.runner == RUNNER_CODEX:
                    try_promote_exec_session_to_cli(current_session_id)
                previous_session_ids = update_previous_session_ids_for_replacement(
                    mams_channel.previous_session_ids,
                    previous_session_id,
                    current_session_id,
                )
                switched_to_existing = False
            updated_mams_channel = build_mams_channel_config(
                mams_channel.name,
                prompt_profile=next_prompt_profile,
                can_mutate=mams_channel.can_mutate,
                runner=mams_channel.runner,
                runner_config=mams_channel.runner_config,
                session_id=current_session_id,
                model=effective_model,
                reasoning_effort=effective_reasoning_effort,
                previous_session_ids=previous_session_ids,
                last_stage_context=None,
                stage_reminder_turn_count=0,
            )
            persist_mams_channels_for_command(repo_root, config, updated_mams_channel)
        except Exception as exc:
            eprint(str(exc))
            return 1

        lines = [
            "dangerous-new-session authorized.",
            f"Target mams_channel: {mams_channel_name}",
            (
                f"Managed mams_channel now points to target session id: {current_session_id}"
                if switched_to_existing
                else f"Managed mams_channel now points to fresh session id: {current_session_id}"
            ),
            "Do not call raw runner CLIs directly and do not edit the managed mams_channel config manually.",
        ]
        if previous_session_ids:
            lines.append(
                "Recorded previous session ids for this mams_channel (newest first): "
                + ", ".join(previous_session_ids)
            )
        else:
            lines.append("There was no prior managed session id for this mams_channel to record.")
        updated_config = read_skill_config(repo_root)
        sys.stdout.write(
            format_invoker_facing_output(
                repo_root,
                updated_config,
                reply="\n".join(lines),
                user_escalation_request=None,
                governor_review_reply=None,
            )
        )
        return 0

    try:
        config, mams_channel = resolve_mams_channels_for_command(
            repo_root,
            mams_channel_name,
            default_model=effective_default_model,
            default_reasoning_effort=effective_default_reasoning_effort,
        )
    except Exception as exc:
        eprint(str(exc))
        return 1

    session_id = mams_channel.session_id
    model = args.model or mams_channel.model or DEFAULT_MODEL
    reasoning_effort = args.reasoning_effort or mams_channel.reasoning_effort or DEFAULT_REASONING_EFFORT
    try:
        reply, user_escalation_request, updated_mams_channel = execute_command_for_mams_channel(
            repo_root,
            mams_channel,
            command=args.cmd,
            stdin_text=stdin_text,
            timeout_s=args.timeout_s,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    except Exception as exc:
        eprint(str(exc))
        return 1

    governor_review_reply: Optional[str] = None
    approved_escalation_request, governor_review_reply, updated_governor = maybe_review_user_escalation_with_governor(
        repo_root,
        config,
        origin_mams_channel=updated_mams_channel,
        origin_command=args.cmd,
        origin_reply=reply,
        user_escalation_request=user_escalation_request,
        timeout_s=args.timeout_s,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
    )
    updated_channels_to_persist = [updated_mams_channel]
    if updated_governor is not None:
        updated_channels_to_persist.append(updated_governor)
    updated_config = persist_multiple_mams_channels(repo_root, config, updated_channels_to_persist)
    if updated_mams_channel.runner == RUNNER_CODEX:
        try_promote_exec_session_to_cli(updated_mams_channel.session_id)
    if updated_governor is not None and updated_governor.runner == RUNNER_CODEX:
        try_promote_exec_session_to_cli(updated_governor.session_id)

    sys.stdout.write(
        format_invoker_facing_output(
            repo_root,
            updated_config,
            reply=reply,
            user_escalation_request=approved_escalation_request,
            governor_review_reply=governor_review_reply,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

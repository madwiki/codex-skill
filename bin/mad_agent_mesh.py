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
INIT_TASK_FIELD = "task_background"
INIT_RECOVERY_FIELD = "recovery_background"
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
CONFIGURE_MAMS_INVOKER_FIELD = "mams_invoker"
CONFIGURE_SHARED_STAGES_FIELD = "shared_stages"
CONFIGURE_MAMS_CHANNELS_FIELD = "mams_channels"
INIT_TASK_REPLY_TITLE = "Task Understanding Reply"
INIT_RECOVERY_REPLY_TITLE = "Context Recovery Reply"
REVIEW_PLAN_REPLY_TITLE = "Plan Review Reply"
REVIEW_WORK_REPLY_TITLE = "Work Review Reply"
SYNC_REPLY_TITLE = "Discussion Reply"
SYNC_PLAN_TITLE = "Plan"
SANDBOX_READ_ONLY = "read-only"
SANDBOX_WORKSPACE_WRITE = "workspace-write"
SANDBOX_DANGER_FULL_ACCESS = "danger-full-access"
PROCESS_POLL_INTERVAL_S = 20
PROCESS_IDLE_TIMEOUT_S = 600
MAMS_CHANNELS_FILENAME = "mams_channels.json"
LEGACY_SESSION_FILENAME = "codex_session.json"
LEGACY_HISTORY_FILENAME = "codex_session_history.json"
MANAGED_DIRNAME = ".mad-agent-mesh"
LEGACY_MANAGED_DIRNAME = ".claude"
DEFAULT_MAMS_CHANNEL_NAME = "default"
DEFAULT_MAMS_CHANNEL_DESCRIPTION = "Primary managed MAMS channel."
MIGRATED_MAMS_CHANNEL_DESCRIPTION = "Migrated primary managed MAMS channel."
CONFIG_VERSION = 5
REF_DIRECTORY = f"{MANAGED_DIRNAME}/refs"
RUNNER_CODEX = "codex"
RUNNER_CLAUDE_CODE = "claude-code"
SUPPORTED_RUNNERS = {RUNNER_CODEX, RUNNER_CLAUDE_CODE}
REF_PATTERN = re.compile(r"\[\[REF:(?P<path>[^:\]]+?)(?:::(?P<locator>[^\]]+))?\]\]")
LEGACY_STAGE_KEY_MAP = {
    "chat": "sync",
    "work-sync": "sync",
    "review-my-plan": "review-this-plan",
    "review-my-work": "review-this-work",
    "request-mutation": "execute-this-plan",
}

LEGACY_STRUCTURED_FILENAMES = (
    "codex_agents.json",
    "codex_channels.json",
    "mams_channels.json",
)

TOOL_HELP = {
    "init": "Bootstrap managed-channel collaboration for a new task or recovery sync (reads JSON from stdin).",
    "invoke": "Invoke one or more mams_channel commands through one blocking wrapper call (reads JSON from stdin).",
    "sync": "Discussion / coordination / disagreement-resolution turn (reads JSON from stdin).",
    "review-this-plan": "Review the submitted plan on the targeted managed channel without mutating state (reads JSON from stdin).",
    "review-this-work": "Review submitted work on the targeted managed channel without mutating state (reads JSON from stdin).",
    "execute-this-plan": "Execute one approved plan on a mutate-capable managed channel (reads JSON from stdin).",
    "execute-this-plan-part": "Execute one approved plan part on a mutate-capable managed channel (reads JSON from stdin).",
    "dangerous-new-session": "Explicitly authorize discarding continuity and starting or switching a managed MAMS mams_channel session (reads JSON from stdin).",
    "configure": "Patch mams_invoker guidance, shared guidance, or mams_channel metadata (reads JSON from stdin).",
    "update-config": "Normalize discoverable managed state and rewrite the canonical config (does not read JSON from stdin).",
}

INVOKE_REQUESTS_FIELD = "requests"
INVOKE_COMMAND_FIELD = "command"
INVOKE_INPUT_FIELD = "input"
INVOKE_MAMS_CHANNEL_FIELD = "mams_channel"
INVOKE_ALLOWED_COMMANDS = {
    "init",
    "sync",
    "review-this-plan",
    "review-this-work",
    "execute-this-plan",
    "execute-this-plan-part",
}
INVOKE_MUTATING_COMMANDS = {"execute-this-plan", "execute-this-plan-part"}


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


CLAUDE_GLOBAL_DIR = (Path.home() / LEGACY_MANAGED_DIRNAME).resolve()
MANAGED_GLOBAL_DIR = (Path.home() / MANAGED_DIRNAME).resolve()


def is_global_managed_dir(directory: Path) -> bool:
    try:
        resolved = directory.resolve()
        return resolved in {CLAUDE_GLOBAL_DIR, MANAGED_GLOBAL_DIR}
    except Exception:
        return str(directory) in {str(CLAUDE_GLOBAL_DIR), str(MANAGED_GLOBAL_DIR)}


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
    - Never treat the global ~/.claude or ~/.mad-agent-mesh directory as a project root.
    - `.mad-agent-mesh/mams_channels.json` is the stable anchor.
    - Legacy structured config filenames and `.claude/codex_session.json` are accepted only as migration anchors so the wrapper can
      migrate them into the new structured config location.
    - `.mad-agent-mesh/` or `.claude/` alone can exist at many levels for other purposes, so we do
      not auto-pick based on the directory alone.
    """
    for p in iter_ancestors(start):
        managed_dir = p / MANAGED_DIRNAME
        legacy_dir = p / LEGACY_MANAGED_DIRNAME
        if is_global_managed_dir(managed_dir) or is_global_managed_dir(legacy_dir):
            continue
        if any((managed_dir / filename).is_file() for filename in LEGACY_STRUCTURED_FILENAMES):
            return p
        if any((legacy_dir / filename).is_file() for filename in LEGACY_STRUCTURED_FILENAMES):
            return p
        if (legacy_dir / LEGACY_SESSION_FILENAME).is_file():
            return p
    return None


def candidate_roots_with_managed_dir(start: Path, limit: int = 5) -> list[Path]:
    candidates: list[Path] = []
    for p in iter_ancestors(start):
        managed_dir = p / MANAGED_DIRNAME
        legacy_dir = p / LEGACY_MANAGED_DIRNAME
        if is_global_managed_dir(managed_dir) or is_global_managed_dir(legacy_dir):
            continue
        if managed_dir.is_dir() or legacy_dir.is_dir():
            candidates.append(p)
            if len(candidates) >= limit:
                break
    return candidates


def mams_channels_file_path(repo_root: Path) -> Path:
    return repo_root / MANAGED_DIRNAME / MAMS_CHANNELS_FILENAME


def iter_legacy_structured_config_paths(repo_root: Path) -> Iterator[Path]:
    for filename in LEGACY_STRUCTURED_FILENAMES:
        managed_path = repo_root / MANAGED_DIRNAME / filename
        if managed_path.name != MAMS_CHANNELS_FILENAME:
            yield managed_path
        yield repo_root / LEGACY_MANAGED_DIRNAME / filename


def legacy_session_file_path(repo_root: Path) -> Path:
    return repo_root / LEGACY_MANAGED_DIRNAME / LEGACY_SESSION_FILENAME


def legacy_session_history_file_path(repo_root: Path) -> Path:
    return repo_root / LEGACY_MANAGED_DIRNAME / LEGACY_HISTORY_FILENAME


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class MamsChannelConfig:
    name: str
    description: str
    focus: Optional[str]
    baseline: Optional[str]
    extra_context: Optional[str]
    stage_guidance: dict[str, str]
    can_mutate: bool
    runner: str
    runner_config: dict[str, object]
    session_id: Optional[str]
    model: Optional[str]
    reasoning_effort: Optional[str]
    previous_session_ids: tuple[str, ...]
    reminder_turn_count: int
    updated_at: str


@dataclass(frozen=True)
class MamsInvokerConfig:
    baseline: Optional[str]
    working_style: Optional[str]
    extra_context: Optional[str]
    stage_guidance: dict[str, str]
    can_mutate: bool


@dataclass(frozen=True)
class MamsSkillConfig:
    version: int
    mams_invoker: MamsInvokerConfig
    shared_stages: dict[str, str]
    mams_channels: list[MamsChannelConfig]
    updated_at: str


def normalize_optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


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


def normalize_stage_key(key: str) -> str:
    return LEGACY_STAGE_KEY_MAP.get(key, key)


def normalize_stage_guidance_map(value: object, *, field_name: str) -> dict[str, str]:
    result = normalize_string_map(value, field_name=field_name)
    normalized: dict[str, str] = {}
    for key, stage_text in result.items():
        normalized[normalize_stage_key(key)] = stage_text
    return normalized


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
    description: Optional[str] = None,
    focus: Optional[str] = None,
    baseline: Optional[str] = None,
    extra_context: Optional[str] = None,
    stage_guidance: Optional[dict[str, str]] = None,
    can_mutate: bool = True,
    runner: str = RUNNER_CODEX,
    runner_config: Optional[dict[str, object]] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    previous_session_ids: tuple[str, ...] = (),
    reminder_turn_count: int = 0,
) -> MamsChannelConfig:
    normalized_name = normalize_optional_string(name)
    if not normalized_name:
        raise ValueError("MAMS channel name must be a non-empty string.")
    normalized_description = normalize_optional_string(description) or default_mams_channel_description(
        normalized_name
    )
    return MamsChannelConfig(
        name=normalized_name,
        description=normalized_description,
        focus=normalize_optional_string(focus),
        baseline=normalize_optional_string(baseline),
        extra_context=normalize_optional_string(extra_context),
        stage_guidance=dict(stage_guidance or {}),
        can_mutate=bool(can_mutate),
        runner=normalize_runner(runner, field_name=f"mams_channels[{normalized_name}].runner"),
        runner_config=normalize_runner_config(runner_config, field_name=f"mams_channels[{normalized_name}].runner_config"),
        session_id=normalize_optional_string(session_id),
        model=normalize_optional_string(model),
        reasoning_effort=normalize_optional_string(reasoning_effort),
        previous_session_ids=normalize_previous_session_ids(list(previous_session_ids)),
        reminder_turn_count=max(0, int(reminder_turn_count)),
        updated_at=iso_now(),
    )


def parse_mams_channel_config(obj: object) -> MamsChannelConfig:
    if not isinstance(obj, dict):
        raise ValueError("Each mams_channel entry must be a JSON object.")
    name = normalize_optional_string(obj.get("name"))
    if not name:
        raise ValueError("Each mams_channel entry requires a non-empty string field: name.")
    description = normalize_optional_string(obj.get("description")) or default_mams_channel_description(name)
    updated_at = normalize_optional_string(obj.get("updated_at")) or iso_now()
    raw_can_mutate = obj.get("can_mutate", True)
    if not isinstance(raw_can_mutate, bool):
        raise ValueError(f"mams_channels[{name}].can_mutate must be a boolean when provided.")
    return MamsChannelConfig(
        name=name,
        description=description,
        focus=normalize_optional_string(obj.get("focus")),
        baseline=normalize_optional_string(obj.get("baseline")),
        extra_context=normalize_optional_string(obj.get("extra_context")),
        stage_guidance=normalize_stage_guidance_map(obj.get("stage_guidance"), field_name=f"mams_channels[{name}].stage_guidance"),
        can_mutate=raw_can_mutate,
        runner=normalize_runner(obj.get("runner"), field_name=f"mams_channels[{name}].runner"),
        runner_config=normalize_runner_config(obj.get("runner_config"), field_name=f"mams_channels[{name}].runner_config"),
        session_id=normalize_optional_string(obj.get("session_id")),
        model=normalize_optional_string(obj.get("model")),
        reasoning_effort=normalize_optional_string(obj.get("reasoning_effort")),
        previous_session_ids=normalize_previous_session_ids(obj.get("previous_session_ids")),
        reminder_turn_count=max(0, int(obj.get("reminder_turn_count", 0) or 0)),
        updated_at=updated_at,
    )


def mams_channel_config_to_json(mams_channel: MamsChannelConfig) -> dict[str, object]:
    return {
        "name": mams_channel.name,
        "description": mams_channel.description,
        "focus": mams_channel.focus,
        "baseline": mams_channel.baseline,
        "extra_context": mams_channel.extra_context,
        "stage_guidance": mams_channel.stage_guidance,
        "can_mutate": mams_channel.can_mutate,
        "runner": mams_channel.runner,
        "runner_config": mams_channel.runner_config,
        "session_id": mams_channel.session_id,
        "model": mams_channel.model,
        "reasoning_effort": mams_channel.reasoning_effort,
        "previous_session_ids": list(mams_channel.previous_session_ids),
        "reminder_turn_count": mams_channel.reminder_turn_count,
        "updated_at": mams_channel.updated_at,
    }


def default_mams_invoker_config() -> MamsInvokerConfig:
    return MamsInvokerConfig(
        baseline=None,
        working_style=None,
        extra_context=None,
        stage_guidance={},
        can_mutate=True,
    )


def default_mams_skill_config(mams_channels: Optional[list[MamsChannelConfig]] = None) -> MamsSkillConfig:
    return MamsSkillConfig(
        version=CONFIG_VERSION,
        mams_invoker=default_mams_invoker_config(),
        shared_stages={},
        mams_channels=list(mams_channels or []),
        updated_at=iso_now(),
    )


def parse_mams_invoker_config(obj: object) -> MamsInvokerConfig:
    if obj is None:
        return default_mams_invoker_config()
    if not isinstance(obj, dict):
        raise ValueError("mams_invoker must be a JSON object when provided.")
    raw_can_mutate = obj.get("can_mutate", True)
    if not isinstance(raw_can_mutate, bool):
        raise ValueError("mams_invoker.can_mutate must be a boolean when provided.")
    return MamsInvokerConfig(
        baseline=normalize_optional_string(obj.get("baseline")),
        working_style=normalize_optional_string(obj.get("working_style")),
        extra_context=normalize_optional_string(obj.get("extra_context")),
        stage_guidance=normalize_stage_guidance_map(obj.get("stage_guidance"), field_name="mams_invoker.stage_guidance"),
        can_mutate=raw_can_mutate,
    )


def mams_invoker_config_to_json(config: MamsInvokerConfig) -> dict[str, object]:
    return {
        "baseline": config.baseline,
        "working_style": config.working_style,
        "extra_context": config.extra_context,
        "stage_guidance": config.stage_guidance,
        "can_mutate": config.can_mutate,
    }


def parse_skill_config_object(obj: object, *, path: Path) -> MamsSkillConfig:
    if not isinstance(obj, dict):
        raise RuntimeError(f"MAMS channel config file must contain a JSON object or legacy JSON array: {path}")
    mams_channels_value = obj.get("mams_channels", obj.get("channels", obj.get("agents")))
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
    try:
        shared_stages = normalize_stage_guidance_map(obj.get("shared_stages"), field_name="shared_stages")
        mams_invoker_source = obj.get("mams_invoker", obj.get("invoker", obj.get("caller", obj.get("claude"))))
        mams_invoker = parse_mams_invoker_config(mams_invoker_source)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    version = obj.get("version")
    if isinstance(version, int):
        normalized_version = version
    else:
        normalized_version = CONFIG_VERSION
    updated_at = normalize_optional_string(obj.get("updated_at")) or iso_now()
    return MamsSkillConfig(
        version=normalized_version,
        mams_invoker=mams_invoker,
        shared_stages=shared_stages,
        mams_channels=mams_channels,
        updated_at=updated_at,
    )


def skill_config_to_json(config: MamsSkillConfig) -> dict[str, object]:
    return {
        "version": config.version,
        "mams_invoker": mams_invoker_config_to_json(config.mams_invoker),
        "shared_stages": config.shared_stages,
        "mams_channels": [mams_channel_config_to_json(mams_channel) for mams_channel in config.mams_channels],
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
    if isinstance(data, list):
        mams_channels = []
        seen: set[str] = set()
        for raw in data:
            mams_channel = parse_mams_channel_config(raw)
            if mams_channel.name in seen:
                raise RuntimeError(f"Duplicate mams_channel name in {path}: {mams_channel.name}")
            seen.add(mams_channel.name)
            mams_channels.append(mams_channel)
        return default_mams_skill_config(mams_channels)
    return parse_skill_config_object(data, path=path)


def write_skill_config(repo_root: Path, config: MamsSkillConfig) -> None:
    path = mams_channels_file_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = skill_config_to_json(config)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_legacy_session_id(repo_root: Path) -> Optional[str]:
    path = legacy_session_file_path(repo_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            sid = data.get("session_id")
            if isinstance(sid, str) and sid.strip():
                return sid.strip()
    except Exception:
        return None
    return None


def read_legacy_session_history(repo_root: Path) -> tuple[str, ...]:
    path = legacy_session_history_file_path(repo_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ()
    if not isinstance(data, dict):
        return ()
    return normalize_previous_session_ids(data.get("previous_session_ids"))


@dataclass(frozen=True)
class MigrationSource:
    kind: str
    path: Optional[Path]
    config: MamsSkillConfig
    detail: str


def structured_config_needs_migration(raw_obj: dict[str, object]) -> bool:
    if any(legacy_key in raw_obj for legacy_key in ("claude", "caller", "invoker", "channels", "agents")):
        return True
    version = raw_obj.get("version")
    if not isinstance(version, int) or version < CONFIG_VERSION:
        return True
    if "work_modes" in raw_obj:
        return True
    mams_invoker = raw_obj.get("mams_invoker")
    if not isinstance(mams_invoker, dict) or "can_mutate" not in mams_invoker:
        return True
    mams_channels = raw_obj.get("mams_channels")
    if isinstance(mams_channels, list):
        for raw_mams_channel in mams_channels:
            if not isinstance(raw_mams_channel, dict) or "can_mutate" not in raw_mams_channel:
                return True
        return False
    return False


def load_migration_source(
    repo_root: Path,
    *,
    default_model: Optional[str],
    default_reasoning_effort: Optional[str],
) -> Optional[MigrationSource]:
    config_path = mams_channels_file_path(repo_root)

    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid mams_channel config JSON in {config_path}: {exc.msg}") from exc
        if isinstance(data, dict):
            if not structured_config_needs_migration(data):
                return None
            return MigrationSource(
                kind="current-structured",
                path=config_path,
                config=replace(parse_skill_config_object(data, path=config_path), version=CONFIG_VERSION, updated_at=iso_now()),
                detail="existing structured config needed normalization",
            )
        if isinstance(data, list):
            return MigrationSource(
                kind="current-array",
                path=config_path,
                config=default_mams_skill_config([parse_mams_channel_config(item) for item in data]),
                detail="legacy array-based config needed normalization",
            )
        raise RuntimeError(f"MAMS channel config file must contain a JSON object or legacy JSON array: {config_path}")

    for legacy_config_path in iter_legacy_structured_config_paths(repo_root):
        if not legacy_config_path.exists():
            continue
        try:
            data = json.loads(legacy_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid mams_channel config JSON in {legacy_config_path}: {exc.msg}") from exc
        if isinstance(data, dict):
            return MigrationSource(
                kind="legacy-structured",
                path=legacy_config_path,
                config=replace(parse_skill_config_object(data, path=legacy_config_path), version=CONFIG_VERSION, updated_at=iso_now()),
                detail="legacy structured config from the old directory",
            )
        if isinstance(data, list):
            return MigrationSource(
                kind="legacy-array",
                path=legacy_config_path,
                config=default_mams_skill_config([parse_mams_channel_config(item) for item in data]),
                detail="legacy array-based config from the old directory",
            )
        raise RuntimeError(f"MAMS channel config file must contain a JSON object or legacy JSON array: {legacy_config_path}")

    legacy_session_id = read_legacy_session_id(repo_root)
    legacy_history = read_legacy_session_history(repo_root)
    if legacy_session_id is None and not legacy_history:
        return None

    migrated = build_mams_channel_config(
        DEFAULT_MAMS_CHANNEL_NAME,
        description=MIGRATED_MAMS_CHANNEL_DESCRIPTION,
        session_id=legacy_session_id,
        model=default_model,
        reasoning_effort=default_reasoning_effort,
        previous_session_ids=legacy_history,
    )
    return MigrationSource(
        kind="legacy-session",
        path=legacy_session_file_path(repo_root),
        config=default_mams_skill_config([migrated]),
        detail="legacy single-session continuity files",
    )


def migrate_mams_channels_config_to_latest(
    repo_root: Path,
    *,
    default_model: Optional[str],
    default_reasoning_effort: Optional[str],
) -> Optional[str]:
    source = load_migration_source(
        repo_root,
        default_model=default_model,
        default_reasoning_effort=default_reasoning_effort,
    )
    if source is None:
        return None
    write_skill_config(repo_root, source.config)
    destination = mams_channels_file_path(repo_root)
    if source.kind == "legacy-session":
        return (
            "Legacy session continuity files were read, normalized, and rewritten into the canonical config at "
            f"{destination}."
        )
    if source.path is not None and source.path != destination:
        return (
            f"Legacy config at {source.path} was read, normalized, and rewritten into the canonical config at {destination}. "
            "User-authored reminder text was left unchanged."
        )
    return (
        f"Config at {destination} was normalized and rewritten into the canonical version {CONFIG_VERSION} format. "
        "User-authored reminder text was left unchanged."
    )


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


def merge_string_map(
    current: dict[str, str],
    patch: Optional[dict[str, Optional[str]]],
) -> dict[str, str]:
    updated = dict(current)
    if not patch:
        return updated
    for key, value in patch.items():
        if value is None:
            updated.pop(key, None)
        else:
            updated[key] = value
    return updated


def apply_configure_payload(
    config: MamsSkillConfig,
    payload: ConfigurePayload,
) -> MamsSkillConfig:
    mams_invoker = config.mams_invoker
    if payload.mams_invoker_patch is not None:
        stage_patch = payload.mams_invoker_patch.get("stage_guidance")
        mams_invoker = MamsInvokerConfig(
            baseline=payload.mams_invoker_patch["baseline"] if "baseline" in payload.mams_invoker_patch else mams_invoker.baseline,
            working_style=payload.mams_invoker_patch["working_style"] if "working_style" in payload.mams_invoker_patch else mams_invoker.working_style,
            extra_context=payload.mams_invoker_patch["extra_context"] if "extra_context" in payload.mams_invoker_patch else mams_invoker.extra_context,
            stage_guidance=merge_string_map(
                mams_invoker.stage_guidance,
                stage_patch if isinstance(stage_patch, dict) else None,
            ),
            can_mutate=payload.mams_invoker_patch["can_mutate"] if "can_mutate" in payload.mams_invoker_patch else mams_invoker.can_mutate,
        )

    shared_stages = merge_string_map(config.shared_stages, payload.shared_stages_patch)

    mams_channels = list(config.mams_channels)
    if payload.mams_channels_patch:
        for patch in payload.mams_channels_patch:
            name = patch["name"]
            existing = find_mams_channel(mams_channels, name)
            if existing is None:
                updated_mams_channel = build_mams_channel_config(
                    name,
                    description=patch.get("description"),
                    focus=patch.get("focus"),
                    baseline=patch.get("baseline"),
                    extra_context=patch.get("extra_context"),
                    stage_guidance=merge_string_map({}, patch.get("stage_guidance") if isinstance(patch.get("stage_guidance"), dict) else None),
                    can_mutate=patch.get("can_mutate", True),
                    model=patch.get("model"),
                    reasoning_effort=patch.get("reasoning_effort"),
                )
            else:
                updated_mams_channel = build_mams_channel_config(
                    name,
                    description=patch.get("description") if "description" in patch else existing.description,
                    focus=patch.get("focus") if "focus" in patch else existing.focus,
                    baseline=patch.get("baseline") if "baseline" in patch else existing.baseline,
                    extra_context=patch.get("extra_context") if "extra_context" in patch else existing.extra_context,
                    stage_guidance=merge_string_map(
                        existing.stage_guidance,
                        patch.get("stage_guidance") if isinstance(patch.get("stage_guidance"), dict) else None,
                    ),
                    can_mutate=patch.get("can_mutate") if "can_mutate" in patch else existing.can_mutate,
                    session_id=existing.session_id,
                    model=patch.get("model") if "model" in patch else existing.model,
                    reasoning_effort=patch.get("reasoning_effort") if "reasoning_effort" in patch else existing.reasoning_effort,
                    previous_session_ids=existing.previous_session_ids,
                )
            mams_channels = upsert_mams_channel(mams_channels, updated_mams_channel)

    return MamsSkillConfig(
        version=CONFIG_VERSION,
        mams_invoker=mams_invoker,
        shared_stages=shared_stages,
        mams_channels=mams_channels,
        updated_at=iso_now(),
    )


@dataclass(frozen=True)
class InitPayload:
    mode: str
    background: str


@dataclass(frozen=True)
class ReviewThisPlanPayload:
    plan_for_review: str
    new_information: Optional[str]
    fresh_user_message: Optional[str]


@dataclass(frozen=True)
class SyncPayload:
    sync_message: str
    fresh_user_message: Optional[str]


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
    mams_invoker_patch: Optional[dict[str, object]]
    shared_stages_patch: Optional[dict[str, Optional[str]]]
    mams_channels_patch: Optional[list[dict[str, object]]]


@dataclass(frozen=True)
class InvokeRequest:
    command: str
    mams_channel_name: Optional[str]
    stdin_text: str


@dataclass(frozen=True)
class InvokePayload:
    requests: tuple[InvokeRequest, ...]


def validate_update_config_input(stdin_text: str) -> None:
    if stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip():
        raise ValueError("update-config does not accept input. Run it with empty stdin.")


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


def parse_init_payload(stdin_text: str) -> InitPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError(
            "Init input is empty. Provide JSON with exactly one of: task_background or "
            "recovery_background."
        )

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Init input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("Init input must be a JSON object.")

    allowed_keys = {
        INIT_TASK_FIELD,
        INIT_RECOVERY_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"Init input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    background_keys = [key for key in (INIT_TASK_FIELD, INIT_RECOVERY_FIELD) if key in obj]
    if len(background_keys) != 1:
        raise ValueError("Init input must contain exactly one of: task_background or recovery_background.")

    if INIT_TASK_FIELD in obj:
        value = obj[INIT_TASK_FIELD]
        mode = "task"
    else:
        value = obj[INIT_RECOVERY_FIELD]
        mode = "recovery"

    if not isinstance(value, str) or not value.strip():
        raise ValueError("Init background must be a non-empty string.")

    return InitPayload(
        mode=mode,
        background=value.strip(),
    )


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

    allowed_keys = {SYNC_MESSAGE_FIELD, SYNC_FRESH_USER_FIELD}
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

    return SyncPayload(
        sync_message=sync_message.strip(),
        fresh_user_message=fresh_user_message,
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


def parse_nullable_string_patch_map(value: object, *, field_name: str) -> dict[str, Optional[str]]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    result: dict[str, Optional[str]] = {}
    for raw_key, raw_value in value.items():
        key = normalize_optional_string(raw_key)
        if not key:
            raise ValueError(f"{field_name} contains an empty key.")
        if raw_value is None:
            result[key] = None
            continue
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"{field_name}.{key} must be a non-empty string or null.")
        result[key] = raw_value.strip()
    return result


def parse_configure_payload(stdin_text: str) -> ConfigurePayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError(
            "configure input is empty. Provide JSON with at least one of: mams_invoker, shared_stages, mams_channels."
        )
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"configure input must be valid JSON: {exc.msg}") from exc
    if not isinstance(obj, dict):
        raise ValueError("configure input must be a JSON object.")

    allowed_keys = {
        CONFIGURE_MAMS_INVOKER_FIELD,
        CONFIGURE_SHARED_STAGES_FIELD,
        CONFIGURE_MAMS_CHANNELS_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"configure input has unsupported fields: {', '.join(sorted(unknown_keys))}")
    if not obj:
        raise ValueError(
            "configure input must contain at least one of: mams_invoker, shared_stages, mams_channels."
        )

    mams_invoker_patch = obj.get(CONFIGURE_MAMS_INVOKER_FIELD)
    if mams_invoker_patch is not None:
        if not isinstance(mams_invoker_patch, dict):
            raise ValueError("configure field mams_invoker must be a JSON object.")
        allowed_mams_invoker_keys = {"baseline", "working_style", "extra_context", "stage_guidance", "can_mutate"}
        unknown_mams_invoker_keys = set(mams_invoker_patch.keys()) - allowed_mams_invoker_keys
        if unknown_mams_invoker_keys:
            raise ValueError(
                "configure.mams_invoker has unsupported fields: "
                + ", ".join(sorted(unknown_mams_invoker_keys))
            )
        if "stage_guidance" in mams_invoker_patch and mams_invoker_patch["stage_guidance"] is not None:
            mams_invoker_patch = dict(mams_invoker_patch)
            mams_invoker_patch["stage_guidance"] = parse_nullable_string_patch_map(
                mams_invoker_patch["stage_guidance"],
                field_name="configure.mams_invoker.stage_guidance",
            )
        for field in ("baseline", "working_style", "extra_context"):
            if field in mams_invoker_patch:
                value = mams_invoker_patch[field]
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    raise ValueError(f"configure.mams_invoker.{field} must be a non-empty string or null.")
                if isinstance(value, str):
                    mams_invoker_patch[field] = value.strip()
        if "can_mutate" in mams_invoker_patch and not isinstance(mams_invoker_patch["can_mutate"], bool):
            raise ValueError("configure.mams_invoker.can_mutate must be a boolean when provided.")

    shared_stages_patch = obj.get(CONFIGURE_SHARED_STAGES_FIELD)
    if shared_stages_patch is not None:
        shared_stages_patch = parse_nullable_string_patch_map(
            shared_stages_patch,
            field_name="configure.shared_stages",
        )

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
                "description",
                "focus",
                "baseline",
                "extra_context",
                "stage_guidance",
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
            for field in ("description", "focus", "baseline", "extra_context", "model", "reasoning_effort", "runner"):
                if field in normalized_mams_channel:
                    value = normalized_mams_channel[field]
                    if value is not None and (not isinstance(value, str) or not value.strip()):
                        raise ValueError(
                            f"configure.mams_channels[{index}].{field} must be a non-empty string or null."
                        )
                    if isinstance(value, str):
                        normalized_mams_channel[field] = value.strip()
            if "stage_guidance" in normalized_mams_channel and normalized_mams_channel["stage_guidance"] is not None:
                normalized_mams_channel["stage_guidance"] = parse_nullable_string_patch_map(
                    normalized_mams_channel["stage_guidance"],
                    field_name=f"configure.mams_channels[{index}].stage_guidance",
                )
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
            if "can_mutate" in normalized_mams_channel and not isinstance(normalized_mams_channel["can_mutate"], bool):
                raise ValueError(f"configure.mams_channels[{index}].can_mutate must be a boolean when provided.")
            mams_channels_patch.append(normalized_mams_channel)

    return ConfigurePayload(
        mams_invoker_patch=mams_invoker_patch,
        shared_stages_patch=shared_stages_patch,
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
        "If compaction, context clear, session replacement, or continuity loss means you cannot confidently identify the referenced source and its relevant content, you must re-read the referenced material before relying on it.",
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


def build_mams_reminder_text_for_channel(
    tool: str,
    *,
    full: bool,
    prompt_text: str,
) -> str:
    if full or tool == "init":
        return prompt_text.strip()

    brief_map = {
        "sync": (
            "Persistent collaboration turn with the mams_invoker, not the end user. "
            "Sync only; discussion, coordination, disagreement handling, and review relay are allowed, but mutation is not. "
            "The configured User Reminder still applies in full. "
            "Return ## Discussion Reply, and add ## Plan only when a candidate plan is genuinely ready. "
            "Compare evidence, surface disagreement clearly, and only ask the mams_invoker to escalate to the user "
            "if a real unresolved disagreement between you and the mams_invoker has persisted for about 10 turns."
        ),
        "review-this-plan": (
            "Hard gate. Review the plan before any mutation, do not mutate in this turn, and judge from facts and whole-system coherence. "
            "The configured User Reminder still applies in full. "
            "The first non-empty line must be approved_to_mutate: true or approved_to_mutate: false, followed by ## Plan Review Reply. "
            "Do not ask for user input unless a real unresolved disagreement between you and the mams_invoker has persisted for about 10 turns."
        ),
        "review-this-work": (
            "Hard gate. Review the actual work, not intent; do not mutate in this turn. "
            "The configured User Reminder still applies in full. "
            "The first non-empty line must be approved_work: true or approved_work: false, followed by ## Work Review Reply. "
            "Do not ask for user input unless a real unresolved disagreement between you and the mams_invoker has persisted for about 10 turns."
        ),
        "execute-this-plan": (
            "The configured User Reminder still applies in full. "
            "Execution turn for a mutate-capable mams_channel. Execute the approved plan as a substantial unit, do not stop for trivial progress, and only stop when the approved plan is complete or a real blocker prevents safe continuation. "
            "Do not widen scope and do not ask the user directly."
        ),
        "execute-this-plan-part": (
            "The configured User Reminder still applies in full. "
            "Execution turn for a mutate-capable mams_channel. Use a plan part only when the full plan is genuinely too large; a plan part must still be a substantial coherent chunk, not a trivial fragment. "
            "Do not stop for incidental small edits. Stop only when the approved plan part is complete or a real blocker prevents safe continuation."
        ),
    }
    return brief_map.get(tool, prompt_text.strip())


def build_mams_reminder_text_for_invoker(tool: str, *, full: bool) -> str:
    full_map = {
        "init": (
            "Run init on every new shared task and after compact/context clear when you need to re-bootstrap shared context. "
            "Init is collaboration bootstrap only. It is not discussion and not mutation."
        ),
        "invoke": (
            "Use invoke as the preferred wrapper when coordinating one or more mams_channels. "
            "Let invoke block until every requested call settles; do not wrap these calls in external polling or repeated status checks."
        ),
        "sync": (
            "This is the general sync turn. Use it for discussion, coordination, disagreement handling, plan repair, and relaying review outcomes. "
            "Keep pushing for real consensus, and do not stop for user input unless a real unresolved mams_invoker/channel disagreement has persisted for about 10 turns."
        ),
        "review-this-plan": (
            "This is the hard gate before execution begins. Submit a concrete plan, require direct fact-checking, and do not treat mere discussion as approval. "
            "Do not ask the user just because execution feels uncertain; escalate only when a real unresolved mams_invoker/channel disagreement has persisted for about 10 turns."
        ),
        "review-this-work": (
            "This is the hard gate before delivery. Review actual work, evidence, and coherence. "
            "approved_work: true accepts only the reviewed execution scope, not automatically the whole larger plan; if more agreed scopes remain, continue directly instead of stopping. "
            "Do not ask the user just because next execution steps are undecided; escalate only when a real unresolved mams_invoker/channel disagreement has persisted for about 10 turns."
        ),
        "execute-this-plan": (
            "This is the execution turn for a whole approved plan. Do not fragment execution into trivial pieces. Finish the approved plan unless a real blocker or invalidated premise forces a stop. "
            "Escalate to the user only for a real unresolved mams_invoker/channel disagreement that has persisted for about 10 turns."
        ),
        "execute-this-plan-part": (
            "This is the execution turn for one approved plan part. Use a plan part only when the full plan is genuinely too large, and require the approved part to be a substantial coherent chunk rather than a tiny fragment. "
            "Do not ask the user about whether to continue execution unless a real unresolved mams_invoker/channel disagreement has persisted for about 10 turns."
        ),
        "configure": (
            "This command applies a mams_invoker-supplied config patch. It does not mutate task files and it does not replace session continuity by itself."
        ),
        "update-config": (
            "This command normalizes managed state into the canonical Mad Agent Mesh config. It does not mutate task files and it does not replace session continuity by itself."
        ),
        "dangerous-new-session": (
            "This command is for destructive continuity replacement. Use it only when the user explicitly authorizes abandoning or switching the managed session continuity."
        ),
    }
    brief_map = {
        "init": "Init re-establishes the collaboration baseline. Use full reminders here.",
        "invoke": "Preferred blocking wrapper for one or more mams_channel calls. Let invoke wait once and return settled results; do not externally poll.",
        "sync": "General sync only. No mutation permission. Full Mad Agent Mesh reminder still applies, and the configured User Reminder still applies in full. Ask the user only for a real unresolved disagreement that persists for about 10 turns.",
        "review-this-plan": "Hard gate before execution. Full Mad Agent Mesh reminder still applies, and the configured User Reminder still applies in full. Ask the user only for a real unresolved disagreement that persists for about 10 turns.",
        "review-this-work": "Hard gate before accepted delivery. approved_work: true accepts only the reviewed execution scope; continue if more agreed scopes remain. Full Mad Agent Mesh reminder still applies, and the configured User Reminder still applies in full. Ask the user only for a real unresolved disagreement that persists for about 10 turns.",
        "execute-this-plan": "Execute the approved plan as a substantial whole. Do not stop for trivial progress. Full Mad Agent Mesh reminder still applies, and the configured User Reminder still applies in full.",
        "execute-this-plan-part": "Execute only the approved plan part, and only use plan-part mode for genuinely large plans. The approved part must still be substantial. Full Mad Agent Mesh reminder still applies, and the configured User Reminder still applies in full.",
        "configure": "MAMS invoker-supplied config patch only. Full Mad Agent Mesh reminder still applies.",
        "update-config": "Config update only. Full Mad Agent Mesh reminder still applies.",
        "dangerous-new-session": "Destructive continuity replacement. Full Mad Agent Mesh reminder still applies.",
    }
    return (full_map if full else brief_map).get(tool, "")


def collaborative_turn_index(tool: str, mams_channel: MamsChannelConfig) -> int:
    if tool == "init":
        return 0
    if tool in {"sync", "review-this-plan", "review-this-work", "execute-this-plan", "execute-this-plan-part"}:
        return mams_channel.reminder_turn_count + 1
    return 0


def should_use_full_reminder(tool: str, turn_index: int) -> bool:
    if tool in {"init", "configure", "update-config", "dangerous-new-session"}:
        return True
    if turn_index <= 0:
        return True
    return (turn_index - 1) % 3 == 0


def build_common_stage_items(
    config: MamsSkillConfig,
    *,
    tool: str,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    stage_name = tool

    shared_stage_text = config.shared_stages.get(stage_name)
    if shared_stage_text:
        items.append(("Shared Stage Guidance", shared_stage_text))

    return items


def build_mams_invoker_user_items(
    config: MamsSkillConfig,
    *,
    tool: str,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    stage_name = tool

    if config.mams_invoker.baseline:
        items.append(("MAMS Invoker Baseline", config.mams_invoker.baseline))
    if config.mams_invoker.working_style:
        items.append(("MAMS Invoker Working Style", config.mams_invoker.working_style))
    if config.mams_invoker.extra_context:
        items.append(("MAMS Invoker Extra Context", config.mams_invoker.extra_context))
    items.append(
        (
            "MAMS Invoker Mutation Permission",
            (
                "The mams_invoker is allowed to mutate directly when appropriate."
                if config.mams_invoker.can_mutate
                else "The mams_invoker is not allowed to mutate directly and must route implementation through a mutate-capable mams_channel."
            ),
        )
    )

    mams_invoker_stage_text = config.mams_invoker.stage_guidance.get(stage_name)
    if mams_invoker_stage_text:
        items.append(("MAMS Invoker Stage Guidance", mams_invoker_stage_text))

    return items


def build_mams_channel_user_items(
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    *,
    tool: str,
) -> list[tuple[str, str]]:
    stage_name = tool
    items: list[tuple[str, str]] = []

    if mams_channel.description and mams_channel.description != default_mams_channel_description(mams_channel.name):
        items.append(("MAMS Channel Description", mams_channel.description))
    if mams_channel.focus:
        items.append(("MAMS Channel Focus", mams_channel.focus))
    if mams_channel.baseline:
        items.append(("MAMS Channel Baseline", mams_channel.baseline))
    if mams_channel.extra_context:
        items.append(("MAMS Channel Extra Context", mams_channel.extra_context))
    items.append(
        (
            "MAMS Channel Mutation Permission",
            (
                "This mams_channel may mutate when the workflow explicitly reaches the mutation entrypoint."
                if mams_channel.can_mutate
                else "This mams_channel must not mutate files. It may discuss, review, or plan, but implementation must be routed elsewhere."
            ),
        )
    )

    mams_channel_stage_text = mams_channel.stage_guidance.get(stage_name)
    if mams_channel_stage_text:
        items.append(("MAMS Channel Stage Guidance", mams_channel_stage_text))

    return items


def compose_prompt(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    *,
    tool: str,
    full_reminder: bool,
    base_parts: list[str],
) -> str:
    if not base_parts:
        raise RuntimeError("compose_prompt requires at least one base part.")
    common_items = build_common_stage_items(config, tool=tool)
    agent_items = build_mams_channel_user_items(config, mams_channel, tool=tool)
    skill_reminder = build_mams_reminder_text_for_channel(
        tool,
        full=full_reminder,
        prompt_text=base_parts[0],
    )
    skill_body_parts = [skill_reminder]
    common_body = render_named_items(common_items)
    if common_body:
        skill_body_parts.append(common_body)
    skill_block = wrap_tagged_block(
        "MAMS_REMINDER_FULL" if full_reminder else "MAMS_REMINDER_BRIEF",
        "## Mad Agent Mesh Reminder ({})\n\n{}".format(
            "Full" if full_reminder else "Brief",
            "\n\n".join(part for part in skill_body_parts if part).strip(),
        ),
    )

    user_body = render_named_items(agent_items)
    user_block = ""
    if user_body:
        user_block = wrap_tagged_block(
            "USER_REMINDER",
            "## User Reminder\n\n{}".format(user_body),
        )

    ref_notice_sections = build_reference_notice(repo_root, [skill_block, user_block, *base_parts[1:]])
    prompt_parts = [skill_block, *ref_notice_sections]
    if user_block:
        prompt_parts.append(user_block)
    prompt_parts.extend(base_parts[1:])
    return "\n\n".join(part for part in prompt_parts if part).strip() + "\n"


def format_output_for_mams_invoker(
    repo_root: Path,
    config: MamsSkillConfig,
    *,
    tool: str,
    full_reminder: bool,
    reply: str,
    migration_notice: Optional[str],
) -> str:
    normalized_reply = reply.rstrip()
    common_items = build_common_stage_items(config, tool=tool)
    mams_invoker_items = build_mams_invoker_user_items(config, tool=tool)
    skill_body_parts = [build_mams_reminder_text_for_invoker(tool, full=full_reminder)]
    common_body = render_named_items(common_items)
    if common_body:
        skill_body_parts.append(common_body)
    skill_block = wrap_tagged_block(
        "MAMS_REMINDER_FULL" if full_reminder else "MAMS_REMINDER_BRIEF",
        "## Mad Agent Mesh Reminder ({})\n\n{}".format(
            "Full" if full_reminder else "Brief",
            "\n\n".join(part for part in skill_body_parts if part).strip(),
        ),
    )

    user_body = render_named_items(mams_invoker_items)
    user_block = ""
    if user_body:
        user_block = wrap_tagged_block(
            "USER_REMINDER",
            "## User Reminder\n\n{}".format(user_body),
        )

    ref_notice_sections = build_reference_notice(repo_root, [skill_block, user_block])

    if not skill_block and not user_block and not ref_notice_sections:
        return append_migration_notice(normalized_reply, migration_notice)

    parts = [
        skill_block,
        *ref_notice_sections,
        user_block,
        wrap_tagged_block("CHANNEL_REPLY", f"## Channel Reply\n\n{normalized_reply}"),
    ]
    return append_migration_notice("\n\n".join(part for part in parts if part), migration_notice)


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
        result_body = "\n".join(
            [
                f"## {item.request.mams_channel_name or DEFAULT_MAMS_CHANNEL_NAME} · {item.request.command} · {item.status}",
                "",
                item.reply if item.status == "ok" and item.reply is not None else f"Error: {item.error}",
            ]
        ).strip()
        result_blocks.append(wrap_tagged_block("INVOKE_RESULT", result_body))
    return wrap_tagged_block(
        "INVOKE_SUMMARY",
        "\n\n".join(["\n".join(summary_body).strip(), *result_blocks]).strip(),
    )


def build_init_prompt(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
) -> tuple[str, str]:
    payload = parse_init_payload(stdin_text)
    if payload.mode == "task":
        prompt_name = "init-task.md"
        label = "Task background from the mams_invoker:"
    else:
        prompt_name = "init-recovery.md"
        label = "Recovery background from the mams_invoker:"

    prompt = compose_prompt(
        repo_root,
        config,
        mams_channel,
        tool="init",
        full_reminder=True,
        base_parts=[
            load_prompt_asset(prompt_name),
            build_labeled_content_block(
                "TASK_BACKGROUND" if payload.mode == "task" else "RECOVERY_BACKGROUND",
                label,
                payload.background,
            ),
        ],
    )

    return prompt, payload.mode


def build_review_this_plan_prompt(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    payload = parse_review_this_plan_payload(stdin_text)
    parts = [
        load_prompt_asset("review-this-plan.md"),
        build_labeled_content_block("PLAN_FOR_REVIEW", "Plan for review from the mams_invoker:", payload.plan_for_review),
    ]

    if payload.new_information:
        parts.extend(
            [
                build_labeled_content_block("NEW_INFORMATION", "New information from the mams_invoker:", payload.new_information),
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
        config,
        mams_channel,
        tool="review-this-plan",
        full_reminder=full_reminder,
        base_parts=parts,
    )


def build_sync_prompt(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    payload = parse_sync_payload(stdin_text)
    parts = [
        load_prompt_asset("sync.md"),
        build_labeled_content_block("SYNC_MESSAGE", "Sync message from the mams_invoker:", payload.sync_message),
    ]

    if payload.fresh_user_message:
        parts.extend(
            [
                wrap_tagged_block(USER_MESSAGE_VERBATIM_TAG, payload.fresh_user_message),
            ]
        )

    return compose_prompt(
        repo_root,
        config,
        mams_channel,
        tool="sync",
        full_reminder=full_reminder,
        base_parts=parts,
    )


def build_review_this_work_prompt(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    payload = parse_review_this_work_payload(stdin_text)
    parts = [
        load_prompt_asset("review-this-work.md"),
        build_labeled_content_block("WORK_FOR_REVIEW", "Work for review from the mams_invoker:", payload.work_for_review),
    ]

    if payload.new_information:
        parts.extend(
            [
                build_labeled_content_block("NEW_INFORMATION", "New information from the mams_invoker:", payload.new_information),
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
        config,
        mams_channel,
        tool="review-this-work",
        full_reminder=full_reminder,
        base_parts=parts,
    )


def build_execute_prompt(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
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
                else "danger-full-access (explicit full-access escalation approved by the mams_invoker)."
            ),
        ),
        build_labeled_content_block(
            "APPROVED_PLAN" if mode == "execute-this-plan" else "APPROVED_PLAN_PART",
            (
                "Approved plan from the mams_invoker:"
                if mode == "execute-this-plan"
                else "Approved plan part from the mams_invoker:"
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
        config,
        mams_channel,
        tool=mode,
        full_reminder=full_reminder,
        base_parts=parts,
    )


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


def validate_init_reply(mode: str, reply: str) -> str:
    expected_title = INIT_TASK_REPLY_TITLE if mode == "task" else INIT_RECOVERY_REPLY_TITLE
    return require_markdown_section(reply, expected_title)


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


def build_prompt(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    tool: str,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    if tool == "init":
        prompt, _mode = build_init_prompt(repo_root, config, mams_channel, stdin_text)
        return prompt
    if tool == "sync":
        return build_sync_prompt(repo_root, config, mams_channel, stdin_text, full_reminder=full_reminder)
    if tool == "review-this-plan":
        return build_review_this_plan_prompt(
            repo_root,
            config,
            mams_channel,
            stdin_text,
            full_reminder=full_reminder,
        )
    if tool == "review-this-work":
        return build_review_this_work_prompt(
            repo_root,
            config,
            mams_channel,
            stdin_text,
            full_reminder=full_reminder,
        )
    if tool in {"execute-this-plan", "execute-this-plan-part"}:
        return build_execute_prompt(
            repo_root,
            config,
            mams_channel,
            stdin_text,
            full_reminder=full_reminder,
            mode=tool,
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
class InvokeSettledResult:
    request: InvokeRequest
    status: str
    reply: Optional[str]
    error: Optional[str]
    updated_mams_channel: Optional[MamsChannelConfig]


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


def command_requires_stdin(command: str) -> bool:
    return command != "update-config"


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
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
    *,
    command: str,
    stdin_text: str,
    timeout_s: int,
    model: Optional[str],
    reasoning_effort: Optional[str],
    full_reminder: bool,
) -> tuple[str, MamsChannelConfig]:
    session_id = mams_channel.session_id
    init_mode: Optional[str] = None

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

    try:
        if command == "init":
            prompt, init_mode = build_init_prompt(repo_root, config, mams_channel, stdin_text)
        else:
            prompt = build_prompt(
                repo_root,
                config,
                mams_channel,
                command,
                stdin_text,
                full_reminder=full_reminder,
            )
        sandbox_mode = resolve_execution_sandbox(command, stdin_text)
        result = run_runner_for_mams_channel(
            repo_root=repo_root,
            mams_channel=mams_channel,
            session_id=session_id,
            prompt=prompt,
            sandbox_mode=sandbox_mode,
            timeout_s=timeout_s,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    except Exception as exc:
        if session_id and looks_like_missing_thread_error(str(exc)):
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

    updated_mams_channel = replace(
        mams_channel,
        session_id=result.session_id,
        model=mams_channel.model or model,
        reasoning_effort=mams_channel.reasoning_effort or reasoning_effort,
        reminder_turn_count=(
            0
            if command == "init"
            else mams_channel.reminder_turn_count + 1
            if command in {"sync", "review-this-plan", "review-this-work", "execute-this-plan", "execute-this-plan-part"}
            else mams_channel.reminder_turn_count
        ),
        updated_at=iso_now(),
    )

    if init_mode is not None:
        result.reply = validate_init_reply(init_mode, result.reply)
    elif command == "review-this-plan":
        result.reply = validate_review_this_plan_reply(result.reply)
    elif command == "review-this-work":
        result.reply = validate_review_this_work_reply(result.reply)
    elif command == "sync":
        result.reply = validate_sync_reply(result.reply)

    return result.reply, updated_mams_channel


def resolve_mams_channels_for_command(
    repo_root: Path,
    mams_channel_name: str,
    *,
    default_model: Optional[str],
    default_reasoning_effort: Optional[str],
) -> tuple[MamsSkillConfig, MamsChannelConfig, Optional[str]]:
    migration_notice = migrate_mams_channels_config_to_latest(
        repo_root,
        default_model=default_model,
        default_reasoning_effort=default_reasoning_effort,
    )
    config = read_skill_config(repo_root)
    mams_channel = find_mams_channel(config.mams_channels, mams_channel_name)
    if mams_channel is None:
        mams_channel = build_mams_channel_config(
            mams_channel_name,
            model=default_model,
            reasoning_effort=default_reasoning_effort,
        )
    return config, mams_channel, migration_notice


def resolve_config_for_update(
    repo_root: Path,
    *,
    default_model: Optional[str],
    default_reasoning_effort: Optional[str],
) -> tuple[MamsSkillConfig, Optional[str], bool]:
    migration_notice = migrate_mams_channels_config_to_latest(
        repo_root,
        default_model=default_model,
        default_reasoning_effort=default_reasoning_effort,
    )
    config_path = mams_channels_file_path(repo_root)
    created_canonical = False
    if config_path.exists():
        config = read_skill_config(repo_root)
    else:
        config = default_mams_skill_config([])
        write_skill_config(repo_root, config)
        created_canonical = True
    return config, migration_notice, created_canonical


def persist_mams_channels_for_command(
    repo_root: Path,
    config: MamsSkillConfig,
    mams_channel: MamsChannelConfig,
) -> None:
    write_skill_config(
        repo_root,
        MamsSkillConfig(
            version=CONFIG_VERSION,
            mams_invoker=config.mams_invoker,
            shared_stages=config.shared_stages,
            mams_channels=upsert_mams_channel(config.mams_channels, replace(mams_channel, updated_at=iso_now())),
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
        mams_invoker=config.mams_invoker,
        shared_stages=config.shared_stages,
        mams_channels=updated_channels,
        updated_at=iso_now(),
    )
    write_skill_config(repo_root, updated_config)
    return updated_config


def append_migration_notice(reply: str, migration_notice: Optional[str]) -> str:
    normalized = reply.rstrip()
    if not migration_notice:
        return normalized + "\n"
    return (
        f"{normalized}\n\n---\n"
        f"Migration notice: {migration_notice}\n"
        "Future calls now use the structured managed mams_channel config automatically.\n"
    )


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
    config, migration_notice, _created_canonical = resolve_config_for_update(
        repo_root,
        default_model=effective_default_model,
        default_reasoning_effort=effective_default_reasoning_effort,
    )

    prepared: list[tuple[InvokeRequest, MamsChannelConfig, bool, Optional[str], Optional[str]]] = []
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
        turn_index = collaborative_turn_index(request.command, mams_channel)
        full_reminder = should_use_full_reminder(request.command, turn_index)
        prepared.append(
            (
                replace(request, mams_channel_name=mams_channel_name),
                mams_channel,
                full_reminder,
                model,
                reasoning_effort,
            )
        )

    def perform(item: tuple[InvokeRequest, MamsChannelConfig, bool, Optional[str], Optional[str]]) -> InvokeSettledResult:
        request, mams_channel, full_reminder, model, reasoning_effort = item
        try:
            reply, updated_mams_channel = execute_command_for_mams_channel(
                repo_root,
                config,
                mams_channel,
                command=request.command,
                stdin_text=request.stdin_text,
                timeout_s=timeout_s,
                model=model,
                reasoning_effort=reasoning_effort,
                full_reminder=full_reminder,
            )
            return InvokeSettledResult(
                request=request,
                status="ok",
                reply=reply,
                error=None,
                updated_mams_channel=updated_mams_channel,
            )
        except Exception as exc:
            return InvokeSettledResult(
                request=request,
                status="error",
                reply=None,
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

    updated_channels = [item.updated_mams_channel for item in settled if item.updated_mams_channel is not None]
    updated_config = (
        persist_multiple_mams_channels(repo_root, config, updated_channels)
        if updated_channels
        else config
    )
    for updated_mams_channel in updated_channels:
        if updated_mams_channel.runner == RUNNER_CODEX:
            try_promote_exec_session_to_cli(updated_mams_channel.session_id)

    summary = format_invoke_summary(settled, execution_mode=execution_mode)
    return format_output_for_mams_invoker(
        repo_root,
        updated_config,
        tool="invoke",
        full_reminder=True,
        reply=summary,
        migration_notice=migration_notice,
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
    if repo_root is None:
        if cwd_explicit:
            chosen = start_cwd.expanduser().resolve()
            chosen_managed_dir = chosen / MANAGED_DIRNAME
            chosen_legacy_dir = chosen / LEGACY_MANAGED_DIRNAME
            if not is_global_managed_dir(chosen_managed_dir) and not is_global_managed_dir(chosen_legacy_dir):
                repo_root = chosen

    if repo_root is None:
        candidates = candidate_roots_with_managed_dir(start_cwd)
        lines = [
            "No project Mad Agent Mesh session root is configured.",
            "Could not find an existing managed session anchor:",
            f"  - <dir>/{MANAGED_DIRNAME}/{MAMS_CHANNELS_FILENAME}",
            f"  - <dir>/{LEGACY_MANAGED_DIRNAME}/{MAMS_CHANNELS_FILENAME} (legacy, auto-migrated once)",
            f"  - <dir>/{LEGACY_MANAGED_DIRNAME}/{LEGACY_SESSION_FILENAME} (legacy, auto-migrated once)",
            f"(excluding the global {MANAGED_GLOBAL_DIR} and {CLAUDE_GLOBAL_DIR} directories).",
            "",
            "Ask the user to choose a directory to store the managed session state for this workspace.",
        ]
        if candidates:
            lines.append(f"Candidate directories that already contain a {MANAGED_DIRNAME}/ or {LEGACY_MANAGED_DIRNAME}/ directory (closest first):")
            for c in candidates:
                lines.append(f"  - {c}")
            lines.append("Then rerun this command with: --cwd <chosen_dir>")
        else:
            lines.append(f"No {MANAGED_DIRNAME}/ or {LEGACY_MANAGED_DIRNAME}/ directory was found in parent directories (excluding the global ones).")
            lines.append("Ask the user to choose a directory, then rerun this command with: --cwd <chosen_dir>.")
        raise RuntimeError("\n".join(lines))

    stdin_text = sys.stdin.read()
    if args.cmd != "update-config" and not stdin_text.strip():
        eprint("Empty input. Provide content via stdin.")
        return 2

    effective_default_model = args.model or DEFAULT_MODEL
    effective_default_reasoning_effort = args.reasoning_effort or DEFAULT_REASONING_EFFORT

    if args.cmd == "configure":
        try:
            payload = parse_configure_payload(stdin_text)
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / MANAGED_DIRNAME).mkdir(parents=True, exist_ok=True)
            config, _mams_channel, migration_notice = resolve_mams_channels_for_command(
                repo_root,
                mams_channel_name,
                default_model=effective_default_model,
                default_reasoning_effort=effective_default_reasoning_effort,
            )
            updated_config = apply_configure_payload(config, payload)
            write_skill_config(repo_root, updated_config)
        except Exception as exc:
            eprint(str(exc))
            return 1

        lines = [
            "configure applied.",
            f"Target mams_channel: {mams_channel_name}",
            f"Config path: {mams_channels_file_path(repo_root)}",
        ]
        if payload.mams_invoker_patch is not None:
            lines.append("Updated: mams_invoker")
        if payload.shared_stages_patch is not None:
            lines.append("Updated: shared_stages")
        if payload.mams_channels_patch is not None:
            lines.append(
                "Updated mams_channels: " + ", ".join(patch["name"] for patch in payload.mams_channels_patch)
            )
        sys.stdout.write(
            format_output_for_mams_invoker(
                repo_root,
                updated_config,
                tool="configure",
                full_reminder=True,
                reply="\n".join(lines),
                migration_notice=migration_notice,
            )
        )
        return 0

    if args.cmd == "update-config":
        try:
            validate_update_config_input(stdin_text)
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / MANAGED_DIRNAME).mkdir(parents=True, exist_ok=True)
            config, migration_notice, created_canonical = resolve_config_for_update(
                repo_root,
                default_model=effective_default_model,
                default_reasoning_effort=effective_default_reasoning_effort,
            )
        except Exception as exc:
            eprint(str(exc))
            return 1

        mams_channel_names = ", ".join(mams_channel.name for mams_channel in config.mams_channels) if config.mams_channels else "(none)"
        if created_canonical:
            status_line = "Created a canonical managed config because no prior managed config was present."
        elif migration_notice:
            status_line = "Normalized existing managed state into the canonical config."
        else:
            status_line = "Canonical managed config is already up to date."
        lines = [
            "update-config applied.",
            status_line,
            f"Config path: {mams_channels_file_path(repo_root)}",
            f"Managed mams_channels: {mams_channel_names}",
        ]
        sys.stdout.write(
            format_output_for_mams_invoker(
                repo_root,
                config,
                tool="update-config",
                full_reminder=True,
                reply="\n".join(lines),
                migration_notice=migration_notice,
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
            config, mams_channel, migration_notice = resolve_mams_channels_for_command(
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
            next_description = payload.mams_channel_description or mams_channel.description
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
                description=next_description,
                focus=mams_channel.focus,
                baseline=mams_channel.baseline,
                extra_context=mams_channel.extra_context,
                stage_guidance=mams_channel.stage_guidance,
                can_mutate=mams_channel.can_mutate,
                runner=mams_channel.runner,
                runner_config=mams_channel.runner_config,
                session_id=current_session_id,
                model=effective_model,
                reasoning_effort=effective_reasoning_effort,
                previous_session_ids=previous_session_ids,
                reminder_turn_count=0,
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
            format_output_for_mams_invoker(
                repo_root,
                updated_config,
                tool="dangerous-new-session",
                full_reminder=True,
                reply="\n".join(lines),
                migration_notice=migration_notice,
            )
        )
        return 0

    try:
        config, mams_channel, migration_notice = resolve_mams_channels_for_command(
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
    turn_index = collaborative_turn_index(args.cmd, mams_channel)
    full_reminder = should_use_full_reminder(args.cmd, turn_index)

    try:
        reply, updated_mams_channel = execute_command_for_mams_channel(
            repo_root,
            config,
            mams_channel,
            command=args.cmd,
            stdin_text=stdin_text,
            timeout_s=args.timeout_s,
            model=model,
            reasoning_effort=reasoning_effort,
            full_reminder=full_reminder,
        )
    except Exception as exc:
        eprint(str(exc))
        return 1

    persist_mams_channels_for_command(repo_root, config, updated_mams_channel)
    if updated_mams_channel.runner == RUNNER_CODEX:
        try_promote_exec_session_to_cli(updated_mams_channel.session_id)

    sys.stdout.write(
        format_output_for_mams_invoker(
            repo_root,
            config,
            tool=args.cmd,
            full_reminder=full_reminder if args.cmd != "init" else True,
            reply=reply,
            migration_notice=migration_notice,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

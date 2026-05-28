#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Tuple


CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
DEFAULT_MODEL = os.environ.get("CODEX_MODEL")
DEFAULT_REASONING_EFFORT = os.environ.get("CODEX_REASONING_EFFORT")
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROMPTS_DIR = SKILL_ROOT / "prompts"

VERBATIM_BEGIN = "<<<USER_MESSAGE_VERBATIM_BEGIN>>>"
VERBATIM_END = "<<<USER_MESSAGE_VERBATIM_END>>>"
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
CHAT_MESSAGE_FIELD = "message_for_codex"
CHAT_FRESH_USER_FIELD = "fresh_user_message"
WORK_SYNC_MESSAGE_FIELD = "sync_message"
WORK_SYNC_FRESH_USER_FIELD = "fresh_user_message"
REQUEST_MUTATION_FIELD = "approved_mutation"
REQUEST_MUTATION_FRESH_USER_FIELD = "fresh_user_message"
REQUEST_MUTATION_SANDBOX_MODE_FIELD = "sandbox_mode"
REQUEST_MUTATION_SANDBOX_DEFAULT = "default"
REQUEST_MUTATION_SANDBOX_FULL_ACCESS = "full-access"
DANGEROUS_NEW_SESSION_PERMISSION_FIELD = "user_permission"
DANGEROUS_NEW_SESSION_TARGET_FIELD = "target_session_id"
DANGEROUS_NEW_SESSION_DESCRIPTION_FIELD = "agent_description"
DANGEROUS_NEW_SESSION_MODEL_FIELD = "model"
DANGEROUS_NEW_SESSION_REASONING_EFFORT_FIELD = "reasoning_effort"
CONFIGURE_CALLER_FIELD = "caller"
CONFIGURE_SHARED_STAGES_FIELD = "shared_stages"
CONFIGURE_AGENTS_FIELD = "agents"
INIT_TASK_REPLY_TITLE = "Task Understanding Reply"
INIT_RECOVERY_REPLY_TITLE = "Context Recovery Reply"
REVIEW_PLAN_REPLY_TITLE = "Plan Review Reply"
REVIEW_WORK_REPLY_TITLE = "Work Review Reply"
WORK_SYNC_REPLY_TITLE = "Discussion Reply"
WORK_SYNC_PLAN_TITLE = "Plan"
SANDBOX_READ_ONLY = "read-only"
SANDBOX_WORKSPACE_WRITE = "workspace-write"
SANDBOX_DANGER_FULL_ACCESS = "danger-full-access"
AGENTS_FILENAME = "codex_agents.json"
LEGACY_SESSION_FILENAME = "codex_session.json"
LEGACY_HISTORY_FILENAME = "codex_session_history.json"
MANAGED_DIRNAME = ".codex-skill"
LEGACY_MANAGED_DIRNAME = ".claude"
DEFAULT_AGENT_NAME = "default"
DEFAULT_AGENT_DESCRIPTION = "Primary Codex collaboration channel."
MIGRATED_AGENT_DESCRIPTION = "Migrated primary Codex collaboration channel."
CONFIG_VERSION = 4
REF_DIRECTORY = f"{MANAGED_DIRNAME}/refs"
REF_PATTERN = re.compile(r"\[\[REF:(?P<path>[^:\]]+?)(?:::(?P<locator>[^\]]+))?\]\]")

TOOL_HELP = {
    "init": "Bootstrap Codex collaboration for a new task or recovery sync (reads JSON from stdin).",
    "chat": "Discussion / disagreement resolution turn (reads JSON from stdin).",
    "review-my-plan": "Codex reviews the caller's plan without mutating state (reads JSON from stdin).",
    "review-my-work": "Codex reviews completed work without mutating state (reads JSON from stdin).",
    "work-sync": "Codex sync turn for discussion, plan output, and review response (reads JSON from stdin).",
    "request-mutation": "Codex performs one approved mutation step when this channel is allowed to mutate (reads JSON from stdin).",
    "dangerous-new-session": "Explicitly authorize discarding continuity and starting or switching a managed Codex agent session (reads JSON from stdin).",
    "configure": "Patch caller guidance, shared guidance, or channel metadata (reads JSON from stdin).",
    "update-config": "Normalize discoverable managed state and rewrite the canonical config (does not read JSON from stdin).",
}


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
    Find the nearest ancestor directory that already owns a managed Codex session
    file.

    IMPORTANT:
    - Never treat the global ~/.claude or ~/.codex-skill directory as a project root.
    - `.codex-skill/codex_agents.json` is the stable anchor.
    - `.claude/codex_agents.json` and `.claude/codex_session.json` are accepted only as legacy anchors so the wrapper can
      migrate them into the new structured config location.
    - `.codex-skill/` or `.claude/` alone can exist at many levels for other purposes, so we do
      not auto-pick based on the directory alone.
    """
    for p in iter_ancestors(start):
        managed_dir = p / MANAGED_DIRNAME
        legacy_dir = p / LEGACY_MANAGED_DIRNAME
        if is_global_managed_dir(managed_dir) or is_global_managed_dir(legacy_dir):
            continue
        if (managed_dir / AGENTS_FILENAME).is_file():
            return p
        if (legacy_dir / AGENTS_FILENAME).is_file():
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


def agents_file_path(repo_root: Path) -> Path:
    return repo_root / MANAGED_DIRNAME / AGENTS_FILENAME


def legacy_agents_file_path(repo_root: Path) -> Path:
    return repo_root / LEGACY_MANAGED_DIRNAME / AGENTS_FILENAME


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
class AgentConfig:
    name: str
    description: str
    focus: Optional[str]
    baseline: Optional[str]
    extra_context: Optional[str]
    stage_guidance: dict[str, str]
    can_mutate: bool
    session_id: Optional[str]
    model: Optional[str]
    reasoning_effort: Optional[str]
    previous_session_ids: tuple[str, ...]
    reminder_turn_count: int
    updated_at: str


@dataclass(frozen=True)
class CallerConfig:
    baseline: Optional[str]
    working_style: Optional[str]
    extra_context: Optional[str]
    stage_guidance: dict[str, str]
    can_mutate: bool


@dataclass(frozen=True)
class SkillConfig:
    version: int
    caller: CallerConfig
    shared_stages: dict[str, str]
    agents: list[AgentConfig]
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


def default_agent_description(name: str) -> str:
    if name == DEFAULT_AGENT_NAME:
        return DEFAULT_AGENT_DESCRIPTION
    return f"Codex collaboration channel '{name}'."


def build_agent_config(
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
    previous_session_ids: tuple[str, ...] = (),
    reminder_turn_count: int = 0,
) -> AgentConfig:
    normalized_name = normalize_optional_string(name)
    if not normalized_name:
        raise ValueError("Agent name must be a non-empty string.")
    normalized_description = normalize_optional_string(description) or default_agent_description(
        normalized_name
    )
    return AgentConfig(
        name=normalized_name,
        description=normalized_description,
        focus=normalize_optional_string(focus),
        baseline=normalize_optional_string(baseline),
        extra_context=normalize_optional_string(extra_context),
        stage_guidance=dict(stage_guidance or {}),
        can_mutate=bool(can_mutate),
        session_id=normalize_optional_string(session_id),
        model=normalize_optional_string(model),
        reasoning_effort=normalize_optional_string(reasoning_effort),
        previous_session_ids=normalize_previous_session_ids(list(previous_session_ids)),
        reminder_turn_count=max(0, int(reminder_turn_count)),
        updated_at=iso_now(),
    )


def parse_agent_config(obj: object) -> AgentConfig:
    if not isinstance(obj, dict):
        raise ValueError("Each agent entry must be a JSON object.")
    name = normalize_optional_string(obj.get("name"))
    if not name:
        raise ValueError("Each agent entry requires a non-empty string field: name.")
    description = normalize_optional_string(obj.get("description")) or default_agent_description(name)
    updated_at = normalize_optional_string(obj.get("updated_at")) or iso_now()
    raw_can_mutate = obj.get("can_mutate", True)
    if not isinstance(raw_can_mutate, bool):
        raise ValueError(f"agents[{name}].can_mutate must be a boolean when provided.")
    return AgentConfig(
        name=name,
        description=description,
        focus=normalize_optional_string(obj.get("focus")),
        baseline=normalize_optional_string(obj.get("baseline")),
        extra_context=normalize_optional_string(obj.get("extra_context")),
        stage_guidance=normalize_string_map(obj.get("stage_guidance"), field_name=f"agents[{name}].stage_guidance"),
        can_mutate=raw_can_mutate,
        session_id=normalize_optional_string(obj.get("session_id")),
        model=normalize_optional_string(obj.get("model")),
        reasoning_effort=normalize_optional_string(obj.get("reasoning_effort")),
        previous_session_ids=normalize_previous_session_ids(obj.get("previous_session_ids")),
        reminder_turn_count=max(0, int(obj.get("reminder_turn_count", 0) or 0)),
        updated_at=updated_at,
    )


def agent_config_to_json(agent: AgentConfig) -> dict[str, object]:
    return {
        "name": agent.name,
        "description": agent.description,
        "focus": agent.focus,
        "baseline": agent.baseline,
        "extra_context": agent.extra_context,
        "stage_guidance": agent.stage_guidance,
        "can_mutate": agent.can_mutate,
        "session_id": agent.session_id,
        "model": agent.model,
        "reasoning_effort": agent.reasoning_effort,
        "previous_session_ids": list(agent.previous_session_ids),
        "reminder_turn_count": agent.reminder_turn_count,
        "updated_at": agent.updated_at,
    }


def default_caller_config() -> CallerConfig:
    return CallerConfig(
        baseline=None,
        working_style=None,
        extra_context=None,
        stage_guidance={},
        can_mutate=True,
    )


def default_skill_config(agents: Optional[list[AgentConfig]] = None) -> SkillConfig:
    return SkillConfig(
        version=CONFIG_VERSION,
        caller=default_caller_config(),
        shared_stages={},
        agents=list(agents or []),
        updated_at=iso_now(),
    )


def parse_caller_config(obj: object) -> CallerConfig:
    if obj is None:
        return default_caller_config()
    if not isinstance(obj, dict):
        raise ValueError("caller must be a JSON object when provided.")
    raw_can_mutate = obj.get("can_mutate", True)
    if not isinstance(raw_can_mutate, bool):
        raise ValueError("caller.can_mutate must be a boolean when provided.")
    return CallerConfig(
        baseline=normalize_optional_string(obj.get("baseline")),
        working_style=normalize_optional_string(obj.get("working_style")),
        extra_context=normalize_optional_string(obj.get("extra_context")),
        stage_guidance=normalize_string_map(obj.get("stage_guidance"), field_name="caller.stage_guidance"),
        can_mutate=raw_can_mutate,
    )


def caller_config_to_json(config: CallerConfig) -> dict[str, object]:
    return {
        "baseline": config.baseline,
        "working_style": config.working_style,
        "extra_context": config.extra_context,
        "stage_guidance": config.stage_guidance,
        "can_mutate": config.can_mutate,
    }


def parse_skill_config_object(obj: object, *, path: Path) -> SkillConfig:
    if not isinstance(obj, dict):
        raise RuntimeError(f"Agent config file must contain a JSON object or legacy JSON array: {path}")
    agents_value = obj.get("agents")
    if agents_value is None:
        raise RuntimeError(f"Config object must contain an 'agents' array: {path}")
    if not isinstance(agents_value, list):
        raise RuntimeError(f"Config field 'agents' must be a JSON array: {path}")
    agents: list[AgentConfig] = []
    seen: set[str] = set()
    for raw in agents_value:
        agent = parse_agent_config(raw)
        if agent.name in seen:
            raise RuntimeError(f"Duplicate agent name in {path}: {agent.name}")
        seen.add(agent.name)
        agents.append(agent)
    try:
        shared_stages = normalize_string_map(obj.get("shared_stages"), field_name="shared_stages")
        caller_source = obj.get("caller", obj.get("claude"))
        caller = parse_caller_config(caller_source)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    version = obj.get("version")
    if isinstance(version, int):
        normalized_version = version
    else:
        normalized_version = CONFIG_VERSION
    updated_at = normalize_optional_string(obj.get("updated_at")) or iso_now()
    return SkillConfig(
        version=normalized_version,
        caller=caller,
        shared_stages=shared_stages,
        agents=agents,
        updated_at=updated_at,
    )


def skill_config_to_json(config: SkillConfig) -> dict[str, object]:
    return {
        "version": config.version,
        "caller": caller_config_to_json(config.caller),
        "shared_stages": config.shared_stages,
        "agents": [agent_config_to_json(agent) for agent in config.agents],
        "updated_at": config.updated_at,
    }


def read_skill_config(repo_root: Path) -> SkillConfig:
    path = agents_file_path(repo_root)
    if not path.exists():
        return default_skill_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid agent config JSON in {path}: {exc.msg}") from exc
    if isinstance(data, list):
        agents = []
        seen: set[str] = set()
        for raw in data:
            agent = parse_agent_config(raw)
            if agent.name in seen:
                raise RuntimeError(f"Duplicate agent name in {path}: {agent.name}")
            seen.add(agent.name)
            agents.append(agent)
        return default_skill_config(agents)
    return parse_skill_config_object(data, path=path)


def write_skill_config(repo_root: Path, config: SkillConfig) -> None:
    path = agents_file_path(repo_root)
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
    config: SkillConfig
    detail: str


def structured_config_needs_migration(raw_obj: dict[str, object]) -> bool:
    if "claude" in raw_obj:
        return True
    version = raw_obj.get("version")
    if not isinstance(version, int) or version < CONFIG_VERSION:
        return True
    if "work_modes" in raw_obj:
        return True
    caller = raw_obj.get("caller")
    if not isinstance(caller, dict) or "can_mutate" not in caller:
        return True
    agents = raw_obj.get("agents")
    if isinstance(agents, list):
        for raw_agent in agents:
            if not isinstance(raw_agent, dict) or "can_mutate" not in raw_agent:
                return True
    return False


def load_migration_source(
    repo_root: Path,
    *,
    default_model: Optional[str],
    default_reasoning_effort: Optional[str],
) -> Optional[MigrationSource]:
    config_path = agents_file_path(repo_root)
    legacy_config_path = legacy_agents_file_path(repo_root)

    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid agent config JSON in {config_path}: {exc.msg}") from exc
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
                config=default_skill_config([parse_agent_config(item) for item in data]),
                detail="legacy array-based config needed normalization",
            )
        raise RuntimeError(f"Agent config file must contain a JSON object or legacy JSON array: {config_path}")

    if legacy_config_path.exists():
        try:
            data = json.loads(legacy_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid agent config JSON in {legacy_config_path}: {exc.msg}") from exc
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
                config=default_skill_config([parse_agent_config(item) for item in data]),
                detail="legacy array-based config from the old directory",
            )
        raise RuntimeError(f"Agent config file must contain a JSON object or legacy JSON array: {legacy_config_path}")

    legacy_session_id = read_legacy_session_id(repo_root)
    legacy_history = read_legacy_session_history(repo_root)
    if legacy_session_id is None and not legacy_history:
        return None

    migrated = build_agent_config(
        DEFAULT_AGENT_NAME,
        description=MIGRATED_AGENT_DESCRIPTION,
        session_id=legacy_session_id,
        model=default_model,
        reasoning_effort=default_reasoning_effort,
        previous_session_ids=legacy_history,
    )
    return MigrationSource(
        kind="legacy-session",
        path=legacy_session_file_path(repo_root),
        config=default_skill_config([migrated]),
        detail="legacy single-session continuity files",
    )


def migrate_agents_config_to_latest(
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
    destination = agents_file_path(repo_root)
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


def find_agent(agents: list[AgentConfig], name: str) -> Optional[AgentConfig]:
    for agent in agents:
        if agent.name == name:
            return agent
    return None


def upsert_agent(agents: list[AgentConfig], updated_agent: AgentConfig) -> list[AgentConfig]:
    next_agents: list[AgentConfig] = []
    replaced_existing = False
    for agent in agents:
        if agent.name == updated_agent.name:
            next_agents.append(updated_agent)
            replaced_existing = True
        else:
            next_agents.append(agent)
    if not replaced_existing:
        next_agents.append(updated_agent)
    return next_agents


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
    config: SkillConfig,
    payload: ConfigurePayload,
) -> SkillConfig:
    caller = config.caller
    if payload.caller_patch is not None:
        stage_patch = payload.caller_patch.get("stage_guidance")
        caller = CallerConfig(
            baseline=payload.caller_patch["baseline"] if "baseline" in payload.caller_patch else caller.baseline,
            working_style=payload.caller_patch["working_style"] if "working_style" in payload.caller_patch else caller.working_style,
            extra_context=payload.caller_patch["extra_context"] if "extra_context" in payload.caller_patch else caller.extra_context,
            stage_guidance=merge_string_map(
                caller.stage_guidance,
                stage_patch if isinstance(stage_patch, dict) else None,
            ),
            can_mutate=payload.caller_patch["can_mutate"] if "can_mutate" in payload.caller_patch else caller.can_mutate,
        )

    shared_stages = merge_string_map(config.shared_stages, payload.shared_stages_patch)

    agents = list(config.agents)
    if payload.agents_patch:
        for patch in payload.agents_patch:
            name = patch["name"]
            existing = find_agent(agents, name)
            if existing is None:
                updated_agent = build_agent_config(
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
                updated_agent = build_agent_config(
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
            agents = upsert_agent(agents, updated_agent)

    return SkillConfig(
        version=CONFIG_VERSION,
        caller=caller,
        shared_stages=shared_stages,
        agents=agents,
        updated_at=iso_now(),
    )


@dataclass(frozen=True)
class InitPayload:
    mode: str
    background: str


@dataclass(frozen=True)
class ReviewMyPlanPayload:
    plan_for_review: str
    new_information: Optional[str]
    fresh_user_message: Optional[str]


@dataclass(frozen=True)
class ChatPayload:
    message_for_codex: str
    fresh_user_message: Optional[str]


@dataclass(frozen=True)
class ReviewMyWorkPayload:
    work_for_review: str
    new_information: Optional[str]
    fresh_user_message: Optional[str]


@dataclass(frozen=True)
class WorkSyncPayload:
    sync_message: str
    fresh_user_message: Optional[str]


@dataclass(frozen=True)
class RequestMutationPayload:
    approved_mutation: str
    fresh_user_message: Optional[str]
    sandbox_mode: str


@dataclass(frozen=True)
class DangerousNewSessionPayload:
    user_permission: str
    target_session_id: Optional[str]
    agent_description: Optional[str]
    model: Optional[str]
    reasoning_effort: Optional[str]


@dataclass(frozen=True)
class ConfigurePayload:
    caller_patch: Optional[dict[str, object]]
    shared_stages_patch: Optional[dict[str, Optional[str]]]
    agents_patch: Optional[list[dict[str, object]]]


def validate_update_config_input(stdin_text: str) -> None:
    if stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip():
        raise ValueError("update-config does not accept input. Run it with empty stdin.")


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


def parse_review_my_plan_payload(stdin_text: str) -> ReviewMyPlanPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("review-my-plan input is empty. Provide JSON with plan_for_review.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"review-my-plan input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("review-my-plan input must be a JSON object.")

    allowed_keys = {
        REVIEW_PLAN_FIELD,
        REVIEW_PLAN_NEW_INFO_FIELD,
        REVIEW_PLAN_FRESH_USER_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"review-my-plan input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    plan_for_review = obj.get(REVIEW_PLAN_FIELD)
    if not isinstance(plan_for_review, str) or not plan_for_review.strip():
        raise ValueError("review-my-plan requires a non-empty string field: plan_for_review.")

    def parse_optional_string(field: str) -> Optional[str]:
        value = obj.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"review-my-plan field {field} must be a non-empty string when provided.")
        return value.strip()

    return ReviewMyPlanPayload(
        plan_for_review=plan_for_review.strip(),
        new_information=parse_optional_string(REVIEW_PLAN_NEW_INFO_FIELD),
        fresh_user_message=parse_optional_string(REVIEW_PLAN_FRESH_USER_FIELD),
    )


def parse_chat_payload(stdin_text: str) -> ChatPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("chat input is empty. Provide JSON with message_for_codex.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"chat input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("chat input must be a JSON object.")

    allowed_keys = {CHAT_MESSAGE_FIELD, CHAT_FRESH_USER_FIELD}
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"chat input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    message = obj.get(CHAT_MESSAGE_FIELD)
    if not isinstance(message, str) or not message.strip():
        raise ValueError("chat requires a non-empty string field: message_for_codex.")

    fresh_user_message = obj.get(CHAT_FRESH_USER_FIELD)
    if fresh_user_message is not None:
        if not isinstance(fresh_user_message, str) or not fresh_user_message.strip():
            raise ValueError("chat field fresh_user_message must be a non-empty string when provided.")
        fresh_user_message = fresh_user_message.strip()

    return ChatPayload(
        message_for_codex=message.strip(),
        fresh_user_message=fresh_user_message,
    )


def parse_review_my_work_payload(stdin_text: str) -> ReviewMyWorkPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("review-my-work input is empty. Provide JSON with work_for_review.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"review-my-work input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("review-my-work input must be a JSON object.")

    allowed_keys = {
        REVIEW_WORK_FIELD,
        REVIEW_WORK_NEW_INFO_FIELD,
        REVIEW_WORK_FRESH_USER_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"review-my-work input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    work_for_review = obj.get(REVIEW_WORK_FIELD)
    if not isinstance(work_for_review, str) or not work_for_review.strip():
        raise ValueError("review-my-work requires a non-empty string field: work_for_review.")

    def parse_optional_string(field: str) -> Optional[str]:
        value = obj.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"review-my-work field {field} must be a non-empty string when provided.")
        return value.strip()

    return ReviewMyWorkPayload(
        work_for_review=work_for_review.strip(),
        new_information=parse_optional_string(REVIEW_WORK_NEW_INFO_FIELD),
        fresh_user_message=parse_optional_string(REVIEW_WORK_FRESH_USER_FIELD),
    )


def parse_work_sync_payload(stdin_text: str) -> WorkSyncPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("work-sync input is empty. Provide JSON with sync_message.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"work-sync input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("work-sync input must be a JSON object.")

    allowed_keys = {WORK_SYNC_MESSAGE_FIELD, WORK_SYNC_FRESH_USER_FIELD}
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"work-sync input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    sync_message = obj.get(WORK_SYNC_MESSAGE_FIELD)
    if not isinstance(sync_message, str) or not sync_message.strip():
        raise ValueError("work-sync requires a non-empty string field: sync_message.")

    fresh_user_message = obj.get(WORK_SYNC_FRESH_USER_FIELD)
    if fresh_user_message is not None:
        if not isinstance(fresh_user_message, str) or not fresh_user_message.strip():
            raise ValueError("work-sync field fresh_user_message must be a non-empty string when provided.")
        fresh_user_message = fresh_user_message.strip()

    return WorkSyncPayload(
        sync_message=sync_message.strip(),
        fresh_user_message=fresh_user_message,
    )


def parse_request_mutation_payload(stdin_text: str) -> RequestMutationPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("request-mutation input is empty. Provide JSON with approved_mutation.")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"request-mutation input must be valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("request-mutation input must be a JSON object.")

    allowed_keys = {
        REQUEST_MUTATION_FIELD,
        REQUEST_MUTATION_FRESH_USER_FIELD,
        REQUEST_MUTATION_SANDBOX_MODE_FIELD,
    }
    unknown_keys = set(obj.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"request-mutation input has unsupported fields: {', '.join(sorted(unknown_keys))}")

    approved_mutation = obj.get(REQUEST_MUTATION_FIELD)
    if not isinstance(approved_mutation, str) or not approved_mutation.strip():
        raise ValueError("request-mutation requires a non-empty string field: approved_mutation.")

    fresh_user_message = obj.get(REQUEST_MUTATION_FRESH_USER_FIELD)
    if fresh_user_message is not None:
        if not isinstance(fresh_user_message, str) or not fresh_user_message.strip():
            raise ValueError("request-mutation field fresh_user_message must be a non-empty string when provided.")
        fresh_user_message = fresh_user_message.strip()

    sandbox_mode = obj.get(REQUEST_MUTATION_SANDBOX_MODE_FIELD, REQUEST_MUTATION_SANDBOX_DEFAULT)
    if sandbox_mode not in {REQUEST_MUTATION_SANDBOX_DEFAULT, REQUEST_MUTATION_SANDBOX_FULL_ACCESS}:
        raise ValueError("request-mutation field sandbox_mode must be exactly 'default' or 'full-access' when provided.")

    return RequestMutationPayload(
        approved_mutation=approved_mutation.strip(),
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
        DANGEROUS_NEW_SESSION_DESCRIPTION_FIELD,
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
        agent_description=parse_optional_config_string(DANGEROUS_NEW_SESSION_DESCRIPTION_FIELD),
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
            "configure input is empty. Provide JSON with at least one of: caller, shared_stages, agents."
        )
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"configure input must be valid JSON: {exc.msg}") from exc
    if not isinstance(obj, dict):
        raise ValueError("configure input must be a JSON object.")

    allowed_keys = {
        CONFIGURE_CALLER_FIELD,
        CONFIGURE_SHARED_STAGES_FIELD,
        CONFIGURE_AGENTS_FIELD,
    }
    legacy_keys = {"claude"} if "claude" in obj else set()
    unknown_keys = set(obj.keys()) - allowed_keys - legacy_keys
    if unknown_keys:
        raise ValueError(f"configure input has unsupported fields: {', '.join(sorted(unknown_keys))}")
    if not obj:
        raise ValueError(
            "configure input must contain at least one of: caller, shared_stages, agents."
        )

    if CONFIGURE_CALLER_FIELD in obj and "claude" in obj:
        raise ValueError("configure input must not contain both caller and legacy claude fields.")

    caller_patch = obj.get(CONFIGURE_CALLER_FIELD, obj.get("claude"))
    if caller_patch is not None:
        if not isinstance(caller_patch, dict):
            raise ValueError("configure field caller must be a JSON object.")
        allowed_caller_keys = {"baseline", "working_style", "extra_context", "stage_guidance", "can_mutate"}
        unknown_caller_keys = set(caller_patch.keys()) - allowed_caller_keys
        if unknown_caller_keys:
            raise ValueError(
                "configure.caller has unsupported fields: "
                + ", ".join(sorted(unknown_caller_keys))
            )
        if "stage_guidance" in caller_patch and caller_patch["stage_guidance"] is not None:
            caller_patch = dict(caller_patch)
            caller_patch["stage_guidance"] = parse_nullable_string_patch_map(
                caller_patch["stage_guidance"],
                field_name="configure.caller.stage_guidance",
            )
        for field in ("baseline", "working_style", "extra_context"):
            if field in caller_patch:
                value = caller_patch[field]
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    raise ValueError(f"configure.caller.{field} must be a non-empty string or null.")
                if isinstance(value, str):
                    caller_patch[field] = value.strip()
        if "can_mutate" in caller_patch and not isinstance(caller_patch["can_mutate"], bool):
            raise ValueError("configure.caller.can_mutate must be a boolean when provided.")

    shared_stages_patch = obj.get(CONFIGURE_SHARED_STAGES_FIELD)
    if shared_stages_patch is not None:
        shared_stages_patch = parse_nullable_string_patch_map(
            shared_stages_patch,
            field_name="configure.shared_stages",
        )

    agents_patch_value = obj.get(CONFIGURE_AGENTS_FIELD)
    agents_patch: Optional[list[dict[str, object]]] = None
    if agents_patch_value is not None:
        if not isinstance(agents_patch_value, list):
            raise ValueError("configure field agents must be a JSON array.")
        agents_patch = []
        for index, raw_agent in enumerate(agents_patch_value):
            if not isinstance(raw_agent, dict):
                raise ValueError(f"configure.agents[{index}] must be a JSON object.")
            allowed_agent_keys = {
                "name",
                "description",
                "focus",
                "baseline",
                "extra_context",
                "stage_guidance",
                "can_mutate",
                "model",
                "reasoning_effort",
            }
            unknown_agent_keys = set(raw_agent.keys()) - allowed_agent_keys
            if unknown_agent_keys:
                raise ValueError(
                    f"configure.agents[{index}] has unsupported fields: {', '.join(sorted(unknown_agent_keys))}"
                )
            name = normalize_optional_string(raw_agent.get("name"))
            if not name:
                raise ValueError(f"configure.agents[{index}] requires a non-empty string field: name.")
            normalized_agent = dict(raw_agent)
            normalized_agent["name"] = name
            for field in ("description", "focus", "baseline", "extra_context", "model", "reasoning_effort"):
                if field in normalized_agent:
                    value = normalized_agent[field]
                    if value is not None and (not isinstance(value, str) or not value.strip()):
                        raise ValueError(
                            f"configure.agents[{index}].{field} must be a non-empty string or null."
                        )
                    if isinstance(value, str):
                        normalized_agent[field] = value.strip()
            if "stage_guidance" in normalized_agent and normalized_agent["stage_guidance"] is not None:
                normalized_agent["stage_guidance"] = parse_nullable_string_patch_map(
                    normalized_agent["stage_guidance"],
                    field_name=f"configure.agents[{index}].stage_guidance",
                )
            if "can_mutate" in normalized_agent and not isinstance(normalized_agent["can_mutate"], bool):
                raise ValueError(f"configure.agents[{index}].can_mutate must be a boolean when provided.")
            agents_patch.append(normalized_agent)

    return ConfigurePayload(
        caller_patch=caller_patch,
        shared_stages_patch=shared_stages_patch,
        agents_patch=agents_patch,
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
    return ["\n".join(lines)]


def render_named_items(items: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"### {title}\n\n{body}" for title, body in items).strip()


def build_brief_user_reminder(label: str, items: list[tuple[str, str]], stage_name: str) -> str:
    if not items:
        return ""
    active = ", ".join(title for title, _body in items)
    emphasis_lines: list[str] = []
    for title, body in items:
        if "Mutation Permission" in title:
            emphasis_lines.append(f"- {body}")
    return (
        f"The configured {label} still applies.\n"
        f"Current stage: {stage_name}.\n"
        f"Active reminder fields: {active}.\n"
        + ("\n".join(emphasis_lines) + "\n" if emphasis_lines else "")
        + "Do not drift from that configured reminder just because the full text is omitted in this turn."
    )


def build_codex_skill_reminder_text_for_codex(
    tool: str,
    *,
    full: bool,
    prompt_text: str,
) -> str:
    if full or tool == "init":
        return prompt_text.strip()

    brief_map = {
        "chat": (
            "Persistent collaboration turn with the caller, not the end user. "
            "Discussion only; no mutation and no gate verdict. "
            "Compare evidence, surface disagreement clearly, and only ask the caller to escalate to the user "
            "if a real unresolved disagreement between you and the caller has persisted for about 10 turns."
        ),
        "review-my-plan": (
            "Hard gate. Review the plan before any mutation, do not mutate in this turn, and judge from facts and whole-system coherence. "
            "The first non-empty line must be approved_to_mutate: true or approved_to_mutate: false, followed by ## Plan Review Reply. "
            "Do not ask for user input unless a real unresolved disagreement between you and the caller has persisted for about 10 turns."
        ),
        "review-my-work": (
            "Hard gate. Review the actual work, not intent; do not mutate in this turn. "
            "The first non-empty line must be approved_work: true or approved_work: false, followed by ## Work Review Reply. "
            "Do not ask for user input unless a real unresolved disagreement between you and the caller has persisted for about 10 turns."
        ),
        "work-sync": (
            "Sync turn only. Discussion, disagreement handling, candidate plan formation, or response to caller review are allowed; mutation is not. "
            "Return ## Discussion Reply, and add ## Plan only when a candidate plan is genuinely ready. "
            "Do not ask for user input unless a real unresolved disagreement between you and the caller has persisted for about 10 turns."
        ),
        "request-mutation": (
            "Mutation turn for a mutate-capable channel. Perform only the approved step, do not widen scope, then stop and report what changed, what you verified, what concerns remain, and where you stopped. "
            "Do not ask the user directly."
        ),
    }
    return brief_map.get(tool, prompt_text.strip())


def build_codex_skill_reminder_text_for_caller(tool: str, *, full: bool) -> str:
    full_map = {
        "init": (
            "Run init on every new shared task and after compact/context clear when you need to re-bootstrap shared context. "
            "Init is collaboration bootstrap only. It is not discussion and not mutation."
        ),
        "chat": (
            "This is discussion only. Do not treat chat as plan approval or mutation permission. "
            "Keep pushing for real consensus, and do not stop for user input unless a real unresolved caller/Codex disagreement has persisted for about 10 turns."
        ),
        "review-my-plan": (
            "This is the hard gate before any approved mutation step begins. Submit a concrete plan, require direct fact-checking, and do not treat mere discussion as approval. "
            "Do not ask the user just because execution feels uncertain; escalate only when a real unresolved caller/Codex disagreement has persisted for about 10 turns."
        ),
        "review-my-work": (
            "This is the hard gate before delivery. Review actual work, evidence, and coherence. "
            "approved_work: true accepts only the reviewed step, not automatically the whole larger plan; if more agreed steps remain, continue directly to the next step instead of stopping. "
            "Do not ask the user just because next execution steps are undecided; escalate only when a real unresolved caller/Codex disagreement has persisted for about 10 turns."
        ),
        "work-sync": (
            "This is the non-mutation sync turn. Use it for discussion, disagreement, candidate plans, and response to review. "
            "It is not mutation permission. Escalate to the user only for a real unresolved caller/Codex disagreement that has persisted for about 10 turns."
        ),
        "request-mutation": (
            "This is the mutation permission turn for the selected mutate-capable channel. Approve exactly one concrete step, then expect Codex to stop and report back. "
            "Do not ask the user about whether to continue execution unless a real unresolved caller/Codex disagreement has persisted for about 10 turns."
        ),
        "configure": (
            "This command applies a caller-supplied config patch. It does not mutate task files and it does not replace session continuity by itself."
        ),
        "update-config": (
            "This command normalizes managed state into the canonical Codex Skill config. It does not mutate task files and it does not replace session continuity by itself."
        ),
        "dangerous-new-session": (
            "This command is for destructive continuity replacement. Use it only when the user explicitly authorizes abandoning or switching the managed session continuity."
        ),
    }
    brief_map = {
        "init": "Init re-establishes the collaboration baseline. Use full reminders here.",
        "chat": "Discussion only. No approval. Full Codex Skill reminder still applies. Ask the user only for a real unresolved disagreement that persists for about 10 turns.",
        "review-my-plan": "Hard gate before mutation. Full Codex Skill reminder still applies. Ask the user only for a real unresolved disagreement that persists for about 10 turns.",
        "review-my-work": "Hard gate before delivery. approved_work: true accepts only the reviewed step; if more agreed steps remain, continue instead of stopping. Full Codex Skill reminder still applies. Ask the user only for a real unresolved disagreement that persists for about 10 turns.",
        "work-sync": "Sync only. No mutation permission. Full Codex Skill reminder still applies. Ask the user only for a real unresolved disagreement that persists for about 10 turns.",
        "request-mutation": "Single approved mutation step on a mutate-capable channel only. Full Codex Skill reminder still applies.",
        "configure": "Caller-supplied config patch only. Full Codex Skill reminder still applies.",
        "update-config": "Config update only. Full Codex Skill reminder still applies.",
        "dangerous-new-session": "Destructive continuity replacement. Full Codex Skill reminder still applies.",
    }
    return (full_map if full else brief_map).get(tool, "")


def collaborative_turn_index(tool: str, agent: AgentConfig) -> int:
    if tool == "init":
        return 0
    if tool in {"chat", "review-my-plan", "review-my-work", "work-sync", "request-mutation"}:
        return agent.reminder_turn_count + 1
    return 0


def should_use_full_reminder(tool: str, turn_index: int) -> bool:
    if tool in {"init", "configure", "update-config", "dangerous-new-session"}:
        return True
    if turn_index <= 0:
        return True
    return (turn_index - 1) % 3 == 0


def build_common_stage_items(
    config: SkillConfig,
    *,
    tool: str,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    stage_name = tool

    shared_stage_text = config.shared_stages.get(stage_name)
    if shared_stage_text:
        items.append(("Shared Stage Guidance", shared_stage_text))

    return items


def build_caller_user_items(
    config: SkillConfig,
    *,
    tool: str,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    stage_name = tool

    if config.caller.baseline:
        items.append(("Caller Baseline", config.caller.baseline))
    if config.caller.working_style:
        items.append(("Caller Working Style", config.caller.working_style))
    if config.caller.extra_context:
        items.append(("Caller Extra Context", config.caller.extra_context))
    items.append(
        (
            "Caller Mutation Permission",
            (
                "The caller is allowed to mutate directly when appropriate."
                if config.caller.can_mutate
                else "The caller is not allowed to mutate directly and must route implementation through a mutate-capable channel."
            ),
        )
    )

    caller_stage_text = config.caller.stage_guidance.get(stage_name)
    if caller_stage_text:
        items.append(("Caller Stage Guidance", caller_stage_text))

    return items


def build_agent_user_items(
    config: SkillConfig,
    agent: AgentConfig,
    *,
    tool: str,
) -> list[tuple[str, str]]:
    stage_name = tool
    items: list[tuple[str, str]] = []

    if agent.description and agent.description != default_agent_description(agent.name):
        items.append(("Agent Description", agent.description))
    if agent.focus:
        items.append(("Agent Focus", agent.focus))
    if agent.baseline:
        items.append(("Agent Baseline", agent.baseline))
    if agent.extra_context:
        items.append(("Agent Extra Context", agent.extra_context))
    items.append(
        (
            "Channel Mutation Permission",
            (
                "This channel may mutate when the workflow explicitly reaches the mutation entrypoint."
                if agent.can_mutate
                else "This channel must not mutate files. It may discuss, review, or plan, but implementation must be routed elsewhere."
            ),
        )
    )

    agent_stage_text = agent.stage_guidance.get(stage_name)
    if agent_stage_text:
        items.append(("Agent Stage Guidance", agent_stage_text))

    return items


def compose_prompt(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
    *,
    tool: str,
    full_reminder: bool,
    base_parts: list[str],
) -> str:
    if not base_parts:
        raise RuntimeError("compose_prompt requires at least one base part.")
    common_items = build_common_stage_items(config, tool=tool)
    agent_items = build_agent_user_items(config, agent, tool=tool)
    skill_reminder = build_codex_skill_reminder_text_for_codex(
        tool,
        full=full_reminder,
        prompt_text=base_parts[0],
    )
    skill_body_parts = [skill_reminder]
    common_body = render_named_items(common_items)
    if common_body:
        skill_body_parts.append(common_body)
    skill_block = "## Codex Skill Reminder ({})\n\n{}".format(
        "Full" if full_reminder else "Brief",
        "\n\n".join(part for part in skill_body_parts if part).strip(),
    )

    if full_reminder:
        user_body = render_named_items(agent_items)
    else:
        user_body = build_brief_user_reminder("User Reminder", agent_items, tool)
    user_block = ""
    if user_body:
        user_block = "## User Reminder ({})\n\n{}".format(
            "Full" if full_reminder else "Brief",
            user_body,
        )

    ref_notice_sections = build_reference_notice(repo_root, [skill_block, user_block, *base_parts[1:]])
    prompt_parts = [skill_block, *ref_notice_sections]
    if user_block:
        prompt_parts.append(user_block)
    prompt_parts.extend(base_parts[1:])
    return "\n\n".join(part for part in prompt_parts if part).strip() + "\n"


def format_output_for_caller(
    repo_root: Path,
    config: SkillConfig,
    *,
    tool: str,
    full_reminder: bool,
    reply: str,
    migration_notice: Optional[str],
) -> str:
    normalized_reply = reply.rstrip()
    common_items = build_common_stage_items(config, tool=tool)
    caller_items = build_caller_user_items(config, tool=tool)
    skill_body_parts = [build_codex_skill_reminder_text_for_caller(tool, full=full_reminder)]
    common_body = render_named_items(common_items)
    if common_body:
        skill_body_parts.append(common_body)
    skill_block = "## Codex Skill Reminder ({})\n\n{}".format(
        "Full" if full_reminder else "Brief",
        "\n\n".join(part for part in skill_body_parts if part).strip(),
    )

    if full_reminder:
        user_body = render_named_items(caller_items)
    else:
        user_body = build_brief_user_reminder("User Reminder", caller_items, tool)
    user_block = ""
    if user_body:
        user_block = "## User Reminder ({})\n\n{}".format(
            "Full" if full_reminder else "Brief",
            user_body,
        )

    ref_notice_sections = build_reference_notice(repo_root, [skill_block, user_block])

    if not skill_block and not user_block and not ref_notice_sections:
        return append_migration_notice(normalized_reply, migration_notice)

    parts = [
        skill_block,
        *ref_notice_sections,
        user_block,
        "## Codex Reply",
        normalized_reply,
    ]
    return append_migration_notice("\n\n".join(part for part in parts if part), migration_notice)


def build_init_prompt(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
    stdin_text: str,
) -> tuple[str, str]:
    payload = parse_init_payload(stdin_text)
    if payload.mode == "task":
        prompt_name = "init-task.md"
        label = "Task background from the caller:"
    else:
        prompt_name = "init-recovery.md"
        label = "Recovery background from the caller:"

    prompt = compose_prompt(
        repo_root,
        config,
        agent,
        tool="init",
        full_reminder=True,
        base_parts=[
            load_prompt_asset(prompt_name),
            label,
            payload.background,
        ],
    )

    return prompt, payload.mode


def build_review_my_plan_prompt(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    payload = parse_review_my_plan_payload(stdin_text)
    parts = [
        load_prompt_asset("review-my-plan.md"),
        "Plan for review from the caller:",
        payload.plan_for_review,
    ]

    if payload.new_information:
        parts.extend(
            [
                "New information from the caller:",
                payload.new_information,
            ]
        )

    if payload.fresh_user_message:
        parts.extend(
            [
                "Fresh user message from the user (verbatim):",
                VERBATIM_BEGIN,
                payload.fresh_user_message,
                VERBATIM_END,
            ]
        )

    return compose_prompt(
        repo_root,
        config,
        agent,
        tool="review-my-plan",
        full_reminder=full_reminder,
        base_parts=parts,
    )


def build_chat_prompt(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    payload = parse_chat_payload(stdin_text)
    parts = [
        load_prompt_asset("chat.md"),
        "Message from the caller:",
        payload.message_for_codex,
    ]

    if payload.fresh_user_message:
        parts.extend(
            [
                "Fresh user message from the user (verbatim):",
                VERBATIM_BEGIN,
                payload.fresh_user_message,
                VERBATIM_END,
            ]
        )

    return compose_prompt(
        repo_root,
        config,
        agent,
        tool="chat",
        full_reminder=full_reminder,
        base_parts=parts,
    )


def build_review_my_work_prompt(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    payload = parse_review_my_work_payload(stdin_text)
    parts = [
        load_prompt_asset("review-my-work.md"),
        "Work for review from the caller:",
        payload.work_for_review,
    ]

    if payload.new_information:
        parts.extend(
            [
                "New information from the caller:",
                payload.new_information,
            ]
        )

    if payload.fresh_user_message:
        parts.extend(
            [
                "Fresh user message from the user (verbatim):",
                VERBATIM_BEGIN,
                payload.fresh_user_message,
                VERBATIM_END,
            ]
        )

    return compose_prompt(
        repo_root,
        config,
        agent,
        tool="review-my-work",
        full_reminder=full_reminder,
        base_parts=parts,
    )


def build_work_sync_prompt(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    payload = parse_work_sync_payload(stdin_text)
    parts = [
        load_prompt_asset("work-sync.md"),
        "Sync message from the caller:",
        payload.sync_message,
    ]

    if payload.fresh_user_message:
        parts.extend(
            [
                "Fresh user message from the user (verbatim):",
                VERBATIM_BEGIN,
                payload.fresh_user_message,
                VERBATIM_END,
            ]
        )

    return compose_prompt(
        repo_root,
        config,
        agent,
        tool="work-sync",
        full_reminder=full_reminder,
        base_parts=parts,
    )


def build_request_mutation_prompt(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    payload = parse_request_mutation_payload(stdin_text)
    sandbox_note = (
        "Execution sandbox for this turn: workspace-write (default mutation sandbox)."
        if payload.sandbox_mode == REQUEST_MUTATION_SANDBOX_DEFAULT
        else "Execution sandbox for this turn: danger-full-access (explicit full-access escalation approved by the caller)."
    )
    parts = [
        load_prompt_asset("request-mutation.md"),
        sandbox_note,
        "Approved mutation from the caller:",
        payload.approved_mutation,
    ]

    if payload.fresh_user_message:
        parts.extend(
            [
                "Fresh user message from the user (verbatim):",
                VERBATIM_BEGIN,
                payload.fresh_user_message,
                VERBATIM_END,
            ]
        )

    return compose_prompt(
        repo_root,
        config,
        agent,
        tool="request-mutation",
        full_reminder=full_reminder,
        base_parts=parts,
    )


def resolve_codex_exec_sandbox(cmd: str, stdin_text: str) -> str:
    if cmd == "request-mutation":
        payload = parse_request_mutation_payload(stdin_text)
        if payload.sandbox_mode == REQUEST_MUTATION_SANDBOX_FULL_ACCESS:
            return SANDBOX_DANGER_FULL_ACCESS
        return SANDBOX_WORKSPACE_WRITE
    return SANDBOX_READ_ONLY


def normalize_reply_text(reply: str) -> str:
    normalized = reply.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("Codex reply is empty.")
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


def validate_review_my_plan_reply(reply: str) -> str:
    parse_required_boolean_line(reply, REVIEW_PLAN_APPROVED_FIELD)
    return require_markdown_section(reply, REVIEW_PLAN_REPLY_TITLE)


def validate_review_my_work_reply(reply: str) -> str:
    parse_required_boolean_line(reply, REVIEW_WORK_APPROVED_FIELD)
    return require_markdown_section(reply, REVIEW_WORK_REPLY_TITLE)


def validate_work_sync_reply(reply: str) -> str:
    normalized = require_markdown_section(reply, WORK_SYNC_REPLY_TITLE, stop_titles=[WORK_SYNC_PLAN_TITLE])
    plan_heading = find_markdown_heading(normalized, WORK_SYNC_PLAN_TITLE)
    if plan_heading is not None:
        require_markdown_section(normalized, WORK_SYNC_PLAN_TITLE)
    return normalized


def build_prompt(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
    tool: str,
    stdin_text: str,
    *,
    full_reminder: bool,
) -> str:
    if tool == "init":
        prompt, _mode = build_init_prompt(repo_root, config, agent, stdin_text)
        return prompt
    if tool == "chat":
        return build_chat_prompt(repo_root, config, agent, stdin_text, full_reminder=full_reminder)
    if tool == "review-my-plan":
        return build_review_my_plan_prompt(
            repo_root,
            config,
            agent,
            stdin_text,
            full_reminder=full_reminder,
        )
    if tool == "review-my-work":
        return build_review_my_work_prompt(
            repo_root,
            config,
            agent,
            stdin_text,
            full_reminder=full_reminder,
        )
    if tool == "work-sync":
        return build_work_sync_prompt(
            repo_root,
            config,
            agent,
            stdin_text,
            full_reminder=full_reminder,
        )
    if tool == "request-mutation":
        return build_request_mutation_prompt(
            repo_root,
            config,
            agent,
            stdin_text,
            full_reminder=full_reminder,
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
class CodexRunResult:
    session_id: str
    reply: str


def build_dangerous_new_session_prompt(permission_text: str) -> str:
    return (
        "You are creating a fresh managed Codex agent session for future collaboration.\n"
        "This call exists only to establish a new session id.\n"
        "Do not ask questions. Do not assume prior task continuity.\n"
        "Reply with a short plain-text acknowledgment that the fresh managed session is ready.\n\n"
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


def resolve_agents_for_command(
    repo_root: Path,
    agent_name: str,
    *,
    default_model: Optional[str],
    default_reasoning_effort: Optional[str],
) -> tuple[SkillConfig, AgentConfig, Optional[str]]:
    migration_notice = migrate_agents_config_to_latest(
        repo_root,
        default_model=default_model,
        default_reasoning_effort=default_reasoning_effort,
    )
    config = read_skill_config(repo_root)
    agent = find_agent(config.agents, agent_name)
    if agent is None:
        agent = build_agent_config(
            agent_name,
            model=default_model,
            reasoning_effort=default_reasoning_effort,
        )
    return config, agent, migration_notice


def resolve_config_for_update(
    repo_root: Path,
    *,
    default_model: Optional[str],
    default_reasoning_effort: Optional[str],
) -> tuple[SkillConfig, Optional[str], bool]:
    migration_notice = migrate_agents_config_to_latest(
        repo_root,
        default_model=default_model,
        default_reasoning_effort=default_reasoning_effort,
    )
    config_path = agents_file_path(repo_root)
    created_canonical = False
    if config_path.exists():
        config = read_skill_config(repo_root)
    else:
        config = default_skill_config([])
        write_skill_config(repo_root, config)
        created_canonical = True
    return config, migration_notice, created_canonical


def persist_agents_for_command(
    repo_root: Path,
    config: SkillConfig,
    agent: AgentConfig,
) -> None:
    write_skill_config(
        repo_root,
        SkillConfig(
            version=CONFIG_VERSION,
            caller=config.caller,
            shared_stages=config.shared_stages,
            agents=upsert_agent(config.agents, replace(agent, updated_at=iso_now())),
            updated_at=iso_now(),
        ),
    )


def append_migration_notice(reply: str, migration_notice: Optional[str]) -> str:
    normalized = reply.rstrip()
    if not migration_notice:
        return normalized + "\n"
    return (
        f"{normalized}\n\n---\n"
        f"Migration notice: {migration_notice}\n"
        "Future calls now use the structured managed agent config automatically.\n"
    )


def run_codex(
    repo_root: Path,
    session_id: Optional[str],
    prompt: str,
    sandbox_mode: str,
    timeout_s: int,
    model: Optional[str],
    reasoning_effort: Optional[str],
) -> CodexRunResult:
    tmp_last = Path(tempfile.mkstemp(prefix="codex-skill-last-", suffix=".txt")[1])
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

        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception:
            proc.kill()
            raise

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                event = safe_json_loads(line.strip())
                if not event:
                    continue
                tid = detect_thread_id(event)
                if tid and not thread_id:
                    thread_id = tid

            rc = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError(f"codex timed out after {timeout_s}s")

        if rc != 0:
            stderr = ""
            try:
                assert proc.stderr is not None
                stderr = proc.stderr.read().strip()
            except Exception:
                stderr = ""
            raise RuntimeError(stderr or f"codex exited with code {rc}")

        if not thread_id:
            raise RuntimeError("Failed to detect Codex thread_id from JSONL output.")

        reply = ""
        try:
            reply = tmp_last.read_text(encoding="utf-8").strip()
        except Exception:
            reply = ""
        if not reply:
            raise RuntimeError("Failed to read Codex last message output.")

        return CodexRunResult(session_id=thread_id, reply=reply)
    finally:
        try:
            tmp_last.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            pass


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
    parser = argparse.ArgumentParser(prog="codex-skill")
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory used to locate the project session root.",
    )
    parser.add_argument(
        "--agent",
        default=DEFAULT_AGENT_NAME,
        help=f"Target agent name inside {MANAGED_DIRNAME}/{AGENTS_FILENAME} (default: default).",
    )
    parser.add_argument("--timeout-s", type=int, default=3600, help="codex exec timeout in seconds.")
    parser.add_argument("--model", default=None, help="Optional model override for this call.")
    parser.add_argument("--reasoning-effort", default=None, help="Optional reasoning effort override for this call.")

    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in TOOL_HELP:
        sub.add_parser(name, help=TOOL_HELP[name])

    args = parser.parse_args()
    agent_name = normalize_optional_string(args.agent)
    if not agent_name:
        eprint("--agent must be a non-empty string.")
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
            "No project Codex session root is configured.",
            "Could not find an existing managed session anchor:",
            f"  - <dir>/{MANAGED_DIRNAME}/{AGENTS_FILENAME}",
            f"  - <dir>/{LEGACY_MANAGED_DIRNAME}/{AGENTS_FILENAME} (legacy, auto-migrated once)",
            f"  - <dir>/{LEGACY_MANAGED_DIRNAME}/{LEGACY_SESSION_FILENAME} (legacy, auto-migrated once)",
            f"(excluding the global {MANAGED_GLOBAL_DIR} and {CLAUDE_GLOBAL_DIR} directories).",
            "",
            "Ask the user to choose a directory to store the Codex session for this workspace.",
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
            config, _agent, migration_notice = resolve_agents_for_command(
                repo_root,
                agent_name,
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
            f"Target agent slot: {agent_name}",
            f"Config path: {agents_file_path(repo_root)}",
        ]
        if payload.caller_patch is not None:
            lines.append("Updated: caller")
        if payload.shared_stages_patch is not None:
            lines.append("Updated: shared_stages")
        if payload.agents_patch is not None:
            lines.append(
                "Updated agents: " + ", ".join(patch["name"] for patch in payload.agents_patch)
            )
        sys.stdout.write(
            format_output_for_caller(
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

        channel_names = ", ".join(agent.name for agent in config.agents) if config.agents else "(none)"
        if created_canonical:
            status_line = "Created a canonical managed config because no prior managed config was present."
        elif migration_notice:
            status_line = "Normalized existing managed state into the canonical config."
        else:
            status_line = "Canonical managed config is already up to date."
        lines = [
            "update-config applied.",
            status_line,
            f"Config path: {agents_file_path(repo_root)}",
            f"Managed channels: {channel_names}",
        ]
        sys.stdout.write(
            format_output_for_caller(
                repo_root,
                config,
                tool="update-config",
                full_reminder=True,
                reply="\n".join(lines),
                migration_notice=migration_notice,
            )
        )
        return 0

    if args.cmd == "dangerous-new-session":
        try:
            payload = parse_dangerous_new_session_payload(stdin_text)
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / MANAGED_DIRNAME).mkdir(parents=True, exist_ok=True)
            config, agent, migration_notice = resolve_agents_for_command(
                repo_root,
                agent_name,
                default_model=effective_default_model,
                default_reasoning_effort=effective_default_reasoning_effort,
            )
            previous_session_id = agent.session_id
            effective_model = payload.model or agent.model or effective_default_model
            effective_reasoning_effort = (
                payload.reasoning_effort
                or agent.reasoning_effort
                or effective_default_reasoning_effort
            )
            next_description = payload.agent_description or agent.description
            if payload.target_session_id:
                current_session_id = payload.target_session_id
                previous_session_ids = update_previous_session_ids_for_replacement(
                    agent.previous_session_ids,
                    previous_session_id,
                    current_session_id,
                )
                switched_to_existing = True
            else:
                prompt = build_dangerous_new_session_prompt(payload.user_permission)
                result = run_codex(
                    repo_root=repo_root,
                    session_id=None,
                    prompt=prompt,
                    sandbox_mode=SANDBOX_READ_ONLY,
                    timeout_s=args.timeout_s,
                    model=effective_model,
                    reasoning_effort=effective_reasoning_effort,
                )
                current_session_id = result.session_id
                try_promote_exec_session_to_cli(current_session_id)
                previous_session_ids = update_previous_session_ids_for_replacement(
                    agent.previous_session_ids,
                    previous_session_id,
                    current_session_id,
                )
                switched_to_existing = False
            updated_agent = build_agent_config(
                agent.name,
                description=next_description,
                focus=agent.focus,
                baseline=agent.baseline,
                extra_context=agent.extra_context,
                stage_guidance=agent.stage_guidance,
                can_mutate=agent.can_mutate,
                session_id=current_session_id,
                model=effective_model,
                reasoning_effort=effective_reasoning_effort,
                previous_session_ids=previous_session_ids,
                reminder_turn_count=0,
            )
            persist_agents_for_command(repo_root, config, updated_agent)
        except Exception as exc:
            eprint(str(exc))
            return 1

        lines = [
            "dangerous-new-session authorized.",
            f"Target agent: {agent_name}",
            (
                f"Managed agent now points to target session id: {current_session_id}"
                if switched_to_existing
                else f"Managed agent now points to fresh session id: {current_session_id}"
            ),
            "Do not call raw `codex` directly and do not edit the managed agent config manually.",
        ]
        if previous_session_ids:
            lines.append(
                "Recorded previous session ids for this agent (newest first): "
                + ", ".join(previous_session_ids)
            )
        else:
            lines.append("There was no prior managed session id for this agent to record.")
        updated_config = read_skill_config(repo_root)
        sys.stdout.write(
            format_output_for_caller(
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
        config, agent, migration_notice = resolve_agents_for_command(
            repo_root,
            agent_name,
            default_model=effective_default_model,
            default_reasoning_effort=effective_default_reasoning_effort,
        )
    except Exception as exc:
        eprint(str(exc))
        return 1

    session_id = agent.session_id
    model = args.model or agent.model or DEFAULT_MODEL
    reasoning_effort = args.reasoning_effort or agent.reasoning_effort or DEFAULT_REASONING_EFFORT
    init_mode: Optional[str] = None
    turn_index = collaborative_turn_index(args.cmd, agent)
    full_reminder = should_use_full_reminder(args.cmd, turn_index)

    if args.cmd == "request-mutation" and not agent.can_mutate:
        eprint(
            "\n".join(
                [
                    f"Channel '{agent.name}' is configured with can_mutate: false.",
                    "request-mutation is only allowed for a mutate-capable channel.",
                    "Choose a different channel or update the channel config through configure.",
                ]
            )
        )
        return 1

    try:
        if args.cmd == "init":
            prompt, init_mode = build_init_prompt(repo_root, config, agent, stdin_text)
        else:
            prompt = build_prompt(
                repo_root,
                config,
                agent,
                args.cmd,
                stdin_text,
                full_reminder=full_reminder,
            )
        sandbox_mode = resolve_codex_exec_sandbox(args.cmd, stdin_text)
        result = run_codex(
            repo_root=repo_root,
            session_id=session_id,
            prompt=prompt,
            sandbox_mode=sandbox_mode,
            timeout_s=args.timeout_s,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    except Exception as exc:
        if session_id and looks_like_missing_thread_error(str(exc)):
            eprint(
                "\n".join(
                    [
                        str(exc),
                        "",
                        f"The managed agent '{agent_name}' has a stored session id locally, but Codex could not resume it.",
                        "Do not manually delete or replace the managed agent config and do not call raw `codex` directly.",
                        "If the user explicitly wants to abandon this continuity and start fresh, run "
                        "<skill_root>/bin/codex-skill-dangerous-new-session.",
                    ]
                )
            )
        else:
            eprint(str(exc))
        return 1

    updated_agent = replace(
        agent,
        session_id=result.session_id,
        model=agent.model or model,
        reasoning_effort=agent.reasoning_effort or reasoning_effort,
        reminder_turn_count=(
            0
            if args.cmd == "init"
            else agent.reminder_turn_count + 1
            if args.cmd in {"chat", "review-my-plan", "review-my-work", "work-sync", "request-mutation"}
            else agent.reminder_turn_count
        ),
        updated_at=iso_now(),
    )
    persist_agents_for_command(repo_root, config, updated_agent)
    try_promote_exec_session_to_cli(result.session_id)

    if init_mode is not None:
        try:
            result.reply = validate_init_reply(init_mode, result.reply)
        except Exception as exc:
            eprint(str(exc))
            return 1
    elif args.cmd == "review-my-plan":
        try:
            result.reply = validate_review_my_plan_reply(result.reply)
        except Exception as exc:
            eprint(str(exc))
            return 1
    elif args.cmd == "review-my-work":
        try:
            result.reply = validate_review_my_work_reply(result.reply)
        except Exception as exc:
            eprint(str(exc))
            return 1
    elif args.cmd == "work-sync":
        try:
            result.reply = validate_work_sync_reply(result.reply)
        except Exception as exc:
            eprint(str(exc))
            return 1

    sys.stdout.write(
        format_output_for_caller(
            repo_root,
            config,
            tool=args.cmd,
            full_reminder=full_reminder if args.cmd != "init" else True,
            reply=result.reply,
            migration_notice=migration_notice,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

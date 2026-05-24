#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
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
INIT_MUTATION_OWNER_FIELD = "mutation_owner"
INIT_MUTATION_OWNER_CLAUDE = "claude"
INIT_MUTATION_OWNER_CODEX = "codex"
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
INIT_TASK_REPLY_TITLE = "Task Understanding Reply"
INIT_RECOVERY_REPLY_TITLE = "Context Recovery Reply"
REVIEW_PLAN_REPLY_TITLE = "Plan Review Reply"
REVIEW_WORK_REPLY_TITLE = "Work Review Reply"
WORK_SYNC_REPLY_TITLE = "Discussion Reply"
WORK_SYNC_PLAN_TITLE = "Plan"
SANDBOX_READ_ONLY = "read-only"
SANDBOX_WORKSPACE_WRITE = "workspace-write"
SANDBOX_DANGER_FULL_ACCESS = "danger-full-access"

TOOL_HELP = {
    "init": "Bootstrap Codex collaboration for a new task or recovery sync (reads JSON from stdin).",
    "chat": "Claude-mutates discussion / disagreement resolution (reads JSON from stdin).",
    "review-my-plan": "Claude-mutates mode: Codex reviews Claude's plan without mutating state (reads JSON from stdin).",
    "review-my-work": "Claude-mutates mode: Codex reviews Claude's work without mutating state (reads JSON from stdin).",
    "work-sync": "Codex-mutates sync turn for discussion, plan output, and review response (reads JSON from stdin).",
    "request-mutation": "Codex-mutates mode: Codex performs one approved mutation step (reads JSON from stdin).",
    "dangerous-new-session": "Explicitly authorize discarding continuity and starting a fresh managed Codex session (reads JSON from stdin).",
}


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


CLAUDE_GLOBAL_DIR = (Path.home() / ".claude").resolve()


def is_global_claude_dir(claude_dir: Path) -> bool:
    try:
        return claude_dir.resolve() == CLAUDE_GLOBAL_DIR
    except Exception:
        return str(claude_dir) == str(CLAUDE_GLOBAL_DIR)


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
    file or a one-time fresh-session authorization.

    IMPORTANT:
    - Never treat the global Claude Code config directory (~/.claude) as a project root.
    - `.claude/codex_session.json` and `.claude/codex_session_intent.json` are stable anchors.
      `.claude/` alone can exist at many levels for other purposes (local guidelines),
      so we do not auto-pick based on `.claude/` alone.
    """
    for p in iter_ancestors(start):
        claude_dir = p / ".claude"
        if is_global_claude_dir(claude_dir):
            continue
        if (
            (claude_dir / "codex_session.json").is_file()
            or (claude_dir / "codex_session_intent.json").is_file()
        ):
            return p
    return None


def candidate_roots_with_claude_dir(start: Path, limit: int = 5) -> list[Path]:
    candidates: list[Path] = []
    for p in iter_ancestors(start):
        claude_dir = p / ".claude"
        if is_global_claude_dir(claude_dir):
            continue
        if claude_dir.is_dir():
            candidates.append(p)
            if len(candidates) >= limit:
                break
    return candidates


def session_file_path(repo_root: Path) -> Path:
    return repo_root / ".claude" / "codex_session.json"


def session_intent_file_path(repo_root: Path) -> Path:
    return repo_root / ".claude" / "codex_session_intent.json"


def read_session_id(repo_root: Path) -> Optional[str]:
    path = session_file_path(repo_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            sid = data.get("session_id")
            if isinstance(sid, str) and sid:
                return sid
    except Exception:
        return None
    return None


def write_session_id(repo_root: Path, session_id: str) -> None:
    path = session_file_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "updated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_session_intent(repo_root: Path) -> Optional[dict]:
    path = session_intent_file_path(repo_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_session_intent(repo_root: Path, permission_text: str) -> None:
    path = session_intent_file_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "action": "dangerous-new-session",
        "user_permission": permission_text,
        "updated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def clear_session_intent(repo_root: Path) -> None:
    try:
        session_intent_file_path(repo_root).unlink(missing_ok=True)  # type: ignore[call-arg]
    except Exception:
        return


@dataclass(frozen=True)
class InitPayload:
    mode: str
    background: str
    mutation_owner: str


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


def parse_init_payload(stdin_text: str) -> InitPayload:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError(
            "Init input is empty. Provide JSON with exactly one of: task_background or "
            "recovery_background, plus mutation_owner."
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
        INIT_MUTATION_OWNER_FIELD,
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

    mutation_owner = obj.get(INIT_MUTATION_OWNER_FIELD)
    if mutation_owner not in {INIT_MUTATION_OWNER_CLAUDE, INIT_MUTATION_OWNER_CODEX}:
        raise ValueError("Init field mutation_owner must be exactly 'claude' or 'codex'.")

    return InitPayload(
        mode=mode,
        background=value.strip(),
        mutation_owner=mutation_owner,
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

    allowed_keys = {DANGEROUS_NEW_SESSION_PERMISSION_FIELD}
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

    return DangerousNewSessionPayload(user_permission=user_permission.strip())


def load_prompt_asset(name: str) -> str:
    path = PROMPTS_DIR / name
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing prompt asset: {path}") from exc
    if not text:
        raise RuntimeError(f"Prompt asset is empty: {path}")
    return text


def build_init_prompt(stdin_text: str) -> tuple[str, str]:
    payload = parse_init_payload(stdin_text)
    if payload.mode == "task":
        prompt_name = (
            "init-task-claude.md"
            if payload.mutation_owner == INIT_MUTATION_OWNER_CLAUDE
            else "init-task-codex.md"
        )
        label = "Task background from Claude:"
    else:
        prompt_name = (
            "init-recovery-claude.md"
            if payload.mutation_owner == INIT_MUTATION_OWNER_CLAUDE
            else "init-recovery-codex.md"
        )
        label = "Recovery background from Claude:"

    prompt = "\n\n".join(
        [
            load_prompt_asset(prompt_name),
            label,
            payload.background,
        ]
    ).strip() + "\n"

    return prompt, payload.mode


def build_review_my_plan_prompt(stdin_text: str) -> str:
    payload = parse_review_my_plan_payload(stdin_text)
    parts = [
        load_prompt_asset("review-my-plan.md"),
        "Plan for review from Claude:",
        payload.plan_for_review,
    ]

    if payload.new_information:
        parts.extend(
            [
                "New information from Claude:",
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

    return "\n\n".join(parts).strip() + "\n"


def build_chat_prompt(stdin_text: str) -> str:
    payload = parse_chat_payload(stdin_text)
    parts = [
        load_prompt_asset("chat.md"),
        "Message from Claude:",
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

    return "\n\n".join(parts).strip() + "\n"


def build_review_my_work_prompt(stdin_text: str) -> str:
    payload = parse_review_my_work_payload(stdin_text)
    parts = [
        load_prompt_asset("review-my-work.md"),
        "Work for review from Claude:",
        payload.work_for_review,
    ]

    if payload.new_information:
        parts.extend(
            [
                "New information from Claude:",
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

    return "\n\n".join(parts).strip() + "\n"


def build_work_sync_prompt(stdin_text: str) -> str:
    payload = parse_work_sync_payload(stdin_text)
    parts = [
        load_prompt_asset("work-sync.md"),
        "Sync message from Claude:",
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

    return "\n\n".join(parts).strip() + "\n"


def build_request_mutation_prompt(stdin_text: str) -> str:
    payload = parse_request_mutation_payload(stdin_text)
    sandbox_note = (
        "Execution sandbox for this turn: workspace-write (default mutation sandbox)."
        if payload.sandbox_mode == REQUEST_MUTATION_SANDBOX_DEFAULT
        else "Execution sandbox for this turn: danger-full-access (explicit full-access escalation approved by Claude)."
    )
    parts = [
        load_prompt_asset("request-mutation.md"),
        sandbox_note,
        "Approved mutation from Claude:",
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

    return "\n\n".join(parts).strip() + "\n"


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


def build_prompt(tool: str, stdin_text: str) -> str:
    if tool == "init":
        prompt, _mode = build_init_prompt(stdin_text)
        return prompt
    if tool == "chat":
        return build_chat_prompt(stdin_text)
    if tool == "review-my-plan":
        return build_review_my_plan_prompt(stdin_text)
    if tool == "review-my-work":
        return build_review_my_work_prompt(stdin_text)
    if tool == "work-sync":
        return build_work_sync_prompt(stdin_text)
    if tool == "request-mutation":
        return build_request_mutation_prompt(stdin_text)
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


def ensure_unique_trash_destination(filename: str) -> Path:
    trash_dir = Path.home() / ".Trash"
    trash_dir.mkdir(parents=True, exist_ok=True)

    candidate = trash_dir / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        numbered = trash_dir / f"{stem}-{counter}{suffix}"
        if not numbered.exists():
            return numbered
        counter += 1


def archive_existing_session_file(repo_root: Path) -> Optional[Path]:
    src = session_file_path(repo_root)
    if not src.exists():
        return None
    dest = ensure_unique_trash_destination(src.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dest)
    return dest


def explain_missing_session(
    repo_root: Path,
    cmd: str,
    has_pending_intent: bool,
) -> str:
    session_path = session_file_path(repo_root)
    dangerous_cmd = "<skill_root>/bin/codex-skill-dangerous-new-session"
    lines = [
        "No managed Codex session is available for this workspace.",
        f"Expected session file: {session_path}",
        "",
        "Session continuity is wrapper-managed. Do not call raw `codex` directly and do not manually edit or delete the managed session file.",
    ]
    if has_pending_intent:
        lines.extend(
            [
                "",
                "A dangerous new session has already been authorized for this workspace.",
                "Run `init` next to bootstrap the fresh managed Codex session before using any other codex-skill command.",
            ]
        )
        return "\n".join(lines)

    if cmd == "init":
        lines.extend(
            [
                "",
                "init must not silently create a fresh managed Codex session.",
                "Starting a fresh managed Codex session changes continuity and is treated as destructive.",
                "Only do that after the user explicitly asks for a fresh start, replacement, or continuity reset.",
                f"Then run {dangerous_cmd} first, and rerun init after it succeeds.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "This command can only continue an existing managed Codex session.",
                "If the user explicitly wants to discard continuity and start fresh, run "
                f"{dangerous_cmd} first, then run init, then continue with the normal workflow.",
            ]
        )
    return "\n".join(lines)


def looks_like_missing_thread_error(message: str) -> bool:
    lowered = message.lower()
    return "thread" in lowered and "not found" in lowered


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
    parser.add_argument("--timeout-s", type=int, default=3600, help="codex exec timeout in seconds.")
    parser.add_argument("--model", default=None, help="Optional model override for this call.")
    parser.add_argument("--reasoning-effort", default=None, help="Optional reasoning effort override for this call.")

    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in TOOL_HELP:
        sub.add_parser(name, help=TOOL_HELP[name])

    args = parser.parse_args()

    cwd_explicit = args.cwd is not None
    start_cwd = Path(args.cwd).expanduser() if cwd_explicit else Path.cwd()

    repo_root = find_session_root(start_cwd)
    if repo_root is None:
        if cwd_explicit:
            chosen = start_cwd.expanduser().resolve()
            chosen_claude_dir = chosen / ".claude"
            if (
                args.cmd == "dangerous-new-session"
                and not is_global_claude_dir(chosen_claude_dir)
            ):
                repo_root = chosen
            elif chosen_claude_dir.is_dir() and not is_global_claude_dir(chosen_claude_dir):
                repo_root = chosen

    if repo_root is None:
        candidates = candidate_roots_with_claude_dir(start_cwd)
        lines = [
            "No project Codex session root is configured.",
            "Could not find an existing managed session anchor:",
            "  - <dir>/.claude/codex_session.json",
            "  - <dir>/.claude/codex_session_intent.json",
            f"(excluding the global Claude Code directory: {CLAUDE_GLOBAL_DIR}).",
            "",
            "Ask the user to choose a directory to store the Codex session for this workspace.",
        ]
        if candidates:
            lines.append("Candidate directories that already contain a .claude/ directory (closest first):")
            for c in candidates:
                lines.append(f"  - {c}")
            lines.append("Then rerun this command with: --cwd <chosen_dir>")
        else:
            lines.append("No .claude/ directory was found in parent directories (excluding the global one).")
            lines.append(
                "Ask the user to choose a directory. For a fresh managed session, "
                "use codex-skill-dangerous-new-session with: --cwd <chosen_dir>; it will create <chosen_dir>/.claude/ if needed."
            )
        raise RuntimeError("\n".join(lines))

    stdin_text = sys.stdin.read()
    if not stdin_text.strip():
        eprint("Empty input. Provide content via stdin.")
        return 2

    if args.cmd == "dangerous-new-session":
        try:
            payload = parse_dangerous_new_session_payload(stdin_text)
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / ".claude").mkdir(parents=True, exist_ok=True)
            archived = archive_existing_session_file(repo_root)
            write_session_intent(repo_root, payload.user_permission)
        except Exception as exc:
            eprint(str(exc))
            return 1

        lines = [
            "dangerous-new-session authorized.",
            "The next step must be init. That init call will be allowed to create a fresh managed Codex session for this workspace.",
            "Do not call raw `codex` directly and do not edit the managed session file manually.",
        ]
        if archived is not None:
            lines.insert(1, f"Archived prior managed session file to: {archived}")
        else:
            lines.insert(1, "No prior managed session file was present to archive.")
        sys.stdout.write("\n".join(lines) + "\n")
        return 0

    session_id = read_session_id(repo_root)
    session_intent = read_session_intent(repo_root)
    has_pending_intent = session_intent is not None
    allow_fresh_session = args.cmd == "init" and session_id is None and has_pending_intent

    if session_id is None and not allow_fresh_session:
        eprint(explain_missing_session(repo_root, args.cmd, has_pending_intent))
        return 1

    if session_id is None and has_pending_intent and args.cmd != "init":
        eprint(explain_missing_session(repo_root, args.cmd, has_pending_intent))
        return 1

    model = args.model or DEFAULT_MODEL
    reasoning_effort = args.reasoning_effort or DEFAULT_REASONING_EFFORT
    init_mode: Optional[str] = None

    try:
        if args.cmd == "init":
            prompt, init_mode = build_init_prompt(stdin_text)
        else:
            prompt = build_prompt(args.cmd, stdin_text)
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
                        "The managed Codex session id exists locally, but Codex could not resume it.",
                        "Do not manually delete or replace the session file and do not call raw `codex` directly.",
                        "If the user explicitly wants to abandon this continuity and start fresh, run "
                        "<skill_root>/bin/codex-skill-dangerous-new-session, then rerun init.",
                    ]
                )
            )
        else:
            eprint(str(exc))
        return 1

    write_session_id(repo_root, result.session_id)
    if allow_fresh_session:
        clear_session_intent(repo_root)
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

    sys.stdout.write(result.reply.rstrip() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

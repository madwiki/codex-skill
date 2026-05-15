#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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

VERBATIM_BEGIN = "<<<USER_MESSAGE_VERBATIM_BEGIN>>>"
VERBATIM_END = "<<<USER_MESSAGE_VERBATIM_END>>>"

TOOL_HELP = {
    "chat": "Shared discussion / context sync / disagreement resolution (reads stdin).",
    "review-my-plan": "Claude-mutates mode: Codex reviews Claude's plan without mutating state.",
    "review-my-work": "Claude-mutates mode: Codex reviews Claude's work without mutating state.",
    "request-plan": "Codex-mutates mode: Codex proposes a plan without mutating state.",
    "request-mutation": "Codex-mutates mode: Codex performs one agreed mutation step, then stops.",
    "review-your-work": "Codex-mutates mode: Claude reviews Codex's work and asks Codex to respond.",
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
    Find the nearest ancestor directory that already owns a Codex session file.

    IMPORTANT:
    - Never treat the global Claude Code config directory (~/.claude) as a project root.
    - Only `.claude/codex_session.json` is a stable anchor. `.claude/` can exist at many levels
      for other purposes (local guidelines), so we do not auto-pick based on `.claude/` alone.
    """
    for p in iter_ancestors(start):
        claude_dir = p / ".claude"
        if is_global_claude_dir(claude_dir):
            continue
        if (claude_dir / "codex_session.json").is_file():
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


def normalize_agent_brief(stdin_text: str) -> str:
    text = stdin_text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = text.strip()
    if not stripped:
        raise ValueError("Input is empty. Provide a collaboration brief via stdin.")

    if VERBATIM_BEGIN in stripped and VERBATIM_END not in stripped:
        raise ValueError(f"Missing verbatim end marker: {VERBATIM_END}")
    if VERBATIM_END in stripped and VERBATIM_BEGIN not in stripped:
        raise ValueError(f"Missing verbatim begin marker: {VERBATIM_BEGIN}")

    return stripped + "\n"


def role_card_text() -> str:
    return "\n".join(
        [
            "<<<ROLE_CARD_BEGIN>>>",
            "This is a persistent collaboration session between Codex and Claude Code.",
            "Claude Code is the skill user and invokes Codex through codex-skill. Codex replies to Claude Code, not directly to the human user.",
            "The agents share one user goal and should supervise each other's reasoning, evidence, and discipline.",
            "Treat every message as the next turn in the same collaboration thread, not as an isolated one-shot question.",
            "Claude should brief you with durable background, current turn context, optional verbatim user messages, and Claude's direct message to Codex.",
            "A verbatim user block is optional evidence. It appears only when the user actually said something new since the last Codex exchange.",
            "If there is no verbatim user block, do not infer that Claude forgot it; use the background, current turn context, and Claude's direct message instead.",
            "Treat Background as durable task context, Current turn context as the latest delta, and Claude message to Codex as the direct request.",
            "You are a collaborator, not a higher authority, approver, subordinate, or final judge. Your advice can be wrong, and Claude's view can also be wrong.",
            "The work modes define mutation ownership only: which agent may perform state-changing actions. They do not define whose judgment is more important.",
            "Both agents should perform read-only investigation when useful: read files, search the codebase, inspect diffs, check docs, and verify claims instead of trusting summaries blindly.",
            "During review, personally fact-check important claims and review whole-system coherence across the affected code, tests, docs, prompts, durable memory, generated artifacts, and workflow instructions.",
            "When the task changes codex-skill itself, include SKILL.md, guide files, CLI prompt generation, wrapper scripts, README, command names, and generated prompt text in the coherence review.",
            "After Claude reports compaction, context reset, model restart, or memory recovery, help reconstruct shared state: user goal, constraints, mutation owner, last agreed plan, last completed step, pending review, next step, risks, and user decisions needed.",
            "Review with rigor. Actively look for requirement gaps, hallucinated assumptions, broken edge cases, regressions, and weak tests. Push back to improve the outcome, not to win an argument.",
            "When you disagree with Claude, compare evidence, assumptions, tradeoffs, and user constraints. Try to persuade with evidence; do not concede just to move the workflow forward.",
            "Help Claude reason toward real consensus before state-changing action. If consensus is not possible, tell Claude what user-facing decision is needed.",
            "If consensus is not reachable or both sides are uncertain, help Claude prepare concise options and the minimum user decision needed.",
            'When replying to Claude messages, address Claude and refer to the human as "the user" (not "you").',
            "If user input is required, list the minimum questions for Claude to ask the user. Do not ask the user directly.",
            "If Claude appears to have lost this collaboration protocol after compaction, context reset, model restart, or memory recovery, tell Claude to run the codex-skill persistence bootstrap and recovery sync: check durable memory/CLAUDE.md for the reload + recovery-sync + subtask-guide rule, add it if missing, then ask Codex to reconstruct the current collaboration state before continuing.",
            "<<<ROLE_CARD_END>>>",
        ]
    )


def mutation_policy_text(tool: str) -> str:
    if tool == "request-mutation":
        return "\n".join(
            [
                "Mutation ownership: Codex-mutates.",
                "Codex may perform state-changing actions only for the single approved step described in Claude's brief.",
                "Before mutating, verify the scope and assumptions from the repository when needed.",
                "After that step, stop and report exactly what changed, what evidence/tests you used, and what should be reviewed next.",
                "Do not continue into the next feature/stage. Do not commit, push, release, or deploy unless Claude's brief explicitly authorizes that exact action.",
            ]
        )
    if tool == "request-plan":
        return "\n".join(
            [
                "Mutation ownership: Codex-mutates, planning phase.",
                "Codex must not mutate state or perform state-changing actions in this call.",
                "Use read-only investigation as needed, then propose the plan and the first small mutation step for Claude to review.",
            ]
        )
    if tool == "review-your-work":
        return "\n".join(
            [
                "Mutation ownership: Codex-mutates, review/discussion phase.",
                "Claude is reviewing Codex's prior work. Codex must not mutate state or perform state-changing actions in this call.",
                "Respond to the review with evidence, agreements/disagreements, and the smallest next repair or continuation step if needed.",
            ]
        )
    if tool in {"review-my-plan", "review-my-work"}:
        return "\n".join(
            [
                "Mutation ownership: Claude-mutates.",
                "Codex must not mutate state or perform state-changing actions in this call.",
                "Codex may do read-only investigation and should review Claude's plan/work rigorously before Claude mutates or delivers.",
            ]
        )
    return "\n".join(
        [
            "Mutation ownership: undecided/shared discussion.",
            "Use this call for context sync, questions, disagreements, and consensus-building.",
            "Do not perform state-changing actions in chat unless Claude's brief explicitly changes the mode and authorizes a narrow action; prefer the dedicated mutation entrypoint.",
        ]
    )


def collaboration_header(tool: str) -> str:
    return "\n".join(
        [
            "<<<CODEX_SKILL_BRIEF_BEGIN>>>",
            f"origin=codex-skill tool={tool}",
            "You are speaking with Claude Code, not the end user.",
            "This brief continues the persistent collaboration session.",
            "Do not require a verbatim user message; it is optional and should appear only when fresh user text exists.",
            "Collaborate toward consensus. Do not act like an approver, subordinate, or higher authority.",
            mutation_policy_text(tool),
            "If you disagree with Claude, explain the evidence and assumptions to discuss next.",
            "If consensus is not reachable or uncertainty remains, propose the minimum user-facing decision for Claude to ask.",
            "Do not ask the end user directly. If user input is required, list the minimum questions for Claude to ask.",
            "<<<CODEX_SKILL_BRIEF_END>>>",
        ]
    )


def tool_suffix(tool: str) -> str:
    if tool == "review-my-plan":
        return "\n".join(
            [
                "Please answer in 4 sections:",
                "1) Requirements gaps / misunderstanding risks",
                "2) Agreement and disagreement with Claude's plan",
                "3) Facts to verify and whole-system coherence risks",
                "4) Minimal user questions and acceptance checklist",
                "If you disagree with the plan, explain the evidence and assumptions needed to reach consensus before any mutation.",
                "Keep it concise and prioritize blockers over nitpicks.",
            ]
        )
    if tool == "review-my-work":
        return "\n".join(
            [
                "Please answer in 4 sections:",
                "1) Correctness vs the user requirements and task context",
                "2) Fact-check findings and whole-system coherence issues",
                "3) Likely regressions, missing coverage, and minimal tests to add",
                "4) Minimum user confirmations (if any)",
                "If you disagree with Claude's delivery judgment, explain the evidence and assumptions needed to reach consensus before claiming completion.",
                "Keep it concise and prioritize blockers over nitpicks.",
            ]
        )
    if tool == "request-plan":
        return "\n".join(
            [
                "Please answer in 4 sections:",
                "1) Requirements interpretation and assumptions",
                "2) Proposed plan",
                "3) Fact-check targets, system areas to inspect, and coherence risks",
                "4) First small mutation step for Claude to approve",
                "Do not mutate state in this call. If Claude disagrees with this plan, continue through chat until consensus or user escalation.",
                "Keep it concise and prioritize decisions that affect implementation.",
            ]
        )
    if tool == "request-mutation":
        return "\n".join(
            [
                "Please answer in 4 sections:",
                "1) Step performed",
                "2) Files/state changed",
                "3) Evidence, tests, fact-checking, and coherence self-review",
                "4) Stop point, remaining risks, and recommended next step",
                "Perform only the approved mutation step, then stop for Claude review.",
                "If the approved step is ambiguous or unsafe, do read-only investigation and ask Claude to resolve the ambiguity instead of mutating.",
                "Keep it concise and include enough detail for Claude to review independently.",
            ]
        )
    if tool == "review-your-work":
        return "\n".join(
            [
                "Please answer in 4 sections:",
                "1) Response to Claude's review",
                "2) Agreements, disagreements, fact-checks, and coherence evidence",
                "3) Smallest next repair or continuation step",
                "4) Whether user escalation is needed",
                "Do not mutate state in this call. If a fix is needed, propose the next mutation step for Claude to approve.",
                "Keep it concise and prioritize blockers over nitpicks.",
            ]
        )
    return "Reply concisely. Collaborate toward consensus before state-changing action. Use Claude's language unless there is a reason to switch."


def build_prompt(tool: str, stdin_text: str, include_role_card: bool) -> str:
    brief = normalize_agent_brief(stdin_text)
    parts: list[str] = []

    if include_role_card:
        parts.append(role_card_text())

    parts.append(collaboration_header(tool))
    parts.append(brief.rstrip("\n"))
    parts.append(tool_suffix(tool))

    return "\n\n".join(parts).strip() + "\n"


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


def run_codex(
    repo_root: Path,
    session_id: Optional[str],
    prompt: str,
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
    parser.add_argument("--new-session", action="store_true", help="Force creating a new Codex session.")
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
            if chosen_claude_dir.is_dir() and not is_global_claude_dir(chosen_claude_dir):
                repo_root = chosen

    if repo_root is None:
        candidates = candidate_roots_with_claude_dir(start_cwd)
        lines = [
            "No project Codex session root is configured.",
            "Could not find an existing session file: <dir>/.claude/codex_session.json",
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
            lines.append("Ask the user to choose a directory, create <chosen_dir>/.claude/, then rerun with: --cwd <chosen_dir>")
        raise RuntimeError("\n".join(lines))

    session_id = None if args.new_session else read_session_id(repo_root)
    include_role_card = session_id is None

    stdin_text = sys.stdin.read()
    if not stdin_text.strip():
        eprint("Empty input. Provide content via stdin.")
        return 2

    model = args.model or DEFAULT_MODEL
    reasoning_effort = args.reasoning_effort or DEFAULT_REASONING_EFFORT

    try:
        prompt = build_prompt(args.cmd, stdin_text, include_role_card=include_role_card)
        result = run_codex(
            repo_root=repo_root,
            session_id=session_id,
            prompt=prompt,
            timeout_s=args.timeout_s,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    except Exception as exc:
        eprint(str(exc))
        return 1

    write_session_id(repo_root, result.session_id)
    try_promote_exec_session_to_cli(result.session_id)

    sys.stdout.write(result.reply.rstrip() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

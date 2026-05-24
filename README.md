# codex-skill

A Claude Skill that lets Claude Code collaborate with a local Codex session, automatically resuming the managed session when it exists and automatically creating a new managed session when none exists yet.

## Install

Personal install:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/madwiki/codex-skill ~/.claude/skills/codex-skill
```

## What it does

- Persists and reuses the managed Codex session id via `<repo>/.claude/codex_session.json`
- Automatically creates a managed Codex session when the workspace does not have one yet
- Treats session continuity as wrapper-managed: use only `bin/codex-skill-*` commands, never raw `codex`, and never manually edit or delete the managed session file
- Uses `dangerous-new-session` only when the user explicitly wants to replace the current managed Codex session, either with a fresh one or with a specific target session id
- Requires a persistence bootstrap on skill load: verify durable memory/`CLAUDE.md` contains the reload + init + subtask-guide rule, and add it if missing
- Uses `init` as the bootstrap entrypoint for a new shared task, after Claude returns from compact or context clear, or when mutation ownership reverses between Claude and Codex
- Requires `init` to declare the current mutation-owner path explicitly through `mutation_owner: "claude"` or `mutation_owner: "codex"`
- Avoids resending durable background every turn; normal ongoing calls send only changed context and the current approved step
- Uses `chat` as the Claude-mutates discussion surface for context sync, disagreements, and consensus-building
- Uses `work-sync` as the Codex-mutates sync surface for discussion, candidate plan output, and response to Claude review
- Runs non-mutation calls under an explicit `read-only` sandbox
- Runs `request-mutation` under `workspace-write` by default, with optional `full-access` escalation when Claude explicitly requests it
- Supports two mutation-owner workflows:
  - Claude-mutates: Claude changes state; Codex reviews Claude's plan/work
  - Codex-mutates: Codex changes state in small approved steps; Claude reviews between steps
- Makes fresh user messages optional. Include a verbatim user block only when the user actually said something new since the last Codex call.
- Frames Claude and Codex as peer reviewers of the same user goal, not as leader/subordinate or approver/implementer.
- Requires review stages to include direct fact-checking and whole-system coherence checks instead of trusting the other agent's summary.
- Uses a 3600-second default timeout because Codex may inspect files, reason, compact, or resume context.

## Entrypoints

Bootstrap:

- `bin/codex-skill-dangerous-new-session`
- `bin/codex-skill-init`

Claude-mutates discussion:

- `bin/codex-skill-chat`

Claude-mutates:

- `bin/codex-skill-review-my-plan`
- `bin/codex-skill-review-my-work`

Codex-mutates:

- `bin/codex-skill-work-sync`
- `bin/codex-skill-request-mutation`

## Docs

- `SKILL.md`
- `dangerous-new-session.md`
- `init.md`
- `chat.md`
- `work-sync.md`
- `review-my-plan.md`
- `review-my-work.md`
- `request-mutation.md`

# codex-skill

A Claude Skill that lets Claude Code collaborate with a local Codex session, resuming prior context when available and falling back cleanly when it is not.

## Install

Personal install:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/madwiki/codex-skill ~/.claude/skills/codex-skill
```

## What it does

- Persists and reuses the Codex session id via `<repo>/.claude/codex_session.json` when recovery is available
- Requires a persistence bootstrap on skill load: verify durable memory/`CLAUDE.md` contains the reload + init + subtask-guide rule, and add it if missing
- Uses `init` as the bootstrap entrypoint for a new shared task or after Claude returns from compact or context clear
- Requires `init` to declare the current mutation-owner path explicitly through `mutation_owner: "claude"` or `mutation_owner: "codex"`
- Avoids resending durable background every turn; normal ongoing calls send only changed context and the current approved step
- Uses `chat` as the Claude-mutates discussion surface for context sync, disagreements, and consensus-building
- Uses `work-sync` as the Codex-mutates sync surface for discussion, candidate plan output, and response to Claude review
- Supports two mutation-owner workflows:
  - Claude-mutates: Claude changes state; Codex reviews Claude's plan/work
  - Codex-mutates: Codex changes state in small approved steps; Claude reviews between steps
- Makes fresh user messages optional. Include a verbatim user block only when the user actually said something new since the last Codex call.
- Frames Claude and Codex as peer reviewers of the same user goal, not as leader/subordinate or approver/implementer.
- Requires review stages to include direct fact-checking and whole-system coherence checks instead of trusting the other agent's summary.
- Uses a 3600-second default timeout because Codex may inspect files, reason, compact, or resume context.

## Entrypoints

Bootstrap:

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
- `init.md`
- `chat.md`
- `work-sync.md`
- `review-my-plan.md`
- `review-my-work.md`
- `request-mutation.md`

# codex-skill

A Claude Skill that lets Claude Code collaborate with a persistent local Codex session.

## Install

Personal install:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/madwiki/codex-skill ~/.claude/skills/codex-skill
```

## What it does

- Persists and reuses the Codex session id via `<repo>/.claude/codex_session.json`
- Requires a persistence bootstrap on skill load: verify durable memory/`CLAUDE.md` contains the reload + recovery-sync + subtask-guide rule, and add it if missing
- Requires a recovery chat after compaction, context reset, model restart, or memory recovery: ask Codex to reconstruct current goal, mutation owner, last agreed plan, last completed step, pending review, next step, and risks before continuing
- Treats `chat` as the shared collaboration path for context sync, disagreements, and consensus-building
- Supports two mutation-owner workflows:
  - Claude-mutates: Claude changes state; Codex reviews Claude's plan/work
  - Codex-mutates: Codex changes state in small approved steps; Claude reviews between steps
- Makes fresh user messages optional. Include a verbatim user block only when the user actually said something new since the last Codex call.
- Frames Claude and Codex as peer reviewers of the same user goal, not as leader/subordinate or approver/implementer.
- Uses a 3600-second default timeout because Codex may inspect files, reason, compact, or resume context.

## Entrypoints

Shared:

- `bin/codex-skill-chat`

Claude-mutates:

- `bin/codex-skill-review-my-plan`
- `bin/codex-skill-review-my-work`

Codex-mutates:

- `bin/codex-skill-request-plan`
- `bin/codex-skill-request-mutation`
- `bin/codex-skill-review-your-work`

## Docs

- `SKILL.md`
- `chat.md`
- `review-my-plan.md`
- `review-my-work.md`
- `request-plan.md`
- `request-mutation.md`
- `review-your-work.md`

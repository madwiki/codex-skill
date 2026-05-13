# codex-skill

A Claude Skill that uses the local `codex` CLI as a persistent collaborator for Claude Code.

## Install

Personal install:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/madwiki/codex-skill ~/.claude/skills/codex-skill
```

## What it does

- Provides three entrypoints: `chat`, `plan`, `review`
- Automatically persists and reuses the Codex session id via `<repo>/.claude/codex_session.json`
- Treats `chat` as the normal collaboration path; `plan` and `review` are specialized chat modes
- Lets Claude Code brief Codex with background, since-last context, optional fresh user messages, and the current agent request
- Uses a 3600-second default timeout because Codex may need to inspect files, reason, compact, or resume context

## Use

- The skill can trigger automatically based on its `description` keywords.
- If it doesn't trigger, explicitly say: "use the codex-skill skill".
- Do not fabricate a user message. Include `<<<USER_MESSAGE_VERBATIM_BEGIN>>>` only when the user actually said something new since the last Codex call.

Docs:

- `SKILL.md`
- `chat.md`
- `plan.md`
- `review.md`

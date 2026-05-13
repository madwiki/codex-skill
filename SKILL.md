---
name: codex-skill
description: >
  [AUTO-TRIGGER] Use /codex-skill as a persistent Codex collaborator for AI-to-AI task coordination. Use chat for normal progress sync,
  uncertainty, requirement changes, stuck states, and disagreements. Use plan before publishing plans/designs/architecture, and review before
  commit/PR/merge/release/deploy or saying done/shipped.
---

# codex-skill

Use Codex as a persistent second agent, not as a one-shot checker. Claude Code keeps doing the work, but periodically briefs Codex so the two agents can maintain shared task state, challenge assumptions, and coordinate the next step.

When you load this skill, decide which guide to read next.

## What to load next (progressive disclosure)

- Normal collaboration, status sync, uncertainty, requirement changes, stuck states, or disagreement → read `chat.md` (path: `<skill_root>/chat.md`)
- Starting to draft or publish a plan/design/architecture (including before ExitPlanMode) → read `plan.md` (path: `<skill_root>/plan.md`)
- About to finalize delivery (done/PR/commit/merge/release/deploy) → read `review.md` (path: `<skill_root>/review.md`)
- If unsure → use `chat.md`

## Continuity contract

Every call should feel like the next message in the same collaboration thread:

- Tell Codex what happened since the last Codex reply: what you told the user, what the user said, what you did, what changed, and what you now believe.
- Include `Background` only for stable task/project context. The first call may need more background; later calls should include only new or changed background.
- Include a verbatim user message only when the user actually said something new since the last Codex call. If there is no fresh user message, omit the block entirely. Never invent or restate a user message just to fill a template.
- When a verbatim user message is included, explain the situation around it in the turn context so Codex understands why the user said it.
- Put your actual request, judgment, plan, or concern in the agent message. Codex is collaborating with the agent and should reply to the agent, not to the end user.

## Patience

The Codex side may need to inspect files, reason through a large context, or compact/resume its own session. Do not treat this as a short RPC-style call. The scripts use a long default timeout; wait patiently unless there is a real failure.

## Paths

- `<skill_root>` = the directory containing this `SKILL.md` (common: `~/.claude/skills/codex-skill`)
- Guides:
  - `<skill_root>/plan.md`
  - `<skill_root>/review.md`
  - `<skill_root>/chat.md`

Follow the chosen guide. It contains the command path and the collaboration message template.

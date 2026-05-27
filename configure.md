# configure

Use this command when the caller needs to update the managed Codex Skill configuration instead of editing `.claude/codex_agents.json` by hand.

This command does **not** mutate task files and does **not** change the current session continuity by itself. It only updates the structured config that future wrapper calls will load.

The caller must not call raw `codex` directly and must not manually edit, delete, or replace `<repo>/.claude/codex_agents.json`.

## What this command can update

- top-level `caller` text fields:
  - `baseline`
  - `working_style`
  - `extra_context`
  - `stage_guidance`
- top-level `shared_stages`
- top-level `work_modes`
- agent metadata inside `agents`

Agent patches are applied by `name`. If the named agent does not exist yet, this command creates it with empty session continuity and the provided metadata.

These text fields are caller-owned guidance content. The wrapper still defines the workflow mechanics separately through the skill prompts and command contracts.

Ownership boundaries:

- `caller.*` is caller-side guidance. It is returned to the caller in wrapper output and is not injected into Codex prompts.
- `shared_stages` and `work_modes.*.stages` are common stage guidance. They may be shown on both sides.
- `agents[*].*` is agent-side guidance. It is injected only into the currently targeted Codex agent prompt.
- Wrapper-injected system guidance is labeled `Codex Skill Reminder`.
- User-configured guidance is labeled `User Reminder`.
- `init` always carries the full reminder text. Normal ongoing turns use a per-agent 3-turn cadence: full reminder on turns 1, 4, 7, ... and a brief reminder on the two turns in between.

## Input contract

Call `configure` with JSON on stdin.

You may send any subset of these fields:

```json
{
  "caller": {
    "baseline": "Optional. Non-empty string or null.",
    "working_style": "Optional. Non-empty string or null.",
    "extra_context": "Optional. Non-empty string or null.",
    "stage_guidance": {
      "review-my-plan": "Optional. Non-empty string or null."
    }
  },
  "shared_stages": {
    "init": "Optional. Non-empty string or null."
  },
  "work_modes": {
    "caller_mutates": {
      "stages": {
        "review-my-plan": "Optional. Non-empty string or null."
      }
    },
    "codex_mutates": {
      "stages": {
        "work-sync": "Optional. Non-empty string or null."
      }
    }
  },
  "agents": [
    {
      "name": "reviewer-a",
      "description": "Optional. Non-empty string or null.",
      "focus": "Optional. Non-empty string or null.",
      "baseline": "Optional. Non-empty string or null.",
      "extra_context": "Optional. Non-empty string or null.",
      "stage_guidance": {
        "review-my-plan": "Optional. Non-empty string or null."
      },
      "model": "Optional. Non-empty string or null.",
      "reasoning_effort": "Optional. Non-empty string or null."
    }
  ]
}
```

Rules:

- Omitted fields stay unchanged.
- `null` clears a configurable text field or removes a stage-guidance entry.
- `agents[].name` is required.
- `configure` does not accept direct `session_id` edits. Use `dangerous-new-session.md` for continuity replacement.

## Unified file references

If any text field needs to point at a large file instead of repeating its full content, use the unified file-reference format:

```text
[[REF:<relative-path>]]
[[REF:<relative-path>::<locator>]]
```

Examples:

```text
[[REF:.claude/codex-skill-refs/rules-77.md]]
[[REF:.claude/codex-skill-refs/rules-77.md::Rule 5]]
[[REF:docs/architecture.md::Event Pipeline]]
```

Rules:

- Use workspace-relative paths.
- Prefer direct text for short or medium guidance. Use `[[REF:...]]` only when the source material is large enough that repeating it every turn would waste context.
- Referenced files must already exist inside the workspace root.
- References are pointers, not inline expansion.
- `.claude/codex-skill-refs/` is the conventional place for long Codex Skill reference documents, but any workspace file may be referenced with the same syntax.
- After compact, context clear, session replacement, or any continuity loss, if Codex cannot confidently identify the referenced source and relevant content, it must re-read the referenced file before relying on it.
- The caller decides when to keep content inline and when to switch to `[[REF:...]]`. The wrapper only provides the reference protocol and reminder behavior.

## Output contract

The wrapper replies in plain text. It should tell the caller:

- that the config update was applied
- which top-level sections were updated
- which agent names were updated
- whether a legacy config was migrated during this command

## Run

```bash
<skill_root>/bin/codex-skill-configure < configure.json
```

Named agent example:

```bash
<skill_root>/bin/codex-skill-configure --agent reviewer-a < configure.json
```

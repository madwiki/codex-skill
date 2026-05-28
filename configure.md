# configure

Use this command when the caller needs to update the managed config instead of editing `.claude/codex_agents.json` by hand.

This command does **not** mutate task files and does **not** change current session continuity by itself.

## What it can update

- top-level `caller`
- top-level `shared_stages`
- channel metadata inside `agents`

Channel patches are applied by `name`. If the named channel does not exist yet, this command creates it with empty continuity and the provided metadata.

Important fields:

- `caller.can_mutate`: reminder-only
- `agents[].can_mutate`: enforced by `request-mutation`

## Input contract

```json
{
  "caller": {
    "baseline": "Optional. Non-empty string or null.",
    "working_style": "Optional. Non-empty string or null.",
    "extra_context": "Optional. Non-empty string or null.",
    "stage_guidance": {
      "review-my-plan": "Optional. Non-empty string or null."
    },
    "can_mutate": false
  },
  "shared_stages": {
    "chat": "Optional. Non-empty string or null."
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
      "can_mutate": false,
      "model": "Optional. Non-empty string or null.",
      "reasoning_effort": "Optional. Non-empty string or null."
    }
  ]
}
```

Rules:

- omitted fields stay unchanged
- `null` clears configurable text fields or removes stage-guidance entries
- `agents[].name` is required
- `can_mutate` must be a boolean when provided
- `configure` does not accept direct `session_id` edits

## References

Use `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]` for large external guidance.

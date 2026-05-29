# configure

Use this command when the mams_invoker needs to update the managed config instead of editing `.mad-agent-mesh/mams_channels.json` by hand.

This command does **not** mutate task files and does **not** change current session continuity by itself.

## What it can update

- top-level `mams_invoker`
- top-level `shared_stages`
- mams_channel metadata inside `mams_channels`

Mams Channel patches are applied by `name`. If the named mams_channel does not exist yet, this command creates it with empty continuity and the provided metadata.

Important fields:

- `mams_invoker.can_mutate`: reminder-only
- `mams_channels[].can_mutate`: enforced by `execute-this-plan` and `execute-this-plan-part`
- `mams_channels[].runner`: chooses the managed runner for that channel (`codex` or `claude-code`)
- `mams_channels[].runner_config`: optional runner-specific adapter config

## Input contract

```json
{
  "mams_invoker": {
    "baseline": "Optional. Non-empty string or null.",
    "working_style": "Optional. Non-empty string or null.",
    "extra_context": "Optional. Non-empty string or null.",
    "stage_guidance": {
      "review-this-plan": "Optional. Non-empty string or null."
    },
    "can_mutate": false
  },
  "shared_stages": {
    "sync": "Optional. Non-empty string or null."
  },
  "mams_channels": [
    {
      "name": "reviewer-a",
      "description": "Optional. Non-empty string or null.",
      "focus": "Optional. Non-empty string or null.",
      "baseline": "Optional. Non-empty string or null.",
      "extra_context": "Optional. Non-empty string or null.",
      "stage_guidance": {
        "review-this-plan": "Optional. Non-empty string or null."
      },
      "can_mutate": false,
      "runner": "codex",
      "runner_config": {
        "permission_mode": "Optional. Claude Code only. Non-empty string when provided.",
        "extra_args": ["Optional extra runner CLI args."]
      },
      "model": "Optional. Non-empty string or null.",
      "reasoning_effort": "Optional. Non-empty string or null."
    }
  ]
}
```

Rules:

- omitted fields stay unchanged
- `null` clears configurable text fields or removes stage-guidance entries
- `mams_channels[].name` is required
- `can_mutate` must be a boolean when provided
- `runner` must be `codex` or `claude-code` when provided
- `runner_config` must be a JSON object when provided
- `configure` does not accept direct `session_id` edits

## References

Use `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]` for large external guidance.

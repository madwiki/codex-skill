# configure

Use `configure` to patch managed channel metadata instead of editing `.mad-agent-mesh/mams_channels.json` by hand.

This command does not mutate task files and does not change session continuity by itself.

## What it can update

- `mams_channels[*].prompt_profile`
- `mams_channels[*].can_mutate`
- `mams_channels[*].runner`
- `mams_channels[*].runner_config`
- `mams_channels[*].model`
- `mams_channels[*].reasoning_effort`

Channel patches are applied by `name`. If a named channel does not exist yet, this command creates it.

## Input contract

```json
{
  "mams_channels": [
    {
      "name": "reviewer-a",
      "prompt_profile": {
        "public": {
          "description": "Optional. Non-empty string or null.",
          "focus": "Optional. Non-empty string or null.",
          "baseline": "Optional. Non-empty string or null.",
          "extra_context": "Optional. Non-empty string or null."
        },
        "plan_stage": {
          "baseline": "Optional. Non-empty string or null."
        },
        "execution_stage": {
          "baseline": "Optional. Non-empty string or null."
        }
      },
      "can_mutate": false,
      "runner": "codex",
      "runner_config": {
        "permission_mode": "Optional. Claude Code only.",
        "extra_args": ["Optional extra runner CLI args."]
      },
      "model": "Optional. Non-empty string or null.",
      "reasoning_effort": "Optional. Non-empty string or null."
    }
  ]
}
```

Rules:

- `mams_channels` is required
- `mams_channels[].name` is required
- omitted fields stay unchanged
- `null` clears configurable text fields
- `can_mutate` must be a boolean when provided
- `runner` must be `codex` or `claude-code` when provided
- `runner_config` must be a JSON object when provided
- `configure` does not accept direct `session_id` edits

# configure

Use this command when the cxsk_invoker needs to update the managed config instead of editing `.codex-skill/cxsk_channels.json` by hand.

This command does **not** mutate task files and does **not** change current session continuity by itself.

## What it can update

- top-level `cxsk_invoker`
- top-level `shared_stages`
- cxsk_channel metadata inside `cxsk_channels`

Cxsk Channel patches are applied by `name`. If the named cxsk_channel does not exist yet, this command creates it with empty continuity and the provided metadata.

Important fields:

- `cxsk_invoker.can_mutate`: reminder-only
- `cxsk_channels[].can_mutate`: enforced by `request-mutation`

## Input contract

```json
{
  "cxsk_invoker": {
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
  "cxsk_channels": [
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
- `cxsk_channels[].name` is required
- `can_mutate` must be a boolean when provided
- `configure` does not accept direct `session_id` edits

## References

Use `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]` for large external guidance.

# mad-agent-mesh

`mad-agent-mesh` is a wrapper around managed runner-backed channels.

Current command surface:

- `bin/invoke`
- `bin/sync`
- `bin/review-this-plan`
- `bin/review-this-work`
- `bin/execute-this-plan`
- `bin/execute-this-plan-part`
- `bin/configure`
- `bin/dangerous-new-session`

## Config

Managed state lives at:

`<repo>/.mad-agent-mesh/mams_channels.json`

Only canonical config is supported. There is no legacy migration path.

Each managed channel stores:

- runner metadata
- prompt profile
- current session id
- previous session ids
- stage reminder state

`prompt_profile` has three user-configured blocks:

- `public`
- `plan_stage`
- `execution_stage`

Built-in workflow prompts are injected per command.
Configured channel guidance is injected per stage with a cadence tied to `session × stage`.

## Notes

- Use wrapper commands only.
- Do not manually edit the managed config.
- If a managed channel stops without a valid structured result, the wrapper retries once with a protocol notice, then writes a diagnostic file if the retry still fails.
- Structured `## User Escalation Request` blocks are reviewed by `governor` first when a governor channel exists.

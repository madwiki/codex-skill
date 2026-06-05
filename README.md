# mad-agent-mesh

`mad-agent-mesh` is a wrapper around managed runner-backed channels.

Explicit skill invocation is `$mad-agent-mesh`, not a slash command.

From the caller's point of view, this repository is a skill:

- the caller is only the workflow messenger and user-facing entrypoint
- the caller must not modify code directly
- the caller must not substitute its own business / planning / review / implementation judgment
- all actual work must be routed through the wrapper commands in this skill

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

Successful wrapper replies also carry an Invoker-facing usage reminder:

- first reply: full
- then `brief / brief / full ...`
- the cadence is global across successful wrapper replies
- the full reminder re-states that the caller must route all work through this skill
- the brief reminder says the full reminder still applies
- both variants remind the caller to re-read `SKILL.md` after compaction or when the operating pattern is unclear

## Notes

- Use wrapper commands only.
- Do not manually edit the managed config.
- The end user speaks only through the workflow caller; managed channels do not talk to the user directly.
- Structured `## User Escalation Request` blocks are reviewed by `governor` first when a governor channel exists.
- The governor decides whether a question should be surfaced, but it still reaches the user only through the workflow caller.
- If no governor channel exists, a valid `## User Escalation Request` is surfaced to the workflow caller directly.
- If a managed channel stops without a valid structured result, the wrapper retries once with a protocol notice, then writes a diagnostic file if the retry still fails.

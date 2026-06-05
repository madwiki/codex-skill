---
name: mad-agent-mesh
description: >
  Use $mad-agent-mesh to coordinate one or more managed MAMS channels through the wrapper commands.
---

# mad-agent-mesh

This skill manages runner-backed channels stored in `<repo>/.mad-agent-mesh/mams_channels.json`.

Explicit skill invocation uses `$mad-agent-mesh`, not a slash command.

## Core rules

- Use wrapper commands only. Do not call raw runner CLIs directly.
- Do not manually edit or replace `<repo>/.mad-agent-mesh/mams_channels.json`.
- The end user speaks only through the workflow caller. Managed channels do not talk to the user directly.
- Session continuity is managed per channel slot through the wrapper.
- As the workflow caller, do not modify code directly and do not give your own business or implementation judgment. Route all actual work through this skill.

## Managed config

The canonical config is:

`<repo>/.mad-agent-mesh/mams_channels.json`

Top-level fields:

- `version`
- `mams_channels`
- `updated_at`

Each `mams_channels[*]` entry may store:

- `name`
- `prompt_profile`
  - `public`
  - `plan_stage`
  - `execution_stage`
- `can_mutate`
- `runner`
- `runner_config`
- `session_id`
- `model`
- `reasoning_effort`
- `previous_session_ids`
- `last_stage_context`
- `stage_reminder_turn_count`
- `updated_at`

`prompt_profile` is user-configured business guidance:

- `public` always applies
- `plan_stage` applies on plan-oriented turns
- `execution_stage` applies on execution-oriented turns

The wrapper injects built-in workflow prompts per command. Those built-in prompts are always injected in full.

The wrapper injects configured channel guidance with a stage cadence:

- first turn in a stage for a session: full
- then `full / brief / brief / full ...`
- switching stages resets the cadence for the new stage
- replacing the session resets the stage cadence

When a wrapper command accepts `fresh_user_message`, that message is injected into the managed channel prompt verbatim as `USER_MESSAGE_VERBATIM`. The wrapper caller may lightly normalize transcription noise before sending it, but the managed channel receives the caller's provided wording, not a wrapper-generated paraphrase.

The wrapper also injects an Invoker-facing usage reminder into successful wrapper replies:

- first reply: full
- then `brief / brief / full ...`
- the cadence is global across successful wrapper replies, not tied to one specific command
- the full reminder re-states that the caller is only the workflow messenger and must route work through this skill
- the brief reminder says the full reminder still applies
- the reminder also tells the caller to re-read `SKILL.md` after compaction or when the operating pattern is unclear

## Wrapper output contract

Invoker should read successful wrapper replies in this order:

1. `INVOKER_SKILL_USAGE_*`
2. optional `GOVERNOR_REVIEW`
3. optional `USER_ESCALATION_REQUEST`
4. `CHANNEL_REPLY`

Meaning:

- `GOVERNOR_REVIEW` is governance guidance for Invoker, not a direct user message
- `USER_ESCALATION_REQUEST` is the user-facing question only after governor review allows it
- `CHANNEL_REPLY` is still the managed channel's actual reply body

For `invoke`, the same rule holds inside the returned `INVOKE_SUMMARY`:

- each `INVOKE_RESULT` may contain its own optional `GOVERNOR_REVIEW`
- then its own optional `USER_ESCALATION_REQUEST`
- both still sit inside the overall caller-facing wrapper output

## Typical caller round-trip

When a managed channel needs user input:

1. run the wrapper command normally
2. inspect optional `GOVERNOR_REVIEW`
3. if a `USER_ESCALATION_REQUEST` is present after that review, surface the question to the user
4. take the user's answer and send it back through the next wrapper command as `fresh_user_message`
5. let the wrapper resume the managed session; do not replace the session unless the user explicitly authorizes `dangerous-new-session`

## Commands

| Situation | Guide |
| --- | --- |
| Drive one or more channel calls through one blocking wrapper call | `invoke.md` |
| General discussion / clarification / plan repair / review relay | `sync.md` |
| Review a submitted plan before execution | `review-this-plan.md` |
| Review completed execution work | `review-this-work.md` |
| Execute one approved whole plan | `execute-this-plan.md` |
| Execute one approved plan part | `execute-this-plan-part.md` |
| Patch channel metadata and prompt profiles | `configure.md` |
| Replace or switch the managed session for a channel after explicit user authorization | `dangerous-new-session.md` |

## Notes

- `invoke` is the preferred blocking wrapper entrypoint.
- Read-only `invoke` requests fan out concurrently.
- Any mutating `invoke` request forces sequential execution.
- If a managed channel returns a structured `## User Escalation Request` and a `governor` channel exists, the wrapper asks the governor to decide whether that request should actually be surfaced.
- If a managed channel ends a turn without a valid structured result, the wrapper retries once in the same session with an explicit protocol notice. If the retry still fails, the wrapper writes a diagnostic file under `<repo>/.mad-agent-mesh/diagnostics/`.

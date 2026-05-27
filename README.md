# codex-skill

A caller-facing skill that lets the caller collaborate with one or more managed Codex agents, automatically resuming the selected agent session when it exists and automatically creating a new one when that agent does not exist yet.

## Install

Personal install:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/madwiki/codex-skill ~/.claude/skills/codex-skill
```

## What it does

- Persists structured managed configuration via `<repo>/.claude/codex_agents.json`
- The config stores:
  - top-level `caller` baseline / working style / stage guidance
  - top-level `shared_stages`
  - top-level `work_modes`
  - `agents`
- Each agent may store:
  - `name`
  - `description`
  - `focus`
  - `baseline`
  - `extra_context`
  - `stage_guidance`
  - `session_id`
  - `model`
  - `reasoning_effort`
  - `previous_session_ids`
- Automatically creates a new managed Codex session for the selected agent when that agent does not have one yet
- Treats session continuity as wrapper-managed: use only `bin/codex-skill-*` commands, never raw `codex`, and never manually edit or delete the managed agent config
- Uses `dangerous-new-session` only when the user explicitly wants to replace the selected managed Codex agent session, either with a fresh one or with a specific target session id
- Automatically migrates both legacy single-session files (`codex_session.json` / `codex_session_history.json`) and older structured configs that still use legacy caller field names or mode names into the latest structured agent config on first use
- When that one-time migration happens, the wrapper includes a migration notice in the command output so the caller sees it immediately
- Supports direct multi-agent usage through `--agent <name>`; the default agent name is `default`
- Supports `configure` to update caller baseline text, shared stage guidance, workflow-stage guidance, and agent-specific focus/baseline text through the skill interface
- `caller.*` is caller-side guidance: it is returned to the caller in wrapper output, not injected into Codex prompts
- `shared_stages` and `work_modes.*.stages` are common stage guidance: they are injected on both sides
- `agents[*].*` is agent-side guidance: it is injected only into the targeted Codex agent prompt
- Wrapper-injected system guidance is labeled `Codex Skill Reminder`
- User-configured guidance is labeled `User Reminder`
- `init` always carries full reminders; ongoing per-agent turns follow a 3-turn cadence: full on 1/4/7/... and brief on the two turns in between
- Supports unified file references in injected text with the format `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]`
- When a prompt contains `[[REF:...]]`, the wrapper injects a reference notice plus a referenced-materials list; referenced files must exist inside the workspace root
- Prefer direct narrative text for short or medium guidance. Use `[[REF:...]]` only when the underlying material is large enough that repeating it every turn would waste context.
- `.claude/codex-skill-refs/` is the conventional place for long Codex Skill reference documents, but the unified `[[REF:...]]` format may point at any workspace file
- User escalation is reserved for a real unresolved disagreement between the caller and Codex that has persisted for about 10 turns on the same issue
- Uses `init` as the bootstrap entrypoint for a new shared task, after the caller returns from compact or context clear, or when mutation ownership reverses between the caller and Codex
- Requires `init` to declare the current mutation-owner path explicitly through `mutation_owner: "caller"` or `mutation_owner: "codex"`
- Avoids resending durable background every turn; normal ongoing calls send only changed context and the current approved step
- Uses `chat` as the caller-mutates discussion surface for context sync, disagreements, and consensus-building
- Uses `work-sync` as the codex-mutates sync surface for discussion, candidate plan output, and response to caller review
- Runs non-mutation calls under an explicit `read-only` sandbox
- Runs `request-mutation` under `workspace-write` by default, with optional `full-access` escalation when the caller explicitly requests it
- Supports two mutation-owner workflows:
  - caller-mutates: the caller changes state; Codex reviews the caller's plan/work
  - codex-mutates: Codex changes state in small approved steps; the caller reviews between steps
- Makes fresh user messages optional. Include a verbatim user block only when the user actually said something new since the last Codex call.
- Frames the caller and Codex as peer reviewers of the same user goal, not as leader/subordinate or approver/implementer.
- Requires review stages to include direct fact-checking and whole-system coherence checks instead of trusting the other agent's summary.
- Uses a 3600-second default timeout because Codex may inspect files, reason, compact, or resume context.

## Entrypoints

All wrapper commands accept an optional `--agent <name>` flag. When omitted, the wrapper uses the `default` agent.

Bootstrap:

- `bin/codex-skill-dangerous-new-session`
- `bin/codex-skill-init`
- `bin/codex-skill-configure`

caller-mutates discussion:

- `bin/codex-skill-chat`

caller-mutates:

- `bin/codex-skill-review-my-plan`
- `bin/codex-skill-review-my-work`

codex-mutates:

- `bin/codex-skill-work-sync`
- `bin/codex-skill-request-mutation`

## Docs

- `SKILL.md`
- `dangerous-new-session.md`
- `configure.md`
- `init.md`
- `chat.md`
- `work-sync.md`
- `review-my-plan.md`
- `review-my-work.md`
- `request-mutation.md`

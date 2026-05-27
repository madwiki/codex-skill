# init

Use this as the collaboration bootstrap entrypoint.

Session continuity is wrapper-managed. The caller must use the wrapper commands and must not call raw `codex` directly or manually edit/delete `<repo>/.claude/codex_agents.json`.

`init` may target a specific managed agent with `--agent <name>`. If that agent does not exist yet, the wrapper creates it automatically and persists it in the structured managed config.

The caller should call `init` in three cases:

- a new shared task is starting and the caller wants to brief Codex on the task background
- the caller has just returned from compact or context clear and wants Codex to help recover the working context
- mutation ownership is switching between the caller and Codex, and the caller wants to re-bootstrap Codex under the new path before continuing

`init` is not a mutation step and not a discussion turn. It exists to give Codex the collaboration protocol plus either the new-task background or the tentative recovery background.

`init` is only the collaboration bootstrap. Session creation or resume for the selected agent happens automatically inside the wrapper before `init` runs.

## Input contract

Call `init` with JSON on stdin. The JSON must contain exactly one background field plus `mutation_owner`.

New task:

```json
{
  "task_background": "Summarize the new task background for Codex here.",
  "mutation_owner": "caller"
}
```

Recovery:

```json
{
  "recovery_background": "Summarize the caller's tentative recovered background here.",
  "mutation_owner": "codex"
}
```

Rules:

- `task_background` and `recovery_background` are mutually exclusive
- one of them is required
- `mutation_owner` is required and must be exactly `caller` or `codex`
- `init` privately injects the Codex collaboration protocol plus the role-specific path framing for the chosen mutation owner; the caller does not need to restate that in the input payload
- if mutation ownership is reversing mid-task, the caller must rerun `init` before using the new path
- for a path reversal with intact task continuity, use `task_background` to restate the current task under the new path
- for a path reversal combined with compact/context clear, use `recovery_background` plus the new `mutation_owner`
- after `init`, the caller resumes the appropriate path:
  - `chat.md` / `review-my-plan.md` / `review-my-work.md` for caller-mutates
  - `work-sync.md` / `request-mutation.md` for codex-mutates

## Output contract

Codex replies in markdown, not JSON.

If the input used `task_background`, Codex must include this required section:

```md
## Task Understanding Reply
...
```

That section should tell the caller what Codex understands about the task, what risks or disagreements stand out, whether the chosen mutation-owner path looks problematic, and what the caller should know before continuing.

If the input used `recovery_background`, Codex must include this required section:

```md
## Context Recovery Reply
...
```

That section should tell the caller what Codex can recover, what remains uncertain, and where the workflow should resume on the chosen mutation-owner path, including which command seems appropriate next if Codex can tell.

If Codex does not have trustworthy prior context to add, it should say so plainly instead of pretending recovery happened.

## Run

```bash
<skill_root>/bin/codex-skill-init < init.json
```

Named agent example:

```bash
<skill_root>/bin/codex-skill-init --agent reviewer-a < init.json
```

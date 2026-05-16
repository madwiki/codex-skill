# chat

Use this as the shared discussion mode for the **Claude-mutates** path, or for general peer discussion before that path's review gates.

If Codex and Claude disagree on the Claude-mutates path, use `chat`. Do not move to mutation until the disagreement is resolved or the user decides.

## When to use

- Routine progress sync that would otherwise be told only to the user
- Requirements discussion or understanding checks
- Choosing between Claude-mutates and Codex-mutates mode
- Mid-task changes, new constraints, or user changes of direction
- Disagreements between Claude and Codex
- Stuck, unclear, unresolved, risky, or confusing states
- Preparing the smallest user-facing decision when consensus is not reachable

## Collaboration rules

- Treat each message as a continuation of the same Codex collaboration session.
- Run the persistence bootstrap in `SKILL.md` first: verify durable memory/`CLAUDE.md` contains the reload + init + subtask-guide rule, and add it if missing.
- For a new shared task, or after compact/context clear, run `init.md` before using chat.
- `chat` is discussion only. It does not authorize mutation.
- On the Codex-mutates path, use `work-sync.md` instead of `chat.md`.
- Include what happened since the last Codex reply, including what Claude told the user when it affects the current state.
- Include a verbatim user message only if the user actually said something new since the last Codex call.
- If there is no new user message, omit the verbatim user block entirely.
- Do not fabricate, summarize-as-verbatim, or reuse stale user text to satisfy a template.
- Treat Codex as a peer collaborator, not an authority. Codex can be wrong; Claude can be wrong.
- Use read-only investigation and concrete evidence to test both agents' claims.
- In review or disagreement, check both facts and whole-system coherence. Do not accept the other agent's framing just to move forward.
- Chat is not the normal place for state-changing work. Prefer the dedicated mutation-owner entrypoint once consensus exists.

## Input contract

Call `chat` with JSON on stdin.

Required:

```json
{
  "message_for_codex": "Write Claude's discussion message here."
}
```

Optional addition:

```json
{
  "message_for_codex": "Write Claude's discussion message here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this discussion."
}
```

Rules:

- `message_for_codex` is required
- `fresh_user_message` is optional
- no other top-level fields are accepted
- include new facts, new constraints, disagreement, or next-step questions directly inside `message_for_codex`

## Output

Codex replies in normal text. `chat` does not enforce a JSON reply format.

## Run

```bash
<skill_root>/bin/codex-skill-chat < chat.json
```

`<skill_root>` is typically `~/.claude/skills/codex-skill`.

The command may take a long time. Wait for Codex to finish unless the process clearly fails.

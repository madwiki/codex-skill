# request-mutation

Use this in **codex-mutates** mode after the caller has read Codex's `plan` from `work-sync.md` and explicitly approves one small state-changing step.

Codex owns mutation for this step. Codex should perform only the approved step, self-check, report evidence, and stop for the caller review.

## When to use

- Codex proposed a candidate `plan` in `work-sync.md` and the caller now approves one concrete step from it
- A prior Codex mutation needs one approved follow-up repair step
- The task should proceed incrementally with the caller review between mutation steps

## Collaboration rules

- For a new shared task, or after compact/context clear, run `init.md` before authorizing mutation.
- This is the only mutation-permission turn in the codex-mutates workflow.
- the caller must approve exactly one mutation step in this call.
- Codex must not continue into the next feature or stage after finishing the approved step.
- Codex must not commit, push, release, deploy, or perform external-state actions unless this exact call explicitly authorizes that action.
- Do not stop for user input just because the next execution step is unclear. Escalate to the user only for a real unresolved caller/Codex disagreement that has persisted for about 10 turns on the same issue.
- Codex must self-check facts and whole-system coherence before reporting the step complete.
- After Codex responds, the caller reviews independently by reading/searching/verifying. If more discussion is needed, the caller returns to `work-sync.md`.

## Input contract

Call `request-mutation` with JSON on stdin.

Required:

```json
{
  "approved_mutation": "Describe the single approved mutation step here."
}
```

Optional addition:

```json
{
  "approved_mutation": "Describe the single approved mutation step here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this mutation.",
  "sandbox_mode": "full-access"
}
```

Rules:

- `approved_mutation` is required
- `fresh_user_message` is optional
- `sandbox_mode` is optional
- no other top-level fields are accepted
- `approved_mutation` should contain the step boundary, any relevant constraints, and the instruction to stop after this step for the caller review
- if `sandbox_mode` is omitted, the wrapper uses the default mutation sandbox: `workspace-write`
- if the caller decides the default mutation sandbox is too restrictive for this approved step, the caller may resend the request with `sandbox_mode: "full-access"`
- `sandbox_mode` may only be `default` or `full-access`

## Output

Codex replies in normal text. The reply should report what changed, what was verified, any fact or coherence concerns, and where Codex stopped.

## Run

```bash
<skill_root>/bin/codex-skill-request-mutation < request-mutation.json
```

# plan

Legacy alias for `review-my-plan.md`.

Use this only when older instructions or habits say `plan`. It means **Claude-mutates** mode: Claude owns state-changing work, and Codex reviews Claude's plan without mutating state.

For the current workflow, read `review-my-plan.md` and run:

```bash
<skill_root>/bin/codex-skill-review-my-plan < message.txt
```

Compatibility command:

```bash
<skill_root>/bin/codex-skill-plan < message.txt
```

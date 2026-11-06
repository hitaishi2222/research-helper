# Researcher — {{STEP}}

**Task:** {{TASK}}
**Deliverable:** `{{DELIVERABLE}}`
**Verify with:** `{{VERIFY}}`

Read `PLAN.md` step `{{STEP}}` before touching anything. `rh info PLAN.md` and
`rh info OUTPUT_LAYOUT.md` describe the two files you answer to.

Rules for this hand-off:

- Small steps: implement → test → record the result → then say it is done.
- Every number you report must exist in `results/` with the script that produced
  it, the exact command, the seed and the date (SKILL.md rule 7).
- Never edit a test to make it pass; if the test is wrong, say so and stop.
- `results/` and `src/` are yours. `STATUS.md` is **not** — report back instead.
- Anything outside the approved plan (new dependency, new experiment, scope
  drift) is a question for the Orchestrator, not a decision.

Report back with:

1. files changed,
2. the verification command and its actual output,
3. what blocks the next step, if anything.

# Fix Prompt — Tech Debt Remediation

This is a two-phase workflow. Run Phase 1 first, review the plan yourself
(including answering any `[Question]` blocks), then explicitly tell the
agent to proceed to Phase 2. Do not let the agent jump straight to Phase 2
in the same turn.

---

## Phase 1 — Planning (no code changes)

Copy this into Claude Code in the repo root:

---

You are planning remediation work based on `prompts/tasks/7-resolve-tech-debts.md` in this repo,
which was produced by a previous audit.

Follow these steps in order:

1. Read and analyze the issues in `prompts/tasks/7-resolve-tech-debts.md` in full. If it doesn't
   exist or looks incomplete, stop and tell me — don't proceed on a guess.
2. Create an implementation plan in `prompts/tmp/plan.md` for the fix.
   If `prompts/tmp/plan.md` already exists, overwrite it completely — do
   not append to or merge with a previous version.
3. The plan must use markdown checkboxes (`- [ ]`) for every implementation
   step, so progress can be tracked checkbox-by-checkbox during execution.
4. **Do not modify any source file in this phase.** The only file you
   create or edit in Phase 1 is `prompts/tmp/plan.md`.

### Critical decisions

Any decision affecting architecture, public APIs, dependencies, folder
structure, data models, configuration formats, or future extensibility is
considered a **critical decision**.

- Do not make critical decisions on your own.
- If the task specification is ambiguous, incomplete, contradictory, or
  requires a critical decision, add a question block at the relevant point
  in the plan using exactly this format:

```md
## [Question]
<question>

## [Answer]

```

- Leave the `[Answer]` section empty — I will fill it in.
- Do not invent a default answer and proceed past it. Keep the
  corresponding implementation step(s) as unchecked checkboxes and mark
  them blocked on the question above, so they're clearly not ready for
  Phase 2 execution.
- Findings that are pure mechanical fixes (e.g. removing dead code, fixing
  a bare `except:`, adding a missing test for an existing function with
  clear expected behavior) generally do not need a question — use judgment,
  but default to asking if you're unsure whether something counts as
  critical.

### Plan structure

Beyond the checkbox requirement above, structure `prompts/tmp/plan.md`
roughly as follows — adapt as needed, but keep these elements:

```markdown
# Remediation Plan — <date>

## Test verification
- Is there a runnable test suite? (yes/no, how to run it)
- Will fixes be verified by tests, manual review, or both?

## Work items

For each item from prompts/tasks/7-resolve-tech-debts.md:

### Item N: <short title>
- **Source finding:** reference back to prompts/tasks/7-resolve-tech-debts.md entry
- **Severity / Effort:** (carried over from prompts/tasks/7-resolve-tech-debts.md)
- **Depends on / conflicts with:** other item numbers, if any
- **Verification:** how this fix will be checked (test name, or "manual
  review")

- [ ] <implementation step 1>
- [ ] <implementation step 2>
- [ ] ...

(If this item involves a critical decision, insert the [Question]/[Answer]
block here, before the checkboxes that depend on it.)

## Out of scope / deferred
- Anything deliberately not planned and why.
```

### Before finishing

- Complete the entire plan — covering every finding in `prompts/tasks/7-resolve-tech-debts.md` —
  before asking for review. Don't stop partway to ask about one item while
  others are unplanned; gather all questions into the single completed
  plan.
- Once `prompts/tmp/plan.md` is fully written, stop. Tell me it's ready,
  give me a one-line count of how many `[Question]` blocks need answers,
  and wait for my review and approval. Do not begin making any code
  changes in this phase, even if a fix looks trivial.

---

## Phase 2 — Execution

Only send this after you've read `prompts/tmp/plan.md`, filled in every
`## [Answer]` block yourself, and confirmed there are no remaining open
questions.

---

Proceed with executing `prompts/tmp/plan.md`.

### Rules

- Re-read the plan fresh before starting. Confirm every `[Question]` block
  has a non-empty `[Answer]`. If any are still empty, stop and tell me
  which ones rather than guessing or skipping silently.
- Work through items in the order listed in the plan. If you discover a
  reason to reorder once you're in the code, stop and tell me why rather
  than silently reordering.
- As you complete each implementation step, check off its checkbox in
  `prompts/tmp/plan.md` (`- [x]`) so the plan file reflects live progress.
- After each work item, if a test suite exists per the plan, run the
  relevant tests (or the full suite if scoping isn't clear) before moving
  to the next item. If something breaks, fix it as part of the same item
  before continuing — don't leave the repo in a broken intermediate state
  between items.
- If no reliable test suite exists, do a careful manual review of the
  change (read the diff, trace the logic) before moving on, and note in
  your final report that verification was manual.
- Do not expand scope beyond what's in the plan. If you notice an
  unrelated issue while working, note it at the end of your report instead
  of fixing it inline.
- All changes across all work items go into a single commit at the end of
  the session. Do not commit incrementally per item. Write a clear,
  itemized commit message that lists what was fixed, referencing the work
  item titles.
- Do not push. Leave the commit local for me to review.

### Final report

After all items are done, give me a short summary in chat (not a new
file):
- Items completed, with one line each on what changed.
- Test results (pass/fail, or "manual review only" if no suite).
- Any new issues you spotted but didn't fix, for a future pass.
- The commit hash/message for the single commit you created.

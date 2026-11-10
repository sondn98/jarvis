# <Task Title> – Implementation Plan

<!--
Template for `prompts/tasks/<N>-<slug>.plan.md`.
Written in the plan phase; no source files are touched while writing it.
Every implementation step is a checkbox so progress is trackable one box at a
time during execution.
-->

## Architecture Summary

Maximum ~10 numbered bullets, one per file or component, each saying what it is
and why it exists.

1. `<module>/config.py` — <what it does>
2. `<module>/models.py` — <what it does>
3. Tests under `tests/unit/<module>/`; <how they're isolated>

---

## Directory Structure

```text
<module>/
├── __init__.py
└── ...

tests/
└── unit/
    └── <module>/
        └── ...
```

---

## Planning Questions

> Every question must be answered by the owner before execution begins.
> Leave each `[Answer]` empty — the owner fills it in.

### [Question 1]

<The decision, stated plainly.>

Options:

- **Option A** — <what it means, honest tradeoff>
- **Option B** — <what it means, honest tradeoff>

<One line on your recommendation and why. Do not pick.>

<Why this is critical: affects architecture / public API / dependencies / folder
structure / data models / config format / extensibility.>

## [Answer 1]

---

## Implementation Steps

> Not executed until every planning question above has a non-empty answer and
> the owner approves the plan.

- [ ] **Step 1 – <name>**: <what changes, in which files>
- [ ] **Step 2 – <name>**: <what changes, in which files>
- [ ] **Step N – Verify**: full gate — `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`

Steps blocked on an unanswered question stay unchecked and are marked
`(blocked on Question N)`.

---

## Verification

- How each step is checked: test name(s), or "manual review" where no test
  applies.
- Per-item: run the relevant tests before moving to the next item.
- Before reporting done: the full gate above.

---

## Out of scope / deferred

- <What is deliberately not planned, and why.>

---

## Notes / flagged assumptions (reversible)

- <Minor assumption made to keep moving, and what would reverse it.>

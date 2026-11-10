# jarvis-task

A Claude Code skill that runs this repo's `prompts/` task workflow: author a
numbered task spec, plan it, get your answers to the decisions that matter, then
execute the plan one checkbox at a time.

Jarvis has been built this way since task 1 — `prompts/archive/` holds eight
tasks' worth of specs and plans. This skill encodes that workflow so each new
task follows it without being re-explained.

`SKILL.md` is the instruction set Claude reads. This README is for you.

---

## Quick start

```
/jarvis-task spec add a memory module so conversations persist across requests
/jarvis-task plan 9          # ← then fill in the [Answer] blocks yourself
/jarvis-task execute 9
```

Forgot the phase? `/jarvis-task 9` infers it from what's on disk and says which
it picked before doing anything.

---

## The three phases

| Phase | Writes | Then |
|---|---|---|
| `spec` | `prompts/tasks/<N>-<slug>.md` | Stops |
| `plan` | `prompts/tasks/<N>-<slug>.plan.md` | Stops at the review gate |
| `execute` | Source, tests, docs | Reports, then asks about wrap-up |

### 1. `spec` — turn an idea into a task spec

Claude reads the modules your idea touches before writing anything, so the spec
describes *this* codebase and not a generic Python project. Output follows
`prompts/templates/task-spec.md`: purpose, goals, structure, requirements, error
handling, logging, tests, **non-goals**, deliverables.

The number is derived automatically (highest prefix in `prompts/tasks/` and
`prompts/archive/`, plus one). Slugs stay short: `9-memory-module`.

Read what it wrote and edit it directly. Pay attention to Non-Goals — across the
archive that section is what actually keeps execution from sprawling.

**This phase is optional.** Tasks 1–8 were authored by hand or elsewhere. Drop
your own spec at `prompts/tasks/9-<slug>.md` and start at phase 2.

### 2. `plan` — decompose it, surface the decisions

Writes a sibling `<N>-<slug>.plan.md` and touches no source file. It contains an
architecture summary, the directory tree, ordered `- [ ]` steps naming the files
each one touches, and a `[Question]` block for every critical decision.

A decision is **critical** if it affects architecture, public APIs, dependencies,
folder structure, data models, config formats, or future extensibility. Claude
will not make those for you — it presents options with tradeoffs and a
recommendation, then leaves the answer empty.

Then it stops and tells you the step count and how many answers are outstanding.

### 3. The gate — you answer

Open the plan and fill each block in place:

```md
## [Question 1]
Should memory persist to disk, or stay in-process for v1?

- **Option A** — in-process dict; simplest, lost on restart
- **Option B** — SQLite; survives restarts, new dependency

Recommendation: A for v1 — nothing yet needs durability.

## [Answer 1] Option A
```

Short answers are fine. `Follow your recommendation` and `Option (a)` both
appear in the archived plans and both work.

This gate is the whole point of the workflow. `execute` refuses to start while
any answer is empty and names the ones it's waiting on.

### 4. `execute` — work the plan

- Re-reads the plan fresh and verifies every answer is filled.
- Works steps in order; stops and explains rather than silently reordering.
- Ticks each checkbox in the plan file as it lands, with a note where reality
  differed from the plan.
- Runs the relevant module tests after each item and fixes breakage inside that
  item — the repo is never left broken between items.
- Won't expand scope: unrelated problems go in the final report, not the diff.

Before reporting done, the full CI-parity gate:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Some tests here need a live model or `DEFAULT_MODEL`. The skill tells Claude to
distinguish those pre-existing failures from real regressions, and never to call
a failing gate green.

You get a chat report: steps completed, actual gate results, anything verified by
manual review instead of tests, issues spotted but not fixed, and anything left
unfinished with the reason.

---

## Audits

A read-only tech-debt audit is one shot — no plan, no gate:

```
/jarvis-task spec audit
```

Claude reads every source file in scope (exhaustive, not sampled), modifies
nothing else, and writes findings to `prompts/tasks/<N>-<slug>.md` following
`prompts/templates/audit-report.md` — severity, location, why it matters,
suggested fix, effort.

The report *is* the spec for the fix work, which is exactly what happened with
`7-tech-debt.md` → `7-resolve-tech-debts.md`. To act on it:

```
/jarvis-task plan <N>
```

---

## Wrap-up

Nothing git-related happens on its own. After the execution report Claude asks
once; if you say yes, it follows the house convention:

- **Branch** `<type>/<slug>` — `feat` | `bugfix` | `update` | `techdebt`.
  Never commits to `master`.
- **One commit** for the whole task, bracket-prefix subject, itemized body:

  ```
  [feat] Memory module

  - Add memory/ package: config, models, store
  - Wire MemoryService into AgentService
  - Tests: tests/unit/memory/
  ```

  Remediation work uses `[tech-debt]` and references the source spec path, e.g.
  `[tech-debt] Remediate audit findings (prompts/tasks/7-tech-debt.md)`.
- **One PR** per task into `master`. Claude never merges.
- **Archive**: `git mv` the spec and plan into `prompts/archive/`.

Say no and the tree stays dirty for you to handle.

---

## Files

```
.claude/skills/jarvis-task/
├── SKILL.md      # instructions Claude reads
└── README.md     # this file

prompts/
├── prompt.md                   # prompt-discovery rules
├── system/karpathy-guidelines.md   # loaded first, every phase
├── templates/                  # read at runtime by the skill
│   ├── task-spec.md
│   ├── plan.md
│   └── audit-report.md
├── tasks/                      # active: <N>-<slug>.md + <N>-<slug>.plan.md
└── archive/                    # completed tasks, moved on merge
```

`prompts/archive/` is deliberately not read during normal work — it's ~5,900
lines and would consume context for nothing. Only the filenames are used, to
derive the next task number. Reference a past task explicitly if you want it
loaded.

---

## Customizing

**Change the document shapes** by editing the files in `prompts/templates/`. The
skill reads them at runtime and they take precedence over Claude's own sense of
what a Jarvis document looks like. No skill edit needed.

**Change the workflow** — phase behaviour, the critical-decision definition, the
verification gate, commit conventions — by editing `SKILL.md`.

`prompts/system/karpathy-guidelines.md` loads before every phase and governs the
whole session: no speculative features, no abstractions for single-use code,
surgical diffs, every changed line traceable to the request. Edits there affect
all phases at once.

---

## What it deliberately doesn't do

- **Never crosses the gate on its own.** Planning and execution are separate
  invocations by design.
- **Never guesses a critical decision.** It asks, with options and tradeoffs.
- **Never touches git unprompted**, including the archive move.
- **Never claims a passing gate it didn't get.**
- **Two genres only** — feature/module build and read-only audit. The phased
  investigate-then-decide shape of `8-mcp-integration.md` and the
  audit-remediation shape of `7-resolve-tech-debts.md` are not built in; write
  those specs by hand and run `plan` / `execute` against them, which works fine.

---

## A note on the gate

The temptation is to let Claude plan and implement in one turn. The archived
plans are the argument against it: `2-api-server-module.plan.md` has five
questions whose answers reshaped the module's public API, and
`8-mcp-integration.plan.md` has seven — the transport choice alone would have
been wrong if guessed, since nothing in the code says Jarvis runs on k8s against
remote services. Those answers only exist because the workflow stopped and asked.

---
name: jarvis-task
description: Run the Jarvis prompts/ task workflow — author a numbered task spec, plan it into a sibling .plan.md with owner-answered [Question] blocks, execute the plan checkbox-by-checkbox, then wrap up. Use when the user says /jarvis-task, asks to write or plan or execute a task in prompts/tasks/, mentions a task number or .plan.md, or asks for a read-only tech-debt audit of this repo.
---

# Jarvis Task Workflow

This repo develops through numbered task specs under `prompts/`. One task = one
spec + one plan + one review gate + one execution pass.

**Invocation:** `/jarvis-task <phase> [target]`

| Phase | Argument | What it does |
|---|---|---|
| `spec` | a rough idea, or `audit` | Write `prompts/tasks/<N>-<slug>.md` |
| `plan` | `<N>` or `<N>-<slug>` | Write `prompts/tasks/<N>-<slug>.plan.md`, then **stop** |
| `execute` | `<N>` or `<N>-<slug>` | Work the plan's checkboxes, verify, then offer wrap-up |

If no phase is given, infer it from state and say which you inferred before
acting: no spec → `spec`; spec but no plan → `plan`; plan with every `[Answer]`
filled → `execute`; plan with empty `[Answer]`s → report which ones and stop.

## Before any phase

1. Read `prompts/system/karpathy-guidelines.md` and follow it for the whole
   session. It is the project's global instruction set, and it outranks your
   default instincts: no speculative features, no abstractions for single-use
   code, surgical diffs, every changed line traceable to the request.
2. Read `prompts/prompt.md` for the prompt-discovery rules.
3. Read the target spec and plan in full if they exist. Never act on a partial
   read or a filename guess. If the spec is missing or looks truncated, stop and
   say so.
4. Do **not** read `prompts/archive/` unless the task explicitly references a
   past task — it's history, and it's large. The exception: deriving the next
   task number (below), which only needs filenames.

Templates live in `prompts/templates/` — `task-spec.md`, `plan.md`,
`audit-report.md`. Read the relevant one at the start of its phase and follow
its structure. They are editable by the owner; they win over your memory of what
a Jarvis document looks like.

## Numbering and naming

Next number `N` = highest numeric prefix across `prompts/tasks/*.md` and
`prompts/archive/*.md`, plus one. Get it from filenames only:

```bash
ls prompts/tasks prompts/archive | grep -oE '^[0-9]+' | sort -n | tail -1
```

Slug is kebab-case and short: `9-memory-module`, not
`9-add-a-memory-module-to-jarvis`. The plan is always the sibling
`<N>-<slug>.plan.md`.

---

# Phase: spec

Turn a rough idea into a full spec at `prompts/tasks/<N>-<slug>.md`.

Two genres — pick by what the user asked for, and say which you picked:

- **Feature / module build** (the default; tasks 1-6, 8). Follow
  `prompts/templates/task-spec.md`.
- **Tech-debt audit** — a read-only investigation whose deliverable is a
  findings report, not code. Follow `prompts/templates/audit-report.md` for the
  *output* shape the spec should demand, and see "Audit genre" below.

How to write it:

1. Investigate first. Read the actual modules the task touches —
   `llm/`, `api_server/`, `agent_orchestration/`, `logging_utils/` — and the
   existing conventions (`pydantic-settings` config per module, `BaseTool` +
   `ToolRegistry`, LangGraph `StateGraph`, `tests/unit/<module>/`). The spec must
   describe this codebase, not a generic Python project.
2. Be prescriptive and concrete. Show intended call shapes, model shapes, and
   log lines. The archived specs read as instructions, not as musings.
3. Write a real **Non-Goals** section. Every archived spec has one, and it is the
   single most load-bearing section — it is what keeps execution from sprawling.
4. Ask the owner about anything genuinely ambiguous in their idea *before*
   writing, not in a `[Question]` block. `[Question]` blocks belong in plans.
5. Don't write a plan in this phase, and don't touch source files.

End by reporting the path written and a one-line summary of scope and
non-goals. Then stop — planning is a separate invocation.

---

# Phase: plan

Produce `prompts/tasks/<N>-<slug>.plan.md` from the spec. **No source file is
created or modified in this phase.** The only file you write is the plan.

Follow `prompts/templates/plan.md`. The non-negotiable elements:

- **Architecture summary** — ~10 numbered bullets, one per file/component.
- **Directory structure** — the actual tree you intend to create.
- **Planning questions** — see below.
- **Implementation steps** — every step a markdown checkbox `- [ ]`, ordered,
  each naming the files it touches. Granularity: one checkbox ≈ one file or one
  coherent change, as in the archived plans.
- **Verification** — per step, the test name or "manual review".

## Critical decisions → `[Question]` blocks

A decision is **critical** if it affects architecture, public APIs,
dependencies, folder structure, data models, configuration formats, or future
extensibility.

- Do not make a critical decision yourself. Do not invent a default and proceed.
- Raise it in the plan, at the point it applies, in exactly this format:

```md
## [Question]
<question, with 2-3 options and honest tradeoffs>

## [Answer]

```

- State your recommendation and the reasoning. Then leave `[Answer]` empty —
  the owner fills it in.
- Numbered variants (`## [Question 1]` / `## [Answer 1]`) are fine and match
  several archived plans.
- Steps that depend on an open question stay unchecked and are marked
  `(blocked on Question N)`.
- Purely mechanical items — deleting dead code, adding a test for existing
  well-defined behaviour, fixing a bare `except` — do not need a question. When
  unsure whether something is critical, ask.

## Finishing the plan

Write the **whole** plan before asking for review. Don't stop partway to ask
about one item while others are unplanned — gather every question into the one
completed plan.

Then **stop**. Report: the plan path, the step count, and how many `[Question]`
blocks need answers. Do not start implementing, even if a step looks trivial.
This gate is the point of the workflow — crossing it in the same turn defeats
it.

---

# Phase: execute

Only after the owner has filled in the answers.

1. **Re-read the plan fresh.** Confirm every `[Question]` has a non-empty
   `[Answer]`. If any are empty, name them and stop — do not guess, do not skip
   them silently.
2. Work items **in the plan's order**. If you find a real reason to reorder once
   you're in the code, stop and say why rather than reordering silently.
3. As each step completes, tick its checkbox in the plan file (`- [x]`) so the
   plan reflects live progress. Where a step's reality differed from the plan,
   append a short note on the checkbox line — the archived plans do exactly this
   and it's what makes them useful later.
4. After each work item, run the **relevant** tests
   (`uv run pytest tests/unit/<module>/`). If something breaks, fix it inside the
   same item — never leave the repo broken between items.
5. **Do not expand scope.** Noticed an unrelated problem? Note it in the final
   report; don't fix it inline.
6. Where a plan step is covered by no test, do a careful manual review — read the
   diff, trace the logic — and say in the report that verification was manual.

## Full gate before reporting done

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

This is CI parity (`.github/workflows/ci.yml`). Report the real result. Some
tests in this repo depend on a live model / `DEFAULT_MODEL`; if those fail,
distinguish pre-existing environment failures from regressions you caused —
run the gate on a clean checkout first if you need to be sure. Never describe a
failing gate as passing.

## Final report (in chat, not a new file)

- Steps completed, one line each on what changed.
- Gate results — actual pass/fail, with output for anything failing.
- Anything verified by manual review rather than tests.
- New issues spotted but deliberately not fixed.
- Anything in the plan you did **not** finish, and why.

## Wrap-up — ask once, then act

After the report, ask the owner once whether to wrap up, and do only what they
approve. Never branch, commit, push, open a PR, or move files unprompted.

If approved, the house convention is:

- **Branch:** `<type>/<slug>` where type is `feat` | `bugfix` | `update` |
  `techdebt` — e.g. `feat/mcp-integration`, `techdebt/remediation-7`.
  Never commit to `master`.
- **Commit:** a single commit for the whole task, never one per item.
  Bracket-prefix subject, itemized body referencing the plan's step titles:

  ```
  [feat] Memory module

  - Add memory/ package: config, models, store
  - Wire MemoryService into AgentService
  - Tests: tests/unit/memory/
  ```

  Use `[tech-debt]` for remediation work, and reference the source spec path in
  the subject when the task came from an audit, e.g.
  `[tech-debt] Remediate audit findings (prompts/tasks/7-tech-debt.md)`.
- **PR:** one PR per task into `master`, body summarizing the spec and the plan
  steps.
- **Archive:** `git mv` both `prompts/tasks/<N>-<slug>.md` and
  `prompts/tasks/<N>-<slug>.plan.md` into `prompts/archive/`. Do this only as
  part of an approved wrap-up — a task isn't archived until it's merged work.

---

# Audit genre

For a read-only tech-debt audit, the phases collapse: the audit *is* the
execution, and its deliverable is the spec file for a future remediation task.

- Write findings to `prompts/tasks/<N>-<slug>.md` following
  `prompts/templates/audit-report.md`, with a dated H1.
- **Modify no other file.** No fixes, no refactors, no "while I was in there".
- Read every Python source file in scope — exhaustive, not sampled. Skip only
  `.venv/`, `__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`,
  build artifacts, and generated/vendored code. Ask before skipping anything you
  are unsure about.
- Keep a running findings list as you go rather than holding it all to the end.
- If exhaustive reading would exhaust context, stop and say so — do not silently
  downgrade to a sampling pass.
- Flag config/secret smells by file and line; never print secret values.
- Severity: **High** = causing or likely to cause bugs/security exposure, or
  blocking change. **Medium** = compounding, gets more expensive if left.
  **Low** = cosmetic, fine to defer. Effort: S = under a day, M = a few days,
  L = needs design.
- Every finding needs a concrete **Why it matters** — a real consequence, not
  "it's bad practice".
- End with **Open questions** for anything ambiguous. Remediation is a separate
  task: plan it with `/jarvis-task plan` against the report you just wrote.

---

# Project facts worth not re-deriving

- Python 3.13, `uv` for dependencies (`uv add`, `uv lock`, `uv run`).
- Pydantic v2 throughout; `pydantic-settings` `BaseSettings` per module reading
  env vars + project-root `.env` — follow this for new config, don't invent a
  second mechanism.
- Modules: `llm/` (provider-agnostic LLM access, LiteLLM provider),
  `agent_orchestration/` (LangGraph `StateGraph`, MCP-sourced tools),
  `api_server/` (OpenAI-compatible FastAPI), `logging_utils/` (incl. TRACE level
  and redaction).
- Tests live in `tests/unit/<module>/` — never inside an implementation package.
  `asyncio_mode = "auto"`, so async tests need no marker.
- Tools come from MCP servers (`MCP_CONFIG_PATH`), adapted onto `BaseTool` and
  registered in `ToolRegistry`. There are no built-in tool implementations.
- Lazy logging (`logger.debug("x: %s", x)`), never f-strings in log calls. No
  `print`. No sensitive content at INFO.

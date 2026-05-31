# Prompt Discovery and Usage

Before starting any task, inspect the `/prompts` directory and load any prompts relevant to the user's request.

## Prompt Structure

* `/prompts/system/`

  * Defines agent behavior, coding standards, communication style, and operating principles.
  * Treat these prompts as global instructions.

* `/prompts/tasks/`

  * Contains task-specific guidance such as code review, test generation, bug fixing, refactoring, deployment, or documentation.
  * Use these prompts when performing the corresponding task.

* `/prompts/templates/`

  * Contains reusable output formats and document templates.
  * Follow these templates when generating artifacts.

* `/prompts/archive/`

  * Historical prompts retained for reference.
  * Do not use archived prompts unless explicitly requested.

## Selection Rules

1. Load only prompts relevant to the current task.
2. Prefer the most specific prompt available.
3. If multiple prompts apply, combine them in the following order:

   * system
   * task
   * template
4. When instructions conflict, the more specific prompt takes precedence.
5. Never assume prompt contents. Read them before use.

## Efficiency

* Avoid loading unrelated prompts.
* Minimize context usage by selecting only the prompts required for the task.
* Summarize large prompt files internally before applying them.

## Missing Prompts

If a required prompt does not exist:

1. Continue using available instructions.
2. Inform the user that no specialized prompt was found.
3. Do not invent missing prompt contents.

Prompt files are considered part of the project's source of truth and should be followed consistently throughout the task.

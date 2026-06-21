# Task: Integrate Jarvis with MCP Servers

## Context

Jarvis is a personal AI agent application. Tool definitions currently live
inside the `agent_orchestration` module as hand-maintained code. The owner
no longer wants to maintain tool implementations in the Jarvis codebase.
Instead, Jarvis should act as an **MCP client**: it should connect to
external MCP (Model Context Protocol) servers and use the tools they expose,
the same way Claude Desktop or other MCP hosts do.

The current built-in tools are prototypes only — they exist to prove the
agent loop works, not because they need to be preserved. They are candidates
for deletion once equivalent functionality is available via MCP, but **do
not delete or migrate anything until the owner explicitly approves it.**

## Your Role and Operating Rules

You are acting as the engineer on this task. Follow these rules strictly:

1. **Investigate before proposing.** Do not assume the language, framework,
   folder structure, or existing patterns. Read the actual codebase first.
2. **No silent decisions on anything critical.** Architecture choices,
   library choices, config formats, and anything that touches deletion of
   existing code require explicit owner sign-off before you implement them.
   When you reach one of these points, stop and present options with
   tradeoffs — do not pick for the owner.
3. **Work in phases.** Complete and get sign-off on each phase before moving
   to the next. Do not jump ahead to implementation while design questions
   are still open.
4. **Show your findings, not just your conclusions.** When you investigate
   the codebase, summarize what you found (file paths, current patterns,
   relevant dependencies already installed) so the owner can sanity-check
   your understanding before decisions are made on top of it.
5. **Flag assumptions explicitly.** If you must assume something minor to
   keep moving, state the assumption out loud and flag it as reversible —
   don't bury it.

---

## Phase 0: Codebase Discovery (no code changes)

Investigate and report back on:

1. **Framework/structure of `agent_orchestration`**
   - Is it built on a framework (LangChain, LlamaIndex, custom agent loop,
     something else)? Pin down the actual library and version.
   - How are tools currently defined today (function-calling schema format,
     decorator pattern, registry, etc.)?
   - How does the orchestration loop currently decide which tool to call and
     execute it (where's the dispatch logic)?
   - What does the LLM provider/SDK integration look like (e.g. raw
     Anthropic/OpenAI SDK calls, or wrapped by a framework)? This matters
     because tool-calling schema needs to match what's sent to the model.

2. **Current tool inventory**
   - List every tool currently implemented, with file location and rough
     LOC, so we know what's actually being replaced.

3. **Existing config/secrets handling**
   - How does Jarvis currently load configuration (env vars, config files,
     a settings module)? This matters for how MCP server configs should be
     loaded — we want to follow existing conventions, not invent a new one
     unless there's a reason to.

4. **Runtime environment**
   - Where/how does Jarvis run (long-lived server process, CLI invocation,
     serverless/lambda-style, desktop app)? This affects whether spawning
     local stdio subprocesses for MCP servers is even viable, and whether
     persistent connections are possible.

5. **Relevant existing dependencies**
   - Check if an MCP SDK is already installed (`mcp` Python package or
     similar) or if anything adjacent is present.

**Output of this phase:** a short written summary of findings. Do not
proceed to Phase 1 until the owner has reviewed it.

---

## Phase 1: Architecture Decisions (proposal, not implementation)

Based on Phase 0 findings, prepare a proposal covering the following open
questions. For each one, present 2–3 viable options with honest tradeoffs.
**Do not pick one — wait for the owner's decision.**

### 1. Transport support
MCP servers can run as local subprocesses (stdio) or as remote
HTTP/SSE/Streamable HTTP services. The owner has not decided this yet and
wants your recommendation based on actual investigation, not a default
guess. Consider:
- What Jarvis's runtime environment (from Phase 0) actually supports.
- Whether the owner's anticipated MCP servers are more likely to be local
  developer tools (filesystem, git, local DBs → favors stdio) or hosted
  services (favors HTTP/SSE).
- Whether supporting both from day one is realistic vs. over-engineering
  for a first version.
- Ask the owner directly if their intended use case isn't yet clear from
  context — don't infer it.

### 2. MCP client library choice
- Use the official `mcp` Python SDK vs. an alternative/custom client.
  Recommend the official SDK unless there's a concrete reason not to, but
  state the reasoning rather than asserting it.

### 3. Integration point in the orchestration loop
- How will MCP-discovered tools be surfaced to the existing
  orchestration/dispatch logic? Options typically include:
  a) An adapter layer that converts MCP tool schemas into whatever format
     the orchestration loop already expects (lowest disruption to existing
     code).
  b) Replacing the existing tool-calling abstraction entirely with an
     MCP-native one (bigger refactor, but removes a translation layer).
- Recommend based on what Phase 0 reveals about coupling in the existing
  code, but let the owner decide.

### 4. Server configuration format
Owner has already specified: **a config file, JSON, similar in spirit to
Claude Desktop's `mcpServers` config block.** Still confirm with the owner:
- Exact location (e.g. `~/.jarvis/mcp_servers.json`, project-root config,
  XDG-style path) — propose options matching existing Jarvis config
  conventions found in Phase 0.
- Whether secrets/env vars for MCP servers (API keys etc.) live inline in
  this file (matching Claude Desktop's pattern) or should be referenced
  from Jarvis's existing secrets mechanism instead.
- Whether config is loaded once at startup or supports hot-reload /
  runtime add-remove of servers.

### 5. Connection lifecycle
- When are MCP server connections established — at Jarvis startup (all
  configured servers), or lazily on first tool use?
- How should Jarvis handle a configured MCP server that's unreachable or
  fails to initialize (fail startup entirely, skip with a warning and
  continue, retry policy)? Propose options, let owner pick.

### 6. Tool name collisions
- If two MCP servers expose tools with the same name, or an MCP tool name
  collides with a remaining built-in tool, how should that resolve
  (namespacing by server name, first-wins, hard error at load time)?
  Propose options.

### 7. Disposition of existing prototype tools
- Owner has indicated these are prototypes and can likely be removed, but
  has not given final approval. Once MCP integration is working, present
  a concrete removal plan (which files, what becomes dead code) and get
  explicit go-ahead before deleting anything. Do not delete proactively.

**Output of this phase:** a written decision doc with the options above and
your recommendation for each. Wait for the owner to respond to every open
item before writing implementation code.

---

## Phase 2: Implementation (only after Phase 1 sign-off)

Once decisions are confirmed, implement in this order, with a natural
checkpoint after each step for the owner to test/review before continuing:

1. Add the MCP client dependency and a minimal connection module that can
   connect to a single hardcoded test server (e.g. a local reference MCP
   server) and list its tools — prove connectivity before building
   anything else on top.
2. Build the config loader for the JSON config file format agreed in
   Phase 1.
3. Build the adapter/integration layer that surfaces MCP tools to the
   existing orchestration loop dispatch logic (per the Phase 1 decision).
4. Wire up multi-server support per the connection lifecycle and collision
   rules agreed in Phase 1.
5. Add error handling for: server unreachable at startup, server crashes
   mid-session, tool call timeout, malformed tool responses.
6. Only after the above is working end-to-end: execute the agreed removal
   plan for prototype tools, if and only if the owner has signed off.

## What NOT to do

- Do not pick a transport (stdio vs HTTP) without owner input, even if one
  seems obviously better from the code.
- Do not delete or modify existing built-in tools before explicit approval
  in Phase 2 step 6.
- Do not invent a new config convention if Jarvis already has one that the
  MCP config can reasonably follow — surface this in Phase 1 rather than
  deciding unilaterally.
- Do not silently swap out the LLM-facing tool-calling format if it would
  break compatibility with how Jarvis currently talks to its model
  provider — flag this as a Phase 1 decision if Phase 0 reveals tight
  coupling.

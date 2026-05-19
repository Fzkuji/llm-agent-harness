# Function-calling unification — plan

Status: **planned, not started.** Discussed at length; this doc is the
agreed scope so the next session can pick it up directly.

## Goal

Today there are two separate ways an `@agentic_function` gets run:

- **chat** → `dispatcher.process_user_turn` → `agent_loop` (an LLM loop
  that calls *tools* — bash, web_search, …).
- **`/run`** → `webui/server.py::_execute_in_context` → `loaded_func(**kwargs)`
  directly. Separate code path, separate "command node".

Unify them: an `@agentic_function` becomes a thing the function-calling
mechanism can invoke — the LLM can call it from inside `agent_loop`, and
`/run` is just a user-triggered call through the *same* dispatch. One
loop, one context (the DAG), one runtime flow.

## Agreed decisions (from the design discussion)

- **Terminology**: rename "tool use" → "function calling" in *our*
  concepts / UI / docs. The provider wire field stays `tools` /
  `tool_calls` (Anthropic / OpenAI API) — add a mapping at the boundary,
  do NOT rename the wire protocol.
- "function calling" == the old "tool use" mechanism only. It does NOT
  include `decision.make` / `runtime.exec(choices=)` — those stay a
  separate, independent mechanism.
- Leaf tools (bash — no LLM inside, no DAG subtree) and agentic
  functions (gui_agent — LLM inside, DAG subtree) merge into one
  registry + one dispatch, but each entry keeps metadata marking its
  kind (leaf vs agentic, takes a runtime or not).
- The DAG / context wiring is **already automatic**: the
  `@agentic_function` decorator writes DAG nodes however it is invoked.
  Unification only changes the *trigger*, not the recording.
- In-process only: a function-call is `func(**kwargs)` in the worker
  process so it shares the live `runtime`. No subprocess. (See the
  runtime "live object" discussion — auth/streaming/cancel can't cross
  a process boundary.)
- `expose` (io / llm / full / hidden) and `render_range`
  (depth uncapped, siblings default 0) semantics are already settled —
  see `context/nodes.py::compute_reads`. The unification must not
  change them.

## Phases (each independently verifiable)

1. **Tool adapter** — new file, pure addition, zero risk. Wrap each
   `@agentic_function` as a tool spec `agent_loop` understands. The
   spec (name, description, params schema) is derived from the
   decorator's `input` metadata — no hand-writing.

2. **Unified dispatch** — `agent_loop`'s function-call dispatch can
   call agentic functions: load the function, inject a runtime, call it
   inside the active DAG context (same as `_execute_in_context` does
   today). The function's DAG subtree chains under the call node via
   `called_by`. Return value → function result → back to the loop.

3. **Route `run` through it** — `run gui_agent(...)` stops going
   through the separate `_execute_in_context`; it routes to the phase-2
   call site. User-triggered and LLM-triggered calls share one path.

4. **Delete the old path** — remove `_execute_in_context`'s standalone
   run implementation once phases 1-3 are green.

## Risks

- `dispatcher` is the entry for both chat and `/run`. A bad refactor
  breaks the whole webui. Do it as a dedicated effort with tests per
  phase, not crammed onto the end of an unrelated session.
- Tool-list bloat if every agentic function is exposed — make it
  opt-in (the agent profile lists which agentic functions are callable).
- Nested runtimes (chat runtime + an exec sub-runtime for the agentic
  function) — runtimes already nest; verify.

## Open questions for next discussion

- Exact naming for the unified registry / the `run`-replacement UI.
- Which agentic functions are exposed as callable by default.
- Whether `run` stays as a user shortcut syntax or is fully replaced.

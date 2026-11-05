# Plan: FDE Academy, an interactive, Claude-guided course on GenAI engineering

## Context
You want to learn the whole syllabus (Modules 01–05, about 150 chapters) hands-on, and to turn the tutorial into a product anyone can use. In the product, the lesson code sits on the left and the live outcome on the right. Learners can watch data move through the code, see a tool call get blocked and the model adapt, and get guidance from Claude on what to do next. Each module ends with a quiz on the whole module and a list of what you got wrong.

The four projects in `FDE\Projects` are **specs and data only, with no code**:
- 01 ticket triage
- 02 vendor screening
- 03 policy RAG
- 04 proposal builder, which ships one working mock API, `mock_api/meridian_api.py`

The projects become the running examples for the lessons and the end-to-end capstones.

**Decisions made:**
- Teach the Agent Loop (Module 02) first, then backfill the foundations.
- Local app that runs with the learner's own API key.
- FastAPI + React/Vite/TS + Monaco.
- Default model `claude-opus-5-5`, switchable to `claude-sonnet-5-5` or `claude-haiku-5-5`.
- Off-machine backup goes to the private GitHub repo **https://github.com/AshishJoshi1/fde-academy** (remote `origin`, branch `main`).
- I commit at `/wrap` without asking each time. You approve the push once, when the remote is set up.

**Environment:**
- Python 3.14.7 is the default and 3.13 is installed as a fallback. Node 24 is installed.
- No Docker, no `uv`, no `ANTHROPIC_API_KEY`, no git repo.

## What gets built
`C:\Users\AshishKumarJoshi\FDE\Lessions\fde-academy\` is a new git repo. `python run.py` sets up a venv, installs dependencies, builds the web app if it's out of date, and opens the browser.

- **Left pane:** the lesson narrative and a Monaco editor, with Run, Step, Reset, Solution and "Run live ($ estimate)" buttons.
- **Right pane (tabs):**
  - **Console.**
  - **Trace timeline:** spans for each LLM call, `tool_use` and `tool_result`. `is_error` results are shown in red.
  - **Messages inspector:** the actual `messages` array, with what was added each turn diff-highlighted.
  - **Token and cost meter:** a context-budget bar split into system+tools, retrieved, history and headroom. It also shows `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` and dollars.
  - **Flow diagram:** the agent-loop diagram, or later a LangGraph node graph, with the active node lit and the data on each edge.
- **Lab controls:**
  - Block tool X.
  - Approve or deny a pending call.
  - Inject a fault: 429, 529, dropped connection, slow first token, malformed `tool_use`, `max_tokens` cut-off, or a fixture timeout or 500.
  - Step mode: off, at each LLM call, or at every frame.
- **Tutor panel:** Claude sees the step, your code, the checks that failed and a trimmed trace. It runs at low effort with a cached prefix and a rate limit.
- **Quiz engine:**
  - Question types: multiple choice, numeric (cost estimate), trace reading ("click the event that caused the wrong answer"), code fixes graded by pytest, and short answers graded by an LLM judge against a rubric.
  - Results are stored per module, with a "what I got wrong" view.

## Runtime architecture (the hard parts)
- **Execution:** each run is a subprocess.
  - Command: `Popen([venv_py, "-X", "utf8", "-u", "-m", "labkit.run", "main.py"])`, using threads to read output. Avoid asyncio subprocess on Windows.
  - Each run gets its own short folder under `%LOCALAPPDATA%`, and the environment is built from an allowlist.
  - Limits: 120 s of active time, a 1 MB console cap, and an event cap.
  - The process tree is killed through a Windows Job Object (created with ctypes), or `killpg` on POSIX.
  - **`-X utf8` is required:** we confirmed that `meridian_api.load_seed()` crashes under cp1252 on "Łódź".
- **IPC:**
  - Subprocess ↔ server: loopback TCP carrying newline-delimited JSON. The first line is a per-run token.
  - Server → browser: **SSE** (`Last-Event-ID` handles replay when the browser reconnects).
  - Browser → server: plain REST POSTs for Next, toggles and approvals.
- **Model relay:** the server hosts `/relay/{run_token}/v1/messages` and `/v1/messages/count_tokens`. The subprocess gets `ANTHROPIC_BASE_URL` pointing there and a dummy key, so **the real key never enters user code**.
  - The relay captures every SDK path: create, stream, tool runner, async and LangGraph nodes.
  - It is the single place for usage and cost accounting, the budget circuit breaker, fault injection, pause points and cassettes.
  - Tool spans come from the requests themselves: `tool_use` in response k, then `tool_result`/`is_error` in request k+1. **A manual loop needs no instrumentation.**
- **Fixture host:** a vendored copy of `meridian_api.py`, unchanged, with a subclassed handler.
  - The subclass adds faults and **logs POST, PUT and DELETE**. The base class returns 501 for these without logging, so a "zero writes" proof that only reads the log would miss them.
  - The server reads new log lines as they arrive and turns them into `fixture.http` events.
- **labkit** (inside the subprocess):
  - Turns log records into events, including structured gate decisions.
  - Turns `input()` into an approval prompt in the UI.
  - Maps exceptions to editor lines.
  - Provides optional `checkpoint()`/`show()`.
  - Later: a LangGraph callback hook that reads `metadata["langgraph_node"]` and the graph topology.
- **Event envelope:** `{v, run_id, seq, t_ns, type, span_id, parent_id, source, data}`. Types: `run.*`, `console.*`, `llm.request` (messages delta), `llm.response` (usage, cost, cassette hit/miss/live), `llm.error`, `tool.call`/`tool.result`, `fixture.http`, `log`, `prompt`, `pause`/`resume`, `check.result`, `cost.update`, `budget.tripped`, and `graph.*` later. The events are shaped like OTel spans so Module 04 can export them over OTLP.
- **Stepping:** the relay pauses before each request, showing the diff and a `count_tokens` bar before any money is spent, and after each response.
  - "Block tool X" edits `work/policy.json`. The lesson's gate reads that file ("policy as config").
  - A retry from the SDK (`x-stainless-retry-count`) attaches to the same frame. Runs abort after 25 min paused.
- **Cassettes, recorded at the relay:** vcrpy and respx can't see `anthropic` 1.x, because it uses httpx2.
  - **Key:** sha256 of canonical JSON for the request. `stream` is excluded, and tool ids, CRLF, ports and paths are normalized.
  - **Storage:** `cassettes/<variant>.jsonl` holds usage, not dollars, so prices come from `pricing.yaml`. There is a variant for each branch: `happy`, `blocked-update`, `fixture-timeout`.
  - **On a miss:** strict mode returns an error shaped like an Anthropic error, plus a diff against the nearest recorded request. `nearest` mode is for lessons where the prompt is edited, and its numbers are marked ≈.
  - `labctl cassettes record|verify` re-runs every solution offline in CI to catch stale cassettes.
- **Cost safety:**
  - A spend ledger with budgets: $0.50 per run, $5 per day, and $1 per day for tutor plus judge.
  - Before each request the relay projects the cost (spent so far + input + `max_tokens` × output price). Over budget, it returns a 403, which the SDK doesn't retry.
  - At most 25 calls per run. The run stops if the same request key repeats 3 times.
  - A live run needs a confirm token issued by the estimate. There is also a global kill switch.
- **Local security:**
  - A secret generated at each launch is sent as a header or a SameSite=Strict cookie, SSE included.
  - A Host-header allowlist (against DNS rebinding), Origin checks and no CORS.
  - The relay only accepts tokens of active runs.
  - Bind to 127.0.0.1.
- **Opus 5.5 rules built into lessons and checks:**
  - `tool_choice` must be `auto` (`any`/`tool` returns 400).
  - Thinking can't be disabled, so set `output_config.effort` explicitly (the default is `medium`).
  - No prefill.
  - Append the whole `response.content`; history only grows.
  - Return all `tool_result`s in one user message, using `is_error` instead of dropping any.

## Cause → effect: showing which code produced the outcome (Milestone 1)
Every visible outcome links back to the exact code line, data value and setting that caused it. Click either end and both sides highlight.

**How code lines are captured** (stdlib only, no SDK patching):
- **For each model call:** while the relay holds a request, it asks labkit over IPC "where are you?". labkit reads `sys._current_frames()`, keeps only frames from the learner's files, and returns `main.py:42 in run_loop()` plus the locals at that point, with `repr` truncated. Every `llm.request` therefore carries its call site and a snapshot of the variables.
  - Sync code is exact: the calling thread is blocked inside the HTTP call.
  - For async code, task stacks are used and marked ≈.
- **Gate decisions, approvals and prints:** gate decisions are logged with `log.info("gate", extra={tool_use_id, tool, decision, rule})`. `LogRecord` already carries `pathname:lineno` and `funcName`. `input()` approvals and `print()` calls record their caller frame the same way.
- **Which lines ran:** a `sys.monitoring` LINE tool (Python 3.12+), limited to the learner's code objects, records the lines that ran and how many times. The editor gutter shows lines that ran (×n) and dims lines that didn't. For example, the `execute_tool(...)` line stays grey when the call was blocked.
- **Pauses:** at a pause point the **Variables** panel shows `messages`, `policy`, `call` and `decision` as they were at that frame.

**Panels that tie it together:**
- **"Why?" causal-chain panel:** a numbered, clickable chain built *deterministically* from event links. The links are `tool_use_id`, the gate log, request k → k+1 and the policy file diff. Lessons can add prose with `story:` annotations. For the block-a-tool lab:
  1. **Your toggle:** you set "Block update_opportunity", so `policy.json` now has `deny: ["update_opportunity"]` (file diff shown).
  2. **The model's request:** response #2 asks for `update_opportunity(opportunity_id="OPP-003", stage="won")` (block highlighted in Messages).
  3. **Your gate:** `main.py:31  if call.name in policy["deny"]:` evaluated True. Locals: `call.name="update_opportunity"`.
  4. **The error result:** `main.py:33` built `tool_result{is_error: true, content: "Blocked by policy: writes are not allowed"}`. `main.py:36 execute_tool(...)` never ran (grey gutter).
  5. **One message back:** request #3 sends all `tool_result`s in one user message (Messages diff).
  6. **The API log:** the fixture shows `GET /opportunities/OPP-003` only, with **0 PATCH** calls.
  7. **The outcome:** the final answer says the update wasn't made and gives the information it could find.
- **Flow diagram animation:** the `tool_use` JSON travels toward "execute tool", hits a red barrier at the gate node, and comes back as an `is_error` result to the model.
- **Compare runs:** the blocked and allowed runs side by side, showing message sequences, fixture log (PATCH vs none), cost and final answer, with the differences highlighted.
- **Tutor "Explain":** narrates the chain using only the deterministic links as its sources, citing step numbers, and never makes up causes.

**Lab 02 restriction variants** (where the restriction lives, compared in one view):
1. Tool not offered: the model can't call it and says so.
2. Offered but blocked by the code gate: `is_error`, the model adapts.
3. Approval in the loop: the run pauses until you click Approve or Deny.
4. Strict schema: a malformed call can't be produced at all.

The lesson's takeaway is that enforcement belongs outside the model: 2–4 hold even under prompt injection, and 1 holds only as long as the tool list is built in code.

## Continuity: progress is never lost, and each day starts where the last one stopped
There are three kinds of state. Each has one owner and lives in files, not in chat history, so a fresh Claude session, a crash or a new laptop all resume cleanly.

| State | Owner | Saved how |
|---|---|---|
| **Learning state:** current step, code drafts, runs, quiz attempts, misses, spend | App SQLite `%LOCALAPPDATA%\fde-academy\academy.db` (WAL, safe if the app crashes) | Editor drafts autosave 2 s after you stop typing and on every run. The home screen has a **"Continue where you left off"** button that reopens the last step with your code and its last trace. `/wrap` runs `labctl export` to write `progress/learner-progress.json` into the repo, and `labctl import` restores it on any machine. |
| **Build state:** what's built, the exact stopping point, the next first action, open issues, decisions | `PROGRESS.md` at the repo root, plus git history | Rewritten at each `/wrap`. Sections: Current position (module/chapter/step), milestone checklist, Last session (date, done, **next first action**), open questions, decisions log. |
| **Code:** the app, lessons, cassettes, project builds | Git: the `fde-academy` repo, plus one repo per `FDE\Projects\0X-*` once its build starts. Each is pushed to a private GitHub repo. | `/wrap` commits every dirty repo listed in PROGRESS.md and pushes it. `.gitignore` covers `.env`, `*.db`, `runs/` and keys. Before the product is ever published, `progress/` must be removed. |

**Daily routine:**
- **Start:** open a terminal in `C:\Users\AshishKumarJoshi\FDE\Lessions\fde-academy` and run `claude`, then `/today`. Start each day from that same folder.
  - The repo's `CLAUDE.md` loads automatically there.
  - Starting fresh each day keeps context small and cheap. `claude --continue` is for picking up the same conversation later in the day.
- **`/today`** (project command, `.claude/commands/today.md`):
  - Reads PROGRESS.md and runs `labctl status`: position, still-wrong items by concept, and spend.
  - Checks `git status` on every tracked repo. If yesterday's work wasn't wrapped, it offers to wrap it first.
  - Re-quizzes up to 3 still-wrong items as spaced review.
  - States today's goal from "next first action", then carries on teaching or building.
- **`/wrap`** (project command):
  - Rewrites PROGRESS.md with the exact stopping point.
  - Runs `labctl export`.
  - Commits each dirty repo with a summary of the day, pushes, and prints a 3-line recap.
- **`/quiz <module>`:** the end-of-module quiz in chat. Answers are saved through `labctl quiz record`, so in-chat and in-app quizzes feed the same "what I got wrong" list.
- **Safety net:**
  - A project `SessionStart` hook in `.claude/settings.json` injects `labctl status --brief`, so I know where we are even if you skip `/today`.
  - Skipping `/wrap` loses nothing on disk. The next `/today` notices the uncommitted work.
- **Memory:** Claude memory is tied to the folder a session starts in, so the repo files are the source of truth, not memory. I'll also save one project memory in the current workspace pointing to the repo and this routine, plus one feedback memory about committing at `/wrap`.

**The product does the same for other learners:** autosave, Continue, and Export/Import progress buttons in the app.

## Content format
`content/<module>/module.yaml` → `<chapter>/chapter.yaml` → `<step>/{step.yaml, step.md, starter/, solution/, cassettes/, quiz/}`, validated with pydantic.

- `step.yaml` declares `files`, `panels`, `run` (mode, step granularity, cassette variants, fixture), `toggles`, `faults` and `checks`.
- Checks are named and come from a registry: `tool_results_batched`, `history_append_only`, `tool_result{is_error}`, `fixture_log{writes:0}`, `no_repeat_call`, `cost_below`, with a `python:` escape hatch.
- Each step also has `hints`, `quiz` items and `tutor_notes` (known misconceptions).
- Starter code reads `os.getenv("LAB_MODEL", "claude-opus-5-5")`.

## SQLite (user data folder, WAL)
Tables: `step_progress`, `code_snapshots`, `runs`, `check_results`, `quiz_attempts` (item, module, concepts, answer, correct, score, graded_by, feedback), `spend`, `tutor_turns`.

"What I got wrong" per module has three parts, grouped by concept:
- **Still wrong:** the latest attempt is incorrect (`ROW_NUMBER() OVER (PARTITION BY item_id …)`).
- **Fixed after retry.**
- **Checks still failing.**

## Repo layout
```
fde-academy/run.py  pyproject.toml (src layout; extras [graph] [rag] [data] [obs])  pricing.yaml
src/academy_server/  app.py security.py
  runs/{manager,sandbox,winjob,ipc,events}.py
  relay/{proxy,sse,cassette,canonical,faults,pricing,budget}.py
  fixtures/meridian/{meridian_api.py (vendored),seed/,host.py}
  content/{schema,loader,checks/,graders/}  tutor/  store/{db.py,migrations/}
src/labkit/{run,ipc,hooks,show,lg}.py
content/m02-agent-loop/...   web/ (Vite+React+TS: @monaco-editor/react, zustand, react-markdown, jsdiff)
tools/labctl.py   tests/
```
- **Core dependencies:** fastapi, uvicorn, `anthropic>=1`, pyyaml, platformdirs, truststore (handles corporate TLS interception), pytest.
- **Later:** langgraph, numpy, pandas, qdrant-client, opentelemetry, with Phoenix optional.
- `run.py` installs with `--only-binary=:all:`. If a wheel for Python 3.14 is missing, it falls back to `py -3.13`.

## Curriculum order and project mapping
The order can change at any time. Every module ends with a quiz in the app and in chat, then a project build.

1. **Module 02, The Agent Loop.** Includes just-in-time primers from 01-A (chapters 2–4) and 01-G (usage fields, `count_tokens`).
   - **Lab 02:** step the loop frame by frame against the Meridian API.
     1. One call.
     2. Manual loop.
     3. Parallel tool calls answered in one message.
     4. Gate and block: `update_opportunity` (PATCH) is denied before any network call. The model gets `is_error`, adapts, and the fixture log proves 0 writes.
     5. `@beta_tool` + `tool_runner`, with an approval gate on a `propose_credit` tool. Lumora never promises credits without approval.
     6. Tighten the schema: `amount` typed as a number in stated units, required `reason`, a category enum, `additionalProperties:false`, `strict:true`, and a description saying when to call the tool. A malformed-call fuzzer shows which bad calls get through.
   - **02-A:** tools, skills, memory and MCP (a tiny MCP server over the Meridian API).
   - **02-B:**
     - Ticket triage as chaining and routing (Project 01).
     - Vendor screening as LangGraph `Send` fan-out with per-check timeouts and partial results that are "never Green" (Project 02).
     - Supervisor/swarm, checkpointer resume and time travel, and HITL with `interrupt()`.
   - **02-C guardrails:** injection tickets and the injection vendor, the policy canary, and GET-only enforced outside the model, with adversarial suites.
   - **02-D state:** simulators for consistency and idempotency, agent state, and compaction.
   - **Apply:** build Projects 01 and 02 end to end.
2. **Module 01, Foundations.**
   - The rest of A, plus G (Lab 01 context budget: a retrieved-context slider, and effort, thinking and `max_tokens`).
   - F (caching, measured on ticket triage's static policy prefix, plus a hunt for whatever is busting the cache).
   - E (each technique has a "worth the tokens?" cost/quality panel).
   - B.
   - **C (NumPy) and D (pandas) are elective tracks** with their own quizzes and an array/DataFrame visualizer (shape, broadcasting, view vs copy).
3. **Module 03, Retrieval.** Project 03 is the spine: Qdrant `:memory:`, hybrid search, reranking, ACL and region/version filters applied in code, the manager-only canary, citations and abstention.
   - **Lab 03:** break retrieval four ways using a recall@5 eval built first.
   - ColPali and Qdrant ops use pre-computed embeddings to keep them local and cheap.
4. **Module 04, Evals and Observability.**
   - One-command `eval_report.md` for each project.
   - An LLM judge with separate grounded, correct and hedged checks.
   - A CI gate with a threshold.
   - OTLP → Phoenix.
   - Capstone rubric self-score: 6 rows × 1–4, with before/after numbers.
5. **Module 05, Reference build.**
   - Smart Support Assistant built twice: Claude Agent SDK, then plain API, on the Lumora data.
   - Project 04 (Agent Skills, GET-only hooks).
   - **Lab 04 part 2:** deploy the LangGraph capstone (state = `messages`, `chunks`, `approved`) to a hosted endpoint and write up the trade-offs.

**Target-outcome skill checks** (graded exercises in the app):
- **Draw the loop and say where it hangs:** "click where it hangs" scenarios. The scenarios are: a missing `tool_result`, `max_tokens` cut off mid-`tool_use`, no turn cap, a pending approval, and `pause_turn`.
- **Read a trace:** recorded failing traces.
- **Estimate cost:** your guess vs `count_tokens` and the real usage.
- **Write an eval before the prompt:** the prompt editor stays locked until an eval exists and runs red.
- **Make a malformed call impossible:** the schema fuzzer.
- **Deploy:** Lab 04 part 2.

## Milestone 1 build order (vertical slice = platform + Lab 02)
0. **Continuity first, so day 1 is already saved:**
   - Delete the stray `Projects\04-proposal-builder\mock_api\__pycache__\` (bytecode created by the design review's import).
   - `git init` `fde-academy` and add `.gitignore`.
   - Write `CLAUDE.md` (conventions, Opus 5.5 rules, session protocol), `PROGRESS.md` (seeded from this plan), and `.claude/commands/{today,wrap,quiz}.md`.
   - Add the `SessionStart` hook, set up with the update-config skill.
   - Save the two memories.
   - I add `origin` = `https://github.com/AshishJoshi1/fde-academy.git`. If the repo already has a first commit (say a README), I pull it first.
   - Git Credential Manager needs a browser login, so you run the first push yourself with `! git push -u origin main`. Later `/wrap` runs push without asking.
   - `labctl status`/`export`/`import` arrive with step 1, because they need the database.
1. `run.py`, the server shell with the security token, SQLite and migrations, and the content loader with its pydantic schema.
2. The sandbox, Job Object, IPC, and Console over SSE.
3. The relay: live pass-through with usage, cost and budget, then cassettes plus `labctl record`/`verify`.
4. The fixture host: vendor the mock API, add the write logging, the log reader and the faults.
5. Web panels: Messages diff, Trace, Token/Cost, and the static agent-loop diagram.
6. The stepper: pause points, `input()` approvals, the `policy.json` toggle and fault arming.
6b. Cause → effect:
   - Call sites through `sys._current_frames()` over IPC.
   - The `sys.monitoring` gutter and the Variables panel.
   - The "Why?" chain builder.
   - Animation of the flow diagram.
   - Compare runs.
7. The six built-in checks, feeding progress.
8. The quiz in all five types, plus the mistakes view.
9. The tutor.
10. The live cost estimate.
11. Lab 02 content (6 steps) plus the Module 02 Lab quiz. Record cassettes with your key; this is a one-time cost, shown before it is spent.

**Deferred to later milestones, one per module:**
- The LangGraph hook and graph view (02-B).
- `show()` visualizers (NumPy/pandas). Line highlighting with `sys.monitoring` is no longer deferred; it moved into Milestone 1.
- OTLP/Phoenix (04).
- Qdrant and embeddings (03).
- Deploy (Lab 04-2).
- A warm interpreter pool, and keyring storage for the key.

## Teaching protocol (per module)
1. I build the module's lessons into the app and record its cassettes.
2. You work through them in the UI with the tutor, and come to me in chat for the deeper "why".
3. End-of-module quiz in the app, plus a short quiz from me in chat. Misses are listed, saved, and re-quizzed when the next module starts.
4. Build the mapped project in `FDE\Projects\0X-*\` to its SPEC deliverables, then score it on the capstone rubric.

## Verification
- `pytest`:
  - Canonicalization and cassette keying (the same request gives the same key, ids are normalized).
  - The sandbox kills the process tree on timeout or abort.
  - The IPC token is rejected when it's wrong.
  - The registry checks, run against recorded event logs.
  - Quiz graders.
  - The SQL for the mistakes view.
- **Security tests:**
  - No secret → 403.
  - Bad Host or Origin → rejected.
  - Token of an inactive run on the relay → 403.
  - The subprocess environment has no real key.
- `labctl cassettes verify` replays every Lab 02 solution offline, and all checks pass with zero misses.
- **Lab 02 acceptance (replay and live):**
  - The stepper pauses at each frame.
  - The blocked PATCH shows up as `is_error` in request k+1.
  - The fixture log shows 0 writes.
  - The final answer acknowledges the block.
  - The live cost lands inside the estimate's low–worst band.
  - A budget trip test (budget set to $0.001) stops the run with `budget.tripped`.
- **Windows:** start under Python 3.14 with `-X utf8`, confirm the "Łódź" seed loads, and confirm the console handles non-ASCII text.
- **UI check:** launch the app and take screenshots of each panel during a stepped Lab 02 run.
- **Cause → effect:**
  - In the blocked run, each of the 7 chain steps highlights the right editor line and the right event.
  - The `execute_tool` line is grey in the blocked run and green in the allowed run.
  - Compare runs shows 1 PATCH vs 0 PATCH.
  - A pytest checks the recorded call sites (`main.py:<line>`) against the solution file.
- **Continuity:**
  - Edit a step, kill the server mid-run, restart: "Continue" reopens the step with the draft intact.
  - `labctl export`, delete the database, `labctl import`: status, misses and spend are identical.
  - Start a new Claude session in `fde-academy`: the `SessionStart` hook shows the position, and `/today` names the same next action PROGRESS.md recorded.
  - `/wrap` leaves every tracked repo clean and pushed (check with `git status` and `git log origin/main -1`).

## Open items (not blockers)
- The projects mandate the Claude Agent SDK, so its docs (code.claude.com/docs/en/agent-sdk) are read when we reach those builds.
- The programme README with baseline rules B1–B5 is not on disk. I'll need it from you, or I'll rebuild it from App 2's summary of it.
- Before recording cassettes: set `ANTHROPIC_API_KEY`, or install the `ant` CLI and log in.

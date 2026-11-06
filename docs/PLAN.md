# Plan: FDE Academy, a learning lab built lesson by lesson

## Goal
A local lab app for one learner (Ashish) to learn GenAI and agent engineering in depth: Python, the Anthropic SDK and LangGraph. Every lesson is a set of **experiments**. For each one you:
1. predict,
2. change one thing,
3. run it live,
4. compare the result with your prediction,
5. explain the gap.

Each lesson ends with a quiz. A Claude tutor guides you with questions and step-by-step hints instead of handing out answers. The app grows one lesson at a time and has no feature a lesson doesn't need.

## Principles
- **Depth over polish.** A feature is built only when a lesson needs it.
- **Simple features first.** Plain server-rendered pages with a little vanilla JavaScript, and a simple code editor on the lab page (or VS Code). A React and Monaco workbench comes later, and only if a lesson needs in-editor line highlighting.
- **Live calls only.** No cassettes, replay or recording. A run costs cents, and the gateway enforces the key's $50 budget (CLAUDE.md, "Gateway").
- **Predict before you run.** An experiment's Run stays locked until its predictions are committed.
- **Change one thing.** Each run shows the diff from your previous run of that step.
- **Everything is saved and repeatable.** Runs, predictions and quiz answers are kept. You can reopen any run for free, redo any lesson, and missed items come back in spaced review.
- **Learn while building.** Building a feature is part of the lesson that needs it. Where a feature is course material itself (the relay is a small LLM gateway, the tutor is an LLM app), Ashish does a hands-on part.
- The Claude API rules in CLAUDE.md apply to all lesson code and app code.

## How a lesson is made
For each lesson:
1. **Content:** `step.md`, starter, solution, `experiments:`, quiz and tutor notes, in `content/`.
2. **App features** the lesson needs that don't exist yet, with tests.
3. **Ashish does the lesson in the UI.** Misses are recorded. A card that misled gets fixed in the content.

**Done when** the content validates, the tests pass and Ashish has completed the lesson in the UI.

## The experience
- **Top of the page:** the lesson text, then the simple editor on your `playground/<step-id>/` files (line numbers, Ctrl+S, Reset). VS Code works on the same files. Each run shows the diff from your previous run.
- **Below it:** the experiment cards, one at a time:
  1. **Predict:** answer the card's prediction questions (multiple choice, number or short text).
  2. **Change:** the card says exactly what to edit. After the run you see the diff from your previous run.
  3. **Run:** a live run. The console streams in, and every model call shows its exact request JSON, response blocks, `stop_reason`, usage, cost, latency and gateway headers.
  4. **Compare:** your predictions next to the actual values. Each mismatch is flagged as a surprise.
  5. **Explain:** the tutor asks you *why* first, then hints in three levels (a nudge, then where to look, then the answer). Then the card's authored explanation appears.
- **In-lab tools**, for example a free "count tokens" button.
- **End of step:** the quiz. Answers go through the same store as `labctl quiz record`.
- **Home page:**
  - Continue where you left off.
  - Spaced review of missed quiz items and wrong predictions.
  - Running scores: prediction accuracy, surprises explained, mistakes cleared.
- **Repeat:**
  - **Reopen** any past run for free: the code snapshot, every call, the console, your predictions.
  - **Redo** an experiment: earlier predictions stay hidden until you commit new ones, then show beside them.
  - **Reset** to the starter whenever you want.

## Architecture
- **Server** (exists): FastAPI on 127.0.0.1 with three security gates (Host allowlist, Origin check, per-launch token cookie), the SQLite store, the content loader and the server-rendered pages.
- **Runner:**
  - Runs `python -X utf8 -u <entry>` in `playground/<step-id>/`.
  - Uses an allowlisted environment and a 120 s timeout, and kills the whole process tree when the limit hits.
  - Streams the console to the browser over SSE.
  - Saves a code snapshot with every run.
- **Thin relay:**
  - Serves `/relay/{run_token}/v1/*` and forwards to the gateway with the real key. The lesson process gets a dummy key and the relay's URL, so the real key never enters lesson code.
  - Records each call (request body, response body or stream, status, headers, timing, usage) as a run event, in order.
  - No cassettes. No budgets, because the gateway enforces them.
- **Store:** existing tables, plus run events, predictions and experiment progress (new migrations). Cost comes from usage × `pricing.yaml`.
- **Tutor:**
  - Sonnet 5.5 through the gateway, called by the server.
  - Context: the step content, tutor notes, your code, your predictions and the trimmed run.
  - The lesson part of the context is a stable prefix, so prompt caching can reuse it.
  - Cost: about $0.01 per turn.
- **UI:** server-rendered pages with small vanilla JavaScript, styled by `web/src/styles/academy.css` (the `/design` page is its reference). A React and Monaco workbench may replace them later. Views:
  - lesson text and the code diff
  - experiment cards and quiz
  - console, call inspector, usage and cost
  - run history
  - tutor
  - home
- **CLI:**
  - `tools/run_live.py <step-id>` runs a step directly against the gateway with the real key.
  - `labctl` handles status, export and import, quiz records and content validation.

## Where things live
| Path | Holds | In git |
|---|---|---|
| `content/` | Lesson source: text, starter, solution, experiments, quiz | Yes |
| `playground/<step-id>/` | Your code. Edited in the lab's editor or VS Code; the lab page and `run_live.py` run it | Yes |
| `%LOCALAPPDATA%\fde-academy\academy.db` | Runs, run events, code snapshots, predictions, quiz attempts, spend | No. Exported to `progress/learner-progress.json` at `/wrap` |
| `%LOCALAPPDATA%\fde-academy\anthropic.env` | Gateway credentials | Never |

## Experiment format (a sketch, finalized while building s01)
```yaml
experiments:
  - id: e2
    title: "Turn up effort"
    question: "What does effort control on Opus 5.5?"
    predict:                      # same item types as quiz
      - {id: p1, type: mcq, prompt: "Will a thinking block appear?", options: ["yes", "no"], answer: 0}
      - {id: p2, type: numeric, prompt: "output_tokens?", answer_from: run.usage.output_tokens, tol_pct: 50}
    change: 'Set output_config.effort to "high". Change nothing else.'
    observe: [content block types, usage.output_tokens, stop_reason]
    tools: [count_tokens]
    explain: >
      Authored explanation, shown after Compare.
```
A prediction is graded either against a fixed answer or against the value the run actually produced (`answer_from`).

## s01 "One call": the end result
| Card | Predict | Change | See |
|---|---|---|---|
| E1 What comes back | Block types, `stop_reason`, size of `output_tokens` | Nothing | Exact request JSON, full response, usage, cost, gateway headers |
| E2 Turn up effort | Thinking block or not? Tokens ×1, ×2 or ×10? | `effort` from `low` to `high` | Predicted vs actual; the diff shows one change |
| E3 The missing tokens | Token count of the answer text | Use the count-tokens tool | Where the unexplained output tokens went |
| E4 Hit the cap | What `max_tokens=20` does | One number | `stop_reason: max_tokens` and a cut-off answer |
| Quiz | q1–q3 in `step.yaml` | | Answers saved, misses come back in review |

**Done when:**
- Tests prove all of the following:
  - a timeout kills the whole process tree;
  - the lesson process never holds the real key;
  - the relay records every request and response in order;
  - predictions, runs and quiz answers persist and export.
- Ashish completes s01 in the UI.

**Build stages**, each one usable at the end:
1. **Runner and thin relay:** run s01 from the browser and see the console and the raw request and response.
2. **Experiment cards, quiz, run history and spaced review** on the lab page: s01 is fully playable and repeatable.
3. **Tutor:** questions and hints based on your actual run.

**Later, only if needed:** the React and Monaco workbench (editing in the page, plus line highlights for the "Why?" chain).

## Lab 02 roadmap: what each step adds to the app
| Step | New in the app |
|---|---|
| s01 One call | Runner, thin relay, lab page, experiment cards, quiz, run history, tutor |
| s02 Manual loop | The Meridian mock API (vendored `meridian_api.py`) as the tools' backend; a messages view of what each turn added; a timeline of all calls |
| s03 Parallel tool calls | Several tool calls per turn on the timeline; an automatic check that all `tool_result`s went back in one user message |
| s04 Gate and block | A "block tool X" toggle (`work/policy.json`); the mock API's write log proving zero writes; the "Why?" chain from outcome back to the code line, shown as a highlighted snippet |
| s05 Tool runner and approval | The run pauses for Approve or Deny in the UI |
| s06 Strict schema | A malformed-call fuzzer and its results |

## Curriculum
Every module ends with `/quiz <module>` (all misses listed and recorded) and then a project build.
1. **Module 02, The Agent Loop.**
   - Lab 02 (above).
   - 02-A: tools, skills, memory and MCP, including a small MCP server over the Meridian API.
   - 02-B: ticket triage as chaining and routing (Project 01); vendor screening as a LangGraph `Send` fan-out with per-check timeouts (Project 02); supervisor and swarm patterns; checkpointer resume; human-in-the-loop with `interrupt()`.
   - 02-C guardrails: prompt-injection test cases and enforcement outside the model.
   - 02-D: state, idempotency and compaction.
2. **Module 01, Foundations.**
   - A: chapters 2–4 come as primers inside Module 02.
   - G: tokens and cost. Lab 01 is the context budget: retrieved-context size, effort, thinking and `max_tokens`.
   - F: prompt caching, measured on ticket triage's fixed policy prefix.
   - E: techniques, each judged on cost against quality.
   - B: content still to be defined.
   - Electives C (NumPy) and D (pandas).
3. **Module 03, Retrieval.** Project 03 (policy RAG):
   - Qdrant in memory, hybrid search and reranking;
   - access-control and region/version filters in code, and a manager-only canary;
   - citations, and abstaining when the documents don't say.
   - Lab 03 breaks retrieval four ways, measured by a recall@5 eval built first.
4. **Module 04, Evals and Observability.** A one-command `eval_report.md` per project, an LLM judge (grounded, correct, hedged), a CI gate, traces in Phoenix, and a self-score against the capstone rubric.
5. **Module 05, Reference build.** The Smart Support Assistant built with the Claude Agent SDK and with the plain API; Project 04 (Agent Skills, GET-only hooks); deploying the LangGraph capstone.

## Out of scope unless a lesson needs it
- cassettes, replay, recording
- in-app budgets (the gateway enforces them)
- multiple users
- flow animations
- side-by-side run comparison
- a line-by-line execution gutter
- fault injection (likely needed from s04)

## Continuity
- `/today` starts a session: it restores context, re-quizzes up to three still-wrong items, and continues from PROGRESS.md's next action.
- `/wrap` ends one: it rewrites PROGRESS.md, exports learner progress, and commits and pushes.
- The SessionStart hook prints the status when you skip `/today`.
- Learner state lives in SQLite, and the export is committed.

## Open items
- The programme README with baseline rules B1–B5, which the Projects specs refer to, isn't on disk.

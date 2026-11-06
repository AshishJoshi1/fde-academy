# FDE Academy: progress

This file is the single source of truth for where the build and the teaching stand. `/wrap` rewrites the "Current position" and "Last session" sections at the end of every session.

## Current position
- **How we work:** the learning lab is built lesson by lesson (`docs/PLAN.md`). Each lesson is its content, plus the app features it needs, plus Ashish doing it in the UI.
- **Teaching:** Module 02, Lab 02, `m02.lab02.s01` "One call" is in progress.
  - **Runs so far:**
    - one at effort `low` (`stop_reason: end_turn`, blocks `['text']`, usage 22 in and 66 out, $0.001408);
    - runs from the lab page;
    - a run on `claude-haiku-4-5` that failed with a 400, because Haiku 4.5 has no `effort` parameter.
  - **Covered:**
    - the raw request JSON and the SDK's `idempotency_key`;
    - the gateway's headers (budget, rate limits, cost, no `request-id`);
    - why `content[0].text` is unsafe;
    - why 4xx errors aren't retried (`_base_client.py:934`);
    - per-model request shapes (`effort` on Opus 5.5 and Sonnet 5.5, `budget_tokens` on Haiku 4.5);
    - reading a gateway-wrapped error.
  - **Open:**
    - the 13-token puzzle (66 output tokens against about 53 for the text), which becomes card E3;
    - the stage-1 predictions (`x-stainless-retry-count`, relay cost against `x-litellm-response-cost-original`, the roughly 3 s before the first call), which go into card E1;
    - the optional Haiku 4.5 challenge (make the code run on it).
  - **Quiz q1–q3:** not asked yet. No misses recorded.
- **Building:**
  - The foundation is done.
  - **s01 stage 1 is done:**
    - **the runner** (`runs/`: Job Object process tree, time limit, allowlisted environment, console over SSE, code snapshot and events per run);
    - **the thin relay** (`relay.py`: dummy key in, real key out, every request and response recorded in order, streams too, cost from `pricing.yaml`);
    - **the lab page** `/lab/<step-id>`.
  - **The simple editor on the lab page is done:** line numbers, Tab and Enter handling, Ctrl+S, Run saves first, Reset, and a 409 guard against overwriting a VS Code edit.
  - The model picker shows what each model accepts. 82 tests pass.
- **Next first action:** s01 stage 2, experiment cards and the quiz on the lab page (server-rendered HTML and vanilla JavaScript).
  1. Replace the step schema's replay and cassette fields (`run.mode`, `run.cassettes`, the trace quiz type's `trace`) with `experiments:` (`docs/PLAN.md`, "Experiment format").
  2. Write s01's cards in `content/m02-agent-loop/lab02-agent-loop/s01-one-call/step.yaml`:
     - **E1 What comes back**, including the stage-1 predictions above;
     - **E2 Turn up effort**;
     - **E3 The missing tokens**, with a count-tokens tool on the page;
     - **E4 Hit the cap** (`max_tokens=20`);
     - candidate **E5 Switch the model**: on `claude-haiku-4-5` it's a 400, and Ashish fixes the code for that model.
  3. Grade predictions against the run (block types, `stop_reason`, token counts, cost), and show the diff since the previous run.
  4. Add quiz q1–q3 on the page, recorded in the store, with spaced review on the home page.
  - **Done when** Ashish can play s01 end to end in the lab page, and pytest covers prediction grading, the diff and quiz recording.
- **Then:** s01 stage 3, the tutor.

## Last session
- **Date:** 2026-11-06 to 2026-11-07 (second session)
- **Done:**
  - **Design system:**
    - `web/src/styles/academy.css`, with a data palette validated for colour-blind readers in both modes;
    - the `/design` style guide, a styled 401 page, `/auth?next=` with a safe-path check, and the restyled home page.
  - **Re-planned to a learning lab built lesson by lesson:**
    - `docs/PLAN.md` and `README.md` rewritten;
    - cassettes and replay dropped; simple features first.
  - **Gateway:** credentials in `%LOCALAPPDATA%\fde-academy\anthropic.env`, gateway facts in CLAUDE.md, and `claude-haiku-4-5` added to `pricing.yaml`.
  - **Running lessons:** `tools/run_live.py`, and `playground/` tracked in git.
  - **s01 stage 1:** runner, thin relay and lab page. Verified with end-to-end tests (real subprocesses, a fake gateway) and in headless Edge.
  - **Stage 2, first part:** the simple editor and the model notes.
  - **Fixed:** the `.gitignore` rule `runs/` also hid the `src/academy_server/runs/` package. It's now `/runs/`.
- **Open questions:**
  - The programme README with baseline rules B1–B5, which the Projects specs refer to, isn't on disk. I need it from you, or I'll rebuild it from App 2's summary.

## Tracked repos
- `.` (fde-academy) → https://github.com/AshishJoshi1/fde-academy

## Build: lesson by lesson (details in `docs/PLAN.md`)
- [x] Foundation: continuity, `run.py`, server shell and security gates, store and migrations, content loader, `labctl`, design system, `tools/run_live.py`
- s01 One call
  - [x] 1. Runner and thin relay, plus the lab page
  - [ ] 2. Experiment cards, quiz, run history, spaced review (on the lab page). The simple editor and model notes are done.
  - [ ] 3. Tutor
  - [ ] s01 content written as experiments E1–E4 (plus candidate E5). Replace the step schema's replay and cassette fields (`run.mode`, `run.cassettes`, the trace quiz type's `trace`) with `experiments:`
  - [ ] Ashish completes s01 in the UI
- [ ] s02 Manual loop
- [ ] s03 Parallel tool calls
- [ ] s04 Gate and block
- [ ] s05 Tool runner and approval
- [ ] s06 Strict schema

## Curriculum progress
| Module | Lessons built | Taught | Quiz score | Project built |
|---|---|---|---|---|
| 02 The Agent Loop | s01 (v1; experiments pending) | s01 in progress | – | 01 ticket triage, 02 vendor screening |
| 01 Foundations (A, G, F, E, B; C and D are electives) | – | – | – | – |
| 03 Retrieval | – | – | – | 03 policy RAG |
| 04 Evals & Observability | – | – | – | eval reports, CI gate |
| 05 Reference build | – | – | – | 04 proposal builder, deploy |

## Decisions log
- 2026-11-06:
  - Teach the Agent Loop first.
  - Local app, bring your own key.
  - FastAPI server. Server-rendered pages first; React and Monaco only if a lesson needs them.
  - Default `claude-opus-5-5`.
  - Private GitHub backup.
  - Commit and push at `/wrap` without asking.
  - UI look: an Anthropic-inspired warm-neutral design system (ivory, oat and slate, a clay accent, serif headings) in one stylesheet; data colours validated with the dataviz validator.
- 2026-11-06 (later):
  - A learning lab for one learner, built lesson by lesson; each lesson adds only the features it needs (`docs/PLAN.md`).
  - Live calls only: no cassettes, replay or recording. Budgets are left to the gateway.
  - Experiments are lesson content (`experiments:` in `step.yaml`): predict, change one thing, run, compare, explain.
  - The tutor uses Sonnet 5.5 through the gateway. Lesson code defaults to Opus 5.5.
  - Ashish's code lives in `playground/<step-id>/`, tracked in git.
  - Live calls go through the Bounteous LiteLLM gateway, with credentials in `%LOCALAPPDATA%\fde-academy\anthropic.env` and never in user-wide env vars (CLAUDE.md, "Gateway").
- 2026-11-07:
  - Simple features first: server-rendered pages, vanilla JavaScript, and a simple editor on the lab page (a textarea with Save), plus VS Code on the same files. The Monaco workbench comes later, only if a lesson needs it.
  - The lab's model picker offers `claude-opus-5-5`, `claude-sonnet-5-5` and `claude-haiku-4-5`, each with a note on what it accepts.
  - `claude-haiku-4-5` is priced from the Claude API skill's model table ($1 in, $5 out per million tokens).

# FDE Academy: progress

This file is the single source of truth for where the build and the teaching stand. `/wrap` rewrites the "Current position" and "Last session" sections at the end of every session.

## Current position
- **How we work:** the learning lab is built lesson by lesson (`docs/PLAN.md`):
  - **building runs ahead of learning:** the next build doesn't wait for Ashish to finish a lesson. He does the lessons in the UI at his own pace, and a step that misleads him gets fixed when he reaches it;
  - **outline first:** guide-step titles approved by Ashish before any build;
  - **one lesson (or build stage) per session;**
  - `tools/browser_check.py <step-id>` passes before a lesson is handed over;
  - every `/wrap` logs the session's `/cost` figure in the "Cost log" below and proposes 1–3 flash cards.
- **Teaching:** Module 02, Lab 02. Ashish is on `m02.lab02.s01` "One call" (9 steps, g1–g9, experiments E2–E5, the quiz in g9), started over on 2026-11-11; steps 2–9, E2–E5, the quiz and the tutor hands-on H1–H3 aren't done yet.
  - **s02 "The manual loop"** is built and ready at `/lab/m02.lab02.s02`, for when he gets there.
  - **Spaced review:** g3.c1 (s01) is **still wrong**, missed again in today's review: he picked `end_turn`, but `tool_use` means "run the tools, then call again". s02's g2 and g5 teach it in his own trace (the Timeline labels each call with its stop_reason).
  - **Flash cards:** 17 in the deck (3 added today), 1 reviewed (`cache-share`, known).
- **Building:** s01 and s02 are complete.
  - **s02** (`content/m02-agent-loop/lab02-agent-loop/s02-manual-loop/`): 8 guided steps (define a tool, the model asks, run the tool, send the result back, loop until end_turn, history only grows with E1, drop a tool_result with E2, quiz q1–q3), written from measured runs (`docs/PLAN.md`, "s02 'The manual loop': the end result").
  - **New in the app for s02:**
    - **the mock Meridian API as a fixture** (`src/academy_server/fixtures/`, vendored unchanged from Projects/04): one per run, its URL and token in the lesson env, each request an `api.request` run event; `run_live.py` starts it too;
    - **lab panels** a step turns on with `panels:`: a timeline (model calls, the tool run between them, API requests), the messages each call sent (carried over or new; the failed call's error unwrapped), and the mock API's request log;
    - **14 new run facts** (first call, loop growth, messages, history_grows, tools, run cost, API requests); the tutor sees the API requests too.
  - **Checks:** 155 tests pass. `tools/browser_check.py` passes on `m02.lab02.s02` (8 steps, the three panels, Start over, flash cards) and on `m02.lab02.s01` (new panels hidden).
- **Next first action:** in a fresh session, propose the s03 "Parallel tool calls" outline for Ashish's OK: guide-step titles, one line each, plus its experiment (a question that needs 3 lookups at once). The source is `docs/PLAN.md`, Module 02 outline, row 2 (several `tool_use` blocks in one turn; all results in one user message; `is_error`).
  - After his OK, build the s03 content and the features it needs: parallel calls on the timeline, and an automatic check that all `tool_result`s went back in one user message.
  - **Done when:** `tools/browser_check.py m02.lab02.s03` passes, then `/wrap`. Then re-estimate Module 02 from the cost log (s02 and s03).

## Last session
- **Date:** 2026-11-11 (second session)
- **Done:**
  - **Spaced review:** g3.c1 asked again and missed again (`end_turn`), recorded with `labctl` (attempt #7).
  - **s02 outline** approved as proposed (8 steps, E1 and E2), then built.
  - **Measured live** through the relay with a throwaway home (learner data untouched): 3 normal runs alike (Call 1: 469 input tokens and only a `tool_use` block; Call 2: 3 messages, 724 input tokens, `end_turn`; about $0.008–0.009 a run), the dropped `tool_result` (400, not retried, 2 calls), and `count_tokens` for where the tokens go (question 33, tool 436, tool result about 190).
  - **Built:** the fixture, the three panels, the new facts, tool-aware fake gateways (browser check and run tests), and tests: `tests/test_fixtures.py` (including a check that the vendored copy matches Projects/04), the real s02 starter run end to end against the real mock API, and loop facts.
  - **Docs:** CLAUDE.md layout (`fixtures/`), `docs/PLAN.md` (Architecture: fixtures and panels; s02 end result).
  - **Flash cards:** `tool-tokens`, `no-tool-result` and `record-before-send` added.
- **Open questions:**
  - **1-hour TTL:** does the gateway pass `ttl: "1h"` through? Still unverified. It can be measured for cents: ask a first question after the cache has expired, and look for `ephemeral_1h_input_tokens` > 0 in "Show request".
  - **Module 02 projects:** set aside. The choice between the Claude Agent SDK and LangGraph for them is undecided and gets discussed after the 17 lessons.
  - **Module 02 outline:** still proposed in `docs/PLAN.md`. Each lesson's steps get approved when that lesson starts.
  - **B1–B5:** the programme README with baseline rules B1–B5, which the Projects specs refer to, isn't on disk.

## Tracked repos
- `.` (fde-academy) → https://github.com/AshishJoshi1/fde-academy

## Build: lesson by lesson (details in `docs/PLAN.md`)
- [x] Foundation: continuity, `run.py`, server shell and security gates, store and migrations, content loader, `labctl`, design system, `tools/run_live.py`
- [x] Learner tools: Start over, flash cards (`docs/PLAN.md`, "Learner tools")
- s01 One call
  - [x] 1. Runner and thin relay, plus the lab page
  - [x] 2. Guided steps, experiments, quiz, run history, spaced review, browser check
  - [x] 3. Tutor (Sonnet 5.5, one thread per guide step, cached lesson prefix, "Show request")
  - [x] s01 content: guided steps g1–g9 with experiments E2–E5 and quiz q1–q3
  - [ ] Ashish does s01 in the UI (at his own pace; not a gate for the next build)
- [ ] Lessons 1–17 of the Module 02 outline (`docs/PLAN.md`, proposed). Lab 02 first:
  - [x] s02 Manual loop: content g1–g8 with E1, E2 and q1–q3; the Meridian fixture, timeline, messages and mock API panels
  - [ ] s03 Parallel tool calls
  - [ ] s04 Gate and block
  - [ ] s05 Tool runner and approval
  - [ ] s06 Strict schema
  - [ ] Lessons 6–17: 02-A to 02-D
- [ ] Module 02 projects: discussed with Ashish after all 17 lessons

## Curriculum progress
Lesson ids follow the curriculum's module order, not the build order: Lab 01 (the context budget) belongs to Module 01 Foundations, which is built after Module 02.

| Module | Lessons built | Taught | Quiz score | Project built |
|---|---|---|---|---|
| 02 The Agent Loop | s01 (guided, with tutor), s02 (guided) | s01 started over on 2026-11-11 (step 1 of 9 was done before); tutor tried once; s02 not started | – | after the 17 lessons: 01 ticket triage, 02 vendor screening |
| 01 Foundations (A, G, F, E, B; C and D are electives) | – | – | – | – |
| 03 Retrieval | – | – | – | 03 policy RAG |
| 04 Evals & Observability | – | – | – | eval reports, CI gate |
| 05 Reference build | – | – | – | 04 proposal builder, deploy |

## Cost log
Claude Code $ is the session's `/cost` total. Gateway $ comes from `labctl status` (learner spend), plus any measurement calls made outside the learner's data.

| Date | Work | Claude Code | Gateway |
|---|---|---|---|
| 2026-11-09 (1st) | s01 stage 2, built twice; s01 content from measured runs | $16 | about $0.02 (measurements) |
| 2026-11-09 (2nd) | `/today` review, s01 g1 content fix, tutor (stage 3) built and measured | $4.87 | $0.010 learner + $0.033 tutor measurement |
| 2026-11-11 | `/today` review; learner tools Start over and flash cards built and browser-checked | $7.09 | $0.00 (browser checks use a fake gateway) |
| 2026-11-11 (2nd) | `/today` review; s02 "The manual loop" outlined, measured, built and browser-checked | $10.07 | $0.00 learner + about $0.032 measurement (5 runs; `count_tokens` is free) |

- **Estimate against actual:** the tutor was estimated at $7–13 and the whole session cost $4.87. Re-estimate Module 02 after s03, from the s02 and s03 rows.
- **Where the 2026-11-11 cost went:**
  - 97% of input came from the cache (12.4M tokens read, 323K written), over 79 requests;
  - one cache miss after an idle past the 1-hour TTL re-cached 37.7K tokens, and the context compaction forced one rebuild;
  - `/wrap` was about 6% of usage and `/today` about 4%.
- **Where the 2026-11-11 (2nd) cost went** ($10.07 over 113 requests, 99% of input from the cache, no cache misses):
  - cache reads, 25.1M tokens: about $5.02 (half);
  - output, 126.2K tokens (the lesson, the code, the tests): about $2.52;
  - cache writes, 314.6K tokens at the 1-hour price: about $2.52;
  - reading `lab.html` whole (about 24K tokens) put it in every later turn's context; read large files in parts.

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
- 2026-11-09:
  - **Teaching format:** lessons are guided walkthroughs: teach one idea, highlight its code lines, say what to do, show the learner's own run values with what to notice, then check with the why.
    - Experiments come only after the idea is taught, inside a step; the quiz is the last step.
    - Run is never locked, the lesson text is never hidden, and the model menu starts on Opus 5.5.
  - **Grading:** predictions and checks are graded against a fixed answer or a fact measured from the run's events (`schema.FACTS`; an unknown fact fails validation).
    - Check and quiz answers are stored as quiz attempts, so misses come back in spaced review.
    - A value the run didn't produce is "not graded", never a miss.
  - **Lesson text:** markdown rendered with `markdown-it-py`, raw HTML disabled.
  - **How we work:** outline first (step titles approved before any build), one lesson per session, and `tools/browser_check.py` (fake gateway, throwaway data) passing before a lesson is handed over.
  - **Module 02 scope:** 17 lessons after s01, proposed in `docs/PLAN.md`. Each module ends with guided projects in the same format, with code that builds up across steps in the project's own repo.
    - The Module 02 projects, including Project 02's SDK, are discussed only after all 17 lessons.
- 2026-11-09 (later):
  - **Tutor:** `claude-sonnet-5-5` at effort `low`, with the Anthropic SDK (not raw HTTP) through the gateway.
    - One thread per guide step, with the lesson as a cached prefix (1-hour TTL) and the lab context resent only on change.
    - The rules are a file Ashish owns (`playground/tutor/rules.md`).
    - No server-side refusal fallback: calls go through LiteLLM, and a refusal returns a message and stores nothing.
  - **Projects:** the Module 02 projects are set aside. The choice between the Claude Agent SDK and LangGraph for them is made later.
  - **Cost:** every `/wrap` logs `/cost` in the Cost log. Module 02 is re-estimated from those numbers after s02 and s03.
- 2026-11-11:
  - **Building runs ahead of learning:** building modules and labs comes first; Ashish finishes the course at his own pace, and finishing a lesson is no longer a gate for the next build.
  - **Learner tools** Ashish asks for are the one exception to "no feature without a lesson": Start over and flash cards.
  - **Start over** keeps the quiz, spend and run history; only the lab's view starts fresh (markers, nothing deleted). The code reset is a checkbox.
  - **Flash cards** hold what building the lab taught, each fact with its source. `/wrap` proposes 1–3 per session, and only the ones Ashish picks are added. A review counts as a quiz attempt, so a miss comes back in spaced review.
- 2026-11-11 (later):
  - **s02 outline** approved as proposed: 8 steps, with E1 (history grows) and E2 (drop a `tool_result`).
  - **Fixtures run in the server, one per run:** the mock Meridian API starts on a free port with a fresh token, and its requests are run events, so the timeline orders model calls and API requests on one clock. The vendored copy stays byte-identical to Projects/04, and a test checks it.
  - **Lab panels are per step** (`panels:` in `step.yaml`): s01 keeps the console only; s02 adds the timeline, the messages view and the mock API log, built on the design system's trace and messages-diff styles.
  - **Measurement runs** use a throwaway home through the real relay, so the learner's runs, spend and history stay his own.

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
  - **s02 "The manual loop"** (9 steps, opening with "Meet Meridian") and **s03 "Parallel tool calls"** are built and ready at `/lab/m02.lab02.s02` and `/lab/m02.lab02.s03`.
  - **Spaced review:** nothing still wrong. g3.c1 (s01: `tool_use` means "run the tools, then call again") was answered right on 2026-11-12, so it's fixed after retry.
  - **Flash cards:** 20 in the deck (3 added on 2026-11-12), 1 reviewed (`cache-share`, known).
- **Building:** s01, s02 and s03 are complete.
  - **s03** (`content/m02-agent-loop/lab02-agent-loop/s03-parallel-tools/`): 6 guided steps (three lookups in one turn, match each result by id, all results in one user message, fewer round trips with E1 "turn parallel calls off", a lookup fails with E2 "an ID that doesn't exist", quiz q1–q3), written from measured runs (`docs/PLAN.md`, "s03 'Parallel tool calls': the end result").
  - **New in the app for s03:**
    - **the Meridian data page** (`/meridian`, in the top bar and linked from the Mock API panel): every opportunity, account and rate-card row the mock API serves, read from its seed files;
    - **s02's first step, "Meet Meridian"**: the company, what OPP-, ACC- and R- IDs are, the three read endpoints;
    - **timeline:** each tool row shows its input and the end of its id, and a call that asked for several shows "N tool_use";
    - **the one message check**, under the timeline and as a pill in Messages, flags split or unanswered results; the same rule is the run fact `loop.results_in_one_message`;
    - **8 new run facts:** `run.input_tokens`, `first.response.tool_uses`, `first.response.tool_inputs`, `loop.tool_results`, `loop.error_results`, `loop.results_in_one_message`, `prev.run.input_tokens`, `ratio.input_tokens`;
    - the fake gateways (browser check and run tests) ask for every OPP- ID in the question in one turn, or one per turn under `disable_parallel_tool_use`.
  - **Checks:** 161 tests pass, including s03's real starter end to end against the real mock API in three forms (as written, E1's change, E2's change), the split and missing results check, and the Meridian page. `tools/browser_check.py` passes on s03 (6 steps), s02 (9 steps) and s01, and now opens the Meridian page too.
- **Next first action:** in a fresh session, propose the s04 "Gate and block" outline for Ashish's OK: guide-step titles, one line each, plus its experiment. The sources are `docs/PLAN.md`, Module 02 outline row 3 (policy enforced in code, not the prompt; a prompt-only "don't write" against a code gate; the request log proves zero writes), and the Lab 02 roadmap row for s04 (a block-tool toggle in `work/policy.json`, the mock API's write log, the "Why?" chain).
  - The mock API's write endpoint is `PATCH /opportunities/{id}`: it accepts the call and stores nothing. Measure live what a prompt-only rule does before writing the steps.
  - **Done when:** `tools/browser_check.py m02.lab02.s04` passes, then `/wrap`.

## Last session
- **Date:** 2026-11-12
- **Done:**
  - **Unwrapped work** from 2026-11-11 (Start over sets lessons back to Not started) was committed and pushed on its own (`fc2ca72`), after the tests and the s02 browser check passed.
  - **Spaced review:** g3.c1 answered right (`tool_use`), recorded with `labctl` (attempt #8).
  - **s03 outline** approved, with "split the results" kept only if the API returned a 400. It doesn't, so that experiment was cut and the missing-ID experiment became E2.
  - **Lessons now introduce Meridian before using its IDs:** s02's "Meet Meridian" step and the Meridian data page.
  - **Measured live** with a scratch script against the gateway (learner data untouched): 6 runs (parallel twice, parallel off, results split, results reversed, OPP-1099), about $0.10. Then one `tools/run_live.py m02.lab02.s03` run of the real starter: 3 `tool_use` blocks, one results message, the right answer (OPP-1046, 22%).
  - **Built:** the s03 content, s02's g1, `/meridian`, the timeline and messages changes, the new facts, the fake gateways and the tests.
  - **Docs:** `docs/PLAN.md` (Architecture: the Meridian data page and the one message check; the s02 table; the s03 end result; the Lab 02 roadmap), CLAUDE.md layout (`/meridian`).
  - **Flash cards:** `parallel-saves-calls`, `cache-miss-big-context` and `split-tool-results` added.
  - **Module 02 re-estimated** from the cost log (below).
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
  - [x] s02 Manual loop: content g1–g9 (g1 "Meet Meridian") with E1, E2 and q1–q3; the Meridian fixture, timeline, messages and mock API panels
  - [x] s03 Parallel tool calls: content g1–g6 with E1, E2 and q1–q3; several tool calls per turn on the timeline, the one message check, the Meridian data page
  - [ ] s04 Gate and block
  - [ ] s05 Tool runner and approval
  - [ ] s06 Strict schema
  - [ ] Lessons 6–17: 02-A to 02-D
- [ ] Module 02 projects: discussed with Ashish after all 17 lessons

## Curriculum progress
Lesson ids follow the curriculum's module order, not the build order: Lab 01 (the context budget) belongs to Module 01 Foundations, which is built after Module 02.

| Module | Lessons built | Taught | Quiz score | Project built |
|---|---|---|---|---|
| 02 The Agent Loop | s01 (guided, with tutor), s02, s03 (guided) | s01 started over on 2026-11-11 (step 1 of 9 was done before); tutor tried once; s02 and s03 not started | – | after the 17 lessons: 01 ticket triage, 02 vendor screening |
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
| 2026-11-12 | `/today` review; the 2026-11-11 Start-over fix committed; s03 "Parallel tool calls" outlined, measured, built and browser-checked; s02 "Meet Meridian"; the Meridian data page | $12.02 | $0.00 learner + about $0.12 measurement (6 runs, plus one live run of the starter) |

- **Estimate against actual:** the tutor was estimated at $7–13 and the whole session cost $4.87.
- **Module 02 re-estimate** (from the s02 and s03 rows): a lesson session costs about $10–12 in Claude Code ($10.07 for s02; $12.02 for s03, which also built s02's new step and the Meridian page). 15 lessons are left (s04–s06, then lessons 6–17), so about $150–180, plus the two guided projects. Gateway measurement stays under $0.15 a lesson.
- **Where the 2026-11-11 cost went:**
  - 97% of input came from the cache (12.4M tokens read, 323K written), over 79 requests;
  - one cache miss after an idle past the 1-hour TTL re-cached 37.7K tokens, and the context compaction forced one rebuild;
  - `/wrap` was about 6% of usage and `/today` about 4%.
- **Where the 2026-11-11 (2nd) cost went** ($10.07 over 113 requests, 99% of input from the cache, no cache misses):
  - cache reads, 25.1M tokens: about $5.02 (half);
  - output, 126.2K tokens (the lesson, the code, the tests): about $2.52;
  - cache writes, 314.6K tokens at the 1-hour price: about $2.52;
  - reading `lab.html` whole (about 24K tokens) put it in every later turn's context; read large files in parts.
- **Where the 2026-11-12 cost went** ($12.02 over 106 requests, 97% of input from the cache):
  - cache writes, 665.8K tokens at the 1-hour price: about $5.33 (44%). One cache miss re-cached 260K tokens (about $2.08); `/cost` reported it as likely server-side, with the prompt unchanged;
  - cache reads, 21.9M tokens: about $4.38;
  - output, 115.6K tokens: about $2.31;
  - the context averaged about 207K tokens per request (21.9M ÷ 106): the `/claude-api` skill text, whole-file reads and the long build stayed in every later turn;
  - `/wrap` was about 10% of usage and `/today` about 4%.

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
- 2026-11-12:
  - **s03 outline** approved, with "split the results" kept only if it returned a 400. Measured, the API accepts split results (it joins consecutive user messages), so it was cut: s03 has 6 steps, E1 (parallel calls off) and E2 (an ID that doesn't exist).
  - **Lessons introduce the scenario before using its IDs:** s02 opens with "Meet Meridian", and the Meridian data page (`/meridian`) shows every record the mock API serves, linked from the top bar and the Mock API panel.
  - **The one message check is the lab's**, because the API won't flag split results: on the timeline, in the messages view, and as the run fact `loop.results_in_one_message`.

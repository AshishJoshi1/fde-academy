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
  - **Flash cards:** 24 in the deck (7 added on 2026-11-12), 1 reviewed (`cache-share`, known).
- **Building:** s01, s02 and s03 are complete. The cost rules are applied (CLAUDE.md "How we work", `today.md`, `wrap.md`), `lab.html`'s JavaScript is split into `src/academy_server/pages/lab_js/` (served at `/static/lab-js/`), and decisions and cost analysis live in `docs/DECISIONS.md`. 162 tests pass; `tools/browser_check.py` passes on s01, s02 and s03 (it failed once on s03 with a null `textContent` error, then passed three times in a row: a suspected timing flake).
- **Next first action:** in a fresh session (`/clear` first), build **s04 "Gate and block"** from the outline Ashish approved on 2026-11-12. Try Sonnet 5.5 for this session (half the price) and log its cost against the $8 target; note any rework.
  - **Guide steps:** (1) Meet the write tool: add `update_opportunity` next to the lookup; (2) Ask it in the prompt: "never write" in the system prompt, then check the request log for a PATCH; (3) A gate in code: `work/policy.json` lists blocked tools, checked before a tool runs (highlighted lines); (4) Return the block as a result: `tool_result` with `is_error: true` and a reason; (5) Prove zero writes: the mock API's request log shows no PATCH, and the "Why?" chain walks from the outcome back to the gate's line; (6) Quiz q1–q3.
  - **Experiments:** E1 "prompt against gate" (try to talk the model into the write, once with only the prompt rule and once with the gate; predict the PATCH count each time); E2 "flip the toggle" (allow `update_opportunity` in `policy.json`, rerun).
  - **New in the app:** the block-tool toggle, a write-attempt marker on the mock API log, the "Why?" chain as a highlighted snippet. The mock API's `PATCH /opportunities/{id}` accepts the call but stores nothing, so the request log is the proof.
  - **Done when:** the content validates, tests and `tools/browser_check.py m02.lab02.s04` pass, `docs/PLAN.md` records s04's end result, then `/wrap`.

## Last session
- **Date:** 2026-11-12 (third session of the day)
- **Done:**
  - **Cost rules applied:** CLAUDE.md "How we work" (the $8 target, `/clear` after `/wrap`, read in parts, subagents for big references, screenshots only when a layout is in question, `/clear` after an idle hour, Sonnet 5.5 trial); `today.md` skips the second status run and reads only the top of PROGRESS.md; `wrap.md` writes decisions to `docs/DECISIONS.md`.
  - **`docs/DECISIONS.md`** now holds the Decisions log and the cost breakdowns; PROGRESS.md shrank by about 55 lines.
  - **`lab.html` split:** from 1,512 lines to about 90; four scripts moved to `pages/lab_js/`, with a `window.LAB` config and a path-safe route; `tests/test_editor.py` covers it.
  - **s04 outline** proposed and approved as written (above).
- **Open questions:**
  - **1-hour TTL:** does the gateway pass `ttl: "1h"` through? Still unverified (look for `ephemeral_1h_input_tokens` > 0 in "Show request" on a first question after the cache expired).
  - **Browser check flake:** the one s03 failure (null `textContent`) wasn't reproduced; if it returns, find the race.
  - **Module 02 projects:** set aside until after the 17 lessons. **Module 02 outline** is still proposed in `docs/PLAN.md`. **B1–B5** isn't on disk.
  - **Flash cards:** none added this session (none picked).

## Tracked repos
- `.` (fde-academy) → https://github.com/AshishJoshi1/fde-academy

## Build: lesson by lesson (details in `docs/PLAN.md`)
- [x] Foundation: continuity, `run.py`, server shell and security gates, store and migrations, content loader, `labctl`, design system, `tools/run_live.py`
- [x] Learner tools: Start over, flash cards, glossary (`docs/PLAN.md`, "Learner tools")
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

| Date | Work | Claude Code (target $8) | Gateway |
|---|---|---|---|
| 2026-11-09 (1st) | s01 stage 2, built twice; s01 content from measured runs | $16 | about $0.02 (measurements) |
| 2026-11-09 (2nd) | `/today` review, s01 g1 content fix, tutor (stage 3) built and measured | $4.87 | $0.010 learner + $0.033 tutor measurement |
| 2026-11-11 | `/today` review; learner tools Start over and flash cards built and browser-checked | $7.09 | $0.00 (browser checks use a fake gateway) |
| 2026-11-11 (2nd) | `/today` review; s02 "The manual loop" outlined, measured, built and browser-checked | $10.07 | $0.00 learner + about $0.032 measurement (5 runs; `count_tokens` is free) |
| 2026-11-12 | `/today` review; the 2026-11-11 Start-over fix committed; s03 "Parallel tool calls" outlined, measured, built and browser-checked; s02 "Meet Meridian"; the Meridian data page; then the glossary (after the first wrap); then the cost-savings review, the Module 02 to 05 cost estimate and 3 cost cards | $14.99 at the glossary wrap ($12.02 at the first wrap, $2.97 for the glossary); the later turns' cost not given | $0.00 learner + about $0.12 measurement (6 runs, plus one live run of the starter) |
| 2026-11-12 (3rd) | `/today`; cost rules applied, Decisions log moved to `docs/DECISIONS.md`, `lab.html` JS split, s04 outline approved | not given | $0.00 |

- Estimates, breakdowns and the decisions log: `docs/DECISIONS.md`.

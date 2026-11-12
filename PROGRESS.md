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
  - **s02 "The manual loop"**, **s03 "Parallel tool calls"** and **s04 "Gate and block"** (8 steps, E1 and E2, q1–q3) are built and ready at `/lab/m02.lab02.s02`, `.s03` and `.s04`.
  - **Spaced review:** 2 still wrong, both from s03: g1.c2 (why the model could ask for all three lookups in one response: because none needs another's result) and g2.c1 (result order doesn't matter: results pair by `tool_use_id`). Missed again on 2026-11-12; recorded with `labctl`.
  - **Flash cards:** 24 in the deck (7 added on 2026-11-12), 1 reviewed (`cache-share`, known).
- **Building:** s01 to s04 are complete. s04 added the facts `api.writes` and `loop.blocked_results`, a "write attempt" pill and writes count in the Mock API panel, and a generalized timeline check in `tools/browser_check.py`. 163 tests pass; `tools/browser_check.py m02.lab02.s04` passes. `docs/PLAN.md` records s04's end result and measured runs.
- **Next first action:** in a fresh session (`/clear` first), propose the guide-step titles for **s05 "Tool runner and approval"** (`docs/PLAN.md`, Lab 02 roadmap: the run pauses for Approve or Deny in the UI) and get Ashish's OK before building. Done when the outline is approved. Optional: Sonnet 5.5 again (s04 cost $0.99 in Claude Code).

## Last session
- **Date:** 2026-11-12 (fourth session of the day, Sonnet 5.5)
- **Done:**
  - **`/today` review:** two s03 items re-asked, both wrong, recorded.
  - **s04 "Gate and block" built:** `update_opportunity` write tool, a prompt rule, a gate in the loop reading `work/policy.json`, `BLOCKED` results with `is_error`; 8 guide steps, E1 (push on the prompt rule) and E2 (gate the wrong tool), q1–q3. Measured live (one run each): prompt rule held, even against an "admin" push; the gate gave 0 writes with the model asking; gating only the lookup also gave 0 writes, from the model's caution.
  - **App:** facts `api.writes` and `loop.blocked_results`; write-attempt pill and writes count in the Mock API panel; `docs/PLAN.md` s04 end result.
- **Open questions:**
  - **Outline deviation:** E1 and E2 differ from the approved outline (the prompt rule held, so "prompt against gate" can't show a failure; "flip the toggle" would repeat g1). Ashish to say if he wants the outline's version.
  - **Write pill unseen:** the browser check's fake gateway never writes, so the pill hasn't been seen in a screenshot.
  - **1-hour TTL**, **browser check flake** and **Module 02 projects:** as before (see `docs/DECISIONS.md` and `docs/PLAN.md`).

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
  - [x] s04 Gate and block: content g1–g8 with E1, E2 and q1–q3; `api.writes`, `loop.blocked_results`, write-attempt pill
  - [ ] s05 Tool runner and approval
  - [ ] s06 Strict schema
  - [ ] Lessons 6–17: 02-A to 02-D
- [ ] Module 02 projects: discussed with Ashish after all 17 lessons

## Curriculum progress
Lesson ids follow the curriculum's module order, not the build order: Lab 01 (the context budget) belongs to Module 01 Foundations, which is built after Module 02.

| Module | Lessons built | Taught | Quiz score | Project built |
|---|---|---|---|---|
| 02 The Agent Loop | s01 (guided, with tutor), s02, s03, s04 (guided) | s01 started over on 2026-11-11 (step 1 of 9 was done before); tutor tried once; s02 and s03 not started | – | after the 17 lessons: 01 ticket triage, 02 vendor screening |
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
| 2026-11-12 (4th) | `/today` review (2 wrong); s04 "Gate and block" measured, built and browser-checked | $0.99 | 6 live measurement runs (not itemized) |

- Estimates, breakdowns and the decisions log: `docs/DECISIONS.md`.

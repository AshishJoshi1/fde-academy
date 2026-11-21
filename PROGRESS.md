# FDE Academy: progress

This file is the single source of truth for where the build and the teaching stand. `/wrap` rewrites the "Current position" and "Last session" sections at the end of every session.

## Current position
- **How we work:** the learning lab is built lesson by lesson (`docs/PLAN.md`):
  - **building runs ahead of learning:** the next build doesn't wait for Ashish to finish a lesson. He does the lessons in the UI at his own pace, and a step that misleads him gets fixed when he reaches it;
  - **outline first:** guide-step titles approved by Ashish before any build;
  - **one lesson (or build stage) per session;**
  - `tools/browser_check.py <step-id>` passes before a lesson is handed over;
  - every `/wrap` logs the session's `/cost` figure in the "Cost log" below and proposes 1–3 flash cards.
- **Teaching:** Module 02, Lab 02. Ashish is on `m02.lab02.s04` "Gate and block" in the UI (s01 was started over on 2026-11-11; s01 steps 2–9, E2–E5, the quiz and the tutor hands-on H1–H3 aren't done).
  - **s02 "The manual loop"** to **s13 "LangGraph basics"** are built and ready at `/lab/m02.lab02.s02` to `.s13`.
  - **Spaced review:** none outstanding.
  - **Flash cards:** 51 in the deck (3 added on 2026-11-21, 2nd session), 1 reviewed (`cache-share`, known).
- **Building:** s01 to s13 are complete. s13 added the `graph` panel (reads `@@graph` lines from the console) and `graph.*` facts. `langgraph` is the optional `graph` extra in `pyproject.toml` (1.2.24 installed in the venv; a fresh venv needs `pip install -e ".[graph]"`). All tests pass; `tools/browser_check.py m02.lab02.s13` passes. The next lesson in the table is **s14 "Fan-out and aggregation"** (`docs/PLAN.md`, Module 02 outline, lesson 13), which needs an outline first.
- **Trial-share work (decide first):** Ashish wants to share the lab with teammates. The approved-in-principle scope is in `C:\Users\AshishKumarJoshi\.claude\plans\how-much-effort-would-twinkly-origami.md` (copied into `docs/DECISIONS.md`): bring-your-own-key, per-user DB (already per-user), a zip builder with a test and an onboarding doc. **Opus 5.5 stays; no Sonnet-only change.** About 2 sessions. Open: Windows-only trial? Keep Haiku 4.5 in the picker?
- **Next first action:** in a fresh session (`/clear` first), ask Ashish whether to start the trial-share work (zip builder and test first, then onboarding doc, then BYOK) or the next lesson. For the lesson: propose the guide-step titles for **lesson 13 "Fan-out and aggregation"** (`docs/PLAN.md`: parallel workers with `Send` or subagents, per-worker timeouts, failing honestly, supervisor against swarm; three checks in parallel, one deliberately slowed; parallel lanes view with a "slow this worker" switch) and get Ashish's OK. Then build it, reusing s13's graph. Done when `tools/browser_check.py <its step id>` passes. Read the LangGraph `Send` docs (subagent) before any code.

## Last session
- **Date:** 2026-11-21 (2nd session, Sonnet 5.5).
- **Done:** `/today`; **s13 "LangGraph basics" built** (PLAN table lesson 12): g1–g10, E1 (take the reducer off `trace`), E2 (take the guard off the retry edge), q1–q3; `main.py` rebuilds s11's chain as a `StateGraph` (nodes classify, enrich, respond, fail; conditional retry edges; `trace` with an `add` reducer; `app.stream(..., stream_mode="values")`). Measured live (Sonnet 5.5, low): 9 visits and 6 calls; bad ticket path `classify -> enrich -> enrich -> fail`; E1 prints `path: respond` with no error; E2 makes 12 visits on ticket 4, 21 in all, 7 calls, then `GraphRecursionError` (default limit 10,007).
- **App:** `graph` panel (visits per ticket with the state after each, changed keys marked), `graph.*` facts, `@@graph` hidden from the Console, browser_check s13 branch. Tests pass.
- **Cards:** 3 added (`overwrite-is-silent`, `graph-loop-is-yours-to-bound`, `graph-adds-no-model-calls`).
- **Open questions:** the Graph panel was not inspected on screen; the trial-share questions above.

## Previous session (2026-11-18)
- **Done:** planning only: the trial-share work (BYOK, per-user DB, zip and onboarding doc) estimated; no code changed.

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
  - [x] s05 Tool runner and approval: content g1–g9 with E1, E2 and q1–q3; `labkit.approve`, approval card, `approval.*` facts
  - [x] s06 Strict schema: content g1–g8 with E1, E2 and q1–q3; `request.strict`, `fuzz.*` facts
  - [x] s07 Designing tools (02-A lesson 6): content g1–g8 with E1, E2 and q1–q3; `tally.*` and `request.tool_count` facts
  - [x] s08 Memory (lesson 7): content g1–g9 with E1, E2 and q1–q3; memory panel, Reset memory, `memory.*` facts
  - [x] s09 MCP (lesson 8): content g1–g9 with E1, E2 and q1–q3; no new app feature
  - [x] s10 The Claude Agent SDK (lesson 9): content g1–g9 with E1 and q1–q3; no new app feature
  - [x] s11 Prompt chains (lesson 10): content g1–g9 with E1, E2 and q1–q3; chain panel, `chain.*` facts
  - [x] s12 Routing and early exit (lesson 11): content g1–g9 with E1, E2 and q1–q3; route panel, `route.*` facts
  - [ ] Lessons 12–17: 02-B to 02-D need outlines
- [ ] Module 02 projects: discussed with Ashish after all 17 lessons

## Curriculum progress
Lesson ids follow the curriculum's module order, not the build order: Lab 01 (the context budget) belongs to Module 01 Foundations, which is built after Module 02.

| Module | Lessons built | Taught | Quiz score | Project built |
|---|---|---|---|---|
| 02 The Agent Loop | s01 (guided, with tutor), s02 to s13 (guided) | s01 started over on 2026-11-11 (step 1 of 9 was done before); tutor tried once; s02 to s08 not started | – | after the 17 lessons: 01 ticket triage, 02 vendor screening |
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
| 2026-11-12 (5th) | `/today` review (2 right); s05 "Tool runner and approval" outlined, measured, built and browser-checked; 3 cards | $1.87 | 4 live measurement runs (not itemized) |
| 2026-11-12 (6th) | `/today`; s06 "Strict tool schemas" outlined, premise tested live (0 of 8 broke), built and browser-checked | $0.90 | about $0.15 (live measurement runs, not itemized) |
| 2026-11-16 | `/today`; s07 "Designing tools" outlined, premise tested live (8 of 12 wrong with vague tools), built and browser-checked; 2 cards | $1.34 | $0.00 learner + about $0.15 (about 100 live calls, not itemized) |
| 2026-11-16 (2nd) | `/today`; s08 "Memory" premise tested live and outline proposed (not yet approved) | $0.28 | about $0.03 (one probe, two runs) |
| 2026-11-16 (3rd) | `/today`; s08 "Memory" outline approved, built and browser-checked; 3 cards | $1.25 | about $0.10 (live runs, not itemized) |
| 2026-11-16 (4th) | `/today`; s09, s10, s11 outlines approved; s09 "MCP" built and browser-checked; 3 cards | $0.80 (Sonnet 5.5; target $8) | about $0.10 (live runs, not itemized) |
| 2026-11-17 | `/today`; s10 "The Claude Agent SDK" researched, measured live through the relay, built and browser-checked; 3 cards | $1.51 (Sonnet 5.5) | about $0.15 (measurement runs; `labctl status` shows $0.04 learner today) |
| 2026-11-17 (2nd) | `/today`; s11 "Prompt chains" built, measured and browser-checked; chain panel; 3 cards | $1.25 | about $0.10 measurement (not itemized; `labctl status` shows learner spend only) |
| 2026-11-18 | `/today`; trial-share (BYOK, zip, onboarding) estimated and planned; no code | $0.64 (Sonnet 5.5; target $8) | $0.00 |
| 2026-11-21 | `/today`; s12 "Routing and early exit" outlined, built, measured live and browser-checked; route panel; 2 cards | $1.05 (Sonnet 5.5; target $8) | about $0.10 measurement (about 40 live calls, not itemized) |

- Estimates, breakdowns and the decisions log: `docs/DECISIONS.md`.
| 2026-11-21 (2nd) | `/today`; s13 "LangGraph basics" outlined, built, measured live and browser-checked; graph panel; 3 cards | $0.96 (Sonnet 5.5; target $8) | about $0.05 measurement (5 live runs, not itemized) |

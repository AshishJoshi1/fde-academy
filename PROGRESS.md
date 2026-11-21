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
  - **s02 "The manual loop"** to **s15 "Checkpoints and human-in-the-loop"** are built and ready at `/lab/m02.lab02.s02` to `.s15`.
  - **Spaced review:** none outstanding.
  - **Flash cards:** 57 in the deck (3 added on 2026-11-21, 4th session), 1 reviewed (`cache-share`, known).
- **Building:** s01 to s15 are complete. s15 added the `ckpt` panel (reads `@@ckpt` lines from the console) and `ckpt.*` facts, and `langgraph-checkpoint-sqlite` in the `graph` extra. All tests pass; `tools/browser_check.py m02.lab02.s15` passes. The next lesson in the table is **"Prompt injection"** (`docs/PLAN.md`, Module 02 outline, lesson 15; step id s16), which needs an outline first.
- **Open items for Ashish to decide:**
  - **Trial-share work:** share the lab with teammates. Scope is in `docs/DECISIONS.md` (copied from `C:\Users\AshishKumarJoshi\.claude\plans\how-much-effort-would-twinkly-origami.md`): bring-your-own-key, per-user DB (already per-user), a zip builder with a test and an onboarding doc. **Opus 5.5 stays; no Sonnet-only change.** About 2 sessions. Open: Windows-only trial? Keep Haiku 4.5 in the picker?
  - **Teach-only LangChain lesson:** outline proposed on 2026-11-21 (g1 what LangChain is; g2 LangChain, LangGraph and LangSmith; g3 s11's chain in LangChain terms; g4 what hand-written SDK calls keep visible; g5 what a framework gives and costs; g6 when to pick which; 3 quiz questions; no code, no live calls). Not yet approved; its place in the lesson order is undecided (`docs/PLAN.md`, Open items).
- **Next first action:** in a fresh session (`/clear` first), ask Ashish which to do: the trial-share work (zip builder and test first, then onboarding doc, then BYOK), the LangChain teach-only lesson (get the outline approved, then write `content/.../step.yaml` with no code), or the next lesson. For the lesson: propose the guide-step titles for **lesson 15 "Prompt injection"** (`docs/PLAN.md`: untrusted text as data, delimiting, a detection signal; `[ADMIN OVERRIDE]`-style tickets against your chain; an attack-case table) and get Ashish's OK. Then build it. Done when `tools/browser_check.py <its step id>` passes. Read any API docs it needs (subagent) before code.

## Last session
- **Date:** 2026-11-21 (4th session, Sonnet 5.5).
- **Done:** `/today`; **s15 "Checkpoints and human-in-the-loop" built** (PLAN table lesson 14): g1–g9, E1 (write before the pause), E2 (run again unchanged), E3 (say no), q1–q3. `main.py` is s13's graph trimmed to one path per ticket (`classify`, `enrich`, `apply`, `respond`, `declined`) with a `SqliteSaver` on `checkpoints.db`, `durability="sync"`, `interrupt()` in `apply`, the s05 `approve()` between two `invoke` calls, and a `CRASH_AT` constant that calls `os._exit(1)`. Measured live (Opus 5.5, low): baseline 6 checkpoints for ticket 1; kill at `respond` then resume under the same `THREAD` reruns only `respond` for ticket 1 (no second approval, no second PATCH); E1 `PATCH_FIRST = True` sends 2 PATCHes for one approval; E2 a finished thread reports "already finished" for both tickets; E3 Deny goes `apply (again)` → `declined`, no PATCH, no `respond` for ticket 1.
- **App:** `ckpt` panel (chips per ticket for what ran, stopped, wrote and replayed, plus the saved-checkpoint table), `ckpt.*` facts, `@@ckpt` hidden from the Console, browser_check s15 branch and a fake-gateway classifier for it. **Bug fixed:** `.stack {display:flex}` overrode the `hidden` attribute, so the Approve/Deny card was visible on every page since s04/s05; `web/src/styles/academy.css` now has `[hidden] { display: none !important; }`. Tests pass. The panel was checked on screen.
- **Cards:** 3 added (`interrupt-replays-the-node`, `checkpoint-saves-between-nodes`, `hidden-attribute-lost-to-display`).
- **Open questions:** the trial-share questions (Windows-only? Haiku 4.5 in the picker?); approve the LangChain outline and choose its place in the order. The outline promised a Kill/Resume control in the panel; the built lesson uses the `CRASH_AT` and `THREAD` constants instead (a real process kill, no new control).

## Previous session (2026-11-21, 3rd)
- **Done:** s14 "Fan-out and aggregation" built (lanes panel, `lanes.*` facts, 3 cards); see the Cost log.

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
  - [x] s13 LangGraph basics (lesson 12): content g1–g10 with E1, E2 and q1–q3; graph panel, `graph.*` facts
  - [x] s14 Fan-out and aggregation (lesson 13): content g1–g11 with E1, E2, E3 and q1–q3; lanes panel, `lanes.*` facts
  - [x] s15 Checkpoints and human-in-the-loop (lesson 14): content g1–g9 with E1, E2, E3 and q1–q3; ckpt panel, `ckpt.*` facts
  - [ ] Lessons 15–17: 02-C and 02-D need outlines (lesson 15 is prompt injection)
- [ ] Module 02 projects: discussed with Ashish after all 17 lessons

## Curriculum progress
Lesson ids follow the curriculum's module order, not the build order: Lab 01 (the context budget) belongs to Module 01 Foundations, which is built after Module 02.

| Module | Lessons built | Taught | Quiz score | Project built |
|---|---|---|---|---|
| 02 The Agent Loop | s01 (guided, with tutor), s02 to s15 (guided) | s01 started over on 2026-11-11 (step 1 of 9 was done before); tutor tried once; s02 to s08 not started | – | after the 17 lessons: 01 ticket triage, 02 vendor screening |
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
| 2026-11-21 (2nd) | `/today`; s13 "LangGraph basics" outlined, built, measured live and browser-checked; graph panel; 3 cards | $0.96 (Sonnet 5.5; target $8) | about $0.05 measurement (5 live runs, not itemized) |
| 2026-11-21 (3rd) | `/today`; s14 "Fan-out and aggregation" outlined, built, measured live and browser-checked; lanes panel; 3 cards; LangChain teach-only lesson planned | $1.82 (Sonnet 5.5; target $8) | about $0.05 measurement (5 live runs, not itemized; `labctl status` shows learner spend only) |
| 2026-11-21 (4th) | `/today`; s15 "Checkpoints and human-in-the-loop" outlined, built, measured live and browser-checked; ckpt panel; hidden-attribute CSS fix; 3 cards | $1.93 (Sonnet 5.5; target $8) | about $0.05 measurement (5 live runs, not itemized; `labctl status` shows learner spend only) |

- Estimates, breakdowns and the decisions log: `docs/DECISIONS.md`.

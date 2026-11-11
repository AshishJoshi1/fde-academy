# FDE Academy: progress

This file is the single source of truth for where the build and the teaching stand. `/wrap` rewrites the "Current position" and "Last session" sections at the end of every session.

## Current position
- **How we work:** the learning lab is built lesson by lesson (`docs/PLAN.md`):
  - **building runs ahead of learning:** the next build doesn't wait for Ashish to finish a lesson. He does the lessons in the UI at his own pace, and a step that misleads him gets fixed when he reaches it;
  - **outline first:** guide-step titles approved by Ashish before any build;
  - **one lesson (or build stage) per session;**
  - `tools/browser_check.py <step-id>` passes before a lesson is handed over;
  - every `/wrap` logs the session's `/cost` figure in the "Cost log" below and proposes 1–3 flash cards.
- **Teaching:** Module 02, Lab 02, `m02.lab02.s01` "One call", a guided lesson of 9 steps (g1–g9) with experiments E2–E5 and the quiz in g9.
  - **Started over** on 2026-11-11, with the code reset. The lab shows step 1 with no ticks; run history, quiz history and spaced review are kept.
  - **Spaced review:** g1.c2 (statelessness) is fixed after retry. **g3.c1 is still wrong:** he picked `end_turn`, but `tool_use` is the one that means "run the tools, then call again". It comes back in review.
  - **Flash cards:** 1 of 14 reviewed (`cache-share`, known).
  - Not done yet: steps 2–9, experiments E2–E5, the quiz, and the tutor hands-on H1–H3 (`docs/PLAN.md`, build stage 3).
- **Building:** s01 is complete: runner and relay, guided steps, experiments, quiz, run history, spaced review, and the tutor (`src/academy_server/tutor.py`; design and measured costs in `docs/PLAN.md`, "Tutor").
  - **Learner tools** (`docs/PLAN.md`, "Learner tools"):
    - **Start over:** one lesson (the lab page) or all lessons (the home page), with an optional playground code reset. It writes a marker per step in `step_restarts` (migration 5) and deletes nothing; lab reads take `since` and show only what came after the marker.
    - **Flash cards:** `/cards`, with the deck in `content/cards/build.yaml` (14 cards, 5 tags). A review is stored as a quiz attempt (`cards:<deck>:<card>`, module `cards`), so "Didn't know" comes back in spaced review. The home page gives quiz items, flash cards and wrong predictions up to 6 slots each.
  - **Checks:** 144 tests pass. `tools/browser_check.py m02.lab02.s01` passes on all 9 steps, then Start over and the flash cards.
- **Next first action:** in a fresh session, propose the s02 "The manual loop" outline for Ashish's OK: guide-step titles, one line each, plus its experiment (drop a `tool_result` and see the 400). The source is `docs/PLAN.md`, Module 02 outline, row 1.
  - After his OK, build the s02 content and the features it needs: the Meridian mock API (vendored `meridian_api.py`) as the tools' backend, a per-turn messages view, and a timeline of all calls.
  - **Done when:** `tools/browser_check.py m02.lab02.s02` passes, then `/wrap`. Ashish doing s01 is not a gate.

## Last session
- **Date:** 2026-11-11
- **Done:**
  - **Spaced review:** g1.c2 answered right ("the whole conversation so far plus the new message"), recorded with `labctl`.
  - **Start over**, built as the approved outline: "Start this lesson over" on the lab page and "Start over all lessons" on the home page.
    - It keeps quiz, spend and run history, and the code reset is optional.
    - Routes: `POST /api/steps/{id}/start-over` and `POST /api/start-over`. Migration 5 adds `step_restarts`.
  - **Flash cards:**
    - `Deck` and `FlashCard` in `content/schema.py`, loaded from `content/cards/`;
    - `GET /api/cards`, `POST /api/cards/{deck}/{card}/review`;
    - the `/cards` page (Study and All cards, a tag filter, a tally) and a top-bar link;
    - `labctl content validate` counts the decks.
  - **Fix found by the browser check:** the home page's spaced review showed only its first items, so older quiz misses could push a missed flash card off. Each kind now gets its own slots, plus an "…and N more" line.
  - **Docs:**
    - CLAUDE.md, "How we work": building runs ahead, the learner-tools exception, flash cards.
    - `docs/PLAN.md`: "Learner tools", and the new "Done when".
    - `/wrap` step 2 proposes flash cards, and `/today` includes them in spaced review.
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
  - [ ] s02 Manual loop
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
| 02 The Agent Loop | s01 (guided, with tutor) | s01 started over on 2026-11-11 (step 1 of 9 was done before); tutor tried once | – | after the 17 lessons: 01 ticket triage, 02 vendor screening |
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

- **Estimate against actual:** the tutor was estimated at $7–13 and the whole session cost $4.87. Re-estimate Module 02 after s02 and s03.
- **Where the 2026-11-11 cost went:**
  - 97% of input came from the cache (12.4M tokens read, 323K written), over 79 requests;
  - one cache miss after an idle past the 1-hour TTL re-cached 37.7K tokens, and the context compaction forced one rebuild;
  - `/wrap` was about 6% of usage and `/today` about 4%.

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

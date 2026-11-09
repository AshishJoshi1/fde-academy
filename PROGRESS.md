# FDE Academy: progress

This file is the single source of truth for where the build and the teaching stand. `/wrap` rewrites the "Current position" and "Last session" sections at the end of every session.

## Current position
- **How we work:** the learning lab is built lesson by lesson (`docs/PLAN.md`):
  - **outline first:** guide-step titles approved by Ashish before any build;
  - **one lesson (or build stage) per session;**
  - `tools/browser_check.py <step-id>` passes before a lesson is handed over;
  - every `/wrap` logs the session's `/cost` figure in the "Cost log" below.
- **Teaching:** Module 02, Lab 02, `m02.lab02.s01` "One call", a guided lesson of 9 steps (g1–g9) with experiments E2–E5 and the quiz in g9.
  - **Step 1 done** with one live run. Check g1.c1 right; **g1.c2 still wrong** after a spaced-review retry (he picked "only the new user message"; the API is stateless, so call 2 resends the whole conversation). It comes back in review.
  - g1 now shows call 2's `messages` list as code, because the concept was missed twice with two different answers.
  - He has asked the tutor once, on g6 (E3's hidden tokens). It withheld E3's prediction p3, since his predictions aren't committed, and gave hint 1 grounded in his run (`output=79`).
  - Steps 2–9, the experiments and the quiz are not done yet. The tutor hands-on H1–H3 is not done yet.
- **Building:** s01 is complete: runner and relay, guided steps, experiments, quiz, run history, spaced review, and the tutor.
  - **Tutor:** `src/academy_server/tutor.py`, `POST /api/steps/{id}/tutor/{guide_id}`, the default rules in `tutor_rules.md`, Ashish's copy in `playground/tutor/rules.md`, and migration 4 (tutor threads). The design and measured costs are in `docs/PLAN.md`, "Tutor".
  - **Checks:** 127 tests pass (10 new in `tests/test_tutor.py`). `tools/browser_check.py m02.lab02.s01` passes on all 9 steps, including the tutor on each.
- **Next first action:** Ashish completes s01 in the UI. This is a teaching session; no new features.
  1. Run `python run.py` and open `/lab/m02.lab02.s01`. Do steps 2–9: each step's checks, experiments E2–E5 through to their explanations, then the quiz.
  2. Do the tutor hands-on (`docs/PLAN.md`, build stage 3):
     - **H1:** predict the request layers and where the cache breakpoints sit, then check with "Show request".
     - **H2:** predict the cache write and read for turns 1 and 2, then edit `rules.md` and explain the re-write.
     - **H3:** try to get an open check's answer out of it, and tighten `rules.md` if it gives one.
  3. Fix any content that misled him.
  - **Done when:** all 9 steps show done in the guide nav, H1–H3 are discussed, and the 1-hour cache TTL is confirmed (`ephemeral_1h_input_tokens` > 0 in "Show request" on a first question after the cache has expired).
- **Then:** the s02 "The manual loop" outline (guide-step titles for Ashish's OK), in a fresh session.

## Last session
- **Date:** 2026-11-09 (second session)
- **Done:**
  - **Spaced review:** g1.c2 was asked again and was wrong again (recorded with `labctl`). s01 g1 now shows call 2's `messages` as code.
  - **Tutor (s01 build stage 3), built as the approved outline:**
    - `claude-sonnet-5-5` at effort `low`, called by the server with the Anthropic SDK through the gateway.
    - **Request layers:** the rules (`system[0]`), then the authored lesson (`system[1]`, 1-hour cache), then one thread per guide step. Each question carries a `<lab_context>` block (open checks, current code, trimmed latest run), sent only when it changed, with a 5-minute breakpoint on the newest question.
    - The UI shows the cost, time and cache tokens per answer, plus "Show request" with the exact body.
    - The browser check fakes the tutor with an `httpx2` transport, because SDK 2.6.0 runs on `httpx2`.
  - **Measured live** (throwaway home, $0.033):
    - the lesson prefix is 10.4K tokens;
    - question 1 cost $0.028 with a 5-minute cache write and took 4.2 s;
    - question 2 cost $0.005 (10.4K cache read) and took 2.6 s;
    - effort `low` returned no thinking blocks;
    - it refused to reveal open check answers.
  - **Ashish's first question** (on g6): $0.0084, 5.1 s. It read 9.8K tokens from the cache and wrote 1.5K.
  - **Cost tooling:** `/wrap` now asks for `/cost` and logs it. Module 02 estimate given: about $200–370 for Claude Code plus $30–100 for the gateway, projects included.
  - **Docs:** `docs/PLAN.md` (tutor design, costs, H1–H3); `CLAUDE.md` layout (`tutor.py`); the home page no longer says "the tutor comes next".
- **Open questions:**
  - **1-hour TTL:** does the gateway pass `ttl: "1h"` through? Ashish's first question read the prefix from the measurement's 5-minute cache, so it is still unverified.
  - **Module 02 projects:** set aside. The choice between the Claude Agent SDK and LangGraph for them is undecided and gets discussed after the 17 lessons.
  - **Module 02 outline:** still proposed in `docs/PLAN.md`. Each lesson's steps get approved when that lesson starts.
  - **B1–B5:** the programme README with baseline rules B1–B5, which the Projects specs refer to, isn't on disk.

## Tracked repos
- `.` (fde-academy) → https://github.com/AshishJoshi1/fde-academy

## Build: lesson by lesson (details in `docs/PLAN.md`)
- [x] Foundation: continuity, `run.py`, server shell and security gates, store and migrations, content loader, `labctl`, design system, `tools/run_live.py`
- s01 One call
  - [x] 1. Runner and thin relay, plus the lab page
  - [x] 2. Guided steps, experiments, quiz, run history, spaced review, browser check
  - [x] 3. Tutor (Sonnet 5.5, one thread per guide step, cached lesson prefix, "Show request")
  - [x] s01 content: guided steps g1–g9 with experiments E2–E5 and quiz q1–q3
  - [ ] Ashish completes s01 in the UI
- [ ] Lessons 1–17 of the Module 02 outline (`docs/PLAN.md`, proposed). Lab 02 first:
  - [ ] s02 Manual loop
  - [ ] s03 Parallel tool calls
  - [ ] s04 Gate and block
  - [ ] s05 Tool runner and approval
  - [ ] s06 Strict schema
  - [ ] Lessons 6–17: 02-A to 02-D
- [ ] Module 02 projects: discussed with Ashish after all 17 lessons

## Curriculum progress
| Module | Lessons built | Taught | Quiz score | Project built |
|---|---|---|---|---|
| 02 The Agent Loop | s01 (guided, with tutor) | s01 step 1 of 9; tutor tried once | – | after the 17 lessons: 01 ticket triage, 02 vendor screening |
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

- **Estimate against actual:** the tutor was estimated at $7–13 and the whole session cost $4.87. Re-estimate Module 02 after s02 and s03.
- **Where the 2nd session's cost went:**
  - loading the `/claude-api` skill was about 32% of usage;
  - one cache miss after an idle of over an hour re-cached 26.9K tokens;
  - 97% of input came from the cache.

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

# FDE Academy: progress

This file is the single source of truth for where the build and the teaching stand. `/wrap` rewrites the "Current position" and "Last session" sections at the end of every session.

## Current position
- **How we work:** the learning lab is built lesson by lesson (`docs/PLAN.md`):
  - **outline first:** guide-step titles approved by Ashish before any build;
  - **one lesson (or build stage) per session;**
  - `tools/browser_check.py <step-id>` passes before a lesson is handed over.
- **Teaching:** Module 02, Lab 02, `m02.lab02.s01` "One call", as a guided lesson:
  - **Steps:** 9 guided steps g1–g9. Steps 1–4 teach; steps 5–8 each teach, then hold experiments E2–E5; step 9 is the quiz.
  - **Ashish has started step 1** with one live run (ok, $0.0017).
    - Check g1.c1 (`max_tokens` is the cap) was right.
    - Check g1.c2 was **wrong**: he picked "only the model's last answer", but every call must carry the whole conversation, because the API is stateless. It's recorded and comes back in review.
  - The 3 quiz answers clicked through the first version were deleted at his request. No experiments have been attempted yet.
- **Building:**
  - **s01 stage 1 is done:** runner, thin relay, lab page.
  - **s01 stage 2 is done:**
    - **content and grading:** the `guide:` and `experiments:` schema, facts measured from run events (`schema.FACTS`), and grading;
    - **store:** migration 3 (experiment attempts, predictions, a run id on each code snapshot);
    - **lab page:** the guide on the left with code-line highlights, your run's values and checks; Run, editor, console and model calls on the right; run history and the diff since the previous run; the count-tokens tool; the quiz;
    - **home page:** spaced review and running scores.
  - **Checks:** 117 tests pass. `tools/browser_check.py m02.lab02.s01` passes on all 9 steps.
- **Next first action:** s01 stage 3, the tutor ("Ask the tutor" on every guide step).
  1. Ask Ashish how step 1 felt, and have him go on to step 2 (`python run.py`, then `/lab/m02.lab02.s01`). Fix the content first if anything misled.
  2. Propose the tutor's outline (what it sees, how it answers, the hands-on part for Ashish, since the tutor is itself an LLM app) and get his OK.
  3. Then build it:
     - `POST /api/steps/{id}/tutor` calls `claude-sonnet-5-5` through the gateway;
     - its context is the step's teaching, Ashish's code and the trimmed latest run, with the lesson part as a cached stable prefix;
     - it answers with questions and hints, not answers;
     - turns go in the `tutor_turns` table, and spend is recorded with source `tutor`.
  - **Done when:** Ashish can ask on any step and get an answer grounded in his run; pytest covers the endpoint with a fake gateway; the browser check passes.
- **Then:** Ashish completes s01, then lesson 1 of the Module 02 outline (s02 The manual loop), outline first.

## Last session
- **Date:** 2026-11-09
- **Done:**
  - **s01 stage 2, built twice.** The first version (prediction cards and a quiz first, the lesson text collapsed, Run locked behind predictions) taught nothing. It was rebuilt as guided steps that teach before they ask.
  - **s01 content** was written from 9 live measurement calls (about $0.02):
    - at effort `low` there is no thinking block, and `output_tokens` is the text's tokens plus about 2;
    - effort `high` adds an empty thinking block of about 13 tokens;
    - `max_tokens=20` cuts the answer mid-word (at `high`, the thinking takes most of the cap);
    - `import anthropic` takes 2.3 s;
    - Haiku 4.5 counts the prompt as 17 input tokens, Opus 5.5 as 22;
    - the gateway's cost header equals `pricing.yaml`;
    - the old "13-token puzzle" was a characters-divided-by-4 estimate.
  - **New:** `src/academy_server/experiments.py`, `tools/browser_check.py`, `tests/test_experiments.py`, and `markdown-it-py` for lesson text.
  - **Docs:**
    - `docs/PLAN.md`: the guide format, module projects, the proposed 17-lesson Module 02 outline, and the s01 table;
    - the README intro;
    - `CLAUDE.md`: the outline-first and one-lesson-per-session rules, and the browser check.
  - **Cost estimate for Module 02:** about $140–275 in all.
    - Building: about 7–15 times this session's $16.
    - API calls: $20–55.
    - The outline-first, one-lesson-per-session and browser-check changes aim at the low end.
- **Open questions:**
  - Ashish's verdict on the guided s01, before the tutor is built.
  - The Module 02 outline in `docs/PLAN.md` is proposed. Each lesson's steps get approved when that lesson starts.
  - The programme README with baseline rules B1–B5, which the Projects specs refer to, isn't on disk.

## Tracked repos
- `.` (fde-academy) → https://github.com/AshishJoshi1/fde-academy

## Build: lesson by lesson (details in `docs/PLAN.md`)
- [x] Foundation: continuity, `run.py`, server shell and security gates, store and migrations, content loader, `labctl`, design system, `tools/run_live.py`
- s01 One call
  - [x] 1. Runner and thin relay, plus the lab page
  - [x] 2. Guided steps, experiments, quiz, run history, spaced review, browser check
  - [ ] 3. Tutor
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
| 02 The Agent Loop | s01 (guided; tutor pending) | s01 step 1 of 9 | – | after the 17 lessons: 01 ticket triage, 02 vendor screening |
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

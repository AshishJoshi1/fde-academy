# FDE Academy: progress

This file is the single source of truth for where the build and the teaching stand. `/wrap` rewrites the "Current position" and "Last session" sections at the end of every session.

## Current position
- **Teaching:** not started. The first module is **Module 02, The Agent Loop**, beginning with Lab 02.
- **Building:** Milestone 1, step 0 (continuity setup) is done except the first push. Next is step 1 (the server shell).
- **Next first action:** you run `! git push -u origin main` once (it needs a browser login). Then I start Milestone 1 step 1: `run.py`, the FastAPI shell with the per-launch security token, the SQLite store, and the content loader.

## Last session
- **Date:** 2026-11-06
- **Done:**
  - Planned the product (see `docs/PLAN.md`).
  - Created the repo, CLAUDE.md, this file, the `/today`, `/wrap` and `/quiz` commands, and the SessionStart status hook.
- **Open questions:**
  - The programme README with baseline rules B1–B5, which the Projects specs refer to, isn't on disk. I need it from you, or I'll rebuild it from App 2's summary.
  - Before cassettes can be recorded, `ANTHROPIC_API_KEY` must be set.

## Tracked repos
- `.` (fde-academy) → https://github.com/AshishJoshi1/fde-academy

## Milestone 1: platform + Lab 02 vertical slice
- [x] 0. Continuity: git, CLAUDE.md, PROGRESS.md, commands, hook, memories (the first push is pending)
- [ ] 1. `run.py`, server shell, security token, SQLite and migrations, content loader, `labctl status/export/import`
- [ ] 2. Sandbox subprocess, Job Object, IPC, Console over SSE
- [ ] 3. Relay: pass-through, usage, cost, budget, cassettes, `labctl record/verify`
- [ ] 4. Fixture host (vendored Meridian API, write logging, faults)
- [ ] 5. Web panels: Messages diff, Trace, Token/Cost, loop diagram
- [ ] 6. Stepper: pause points, approvals, `policy.json` toggle, fault arming
- [ ] 6b. Cause → effect: call sites, `sys.monitoring` gutter, Variables, "Why?" chain, flow animation, Compare runs
- [ ] 7. Built-in checks feeding progress
- [ ] 8. Quiz engine (5 types) and the mistakes view
- [ ] 9. Tutor panel
- [ ] 10. Live cost estimate
- [ ] 11. Lab 02 content (6 steps), cassettes recorded, Module 02 Lab quiz

## Curriculum progress
| Module | Lessons built | Taught | Quiz score | Project built |
|---|---|---|---|---|
| 02 The Agent Loop | – | – | – | 01 ticket triage, 02 vendor screening |
| 01 Foundations (A, G, F, E, B; C and D are electives) | – | – | – | – |
| 03 Retrieval | – | – | – | 03 policy RAG |
| 04 Evals & Observability | – | – | – | eval reports, CI gate |
| 05 Reference build | – | – | – | 04 proposal builder, deploy |

## Quiz misses not yet in the database
(Record here until `labctl quiz record` exists: module, question, your answer, correct answer, concept.)

## Decisions log
- 2026-11-06:
  - Teach Agent Loop first.
  - Local app, bring your own key.
  - FastAPI + React + Monaco.
  - Default `claude-opus-5-5`.
  - Replay cassettes by default.
  - Private GitHub backup.
  - Commit and push at `/wrap` without asking.

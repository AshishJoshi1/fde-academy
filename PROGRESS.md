# FDE Academy: progress

This file is the single source of truth for where the build and the teaching stand. `/wrap` rewrites the "Current position" and "Last session" sections at the end of every session.

## Current position
- **Teaching:** not started. The first module is **Module 02, The Agent Loop**, beginning with Lab 02 (`m02.lab02.s01` is written).
- **Building:** Milestone 1 steps 0–1 are done (26 tests pass; the real server was smoke-tested through `run.py`).
  - The request in progress, interrupted by `/wrap`: **Anthropic-style CSS for every UI page**. It comes before step 2.
- **Next first action:** build the design system. **Done when** pytest passes and screenshots of `/`, `/design` and the unauthorized page look right in light and dark mode.
  1. **Data palette:** validate the warm data palette with the dataviz validator: `node <dataviz skill>/scripts/validate_palette.js "<hexes>" --mode light --surface "#FAF9F5"`, then `--mode dark --surface "#262624"`.
     - Candidates: sky `#6A9BCC`, clay `#D97757`, olive `#788C5D`, plus dark steps.
     - Use them for the token meter's segments (system+tools / retrieved / history) and the trace's LLM-call / tool_use marks.
     - Headroom is a neutral track. ok / is_error / blocked use the status colors (good / critical / warning), always with an icon and label.
  2. **Stylesheet:** write `web/src/styles/academy.css`. This one file serves both the server pages now and the React app in step 5.
     - Tokens: ivory `#FAF9F5`, oat `#F0EEE6`, hairline `#E8E6DC`, slate text `#141413`, secondary text `#5E5D59`, clay accent `#D97757`, link/accent text `#B05730` (4.7:1 on ivory).
     - Type: system serif headings (Georgia / Palatino), system sans UI and numbers, mono for code.
     - Dark mode through `prefers-color-scheme` and `[data-theme]`.
     - No Anthropic logo or proprietary fonts.
  3. **Wiring:**
     - Serve the stylesheet at `/static/academy.css`, an open path since CSS isn't sensitive.
     - Restyle the home placeholder.
     - Return a styled HTML 401 page for browser navigation (the API keeps JSON).
     - Add `/auth?next=` with a safe relative-path check.
     - Add a `/design` style-guide page: palette, type, buttons, pills, tabs, code, a workbench mockup (code left, outcome tabs right), trace timeline, messages diff, token meter, the "Why?" chain and a quiz card.
  4. **Check visually:** take screenshots with headless Edge (`msedge --headless=new --screenshot`).
- **Then:** Milestone 1 step 2. Create `src/academy_server/runs/{sandbox,winjob,ipc,manager,events}.py` and `src/labkit/run.py`.
  - The subprocess is launched with `Popen([venv_py, "-X", "utf8", "-u", "-m", "labkit.run", "main.py"])`, with an allowlisted environment, a Job Object and a 120 s limit.
  - IPC is loopback TCP with a per-run token. Console output streams over SSE at `GET /api/runs/{id}/events`.
  - **Done when** pytest proves: a timeout kills the whole process tree, a wrong IPC token is rejected, stdout arrives in order, and there's no real `ANTHROPIC_API_KEY` in the subprocess environment.

## Last session
- **Date:** 2026-11-06 (first session)
- **Done:**
  - Planned the product (`docs/PLAN.md`).
  - Created the repo, CLAUDE.md, this file, the `/today`, `/wrap` and `/quiz` commands, and the SessionStart status hook. First push to GitHub done.
  - Milestone 1 step 1:
    - `run.py` bootstrap.
    - FastAPI app with 3 security gates (Host allowlist, Origin check, per-launch token → SameSite=Strict cookie).
    - SQLite store: WAL, migrations, autosaved drafts, "what I got wrong" queries, export/import.
    - Strict pydantic lesson schema and loader.
    - `labctl`.
    - First lesson step `m02.lab02.s01` "One call".
  - The SDK is `anthropic` 2.6.0: Bearer auth, `anthropic-version` 2026-10-21, and no `temperature` in `create()`.
  - Started `/doctor`, paused before any change. Findings so far:
    - The native install (2.1.318) is healthy.
    - Background auto-updates are off (`autoUpdates: false`), and the latest-version lookup wasn't run.
    - The 12 skills synced from claude.ai have never been used and cost about 1.76k est. tokens per session.
    - About 45 claude.ai connectors are unauthenticated and unused.
    - No slow hooks, and no denials that justify allow rules.
    - /usage flagged subagent cost: 5 Explore/Plan spawns inherited Opus.
    - Re-run `/doctor` to finish and apply.
- **Open questions:**
  - The programme README with baseline rules B1–B5, which the Projects specs refer to, isn't on disk. I need it from you, or I'll rebuild it from App 2's summary.
  - Before cassettes can be recorded, `ANTHROPIC_API_KEY` must be set.

## Tracked repos
- `.` (fde-academy) → https://github.com/AshishJoshi1/fde-academy

## Milestone 1: platform + Lab 02 vertical slice
- [x] 0. Continuity: git, CLAUDE.md, PROGRESS.md, commands, hook, memories, first push
- [x] 1. `run.py`, server shell, security token, SQLite and migrations, content loader, `labctl status/export/import`
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
  - UI look: Anthropic-inspired warm-neutral design system (ivory/oat/slate, clay accent, serif headings), one stylesheet shared by the server pages and the React app; data colors validated with the dataviz validator.

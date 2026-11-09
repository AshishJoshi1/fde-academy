# FDE Academy

A local lab for learning GenAI and agent engineering in depth: agent loops, tools, guardrails, retrieval, evals, observability and deployment, with Python, the Anthropic SDK and LangGraph. It's built for one learner.

Every lesson is a guided walkthrough in the browser. Each step teaches one idea, highlights the code it's about, has you run or change that code live against Claude, shows what your own run measured, and checks your understanding. Once an idea is taught, experiments test it: predict, change one thing, run, compare, explain the gap.

Each lesson ends with a quiz, and missed items come back in spaced review. Each module ends with a project built step by step in the same format, connecting what the lessons taught. A Claude tutor on every step answers your "why?" with questions and hints.

> Status: built lesson by lesson. See [docs/PLAN.md](docs/PLAN.md) and [PROGRESS.md](PROGRESS.md).

## Run
- **The app:** `python run.py`. It sets up `.venv`, starts the server on 127.0.0.1 and opens the browser.
- **A lesson step from the command line:** `.venv/Scripts/python -X utf8 tools/run_live.py m02.lab02.s01`. Your code is in `playground/<step-id>/`.
- **Gateway:** live calls go through the gateway configured in `%LOCALAPPDATA%\fde-academy\anthropic.env` (see CLAUDE.md, "Gateway").
- **Tests:** `.venv/Scripts/python -X utf8 -m pytest`.

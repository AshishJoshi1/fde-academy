# FDE Academy

A local lab for learning GenAI and agent engineering in depth: agent loops, tools, guardrails, retrieval, evals, observability and deployment, with Python, the Anthropic SDK and LangGraph. It's built for one learner.

Every lesson is a set of experiments. For each one you:
1. predict what will happen;
2. change one thing in real code;
3. run it live against Claude;
4. compare the result with your prediction;
5. explain the gap.

A Claude tutor guides you with questions and hints. Each lesson ends with a quiz, and missed items come back in spaced review.

> Status: built lesson by lesson. See [docs/PLAN.md](docs/PLAN.md) and [PROGRESS.md](PROGRESS.md).

## Run
- **The app:** `python run.py`. It sets up `.venv`, starts the server on 127.0.0.1 and opens the browser.
- **A lesson step from the command line:** `.venv/Scripts/python -X utf8 tools/run_live.py m02.lab02.s01`. Your code is in `playground/<step-id>/`.
- **Gateway:** live calls go through the gateway configured in `%LOCALAPPDATA%\fde-academy\anthropic.env` (see CLAUDE.md, "Gateway").
- **Tests:** `.venv/Scripts/python -X utf8 -m pytest`.

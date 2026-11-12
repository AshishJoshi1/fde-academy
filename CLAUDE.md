# FDE Academy: instructions for Claude

FDE Academy is a local lab app, for Ashish only, that teaches GenAI and agent engineering in depth with Python, the Anthropic SDK and LangGraph. Every lesson is a set of experiments (predict, change one thing, run live, compare, explain) that ends in a quiz, with a Claude tutor that guides through questions and hints.

- Full design: `docs/PLAN.md`. Build state and the exact stopping point: `PROGRESS.md`.
- Remote: https://github.com/AshishJoshi1/fde-academy (private), branch `main`.
- **How we work:** the app is built lesson by lesson (`docs/PLAN.md`, "How a lesson is made").
  - Each lesson is its content plus the app features it needs. No feature without a lesson that needs it, except learner tools Ashish asks for (Start over, flash cards).
  - **Building runs ahead of learning:** the next lesson's build doesn't wait for Ashish to finish the previous one. He does the lessons in the UI at his own pace; a step that misleads him gets fixed when he reaches it.
  - **Outline first:** before building a lesson, propose its guide-step titles (one line each, plus any experiment) and get Ashish's OK. No content or features before that.
  - **One lesson per session:** a session builds one lesson (or one build stage), then ends with `/wrap`. The next lesson starts in a fresh session, because every turn resends the whole conversation.
  - Lessons teach before they ask: guided steps (teach, highlight the code, do, your run, check), then experiments (`docs/PLAN.md`, "The experience").
  - Teach while building: explain the code, and give Ashish a hands-on part where a feature is course material (the relay, the tutor).
  - Live calls only: no cassettes, replay or recording.
  - Simple features first: server-rendered pages and vanilla JavaScript.
  - Until a lesson's UI exists, Ashish runs its code with `tools/run_live.py`.
  - **Flash cards:** `content/cards/build.yaml` holds what building the lab taught, each fact with its source (`/cards` in the app). `/wrap` proposes 1–3 new cards from the session; only the ones Ashish approves are added.

## Session protocol (do this every session)
- **Start:** run `/today`, or at minimum read `PROGRESS.md` and run `python -X utf8 tools/session_status.py`. Continue from "Next first action". Never start new work before checking for unwrapped changes.
- **End:** run `/wrap`. It rewrites PROGRESS.md (exact stopping point and the next first action), exports learner progress, and commits and pushes every dirty tracked repo.
  - **Standing permission:** commit and push at `/wrap` without asking.
  - Commits at other times still need the user's OK.
- **End of each module:** run `/quiz <module>` on the whole module, then list every wrong answer. Record every answer with `labctl quiz record`.
- Teaching style: explain the *why*, show the trace and the code line that caused each outcome, and quiz before moving on. The learner wants hands-on, interactive learning.

## Repo conventions
- Python 3.14 (fallback `py -3.13`). Always run Python with `-X utf8`; under cp1252 the Meridian seed data ("Łódź") crashes.
- Layout:
  - `src/academy_server` is the FastAPI server: content loader, store, security and server-rendered pages, plus:
    - `runs/`: `proctree.py` (Job Object process tree) and `manager.py` (the run lifecycle and its ordered events);
    - `relay.py` (the thin relay to the gateway);
    - `fixtures/`: the mock Meridian API (`meridian/meridian_api.py` and its seed, vendored unchanged from Projects/04), started for each run of a step with `run: {fixture: meridian}`; `/meridian` shows its data, so lessons can refer to its IDs;
    - `tutor.py` (the tutor's request layers; its default rules are `tutor_rules.md`, and Ashish's copy is `playground/tutor/rules.md`);
    - `pricing.py`, `credentials.py` and `playground.py`.
  - `web/` has only `src/styles/academy.css`, the design system; `/design` is its reference page. A React and Monaco workbench may come later, only if a lesson needs it.
  - `src/labkit` (empty) is for in-process hooks, added when a lesson needs them (s05 approvals).
  - `content/` holds the lessons, the flash-card decks in `content/cards/`, and the glossary of commands (`content/glossary.yaml`, shown at `/glossary`; a test checks every slash command, `labctl` subcommand and tool has an entry).
  - `tools/` holds `labctl`, `session_status.py` and `run_live.py`.
  - `playground/<step-id>/` (tracked in git) holds Ashish's code for each step. He edits it in the lab page's simple editor or in VS Code. A save from the page refuses to overwrite a file changed on disk (409) unless he confirms.
- Run the app with `python run.py`. Run tests with `.venv/Scripts/python -X utf8 -m pytest`, and validate lessons with `.venv/Scripts/python -X utf8 tools/labctl.py content validate`.
- Run a lesson step from the browser: `python run.py`, then open `/lab/<step-id>`. It shows the console and every model call's exact request and response.
- Browser-check a lesson: `.venv/Scripts/python -X utf8 tools/browser_check.py <step-id>`. It walks every guide step in headless Edge (Run, checks, experiments, quiz), then Start over and the flash cards, against a fake gateway, with its own temporary data and playground: no API spend, and your progress is untouched. It reports JavaScript errors and saves a screenshot per step. Run it before handing a lesson to Ashish.
- Run a lesson step from the command line: `.venv/Scripts/python -X utf8 tools/run_live.py <step-id>` (`--reset`, `--model`).
  - The first run copies the starter into `playground/`, and later runs never overwrite edits.
  - Prefix `ANTHROPIC_LOG=debug` to log each request body and retry decision. It never logs the key.
  - Ashish's `!` commands run in bash, so give bash syntax, not PowerShell.
- `academy_server/__init__.py`, `paths.py`, `store/` and `labctl.py` must stay **stdlib-only**, because the SessionStart hook and `/today` run them with a bare system Python.
- `.gitattributes` forces LF line endings (py, json, yaml, md, ts, js, css, html, toml), so files are byte-identical on every machine.
- Never commit secrets. The real API key lives only in `%LOCALAPPDATA%\fde-academy\anthropic.env`, never in the repo, memory or logs.
  - `tools/run_live.py` hands it to the lesson process only.
  - UI runs go through the relay, which keeps the key and gives lesson code a dummy one.
- Prices come from `pricing.yaml`. Never hard-code dollars in code; store usage.

## Claude API rules (current as of 2026-11)
- Default model `claude-opus-5-5` through `os.getenv("LAB_MODEL", "claude-opus-5-5")`.
  - Switchable to `claude-sonnet-5-5`. For Haiku, use `claude-haiku-4-5`: the gateway key has no `claude-haiku-5-5`.
  - **Haiku 4.5 is the previous generation:**
    - it rejects `output_config.effort` with a 400;
    - it thinks only with `thinking: {type: "enabled", budget_tokens: N}` (at least 1024, and less than `max_tokens`), and not at all if `thinking` is omitted;
    - 200K context, 64K max output, a 4,096-token minimum for prompt caching.
    - Lesson code that sets `effort` must run on Opus 5.5 or Sonnet 5.5.
  - **Sonnet 5.5** differs from Opus 5.5:
    - effort defaults to `high`, not `medium`;
    - thinking can be turned off with `thinking: {type: "between_tools"}` (effort `high` or below); `disabled` returns a 400.
  - `temperature`, `top_p` and `top_k` return a 400 on every model with the SDK's API version `2026-10-21`.
  - No date suffixes.
- **On Opus 5.5:**
  - Thinking can't be disabled. Set `output_config: {"effort": ...}` explicitly; the default is `medium`.
  - The model still decides how much to think. At `low` effort on an easy prompt it may return only a `text` block, with no `thinking` block. Never assume block positions; filter by `block.type`.
  - `budget_tokens` and `temperature`/`top_p`/`top_k` return 400.
  - Forced `tool_choice` (`any`/`tool`) returns 400; use `auto` plus `strict: true`.
  - No assistant prefill.
- **Agent loops:**
  - Append the whole `response.content`.
  - Put every `tool_result` in ONE user message, and use `is_error: true` instead of dropping a result.
  - History only grows. Opus 5.5 binds thinking blocks to the conversation, so never edit earlier turns.
  - Check `stop_reason` (`tool_use`, `end_turn`, `max_tokens`, `refusal`, `pause_turn`) before reading content.
- Token counting: `client.messages.count_tokens`, never tiktoken.
- Usage fields: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`.
- Tool runner: `@beta_tool` + `client.beta.messages.tool_runner(...)`. Approval gates go inside the tool, or in the `for message in runner:` body with `runner.set_messages_params()`.
- Projects in `C:\Users\AshishKumarJoshi\FDE\Projects` mandate the **Claude Agent SDK** (a separate product). Read code.claude.com/docs/en/agent-sdk before writing that code; never guess its API.

## Gateway (every live call goes through it)
- **Where:** the Bounteous LiteLLM proxy at `https://gateway.bounteous.tools`, not api.anthropic.com.
- **Credentials:** `%LOCALAPPDATA%\fde-academy\anthropic.env` holds `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY`.
  - Never set these as user-wide environment variables: Claude Code reads the same names and would switch its own login.
- **Models:** `client.models.list()` is the source of truth.
  - This key has `claude-opus-5-5`, `claude-sonnet-5-5` and `claude-haiku-4-5`. For Module 03 it also has `text-embedding-3-small` and `text-embedding-3-large`.
  - It has no `claude-haiku-5-5`, which returns 401 "key not allowed to access model".
- **Tracing:** no Anthropic `request-id` header comes back (the SDK logs `request_id: None`). Use the `x-litellm-call-id` response header.
- **Errors:** the gateway wraps Anthropic's error JSON (including its `request_id`) as a string inside its own envelope, `{"error": {"message": ..., "code": "400"}}`. The SDK still raises the right exception class, because it maps the HTTP status, not the body.
- **Limits per key** (in the response headers): a $50 budget (`x-litellm-key-max-budget`, with spend so far in `x-litellm-key-spend`), 60 requests per minute and 100,000 tokens per minute. Going over returns 429, which the SDK retries.
- **Cost:** `x-litellm-response-cost-original` is the gateway's cost for the call, and it matches `pricing.yaml`.
- **Passes through unchanged:** `output_config`, `count_tokens` and all four usage fields. No truststore needed.

## Related folders
- `C:\Users\AshishKumarJoshi\FDE\Projects\0{1..4}-*`: capstone specs. 04 ships `mock_api/meridian_api.py`, vendored unchanged in `src/academy_server/fixtures/meridian/` (a test checks the copy matches).
- Each project becomes its own git repo when its build starts. List it under "Tracked repos" in PROGRESS.md so `/wrap` commits it.

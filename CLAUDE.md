# FDE Academy: instructions for Claude

FDE Academy is an interactive, local web app that teaches GenAI and agent engineering with Python, the Anthropic SDK and LangGraph. Lesson code sits on the left and the live outcome on the right: trace, messages, tokens/cost, flow, and "Why?" cause-and-effect. A Claude tutor guides the learner. It is also the learner's (Ashish's) own course, taught module by module.

- Full design: `docs/PLAN.md`. Build state and the exact stopping point: `PROGRESS.md`.
- Remote: https://github.com/AshishJoshi1/fde-academy (private), branch `main`.

## Session protocol (do this every session)
- **Start:** run `/today`, or at minimum read `PROGRESS.md` and run `python -X utf8 tools/session_status.py`. Continue from "Next first action". Never start new work before checking for unwrapped changes.
- **End:** run `/wrap`. It rewrites PROGRESS.md (exact stopping point and the next first action), exports learner progress, and commits and pushes every dirty tracked repo.
  - **Standing permission:** commit and push at `/wrap` without asking.
  - Commits at other times still need the user's OK.
- **End of each module:** run `/quiz <module>` on the whole module, then list every wrong answer. Record answers with `labctl quiz record` once labctl exists; until then, record them in PROGRESS.md.
- Teaching style: explain the *why*, show the trace and the code line that caused each outcome, and quiz before moving on. The learner wants hands-on, interactive learning.

## Repo conventions
- Python 3.14 (fallback `py -3.13`). Always run Python with `-X utf8`; under cp1252 the Meridian seed data ("Łódź") crashes.
- Layout:
  - `src/academy_server` is the FastAPI server: relay, sandbox, fixtures, content, store.
  - `src/labkit` runs inside the subprocess.
  - `web/` is the React + Vite + TS + Monaco frontend.
  - `content/` holds the lessons.
  - `tools/` holds `labctl` and `session_status.py`.
- Run the app with `python run.py`. Run tests with `.venv/Scripts/python -X utf8 -m pytest`, and validate lessons with `.venv/Scripts/python -X utf8 tools/labctl.py content validate`.
- `academy_server/__init__.py`, `paths.py`, `store/` and `labctl.py` must stay **stdlib-only**, because the SessionStart hook and `/today` run them with a bare system Python.
- `.gitattributes` forces LF line endings. Cassette keys hash request bodies, so CRLF would break them.
- Never commit secrets. The real API key lives only in the server process; lesson subprocesses get a dummy key and `ANTHROPIC_BASE_URL` pointing at the relay.
- Prices come from `pricing.yaml`. Never hard-code dollars in code or cassettes; store usage.

## Claude API rules (current as of 2026-11)
- Default model `claude-opus-5-5` through `os.getenv("LAB_MODEL", "claude-opus-5-5")`. Switchable to `claude-sonnet-5-5` or `claude-haiku-5-5`. No date suffixes.
- **On Opus 5.5:**
  - Thinking can't be disabled. Set `output_config: {"effort": ...}` explicitly; the default is `medium`.
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

## Related folders
- `C:\Users\AshishKumarJoshi\FDE\Projects\0{1..4}-*`: capstone specs. 04 ships `mock_api/meridian_api.py`, which is vendored as the lesson fixture.
- Each project becomes its own git repo when its build starts. List it under "Tracked repos" in PROGRESS.md so `/wrap` commits it.

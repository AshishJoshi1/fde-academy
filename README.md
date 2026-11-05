# FDE Academy

An interactive, Claude-guided course on building GenAI systems: agent loops, tools, guardrails, retrieval, evals, observability and deployment. It uses Python, the Anthropic SDK and LangGraph.

Each lesson puts your editable code on the left and the live outcome on the right:
- the trace;
- the actual `messages` array, growing turn by turn;
- tokens and cost;
- the flow of data;
- a **"Why?"** chain that links every outcome back to the exact line of code, value and setting that caused it.

For example, block a tool, watch the model get an `is_error` result and adapt, and confirm from the API log that the write never happened.

> Status: under construction. See [PROGRESS.md](PROGRESS.md) and [docs/PLAN.md](docs/PLAN.md).

## Quick start (when Milestone 1 lands)
```
python run.py
```
- It runs locally and you bring your own `ANTHROPIC_API_KEY`.
- Every lesson also works offline and free, from recorded cassettes.
- Live runs show a cost estimate before sending.

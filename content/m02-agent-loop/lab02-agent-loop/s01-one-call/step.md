# One call: what actually comes back

Before building a loop, look closely at a single request and response. Every later step is built from this shape.

**The request** has four parts:
- `model`
- `max_tokens`, the hard cap on what the model may *generate*
- `output_config.effort`, which controls how hard it thinks
- `messages`, the conversation so far

**The response** is not a string. It has three parts:

| Field | What it tells you |
|---|---|
| `content` | A **list of blocks**. On `claude-opus-5-5`, thinking is always on, so you may see `thinking` blocks (empty text by default) before the `text` block. |
| `stop_reason` | **Why** it stopped: `end_turn` (finished), `tool_use` (wants a tool), `max_tokens` (cut off), `refusal`, or `pause_turn`. |
| `usage` | What you pay for: `input_tokens`, `output_tokens` (thinking included), `cache_creation_input_tokens`, `cache_read_input_tokens`. |

## Do this
1. Click **Run** (replay, free). In the **Messages** panel, open the response and count its blocks.
2. In **Tokens**, compare `output_tokens` with the length of the text you got. Where did the extra tokens go?
3. Change `effort` from `"low"` to `"medium"` and click **Run live ($ estimate)**. Did the output tokens and the cost change?

## Why it matters
An agent loop is just this call repeated, with `stop_reason` deciding what happens next. If you read `content[0].text`, the first thinking block will break your code. If you ignore `max_tokens`, half-finished answers get through looking complete.

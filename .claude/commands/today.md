---
description: Start the day. Restore context, do a spaced review of past misses, and continue from the recorded next action.
---
Start today's FDE Academy session. Follow these steps in order and keep the output short.

1. **Restore context.**
   - The SessionStart hook already printed the session status: don't run `tools/session_status.py` again.
   - Read only the top of `PROGRESS.md` (Current position and Last session; `grep -n '^## '` for the line numbers, then `offset` and `limit`). The decisions log and cost analysis are in `docs/DECISIONS.md`: don't read them unless needed.
   - If `tools/labctl.py` exists, run `python -X utf8 tools/labctl.py status`.
2. **Unwrapped work check.** If any tracked repo has uncommitted changes, or commits that aren't pushed, from a previous day:
   - Say so.
   - Offer to run the `/wrap` steps for that work first, with a commit dated to describe that work.
   - Don't silently mix it into today's work.
3. **Spaced review.** Take up to 3 still-wrong quiz items: from `labctl` once it exists, otherwise from the "Quiz misses not yet in the database" section of PROGRESS.md.
   - Re-ask each one with AskUserQuestion, or as a short open question for trace-reading and code items.
   - Tell me right or wrong, give the one-line why, and record the result in the same place it came from.
   - Flash cards (item ids `cards:<deck>:<card>`) count too: ask the card's question, and record with `labctl quiz record --module cards --item <item id> --type flashcard`.
   - Skip this step if there are no misses.
4. **Today's goal.** State in 1–2 lines where we are (module/chapter/step or build step) and today's goal, taken from "Next first action".
5. **Continue.** Start that next action straight away, either teaching or building, unless I redirect.

$ARGUMENTS

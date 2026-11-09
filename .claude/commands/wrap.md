---
description: End the day. Save the exact stopping point, export learner progress, then commit and push every tracked repo.
---
Wrap up today's FDE Academy session. Standing permission: commit and push without asking.

1. **Rewrite PROGRESS.md.**
   - **Current position:** teaching position (module/chapter/step) and build position (milestone step).
   - **Next first action:** one concrete, resumable instruction. Name the file or step, plus what "done" looks like.
   - **Last session:** date (today), what was done, and open questions or blockers.
   - Tick the milestone checklist and update the curriculum table.
   - Move any quiz misses from this session into the misses section, unless `labctl quiz record` already stored them.
   - Add today's decisions to the decisions log.
   - **Cost log:** ask me for this session's `/cost` figure (you can't read it yourself) and add a row to the "Cost log" table: date, what was built or taught, Claude Code $, and gateway $ from `labctl status`. If I don't give it, write "not given"; never guess.
2. **Export learner state.** If `tools/labctl.py` exists, run `python -X utf8 tools/labctl.py export --to progress/learner-progress.json`.
3. **Commit and push each tracked repo** listed under "Tracked repos" in PROGRESS.md:
   - Run `git status`, then stage the changes.
   - Never stage `.env`, keys or `*.db`. Check `git diff --cached --name-only` before committing.
   - Commit with a message that summarizes the day (`wrap: <date> - <summary>`), ending with the attribution trailer.
   - Then `git push`.
   - If the push fails for an auth reason, tell me to run `! git push` myself. Don't retry in a loop.
4. **Recap.** Print exactly 3 lines: what got done, where we stopped, and the next first action.

$ARGUMENTS

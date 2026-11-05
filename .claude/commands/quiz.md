---
description: End-of-module quiz on the whole module. Grades the answers, lists every miss and records them. Usage: /quiz <module id, e.g. m02>
argument-hint: <module>
---
Run the end-of-module quiz for module: $ARGUMENTS

1. **Cover the whole module**, every chapter taught so far, not just the last lesson.
   - If the module has a quiz bank under `content/<module>/**/quiz/`, draw from it. Otherwise write the questions from the syllabus in `docs/PLAN.md` and the lessons taught.
   - Ask 10–15 questions, mixing these types:
     - multiple choice (use AskUserQuestion, up to 4 per call);
     - "read this trace or snippet and say why the answer was wrong";
     - "estimate the cost of this request" (numeric, using `pricing.yaml` rates);
     - "fix this tool schema or loop bug";
     - one "draw it": describe the agent loop and where it hangs.
   - At least 3 questions must map to the target outcomes in `docs/PLAN.md`.
2. **Ask questions in small batches**, then grade them. For free-text answers, grade against an explicit rubric and show the rubric.
3. **Report:**
   - The score.
   - A table of **every question I got wrong**: question, my answer, correct answer, concept, and the lesson to revisit.
   - Then 2–3 sentences on the pattern behind the misses.
4. **Record.** Use `python -X utf8 tools/labctl.py quiz record ...` if labctl exists. Otherwise append the misses to the "Quiz misses not yet in the database" section of PROGRESS.md and update the module's quiz score in the curriculum table.

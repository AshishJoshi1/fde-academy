"""labctl: command-line access to learner state. Used by /today, /wrap, /quiz and the SessionStart hook.

Standard library only, except `content validate` (needs the venv), so it runs under a bare
system Python too:  python -X utf8 tools/labctl.py status --brief

  status [--brief|--json]          where you are, quiz misses, spend
  mistakes [--module m02] [--json] what I got wrong (still wrong / fixed after retry / failing checks)
  export [--to PATH]               write learner state to JSON (default progress/learner-progress.json)
  import --from PATH [--yes]       replace learner state from an export
  quiz record ...                  record a quiz answer given in chat (see `quiz record -h`)
  content validate                 load content/ and list errors (venv only)
  open                             re-open the running app in the browser
  where                            print data paths
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import webbrowser
from pathlib import Path

from . import paths
from .store import Store


def _store() -> Store:
    return Store(paths.db_path())


def cmd_status(args) -> int:
    if not paths.db_path().exists():
        print("Learner DB: not created yet. Start the app once (python run.py).")
        return 0
    st = _store().status()
    if args.json:
        print(json.dumps(st, indent=2))
        return 0
    pos = st["position"]
    where = f"{pos['step_id']} ({pos['filename'] or '-'})" if pos else "not started"
    mods = ", ".join(f"{m}: {c.get('completed', 0)} done/{sum(c.values())} opened"
                     for m, c in sorted(st["modules"].items())) or "none opened"
    q = st["quiz"]
    concepts = ", ".join(list(_store().mistakes()["by_concept"])[:5])
    lines = [
        f"Learner position: {where}",
        f"Steps: {mods}",
        f"Quiz: {q['attempts']} attempts, {q['still_wrong']} still wrong"
        + (f" (concepts: {concepts})" if concepts else "") + f", {q['fixed_after_retry']} fixed after retry",
        f"Spend: today ${st['spend']['today_usd']:.4f}, total ${st['spend']['total_usd']:.4f}",
    ]
    pr = st.get("predictions")
    if pr and pr["graded"]:
        lines.insert(3, f"Predictions: {pr['right']}/{pr['graded']} right, {pr['explained']}/{pr['surprises']} "
                        f"surprises explained, {pr['cards_done']} card(s) done")
    if not args.brief:
        lines += [f"Failing checks (latest run per step): {st['failing_checks']}", f"DB: {st['db']}"]
    print("\n".join(lines))
    return 0


def cmd_mistakes(args) -> int:
    m = _store().mistakes(args.module)
    if args.json:
        print(json.dumps(m, indent=2))
        return 0
    def show(title, rows):
        print(f"\n{title} ({len(rows)})")
        for r in rows:
            print(f"  - [{r['module_id']}] {r['item_id']}: {r['question'] or ''}".rstrip())
            print(f"      you: {r['answer']!r}   correct: {r['correct']!r}   concepts: {r['concepts']}"
                  f"   misses: {r['misses']}/{r['tries']}")
    show("Still wrong", m["still_wrong"])
    show("Fixed after retry", m["fixed_after_retry"])
    print(f"\nFailing checks ({len(m['failing_checks'])})")
    for f in m["failing_checks"]:
        print(f"  - {f['step_id']}: {f['check_id']}: {f['message'] or ''}")
    if m["by_concept"]:
        print("\nBy concept: " + ", ".join(f"{k} x{v}" for k, v in m["by_concept"].items()))
    return 0


def cmd_export(args) -> int:
    dest = Path(args.to) if args.to else paths.default_export_path()
    if not paths.db_path().exists():
        print("nothing to export: learner DB not created yet")
        return 0
    data = _store().export_all()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8",
                   newline="\n")
    tmp.replace(dest)  # atomic: a crash never leaves a half-written export
    counts = {t: len(rows) for t, rows in data["tables"].items() if rows}
    print(f"exported to {dest}: {counts or 'empty'}")
    return 0


def cmd_import(args) -> int:
    src = Path(args.src)
    data = json.loads(src.read_text(encoding="utf-8"))
    store = _store()
    if not store.is_empty() and not args.yes:
        print(f"refusing: {paths.db_path()} already has learner data. Re-run with --yes to REPLACE it "
              "(export it first if unsure).", file=sys.stderr)
        return 2
    counts = store.import_all(data)
    print(f"imported from {src}: {({t: n for t, n in counts.items() if n}) or 'empty'}")
    return 0


def cmd_quiz_record(args) -> int:
    # Stable across processes (built-in hash() is randomized per run), so re-asking the same
    # question later counts as a retry of the same item.
    digest = hashlib.sha1(" ".join(args.question.lower().split()).encode()).hexdigest()[:10]
    item = args.item or f"chat:{args.module}:{digest}"
    rid = _store().record_quiz_attempt(
        item_id=item, module_id=args.module, type=args.type, answer=args.answer,
        correct=args.right, question=args.question, correct_answer=args.correct_answer,
        concepts=args.concept, graded_by=args.graded_by, feedback=args.feedback, source=args.source)
    print(f"recorded attempt #{rid} for {item}: {'right' if args.right else 'WRONG'}")
    return 0


def cmd_content_validate(args) -> int:
    try:
        from .content.loader import load_content
    except ImportError:
        print("content validate needs the venv: .venv\\Scripts\\python -X utf8 tools/labctl.py content validate",
              file=sys.stderr)
        return 2
    tree = load_content(paths.content_dir())
    cards = sum(len(d.cards) for d in tree.decks.values())
    terms = sum(len(sec.entries) for sec in tree.glossary.sections) if tree.glossary else 0
    print(f"{len(tree.modules)} module(s), {len(tree.steps)} step(s), {len(tree.decks)} deck(s) of flash cards "
          f"({cards} cards), glossary: {terms} entries")
    for e in tree.errors:
        print(f"  ERROR {e}")
    return 1 if tree.errors else 0


def cmd_open(args) -> int:
    info = paths.server_info_path()
    if not info.exists():
        print("the app isn't running. Start it with: python run.py")
        return 1
    url = json.loads(info.read_text(encoding="utf-8"))["url"]
    webbrowser.open(url)
    print(f"opened {url.split('?')[0]}")
    return 0


def cmd_where(args) -> int:
    print(f"repo:    {paths.repo_root()}\ndata:    {paths.data_dir()}\ndb:      {paths.db_path()}\n"
          f"export:  {paths.default_export_path()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="labctl", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status"); p.add_argument("--brief", action="store_true"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("mistakes"); p.add_argument("--module"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_mistakes)
    p = sub.add_parser("export"); p.add_argument("--to"); p.set_defaults(fn=cmd_export)
    p = sub.add_parser("import"); p.add_argument("--from", dest="src", required=True)
    p.add_argument("--yes", action="store_true", help="replace existing learner data"); p.set_defaults(fn=cmd_import)

    quiz = sub.add_parser("quiz").add_subparsers(dest="quiz_cmd", required=True)
    p = quiz.add_parser("record", help="record a quiz answer (e.g. from /quiz in chat)")
    p.add_argument("--module", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--answer", required=True, help="what the learner answered")
    p.add_argument("--correct-answer", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--right", action="store_true"); g.add_argument("--wrong", dest="right", action="store_false")
    p.add_argument("--concept", action="append", default=[])
    p.add_argument("--item", help="stable item id; re-asking the same item tracks fixed-after-retry")
    p.add_argument("--type", default="open")
    p.add_argument("--feedback")
    p.add_argument("--graded-by", default="claude-chat")
    p.add_argument("--source", default="chat")
    p.set_defaults(fn=cmd_quiz_record)

    content = sub.add_parser("content").add_subparsers(dest="content_cmd", required=True)
    content.add_parser("validate").set_defaults(fn=cmd_content_validate)
    sub.add_parser("open").set_defaults(fn=cmd_open)
    sub.add_parser("where").set_defaults(fn=cmd_where)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

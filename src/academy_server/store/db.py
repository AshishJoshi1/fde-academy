"""SQLite learner-state store. Standard library only.

One connection shared across FastAPI's worker threads, serialized by a lock.
That's fine for a single-user local app. WAL mode means a crash mid-write
loses at most the in-flight transaction, never the database.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Iterable

from .migrations import MIGRATIONS

EXPORT_FORMAT = "fde-academy-progress"
# Insert order respects foreign keys (runs before check_results); delete in reverse.
EXPORT_TABLES = [
    "step_progress", "code_snapshots", "runs", "run_events", "check_results",
    "quiz_attempts", "spend", "tutor_turns", "position",
]
_ORDER_BY = {
    "step_progress": "step_id", "code_snapshots": "id", "runs": "started_at, run_id", "run_events": "run_id, seq",
    "check_results": "run_id, check_id", "quiz_attempts": "id", "spend": "id",
    "tutor_turns": "id", "position": "id",
}
DRAFTS_KEPT = 20          # per (step, file)
RUN_SNAPSHOTS_KEPT = 10   # per (step, file)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def code_hash(files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b"\0" + files[name].replace("\r\n", "\n").encode() + b"\0")
    return h.hexdigest()[:16]


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self.migrate()

    # ------------------------------------------------------------------ plumbing
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]

    @property
    def schema_version(self) -> int:
        with self._lock:
            return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def migrate(self) -> None:
        with self._lock:
            current = self.schema_version
            for version, sql in enumerate(MIGRATIONS[current:], start=current + 1):
                try:
                    self._conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
                except sqlite3.Error:
                    if self._conn.in_transaction:
                        self._conn.execute("ROLLBACK")
                    raise

    # ------------------------------------------------------------- progress
    def _touch_step(self, c: sqlite3.Connection, step_id: str, module_id: str) -> None:
        c.execute(
            """INSERT INTO step_progress (step_id, module_id, status, last_opened_at)
               VALUES (?, ?, 'in_progress', ?)
               ON CONFLICT (step_id) DO UPDATE SET
                 last_opened_at = excluded.last_opened_at,
                 status = CASE WHEN status = 'not_started' THEN 'in_progress' ELSE status END""",
            (step_id, module_id, utcnow()),
        )

    def _set_position(self, c: sqlite3.Connection, **fields: Any) -> None:
        fields["updated_at"] = utcnow()
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{k} = excluded.{k}" for k in fields)
        c.execute(
            f"INSERT INTO position (id, {cols}) VALUES (1, {marks}) "
            f"ON CONFLICT (id) DO UPDATE SET {updates}",
            tuple(fields.values()),
        )

    def open_step(self, step_id: str, module_id: str, filename: str | None = None) -> None:
        with self.tx() as c:
            self._touch_step(c, step_id, module_id)
            self._set_position(c, step_id=step_id, filename=filename)

    def set_cursor(self, step_id: str, filename: str, line: int, col: int) -> None:
        with self.tx() as c:
            self._set_position(c, step_id=step_id, filename=filename, cursor_line=line, cursor_col=col)

    def position(self) -> dict[str, Any] | None:
        rows = self._query("SELECT step_id, filename, cursor_line, cursor_col, last_run_id, updated_at "
                           "FROM position WHERE id = 1")
        return rows[0] if rows and rows[0]["step_id"] else None

    def step_status(self) -> dict[str, str]:
        return {r["step_id"]: r["status"] for r in self._query("SELECT step_id, status FROM step_progress")}

    def complete_step(self, step_id: str, module_id: str, files: dict[str, str]) -> None:
        with self.tx() as c:
            self._touch_step(c, step_id, module_id)
            c.execute("UPDATE step_progress SET status = 'completed', completed_at = ?, code_hash = ? "
                      "WHERE step_id = ?", (utcnow(), code_hash(files), step_id))

    # ---------------------------------------------------------------- drafts
    def save_draft(self, step_id: str, module_id: str, filename: str, code: str) -> bool:
        """Autosave. Returns True when a new snapshot was written (identical code is skipped)."""
        code = code.replace("\r\n", "\n")  # Monaco on Windows may send CRLF
        with self.tx() as c:
            last = c.execute(
                "SELECT code FROM code_snapshots WHERE step_id = ? AND filename = ? AND kind = 'draft' "
                "ORDER BY id DESC LIMIT 1", (step_id, filename)).fetchone()
            changed = last is None or last["code"] != code
            if changed:
                c.execute("INSERT INTO code_snapshots (step_id, kind, filename, code, created_at) "
                          "VALUES (?, 'draft', ?, ?, ?)", (step_id, filename, code, utcnow()))
                self._prune(c, step_id, filename, "draft", DRAFTS_KEPT)
            self._touch_step(c, step_id, module_id)
            self._set_position(c, step_id=step_id, filename=filename)
        return changed

    def _prune(self, c: sqlite3.Connection, step_id: str, filename: str, kind: str, keep: int) -> None:
        c.execute(
            """DELETE FROM code_snapshots
               WHERE step_id = ? AND filename = ? AND kind = ? AND id NOT IN (
                 SELECT id FROM code_snapshots WHERE step_id = ? AND filename = ? AND kind = ?
                 ORDER BY id DESC LIMIT ?)""",
            (step_id, filename, kind, step_id, filename, kind, keep))

    def latest_code(self, step_id: str, filename: str) -> str | None:
        """Most recent draft or run snapshot. This is what 'Continue' restores."""
        rows = self._query("SELECT code FROM code_snapshots WHERE step_id = ? AND filename = ? "
                           "ORDER BY id DESC LIMIT 1", (step_id, filename))
        return rows[0]["code"] if rows else None

    def discard_drafts(self, step_id: str) -> None:
        """'Reset to starter'. Run snapshots are kept as history."""
        with self.tx() as c:
            c.execute("DELETE FROM code_snapshots WHERE step_id = ? AND kind = 'draft'", (step_id,))

    # ------------------------------------------------------------------ runs
    def record_run_start(self, run_id: str, step_id: str, module_id: str, mode: str,
                         model: str | None, files: dict[str, str]) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO runs (run_id, step_id, module_id, mode, model, started_at) "
                      "VALUES (?, ?, ?, ?, ?, ?)", (run_id, step_id, module_id, mode, model, utcnow()))
            for name, code in files.items():
                c.execute("INSERT INTO code_snapshots (step_id, kind, filename, code, created_at) "
                          "VALUES (?, 'run', ?, ?, ?)", (step_id, name, code.replace("\r\n", "\n"), utcnow()))
                self._prune(c, step_id, name, "run", RUN_SNAPSHOTS_KEPT)
            self._touch_step(c, step_id, module_id)
            c.execute("UPDATE step_progress SET attempts = attempts + 1 WHERE step_id = ?", (step_id,))
            self._set_position(c, step_id=step_id, last_run_id=run_id)

    def record_run_end(self, run_id: str, outcome: str, cost_usd: float,
                       checks: Iterable[dict[str, Any]] = ()) -> None:
        checks = list(checks)
        with self.tx() as c:
            for ch in checks:
                c.execute("INSERT OR REPLACE INTO check_results (run_id, check_id, passed, message, evidence_json) "
                          "VALUES (?, ?, ?, ?, ?)",
                          (run_id, ch["check_id"], int(bool(ch["passed"])), ch.get("message"),
                           json.dumps(ch.get("evidence", []))))
            c.execute("UPDATE runs SET outcome = ?, cost_usd = ?, ended_at = ?, checks_passed = ?, checks_total = ? "
                      "WHERE run_id = ?",
                      (outcome, cost_usd, utcnow(), sum(1 for ch in checks if ch["passed"]), len(checks), run_id))

    def save_run_events(self, run_id: str, events: Iterable[dict[str, Any]]) -> None:
        with self.tx() as c:
            c.executemany("INSERT OR REPLACE INTO run_events (run_id, seq, t_ms, type, data_json) VALUES (?, ?, ?, ?, ?)",
                          [(run_id, e["seq"], e["t_ms"], e["type"], json.dumps(e["data"], ensure_ascii=False))
                           for e in events])

    def run_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._query("SELECT seq, t_ms, type, data_json FROM run_events WHERE run_id = ? ORDER BY seq", (run_id,))
        return [{"seq": r["seq"], "t_ms": r["t_ms"], "type": r["type"], "data": json.loads(r["data_json"])} for r in rows]

    def run_record(self, run_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        return rows[0] if rows else None

    def runs_for_step(self, step_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._query("SELECT run_id, model, outcome, cost_usd, started_at, ended_at FROM runs "
                           "WHERE step_id = ? ORDER BY started_at DESC, run_id DESC LIMIT ?", (step_id, limit))

    # ----------------------------------------------------------------- spend
    def record_spend(self, source: str, cost_usd: float, *, run_id: str | None = None,
                     model: str | None = None, usage: dict[str, int] | None = None) -> None:
        u = usage or {}
        with self.tx() as c:
            c.execute(
                "INSERT INTO spend (ts, source, run_id, model, input_tokens, output_tokens, "
                "cache_write_tokens, cache_read_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (utcnow(), source, run_id, model, u.get("input_tokens", 0), u.get("output_tokens", 0),
                 u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0), cost_usd))

    def spend_summary(self) -> dict[str, Any]:
        rows = self._query(
            """SELECT source,
                      SUM(cost_usd) AS total,
                      SUM(CASE WHEN date(ts, 'localtime') = date('now', 'localtime') THEN cost_usd ELSE 0 END) AS today
               FROM spend GROUP BY source""")
        return {
            "today_usd": round(sum(r["today"] or 0 for r in rows), 6),
            "total_usd": round(sum(r["total"] or 0 for r in rows), 6),
            "by_source": {r["source"]: round(r["total"] or 0, 6) for r in rows},
        }

    # ------------------------------------------------------------------ quiz
    def record_quiz_attempt(self, *, item_id: str, module_id: str, type: str, answer: Any,
                            correct: bool, step_id: str | None = None, item_version: int = 1,
                            concepts: Iterable[str] = (), question: str | None = None,
                            correct_answer: Any = None, score: float | None = None,
                            graded_by: str = "auto", feedback: str | None = None,
                            source: str = "app") -> int:
        with self.tx() as c:
            cur = c.execute(
                """INSERT INTO quiz_attempts (item_id, item_version, module_id, step_id, type, concepts_json,
                       question, answer_json, correct_json, correct, score, graded_by, feedback, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item_id, item_version, module_id, step_id, type, json.dumps(sorted(set(concepts))),
                 question, json.dumps(answer), None if correct_answer is None else json.dumps(correct_answer),
                 int(bool(correct)), score, graded_by, feedback, source, utcnow()))
            return int(cur.lastrowid)

    def mistakes(self, module_id: str | None = None) -> dict[str, Any]:
        """'What I got wrong': still wrong, fixed after retry, and failing checks, grouped by concept."""
        ranked = """
            WITH ranked AS (
              SELECT *,
                     ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY created_at DESC, id DESC) AS rn,
                     SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) OVER (PARTITION BY item_id) AS misses,
                     COUNT(*) OVER (PARTITION BY item_id) AS tries
              FROM quiz_attempts WHERE (? IS NULL OR module_id = ?)
            )"""
        cols = ("item_id, module_id, step_id, type, question, answer_json, correct_json, concepts_json, "
                "feedback, misses, tries, created_at AS last_attempt_at")
        still = self._query(f"{ranked} SELECT {cols} FROM ranked WHERE rn = 1 AND correct = 0 "
                            "ORDER BY created_at", (module_id, module_id))
        fixed = self._query(f"{ranked} SELECT {cols} FROM ranked WHERE rn = 1 AND correct = 1 AND misses > 0 "
                            "ORDER BY created_at", (module_id, module_id))
        failing = self._query(
            """WITH latest AS (
                 SELECT run_id, step_id, module_id,
                        ROW_NUMBER() OVER (PARTITION BY step_id ORDER BY started_at DESC, run_id DESC) AS rn
                 FROM runs WHERE (? IS NULL OR module_id = ?)
               )
               SELECT l.step_id, c.check_id, c.message, l.run_id
               FROM latest l JOIN check_results c ON c.run_id = l.run_id
               WHERE l.rn = 1 AND c.passed = 0 ORDER BY l.step_id, c.check_id""",
            (module_id, module_id))
        for row in still + fixed:
            for key in ("answer_json", "correct_json", "concepts_json"):
                raw = row.pop(key, None)
                row[key.removesuffix("_json")] = json.loads(raw) if raw else None
        by_concept = Counter(c for row in still for c in (row["concepts"] or ["(untagged)"]))
        return {"still_wrong": still, "fixed_after_retry": fixed, "failing_checks": failing,
                "by_concept": dict(by_concept.most_common())}

    # ---------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        counts = self._query("SELECT module_id, status, COUNT(*) AS n FROM step_progress GROUP BY module_id, status")
        modules: dict[str, dict[str, int]] = {}
        for r in counts:
            modules.setdefault(r["module_id"], {})[r["status"]] = r["n"]
        quiz = self._query("SELECT COUNT(*) AS attempts, COALESCE(SUM(correct), 0) AS correct FROM quiz_attempts")[0]
        m = self.mistakes()
        return {
            "position": self.position(),
            "modules": modules,
            "quiz": {"attempts": quiz["attempts"], "correct": quiz["correct"],
                     "still_wrong": len(m["still_wrong"]), "fixed_after_retry": len(m["fixed_after_retry"])},
            "failing_checks": len(m["failing_checks"]),
            "spend": self.spend_summary(),
            "db": str(self.path),
        }

    # -------------------------------------------------------- export/import
    def export_all(self) -> dict[str, Any]:
        tables = {t: self._query(f"SELECT * FROM {t} ORDER BY {_ORDER_BY[t]}") for t in EXPORT_TABLES}
        return {"format": EXPORT_FORMAT, "schema_version": self.schema_version,
                "exported_at": utcnow(), "tables": tables}

    def is_empty(self) -> bool:
        return all(self._query(f"SELECT 1 FROM {t} LIMIT 1") == [] for t in EXPORT_TABLES)

    def import_all(self, data: dict[str, Any]) -> dict[str, int]:
        """Replace all learner state with an export. Returns rows imported per table."""
        if data.get("format") != EXPORT_FORMAT:
            raise ValueError(f"not an FDE Academy progress export (format={data.get('format')!r})")
        if int(data.get("schema_version", 0)) > self.schema_version:
            raise ValueError(f"export is from a newer schema ({data['schema_version']} > {self.schema_version}); "
                             "update FDE Academy first")
        imported: dict[str, int] = {}
        with self.tx() as c:
            for t in reversed(EXPORT_TABLES):
                c.execute(f"DELETE FROM {t}")
            for t in EXPORT_TABLES:
                rows = data.get("tables", {}).get(t, [])
                cols_now = {r["name"] for r in c.execute(f"PRAGMA table_info({t})")}
                for row in rows:
                    keep = {k: v for k, v in row.items() if k in cols_now}
                    c.execute(f"INSERT INTO {t} ({', '.join(keep)}) VALUES ({', '.join('?' for _ in keep)})",
                              tuple(keep.values()))
                imported[t] = len(rows)
        return imported

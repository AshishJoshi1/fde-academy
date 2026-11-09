"""Schema migrations, applied in order. PRAGMA user_version = number applied.

Never edit a migration that has shipped; append a new one.
"""

MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE step_progress (
        step_id        TEXT PRIMARY KEY,           -- e.g. m02.lab02.s01
        module_id      TEXT NOT NULL,
        status         TEXT NOT NULL DEFAULT 'not_started'
                       CHECK (status IN ('not_started', 'in_progress', 'completed')),
        attempts       INTEGER NOT NULL DEFAULT 0, -- runs of this step
        last_opened_at TEXT,
        completed_at   TEXT,
        code_hash      TEXT                        -- hash of the code that completed it
    );

    CREATE TABLE code_snapshots (
        id         INTEGER PRIMARY KEY,
        step_id    TEXT NOT NULL,
        kind       TEXT NOT NULL CHECK (kind IN ('draft', 'run')),
        filename   TEXT NOT NULL,
        code       TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX code_snapshots_lookup ON code_snapshots (step_id, filename, kind, id);

    CREATE TABLE runs (
        run_id        TEXT PRIMARY KEY,
        step_id       TEXT NOT NULL,
        module_id     TEXT NOT NULL,
        mode          TEXT NOT NULL,                -- replay | live | python
        model         TEXT,
        outcome       TEXT,                         -- ok | error | timeout | aborted | budget
        cost_usd      REAL NOT NULL DEFAULT 0,
        checks_passed INTEGER,
        checks_total  INTEGER,
        started_at    TEXT NOT NULL,
        ended_at      TEXT
    );
    CREATE INDEX runs_by_step ON runs (step_id, started_at);

    CREATE TABLE check_results (
        run_id        TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
        check_id      TEXT NOT NULL,
        passed        INTEGER NOT NULL,
        message       TEXT,
        evidence_json TEXT,                         -- list of event seq numbers
        PRIMARY KEY (run_id, check_id)
    );

    CREATE TABLE quiz_attempts (
        id            INTEGER PRIMARY KEY,
        item_id       TEXT NOT NULL,                -- bank item id, or chat:<module>:<date>:<n>
        item_version  INTEGER NOT NULL DEFAULT 1,
        module_id     TEXT NOT NULL,
        step_id       TEXT,
        type          TEXT NOT NULL,                -- mcq | numeric | trace_reading | code_fix | short_answer | open
        concepts_json TEXT NOT NULL DEFAULT '[]',
        question      TEXT,
        answer_json   TEXT NOT NULL,
        correct_json  TEXT,
        correct       INTEGER NOT NULL,
        score         REAL,
        graded_by     TEXT NOT NULL,                -- auto | judge | self | claude-chat
        feedback      TEXT,
        source        TEXT NOT NULL DEFAULT 'app',  -- app | chat
        created_at    TEXT NOT NULL
    );
    CREATE INDEX quiz_by_item ON quiz_attempts (item_id, created_at);
    CREATE INDEX quiz_by_module ON quiz_attempts (module_id);

    CREATE TABLE spend (
        id                 INTEGER PRIMARY KEY,
        ts                 TEXT NOT NULL,
        source             TEXT NOT NULL,           -- run | tutor | judge | record
        run_id             TEXT,
        model              TEXT,
        input_tokens       INTEGER NOT NULL DEFAULT 0,
        output_tokens      INTEGER NOT NULL DEFAULT 0,
        cache_write_tokens INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
        cost_usd           REAL NOT NULL
    );

    CREATE TABLE tutor_turns (
        id         INTEGER PRIMARY KEY,
        step_id    TEXT,
        role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content    TEXT NOT NULL,
        cost_usd   REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE position (
        id          INTEGER PRIMARY KEY CHECK (id = 1),
        step_id     TEXT,
        filename    TEXT,
        cursor_line INTEGER,
        cursor_col  INTEGER,
        last_run_id TEXT,
        updated_at  TEXT
    );
    """,
    # 2: run events (the ordered record of a run: console lines, model calls, exit)
    """
    CREATE TABLE run_events (
        run_id    TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
        seq       INTEGER NOT NULL,
        t_ms      INTEGER NOT NULL,                 -- milliseconds since the run started
        type      TEXT NOT NULL,                    -- run.started | console.out | llm.request | ...
        data_json TEXT NOT NULL,
        PRIMARY KEY (run_id, seq)
    );
    """,
    # 3: experiments (predictions graded against a run), and which run each code snapshot is from
    """
    ALTER TABLE code_snapshots ADD COLUMN run_id TEXT;   -- set on kind = 'run'
    CREATE INDEX code_snapshots_by_run ON code_snapshots (run_id);
    -- Earlier run snapshots: each was written in its run's start transaction, just after the run row.
    UPDATE code_snapshots SET run_id = (
        SELECT r.run_id FROM runs r WHERE r.step_id = code_snapshots.step_id
          AND r.started_at <= code_snapshots.created_at ORDER BY r.started_at DESC, r.run_id DESC LIMIT 1)
    WHERE kind = 'run';

    CREATE TABLE experiment_attempts (
        id            INTEGER PRIMARY KEY,
        step_id       TEXT NOT NULL,
        module_id     TEXT NOT NULL,
        experiment_id TEXT NOT NULL,                -- e.g. e2
        attempt       INTEGER NOT NULL,             -- 1, then 2 after a redo, ...
        run_id        TEXT REFERENCES runs (run_id),  -- the run the predictions are graded against
        explanation   TEXT,                         -- the learner's own why, before the card's
        committed_at  TEXT NOT NULL,
        graded_at     TEXT,
        explained_at  TEXT,
        UNIQUE (step_id, experiment_id, attempt)
    );

    CREATE TABLE predictions (
        attempt_id  INTEGER NOT NULL REFERENCES experiment_attempts (id) ON DELETE CASCADE,
        item_id     TEXT NOT NULL,                  -- e.g. p1
        type        TEXT NOT NULL,                  -- mcq | numeric | text
        prompt      TEXT,
        answer_json TEXT NOT NULL,
        actual_json TEXT,                           -- what the run measured, once graded
        actual_display TEXT,
        correct     INTEGER,                        -- NULL: not auto-graded, or not measured
        note        TEXT,
        PRIMARY KEY (attempt_id, item_id)
    );
    """,
    # 4: tutor threads, one per guide step. A thread is replayed to the model on every turn, so
    # each turn keeps exactly what was sent (user) or returned (assistant), not just its text.
    """
    ALTER TABLE tutor_turns ADD COLUMN guide_id TEXT;       -- e.g. g2; with step_id, names the thread
    ALTER TABLE tutor_turns ADD COLUMN sent_json TEXT;      -- user: content sent; assistant: content blocks returned
    ALTER TABLE tutor_turns ADD COLUMN request_json TEXT;   -- assistant: the exact request body of its call
    ALTER TABLE tutor_turns ADD COLUMN usage_json TEXT;     -- assistant: the call's usage
    ALTER TABLE tutor_turns ADD COLUMN model TEXT;
    ALTER TABLE tutor_turns ADD COLUMN ms INTEGER;          -- assistant: wall time of the call
    CREATE INDEX tutor_by_thread ON tutor_turns (step_id, guide_id, id);
    """,
]

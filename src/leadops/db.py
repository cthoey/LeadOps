from __future__ import annotations

from pathlib import Path
import sqlite3


ASSESSMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    confidence REAL NOT NULL,
    profile_fit TEXT NOT NULL DEFAULT 'unknown',
    activation_signal TEXT NOT NULL DEFAULT 'unknown',
    evidence_confidence TEXT NOT NULL DEFAULT 'thin',
    freshness TEXT NOT NULL DEFAULT 'unknown',
    action_queue TEXT NOT NULL DEFAULT 'watch',
    summary_thesis TEXT NOT NULL DEFAULT '',
    fit_rationale TEXT NOT NULL DEFAULT '',
    activation_rationale TEXT NOT NULL DEFAULT '',
    outreach_angle TEXT NOT NULL,
    draft_subject TEXT NOT NULL,
    draft_body TEXT NOT NULL,
    signal_tags_json TEXT NOT NULL DEFAULT '[]',
    risk_tags_json TEXT NOT NULL DEFAULT '[]',
    unknowns_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL,
    source_date TEXT,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(target_id) REFERENCES targets(id),
    FOREIGN KEY(run_id) REFERENCES daily_runs(id)
);
"""


REVIEW_ITEMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    packet_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    assessment_id INTEGER NOT NULL,
    section TEXT NOT NULL,
    rank_index INTEGER NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(packet_id) REFERENCES review_packets(id),
    FOREIGN KEY(target_id) REFERENCES targets(id),
    FOREIGN KEY(assessment_id) REFERENCES assessments(id)
);
"""


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    url TEXT,
    domain TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    raw_evidence TEXT NOT NULL DEFAULT '',
    dedupe_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_packeted_at TEXT,
    next_followup_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

""" + ASSESSMENTS_TABLE_SQL + """

CREATE TABLE IF NOT EXISTS review_packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    packet_date TEXT NOT NULL,
    version INTEGER NOT NULL,
    markdown_path TEXT NOT NULL,
    json_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES daily_runs(id)
);

""" + REVIEW_ITEMS_TABLE_SQL + """

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(target_id) REFERENCES targets(id)
);

CREATE TABLE IF NOT EXISTS query_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS query_run_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_run_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    discovery_score REAL NOT NULL,
    discovery_confidence REAL NOT NULL,
    candidate_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(query_run_id) REFERENCES query_runs(id),
    FOREIGN KEY(target_id) REFERENCES targets(id)
);

CREATE INDEX IF NOT EXISTS idx_targets_status ON targets(status);
CREATE INDEX IF NOT EXISTS idx_targets_followup ON targets(next_followup_at);
CREATE INDEX IF NOT EXISTS idx_assessments_target_run ON assessments(target_id, run_id);
CREATE INDEX IF NOT EXISTS idx_packets_date ON review_packets(packet_date);
CREATE INDEX IF NOT EXISTS idx_query_runs_status ON query_runs(status);
CREATE INDEX IF NOT EXISTS idx_query_run_targets_run ON query_run_targets(query_run_id);
"""


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_database(database_path: Path) -> None:
    conn = connect(database_path)
    try:
        conn.executescript(SCHEMA)
        _migrate_assessments_table(conn)
        _ensure_assessment_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_assessment_columns(conn: sqlite3.Connection) -> None:
    columns = {
        "profile_fit": "TEXT NOT NULL DEFAULT 'unknown'",
        "activation_signal": "TEXT NOT NULL DEFAULT 'unknown'",
        "evidence_confidence": "TEXT NOT NULL DEFAULT 'thin'",
        "freshness": "TEXT NOT NULL DEFAULT 'unknown'",
        "action_queue": "TEXT NOT NULL DEFAULT 'watch'",
        "summary_thesis": "TEXT NOT NULL DEFAULT ''",
        "fit_rationale": "TEXT NOT NULL DEFAULT ''",
        "activation_rationale": "TEXT NOT NULL DEFAULT ''",
        "signal_tags_json": "TEXT NOT NULL DEFAULT '[]'",
        "risk_tags_json": "TEXT NOT NULL DEFAULT '[]'",
        "unknowns_json": "TEXT NOT NULL DEFAULT '[]'",
        "source_date": "TEXT",
    }
    existing = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(assessments)").fetchall()
    }
    for name, definition in columns.items():
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE assessments ADD COLUMN {name} {definition}")


def _migrate_assessments_table(conn: sqlite3.Connection) -> None:
    existing = [str(row["name"]) for row in conn.execute("PRAGMA table_info(assessments)").fetchall()]
    if not existing:
        return

    desired = {
        "id",
        "target_id",
        "run_id",
        "provider",
        "confidence",
        "profile_fit",
        "activation_signal",
        "evidence_confidence",
        "freshness",
        "action_queue",
        "summary_thesis",
        "fit_rationale",
        "activation_rationale",
        "outreach_angle",
        "draft_subject",
        "draft_body",
        "signal_tags_json",
        "risk_tags_json",
        "unknowns_json",
        "evidence_json",
        "source_date",
        "raw_json",
        "created_at",
    }
    legacy_markers = {
        "fit_score",
        "recommend",
        "why_fit",
        "why_now",
        "risks_json",
        "rubric_json",
    }
    if set(existing) == desired and not any(name in legacy_markers for name in existing):
        return

    conn.execute("ALTER TABLE assessments RENAME TO assessments_legacy")
    conn.executescript(ASSESSMENTS_TABLE_SQL)

    rows = conn.execute("SELECT * FROM assessments_legacy ORDER BY id ASC").fetchall()
    for row in rows:
        payload = dict(row)
        summary_thesis = str(payload.get("summary_thesis") or payload.get("fit_rationale") or payload.get("why_fit") or "")
        fit_rationale = str(payload.get("fit_rationale") or payload.get("why_fit") or "")
        activation_rationale = str(payload.get("activation_rationale") or payload.get("why_now") or "")
        risk_tags_json = payload.get("risk_tags_json")
        if risk_tags_json is None:
            risk_tags_json = payload.get("risks_json") or "[]"
        conn.execute(
            """
            INSERT INTO assessments (
                id, target_id, run_id, provider, confidence,
                profile_fit, activation_signal, evidence_confidence, freshness, action_queue,
                summary_thesis, fit_rationale, activation_rationale, outreach_angle, draft_subject, draft_body,
                signal_tags_json, risk_tags_json, unknowns_json, evidence_json,
                source_date, raw_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(payload["id"]),
                int(payload["target_id"]),
                int(payload["run_id"]),
                str(payload["provider"]),
                float(payload.get("confidence", 0.0)),
                str(payload.get("profile_fit") or "unknown"),
                str(payload.get("activation_signal") or "unknown"),
                str(payload.get("evidence_confidence") or "thin"),
                str(payload.get("freshness") or "unknown"),
                str(payload.get("action_queue") or "watch"),
                summary_thesis,
                fit_rationale,
                activation_rationale,
                str(payload.get("outreach_angle") or ""),
                str(payload.get("draft_subject") or ""),
                str(payload.get("draft_body") or ""),
                str(payload.get("signal_tags_json") or "[]"),
                str(risk_tags_json),
                str(payload.get("unknowns_json") or "[]"),
                str(payload.get("evidence_json") or "[]"),
                str(payload["source_date"]) if payload.get("source_date") is not None else None,
                str(payload.get("raw_json") or "{}"),
                str(payload.get("created_at") or ""),
            ),
        )

    _rebuild_review_items_assessment_fk(conn)
    conn.execute("DROP TABLE assessments_legacy")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assessments_target_run ON assessments(target_id, run_id)")


def _rebuild_review_items_assessment_fk(conn: sqlite3.Connection) -> None:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'review_items'"
    ).fetchone()
    if not table_exists:
        return

    foreign_keys = conn.execute("PRAGMA foreign_key_list(review_items)").fetchall()
    if not any(str(row["table"]) == "assessments_legacy" for row in foreign_keys):
        return

    conn.execute("ALTER TABLE review_items RENAME TO review_items_legacy")
    conn.executescript(REVIEW_ITEMS_TABLE_SQL)

    rows = conn.execute("SELECT * FROM review_items_legacy ORDER BY id ASC").fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO review_items (
                id, packet_id, target_id, assessment_id, section,
                rank_index, score, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["id"]),
                int(row["packet_id"]),
                int(row["target_id"]),
                int(row["assessment_id"]),
                str(row["section"]),
                int(row["rank_index"]),
                float(row["score"]),
                float(row["confidence"]),
                str(row["created_at"]),
            ),
        )

    conn.execute("DROP TABLE review_items_legacy")

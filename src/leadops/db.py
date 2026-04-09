from __future__ import annotations

from pathlib import Path
import sqlite3


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

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    fit_score REAL NOT NULL,
    confidence REAL NOT NULL,
    recommend INTEGER NOT NULL,
    why_fit TEXT NOT NULL,
    why_now TEXT NOT NULL,
    outreach_angle TEXT NOT NULL,
    draft_subject TEXT NOT NULL,
    draft_body TEXT NOT NULL,
    risks_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    rubric_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(target_id) REFERENCES targets(id),
    FOREIGN KEY(run_id) REFERENCES daily_runs(id)
);

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
        conn.commit()
    finally:
        conn.close()

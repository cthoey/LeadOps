from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3

from leadops.models import AssessmentResult, DiscoveryCandidate
from leadops.util import dedupe_key, domain_from_url, normalize_name, utcnow


TARGET_STATUSES = {
    "candidate",
    "approved",
    "rejected",
    "sent",
    "replied",
    "snoozed",
    "archived",
}


@dataclass(slots=True)
class TargetRecord:
    id: int
    kind: str
    name: str
    url: str
    source: str
    notes: str
    raw_evidence: str
    status: str
    domain: str
    dedupe_key: str
    last_packeted_at: str | None
    next_followup_at: str | None


@dataclass(slots=True)
class FeedbackExample:
    action: str
    reason: str
    notes: str
    created_at: str
    target_id: int
    target_kind: str
    target_name: str
    target_source: str
    target_notes: str
    target_url: str

    def as_payload(self) -> dict[str, str]:
        return {
            "action": self.action,
            "reason": self.reason,
            "notes": self.notes,
            "created_at": self.created_at,
            "target_id": str(self.target_id),
            "kind": self.target_kind,
            "name": self.target_name,
            "source": self.target_source,
            "url": self.target_url,
            "summary": self.target_notes,
        }


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def close(self) -> None:
        self.conn.close()

    def add_or_update_target(
        self,
        *,
        kind: str,
        name: str,
        url: str | None,
        source: str,
        notes: str,
        raw_evidence: str = "",
    ) -> tuple[int, str]:
        if kind not in {"connector", "founder"}:
            raise ValueError("kind must be connector or founder")

        now = utcnow()
        normalized = normalize_name(name)
        domain = domain_from_url(url)
        key = dedupe_key(kind, name, url)
        row = self.conn.execute(
            "SELECT id, notes, raw_evidence FROM targets WHERE dedupe_key = ?",
            (key,),
        ).fetchone()
        if row:
            merged_notes = "\n\n".join([item for item in [row["notes"], notes] if item]).strip()
            merged_evidence = "\n\n".join([item for item in [row["raw_evidence"], raw_evidence] if item]).strip()
            self.conn.execute(
                """
                UPDATE targets
                SET name = ?, normalized_name = ?, url = COALESCE(?, url), domain = ?, source = ?,
                    notes = ?, raw_evidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    normalized,
                    url,
                    domain,
                    source,
                    merged_notes,
                    merged_evidence,
                    now,
                    int(row["id"]),
                ),
            )
            self.conn.commit()
            return int(row["id"]), "updated"

        cur = self.conn.execute(
            """
            INSERT INTO targets (
                kind, name, normalized_name, url, domain, source, notes, raw_evidence,
                dedupe_key, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?)
            """,
            (kind, name, normalized, url, domain, source, notes, raw_evidence, key, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid), "created"

    def import_jsonl(self, path: Path) -> tuple[int, int]:
        created = 0
        updated = 0
        if not path.exists():
            return created, updated
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                _id, action = self.add_or_update_target(
                    kind=str(item["kind"]),
                    name=str(item["name"]),
                    url=str(item.get("url", "")).strip() or None,
                    source=str(item.get("source", "import")),
                    notes=str(item.get("notes", "")),
                    raw_evidence=str(item.get("raw_evidence", "")),
                )
                if action == "created":
                    created += 1
                else:
                    updated += 1
        return created, updated

    def start_run(self, run_date: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO daily_runs (run_date, started_at, status) VALUES (?, ?, 'running')",
            (run_date, utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def start_query_run(self, *, query_text: str, kind: str, provider: str) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO query_runs (query_text, kind, provider, started_at, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            (query_text, kind, provider, utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, status: str, notes: str = "") -> None:
        self.conn.execute(
            "UPDATE daily_runs SET finished_at = ?, status = ?, notes = ? WHERE id = ?",
            (utcnow(), status, notes, run_id),
        )
        self.conn.commit()

    def finish_query_run(self, query_run_id: int, *, status: str, notes: str = "", raw_json: str = "") -> None:
        self.conn.execute(
            """
            UPDATE query_runs
            SET finished_at = ?, status = ?, notes = ?, raw_json = ?
            WHERE id = ?
            """,
            (utcnow(), status, notes, raw_json, query_run_id),
        )
        self.conn.commit()

    def list_candidate_targets(self, on_or_before: str | None = None) -> list[TargetRecord]:
        if on_or_before is None:
            rows = self.conn.execute(
                """
                SELECT id, kind, name, COALESCE(url, '') AS url, source, notes, raw_evidence,
                       status, domain, dedupe_key, last_packeted_at, next_followup_at
                FROM targets
                WHERE status IN ('candidate', 'approved')
                ORDER BY created_at ASC
                """
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT id, kind, name, COALESCE(url, '') AS url, source, notes, raw_evidence,
                       status, domain, dedupe_key, last_packeted_at, next_followup_at
                FROM targets
                WHERE status IN ('candidate', 'approved')
                  AND (next_followup_at IS NULL OR next_followup_at <= ?)
                ORDER BY created_at ASC
                """,
                (on_or_before,),
            ).fetchall()
        return [self._row_to_target(row) for row in rows]

    def list_due_followups(self, on_or_before: str) -> list[TargetRecord]:
        rows = self.conn.execute(
            """
            SELECT id, kind, name, COALESCE(url, '') AS url, source, notes, raw_evidence,
                   status, domain, dedupe_key, last_packeted_at, next_followup_at
            FROM targets
            WHERE status = 'sent'
              AND next_followup_at IS NOT NULL
              AND next_followup_at <= ?
            ORDER BY next_followup_at ASC, updated_at ASC
            """,
            (on_or_before,),
        ).fetchall()
        return [self._row_to_target(row) for row in rows]

    def list_targets(self) -> list[TargetRecord]:
        rows = self.conn.execute(
            """
            SELECT id, kind, name, COALESCE(url, '') AS url, source, notes, raw_evidence,
                   status, domain, dedupe_key, last_packeted_at, next_followup_at
            FROM targets
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [self._row_to_target(row) for row in rows]

    def save_assessment(self, run_id: int, target_id: int, provider: str, assessment: AssessmentResult) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO assessments (
                target_id, run_id, provider, confidence,
                profile_fit, activation_signal, evidence_confidence, freshness, action_queue,
                summary_thesis, fit_rationale, activation_rationale, outreach_angle, draft_subject, draft_body,
                signal_tags_json, risk_tags_json, unknowns_json, evidence_json,
                source_date, raw_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_id,
                run_id,
                provider,
                assessment.confidence,
                assessment.profile_fit,
                assessment.activation_signal,
                assessment.evidence_confidence,
                assessment.freshness,
                assessment.action_queue,
                assessment.summary_thesis,
                assessment.fit_rationale,
                assessment.activation_rationale,
                assessment.outreach_angle,
                assessment.draft_subject,
                assessment.draft_body,
                json.dumps(assessment.signal_tags, indent=2),
                json.dumps(assessment.risk_tags, indent=2),
                json.dumps(assessment.unknowns_to_verify, indent=2),
                json.dumps(assessment.evidence, indent=2),
                assessment.source_date,
                json.dumps(assessment.raw_response, indent=2),
                utcnow(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def next_packet_version(self, packet_date: str) -> int:
        return self._next_packet_version(packet_date)

    def create_packet(
        self,
        run_id: int,
        packet_date: str,
        markdown_path: Path,
        json_path: Path,
        *,
        version: int | None = None,
    ) -> int:
        if version is None:
            version = self._next_packet_version(packet_date)
        cur = self.conn.execute(
            """
            INSERT INTO review_packets (run_id, packet_date, version, markdown_path, json_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, packet_date, version, str(markdown_path), str(json_path), utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_packet_item(
        self,
        *,
        packet_id: int,
        target_id: int,
        assessment_id: int,
        section: str,
        rank_index: int,
        score: float,
        confidence: float,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO review_items (
                packet_id, target_id, assessment_id, section, rank_index, score, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (packet_id, target_id, assessment_id, section, rank_index, score, confidence, utcnow()),
        )
        self.conn.commit()

    def mark_packeted(self, target_id: int, packet_date: str) -> None:
        self.conn.execute(
            "UPDATE targets SET last_packeted_at = ?, updated_at = ? WHERE id = ?",
            (packet_date, utcnow(), target_id),
        )
        self.conn.commit()

    def update_status(self, target_id: int, *, status: str, followup_date: str | None = None, reason: str = "") -> None:
        if status not in TARGET_STATUSES:
            raise ValueError(f"Unsupported status: {status}")
        self.conn.execute(
            """
            UPDATE targets
            SET status = ?, next_followup_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, followup_date, utcnow(), target_id),
        )
        self.conn.execute(
            "INSERT INTO feedback (target_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
            (target_id, status, reason, utcnow()),
        )
        self.conn.commit()

    def add_query_run_target(
        self,
        *,
        query_run_id: int,
        target_id: int,
        action: str,
        candidate: DiscoveryCandidate,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO query_run_targets (
                query_run_id, target_id, action, discovery_score, discovery_confidence,
                candidate_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_run_id,
                target_id,
                action,
                candidate.priority_score,
                candidate.confidence,
                json.dumps(candidate.as_dict(), indent=2),
                utcnow(),
            ),
        )
        self.conn.commit()

    def feedback_context_payload(self, limit_per_action: int = 3) -> dict[str, list[dict[str, str]]]:
        examples = self.list_feedback_examples(limit_per_action=limit_per_action)
        positive_actions = {"approved", "sent", "replied"}
        negative_actions = {"rejected", "snoozed", "archived"}

        liked: list[dict[str, str]] = []
        avoided: list[dict[str, str]] = []
        for example in examples:
            payload = example.as_payload()
            if example.action in positive_actions:
                liked.append(payload)
            elif example.action in negative_actions:
                avoided.append(payload)

        return {
            "liked": liked,
            "avoided": avoided,
        }

    def list_feedback_examples(self, limit_per_action: int = 3) -> list[FeedbackExample]:
        rows = self.conn.execute(
            """
            SELECT
                f.action,
                f.reason,
                f.notes,
                f.created_at,
                t.id AS target_id,
                t.kind AS target_kind,
                t.name AS target_name,
                t.source AS target_source,
                t.notes AS target_notes,
                COALESCE(t.url, '') AS target_url
            FROM feedback f
            JOIN targets t ON t.id = f.target_id
            ORDER BY f.created_at DESC, f.id DESC
            """
        ).fetchall()

        counts: dict[str, int] = {}
        items: list[FeedbackExample] = []
        for row in rows:
            action = str(row["action"])
            seen = counts.get(action, 0)
            if seen >= limit_per_action:
                continue
            counts[action] = seen + 1
            items.append(
                FeedbackExample(
                    action=action,
                    reason=str(row["reason"]),
                    notes=str(row["notes"]),
                    created_at=str(row["created_at"]),
                    target_id=int(row["target_id"]),
                    target_kind=str(row["target_kind"]),
                    target_name=str(row["target_name"]),
                    target_source=str(row["target_source"]),
                    target_notes=str(row["target_notes"]),
                    target_url=str(row["target_url"]),
                )
            )
        return items

    def _next_packet_version(self, packet_date: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM review_packets WHERE packet_date = ?",
            (packet_date,),
        ).fetchone()
        return int(row["version"]) + 1

    @staticmethod
    def _row_to_target(row: sqlite3.Row) -> TargetRecord:
        return TargetRecord(
            id=int(row["id"]),
            kind=str(row["kind"]),
            name=str(row["name"]),
            url=str(row["url"]),
            source=str(row["source"]),
            notes=str(row["notes"]),
            raw_evidence=str(row["raw_evidence"]),
            status=str(row["status"]),
            domain=str(row["domain"]),
            dedupe_key=str(row["dedupe_key"]),
            last_packeted_at=row["last_packeted_at"],
            next_followup_at=row["next_followup_at"],
        )

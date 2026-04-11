from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from leadops.approaches import get_approach
from leadops.cli import main as cli_main
from leadops.config import EmailConfig, initialize_workspace, load_workspace_config
from leadops.daily import run_daily
from leadops.db import connect, initialize_database
from leadops.discovery import discover_track, discover_web
from leadops.extract import extract_from_html
from leadops.mailer import send_email_digest
from leadops.models import AssessmentResult, DiscoveryBatch, DiscoveryCandidate
from leadops.query_plans import get_track
from leadops.repository import Repository
from leadops.schedule import LaunchdSpec, build_program_arguments, render_launchd_plist
from leadops.util import dedupe_key


class LeadOpsTests(unittest.TestCase):
    def _repo_for_workspace(self, workspace: Path) -> Repository:
        config = load_workspace_config(workspace)
        initialize_database(config.database_path)
        conn = connect(config.database_path)
        self.addCleanup(conn.close)
        return Repository(conn)

    def _candidate_queue_items(self, payload: dict[str, object]) -> list[dict[str, object]]:
        queues = payload.get("queues", {})
        if not isinstance(queues, dict):
            return []
        items: list[dict[str, object]] = []
        for queue_name in ("pursue_now", "watch", "nurture"):
            queue_items = queues.get(queue_name, [])
            if isinstance(queue_items, list):
                items.extend(item for item in queue_items if isinstance(item, dict))
        return items

    def test_dedupe_prefers_domain(self) -> None:
        self.assertEqual(dedupe_key("founder", "Example", "https://www.example.com/app"), "founder:example.com")

    def test_initialize_workspace_loads_business_profile_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            config = load_workspace_config(workspace)

            self.assertIn("customer-facing software", config.profile.offer)
            self.assertTrue(config.profile.ideal_customer)
            self.assertTrue(config.profile.fit_definition)
            self.assertGreater(len(config.profile.preferred_signals), 0)
            self.assertGreater(len(config.profile.caution_signals), 0)
            self.assertGreater(len(config.profile.post_contact_checks), 0)

    def test_list_candidate_targets_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            repo = self._repo_for_workspace(workspace)

            first_id, _ = repo.add_or_update_target(
                kind="founder",
                name="Older Candidate",
                url="https://older.example",
                source="manual",
                notes="Older product opportunity.",
            )
            second_id, _ = repo.add_or_update_target(
                kind="founder",
                name="Newer Candidate",
                url="https://newer.example",
                source="manual",
                notes="Newer product opportunity.",
            )

            repo.conn.execute(
                "UPDATE targets SET created_at = ?, updated_at = ? WHERE id = ?",
                ("2026-04-08T00:00:00Z", "2026-04-08T00:00:00Z", first_id),
            )
            repo.conn.execute(
                "UPDATE targets SET created_at = ?, updated_at = ? WHERE id = ?",
                ("2026-04-09T00:00:00Z", "2026-04-09T00:00:00Z", second_id),
            )
            repo.conn.commit()

            targets = repo.list_candidate_targets()
            self.assertEqual([target.name for target in targets[:2]], ["Newer Candidate", "Older Candidate"])

    def test_extract_from_html(self) -> None:
        page = extract_from_html(
            """
            <html>
              <head>
                <title>Example Startup | Build Faster</title>
                <meta name="description" content="Founder-led startup with beta product." />
              </head>
              <body>
                <main>
                  <h1>Build your roadmap</h1>
                  <p>We help teams launch their prototype.</p>
                </main>
              </body>
            </html>
            """,
            final_url="https://example.com",
        )
        self.assertEqual(page.lead_name(), "Example Startup")
        self.assertIn("Founder-led startup", page.raw_evidence())
        self.assertIn("Build your roadmap", page.raw_evidence())

    def test_run_daily_writes_packet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)
            repo.add_or_update_target(
                kind="founder",
                name="Example Startup",
                url="https://example.com",
                source="manual",
                notes="Founder-led startup with roadmap, prototype, no engineering team, and early launch needs.",
            )

            result = run_daily(repo, config, "2026-04-08")
            self.assertTrue(result.packet_markdown.exists())
            self.assertTrue(result.packet_json.exists())
            self.assertTrue(result.digest_text.exists())
            self.assertTrue(result.digest_html.exists())
            self.assertGreaterEqual(result.surfaced_new, 1)
            digest_body = result.digest_text.read_text(encoding="utf-8")
            digest_html = result.digest_html.read_text(encoding="utf-8")
            self.assertIn("LeadOps Daily Brief - 2026-04-08", digest_body)
            self.assertIn("<!doctype html>", digest_html)
            self.assertIn("summary-card", digest_html)
            self.assertIn("Example Startup", digest_html)

    def test_run_daily_send_digest_failure_does_not_advance_packet_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)
            target_id, _ = repo.add_or_update_target(
                kind="founder",
                name="Digest Failure Startup",
                url="https://digest-failure.example",
                source="manual",
                notes="Founder-led prototype with roadmap pressure and no engineering team.",
            )

            with patch("leadops.daily.send_email_digest", side_effect=RuntimeError("smtp down")):
                with self.assertRaisesRegex(RuntimeError, "smtp down"):
                    run_daily(repo, config, "2026-04-10", send_digest=True)

            target = next(item for item in repo.list_targets() if item.id == target_id)
            self.assertIsNone(target.last_packeted_at)
            run_row = repo.conn.execute("SELECT status FROM daily_runs ORDER BY id DESC LIMIT 1").fetchone()
            packet_count_row = repo.conn.execute("SELECT COUNT(*) AS count FROM review_packets").fetchone()
            review_item_count_row = repo.conn.execute("SELECT COUNT(*) AS count FROM review_items").fetchone()
            self.assertEqual(run_row["status"], "failed")
            self.assertEqual(int(packet_count_row["count"]), 0)
            self.assertEqual(int(review_item_count_row["count"]), 0)

    def test_run_daily_assesses_bounded_newest_candidate_window(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)

            for index in range(25):
                target_id, _ = repo.add_or_update_target(
                    kind="founder",
                    name=f"Candidate {index:02d}",
                    url=f"https://candidate-{index:02d}.example",
                    source="manual",
                    notes="Project-shaped launch-ready software work.",
                )
                timestamp = f"2026-04-{index + 1:02d}T00:00:00Z"
                repo.conn.execute(
                    "UPDATE targets SET created_at = ?, updated_at = ? WHERE id = ?",
                    (timestamp, timestamp, target_id),
                )
            repo.conn.commit()

            assessed_names: list[str] = []

            def _assess(target, _config, _approach=None, _feedback_context=None):
                assessed_names.append(target.name)
                return AssessmentResult(
                    confidence=0.9,
                    profile_fit="high",
                    activation_signal="explicit",
                    evidence_confidence="strong",
                    freshness="fresh",
                    action_queue="pursue_now",
                    summary_thesis=f"{target.name} looks promising.",
                    fit_rationale="High fit for the configured profile.",
                    activation_rationale="Public signals justify immediate outreach.",
                    outreach_angle="Reach out now.",
                    draft_subject=f"Build help for {target.name}",
                    draft_body="Would love to talk.",
                )

            provider = MagicMock()
            provider.name = "mock"
            provider.assess.side_effect = _assess

            with patch("leadops.daily._provider_for_config", return_value=provider):
                result = run_daily(repo, config, "2026-04-15")

            self.assertEqual(provider.assess.call_count, 20)
            self.assertEqual(assessed_names[0], "Candidate 24")
            self.assertEqual(assessed_names[-1], "Candidate 05")
            self.assertEqual(result.surfaced_new, config.profile.daily_new_lead_cap)

    def test_run_daily_preserves_same_day_packet_versions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)
            repo.add_or_update_target(
                kind="founder",
                name="First Same Day Startup",
                url="https://first-same-day.example",
                source="manual",
                notes="Founder-led prototype with roadmap pressure and no engineering team.",
            )

            first_result = run_daily(repo, config, "2026-04-10")

            repo.add_or_update_target(
                kind="founder",
                name="Second Same Day Startup",
                url="https://second-same-day.example",
                source="manual",
                notes="Founder-led MVP with launch pressure and no visible engineering team.",
            )

            second_result = run_daily(repo, config, "2026-04-10")

            packet_rows = repo.conn.execute(
                "SELECT version, markdown_path, json_path FROM review_packets ORDER BY version ASC"
            ).fetchall()
            self.assertEqual([int(row["version"]) for row in packet_rows], [1, 2])
            self.assertTrue(str(first_result.packet_markdown).endswith("daily-brief.v1.md"))
            self.assertTrue(str(second_result.packet_markdown).endswith("daily-brief.v2.md"))
            self.assertNotEqual(packet_rows[0]["markdown_path"], packet_rows[1]["markdown_path"])
            self.assertIn("First Same Day Startup", Path(packet_rows[0]["json_path"]).read_text(encoding="utf-8"))
            self.assertIn("Second Same Day Startup", Path(packet_rows[1]["json_path"]).read_text(encoding="utf-8"))

            latest_payload = json.loads((workspace / "outbox" / "2026-04-10" / "daily-brief.json").read_text(encoding="utf-8"))
            self.assertEqual(latest_payload["run_context"]["packet_version"], 2)
            self.assertIn("Second Same Day Startup", json.dumps(latest_payload))

    def test_send_email_digest_uses_smtp(self) -> None:
        email_config = EmailConfig(
            mode="smtp",
            host="smtp.example.com",
            port=587,
            username="",
            password_env="LEADOPS_SMTP_PASSWORD",
            from_addr="sender@example.com",
            to_addr="recipient@example.com",
            starttls=True,
            send_on_run=False,
        )

        smtp_instance = MagicMock()
        smtp_cm = MagicMock()
        smtp_cm.__enter__.return_value = smtp_instance
        smtp_cm.__exit__.return_value = None

        with patch("leadops.mailer.smtplib.SMTP", return_value=smtp_cm) as smtp_cls:
            send_email_digest(
                email_config=email_config,
                subject="LeadOps Daily Brief - 2026-04-08 (1 new, 0 follow-ups)",
                body_text="Test digest body",
                body_html="<html><body><p>Test digest body</p></body></html>",
            )

        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=60)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.send_message.assert_called_once()
        sent_message = smtp_instance.send_message.call_args.args[0]
        self.assertTrue(sent_message.is_multipart())
        payload = sent_message.get_payload()
        self.assertEqual(payload[0].get_content_type(), "text/plain")
        self.assertEqual(payload[1].get_content_type(), "text/html")

    def test_render_launchd_plist_contains_daily_wrapper(self) -> None:
        repo_root = Path("/tmp/leadops")
        workspace = Path("/tmp/leadops-workspace")
        program_arguments = build_program_arguments(
            repo_root=repo_root,
            workspace=workspace,
            approach_name="balanced",
            discover_tracks=["daily"],
            discover_per_query_limit=1,
            send_digest=True,
        )
        spec = LaunchdSpec(
            label="com.example.leadops.daily",
            plist_path=Path("/tmp/com.example.leadops.daily.plist"),
            times=((8, 0),),
            program_arguments=program_arguments,
            working_directory=repo_root,
            stdout_path=workspace / "var" / "log" / "launchd.stdout.log",
            stderr_path=workspace / "var" / "log" / "launchd.stderr.log",
        )

        plist_text = render_launchd_plist(spec)

        self.assertIn("com.example.leadops.daily", plist_text)
        self.assertIn("/tmp/leadops/bin/leadops-daily", plist_text)
        self.assertIn("--approach", plist_text)
        self.assertIn("balanced", plist_text)
        self.assertIn("--discover-track", plist_text)
        self.assertIn("--send-digest", plist_text)

    def test_render_launchd_plist_supports_multiple_daily_times(self) -> None:
        repo_root = Path("/tmp/leadops")
        workspace = Path("/tmp/leadops-workspace")
        spec = LaunchdSpec(
            label="com.example.leadops.daily",
            plist_path=Path("/tmp/com.example.leadops.daily.plist"),
            times=((8, 0), (11, 0), (14, 0), (17, 0)),
            program_arguments=build_program_arguments(
                repo_root=repo_root,
                workspace=workspace,
                approach_name=None,
                discover_tracks=[],
                discover_per_query_limit=2,
                send_digest=True,
            ),
            working_directory=repo_root,
            stdout_path=workspace / "var" / "log" / "launchd.stdout.log",
            stderr_path=workspace / "var" / "log" / "launchd.stderr.log",
        )

        plist_text = render_launchd_plist(spec)

        self.assertGreaterEqual(plist_text.count("<key>Hour</key>"), 4)
        self.assertIn("<integer>17</integer>", plist_text)
        self.assertNotIn("--approach", plist_text)

    def test_run_daily_preserves_approach_context_when_provided(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            fake_provider = Path(__file__).with_name("fake_provider.py").resolve()
            config_path = workspace / "leadops.toml"
            config_path.write_text(
                f"""
[profile]
name = "Your Practice"
offer = "Independent product engineer helping founders and very small teams."
daily_new_lead_cap = 5
daily_followup_cap = 5
cooldown_days = 21
hard_rejects = []

[llm]
provider = "command"
command = "python3 {fake_provider}"
timeout_seconds = 30
""".strip()
                + "\n",
                encoding="utf-8",
            )
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)
            repo.add_or_update_target(
                kind="connector",
                name="Design Studio A",
                url="https://design-a.example",
                source="manual",
                notes="Founder-facing product design studio for startup MVP work.",
            )
            repo.add_or_update_target(
                kind="connector",
                name="Design Studio B",
                url="https://design-b.example",
                source="manual",
                notes="Founder-facing design partner for early product teams.",
            )
            repo.add_or_update_target(
                kind="founder",
                name="Builder Need Startup",
                url="https://builder-need.example",
                source="manual",
                notes="Founder-led no-code prototype with waitlist, roadmap pressure, and no visible engineering team.",
            )

            result = run_daily(repo, config, "2026-04-09", approach=get_approach("transition_focus"))

            self.assertEqual(result.surfaced_new, 3)
            payload = json.loads((workspace / "outbox" / "2026-04-09" / "daily-brief.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["run_context"]["approach"]["label"], "Transition Focus")
            surfaced = self._candidate_queue_items(payload)
            self.assertEqual(len(surfaced), 3)
            surfaced_kinds = [item["target"]["kind"] for item in surfaced]
            self.assertEqual(surfaced_kinds.count("founder"), 1)
            self.assertEqual(surfaced_kinds.count("connector"), 2)
            digest_text = (workspace / "outbox" / "2026-04-09" / "daily-digest.txt").read_text(encoding="utf-8")
            digest_html = (workspace / "outbox" / "2026-04-09" / "daily-digest.html").read_text(encoding="utf-8")
            self.assertIn("Run context", digest_text)
            self.assertIn("Transition Focus (transition_focus)", digest_text)
            self.assertIn("Prioritize:", digest_text)
            self.assertIn("Reject:", digest_text)
            self.assertIn("Run Context", digest_html)
            self.assertIn("Transition Focus", digest_html)

    def test_transition_focus_rejects_live_product_without_gap_signal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)
            repo.add_or_update_target(
                kind="founder",
                name="Launched Product Co",
                url="https://launched.example",
                source="manual",
                notes="Founder-led startup with launched product, active users, and customers. Hiring engineers.",
            )

            result = run_daily(repo, config, "2026-04-09", approach=get_approach("transition_focus"))

            self.assertEqual(result.surfaced_new, 0)

    def test_cli_run_daily_uses_no_approach_by_default(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            repo = self._repo_for_workspace(workspace)
            repo.add_or_update_target(
                kind="founder",
                name="Prototype Founder",
                url="https://prototype.example",
                source="manual",
                notes="Founder-led roadmap and prototype with no engineering team and launch pressure.",
            )

            exit_code = cli_main(["run-daily", "--workspace", str(workspace), "--date", "2026-04-09"])

            self.assertEqual(exit_code, 0)
            payload = json.loads((workspace / "outbox" / "2026-04-09" / "daily-brief.json").read_text(encoding="utf-8"))
            self.assertIsNone(payload["run_context"]["approach"])

    def test_cli_requires_existing_workspace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            missing_workspace = Path(tmp) / "missing-workspace"

            with self.assertRaises(SystemExit) as exc:
                cli_main(["list-targets", "--workspace", str(missing_workspace)])

            self.assertIn("Missing workspace config", str(exc.exception))
            self.assertIn("init-workspace", str(exc.exception))

    def test_feedback_context_payload_groups_recent_liked_and_avoided(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)

            liked_id, _ = repo.add_or_update_target(
                kind="founder",
                name="Liked Startup",
                url="https://liked.example",
                source="manual",
                notes="Founder-led prototype with clear build need.",
            )
            avoided_id, _ = repo.add_or_update_target(
                kind="connector",
                name="Avoided Studio",
                url="https://avoided.example",
                source="manual",
                notes="Feels too advisory and not enough build handoff.",
            )

            repo.update_status(liked_id, status="approved", reason="Very close to idea-to-launch work.")
            repo.update_status(avoided_id, status="rejected", reason="Too advisory and not enough product build ownership.")

            payload = repo.feedback_context_payload(limit_per_action=2)

            self.assertEqual(len(payload["liked"]), 1)
            self.assertEqual(len(payload["avoided"]), 1)
            self.assertEqual(payload["liked"][0]["name"], "Liked Startup")
            self.assertEqual(payload["avoided"][0]["name"], "Avoided Studio")
            self.assertIn("idea-to-launch", payload["liked"][0]["reason"])
            self.assertIn("advisory", payload["avoided"][0]["reason"])

    def test_initialize_database_migrates_legacy_assessments_schema(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            db_path = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE targets (
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
                CREATE TABLE daily_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER NOT NULL,
                    run_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    fit_score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    recommend INTEGER NOT NULL,
                    profile_fit TEXT NOT NULL DEFAULT 'unknown',
                    activation_signal TEXT NOT NULL DEFAULT 'unknown',
                    evidence_confidence TEXT NOT NULL DEFAULT 'thin',
                    freshness TEXT NOT NULL DEFAULT 'unknown',
                    action_queue TEXT NOT NULL DEFAULT 'watch',
                    why_fit TEXT NOT NULL,
                    why_now TEXT NOT NULL,
                    summary_thesis TEXT NOT NULL DEFAULT '',
                    outreach_angle TEXT NOT NULL,
                    draft_subject TEXT NOT NULL,
                    draft_body TEXT NOT NULL,
                    signal_tags_json TEXT NOT NULL DEFAULT '[]',
                    risk_tags_json TEXT NOT NULL DEFAULT '[]',
                    unknowns_json TEXT NOT NULL DEFAULT '[]',
                    risks_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    rubric_json TEXT NOT NULL,
                    source_date TEXT,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE review_packets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    packet_date TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    markdown_path TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES daily_runs(id)
                );
                CREATE TABLE review_items (
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
                INSERT INTO targets (
                    id, kind, name, normalized_name, source, dedupe_key, status, created_at, updated_at
                ) VALUES (
                    1, 'founder', 'Legacy Co', 'legacy co', 'manual', 'founder:legacy.example',
                    'candidate', '2026-04-09T00:00:00Z', '2026-04-09T00:00:00Z'
                );
                INSERT INTO daily_runs (id, run_date, started_at, status, notes)
                VALUES (1, '2026-04-09', '2026-04-09T00:00:00Z', 'done', '');
                INSERT INTO review_packets (
                    id, run_id, packet_date, version, markdown_path, json_path, created_at
                ) VALUES (
                    1, 1, '2026-04-09', 1, '/tmp/packet.md', '/tmp/packet.json', '2026-04-09T00:00:00Z'
                );
                INSERT INTO assessments (
                    target_id, run_id, provider, fit_score, confidence, recommend,
                    profile_fit, activation_signal, evidence_confidence, freshness, action_queue,
                    why_fit, why_now, summary_thesis, outreach_angle, draft_subject, draft_body,
                    signal_tags_json, risk_tags_json, unknowns_json, risks_json, evidence_json,
                    rubric_json, source_date, raw_json, created_at
                ) VALUES (
                    1, 1, 'mock', 88.0, 0.9, 1,
                    'high', 'explicit', 'strong', 'fresh', 'pursue_now',
                    'Old fit rationale', 'Old activation rationale', '', 'Angle', 'Subject', 'Body',
                    '["signal"]', '["risk"]', '["budget"]', '["risk"]', '["evidence"]',
                    '{}', '2026-04-09', '{"id":"legacy"}', '2026-04-09T00:00:00Z'
                );
                INSERT INTO review_items (
                    id, packet_id, target_id, assessment_id, section, rank_index, score, confidence, created_at
                ) VALUES (
                    1, 1, 1, 1, 'pursue_now', 1, 88.0, 0.9, '2026-04-09T00:00:00Z'
                );
                """
            )
            conn.commit()
            conn.close()

            initialize_database(db_path)

            migrated = connect(db_path)
            self.addCleanup(migrated.close)
            row = migrated.execute("SELECT * FROM assessments").fetchone()
            columns = [item["name"] for item in migrated.execute("PRAGMA table_info(assessments)").fetchall()]
            review_item = migrated.execute("SELECT * FROM review_items").fetchone()
            review_fk_tables = [item["table"] for item in migrated.execute("PRAGMA foreign_key_list(review_items)").fetchall()]

            self.assertNotIn("fit_score", columns)
            self.assertEqual(row["fit_rationale"], "Old fit rationale")
            self.assertEqual(row["activation_rationale"], "Old activation rationale")
            self.assertEqual(row["risk_tags_json"], '["risk"]')
            self.assertEqual(review_item["assessment_id"], 1)
            self.assertIn("assessments", review_fk_tables)
            self.assertNotIn("assessments_legacy", review_fk_tables)

    def test_command_provider_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            fake_provider = Path(__file__).with_name("fake_provider.py").resolve()
            config_path = workspace / "leadops.toml"
            config_path.write_text(
                f"""
[profile]
name = "Your Practice"
offer = "Independent product engineer helping founders and very small teams."
daily_new_lead_cap = 5
daily_followup_cap = 5
cooldown_days = 21
hard_rejects = []

[llm]
provider = "command"
command = "python3 {fake_provider}"
timeout_seconds = 30
""".strip()
                + "\n",
                encoding="utf-8",
            )
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)
            repo.add_or_update_target(
                kind="founder",
                name="Command Provider Startup",
                url="https://example.net",
                source="manual",
                notes="Founder-led startup with prototype work.",
            )

            result = run_daily(repo, config, "2026-04-08")
            self.assertEqual(result.surfaced_new, 1)
            payload = (workspace / "outbox" / "2026-04-08" / "daily-brief.json").read_text(encoding="utf-8")
            self.assertIn("Command Provider Startup", payload)

    def test_discover_web_ingests_candidates_and_tracks_query_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            fake_discovery_provider = Path(__file__).with_name("fake_discovery_provider.py").resolve()
            config_path = workspace / "leadops.toml"
            config_path.write_text(
                f"""
[profile]
name = "Your Practice"
offer = "Independent product engineer helping founders and very small teams."
daily_new_lead_cap = 5
daily_followup_cap = 5
cooldown_days = 21
hard_rejects = []

[llm]
provider = "mock"
timeout_seconds = 30

[discovery]
provider = "command"
command = "python3 {fake_discovery_provider}"
timeout_seconds = 30
""".strip()
                + "\n",
                encoding="utf-8",
            )
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)

            result = discover_web(
                repo,
                config,
                query="founder prototype launch-ready web app",
                kind="founder",
                limit=3,
                source="web-discovery",
            )

            self.assertEqual(result.total_candidates, 1)
            self.assertEqual(result.created, 1)

            targets = repo.list_targets()
            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].name, "Proto Foundry")
            self.assertIn("Sources:", targets[0].raw_evidence)

            conn = connect(config.database_path)
            self.addCleanup(conn.close)
            query_runs = conn.execute("SELECT COUNT(*) AS count FROM query_runs").fetchone()
            query_run_targets = conn.execute("SELECT COUNT(*) AS count FROM query_run_targets").fetchone()
            self.assertEqual(int(query_runs["count"]), 1)
            self.assertEqual(int(query_run_targets["count"]), 1)

    def test_discover_track_runs_multiple_queries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            fake_discovery_provider = Path(__file__).with_name("fake_discovery_provider.py").resolve()
            config_path = workspace / "leadops.toml"
            config_path.write_text(
                f"""
[profile]
name = "Your Practice"
offer = "Independent product engineer helping founders and very small teams."
daily_new_lead_cap = 5
daily_followup_cap = 5
cooldown_days = 21
hard_rejects = []

[llm]
provider = "mock"
timeout_seconds = 30

[discovery]
provider = "command"
command = "python3 {fake_discovery_provider}"
timeout_seconds = 30
""".strip()
                + "\n",
                encoding="utf-8",
            )
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)

            result = discover_track(
                repo,
                config,
                track=get_track("daily"),
                limit_override=1,
                source_prefix="test-discovery",
            )

            self.assertEqual(result.track_name, "daily")
            self.assertEqual(len(result.results), 3)
            self.assertEqual(result.total_candidates, 3)
            self.assertEqual(result.total_created, 2)
            self.assertEqual(result.total_updated, 1)

    def test_discover_web_caps_provider_results_to_requested_limit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            config_path = workspace / "leadops.toml"
            config_path.write_text(
                """
[profile]
name = "Your Practice"
offer = "Independent product engineer helping founders and very small teams."
daily_new_lead_cap = 5
daily_followup_cap = 5
cooldown_days = 21
hard_rejects = []

[llm]
provider = "mock"
timeout_seconds = 30

[discovery]
provider = "command"
command = "ignored"
timeout_seconds = 30
""".strip()
                + "\n",
                encoding="utf-8",
            )
            config = load_workspace_config(workspace)
            repo = self._repo_for_workspace(workspace)
            batch = DiscoveryBatch(
                candidates=[
                    DiscoveryCandidate(
                        name="Candidate One",
                        url="https://candidate-one.example",
                        confidence=0.9,
                        profile_fit="high",
                        activation_signal="explicit",
                        evidence_confidence="strong",
                        freshness="fresh",
                        summary_thesis="Strong candidate one.",
                        fit_rationale="Strong fit one.",
                        activation_rationale="Strong signal one.",
                    ),
                    DiscoveryCandidate(
                        name="Candidate Two",
                        url="https://candidate-two.example",
                        confidence=0.8,
                        profile_fit="medium",
                        activation_signal="inferred",
                        evidence_confidence="moderate",
                        freshness="unknown",
                        summary_thesis="Strong candidate two.",
                        fit_rationale="Strong fit two.",
                        activation_rationale="Strong signal two.",
                    ),
                ],
                raw_response={"id": "fake-over-limit"},
            )

            with patch("leadops.discovery._discover_with_command", return_value=batch):
                result = discover_web(
                    repo,
                    config,
                    query="founder prototype launch-ready web app",
                    kind="founder",
                    limit=1,
                    source="web-discovery",
                )

            self.assertEqual(result.total_candidates, 1)
            self.assertEqual(result.created, 1)
            self.assertEqual(len(repo.list_targets()), 1)
            query_row = repo.conn.execute("SELECT notes FROM query_runs ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIn("truncated=true", str(query_row["notes"]))

    def test_candidate_snooze_hides_until_due_date(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leadops-tests.") as tmp:
            workspace = initialize_workspace(Path(tmp))
            repo = self._repo_for_workspace(workspace)
            config = load_workspace_config(workspace)

            target_id, _ = repo.add_or_update_target(
                kind="founder",
                name="Snoozed Candidate",
                url="https://example.com/waitlist",
                source="manual",
                notes="Founder-led prototype with roadmap pressure, no engineering team, and clear early-stage build work.",
            )
            repo.update_status(
                target_id,
                status="candidate",
                followup_date="2026-04-10",
                reason="Snoozed until tomorrow.",
            )

            hidden_result = run_daily(repo, config, "2026-04-09")
            self.assertEqual(hidden_result.surfaced_new, 0)

            visible_result = run_daily(repo, config, "2026-04-10")
            self.assertEqual(visible_result.surfaced_new, 1)


if __name__ == "__main__":
    unittest.main()

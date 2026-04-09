from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from leadops.config import EmailConfig, initialize_workspace, load_workspace_config
from leadops.daily import run_daily
from leadops.db import connect, initialize_database
from leadops.discovery import discover_track, discover_web
from leadops.extract import extract_from_html
from leadops.mailer import send_email_digest
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

    def test_dedupe_prefers_domain(self) -> None:
        self.assertEqual(dedupe_key("founder", "Example", "https://www.example.com/app"), "founder:example.com")

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
                notes="Founder-led startup with beta product and early launch needs.",
            )

            result = run_daily(repo, config, "2026-04-08")
            self.assertTrue(result.packet_markdown.exists())
            self.assertTrue(result.packet_json.exists())
            self.assertTrue(result.digest_text.exists())
            self.assertGreaterEqual(result.surfaced_new, 1)
            digest_body = result.digest_text.read_text(encoding="utf-8")
            self.assertIn("LeadOps Daily Brief - 2026-04-08", digest_body)

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
                body="Test digest body",
            )

        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=60)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.send_message.assert_called_once()

    def test_render_launchd_plist_contains_daily_wrapper(self) -> None:
        repo_root = Path("/tmp/leadops")
        workspace = Path("/tmp/leadops-workspace")
        program_arguments = build_program_arguments(
            repo_root=repo_root,
            workspace=workspace,
            discover_tracks=["daily"],
            discover_per_query_limit=1,
            send_digest=True,
        )
        spec = LaunchdSpec(
            label="com.example.leadops.daily",
            plist_path=Path("/tmp/com.example.leadops.daily.plist"),
            hour=8,
            minute=0,
            program_arguments=program_arguments,
            working_directory=repo_root,
            stdout_path=workspace / "var" / "log" / "launchd.stdout.log",
            stderr_path=workspace / "var" / "log" / "launchd.stderr.log",
        )

        plist_text = render_launchd_plist(spec)

        self.assertIn("com.example.leadops.daily", plist_text)
        self.assertIn("/tmp/leadops/bin/leadops-daily", plist_text)
        self.assertIn("--discover-track", plist_text)
        self.assertIn("--send-digest", plist_text)

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
                notes="Founder-led beta product with clear early-stage build work.",
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

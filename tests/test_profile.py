"""Offline tests for the profile activity renderer."""

import sys
from pathlib import Path
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_profile import render_activity, replace_section, safe_title


class ProfileActivityTests(unittest.TestCase):
    def test_only_explicit_section_changes(self):
        initial = "Intro\n<!-- profile-activity:start -->\nold\n<!-- profile-activity:end -->\nEnd"
        updated = replace_section(initial, "new")
        self.assertEqual(
            updated,
            "Intro\n<!-- profile-activity:start -->\nnew\n<!-- profile-activity:end -->\nEnd",
        )

    def test_rejects_missing_markers(self):
        with self.assertRaises(ValueError):
            replace_section("No markers here", "data")

    def test_render_counts_only_passed_public_data(self):
        now = datetime(2026, 11, 7, tzinfo=timezone.utc)
        releases = [
            ("AaronPG095/FluentTimer", {
                "tag_name": "v1.2.0",
                "published_at": "2026-11-01T10:00:00Z",
                "prerelease": False,
            })
        ]
        prs = [
            ("AaronPG095/FluentTimer", {
                "state": "closed",
                "merged_at": "2026-11-02T10:00:00Z",
                "updated_at": "2026-11-02T10:00:00Z",
                "title": "feat: add tray shortcuts",
                "number": 42,
            }),
            ("AaronPG095/FluentTimer", {
                "state": "open",
                "updated_at": "2026-11-03T10:00:00Z",
                "title": "Sync token-lean pack and review workflow from AI-Dev-Workflow",
                "number": 43,
            }),
            ("AaronPG095/FluentTimer", {
                "state": "closed",
                "merged_at": "2026-11-04T10:00:00Z",
                "updated_at": "2026-11-04T10:00:00Z",
                "title": "Plan - Process: AI Dev Workflow rollout",
                "number": 44,
            }),
        ]
        output = render_activity(
            ["AaronPG095/FluentTimer"], releases, prs, now
        )
        self.assertIn("**1** | **1** | **3**", output)
        self.assertIn("FluentTimer v1.2.0", output)
        self.assertIn("FluentTimer: Add tray shortcuts", output)
        self.assertNotIn("Sync token-lean", output)
        self.assertNotIn("AI Dev Workflow rollout", output)

    def test_preserve_telemetry_keeps_svg_without_metrics(self):
        output = render_activity(["AaronPG095/FluentTimer"], [], [], preserve_telemetry=True)
        self.assertIn("assets/github-stats.svg", output)
        self.assertNotIn("Public repositories | Published releases", output)

    def test_recent_prs_prefers_repo_diversity_before_repeating(self):
        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        prs = [
            ("AaronPG095/AI-Dev-Workflow", {
                "state": "closed",
                "merged_at": "2026-11-13T10:00:00Z",
                "updated_at": "2026-11-13T10:00:00Z",
                "title": "Plan - Feature: Supervisor",
                "number": 25,
            }),
            ("AaronPG095/AI-Dev-Workflow", {
                "state": "closed",
                "merged_at": "2026-11-12T10:00:00Z",
                "updated_at": "2026-11-12T10:00:00Z",
                "title": "Plan - Feature: Waves",
                "number": 24,
            }),
            ("AaronPG095/FluentTimer", {
                "state": "closed",
                "merged_at": "2026-11-07T10:00:00Z",
                "updated_at": "2026-11-07T10:00:00Z",
                "title": "feat: multi-timer pill rows",
                "number": 6,
            }),
            ("AaronPG095/TokenHUD", {
                "state": "closed",
                "merged_at": "2026-10-31T10:00:00Z",
                "updated_at": "2026-10-31T10:00:00Z",
                "title": "Shared AI development process",
                "number": 1,
            }),
        ]
        output = render_activity(
            ["AaronPG095/AI-Dev-Workflow", "AaronPG095/FluentTimer", "AaronPG095/TokenHUD"],
            [],
            prs,
            now,
        )
        self.assertIn("AI-Dev-Workflow: Supervisor", output)
        self.assertNotIn("AI-Dev-Workflow: Waves", output)
        self.assertIn("FluentTimer: Multi-timer pill rows", output)
        self.assertIn("TokenHUD: Shared AI development process", output)

    def test_safe_title_escapes_markdown_and_strips_prefixes(self):
        title = safe_title("Fix [link](target) and markup")
        self.assertNotIn("[link](target)", title)
        self.assertIn("Fix", title)
        self.assertEqual(
            safe_title("Plan - Feature: Agentic Outer-Loop Supervisor"),
            "Agentic Outer-Loop Supervisor",
        )


class DashboardTests(unittest.TestCase):
    def test_combined_daily_counts_use_utc_and_count_overlap_once(self):
        from datetime import date
        from unittest.mock import patch
        from update_profile import combined_commit_days

        today = date(2026, 11, 7)
        response = {"total_count": 1, "incomplete_results": False, "items": [
            {"commit": {"author": {"date": "2026-11-08T01:00:00+02:00"}}},
        ]}
        with patch("update_profile.api_json", return_value=response) as api, patch("update_profile.sleep"):
            counts = combined_commit_days(today, "test-token")
        self.assertEqual(counts[today], 1)
        self.assertEqual(sum(counts.values()), 1)
        self.assertEqual(api.call_args.kwargs["token"], "test-token")

    def test_streak_stays_current_through_a_quiet_today(self):
        from datetime import date, timedelta
        from github_metrics import streaks

        today = date(2026, 11, 7)
        daily = {today - timedelta(days=i): count for i, count in enumerate([0, 2, 1, 0, 5])}
        self.assertEqual(streaks(daily, today), (2, 2))

    def test_stats_svg_renders_telemetry_cards_and_singular_tooltip(self):
        from datetime import date
        from github_metrics import metrics_from_data, stats_svg

        today = date(2026, 11, 13)
        daily = {today: 1}
        metrics = metrics_from_data(
            {"commits": 2650, "pull_requests": 160, "issues": 0},
            daily,
            repos=38,
            releases=14,
            today=today,
        )
        svg = stats_svg(metrics)
        self.assertIn("Development telemetry", svg)
        self.assertIn("2,650", svg)
        self.assertIn("160", svg)
        self.assertIn("14", svg)
        self.assertIn("1 commit</title>", svg)
        self.assertNotIn("1 commits</title>", svg)


if __name__ == "__main__":
    unittest.main()

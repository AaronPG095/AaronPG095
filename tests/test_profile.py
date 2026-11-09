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
        ]
        output = render_activity(
            ["AaronPG095/FluentTimer"], releases, prs, now
        )
        self.assertIn("**1** | **1** | **2**", output)
        self.assertIn("FluentTimer v1.2.0", output)
        self.assertIn("FluentTimer: Add tray shortcuts", output)
        self.assertNotIn("Sync token-lean", output)

    def test_safe_title_escapes_markdown(self):
        title = safe_title("Fix [link](target) and markup")
        self.assertNotIn("[link](target)", title)
        self.assertIn("Fix", title)


class DashboardTests(unittest.TestCase):
    def test_combined_daily_counts_use_utc_and_count_overlap_once(self):
        from datetime import date
        from unittest.mock import patch
        from update_profile import combined_commit_days

        today = date(2026, 11, 7)
        response = {"total_count": 1, "incomplete_results": False, "items": [
            {"commit": {"author": {"date": "2026-11-08T01:00:00+02:00"}}},
        ]}
        with patch("update_profile.api_json", return_value=response) as api:
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


if __name__ == "__main__":
    unittest.main()

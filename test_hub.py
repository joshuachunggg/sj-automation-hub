import unittest
from types import SimpleNamespace
from unittest.mock import patch

import hub


class HubCommandTest(unittest.TestCase):
    def test_login_uses_shared_firefox_profile(self):
        args = hub.command("login", {})
        self.assertEqual(args[1].split("/")[-1], "auth_login.py")
        self.assertEqual(args[-1], str(hub.PROFILE))

    def test_publish_has_no_browser_or_login_arguments(self):
        args = hub.command("publish", {"workbook": "workbook.xlsx", "workers": 3, "mode": "publish"})
        self.assertNotIn("--browser", args)
        self.assertNotIn("auth_login.py", " ".join(args))

    def test_publish_passes_country_codes_to_skip(self):
        args = hub.command("publish", {"workbook": "workbook.xlsx", "skip_countries": "uk, ca"})
        self.assertEqual(args[args.index("--skip-country") + 1], "uk, ca")

    def test_qa_uses_firefox_profile(self):
        args = hub.command("qa", {"workbook": "workbook.xlsx", "mode": "plan"})
        self.assertIn("firefox", args)
        self.assertEqual(args[args.index("--user-data-dir") + 1], str(hub.PROFILE))

    def test_qa_retry_only_runs_failed_child_copies(self):
        self.assertIn("--retry-failed", hub.command("qa", {"workbook": "workbook.xlsx", "mode": "retry"}))

    def test_macos_picker_returns_selected_workbook(self):
        with patch("hub.platform.system", return_value="Darwin"), patch.object(
            hub.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="/tmp/workbook.xlsx\n")
        ):
            self.assertEqual(hub.pick_workbook(), "/tmp/workbook.xlsx")

    def test_dashboard_tracks_workers_and_countries(self):
        view = hub.dashboard('\n'.join((
            'UI {"kind":"publish","event":"start","total":2,"locales":["uk","ca"]}',
            'UI {"kind":"publish","event":"worker","slot":1,"site":"uk","status":"checking live"}',
            'UI {"kind":"publish","event":"locale","site":"uk","status":"live"}',
        )))
        self.assertEqual(view["workers"]["1"]["site"], "uk")
        self.assertEqual(view["locales"]["uk"]["status"], "live")

    def test_dashboard_marks_skipped_countries_as_not_processed(self):
        view = hub.dashboard('UI {"kind":"publish","event":"start","total":1,"locales":["sg"],"skipped":["uk"]}')
        self.assertEqual(view["locales"]["uk"]["status"], "skipped — not processed")

    def test_dashboard_keeps_pending_qa_findings_current(self):
        view = hub.dashboard('UI {"kind":"qa","event":"parent","site":"uk","status":"pending","findings":["different punctuation"]}')
        self.assertEqual(view["current"]["status"], "pending")
        self.assertEqual(view["current"]["findings"], ["different punctuation"])

    def test_dashboard_keeps_copy_error_detail(self):
        view = hub.dashboard('UI {"kind":"qa","event":"child","site":"ca","status":"error","error":"SIM rejected copy"}')
        self.assertEqual(view["children"]["ca"]["error"], "SIM rejected copy")


if __name__ == "__main__":
    unittest.main()

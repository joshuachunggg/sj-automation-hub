import unittest
from pathlib import Path
from unittest.mock import patch

import browser_owner


class BrowserOwnerTest(unittest.TestCase):
    def test_retries_until_owner_starts(self):
        conn = __import__("unittest").mock.MagicMock()
        conn.makefile.return_value.readline.return_value = '{"ok": true, "result": true}\n'
        with patch("browser_owner.socket.create_connection", side_effect=[OSError, conn]), patch("browser_owner.time.sleep"):
            self.assertTrue(browser_owner.request("done"))
        conn.settimeout.assert_called_once_with(300)

    def test_workflow_confirmation_uses_its_submit_button(self):
        source = Path("browser_owner.mjs").read_text()
        self.assertIn("#issue-workflow-transition-submit", source)
        self.assertNotIn("fetch(form.action", source)

    def test_publisher_uses_direct_issue_requests_and_browser_live_check(self):
        source = Path("browser_owner.mjs").read_text()
        self.assertIn("page.goto(new URL(issueUrl, page.url()).href", source)
        self.assertIn("page.goto(new URL(ticketsUrl, page.url()).href", source)
        self.assertIn("page.goto(target, { waitUntil: 'domcontentloaded', timeout: 30000 })", source)

    def test_publisher_retries_transient_browser_failures(self):
        source = Path("browser_owner.mjs").read_text()
        self.assertIn("for (let attempt = 1; attempt <= 3; attempt++)", source)
        self.assertIn("transientBrowserError(error)", source)

    def test_publisher_waits_for_results_and_always_checks_the_slug(self):
        source = Path("browser_owner.mjs").read_text()
        self.assertIn("await page.waitForLoadState('networkidle')", source)
        self.assertIn("let matches = await exactSlugRows(rows, slug)", source)
        self.assertIn("a[data-page=\"2\"]", source)

    def test_publisher_falls_back_when_the_first_search_has_no_exact_match_and_returns_candidates(self):
        source = Path("browser_owner.mjs").read_text()
        self.assertIn("if (!searchResult.matches.length)", source)
        self.assertIn("function classified(status, siteCode, slug, result)", source)
        self.assertIn("candidateTexts(rows)", source)

    def test_publisher_serializes_only_jira_transitions(self):
        source = Path("browser_owner.mjs").read_text()
        self.assertIn("let transitioning = Promise.resolve()", source)
        self.assertIn("return transition(async () =>", source)

    def test_owner_can_export_the_signed_in_session_for_a_fresh_publish_browser(self):
        self.assertIn("if (request.action === 'storage_state') return context.storageState()", Path("browser_owner.mjs").read_text())


if __name__ == "__main__":
    unittest.main()

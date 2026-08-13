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
        self.assertIn("fetch(form.action", source)

    def test_publisher_clicks_do_not_wait_for_navigation(self):
        self.assertIn("locator.click({ noWaitAfter: true })", Path("browser_owner.mjs").read_text())

    def test_publisher_retries_transient_browser_failures(self):
        source = Path("browser_owner.mjs").read_text()
        self.assertIn("for (let attempt = 1; attempt <= 3; attempt++)", source)
        self.assertIn("transientBrowserError(error)", source)


if __name__ == "__main__":
    unittest.main()

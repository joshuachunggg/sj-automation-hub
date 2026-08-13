import unittest
from unittest.mock import patch

import browser_owner


class BrowserOwnerTest(unittest.TestCase):
    def test_retries_until_owner_starts(self):
        conn = __import__("unittest").mock.MagicMock()
        conn.makefile.return_value.readline.return_value = '{"ok": true, "result": true}\n'
        with patch("browser_owner.socket.create_connection", side_effect=[OSError, conn]), patch("browser_owner.time.sleep"):
            self.assertTrue(browser_owner.request("done"))


if __name__ == "__main__":
    unittest.main()

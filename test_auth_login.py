import os
import unittest
from unittest.mock import MagicMock, patch

import auth_login


class AuthLoginTest(unittest.TestCase):
    def test_env_prefers_process_environment(self):
        with patch.dict(os.environ, {"WMC_USERNAME": "from-process"}):
            self.assertEqual(auth_login.env("WMC_USERNAME"), "from-process")

    def test_existing_session_skips_credential_entry(self):
        page = MagicMock()
        support = page.get_by_role.return_value.first
        self.assertIs(auth_login.wait_for_support(page), support)
        page.locator.assert_not_called()


if __name__ == "__main__":
    unittest.main()

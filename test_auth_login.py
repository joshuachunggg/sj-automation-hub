import unittest
from unittest.mock import call, patch

import auth_login


class AuthLoginTest(unittest.TestCase):
    def test_login_uses_shared_browser_owner(self):
        with patch("auth_login.request", return_value="WMC home ready") as request, patch("builtins.input", return_value=""):
            auth_login.main()
        self.assertEqual([item.args[0] for item in request.call_args_list], ["login", "done"])


if __name__ == "__main__":
    unittest.main()

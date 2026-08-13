import os
import unittest
from unittest.mock import MagicMock, call, patch

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

    def test_missing_close_button_does_not_skip_login(self):
        page = MagicMock()
        support = page.get_by_role.return_value.first
        support.wait_for.side_effect = [auth_login.TimeoutError("x"), None]
        email = page.get_by_role.return_value
        email.wait_for.return_value = None
        page.locator.return_value.filter.return_value.nth.return_value.click.side_effect = auth_login.TimeoutError("x")
        self.assertIs(auth_login.wait_for_support(page), support)
        self.assertTrue(page.get_by_role.return_value.get_by_role.return_value.click.called)

    def test_opens_all_recorded_support_servers(self):
        context, page, support, popup = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        support.count.return_value = 4
        context.expect_page.return_value.__enter__.return_value.value = popup
        auth_login.open_support_servers(context, page, support)
        self.assertEqual([item.args[0] for item in support.nth.call_args_list], [0, 2, 3])
        self.assertEqual(popup.wait_for_load_state.call_count, 3)
        self.assertEqual(popup.close.call_count, 3)


if __name__ == "__main__":
    unittest.main()

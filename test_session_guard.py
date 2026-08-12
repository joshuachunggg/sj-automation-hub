import unittest

from session_guard import dismiss_jira_notice


class NoticeDismissalTest(unittest.IsolatedAsyncioTestCase):
    async def test_clicks_hide_today_notice(self):
        class Overlay:
            async def wait_for(self, state, timeout):
                return None

        class Page:
            clicked = False

            async def evaluate(self, script):
                self.clicked = True
                return True

            def locator(self, selector):
                return Overlay()

        page = Page()
        self.assertTrue(await dismiss_jira_notice(page))
        self.assertTrue(page.clicked)


if __name__ == "__main__":
    unittest.main()


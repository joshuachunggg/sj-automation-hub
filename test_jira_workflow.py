import inspect
import unittest

from jira_workflow import _has_exact_slug, _is_in_production, _status_is_live


class ExactSlugTest(unittest.TestCase):
    def test_rejects_similar_urls(self):
        slug = "samsung-galaxy-device-appears-to-be-slow-or-unresponsive"
        self.assertTrue(_has_exact_slug(f"[se] {slug}", slug))
        self.assertFalse(_has_exact_slug(f"[se] {slug}-after-update", slug))
        self.assertFalse(_has_exact_slug(f"[se] fix-{slug}", slug))

    def test_workflow_uses_direct_navigation_and_a_transition_lock(self):
        from jira_workflow import process_column
        source = inspect.getsource(process_column)
        self.assertIn("tickets_url = await tickets.get_attribute", source)
        self.assertIn("issue_url = await ticket.get_attribute", source)
        self.assertIn("async with transition_lock:", source)


class ProductionStateTest(unittest.IsolatedAsyncioTestCase):
    async def test_detects_live_from_the_transition_button(self):
        class Dropdown:
            async def is_visible(self): return True
            async def inner_text(self): return "LIVE"

        class Page:
            def locator(self, selector):
                self.selector = selector
                return Dropdown()

        page = Page()
        self.assertTrue(await _status_is_live(page))
        self.assertEqual(page.selector, "#opsbar-transitions_more")

    async def test_detects_production_dropdown(self):
        class Dropdown:
            def filter(self, has_text):
                return self

            async def wait_for(self, state, timeout):
                return None

        class Page:
            def locator(self, selector):
                return Dropdown()

        page = Page()
        self.assertTrue(await _is_in_production(page))


if __name__ == "__main__":
    unittest.main()

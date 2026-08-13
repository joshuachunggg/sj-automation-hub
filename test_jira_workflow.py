import inspect
import unittest

from jira_workflow import _has_exact_slug, _is_in_production, _status_is_live, _workflow_state


class ExactSlugTest(unittest.TestCase):
    def test_rejects_similar_urls(self):
        slug = "samsung-galaxy-device-appears-to-be-slow-or-unresponsive"
        self.assertTrue(_has_exact_slug(f"[se] {slug}", slug))
        self.assertFalse(_has_exact_slug(f"[se] {slug}-after-update", slug))
        self.assertFalse(_has_exact_slug(f"[se] fix-{slug}", slug))

    def test_workflow_uses_direct_navigation_without_waiting_for_other_workers(self):
        from jira_workflow import process_column
        source = inspect.getsource(process_column)
        self.assertIn("tickets_url = await tickets.get_attribute", source)
        self.assertIn("issue_url = await ticket.get_attribute", source)
        self.assertNotIn("async with _transition_lock:", source)
        self.assertNotIn("await search_box.click()", source)
        self.assertIn('page.locator("a.issue-link")', inspect.getsource(__import__("jira_workflow")._find_ticket_link))


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

    async def test_detects_new_request_without_waiting_for_production(self):
        class Dropdown:
            async def is_visible(self): return True
            async def inner_text(self): return "New Request"

        class Page:
            def locator(self, selector): return Dropdown()

        self.assertEqual(await _workflow_state(Page()), "NEW REQUEST")

    async def test_detects_production_dropdown(self):
        class Dropdown:
            async def is_visible(self): return True
            async def inner_text(self): return "PRODUCTION"

        class Page:
            def locator(self, selector):
                return Dropdown()

        page = Page()
        self.assertTrue(await _is_in_production(page))


if __name__ == "__main__":
    unittest.main()

import unittest

from jira_workflow import _has_exact_slug, _is_in_production


class ExactSlugTest(unittest.TestCase):
    def test_rejects_similar_urls(self):
        slug = "samsung-galaxy-device-appears-to-be-slow-or-unresponsive"
        self.assertTrue(_has_exact_slug(f"[se] {slug}", slug))
        self.assertFalse(_has_exact_slug(f"[se] {slug}-after-update", slug))
        self.assertFalse(_has_exact_slug(f"[se] fix-{slug}", slug))


class ProductionStateTest(unittest.IsolatedAsyncioTestCase):
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


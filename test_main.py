import asyncio
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main
from main import LiveMonitor


class LiveMonitorTest(unittest.TestCase):
    def test_releases_worker_slot(self):
        log = io.StringIO()
        monitor = LiveMonitor(2, log)
        slot = monitor.claim(SimpleNamespace(sheet_name="Europe", col_idx=22, site_code="se"))
        monitor.status(slot, "se: searching Jira")
        monitor.release(slot)
        self.assertEqual(monitor.slots, ["idle", "idle"])

    def test_live_check_saves_before_returning(self):
        class Monitor:
            def claim(self, col): return 0
            def release(self, slot): pass
            def status(self, slot, status): pass
            def log(self, message): pass

        col = SimpleNamespace(sheet_name="Europe", col_idx=22, site_code="se", editor_url="https://example.test/editor.html/content/samsung/se/page")
        with patch.object(main, "FILE_PATH", "test.xlsx", create=True), \
             patch.object(main, "check_live_async", AsyncMock(return_value=True)), \
             patch.object(main, "write_live_url") as write:
            result = asyncio.run(main._wait_for_live(None, col, asyncio.Semaphore(1), Monitor(), object()))
        self.assertTrue(result[2])
        write.assert_called_once()


if __name__ == "__main__":
    unittest.main()

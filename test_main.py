import asyncio
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main
from main import LiveMonitor
from openpyxl import Workbook
from sheet_io import find_columns


class LiveMonitorTest(unittest.TestCase):
    def test_open_tab_reuses_firefox_start_tab(self):
        blank = SimpleNamespace(url="about:blank")
        context = SimpleNamespace(pages=[blank])
        self.assertIs(asyncio.run(main._open_tab(context)), blank)

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

    def test_validate_all_includes_existing_live_urls(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Global"
        ws.cell(2, 2, "samsung.com/sg/page")
        ws.cell(3, 2, "https://example.test/editor.html/content/samsung/sg/page")
        ws.cell(8, 2, "sg")
        ws.cell(13, 2, "page")
        self.assertEqual([c.site_code for c in find_columns(wb, pending_only=False)], ["sg"])

    def test_validation_uses_parallel_workers(self):
        class Monitor:
            def __init__(self): self.slot = 0
            def claim(self, col): self.slot += 1; return self.slot
            def release(self, slot): pass
            def status(self, slot, status): pass

        active = peak = 0
        async def check(context, url, timeout):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1
            return True

        columns = [SimpleNamespace(sheet_name="Global", col_idx=i, site_code=str(i), editor_url=f"https://example.test/editor.html/content/samsung/{i}/page") for i in (2, 3)]
        with patch.object(main, "FILE_PATH", "test.xlsx", create=True), \
             patch.object(main, "check_live_async", check), \
             patch.object(main, "write_live_url"):
            async def run():
                semaphore = asyncio.Semaphore(2)
                await asyncio.gather(*(main._validate_one(None, col, semaphore, Monitor(), object(), lambda _: None) for col in columns))
            asyncio.run(run())
        self.assertEqual(peak, 2)


if __name__ == "__main__":
    unittest.main()

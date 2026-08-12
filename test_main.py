import io
import unittest
from types import SimpleNamespace

from main import LiveMonitor


class LiveMonitorTest(unittest.TestCase):
    def test_releases_worker_slot(self):
        log = io.StringIO()
        monitor = LiveMonitor(2, log)
        slot = monitor.claim(SimpleNamespace(sheet_name="Europe", col_idx=22, site_code="se"))
        monitor.status(slot, "se: searching Jira")
        monitor.release(slot)
        self.assertEqual(monitor.slots, ["idle", "idle"])
        self.assertIn("PROGRESS\t1", log.getvalue())


if __name__ == "__main__":
    unittest.main()

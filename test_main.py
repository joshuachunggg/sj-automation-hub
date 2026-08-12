import io
import unittest
from types import SimpleNamespace

from main import LiveMonitor


class LiveMonitorTest(unittest.TestCase):
    def test_releases_worker_slot(self):
        monitor = LiveMonitor(2, io.StringIO())
        slot = monitor.claim(SimpleNamespace(site_code="se"))
        monitor.status(slot, "se: searching Jira")
        monitor.release(slot)
        self.assertEqual(monitor.slots, ["idle", "idle"])


if __name__ == "__main__":
    unittest.main()


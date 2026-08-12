import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hub


class DotenvTest(unittest.TestCase):
    def test_load_env_reads_values_without_exporting_them(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("# local only\nWMC_USERNAME=user@example.com\nWMC_PASSWORD=secret\n")
            with patch.object(hub, "ENV_FILE", env_file):
                self.assertEqual(
                    hub.load_env(),
                    {"WMC_USERNAME": "user@example.com", "WMC_PASSWORD": "secret"},
                )


if __name__ == "__main__":
    unittest.main()

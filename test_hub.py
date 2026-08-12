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

    def test_chrome_launches_its_binary_with_a_fresh_window(self):
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        with patch.object(hub, "chrome_command", return_value=chrome), \
             patch.object(hub.subprocess, "Popen") as popen:
            self.assertTrue(hub.launch_dev_chrome())
        self.assertEqual(popen.call_args.args[0][:2], [chrome, "--new-window"])

    def test_macos_chrome_activation_targets_chrome(self):
        with patch.object(hub.platform, "system", return_value="Darwin"), \
             patch.object(hub.subprocess, "run") as run:
            hub.activate_dev_chrome()
        self.assertEqual(run.call_args.args[0][:2], ["osascript", "-e"])

    def test_faq_login_returns_directly_to_qa_after_success(self):
        with patch.object(hub, "use_existing_dev_chrome", return_value=False), \
             patch.object(hub, "dev_chrome_ready", return_value=True), \
             patch.object(hub, "run_logged", return_value=True) as run:
            with patch.object(hub, "load_env", return_value={"WMC_LOGIN_URL": "url", "WMC_USERNAME": "user", "WMC_PASSWORD": "pass"}):
                self.assertTrue(hub.ensure_faq_chrome())
        self.assertTrue(run.call_args.kwargs["return_on_success"])

    def test_existing_dev_chrome_skips_wmc_login(self):
        with patch.object(hub, "use_existing_dev_chrome", return_value=True), \
             patch.object(hub, "run_logged") as run:
            self.assertTrue(hub.ensure_faq_chrome())
        run.assert_not_called()

    def test_process_screen_returns_handoff_success(self):
        class Process:
            def terminate(self):
                pass

        with patch.object(hub.curses, "wrapper", return_value=True):
            self.assertTrue(hub.wait_process("WMC", Process(), Path("/tmp/no-log"), return_on_success=True))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from io import StringIO
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

    def test_jira_login_starts_browser_before_showing_login_screen(self):
        class Process:
            stdin = StringIO()

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(hub, "LOG_DIR", Path(directory)), \
                 patch.object(hub.subprocess, "Popen", return_value=Process()) as popen, \
                 patch.object(hub, "panel", side_effect=lambda *args, **kwargs: bool(popen.called)), \
                 patch.object(hub, "wait_process"):
                hub.jira_login()
        self.assertTrue(popen.called)

    def test_publishing_status_tracks_agents_and_locales(self):
        workers, agents, locales = hub.publishing_status([
            "PUBLISHING WORKERS\t2",
            "PROGRESS\t1\tGlobal\t2\tsg\topening Jira",
            "LOCALE\tGlobal\t2\tsg\tin progress: opening Jira",
            "LOCALE\tEurope\t3\tde\tlive",
        ])
        self.assertEqual(workers, 2)
        self.assertEqual(agents, {1: "sg: opening Jira"})
        self.assertEqual(locales[("Europe", 3, "de")], "live")


if __name__ == "__main__":
    unittest.main()

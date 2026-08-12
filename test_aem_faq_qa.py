import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

logging.disable(logging.CRITICAL)
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from aem_faq_qa import audit_findings, audit_page, column_kind, detail_ids, language_findings, parent_for_child, parse_args, review_answer, review_parent, run_all, text_findings
from hub import chrome_command, chrome_ready, pick_file


class AemFaqQaTest(unittest.TestCase):
    def test_child_uses_previous_yellow_parent(self):
        wb = Workbook()
        ws = wb.active
        ws.cell(8, 2).value = "sg"
        ws.cell(11, 2).fill = PatternFill("solid", fgColor="FFFFFF00")
        ws.cell(8, 3).value = "az"
        ws.cell(8, 4).value = "africa_en"
        ws.cell(11, 4).fill = PatternFill("solid", fgColor="FFFCE5CD")

        self.assertEqual(column_kind(ws.cell(11, 2)), "parent-with-children")
        self.assertEqual(column_kind(ws.cell(11, 3)), "parent")
        self.assertEqual(column_kind(ws.cell(11, 4)), "child")
        self.assertEqual(parent_for_child(ws, 4), 2)

    def test_detail_url_accepts_recorded_param_names(self):
        ids = detail_ids(
            "https://example.test/detail?siteCdParam=africa_en&contentIdParam=2204677&requestIdParam=631127"
        )
        self.assertEqual(ids, {"contentId": "2204677", "requestId": "631127"})

    def test_text_findings_detects_mixed_step_labels(self):
        findings = text_findings(["<p><strong>Step 1</strong></p><p><strong>Stage 2</strong></p>??"])
        self.assertIn("repeated punctuation", findings)
        self.assertIn("inconsistent bold numbered labels: stage, step", findings)

    def test_text_findings_detects_burmese_step_punctuation(self):
        findings = text_findings(["<b>အဆင့် ၁</b>. <b>အဆင့် ၂</b>။"])
        self.assertIn("differing punctuation after အဆင့်: ., ။", findings)

    def test_language_findings_flags_foreign_script(self):
        findings = language_findings([{"text": ["Restart your watch. အဆင့် သုံး"]}])
        self.assertEqual(findings, ["possible mixed language: Burmese text on a Latin page"])

    def test_language_findings_ignores_product_names_and_punctuation(self):
        self.assertEqual(language_findings([{"text": ["Restart Galaxy Watch 7."]}]), [])

    def test_language_findings_allows_english_on_any_page(self):
        self.assertEqual(language_findings([{"text": ["รีสตาร์ท Galaxy Watch เพื่อดำเนินการต่อ"]}]), [])

    def test_audit_findings_ignores_component_count_and_order(self):
        audit = {"components": [{"type": "text", "settings": {}, "text": []}]}
        baseline = {"components": [
            {"type": "image", "settings": {}, "text": []},
            {"type": "text", "settings": {}, "text": []},
        ]}
        self.assertEqual(audit_findings(audit, baseline), [])

    def test_review_answer_keeps_a_skip_note(self):
        self.assertEqual(review_answer("y"), (True, ""))
        self.assertEqual(review_answer("n punctuation needs review"), (False, "punctuation needs review"))

    def test_copy_workers_default_to_three(self):
        with patch("sys.argv", ["aem_faq_qa.py", "--workbook", "workbook.xlsx", "--plan"]):
            self.assertEqual(parse_args().copy_workers, 3)

    def test_review_approval_writes_editor_link(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Global"
        ws.cell(6, 2).value = "/sg/support/mobile-devices/example"
        ws.cell(8, 2).value = "sg"
        ws.cell(13, 2).value = "example"
        with patch("builtins.input", return_value="y"), patch.object(wb, "save") as save:
            review_parent(wb, "workbook.xlsx", ws, 2)
        self.assertEqual(ws.cell(3, 2).value, "https://p6spp-ap-author.samsung.com/editor.html/content/samsung/sg/support/mobile-devices/example.html")
        save.assert_called_once_with("workbook.xlsx")

    def test_chrome_ready_returns_false_when_port_is_closed(self):
        with patch("hub.urlopen", side_effect=OSError):
            self.assertFalse(chrome_ready())

    def test_picker_returns_the_native_selection(self):
        with patch("hub.platform.system", return_value="Darwin"), patch(
            "hub.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="/tmp/faq.xlsx\n")
        ):
            self.assertEqual(pick_file(), "/tmp/faq.xlsx")

    def test_chrome_command_uses_windows_standard_location(self):
        with patch("hub.platform.system", return_value="Windows"), patch.dict(
            "hub.os.environ", {"LOCALAPPDATA": "C:/Users/test/AppData/Local"}, clear=True
        ), patch("hub.Path.exists", return_value=True):
            self.assertEqual(chrome_command(), "C:/Users/test/AppData/Local/Google/Chrome/Application/chrome.exe")

    def test_audit_failure_without_stderr_does_not_stop_the_pass(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Global"
        ws.cell(8, 2).value = "sg"
        ws.cell(13, 2).value = "example"
        args = SimpleNamespace(apply=False, review=False, copy_workers=1)
        error = __import__("subprocess").CalledProcessError(1, ["node"], stderr="")
        with patch("aem_faq_qa.audit_page", side_effect=error):
            run_all(wb, args)

    def test_audit_reads_node_output_as_utf8(self):
        result = SimpleNamespace(stdout='{"components": [{"text": ["အဆင့်"]}]}')
        with patch("aem_faq_qa.subprocess.run", return_value=result) as run:
            self.assertEqual(audit_page("https://example.test", "/content/example"), {"components": [{"text": ["အဆင့်"]}]})
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def test_audit_timeout_does_not_stop_the_pass(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Global"
        ws.cell(8, 2).value = "sg"
        ws.cell(13, 2).value = "example"
        args = SimpleNamespace(apply=False, review=False, copy_workers=1)
        with patch("aem_faq_qa.audit_page", side_effect=__import__("subprocess").TimeoutExpired(["node"], 60)):
            run_all(wb, args)


if __name__ == "__main__":
    unittest.main()

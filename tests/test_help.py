import json
import os
import re
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QTextLength, QTextTable
from PySide6.QtWidgets import QApplication, QPushButton

from psytags import config, i18n
from psytags.config import Options
from psytags.ui import help as uihelp
from psytags.websources import coverfetch, coverprovider as cp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def source(lang: str, topic: str) -> str:
    with open(os.path.join(ROOT, "psytags", "resources", "help", lang, f"{topic}.md"), encoding="utf-8") as fh:
        return fh.read()


WRITTEN = [k for k in uihelp.topic_keys() if k != uihelp.SHORTCUTS_TOPIC]


class TextTests(unittest.TestCase):
    def setUp(self):
        # These check the texts as written; a Mac shows them in its symbols (test_mac_keys).
        patcher = mock.patch("psytags.ui.keys.on_mac", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_topic_exists_in_both_languages(self):
        for lang in ("de", "en"):
            for topic in WRITTEN:
                self.assertTrue(source(lang, topic).startswith("# "), f"{lang}/{topic}")

    def test_links_between_topics_lead_somewhere(self):
        known = set(uihelp.topic_keys())
        for lang in ("de", "en"):
            for topic in WRITTEN:
                for target in re.findall(r"\]\(help:([\w-]+)\)", source(lang, topic)):
                    self.assertIn(target, known, f"{lang}/{topic}")

    def test_both_languages_link_to_the_same_topics(self):
        for topic in WRITTEN:
            links = [sorted(re.findall(r"\]\(help:([\w-]+)\)", source(lang, topic))) for lang in ("de", "en")]
            self.assertEqual(links[0], links[1], topic)

    def test_the_first_page_warns_about_copies(self):
        self.assertIn("Kopien", source("de", uihelp.FIRST_TOPIC))
        self.assertIn("copies", source("en", uihelp.FIRST_TOPIC))

    def test_every_summary_reason_is_explained(self):
        for lang, words in (("de", ("Titel passt nicht", "Länge weicht", "Mehrere Ausgaben", "Keine passende Ausgabe")),
                            ("en", ("Title does not match", "Length differs", "Several editions", "No matching edition"))):
            text = source(lang, "summary")
            for word in words:
                self.assertIn(word, text, lang)

    def test_every_action_with_a_key_is_listed(self):
        self.assertIn("Alt+1", uihelp.page(uihelp.SHORTCUTS_TOPIC))
        self.assertIn("Strg+Alt+B", uihelp.page(uihelp.SHORTCUTS_TOPIC))

    def test_the_english_page_names_the_english_keys(self):
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "de")
        text = uihelp.page(uihelp.SHORTCUTS_TOPIC)
        self.assertIn("Ctrl+Alt+B", text)
        self.assertNotIn("Strg", text)

    def test_the_page_follows_the_language(self):
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "de")
        self.assertEqual(uihelp.page("start"), source("en", "start"))


class PluginGuideTests(unittest.TestCase):
    def _blocks(self, lang):
        return [json.loads(b) for b in re.findall(r"```json\n(.*?)```", source(lang, "plugins"), re.S)]

    def test_every_field_is_documented(self):
        for lang in ("de", "en"):
            for name in cp.KNOWN_FIELDS:
                self.assertIn(f"`{name}`", source(lang, "plugins"), lang)

    def test_the_example_in_the_text_is_the_example_file(self):
        with open(os.path.join(ROOT, "docs", "cover-provider-example.json"), encoding="utf-8") as fh:
            example = json.load(fh)
        for lang in ("de", "en"):
            self.assertEqual(self._blocks(lang)[1], example, lang)

    def test_the_worked_example_delivers_a_certain_cover(self):
        for lang in ("de", "en"):
            answer, description = self._blocks(lang)
            description.pop("format")
            got = cp.rows(cp.Provider(**description), json.dumps(answer))
            self.assertEqual(got[0]["_image"], "https://img.example.com/1/1400x1400.jpg")
            self.assertIsNotNone(coverfetch.confident(coverfetch.rank(got, "Example Album", "Example Band", 10)))

    def test_github_readers_are_sent_to_the_guide(self):
        with open(os.path.join(ROOT, "docs", "cover-provider.md"), encoding="utf-8") as fh:
            self.assertIn("resources/help/en/plugins.md", fh.read())


class Dialogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _dialog(self, topic=""):
        d = uihelp.HelpDialog(None, topic)
        self.addCleanup(d.deleteLater)
        return d


class HelpDialogTests(Dialogs):
    def test_it_starts_with_the_page_about_copies(self):
        d = self._dialog()
        self.assertEqual(d.current_topic(), uihelp.FIRST_TOPIC)
        self.assertIn("Kopien", d.text.toPlainText())

    def test_it_can_open_at_a_topic(self):
        self.assertEqual(self._dialog("plugins").current_topic(), "plugins")

    def test_an_unknown_topic_opens_the_first_page(self):
        self.assertEqual(self._dialog("gibt-es-nicht").current_topic(), uihelp.FIRST_TOPIC)

    def test_choosing_a_topic_shows_it(self):
        d = self._dialog()
        d.show_topic("moods")
        self.assertEqual(d.current_topic(), "moods")
        self.assertIn("ffmpeg", d.text.toPlainText())

    def test_group_titles_cannot_be_chosen(self):
        d = self._dialog()
        self.assertFalse(d.nav.item(0).isSelected())
        self.assertEqual(int(d.nav.item(0).flags().value), 0)

    def test_the_summary_stands_out_in_the_list(self):
        d = self._dialog()
        fonts = {d.nav.item(i).data(uihelp.TOPIC_ROLE): d.nav.item(i).font().bold() for i in range(d.nav.count())}
        self.assertTrue(fonts["summary"])
        self.assertFalse(fonts["moods"])

    def test_a_link_to_a_topic_stays_in_the_window(self):
        d = self._dialog()
        with mock.patch.object(QDesktopServices, "openUrl") as browser:
            d._link(QUrl("help:summary"))
        self.assertEqual(d.current_topic(), "summary")
        browser.assert_not_called()

    def test_other_links_go_to_the_browser(self):
        d = self._dialog()
        with mock.patch.object(QDesktopServices, "openUrl") as browser:
            d._link(QUrl("https://example.invalid/"))
        browser.assert_called_once()
        self.assertEqual(d.current_topic(), uihelp.FIRST_TOPIC)


class PageLookTests(Dialogs):
    def _blocks(self, d):
        block = d.text.document().begin()
        while block.isValid():
            yield block
            block = block.next()

    def _tables(self, d):
        return [f for f in d.text.document().rootFrame().childFrames() if isinstance(f, QTextTable)]

    def _headings(self, d, level):
        return [b for b in self._blocks(d) if b.blockFormat().headingLevel() == level]

    def test_headings_step_down_in_size(self):
        d = self._dialog("summary")
        sizes = [self._headings(d, n)[0].charFormat().fontPointSize() for n in (1, 2)]
        self.assertGreater(sizes[0], sizes[1])
        body = next(b for b in self._blocks(d) if b.text() and not b.blockFormat().headingLevel())
        self.assertGreater(sizes[1], d.text.document().defaultFont().pointSizeF())
        self.assertGreater(body.blockFormat().lineHeight(), 100)

    def test_a_heading_stands_closer_to_its_text_than_to_the_last_one(self):
        fmt = self._headings(self._dialog("summary"), 2)[0].blockFormat()
        self.assertGreater(fmt.topMargin(), fmt.bottomMargin())

    def test_tables_have_no_grid_and_use_the_width(self):
        table = max(self._tables(self._dialog("summary")), key=lambda t: t.rows())
        fmt = table.format()
        self.assertEqual(fmt.border(), 0)
        self.assertEqual(fmt.width().type(), QTextLength.Type.PercentageLength)
        self.assertEqual(fmt.width().rawValue(), 100)

    def test_a_one_cell_table_is_a_note_with_a_background(self):
        for topic in ("start", "summary"):
            d = self._dialog(topic)
            note = next(t for t in self._tables(d) if t.rows() == 1 and t.columns() == 1)
            self.assertNotEqual(note.cellAt(0, 0).format().background().style(), Qt.BrushStyle.NoBrush)

    def test_code_blocks_have_a_background(self):
        d = self._dialog("plugins")
        code = next(b for b in self._blocks(d) if b.blockFormat().nonBreakableLines())
        self.assertNotEqual(code.blockFormat().background().style(), Qt.BrushStyle.NoBrush)

    def test_code_uses_a_real_code_font(self):
        d = self._dialog("plugins")
        code = next(b for b in self._blocks(d) if b.blockFormat().nonBreakableLines() and b.text())
        self.assertIn("Cascadia Mono", code.begin().fragment().charFormat().fontFamilies())

    def test_a_list_keeps_its_distance_to_the_next_paragraph(self):
        d = self._dialog("start")
        items = [b for b in self._blocks(d) if b.textList() is not None]
        self.assertGreater(items[-1].blockFormat().bottomMargin(), items[0].blockFormat().bottomMargin())

    def test_long_lines_do_not_run_across_a_wide_window(self):
        d = self._dialog("start")
        d.resize(1900, 900)
        d.show()
        self.app.processEvents()
        frame = d.text.document().rootFrame().frameFormat()
        self.assertLessEqual(d.text.viewport().width() - frame.leftMargin() - frame.rightMargin(), uihelp.MAX_TEXT_WIDTH + 1)

    def test_a_new_page_starts_at_the_top(self):
        d = self._dialog("plugins")
        d.resize(800, 500)
        d.show()
        self.app.processEvents()
        d.text.verticalScrollBar().setValue(500)
        d.show_topic("trouble")
        self.assertEqual(d.text.verticalScrollBar().value(), 0)


class WiringTests(Dialogs):
    def test_f1_opens_the_help(self):
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        with mock.patch.object(uihelp, "HelpDialog") as dialog:
            MainWindow.show_help(win)
        dialog.assert_called_once_with(win)
        dialog.return_value.exec.assert_called_once()

    def test_the_options_lead_to_the_plugin_guide(self):
        from psytags.ui.dialogs.options import OptionsDialog
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        button = next(b for b in d.findChildren(QPushButton) if b.text() == "Anleitung für Plugins")
        with mock.patch.object(uihelp, "HelpDialog") as dialog:
            button.click()
        dialog.assert_called_once_with(d, "plugins")
        dialog.return_value.exec.assert_called_once()

    def test_the_summary_leads_to_its_help(self):
        from psytags.ui.dialogs.tagsources import BatchSummaryDialog
        d = BatchSummaryDialog([], lambda tracks: tracks)
        self.addCleanup(d.deleteLater)
        button = next(b for b in d.findChildren(QPushButton) if b.text() == "Hilfe zur Übersicht")
        with mock.patch.object(uihelp, "HelpDialog") as dialog:
            button.click()
        dialog.assert_called_once_with(d, "summary")
        dialog.return_value.exec.assert_called_once()


if __name__ == "__main__":
    unittest.main()

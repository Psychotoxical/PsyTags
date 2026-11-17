"""Every language file: known texts only, the same placeholders, mnemonics and valid plural forms."""
import json
import os
import re
import unittest

from psytags import i18n

PLURALS = {"ru": {"one", "few", "many", "other"}, "uk": {"one", "few", "many", "other"},
           "pl": {"one", "few", "many", "other"}, "ro": {"one", "few", "other"},
           "ja": {"other"}, "zh": {"other"}}
_PLACEHOLDER = re.compile(r"\{\d\}|\{album\}|\{artist\}")
_MNEMONIC = re.compile(r"&(?=[^\s&])")


def _load(code):
    with open(os.path.join(i18n.LOCALES, f"{code}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _forms(value):
    return list(value.values()) if isinstance(value, dict) else [value]


class LocaleFileTests(unittest.TestCase):
    def test_every_language_but_german_and_english_has_a_file(self):
        missing = [c for c in i18n.CODES if c not in ("de", "en")
                   and not os.path.exists(os.path.join(i18n.LOCALES, f"{c}.json"))]
        self.assertEqual(missing, [])

    def test_the_files_hold_only_known_texts(self):
        known = set(i18n.EN.values())
        for code in self._codes():
            with self.subTest(code):
                self.assertEqual(sorted(set(_load(code)) - known), [])

    def test_placeholders_and_mnemonics_match(self):
        for code in self._codes():
            for key, value in _load(code).items():
                for form in _forms(value):
                    with self.subTest(code=code, key=key):
                        self.assertIsInstance(form, str)
                        self.assertEqual(sorted(_PLACEHOLDER.findall(form)), sorted(_PLACEHOLDER.findall(key)))
                        self.assertEqual(len(_MNEMONIC.findall(form)), len(_MNEMONIC.findall(key)))

    def test_plural_forms_belong_to_the_language(self):
        for code in self._codes():
            allowed = PLURALS.get(code, {"one", "other"})
            for key, value in _load(code).items():
                if isinstance(value, dict):
                    with self.subTest(code=code, key=key):
                        self.assertIn("other", value)
                        self.assertLessEqual(set(value), allowed)

    def test_a_plural_form_follows_the_number(self):
        i18n._catalogs["ru"] = {"{1} files": {"one": "{1} файл", "few": "{1} файла", "many": "{1} файлов",
                                              "other": "{1} файла"}}
        try:
            i18n.set_language("ru")
            self.assertEqual([i18n.tr("{1} Dateien", n) for n in (1, 3, 5, 21)],
                             ["1 файл", "3 файла", "5 файлов", "21 файл"])
        finally:
            i18n.set_language("de")
            i18n._catalogs.pop("ru", None)

    def test_a_missing_text_shows_in_english(self):
        i18n._catalogs["fr"] = {}
        try:
            i18n.set_language("fr")
            self.assertEqual(i18n.tr("Cover von {1} laden", "X"), "Load cover from X")
        finally:
            i18n.set_language("de")
            i18n._catalogs.pop("fr", None)

    def test_the_system_language_is_found(self):
        self.assertEqual([i18n.system_code(n) for n in ("de_DE", "nb_NO", "no", "zh_CN", "pt_BR", "C")],
                         ["de", "nb", "nb", "zh", "en", "en"])

    @staticmethod
    def _codes():
        return [f[:-5] for f in sorted(os.listdir(i18n.LOCALES)) if f.endswith(".json")]


if __name__ == "__main__":
    unittest.main()

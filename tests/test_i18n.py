"""Every German UI text needs an English entry (psytags.i18n.EN)."""
import ast
import pathlib
import re
import unittest

from psytags import config, i18n

ROOT = pathlib.Path(__file__).resolve().parent.parent / "psytags"


def _ui_texts() -> dict[str, str]:
    """Literal texts passed to tr() and to the action factory A(text, slot, key, tip)."""
    found: dict[str, str] = {}
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "tr":
                args = node.args[:1]
            elif node.func.id == "A":
                args = node.args[:1] + node.args[3:4] + [k.value for k in node.keywords if k.arg == "tip"]
            else:
                continue
            for a in args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.strip():
                    found.setdefault(a.value, f"{path.name}:{a.lineno}")
    return found


def _dynamic_texts() -> list[str]:
    """Texts kept in lists and translated with tr(variable) when shown."""
    from psytags.ui import help as uihelp
    out = []
    for group, items in uihelp.SHORTCUTS:
        out.append(group)
        out += [text for _key, text in items]
    out += [c.name for c in config.DEFAULT_COLUMNS] + [f.name for f in config.DEFAULT_PANEL]
    return out


class EnglishCoverageTests(unittest.TestCase):
    def test_every_tr_text_has_english(self):
        missing = [f"{where}: {text!r}" for text, where in _ui_texts().items() if text not in i18n.EN]
        self.assertEqual(missing, [], "ohne englische Übersetzung:\n" + "\n".join(missing))

    def test_listed_texts_have_english(self):
        missing = [t for t in _dynamic_texts() if t not in i18n.EN]
        self.assertEqual(missing, [])

    def test_placeholders_match(self):
        bad = [k for k, v in i18n.EN.items()
               if sorted(re.findall(r"\{\d\}", k)) != sorted(re.findall(r"\{\d\}", v))]
        self.assertEqual(bad, [])

    def test_tr_switches_language(self):
        try:
            i18n.set_language("en")
            self.assertEqual(i18n.tr("Cover von {1} laden", "MusicBrainz"), "Load cover from MusicBrainz")
        finally:
            i18n.set_language("de")
        self.assertEqual(i18n.tr("Cover von {1} laden", "MusicBrainz"), "Cover von MusicBrainz laden")


if __name__ == "__main__":
    unittest.main()

"""Shortcuts on a Mac.

Qt puts Ctrl on the Command key there. ⌘Q quits, ⌘H hides and ⌘⇥ switches programs, so those go
to the Control key: the same key the fingers use on Windows. A MacBook has no forward delete,
so ⌫ also removes files from the list. The help shows every shortcut in Mac symbols.
"""
from __future__ import annotations

import re
import sys

MAC_SYSTEM_KEYS = {"Ctrl+Q": "Meta+Q", "Ctrl+H": "Meta+H", "Ctrl+Tab": "Meta+Tab", "Ctrl+Shift+Tab": "Meta+Shift+Tab"}
MAC_EXTRA_KEYS = {"Del": ["Backspace"]}

_MODIFIERS = {"strg": "Ctrl", "ctrl": "Ctrl", "alt": "Alt", "umschalt": "Shift", "shift": "Shift"}
_SYMBOLS = (("Meta", "⌃"), ("Alt", "⌥"), ("Shift", "⇧"), ("Ctrl", "⌘"))      # Apple's order
_KEY_SYMBOLS = {"entf": "⌫", "del": "⌫", "tab": "⇥", "backspace": "⌫"}
_SHORTCUT = re.compile(r"\b((?:(?:Strg|Ctrl|Alt|Umschalt|Shift)[+-])+)([A-Za-zÄÖÜäöü0-9]+)\b")
_ALONE = re.compile(r"(?<![\w+])(Entf|Del)(?![\w+])")


def on_mac(platform: str | None = None) -> bool:
    return (platform or sys.platform) == "darwin"


def mac_keys(keys: str, platform: str | None = None) -> str:
    return MAC_SYSTEM_KEYS.get(keys, keys) if on_mac(platform) else keys


def extra_keys(keys: str, platform: str | None = None) -> list[str]:
    return MAC_EXTRA_KEYS.get(keys, []) if on_mac(platform) else []


def _symbols(match: re.Match) -> str:
    mods = [_MODIFIERS[m.lower()] for m in re.split(r"[+-]", match.group(1)) if m]
    key = match.group(2)
    if key.lower() in ("klick", "click"):
        return "".join(s for name, s in _SYMBOLS if name in mods) + "-" + key
    portable = mac_keys("+".join(mods + [key.upper() if len(key) == 1 else key]), "darwin")
    mods = portable.split("+")[:-1]
    sign = _KEY_SYMBOLS.get(key.lower(), key.upper() if len(key) == 1 else key)
    return "".join(s for name, s in _SYMBOLS if name in mods) + sign


def mac_text(text: str) -> str:
    """Every shortcut in ``text`` in the symbols a Mac keyboard shows: Strg+Shift+M → ⇧⌘M."""
    return _ALONE.sub("⌫", _SHORTCUT.sub(_symbols, text))

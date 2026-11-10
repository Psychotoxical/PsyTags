"""Remember dialog geometry, splitter positions and list header states across restarts."""
from __future__ import annotations

import os

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QDialog, QHeaderView, QSplitter, QTableView, QTreeView

from .. import config


def geometry_key(key: str) -> str:
    """Tiling and floating desktops lay windows out differently, so each keeps its own."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return f"{key}_{desktop}" if desktop else key


def remember(dialog: QDialog, key: str) -> None:
    """Restore now and save whenever the dialog closes (OK, Cancel, Esc, X)."""
    s = config.settings()
    g = s.value(geometry_key(f"dialogs/{key}/geometry"))
    if isinstance(g, (QByteArray, bytes)):
        dialog.restoreGeometry(g)
    for i, sp in enumerate(dialog.findChildren(QSplitter)):
        st = s.value(f"dialogs/{key}/splitter{i}")
        if isinstance(st, (QByteArray, bytes)):
            sp.restoreState(st)
    for i, h in enumerate(_headers(dialog)):
        st = s.value(f"dialogs/{key}/header{i}")
        if isinstance(st, (QByteArray, bytes)):
            h.restoreState(st)
    dialog.finished.connect(lambda _=0: _save(dialog, key))


def _headers(dialog) -> list[QHeaderView]:
    out = []
    for v in dialog.findChildren(QTreeView) + dialog.findChildren(QTableView):
        h = v.header() if isinstance(v, QTreeView) else v.horizontalHeader()
        out.append(h)
    return out


def _save(dialog: QDialog, key: str) -> None:
    s = config.settings()
    s.setValue(geometry_key(f"dialogs/{key}/geometry"), dialog.saveGeometry())
    for i, sp in enumerate(dialog.findChildren(QSplitter)):
        s.setValue(f"dialogs/{key}/splitter{i}", sp.saveState())
    for i, h in enumerate(_headers(dialog)):
        s.setValue(f"dialogs/{key}/header{i}", h.saveState())
    s.sync()


def save_bool(key: str, value: bool) -> None:
    config.settings().setValue(key, bool(value))


def load_bool(key: str, default: bool = False) -> bool:
    v = config.settings().value(key)
    if v is None:
        return default
    return v in (True, "true", "1", 1)


def bind_widgets(owner, prefix: str, names: list[str]) -> None:
    """Restore the values of owner.<name> widgets (check box, spin box, combo box)
    from settings and save them on every change."""
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QSpinBox
    s = config.settings()
    for n in names:
        w = getattr(owner, n)
        key = f"{prefix}/{n}"
        v = s.value(key)
        if isinstance(w, QAbstractButton) and w.isCheckable():
            if v is not None:
                w.setChecked(v in (True, "true", "1", 1))
            w.toggled.connect(lambda on, k=key: config.settings().setValue(k, on))
        elif isinstance(w, QSpinBox):
            if v is not None:
                w.setValue(int(v))
            w.valueChanged.connect(lambda x, k=key: config.settings().setValue(k, x))
        elif isinstance(w, QComboBox):
            if v is not None:
                if w.isEditable():
                    w.setEditText(str(v))
                else:
                    w.setCurrentIndex(int(v))
            if w.isEditable():
                w.editTextChanged.connect(lambda t, k=key: config.settings().setValue(k, t))
            else:
                w.currentIndexChanged.connect(lambda i, k=key: config.settings().setValue(k, i))

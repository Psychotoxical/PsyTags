"""Remember dialog geometry, splitter positions and list header states across restarts."""
from __future__ import annotations

import os

from PySide6.QtCore import QByteArray, QEvent, QObject, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHeaderView, QSplitter, QTableView, QTreeView

from .. import config


def geometry_key(key: str) -> str:
    """Tiling and floating desktops lay windows out differently, so each keeps its own."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return f"{key}_{desktop}" if desktop else key


class _Placement(QObject):
    """Where a dialog stood when it appeared, to tell whether the user moved it."""

    def __init__(self, dialog: QDialog):
        super().__init__(dialog)
        self.shown_at: QPoint | None = None
        dialog.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Show and self.shown_at is None:
            self.shown_at = watched.pos()
        return False


def _owner(dialog: QDialog):
    parent = dialog.parentWidget()
    return parent.window() if parent is not None else None


def _on_a_screen(top_left: QPoint, size: QSize) -> bool:
    """True if the title bar of a window there can be grabbed on one of the screens."""
    grip = QRect(top_left, QSize(size.width(), 30))
    for screen in QGuiApplication.screens():
        seen = screen.availableGeometry().intersected(grip)
        if seen.width() >= 80 and seen.height() >= 20:
            return True
    return False


def remember(dialog: QDialog, key: str) -> None:
    """Restore now and save whenever the dialog closes (OK, Cancel, Esc, X).

    A dialog opens centred on its window. Once the user has moved it, it keeps that place
    relative to the window, so it follows the window to another screen and still may stand
    beside it or on a different screen."""
    s = config.settings()
    size = s.value(geometry_key(f"dialogs/{key}/size"))
    if isinstance(size, QSize) and size.isValid():
        dialog.resize(size)
    else:
        g = s.value(geometry_key(f"dialogs/{key}/geometry"))      # saved by an older version
        if isinstance(g, (QByteArray, bytes)):
            dialog.restoreGeometry(g)
            dialog.setAttribute(Qt.WidgetAttribute.WA_Moved, False)    # its place was absolute: centre again
    offset, owner = s.value(geometry_key(f"dialogs/{key}/offset")), _owner(dialog)
    if isinstance(offset, QPoint) and owner is not None:
        place = owner.pos() + offset
        if _on_a_screen(place, dialog.size()):
            dialog.move(place)
    dialog._placement = _Placement(dialog)
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
    if not (dialog.isMaximized() or dialog.isFullScreen()):
        s.setValue(geometry_key(f"dialogs/{key}/size"), dialog.size())
        shown_at, owner = dialog._placement.shown_at, _owner(dialog)
        if owner is not None and shown_at is not None and dialog.pos() != shown_at:
            s.setValue(geometry_key(f"dialogs/{key}/offset"), dialog.pos() - owner.pos())
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

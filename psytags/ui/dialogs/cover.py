"""Cover preview window and "Adjust cover"."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from ...i18n import tr


class CoverPreview(QDialog):
    """Larger cover window; stays open and follows the selection."""
    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Cover"))
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(200, 200)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)
        self._img = None
        self.resize(560, 560)

    @classmethod
    def show_for(cls, parent, cover_view) -> None:
        if cls._instance is None:
            cls._instance = CoverPreview(parent)
            cover_view.changed.connect(lambda: cls._instance._set(cover_view._img))
        cls._instance._set(cover_view._img)
        cls._instance.show()
        cls._instance.raise_()

    def _set(self, img):
        self._img = img
        self._update()

    def resizeEvent(self, e):
        self._update()
        super().resizeEvent(e)

    def _update(self):
        if self._img is None:
            self.label.clear()
            return
        self.label.setPixmap(QPixmap.fromImage(self._img).scaled(
            self.label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self.setWindowTitle(f"{tr('Cover')} - {self._img.width()}x{self._img.height()}")


def _scale(img: QImage, n: int, mode: int, minimum=False) -> QImage:
    if mode in (1, 2):
        return img.scaled(n, n, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    aspect = Qt.AspectRatioMode.KeepAspectRatioByExpanding if minimum else Qt.AspectRatioMode.KeepAspectRatio
    return img.scaled(n, n, aspect, Qt.TransformationMode.SmoothTransformation)

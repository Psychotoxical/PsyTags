"""Cover preview window and "Adjust cover"."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QSpinBox, QVBoxLayout)

from ... import tags
from ...i18n import tr
from ..tagpanel import image_to_bytes


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


def adjust_cover(parent, cover: tags.Cover) -> tags.Cover | None:
    d = QDialog(parent)
    d.setWindowTitle(tr("Album-Cover anpassen"))
    f = QFormLayout(d)
    fmt = QComboBox()
    fmt.addItems([tr("Original"), "JPEG", "PNG"])
    f.addRow(tr("Bildformat"), fmt)
    quality = QComboBox()
    quality.addItems([tr("Niedrig"), tr("Mittel"), tr("Hoch"), tr("Höchste")])
    quality.setCurrentIndex(2)
    f.addRow(tr("Qualität"), quality)
    size_on = QCheckBox(tr("Bildgröße"))
    size_on.setChecked(True)
    size = QSpinBox()
    size.setRange(16, 10000)
    size.setValue(600)
    f.addRow(size_on, size)
    mode = QComboBox()
    mode.addItems([tr("max. Größe"), tr("min. Größe")])
    f.addRow("", mode)
    scaling = QComboBox()
    scaling.addItems([tr("Proportional skalieren"), tr("Quadratisch skalieren"),
                      tr("Quadratisch beschneiden")])
    f.addRow("", scaling)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    f.addRow(bb)
    if not d.exec():
        return None
    img = QImage.fromData(cover.data)
    if img.isNull():
        return None
    if size_on.isChecked():
        n = size.value()
        sc = scaling.currentIndex()
        if sc == 2:
            side = min(img.width(), img.height())
            img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
        w, h = img.width(), img.height()
        if mode.currentIndex() == 0:      # max: shrink only if larger
            if w > n or h > n:
                img = _scale(img, n, sc)
        else:                             # min: smaller side becomes n
            img = _scale(img, n, sc, minimum=True)
    fmt_i = fmt.currentIndex()
    if fmt_i == 0:
        out_fmt = "PNG" if cover.mime == "image/png" else "JPG"
    else:
        out_fmt = "JPG" if fmt_i == 1 else "PNG"
    q = [50, 75, 90, 100][quality.currentIndex()]
    from PySide6.QtCore import QBuffer, QByteArray
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, out_fmt, q)
    return tags.Cover(bytes(ba.data()), "image/png" if out_fmt == "PNG" else "image/jpeg",
                      cover.type, cover.description)


def _scale(img: QImage, n: int, mode: int, minimum=False) -> QImage:
    if mode in (1, 2):
        return img.scaled(n, n, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    aspect = Qt.AspectRatioMode.KeepAspectRatioByExpanding if minimum else Qt.AspectRatioMode.KeepAspectRatio
    return img.scaled(n, n, aspect, Qt.TransformationMode.SmoothTransformation)

"""PsyTags's own toolbar icon set, painted with QPainter on a 16x16 grid.

Compact light outlines on dark surfaces, with restrained semantic accents.
Unknown names fall back to theme icons.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QIcon, QImage, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)

from . import theme

# The drawing functions take these as default arguments, so a theme change recolors
# the objects in place (refresh_colors) instead of replacing them.
_COLOR_NAMES = {"INK": "ICON_INK", "FOLDER": "ICON_INK", "GREEN": "ICON_POSITIVE", "BLUE": "ACCENT",
                "RED": "ERROR", "WHITE": "TEXT", "PAPER": "CHROME"}
INK, FOLDER, GREEN, BLUE, RED, WHITE, PAPER = (QColor(getattr(theme, n)) for n in _COLOR_NAMES.values())

THEME_FALLBACK = {"help": ["help-contents"]}


def _pen(c=INK, w=1.0):
    p = QPen(c, w)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _poly(p, pts, close=True, fill=None):
    path = QPainterPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    if close:
        path.closeSubpath()
    p.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
    p.drawPath(path)


# -- primitives ----------------------------------------------------------------

def folder(p, x=0.5, y=3.5, w=13, h=10, color=FOLDER):
    p.setPen(_pen(color))
    _poly(p, [(x, y + 1), (x + 4, y + 1), (x + 5.5, y + 2.5), (x + w, y + 2.5),
              (x + w, y + h), (x, y + h)], fill=PAPER)


def doc(p, x=3.5, y=1.5, w=9, h=13, fold=3):
    p.setPen(_pen())
    _poly(p, [(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)],
          fill=PAPER)
    p.drawLine(QPointF(x + w - fold, y), QPointF(x + w - fold, y + fold))
    p.drawLine(QPointF(x + w - fold, y + fold), QPointF(x + w, y + fold))


def badge_plus(p, cx, cy, r=3.2, color=GREEN):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setPen(_pen(WHITE, 1.2))
    p.drawLine(QPointF(cx - r + 1.3, cy), QPointF(cx + r - 1.3, cy))
    p.drawLine(QPointF(cx, cy - r + 1.3), QPointF(cx, cy + r - 1.3))


def badge_play(p, cx, cy, r=3.4, color=GREEN):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setBrush(WHITE)
    p.drawPolygon(QPolygonF([QPointF(cx - 1, cy - 1.8), QPointF(cx + 1.9, cy), QPointF(cx - 1, cy + 1.8)]))


def arrow(p, x1, y1, x2, y2, color=BLUE, head=2.2, w=1.2):
    p.setPen(_pen(color, w))
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    a = math.atan2(y2 - y1, x2 - x1)
    for s in (-1, 1):
        p.drawLine(QPointF(x2, y2), QPointF(x2 - head * math.cos(a + s * 0.6),
                                             y2 - head * math.sin(a + s * 0.6)))


def tagdot(p, cx, cy, r=2.3):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(INK)
    p.drawEllipse(QPointF(cx, cy), r, r)


def lines(p, x, y, w, n=3, gap=2.2, color=INK):
    p.setPen(_pen(color))
    for i in range(n):
        p.drawLine(QPointF(x, y + i * gap), QPointF(x + w, y + i * gap))


def wand(p, sparkle=True):
    p.setPen(_pen(INK, 1.4))
    p.drawLine(QPointF(2.5, 13.5), QPointF(10, 6))
    p.setPen(_pen(INK, 1))
    if sparkle:
        for (x, y) in ((12.5, 3.5),):
            p.drawLine(QPointF(x - 2, y), QPointF(x + 2, y))
            p.drawLine(QPointF(x, y - 2), QPointF(x, y + 2))
        p.drawPoint(QPointF(9, 2.5))
        p.drawPoint(QPointF(13.5, 8))


# -- icons -----------------------------------------------------------------------

def i_save(p):
    p.setPen(_pen())
    _poly(p, [(1.5, 1.5), (12, 1.5), (14.5, 4), (14.5, 14.5), (1.5, 14.5)], fill=PAPER)
    p.drawRect(QRectF(4.5, 1.5, 6, 4))
    p.drawRect(QRectF(4, 9, 8, 5.5))


def i_remove(p):
    p.setPen(_pen(INK, 1.3))
    p.drawLine(QPointF(3.5, 3.5), QPointF(12.5, 12.5))
    p.drawLine(QPointF(12.5, 3.5), QPointF(3.5, 12.5))


def _curved(p, mirror):
    p.save()
    if mirror:
        p.translate(16, 0)
        p.scale(-1, 1)
    p.setPen(_pen(INK, 1.2))
    path = QPainterPath()
    path.moveTo(3.5, 6.5)
    path.cubicTo(6, 3.5, 13, 3.5, 13, 9)
    path.cubicTo(13, 12, 10, 13.5, 7.5, 13)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.drawLine(QPointF(3.5, 6.5), QPointF(3.2, 2.8))
    p.drawLine(QPointF(3.5, 6.5), QPointF(7.2, 6.6))
    p.restore()


def i_undo(p):
    _curved(p, False)


def i_redo(p):
    _curved(p, True)


def i_folder_open(p):
    folder(p)


def i_folder_add(p):
    folder(p, x=0.5, y=4.5, w=12, h=9)
    badge_plus(p, 11.8, 4.2)


def i_folder_playlist(p):
    folder(p, x=0.5, y=4.5, w=12, h=9)
    p.setPen(_pen(BLUE))
    p.drawRect(QRectF(7.5, 8.5, 6, 6))
    lines(p, 9, 10.5, 3, n=2, gap=2, color=BLUE)


def i_folder_up(p):
    folder(p, x=2.5, y=4.5, w=12, h=9)
    arrow(p, 3, 15, 3, 7)


def i_favorite(p):
    pts = []
    for i in range(10):
        r = 6.5 if i % 2 == 0 else 2.8
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((8 + r * math.cos(a), 8.5 + r * math.sin(a)))
    p.setPen(_pen(FOLDER, 1.1))
    _poly(p, pts)


def i_refresh(p):
    p.setPen(_pen(BLUE, 1.4))
    p.drawArc(QRectF(2.5, 2.5, 11, 11), 60 * 16, 290 * 16)
    p.drawLine(QPointF(11.3, 1.8), QPointF(11.3, 5))
    p.drawLine(QPointF(11.3, 5), QPointF(8.2, 4.7))


def i_select(p):
    p.setPen(_pen())
    _poly(p, [(5, 3), (5, 13), (7.5, 10.5), (9.5, 14.5), (11, 13.8), (9, 10), (12.5, 10)],
          fill=PAPER)
    p.setPen(_pen(BLUE))
    for (x1, y1, x2, y2) in ((3, 1.5, 3.8, 2.8), (1, 4, 2.5, 4.5), (6.5, 0.8, 6.5, 2)):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def i_copy_to(p):
    p.setPen(_pen())
    p.drawRect(QRectF(1.5, 1.5, 6, 5))
    folder(p, x=5.5, y=6.5, w=9, h=7)
    arrow(p, 4.5, 7, 4.5, 11.5, head=1.6)


def i_move_to(p):
    p.setPen(_pen(INK, 1))
    p.setPen(QPen(INK, 1, Qt.PenStyle.DotLine))
    p.drawRect(QRectF(1.5, 1.5, 6, 5))
    folder(p, x=5.5, y=6.5, w=9, h=7)
    arrow(p, 4.5, 7, 4.5, 11.5, head=1.6)


def i_tag_filename(p):
    tagdot(p, 3.5, 4)
    arrow(p, 5, 10, 8.5, 10, head=1.6)
    doc(p, 9.5, 5.5, 6, 9, 2)


def i_filename_tag(p):
    doc(p, 0.5, 1.5, 6, 9, 2)
    arrow(p, 7, 11, 10.5, 11, head=1.6)
    tagdot(p, 13, 11.5)


def i_filename_filename(p):
    doc(p, 0.5, 1.5, 6, 9, 2)
    arrow(p, 7, 11, 9.5, 11, head=1.6)
    doc(p, 9.5, 5.5, 6, 9, 2)


def i_textfile_tag(p):
    p.setPen(_pen(BLUE, 1))
    font = p.font()
    font.setPixelSize(7)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(0, 0, 9, 8), Qt.AlignmentFlag.AlignCenter, "ab")
    arrow(p, 6, 11, 9.5, 11, head=1.6)
    tagdot(p, 12.5, 11.5)


def i_tag_tag(p):
    tagdot(p, 3.5, 4)
    arrow(p, 5, 10, 8.5, 10, head=1.6)
    tagdot(p, 12, 11.5)


def i_actions(p):
    wand(p)


def i_quick_action(p):
    wand(p, sparkle=False)
    p.setPen(_pen(BLUE))
    p.drawLine(QPointF(10.5, 1.5), QPointF(14.5, 5.5))
    p.drawLine(QPointF(9, 3), QPointF(13, 7))


def i_extended(p):
    p.setPen(_pen())
    p.drawRect(QRectF(1.5, 2.5, 13, 11))
    p.drawLine(QPointF(6, 2.5), QPointF(6, 13.5))
    lines(p, 8, 5.5, 4.5, n=3, gap=2.5)
    lines(p, 3, 5.5, 1.5, n=3, gap=2.5)


def i_export(p):
    doc(p, 4.5, 1.5, 9, 13, 3)
    lines(p, 6.5, 7, 5, n=3, gap=2)
    arrow(p, 0.5, 4.5, 6, 4.5, head=1.8)


def i_playlist(p):
    doc(p, 1.5, 1.5, 9, 13, 3)
    lines(p, 3.5, 6, 4, n=3, gap=2)
    badge_play(p, 11.5, 11.5)


def i_playlist_sel(p):
    doc(p, 1.5, 1.5, 9, 13, 3)
    p.setPen(_pen(BLUE))
    p.drawRect(QRectF(3, 6, 5, 2))
    lines(p, 3.5, 10.5, 4, n=1)
    badge_play(p, 11.5, 11.5, color=QColor(theme.ICON_MUTED))


def i_numbering(p):
    font = p.font()
    font.setPixelSize(5)
    p.setFont(font)
    p.setPen(_pen())
    for i, n in enumerate("123"):
        p.drawText(QRectF(0.5, 0.5 + i * 5, 4, 5), Qt.AlignmentFlag.AlignCenter, n)
    lines(p, 6, 3, 8.5, n=3, gap=5)


def i_freedb(p):
    p.setPen(_pen())
    p.drawEllipse(QRectF(1.5, 1.5, 13, 13))
    p.drawEllipse(QRectF(5, 1.5, 6, 13))
    p.drawLine(QPointF(1.5, 8), QPointF(14.5, 8))
    p.drawLine(QPointF(8, 1.5), QPointF(8, 14.5))


def i_web(p):
    i_freedb(p)
    p.setPen(_pen(BLUE, 1.3))
    p.setBrush(PAPER)
    p.drawEllipse(QRectF(8, 8, 6, 6))
    p.drawLine(QPointF(13, 13), QPointF(15, 15))


def i_genres(p):
    """Label with a note: genres & moods from Last.fm."""
    p.setPen(_pen())
    _poly(p, [(1.5, 3.5), (10, 3.5), (14.5, 8), (10, 12.5), (1.5, 12.5)], fill=PAPER)
    p.drawEllipse(QRectF(10, 7, 2, 2))
    p.setPen(_pen(RED, 1.2))                       # eighth note, drawn (no font needed)
    p.setBrush(RED)
    p.drawEllipse(QRectF(3, 8.6, 3, 2.3))
    p.drawLine(QPointF(5.8, 9.6), QPointF(5.8, 5))
    p.drawLine(QPointF(5.8, 5), QPointF(8, 6.6))


def i_moods(p):
    """Waveform with an accent: moods from the audio."""
    p.setPen(_pen(INK, 1.4))
    for x, h in ((2.5, 4), (5.5, 9), (8.5, 12), (11.5, 6)):
        p.drawLine(QPointF(x, 8 - h / 2), QPointF(x, 8 + h / 2))
    p.setPen(_pen(RED, 1.4))
    p.drawLine(QPointF(14, 6), QPointF(14, 10))


def _bolt(p, dx=0.0, dy=0.0):
    p.setPen(_pen(GREEN, 0.8))
    pts = [(11.5, 4.5), (8, 10), (10.5, 10), (9.5, 15), (14.5, 8.5), (12, 8.5), (13, 4.5)]
    _poly(p, [(x + dx, y + dy) for x, y in pts], fill=GREEN)


def i_auto_album(p):
    """Disc with a bolt: choose the album automatically."""
    p.setPen(_pen())
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(1.5, 2, 11, 11))
    p.drawEllipse(QRectF(6, 6.5, 2, 2))
    _bolt(p)


def i_auto_all(p):
    """Two discs with a bolt: all albums automatically."""
    p.setPen(_pen())
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(0.8, 1, 8, 8))
    p.drawEllipse(QRectF(3.8, 5.5, 8, 8))
    p.drawEllipse(QRectF(7, 8.7, 1.6, 1.6))
    _bolt(p)


def i_batch_summary(p):
    """List with check marks: result of the automatic run."""
    p.setPen(_pen())
    for y in (4, 8, 12):
        p.drawLine(QPointF(7, y), QPointF(14.5, y))
    p.setPen(_pen(GREEN, 1.4))
    for y in (4, 8, 12):
        p.drawLine(QPointF(1.5, y), QPointF(3, y + 1.5))
        p.drawLine(QPointF(3, y + 1.5), QPointF(5.4, y - 1.6))


def i_options(p):
    p.setPen(_pen(INK, 1.6))
    p.drawLine(QPointF(3, 13), QPointF(9.5, 6.5))
    p.setPen(_pen(INK, 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(8, 1.5, 7, 7), 200 * 16, 270 * 16)


def i_play(p):
    badge_play(p, 8, 8, r=6.5)


PAINTED = {
    "save": i_save, "remove": i_remove, "undo": i_undo, "redo": i_redo,
    "folder-open": i_folder_open, "folder-add": i_folder_add, "folder-playlist": i_folder_playlist,
    "folder-up": i_folder_up, "favorite": i_favorite, "refresh": i_refresh, "select": i_select,
    "copy-to": i_copy_to, "move-to": i_move_to,
    "tag-filename": i_tag_filename, "filename-tag": i_filename_tag,
    "filename-filename": i_filename_filename, "textfile-tag": i_textfile_tag, "tag-tag": i_tag_tag,
    "actions": i_actions, "quick-action": i_quick_action, "extended": i_extended,
    "export": i_export, "playlist": i_playlist, "playlist-sel": i_playlist_sel,
    "numbering": i_numbering, "freedb": i_freedb, "web": i_web, "options": i_options,
    "play": i_play, "genres": i_genres, "moods": i_moods, "auto-album": i_auto_album,
    "auto-all": i_auto_all, "batch-summary": i_batch_summary,
}


def _render(fn, size: int, disabled=False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.scale(size / 16, size / 16)
    if disabled:
        p.setOpacity(0.35)
    fn(p)
    p.end()
    return pm


def refresh_colors() -> None:
    """Take the colors of the theme now current; icons are drawn anew on the next request."""
    for var, name in _COLOR_NAMES.items():
        globals()[var].setRgba(QColor(getattr(theme, name)).rgba())
    icon.cache_clear()


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    if name == "app":
        return _app_icon()
    fn = PAINTED.get(name)
    if fn is not None:
        ic = QIcon()
        for size in (16, 24, 32, 48):
            ic.addPixmap(_render(fn, size), QIcon.Mode.Normal)
            ic.addPixmap(_render(fn, size, True), QIcon.Mode.Disabled)
        return ic
    for n in THEME_FALLBACK.get(name, [name]):
        ic = QIcon.fromTheme(n)
        if not ic.isNull():
            return ic
    return QIcon()


def _resource(name: str) -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", name)


def _app_icon() -> QIcon:
    ic = QIcon()
    for size in (16, 32, 64, 256):
        ic.addFile(_resource(f"icon-{size}.png"), QSize(size, size))
    return ic


def logo_pixmap(height: int) -> QPixmap:
    """The PsyTags lettering in the accent color of the current theme, sharp on any display."""
    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen is not None else 1.0
    image = QImage(_resource("logo.png")).scaledToHeight(round(height * ratio), Qt.TransformationMode.SmoothTransformation)
    image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), QColor(theme.ACCENT))
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap

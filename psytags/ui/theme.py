"""Compact dark appearance shared by the editor and its dialogs."""
from __future__ import annotations

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractItemView, QApplication, QProxyStyle, QStyle, QStyleFactory

BACKGROUND = "#1b2027"
CHROME = "#222933"
PANEL = "#242c36"
FIELD = "#1c232c"
BORDER = "#3c4755"
FIELD_BORDER = "#6a798d"
ALTERNATE = "#222a34"
DISABLED = "#778494"
HOVER = "#303e50"
VISITED_LINK = "#c2b4f0"
ICON_INK = "#cbd5e1"
ICON_POSITIVE = "#528a69"
ICON_MUTED = "#7f8c8d"
TEXT = "#e1e7ef"
SECONDARY = "#a9b5c4"
ACCENT = "#8ab9ff"
SELECTION = "#294365"
ERROR = "#ffaaa5"
WARNING = "#f0c58b"
WARNING_BACKGROUND = "#493a27"


def dark_palette() -> QPalette:
    p = QPalette()
    c = QPalette.ColorRole
    colors = {
        c.Window: PANEL, c.WindowText: TEXT, c.Base: FIELD,
        c.AlternateBase: ALTERNATE, c.Text: TEXT,
        c.Button: CHROME, c.ButtonText: TEXT,
        c.Highlight: SELECTION, c.HighlightedText: TEXT,
        c.ToolTipBase: CHROME, c.ToolTipText: TEXT,
        c.PlaceholderText: SECONDARY, c.Link: ACCENT,
        c.LinkVisited: VISITED_LINK, c.BrightText: ERROR,
        c.Light: BORDER, c.Midlight: BORDER, c.Mid: BORDER,
        c.Dark: BACKGROUND, c.Shadow: BACKGROUND,
    }
    for role, color in colors.items():
        p.setColor(role, QColor(color))
    for role in (c.WindowText, c.Text, c.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(DISABLED))
    return p


STYLE = Template("""
QMainWindow { background: $CHROME; }
QMenuBar, QToolBar, QStatusBar { background: $CHROME; }
QMenuBar::item { background: transparent; }
QMenuBar::item:selected, QMenu::item:selected { background: $SELECTION; color: $TEXT; }
QMenu { background: $CHROME; color: $TEXT; border: 1px solid $BORDER; }
QMenu::item:disabled { color: $DISABLED; }
QMenu::separator { height: 1px; background: $BORDER; margin: 3px 5px; }
QToolBar { border: none; border-bottom: 1px solid $BORDER; spacing: 1px; padding: 1px; }
QToolBar::separator { width: 1px; background: $BORDER; margin: 3px 4px; }
/* Fusion owns tool-button geometry, split menus, arrows and disabled states. */
QMainWindow::separator { background: $BORDER; }
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background: $FIELD; color: $TEXT;
    border: 1px solid $FIELD_BORDER; border-radius: 3px;
    selection-background-color: $SELECTION; selection-color: $TEXT;
}
QLineEdit, QComboBox { min-height: 22px; }
QComboBox:editable { background: $FIELD; }
QComboBox QLineEdit, QAbstractSpinBox QLineEdit {
    border: none; border-radius: 0; background: transparent; min-height: 0; padding: 0;
}
QAbstractItemView QLineEdit { min-height: 0; padding: 0; border-radius: 0; }
QLineEdit:focus, QComboBox:focus,
QTextEdit:focus, QPlainTextEdit:focus { border-color: $ACCENT; }
QLineEdit:disabled, QComboBox:disabled { color: $DISABLED; }
QAbstractItemView {
    background: $BACKGROUND; alternate-background-color: $ALTERNATE; color: $TEXT;
    border: 1px solid $BORDER;
    selection-background-color: $SELECTION; selection-color: $TEXT;
}
QAbstractItemView::item:selected { background: $SELECTION; color: $TEXT; }
QAbstractItemView::item:selected:!active { background: $HOVER; }
QHeaderView { background: $CHROME; }
QHeaderView::section { background: $CHROME; color: $SECONDARY;
    border: none; border-right: 1px solid $BORDER;
    border-bottom: 1px solid $BORDER; padding: 2px 4px; }
QTableCornerButton::section { background: $CHROME; border: none; }
QPushButton { background: $CHROME; color: $TEXT; border: 1px solid $BORDER;
    border-radius: 3px; padding: 3px 10px; min-width: 58px; }
QPushButton:hover { background: $HOVER; }
QPushButton:pressed { background: $SELECTION; }
QPushButton:default { border-color: $ACCENT; background: $SELECTION; }
QPushButton:focus { border-color: $ACCENT; }
QPushButton:disabled { color: $DISABLED; }
QTabWidget::pane { border: 1px solid $BORDER; }
QTabBar::tab { background: $CHROME; color: $SECONDARY; padding: 4px 9px;
    border: 1px solid transparent; }
QTabBar::tab:selected { color: $TEXT; background: $PANEL; border-bottom-color: $ACCENT; }
QGroupBox { border: 1px solid $BORDER; border-radius: 3px; margin-top: 7px; }
QGroupBox::title { subcontrol-origin: margin; left: 7px; padding: 0 3px; }
QStatusBar { border-top: 1px solid $BORDER; color: $SECONDARY; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $SECONDARY; padding: 0 4px; }
QToolTip { background: $CHROME; color: $TEXT; border: 1px solid $BORDER; }
""").substitute(
    CHROME=CHROME,
    SELECTION=SELECTION,
    TEXT=TEXT,
    BORDER=BORDER,
    DISABLED=DISABLED,
    PANEL=PANEL,
    FIELD=FIELD,
    FIELD_BORDER=FIELD_BORDER,
    ACCENT=ACCENT,
    BACKGROUND=BACKGROUND,
    ALTERNATE=ALTERNATE,
    HOVER=HOVER,
    SECONDARY=SECONDARY,
)


class DarkStyle(QProxyStyle):
    """Paint crisp focus and field frames without changing Fusion geometry."""

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
            view = widget
            while view is not None and not isinstance(view, QAbstractItemView):
                view = view.parentWidget()
            in_view = view is not None and (
                widget is view or widget is view.viewport()
                or view.viewport().isAncestorOf(widget)
            )
            if in_view:
                if not view.hasFocus():
                    return
            elif not option.state & QStyle.StateFlag.State_KeyboardFocusChange:
                return
            painter.save()
            painter.setPen(QColor(ACCENT))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)

    def drawComplexControl(self, control, option, painter, widget=None):
        super().drawComplexControl(control, option, painter, widget)
        if control == QStyle.ComplexControl.CC_SpinBox and option.frame:
            color = ACCENT if option.state & QStyle.StateFlag.State_HasFocus else FIELD_BORDER
            painter.save()
            painter.setPen(QColor(color))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()


def apply_theme(app: QApplication) -> None:
    """Apply appearance only; font, widget geometry and shortcuts stay owned by the UI."""
    # Newer Qt versions also carry the choice into native Windows decorations.
    if hasattr(app.styleHints(), "setColorScheme"):
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    app.setStyle(DarkStyle(QStyleFactory.create("Fusion")))
    app.setPalette(dark_palette())
    app.setStyleSheet(STYLE)

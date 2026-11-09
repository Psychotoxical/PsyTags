"""Catppuccin Mocha and Latte, the two themes PsyTags shares with Psysonic."""
from __future__ import annotations

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractItemView, QApplication, QProxyStyle, QStyle, QStyleFactory

MOCHA = {
    "BACKGROUND": "#1e1e2e", "CHROME": "#181825", "PANEL": "#181825", "FIELD": "#11111b",
    "BUTTON": "#313244", "HOVER": "#45475a", "BORDER": "#45475a", "FIELD_BORDER": "#585b70",
    "ALTERNATE": "#232334", "DISABLED": "#7f849c",
    "TEXT": "#cdd6f4", "SECONDARY": "#a6adc8", "ACCENT": "#cba6f7", "ACCENT_HOVER": "#dfc8fb",
    "ACCENT_TEXT": "#1e1e2e", "SELECTION": "#45385c", "VISITED_LINK": "#b4befe",
    "ICON_INK": "#cdd6f4", "ICON_POSITIVE": "#a6e3a1", "ICON_MUTED": "#7f849c",
    "ERROR": "#f38ba8", "WARNING": "#f9e2af", "WARNING_BACKGROUND": "#4a4030",
    "OK_BACKGROUND": "#2a3b32", "OK_TEXT": "#a6e3a1", "BAD_BACKGROUND": "#4b2c36", "BAD_TEXT": "#fbb4c6",
}
LATTE = {
    "BACKGROUND": "#eff1f5", "CHROME": "#e6e9ef", "PANEL": "#e6e9ef", "FIELD": "#dce0e8",
    "BUTTON": "#ccd0da", "HOVER": "#bcc0cc", "BORDER": "#bcc0cc", "FIELD_BORDER": "#acb0be",
    "ALTERNATE": "#e9ecf1", "DISABLED": "#8c8fa1",
    "TEXT": "#4c4f69", "SECONDARY": "#5c5f77", "ACCENT": "#8839ef", "ACCENT_HOVER": "#7a2fd8",
    "ACCENT_TEXT": "#eff1f5", "SELECTION": "#d8c9f4", "VISITED_LINK": "#7287fd",
    "ICON_INK": "#4c4f69", "ICON_POSITIVE": "#40a02b", "ICON_MUTED": "#8c8fa1",
    "ERROR": "#d20f39", "WARNING": "#df8e1d", "WARNING_BACKGROUND": "#f6e6c8",
    "OK_BACKGROUND": "#cfe9cc", "OK_TEXT": "#2b6e1c", "BAD_BACKGROUND": "#f6ccd6", "BAD_TEXT": "#9c0b2b",
}
THEMES = {"mocha": MOCHA, "latte": LATTE}
CURRENT = "mocha"
globals().update(MOCHA)


def use(name: str) -> None:
    """Make a theme current. Call before the window modules are imported: they take the colors then."""
    global CURRENT
    CURRENT = name if name in THEMES else "mocha"
    globals().update(THEMES[CURRENT])


def app_palette() -> QPalette:
    g = globals()
    p = QPalette()
    c = QPalette.ColorRole
    colors = {
        c.Window: g["PANEL"], c.WindowText: g["TEXT"], c.Base: g["FIELD"],
        c.AlternateBase: g["ALTERNATE"], c.Text: g["TEXT"],
        c.Button: g["BUTTON"], c.ButtonText: g["TEXT"],
        c.Highlight: g["SELECTION"], c.HighlightedText: g["TEXT"],
        c.ToolTipBase: g["CHROME"], c.ToolTipText: g["TEXT"],
        c.PlaceholderText: g["SECONDARY"], c.Link: g["ACCENT"],
        c.LinkVisited: g["VISITED_LINK"], c.BrightText: g["ERROR"],
        c.Light: g["BORDER"], c.Midlight: g["BORDER"], c.Mid: g["BORDER"],
        c.Dark: g["BACKGROUND"], c.Shadow: g["BACKGROUND"],
    }
    for role, color in colors.items():
        p.setColor(role, QColor(color))
    for role in (c.WindowText, c.Text, c.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(g["DISABLED"]))
    return p


_STYLE = Template("""
QMainWindow { background: $BACKGROUND; }
QMainWindow::separator { background: $BORDER; width: 1px; height: 1px; }
QWidget#Header, QWidget#StepBar { background: $CHROME; border-bottom: 1px solid $BORDER; }
QLabel#Wordmark { font-size: 17px; font-weight: 700; margin-right: 14px; }
QPushButton#HeaderButton, QToolButton#MenuButton {
    background: $BUTTON; color: $TEXT; border: 1px solid $FIELD_BORDER; border-radius: 6px;
    min-height: 32px; min-width: 0; padding: 0 14px;
}
QToolButton#MenuButton::menu-indicator { image: none; width: 0; }
QPushButton#HeaderButton:hover, QToolButton#MenuButton:hover { background: $HOVER; }
QPushButton#HeaderButton:disabled { color: $DISABLED; }
QLineEdit#Search { min-height: 32px; padding: 0 12px; border-radius: 6px; }
QPushButton#Primary {
    background: $ACCENT; color: $ACCENT_TEXT; border: none; border-radius: 8px;
    min-height: 56px; min-width: 0; padding: 0;
}
QPushButton#Primary:hover { background: $ACCENT_HOVER; }
QPushButton#Primary:disabled { background: $BUTTON; }
QLabel#PrimaryTitle { color: $ACCENT_TEXT; background: transparent; font-size: 14px; font-weight: 700; }
QLabel#PrimaryKey { color: $ACCENT_TEXT; background: transparent; font-size: 11px; font-weight: 500; }
QLabel#PrimaryTitle:disabled, QLabel#PrimaryKey:disabled { color: $DISABLED; }
QPushButton#Step {
    background: $BUTTON; color: $TEXT; border: 1px solid $BORDER; border-radius: 8px;
    min-height: 56px; min-width: 0; padding: 0;
}
QPushButton#Step:hover { background: $HOVER; }
QPushButton#Step:disabled { background: $CHROME; }
QPushButton#Step QLabel, QFrame#StepSplit QLabel { background: transparent; }
QFrame#StepSplit { background: $BUTTON; border: 1px solid $BORDER; border-radius: 8px; min-height: 56px; }
QPushButton#StepChoice {
    background: $HOVER; color: $TEXT; border: none; border-radius: 5px;
    min-height: 22px; min-width: 0; padding: 0 12px; font-size: 11px; font-weight: 500;
}
QPushButton#StepChoice:hover { background: $ACCENT; color: $ACCENT_TEXT; }
QPushButton#StepChoice:disabled { background: transparent; color: $DISABLED; }
QLabel#StepNumber {
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
    border: 1px solid $ACCENT; border-radius: 12px; color: $ACCENT; font-weight: 600;
    qproperty-alignment: AlignCenter;
}
QLabel#StepNumber:disabled { color: $DISABLED; border-color: $DISABLED; }
QLabel#StepTitle { font-weight: 600; }
QLabel#StepKey, QLabel#PanelCount { color: $SECONDARY; font-size: 11px; }
QLabel#StepTitle:disabled, QLabel#StepKey:disabled { color: $DISABLED; }
QLabel#PanelTitle { font-size: 14px; font-weight: 600; }
QLabel#FieldLabel { color: $SECONDARY; font-size: 12px; }
QLabel#ProgressTitle { font-size: 14px; font-weight: 600; }
QLabel#DialogTitle { font-size: 16px; font-weight: 600; }
QLabel#DialogSubtitle { color: $SECONDARY; font-size: 12px; }
QAbstractItemView#DialogList { background: $BACKGROUND; border: 1px solid $BORDER; border-radius: 8px; padding: 2px; }
QTreeView#DialogList::item, QListView#DialogList::item { height: 28px; }
QLabel#CoverBox { background: $FIELD; border: 1px solid $BORDER; border-radius: 8px; }
QSplitter::handle { background: transparent; }
QDialogButtonBox QPushButton { min-height: 26px; min-width: 84px; }
QPushButton#DialogPrimary { background: $ACCENT; color: $ACCENT_TEXT; border: none; font-weight: 600; }
QPushButton#DialogPrimary:hover { background: $ACCENT_HOVER; }
QPushButton#DialogPrimary:disabled { background: $BUTTON; color: $DISABLED; }
QLabel#ProgressCount { color: $SECONDARY; font-size: 12px; }
QProgressBar { background: $FIELD; border: none; border-radius: 4px; }
QProgressBar::chunk { background: $ACCENT; border-radius: 4px; }
QPushButton#ChipButton { padding: 3px 11px; min-width: 0; border-radius: 11px; }
QListWidget#SchemeChips { background: $FIELD; border: 1px solid $FIELD_BORDER; border-radius: 6px; padding: 4px; }
QListWidget#SchemeChips::item { background: $BUTTON; border-radius: 10px; padding: 3px 10px; margin: 2px; }
QListWidget#SchemeChips::item:hover { background: $HOVER; }
QWidget#PanelHost { background: $CHROME; }
QFrame#StepDivider { background: $BORDER; }
QMenu { background: $CHROME; color: $TEXT; border: 1px solid $BORDER; padding: 4px; }
QMenu::item { padding: 5px 22px; border-radius: 4px; }
QMenu::item:selected { background: $SELECTION; color: $TEXT; }
QMenu::item:disabled { color: $DISABLED; }
QMenu::separator { height: 1px; background: $BORDER; margin: 4px 6px; }
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background: $FIELD; color: $TEXT;
    border: 1px solid $FIELD_BORDER; border-radius: 6px;
    selection-background-color: $SELECTION; selection-color: $TEXT;
}
QLineEdit, QComboBox { min-height: 26px; padding: 0 6px; }
QComboBox:editable { background: $FIELD; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QLineEdit, QAbstractSpinBox QLineEdit {
    border: none; border-radius: 0; background: transparent; min-height: 0; padding: 0;
}
QAbstractItemView QLineEdit { min-height: 0; padding: 0; border-radius: 0; }
QLineEdit:focus, QComboBox:focus,
QTextEdit:focus, QPlainTextEdit:focus { border-color: $ACCENT; }
QLineEdit:disabled, QComboBox:disabled { color: $DISABLED; }
QAbstractItemView {
    background: $BACKGROUND; alternate-background-color: $ALTERNATE; color: $TEXT;
    border: none; outline: 0;
    selection-background-color: $SELECTION; selection-color: $TEXT;
}
QAbstractItemView::item { padding: 0 4px; }
QAbstractItemView::item:selected { background: $SELECTION; color: $TEXT; }
QAbstractItemView::item:selected:!active { background: $SELECTION; }
QHeaderView { background: $BACKGROUND; }
QHeaderView::section { background: $BACKGROUND; color: $SECONDARY; font-weight: 500;
    border: none; border-bottom: 1px solid $BORDER; padding: 6px 8px; }
QTableCornerButton::section { background: $BACKGROUND; border: none; }
QPushButton { background: $BUTTON; color: $TEXT; border: 1px solid $FIELD_BORDER;
    border-radius: 6px; padding: 4px 12px; min-width: 58px; }
QPushButton:hover { background: $HOVER; }
QPushButton:pressed { background: $SELECTION; }
QPushButton:default { border-color: $ACCENT; }
QPushButton:focus { border-color: $ACCENT; }
QPushButton:disabled { color: $DISABLED; }
QTabWidget::pane { border: 1px solid $BORDER; border-radius: 6px; }
QTabBar::tab { background: transparent; color: $SECONDARY; padding: 6px 12px;
    border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: $TEXT; border-bottom-color: $ACCENT; }
QGroupBox { border: 1px solid $BORDER; border-radius: 6px; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QStatusBar { background: $CHROME; border-top: 1px solid $BORDER; color: $SECONDARY; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $SECONDARY; padding: 0 6px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle { background: $BORDER; border-radius: 4px; margin: 2px; }
QScrollBar::handle:vertical { min-height: 28px; }
QScrollBar::handle:horizontal { min-width: 28px; }
QScrollBar::handle:hover { background: $FIELD_BORDER; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QToolTip { background: $CHROME; color: $TEXT; border: 1px solid $BORDER; }
""")


def style_sheet() -> str:
    return _STYLE.substitute(THEMES[CURRENT])


class AppStyle(QProxyStyle):
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
                return                          # the selected row is mark enough
            if not option.state & QStyle.StateFlag.State_KeyboardFocusChange:
                return
            painter.save()
            painter.setPen(QColor(globals()["ACCENT"]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)

    def drawComplexControl(self, control, option, painter, widget=None):
        super().drawComplexControl(control, option, painter, widget)
        if control == QStyle.ComplexControl.CC_SpinBox and option.frame:
            g = globals()
            color = g["ACCENT"] if option.state & QStyle.StateFlag.State_HasFocus else g["FIELD_BORDER"]
            painter.save()
            painter.setPen(QColor(color))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()


def apply_theme(app: QApplication, name: str = "mocha") -> None:
    """Apply a theme; the window modules imported afterwards use its colors."""
    use(name)
    if hasattr(app.styleHints(), "setColorScheme"):       # also colors native window frames
        app.styleHints().setColorScheme(Qt.ColorScheme.Light if CURRENT == "latte" else Qt.ColorScheme.Dark)
    app.setStyle(AppStyle(QStyleFactory.create("Fusion")))
    app.setPalette(app_palette())
    app.setStyleSheet(style_sheet())

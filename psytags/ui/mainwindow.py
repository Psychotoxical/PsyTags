"""Main window: menus, toolbar, tag panel, file list, filter and status bar."""
from __future__ import annotations

import contextlib
import copy
import os
import subprocess
import sys
import threading

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QActionGroup, QCursor, QDesktopServices, QIcon, QKeySequence,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDockWidget, QFileDialog,
                               QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMenu,
                               QMessageBox, QProgressBar, QProgressDialog, QStatusBar, QToolBar, QToolButton,
                               QToolTip,
                               QVBoxLayout, QWidget)

from .. import albumorder, config, convert, script, tags
from ..config import Options
from ..i18n import tr
from ..track import Track, fmt_length, fmt_size
from ..undo import Recorder, UndoStack
from .filelist import FileListModel, FileListView
from .docktitle import DockTitle
from .icons import icon
from .tagpanel import TagPanel, image_to_bytes

AUDIO_EXT = set(tags.SUPPORTED_EXTENSIONS)


class _HoverTips(QObject):
    """Shows the tooltips of the toolbar buttons itself: on Windows Qt's own hover tip often
    stayed away for these buttons, while asking for the tip directly always worked."""

    DELAY = 700

    def __init__(self, parent=None):
        super().__init__(parent)
        self.button = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.DELAY)
        self.timer.timeout.connect(self.show_tip)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.Enter:
            self.button = obj
            self.timer.start()
        elif kind in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Hide):
            self.timer.stop()
            QToolTip.hideText()
        elif kind == QEvent.Type.ToolTip:
            return True                             # no second tip from Qt
        return False

    def show_tip(self):
        b = self.button
        if b is not None and b.underMouse() and b.toolTip():
            QToolTip.showText(QCursor.pos(), b.toolTip(), b, b.rect())


class _StayingProgress(QProgressDialog):
    """Stays open and modal after Cancel until the running step has finished."""

    def __init__(self, text: str, maximum: int, parent):
        super().__init__(text, tr("Abbrechen"), 0, maximum, parent)
        self.stop = threading.Event()
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.canceled.disconnect(self.cancel)
        self.canceled.connect(self.request_stop)

    def request_stop(self):
        self.stop.set()
        self.setLabelText(tr("Wird abgebrochen ..."))

    def closeEvent(self, event):
        event.ignore()
        self.request_stop()

    def reject(self):
        self.request_stop()

    def finish(self):
        self.hide()
        self.deleteLater()
        if self.parentWidget() is not None:         # tooltips only appear in an active window
            self.parentWidget().activateWindow()


# ---------------------------------------------------------------------------
# Background directory reader

class Loader(QObject):
    progress = Signal(int, int)
    finished = Signal(list, bool)

    def __init__(self, paths: list[str], subfolders: bool, add: bool):
        super().__init__()
        self.paths, self.subfolders, self.add = paths, subfolders, add
        self.abort = False

    def run(self):
        files: list[str] = []
        for p in self.paths:
            if os.path.isfile(p):
                if os.path.splitext(p)[1].lower().lstrip(".") in AUDIO_EXT:
                    files.append(p)
                continue
            if self.subfolders:
                for root, dirs, names in os.walk(p):
                    dirs.sort(key=str.lower)
                    for n in sorted(names, key=str.lower):
                        if os.path.splitext(n)[1].lower().lstrip(".") in AUDIO_EXT:
                            files.append(os.path.join(root, n))
            else:
                try:
                    for n in sorted(os.listdir(p), key=str.lower):
                        full = os.path.join(p, n)
                        if os.path.isfile(full) and os.path.splitext(n)[1].lower().lstrip(".") in AUDIO_EXT:
                            files.append(full)
                except OSError:
                    pass
        out = []
        n = len(files)
        for i, f in enumerate(files, 1):
            if self.abort:
                break
            out.append(Track(f).load())
            if i % 25 == 0 or i == n:
                self.progress.emit(i, n)
        self.finished.emit(out, self.add)


# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, start_paths: list[str] | None = None):
        super().__init__()
        self.opts = Options.load()
        self.settings = config.settings()
        self.undo = UndoStack()
        self._group_rec: Recorder | None = None    # one undo step across several writes
        self._group_errors: list[str] = []
        self._auto_done: dict[int, Track] = {}     # finished by the automatic run; holding the
                                                   # tracks keeps their ids from being reused
        self._mood_done: dict[int, Track] = {}     # analyzed in this list, no need to run again
        self._last_batch: list = []
        self.current_dir = ""
        # isabs() also drops the single characters older versions stored by mistake.
        self.dir_history: list[str] = [d for d in config.string_list(self.settings, "dirs/history")
                                       if os.path.isabs(d)]
        self.back_stack: list[str] = []
        self.fwd_stack: list[str] = []
        self.tag_clipboard: list[tuple[dict, list]] = []
        self.last_action = None
        self._loader_thread = None
        self._panel_tracks: list[Track] = []

        self.setWindowTitle("PsyTags")
        self.setWindowIcon(icon("app"))
        self.model = FileListModel(config.load_columns())
        self.view = FileListView(self.model)
        self.setCentralWidget(self.view)
        self.model.edited.connect(self._list_edited)
        self.view.files_dropped.connect(lambda p, add: self.load_paths(p, add))
        self.view.context_menu.connect(self._context_menu)
        self.view.selectionModel().selectionChanged.connect(self._selection_changed)
        self.view.doubleClicked.connect(lambda i: None)
        self._restore_sort()
        self._cols_timer = QTimer(self)
        self._cols_timer.setSingleShot(True)
        self._cols_timer.setInterval(400)
        self._cols_timer.timeout.connect(lambda: config.save_columns(self.model.all_columns))
        self.view.columns_changed.connect(self._cols_timer.start)
        self.view.sort_changed.connect(self._save_sort)

        self._build_panel()
        self._build_filter()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._restore_state()
        self._update_actions()
        # Also persist while running, so nothing is lost if the session ends abruptly.
        self._autosave = QTimer(self)
        self._autosave.setInterval(20_000)
        self._autosave.timeout.connect(self.save_state)
        self._autosave.start()
        QApplication.instance().aboutToQuit.connect(self.save_state)

        paths = start_paths or []
        if not paths:
            last = self.settings.value("dirs/last", "")
            if self.opts.start_in_last_dir and last and os.path.isdir(last):
                paths = [last]
        if paths:
            QTimer.singleShot(0, lambda: self.load_paths(paths, False))

    # ------------------------------------------------------------------ layout
    def _build_panel(self):
        self.panel = TagPanel()
        self._rebuild_panel()
        self.panel.changed.connect(self._update_actions)
        self.panel.save_requested.connect(self.save_tags)
        self.panel.directory_chosen.connect(lambda d: self.load_paths([os.path.expanduser(d)], False))
        self.panel.cover.request.connect(self._cover_command)
        self.panel.cover.fetch_entries = self._cover_fetch_entries
        self.panel_dock = QDockWidget(tr("Tag-Panel"), self)
        self.panel_dock.setObjectName("TagPanel")
        self.panel_dock.setWidget(self.panel)
        self.panel_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                                    | QDockWidget.DockWidgetFeature.DockWidgetMovable
                                    | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.panel_dock.setTitleBarWidget(DockTitle(self.panel_dock))
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.panel_dock)

    def _build_filter(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.addWidget(QLabel(tr("Filter:")))
        self.filter_combo = QComboBox()
        self.filter_combo.setEditable(True)
        self.filter_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.filter_combo.addItems(config.string_list(self.settings, "filter/history"))
        self.filter_combo.setEditText("")
        self.filter_combo.setSizePolicy(self.filter_combo.sizePolicy().horizontalPolicy().Expanding,
                                        self.filter_combo.sizePolicy().verticalPolicy())
        lay.addWidget(self.filter_combo, 1)
        go = QToolButton()
        go.setArrowType(Qt.ArrowType.RightArrow)
        go.setAutoRaise(False)
        go.clicked.connect(self.apply_filter)
        lay.addWidget(go)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(300)
        self._filter_timer.timeout.connect(self.apply_filter)
        self.filter_combo.editTextChanged.connect(lambda _: self._filter_timer.start()
                                                  if self.act_filter_auto.isChecked() else None)
        self.filter_combo.lineEdit().returnPressed.connect(self.apply_filter)
        self.filter_dock = QDockWidget(tr("Filter"), self)
        self.filter_dock.setObjectName("Filter")
        self.filter_dock.setWidget(w)
        self.filter_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                                     | QDockWidget.DockWidgetFeature.DockWidgetMovable
                                     | QDockWidget.DockWidgetFeature.DockWidgetVerticalTitleBar)
        self.filter_dock.setTitleBarWidget(DockTitle(self.filter_dock, vertical=True))
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.filter_dock)
        self.filter_dock.visibilityChanged.connect(self._filter_visibility)

    def _filter_visibility(self, visible: bool):
        if not visible and self.model.filter_text and not self.filter_dock.isVisible():
            self.model.set_filter("")
            self._update_status()

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_msg = QLabel(tr("Bereit"))
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setMaximumHeight(14)
        self.progress.hide()
        self.status_sel = QLabel()
        self.status_all = QLabel()
        for l in (self.status_sel, self.status_all):
            l.setFrameShape(QLabel.Shape.Panel)
            l.setFrameShadow(QLabel.Shadow.Sunken)
            l.setContentsMargins(4, 0, 4, 0)
        sb.addWidget(self.status_msg, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.status_sel)
        sb.addPermanentWidget(self.status_all)
        self._update_status()

    # ------------------------------------------------------------------ actions
    def _act(self, text, slot=None, shortcut=None, tip="", icon_name=None, checkable=False,
             extra_shortcuts=()) -> QAction:
        a = QAction(tr(text), self)
        if icon_name:
            a.setIcon(icon(icon_name))
        keys = []
        if shortcut:
            keys.append(QKeySequence(shortcut))
        keys += [QKeySequence(k) for k in extra_shortcuts]
        if keys:
            a.setShortcuts(keys)
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        if tip:
            a.setStatusTip(tr(tip))
            a.setToolTip(tr(text).replace("&", "").replace("...", ""))
        a.setCheckable(checkable)
        if slot is not None:
            a.triggered.connect(slot)
        self.addAction(a)
        return a

    def _build_actions(self):
        A = self._act
        # File
        self.act_save = A("Tag &speichern", self.save_tags, "Ctrl+S", "Speichert den Tag in ausgewählten Dateien.", "save")
        self.act_remove = A("Tag ent&fernen", self.remove_tags, "Ctrl+R", "Entfernt den Tag aus den ausgewählten Dateien.", "remove")
        self.act_read = A("Tag &auslesen", self.read_tags, "Ctrl+T", "Lädt den Tag der markierten Datei in die Eingabefelder im Tag-Panel.")
        self.act_dir = A("Verzeichnis wechseln...", self.choose_directory, "Ctrl+D", "Verzeichnis wechseln...", "folder-open")
        self.act_add_dir = A("Verzeichnis hinzufügen...", self.add_directory, "Ctrl+H", "Fügt der Dateiansicht ein Verzeichnis hinzu.", "folder-add")
        self.act_up = A("Übergeordnetes Verzeichnis", self.dir_up, "Ctrl+Shift+D", "Wechselt in das übergeordnete Verzeichnis.", "folder-up")
        self.act_fav = A("Standardverzeichnis", self.favorite_dir, "Ctrl+M", "Wechselt in das eingestellte Standardverzeichnis.", "favorite")
        self.act_open_fm = A("Im Dateimanager öffnen", self.open_in_file_manager, None, "Öffnet die ausgewählten Dateien im Dateimanager.")
        self.act_options = A("&Optionen...", self.show_options, "Ctrl+O", "Zeigt den Optionendialog an.", "options")
        self.act_open_cfg = A("Konfigurationsordner öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(config.config_dir())))
        self.act_exit = A("&Beenden", self.close, "Alt+F4", "Beendet die Anwendung.")
        self.act_refresh = A("&Aktualisieren", self.refresh, "F5", "Aktualisiert die Dateiansicht.", "refresh")
        self.act_back = A("Zurück", self.dir_back, "Alt+Left")
        self.act_fwd = A("Vorwärts", self.dir_forward, "Alt+Right")
        # Edit
        self.act_undo = A("&Rückgängig", self.do_undo, "Ctrl+Z", "Macht die letzte Aktion rückgängig.", "undo",
                          extra_shortcuts=["Ctrl+Shift+Z"])
        self.act_redo = A("&Wiederholen", self.do_redo, "Ctrl+Y", "Wiederholt die letzte rückgängig gemachte Aktion.", "redo")
        self.act_cut = A("Au&sschneiden", self.cut, "Ctrl+X", "Schneidet die Textauswahl oder den Tag der ausgewählten Datei aus.")
        self.act_copy = A("K&opieren", self.copy, "Ctrl+C", "Kopiert die Textauswahl oder den Tag der ausgewählten Datei.")
        self.act_paste = A("&Einfügen", self.paste, "Ctrl+V", "Fügt den Inhalt der Zwischenablage ein.")
        self.act_find = A("S&uchen...", self.find, "Ctrl+F", "Sucht Dateien in der Dateiliste.")
        self.act_rename = A("Umbenennen", self.view.edit_first_editable, "F2", "Benennt die ausgewählte Datei um.")
        self.act_remove_files = A("E&ntfernen", self.remove_from_list, "Del", "Entfernt die ausgewählten Dateien aus der Dateiliste.")
        self.act_delete = A("Löschen...", lambda: self.delete_files(False), None, "Löscht die ausgewählten Dateien.",
                            extra_shortcuts=["Ctrl+Del"])
        self.act_delete_perm = A("Endgültig löschen...", lambda: self.delete_files(True), "Ctrl+Shift+Del")
        self.act_select_all = A("&Alle Dateien auswählen", self.view.selectAll, "Ctrl+A", "Wählt alle Dateien in der Dateiansicht aus.")
        self.act_invert = A("Auswahl &umkehren", self.invert_selection, "Ctrl+Shift+A", "Kehrt die aktuelle Auswahl um.")
        self.act_unselect = A("Auswahl auf&heben", self.view.clearSelection, "Ctrl+U", "Hebt die aktuelle Auswahl auf.")
        self.act_next = A("&Nächste Datei auswählen", self.select_next, "Ctrl+N", "Markiert die nächste Datei in der Dateiansicht.",
                          extra_shortcuts=["Ctrl+Shift+N"])
        self.act_similar = A("Ähnliche Dateien auswählen", lambda: self.select_similar(False), "Ctrl+G", "Wählt ähnliche Dateien basierend auf dem Sortierkriterium aus.")
        self.act_similar_next = A("Nächste ähnliche Dateien auswählen", lambda: self.select_similar(True), "Ctrl+Shift+G")
        # Cover
        self.act_cover_add = A("Cover hinzu&fügen...", lambda: self._cover_command("add"), "Ctrl+Alt+A")
        self.act_cover_replace = A("Cover er&setzen...", lambda: self._cover_command("replace"))
        self.act_cover_adjust = A("Cover anpassen...", lambda: self._cover_command("adjust"))
        self.act_cover_remove = A("Cover entfe&rnen", lambda: self._cover_command("remove"))
        self.act_cover_extract = A("Cover &extrahieren...", lambda: self._cover_command("extract"))
        self.act_cover_manage = A("Cover &verwalten...", lambda: self._cover_command("manage"), "Ctrl+Alt+M")
        # View
        self.act_ext_tags = A("&Erweiterte Tags...", self.extended_tags, "Alt+T", "Zeigt den erweiterten Tag-Dialog an.", "extended")
        self.act_panel = self.panel_dock.toggleViewAction()
        self.act_panel.setText(tr("&Tag-Panel"))
        self.act_panel.setShortcut(QKeySequence("Ctrl+Q"))
        self.addAction(self.act_panel)
        self.act_filter = self.filter_dock.toggleViewAction()
        self.act_filter.setText(tr("&Filter"))
        self.act_filter.setShortcut(QKeySequence("F3"))
        self.act_filter.triggered.connect(lambda on: self.filter_combo.setFocus() if on else None)
        self.addAction(self.act_filter)
        self.act_filter_auto = A("Filter automatisch anwenden", None, checkable=True)
        self.act_filter_auto.setChecked(self.settings.value("filter/auto", True) in (True, "true"))
        self.act_customize_cols = A("Spalten anpassen...", self.customize_columns)
        self.act_customize_panel = A("Tag-Panel anpassen...", self.customize_panel)
        self.act_autofit = A("Spaltenbreiten anpassen", self.autofit_columns, "Ctrl++",
                             extra_shortcuts=["Ctrl+="])
        # Convert
        self.act_ttf = A("&Tag - Dateiname", self.tag_to_filename, "Alt+1", "Benennt Dateien anhand des Tags nach einem definierten Muster um.", "tag-filename",
                         extra_shortcuts=["Alt+Shift+1"])
        self.act_wizard = A("Tracknummern-Assistent...", self.numbering_wizard, "Ctrl+K", "Startet den Assistenten zum Schreiben von Track- und Discnummern.", "numbering",
                            extra_shortcuts=["Ctrl+Shift+K"])
        # Actions
        # Tag sources
        self.act_last_source = A("Zuletzt verwendete Tag-Quelle", lambda: self.run_last_source(False),
                                 "Ctrl+I", "Führt die zuletzt verwendete Tag-Quelle aus.", "web")
        self.act_last_source_quick = A("Zuletzt verwendete Tag-Quelle (Schnell)",
                                       lambda: self.run_last_source(True), "Ctrl+Shift+I")
        self.act_lastfm = A("Genres von Last.fm holen",
                            lambda: self.fetch_lastfm(self.view.selected_tracks()), "Ctrl+Shift+L",
                            "Holt Genres für die ausgewählten Dateien, ohne Tag-Quelle.",
                            "genres")
        self.act_moods = A("Moods analysieren", self.analyze_all_moods, "Ctrl+Shift+M",
                           "Ermittelt die Moods aller Dateien in der Liste aus dem Audio.", "moods")
        self.act_auto_mb = A("MusicBrainz automatisch", self.auto_musicbrainz, "Ctrl+Shift+B",
                             "Taggt das markierte Album, wenn es sicher erkannt wird, sonst öffnet sich die Trefferliste.",
                             "auto-album")
        self.act_auto_all = A("Alle Alben automatisch", self.auto_all_albums, "Ctrl+Alt+B",
                              "Analysiert die Moods und taggt alle Alben der Liste; unsichere Alben bleiben unverändert.",
                              "auto-all")
        self.act_batch_summary = A("Übersicht des letzten Laufs...", self.show_batch_summary, None,
                                   "Zeigt das Ergebnis des letzten automatischen Laufs.", "batch-summary")
        # Tools / misc
        self.act_reset_inputs = A("Alle &Eingabefelder zurücksetzen", self.panel.reset_inputs, "Ctrl+B")
        self.act_default_inputs = A("Eingabefelder auf Standard&werte", self.panel.default_inputs, "Ctrl+W")
        self.act_play = A("Abspielen", self.play, "F4", "Spielt die ausgewählten Dateien ab.", extra_shortcuts=["Ctrl+Shift+T"])
        self.act_props = A("Eigenschaften...", self.properties, "Alt+Return", "Zeigt die Eigenschaften der ausgewählten Datei an.")
        # Help
        self.act_help = A("&Hilfethemen", lambda: __import__("psytags.ui.help", fromlist=["x"]).show_help(self), "F1", "", "help")
        self.act_keys = A("&Tastaturkürzel", lambda: __import__("psytags.ui.help", fromlist=["x"]).show_shortcuts(self))
        self.act_about = A("Über PsyTags...", self.about)
        # Focus cycling between panes
        QShortcut(QKeySequence("Ctrl+Tab"), self, lambda: self._cycle_focus(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, lambda: self._cycle_focus(-1))

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu(tr("&Datei"))
        for a in (self.act_save, self.act_remove, self.act_read, None, self.act_dir, self.act_add_dir,
                  self.act_fav, self.act_open_fm, None, self.act_options, self.act_open_cfg, None, self.act_exit):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu(tr("&Bearbeiten"))
        for a in (self.act_undo, self.act_redo, None, self.act_cut, self.act_copy,
                  self.act_paste, None, self.act_find, None):
            m.addSeparator() if a is None else m.addAction(a)
        cm = m.addMenu(tr("Cover"))
        for a in (self.act_cover_add, self.act_cover_replace, self.act_cover_adjust,
                  self.act_cover_remove, self.act_cover_extract, None, self.act_cover_manage):
            cm.addSeparator() if a is None else cm.addAction(a)
        m.addSeparator()
        for a in (self.act_rename, self.act_remove_files,
                  self.act_delete, None, self.act_select_all, self.act_invert, self.act_unselect,
                  self.act_next, self.act_similar, self.act_similar_next):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu(tr("A&nsicht"))
        m.addAction(self.act_refresh)
        self.sort_menu = m.addMenu(tr("&Sortieren nach"))
        self.sort_menu.aboutToShow.connect(self._fill_sort_menu)
        m.addSeparator()
        m.addAction(self.act_ext_tags)
        m.addAction(self.act_panel)
        m.addAction(self.act_filter)
        m.addAction(self.act_filter_auto)
        tb = m.addMenu(tr("Sym&bolleisten"))
        self.toolbar_menu = tb
        cols = m.addMenu(tr("Spalte&n"))
        self.columns_menu = cols
        cols.aboutToShow.connect(self._fill_columns_menu)
        m.addAction(self.act_customize_panel)

        m = mb.addMenu(tr("&Konverter"))
        for a in (self.act_ttf, self.act_wizard):
            m.addAction(a)

        m = mb.addMenu(tr("Tag-&Quellen"))
        self.sources_menu = m
        m.aboutToShow.connect(self._fill_sources_menu)

        m = mb.addMenu(tr("&Hilfe"))
        for a in (self.act_help, self.act_keys, None, self.act_about):
            m.addSeparator() if a is None else m.addAction(a)

    def _build_toolbar(self):
        tb = QToolBar(tr("&Hauptsymbolleiste"), self)
        tb.setObjectName("MainToolbar")
        tb.setIconSize(QSize(42, 42))
        tb.setMovable(True)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        for a in (self.act_save, self.act_remove, self.act_undo, self.act_redo, None,
                  self.act_dir, self.act_add_dir, self.act_up, self.act_fav,
                  self.act_refresh, None, self.act_ttf, None,
                  self.act_ext_tags, None,
                  self.act_wizard, None, self.act_moods, self.act_auto_mb, self.act_auto_all, self.act_batch_summary,
                  self.act_last_source, self.act_lastfm, None,
                  self.act_options):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.toolbar = tb
        self._hover_tips = _HoverTips(self)
        for a in tb.actions():
            button = tb.widgetForAction(a)
            if button is not None:
                button.installEventFilter(self._hover_tips)
        btn = tb.widgetForAction(self.act_last_source)
        if isinstance(btn, QToolButton):
            self.sources_popup = QMenu(self)
            self.sources_popup.aboutToShow.connect(lambda: self._fill_sources_submenu(self.sources_popup))
            btn.setMenu(self.sources_popup)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._update_last_source_tip()
        self.toolbar_menu.addAction(tb.toggleViewAction())
        tb.toggleViewAction().setText(tr("&Hauptsymbolleiste"))

    def _restore_state(self):
        g = self.settings.value("window/geometry")
        if g is not None:
            self.restoreGeometry(g)
        else:
            self.resize(1400, 850)
        s = self.settings.value("window/state")
        if s is not None:
            self.restoreState(s)
        w = self.settings.value("window/panel_width")
        if w:
            self.resizeDocks([self.panel_dock], [int(w)], Qt.Orientation.Horizontal)
        else:
            self.resizeDocks([self.panel_dock], [355], Qt.Orientation.Horizontal)
        self.filter_dock.setVisible(self.settings.value("window/filter_visible", "true") in (True, "true"))

    def closeEvent(self, e):
        if self.panel.dirty and self.panel.tracks:
            self.save_tags()
        self.save_state()
        super().closeEvent(e)

    def save_state(self) -> None:
        """Persist everything the user arranged; called on close, on quit and periodically."""
        config.save_columns(self.model.all_columns)
        self._save_sort()
        if not self.isMinimized():
            self.settings.setValue("window/geometry", self.saveGeometry())
            self.settings.setValue("window/state", self.saveState())
            if self.panel_dock.isVisible() and not self.panel_dock.isFloating():
                self.settings.setValue("window/panel_width", self.panel_dock.width())
        self.settings.setValue("window/filter_visible", self.filter_dock.isVisible())
        self.settings.setValue("filter/auto", self.act_filter_auto.isChecked())
        self.settings.setValue("dirs/last", self.current_dir)
        self.settings.setValue("dirs/history", self.dir_history[:30])
        self.settings.sync()

    def _save_sort(self) -> None:
        m = self.model
        self.settings.setValue("filelist/sort", [f"{int(d)}\t{m.columns[c - 1].value}"
                                                 for c, d in m.sort_keys if 0 < c <= len(m.columns)])

    def _restore_sort(self) -> None:
        raw = self.settings.value("filelist/sort") or []
        if isinstance(raw, str):
            raw = [raw]
        values = [c.value for c in self.model.columns]
        keys = []
        for item in raw:
            d, _, value = str(item).partition("\t")
            if value in values:
                keys.append((values.index(value) + 1, d == "1"))
        self.model.sort_keys = keys

    # ------------------------------------------------------------------ status
    def _update_status(self):
        sel = self.view.selected_tracks() if hasattr(self, "view") else []
        rows = self.model.rows

        def seg(ts):
            secs = int(round(sum(t.data.info.length for t in ts)))
            h, rem = divmod(secs, 3600)
            return f"{len(ts)} ({h:02d}:{rem // 60:02d}:{rem % 60:02d} | " \
                   f"{fmt_size(sum(t.size for t in ts))})"
        self.status_sel.setText(seg(sel))
        if self.model.filter_text:
            self.status_all.setText(f"{len(rows)}/{len(self.model.all)} "
                                    + seg(rows)[len(str(len(rows))) + 1:])
        else:
            self.status_all.setText(seg(rows))

    def message(self, text: str, timeout: int = 0):
        self.status_msg.setText(text or tr("Bereit"))
        if timeout:
            QTimer.singleShot(timeout, lambda: self.status_msg.setText(tr("Bereit")))

    def _update_actions(self):
        has_sel = bool(self.view.selectionModel().hasSelection())
        for a in (self.act_remove, self.act_read, self.act_cut, self.act_copy,
                  self.act_rename, self.act_remove_files, self.act_delete, self.act_ttf,
                  self.act_wizard, self.act_ext_tags, self.act_play,
                  self.act_props, self.act_cover_add, self.act_lastfm,
                  self.act_auto_mb):
            a.setEnabled(has_sel)
        for a in (self.act_moods, self.act_auto_all):
            a.setEnabled(bool(self.model.rows))
        self.act_batch_summary.setEnabled(bool(self._last_batch))
        self.act_save.setEnabled(has_sel)
        self.act_undo.setEnabled(self.undo.can_undo())
        self.act_redo.setEnabled(self.undo.can_redo() or self.last_action is not None)
        self.act_back.setEnabled(bool(self.back_stack))
        self.act_fwd.setEnabled(bool(self.fwd_stack))

    # ------------------------------------------------------------------ loading
    def load_paths(self, paths: list[str], add: bool):
        paths = [os.path.abspath(p) for p in paths if p and os.path.exists(p)]
        if not paths:
            return
        if self.panel.dirty and self.panel.tracks:
            self.save_tags()
        if not add:
            # Several folders dropped: like Mp3tag, the first one becomes the working directory.
            d = paths[0] if os.path.isdir(paths[0]) else os.path.dirname(paths[0])
            if self.current_dir and self.current_dir != d:
                self.back_stack.append(self.current_dir)
                self.fwd_stack.clear()
            self._set_current_dir(d)
        if self._loader_thread is not None:
            self._loader.abort = True
            self._loader_thread.quit()
            self._loader_thread.wait()
        self.message(tr("Einlesen des Verzeichnisses"))
        self.progress.setValue(0)
        self.progress.show()
        self._loader = Loader(paths, self.opts.subfolders, add)
        th = QThread(self)
        self._loader.moveToThread(th)
        th.started.connect(self._loader.run)
        self._loader.progress.connect(self._load_progress)
        self._loader.finished.connect(self._load_finished)
        self._loader.finished.connect(th.quit)
        self._loader_thread = th
        th.start()

    def _set_current_dir(self, d: str):
        self.current_dir = d
        convert.working_dir = d
        if d in self.dir_history:
            self.dir_history.remove(d)
        self.dir_history.insert(0, d)
        self.panel.set_directories(d, self.dir_history)
        self.setWindowTitle(f"PsyTags  -  {d}")
        self.settings.setValue("dirs/last", d)
        self.settings.setValue("dirs/history", self.dir_history[:30])

    def _load_progress(self, i, n):
        self.progress.setMaximum(n)
        self.progress.setValue(i)
        self.message(tr("Lese Tag-Informationen ... {1} von {2}", i, n))

    def _load_finished(self, tracks: list[Track], add: bool):
        self.progress.hide()
        self._loader_thread = None
        tracks = albumorder.loaded_order(tracks, self._loader.paths)
        if not add:
            self._auto_done.clear()
            self._mood_done.clear()
        if add:
            self.model.add_tracks(tracks)
        else:
            self.model.set_tracks(tracks)
        self.view.apply_widths()
        self.message("")
        self._selection_changed()

    def choose_directory(self):
        d = QFileDialog.getExistingDirectory(self, tr("Verzeichnis auswählen"), self.current_dir
                                             or os.path.expanduser("~"))
        if d:
            self.load_paths([d], False)

    def add_directory(self):
        d = QFileDialog.getExistingDirectory(self, tr("Verzeichnis hinzufügen..."), self.current_dir
                                             or os.path.expanduser("~"))
        if d:
            self.load_paths([d], True)

    def refresh(self):
        sel = [t.path for t in self.view.selected_tracks()]
        # F5 reloads the working directory, even when the list is empty right now.
        if self.current_dir and os.path.isdir(self.current_dir):
            self.load_paths([self.current_dir], False)
        else:
            dirs = sorted({os.path.dirname(t.path) for t in self.model.all})
            if not dirs:
                return
            self.load_paths(dirs, False)
        QTimer.singleShot(400, lambda: self.view.select_tracks(
            [t for t in self.model.rows if t.path in sel]))

    def dir_up(self):
        if self.current_dir:
            parent = os.path.dirname(self.current_dir.rstrip(os.sep))
            if parent and parent != self.current_dir:
                self.load_paths([parent], False)

    def dir_back(self):
        if self.back_stack:
            self.fwd_stack.append(self.current_dir)
            d = self.back_stack.pop()
            self.current_dir = ""
            self.load_paths([d], False)

    def dir_forward(self):
        if self.fwd_stack:
            self.back_stack.append(self.current_dir)
            d = self.fwd_stack.pop()
            self.current_dir = ""
            self.load_paths([d], False)

    def favorite_dir(self):
        d = self.opts.favorite_dir or QStandardPathsMusic()
        if d and os.path.isdir(d):
            self.load_paths([d], False)

    # ------------------------------------------------------------------ selection
    def _selection_changed(self, *_):
        new = self.view.selected_tracks()
        if self.panel.dirty and self._panel_tracks and self.opts.save_on_selection_change \
                and [id(t) for t in new] != [id(t) for t in self._panel_tracks]:
            self._write_panel(self._panel_tracks)
        self._panel_tracks = new
        self.panel.load(new)
        self._update_status()
        self._update_actions()

    def invert_selection(self):
        sel = {id(t) for t in self.view.selected_tracks()}
        self.view.select_tracks([t for t in self.model.rows if id(t) not in sel])

    def select_next(self):
        rows = self.view.selected_rows()
        r = (rows[-1] + 1) if rows else 0
        if r < self.model.rowCount():
            self.view.select_tracks([self.model.rows[r]])

    def select_similar(self, next_group: bool):
        rows = self.model.rows
        if not rows:
            return
        sel_rows = self.view.selected_rows()
        if not self.model.sort_keys:
            return
        col = self.model.sort_keys[0][0]
        expr = self.model.columns[col - 1].sort or self.model.columns[col - 1].value
        start = sel_rows[0] if sel_rows else 0
        key = script.format(expr, rows[start])
        if next_group:
            i = (sel_rows[-1] + 1) if sel_rows else 0
            while i < len(rows) and script.format(expr, rows[i]) == key:
                i += 1
            if i >= len(rows):
                return
            key = script.format(expr, rows[i])
        self.view.select_tracks([t for t in rows if script.format(expr, t) == key])

    def _cycle_focus(self, d: int):
        order = [self.panel, self.filter_combo, self.view]
        order = [w for w in order if w.isVisible()]
        fw = QApplication.focusWidget()
        idx = 0
        for i, w in enumerate(order):
            if fw is w or (fw is not None and w.isAncestorOf(fw)):
                idx = i
        nxt = order[(idx + d) % len(order)]
        if nxt is self.panel:
            self.panel.focus_first()
        else:
            nxt.setFocus()

    # ------------------------------------------------------------------ writing
    def _write(self, label: str, tracks: list[Track], mutate) -> int:
        """Apply ``mutate(track)`` to every track, save it, and record undo."""
        rec = self._group_rec or Recorder(label)
        errors = []
        n = len(tracks)
        self.progress.setMaximum(max(1, n))
        self.progress.show()
        for i, t in enumerate(tracks, 1):
            rec.before(t)
            try:
                if mutate(t) is not False and t.modified:
                    t.save(self.opts.id3_version, self.opts.write_id3v1, self.opts.keep_mtime)
            except Exception as e:
                t.revert()
                errors.append(f"{t.filename}: {e}")
            if n > 20:
                self.progress.setValue(i)
                self.message(tr("Schreibe Tag-Informationen ... {1} von {2}", i, n))
                QApplication.processEvents()
        self.progress.hide()
        if self._group_rec is None:
            self.undo.push(rec.finish())
        self.model.refresh_tracks(tracks)
        self.message("")
        if errors and self._group_rec is not None:
            self._group_errors += errors
        elif errors:
            QMessageBox.warning(self, tr("Fehler"), "\n".join(errors[:30]))
        self._update_actions()
        return n - len(errors)

    @contextlib.contextmanager
    def _undo_group(self, label: str):
        """All writes inside form one undo step; write errors are collected, not shown."""
        self._group_rec, self._group_errors = Recorder(label), []
        try:
            yield
        finally:
            rec, self._group_rec = self._group_rec, None
            self.undo.push(rec.finish())
            self._update_actions()

    def _write_panel(self, tracks: list[Track]) -> bool:
        """Write the panel inputs to ``tracks``. Returns False if a file failed;
        the inputs then stay dirty so they are not lost."""
        pending = self.panel.pending()
        covers = self.panel.cover.covers if self.panel.covers_dirty else None

        def apply(t: Track):
            for name, value in pending.items():
                t.set(name, value or "")
            if covers is not None:
                t.data.covers = list(covers)
        ok = self._write(tr("Tag speichern"), tracks, apply) == len(tracks)
        if ok:
            self.panel.clear_dirty()
        return ok

    def save_tags(self):
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        if self._write_panel(tracks):
            self.panel.load(tracks)
        self.message(tr("Tag-Informationen gespeichert"), 3000)

    def read_tags(self):
        tracks = self.view.selected_tracks()
        for t in tracks:
            t.load()
        self.model.refresh_tracks(tracks)
        self.panel.load(tracks)

    def remove_tags(self):
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        if QMessageBox.question(self, "PsyTags", tr("Möchten Sie den Tag wirklich aus {1} Datei(en) entfernen?",
                                                   len(tracks))) != QMessageBox.StandardButton.Yes:
            return
        rec = Recorder(tr("Tag entfernen"))
        for t in tracks:
            rec.before(t)
            try:
                t.remove_tags()
            except Exception as e:
                QMessageBox.warning(self, tr("Fehler"), f"{t.filename}: {e}")
        self.undo.push(rec.finish())
        self.model.refresh_tracks(tracks)
        self.panel.load(tracks)
        self._update_actions()

    def _list_edited(self, t: Track, name: str, old: str, new: str):
        if name in ("_FILENAME_EXT", "_FILENAME"):
            if name == "_FILENAME":
                new = new + os.path.splitext(t.path)[1]
            self._rename([(t, os.path.join(t.folder, new))], tr("Umbenennen"))
            return
        self._write(tr("Bearbeiten"), [t], lambda tr_: tr_.set(name, new))
        self.panel.load(self.view.selected_tracks())

    # ------------------------------------------------------------------ undo
    def _run_undo(self, fn):
        ops = self.undo.undo_ops if fn == self.undo.undo else self.undo.redo_ops
        op = ops[-1] if ops else None
        try:
            fn(self.opts)
        except Exception as e:
            QMessageBox.warning(self, tr("Fehler"), str(e))
        if op:
            self.model.refresh_tracks([c.track for c in op.changes])
            self.panel.load(self.view.selected_tracks())

    def do_undo(self):
        self._run_undo(self.undo.undo)
        self._update_actions()

    def do_redo(self):
        if self.undo.can_redo():
            self._run_undo(self.undo.redo)
        elif self.last_action is not None:
            self.last_action()
        self._update_actions()

    # ------------------------------------------------------------------ clipboard
    def _text_focus(self):
        fw = QApplication.focusWidget()
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return fw
        return None

    def copy(self):
        w = self._text_focus()
        if w is not None:
            w.copy()
            return
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        self.tag_clipboard = [(copy.deepcopy(t.data.fields), list(t.data.covers)) for t in tracks]
        lines = []
        for t in tracks:
            lines.append(script.format(config.history("copy_text")[0], t))
        QApplication.clipboard().setText("\n".join(lines))
        self.message(tr("Tag von {1} Datei(en) kopiert", len(tracks)), 3000)

    def cut(self):
        w = self._text_focus()
        if w is not None:
            w.cut()
            return
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        self.copy()

        def clear(t):
            t.data.fields.clear()
            t.data.covers = []
        self._write(tr("Ausschneiden"), tracks, clear)
        self.panel.load(tracks)

    def paste(self):
        w = self._text_focus()
        if w is not None:
            w.paste()
            return
        tracks = self.view.selected_tracks()
        if not tracks or not self.tag_clipboard:
            return
        clip = self.tag_clipboard

        def apply(t, i=[0]):
            fields, covers = clip[min(i[0], len(clip) - 1)] if len(clip) > 1 else clip[0]
            i[0] += 1
            t.data.fields = copy.deepcopy(fields)
            t.data.covers = list(covers)
        self._write(tr("Einfügen"), tracks, apply)
        self.panel.load(tracks)

    # ------------------------------------------------------------------ converters
    def _rename(self, pairs: list[tuple[Track, str]], label: str, remove_old_albums: bool = False):
        rec = Recorder(label)
        errors = []
        moves = []
        for t, new in pairs:
            rec.before(t)
            try:
                old = t.path
                convert.rename(t, new)
                moves.append((old, t.path))
            except Exception as e:
                errors.append(f"{t.filename}: {e}")
        self.undo.push(rec.finish())
        self.model.refresh_tracks([t for t, _ in pairs])
        if errors:
            QMessageBox.warning(self, tr("Fehler"), "\n".join(errors[:30]))
        if remove_old_albums:
            self._trash_old_albums(moves)
        self._update_actions()

    def _trash_old_albums(self, moves: list[tuple[str, str]]) -> None:
        """The albums now live in their new folders: the old ones, with whatever is left in them
        (images, cue sheets, ...), go to the recycle bin."""
        from PySide6.QtCore import QFile
        convert.fix_folder_case(moves)
        leftovers = convert.emptied_album_folders(moves) + convert.leftovers_in_renamed_albums(moves)
        failed = [f for f in leftovers if not QFile.moveToTrash(f)]
        if len(leftovers) > len(failed):
            self.message(tr("{1} alte Ordner oder Dateien in den Papierkorb verschoben", len(leftovers) - len(failed)), 8000)
        if failed:
            QMessageBox.warning(self, tr("Fehler"), tr("Diese Ordner konnten nicht entfernt werden:\n{1}", "\n".join(failed)))

    def tag_to_filename(self):
        from .dialogs.converters import TagToFilenameDialog
        tracks = self.view.selected_tracks()
        d = TagToFilenameDialog(tracks, self)
        if d.exec():
            fmt = d.format()
            whole_albums = "\\" in fmt or "/" in fmt      # a format with folders moves the album
            self._rename([(t, convert.tag_to_filename(t, fmt)) for t in tracks], tr("Tag - Dateiname"),
                         remove_old_albums=whole_albums)
            self.last_action = lambda: self._rename(
                [(t, convert.tag_to_filename(t, fmt)) for t in self.view.selected_tracks()],
                tr("Tag - Dateiname"), remove_old_albums=whole_albums)

    def numbering_wizard(self):
        from .dialogs.numbering import NumberingWizard
        tracks = self.view.selected_tracks()
        shift = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        d = NumberingWizard(tracks, self, per_folder=shift)
        if d.exec():
            plan = d.plan()
            self._write(tr("Tracknummern-Assistent"), tracks,
                        lambda t: [t.set(k, v) for k, v in plan.get(id(t), {}).items()])
            self.panel.load(tracks)

    # ------------------------------------------------------------------ actions
    # ------------------------------------------------------------------ tag sources
    def _fill_sources_menu(self):
        m = self.sources_menu
        m.clear()
        self._add_source_entries(m)
        m.addSeparator()
        self._add_cover_source_menu(m)
        m.addAction(tr("Cover-Mindestgröße ({1} px)...", self._cover_min_size()), self.set_cover_min_size)
        m.addSeparator()
        for a in (self.act_moods, self.act_auto_mb, self.act_auto_all, self.act_batch_summary):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_lastfm)
        m.addAction(tr("Genres von Last.fm..."), self.lastfm_settings)
        m.addAction(tr("Discogs-Zugang..."), self.discogs_token)

    def _add_cover_source_menu(self, m: QMenu) -> None:
        """Which source supplies the cover after a tag import (e.g. Apple Music after MusicBrainz)."""
        from ..sources import list_sources
        current = self.settings.value("tagsources/cover_source", "")
        if current and os.path.exists(current):
            label = os.path.splitext(os.path.basename(current))[0].replace("&", "").replace("#", " – ")
            a = m.addAction(tr("Nur Cover holen von {1}", label),
                            lambda: self.fetch_cover_from_source(self.view.selected_tracks()))
            a.setEnabled(bool(self.view.selected_tracks()))
        sub = m.addMenu(tr("Cover anschließend holen von"))
        group = QActionGroup(sub)
        a = sub.addAction(tr("(nicht automatisch)"))
        a.setCheckable(True)
        a.setChecked(not current)
        a.triggered.connect(lambda: self.settings.setValue("tagsources/cover_source", ""))
        group.addAction(a)
        sub.addSeparator()
        for name, path in list_sources():
            a = sub.addAction(name.replace("&", "").replace("#", " – "))
            a.setCheckable(True)
            a.setChecked(path == current)
            a.triggered.connect(lambda _=False, p=path: self.settings.setValue("tagsources/cover_source", p))
            group.addAction(a)

    def _cover_min_size(self) -> int:
        try:
            return int(self.settings.value("tagsources/cover_min_size", 1000))
        except (TypeError, ValueError):
            return 1000

    def set_cover_min_size(self) -> None:
        n, ok = QInputDialog.getInt(self, tr("Cover-Mindestgröße"),
                                    tr("Cover aus Tag-Quellen nur übernehmen ab (Pixel, 0 = immer):"),
                                    self._cover_min_size(), 0, 10000, 100)
        if ok:
            self.settings.setValue("tagsources/cover_min_size", n)

    def _cover_big_enough(self, data: bytes | None, label: str, ask: bool = False) -> bool:
        """False (with a status message) if a downloaded cover is below the minimum size.
        With ``ask`` the user may take it anyway."""
        if not data:
            return False
        from PySide6.QtGui import QImage
        img = QImage.fromData(data)
        n = self._cover_min_size()
        if img.isNull() or (img.width() >= n and img.height() >= n):
            return True
        if ask and QMessageBox.question(
                self, label, tr("Das Cover von {1} ist nur {2}x{3} groß (Mindestgröße {4}). "
                                "Trotzdem übernehmen?", label, img.width(), img.height(), n)) \
                == QMessageBox.StandardButton.Yes:
            return True
        self.message(tr("Cover von {1} zu klein ({2}x{3}, mindestens {4}) – nicht übernommen",
                        label, img.width(), img.height(), n), 8000)
        return False

    def _manual_cover_source(self) -> str:
        """Source for the cover context menu: the configured cover source, else Apple Music."""
        from ..sources import list_sources
        path = self.settings.value("tagsources/cover_source", "")
        if path and os.path.exists(path):
            return path
        return next((p for name, p in list_sources() if "apple" in name.lower()), "")

    def _mb_cover_source(self) -> str:
        """MusicBrainz source for the cover context menu: the cover-art one, else the plain one."""
        from ..sources import list_sources
        srcs = {name.replace("&", "").lower(): p for name, p in list_sources()}
        return srcs.get("cover art#musicbrainz") or srcs.get("musicbrainz") or ""

    def _cover_fetch_entries(self) -> list[tuple[str, str]]:
        """(command, menu text) for the cover context menu: the cover source (Apple Music)
        and MusicBrainz, e.g. when Apple Music delivered a wrong cover."""
        if not self.view.selected_tracks():
            return []
        out = []
        path = self._manual_cover_source()
        if path:
            name = os.path.splitext(os.path.basename(path))[0].replace("&", "")
            out.append(("fetch", tr("Cover von {1} laden", name.split("#")[0].strip() or name)))
        mb = self._mb_cover_source()
        if mb and mb != path:
            out.append(("fetch_mb", tr("Cover von {1} laden", "MusicBrainz")))
        return out

    def fetch_cover_from_source(self, tracks, exclude: str = "", path: str = "",
                                manual: bool = False, interactive: bool = True) -> str | None:
        """Cover-only fetch from the configured cover source; replaces the front cover.
        ``manual``: started by the user, so a too small cover may be taken after asking.
        Without ``interactive`` no dialog opens. Returns None if it did not run, "" if it
        worked, otherwise what went wrong."""
        from ..websources import coverfetch
        from ..websources import http as wshttp
        from ..websources import runner
        from .dialogs.tagsources import ResultsDialog
        path = path or self.settings.value("tagsources/cover_source", "")
        if not path or not os.path.exists(path) or path == exclude or not tracks:
            return None
        label = os.path.splitext(os.path.basename(path))[0].replace("&", "").replace("#", " – ")
        try:
            src, rows, matches = self._background(tr("Cover-Suche bei {1}", label),
                                                  lambda: coverfetch.search(path, tracks))
        except (wshttp.FetchError, runner.ScriptError) as e:
            if interactive:
                QMessageBox.warning(self, label, str(e))
            return str(e).splitlines()[0]
        # the release the files were tagged from, then every confident match: one of them may
        # have no artwork (MusicBrainz) while another release of the album has a cover
        exact = coverfetch.release_row(rows, (tracks[0].get("MUSICBRAINZ_ALBUMID") or [""])[0])
        auto = coverfetch.candidates(matches, exact)
        try:
            found = self._background(tr("Cover von {1} laden", label),
                                     lambda: coverfetch.first_cover(src, auto)) if auto else None
        except (wshttp.FetchError, runner.ScriptError, OSError) as e:
            if interactive:
                QMessageBox.warning(self, label, str(e))
            return str(e).splitlines()[0]
        if found is None and not interactive:
            return tr("Kein sicherer Treffer bei {1}", label)
        if found is None:                           # let the user pick among the other releases
            tried = {id(r) for r in auto}
            ranked = [m.row for m in matches]
            rest = [r for r in ranked + [r for r in rows if r not in ranked] if id(r) not in tried]
            if not rest:
                self.message(tr("Kein Cover bei {1} gefunden", label), 5000)
                return tr("Kein Cover bei {1} gefunden", label)
            d = ResultsDialog(src, rest, self)
            d.setWindowTitle(tr("Cover von {1} – bitte Album wählen", label))
            if d.exec() != 1 or d.selected() is None:
                return tr("Abgebrochen")
            row = d.selected()
            try:
                got = self._background(tr("Cover von {1} laden", label),
                                       lambda: coverfetch.fetch_cover(src, row))
            except (wshttp.FetchError, runner.ScriptError, OSError) as e:
                QMessageBox.warning(self, label, str(e))
                return str(e).splitlines()[0]
            if not got:
                self.message(tr("Kein Cover bei {1} gefunden", label), 5000)
                return tr("Kein Cover bei {1} gefunden", label)
        else:
            got = found[1]
        data, mime = got
        if not self._cover_big_enough(data, label, ask=manual):
            return tr("Cover von {1} zu klein", label)  # the tag source's cover stays as fallback
        new = tags.Cover(data, mime, 3, src.get("name") or label)

        def apply(t):
            t.data.covers = [new] + [c for c in t.data.covers if c.type != 3]
        self._write(tr("Cover von {1}", label), tracks, apply)
        self.panel.load(self.view.selected_tracks())
        from PySide6.QtGui import QImage
        img = QImage.fromData(data)
        self.message(tr("Cover von {1}: {2}x{3}", label, img.width(), img.height()), 6000)
        return ""

    def _add_source_entries(self, m: QMenu) -> None:
        """Tag sources; `#` in the file name creates submenus, `&` is the mnemonic.
        .settings files are appended at the end, separated from the sources."""
        from ..sources import list_settings, list_sources
        has_sel = bool(self.view.selected_tracks())

        def place(name: str):
            parts = name.split("#")
            sub = m
            for p in parts[:-1]:
                found = [a.menu() for a in sub.actions() if a.menu() and a.menu().title() == p]
                sub = found[0] if found else sub.addMenu(p)
            return sub, parts[-1]
        for name, path in list_sources():
            sub, label = place(name)
            a = sub.addAction(label, lambda _=False, p=path: self.run_source(p))
            a.setEnabled(has_sel)
        settings = list_settings()
        if settings:
            m.addSeparator()
        for name, path in settings:
            sub, label = place(name)
            sub.addAction(label, lambda _=False, p=path: self.source_settings(p))

    def discogs_token(self):
        from .dialogs.tagsources import DiscogsTokenDialog
        DiscogsTokenDialog(self).exec()

    def source_settings(self, path: str):
        import json as _json
        from .dialogs.tagsources import SourceSettingsDialog
        try:
            with open(path, encoding="utf-8-sig") as fh:
                schema = _json.load(fh)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("Fehler"), str(e))
            return
        SourceSettingsDialog(schema, self).exec()

    def _update_last_source_tip(self) -> None:
        """Toolbar tooltip names the source the button will run."""
        p = self.settings.value("tagsources/last", "")
        if p and os.path.exists(p):
            name = os.path.splitext(os.path.basename(p))[0].replace("&", "").replace("#", " – ")
            self.act_last_source.setToolTip(tr("Tag-Quelle: {1} (Strg+I)", name))
        else:
            self.act_last_source.setToolTip(tr("Tag-Quelle wählen"))

    def run_last_source(self, quick: bool):
        p = self.settings.value("tagsources/last", "")
        if p and os.path.exists(p):
            self.run_source(p, quick)
        else:
            self.sources_menu.exec(self.mapToGlobal(self.rect().center()))

    def _background(self, label: str, fn):
        """Run fn in a worker thread while keeping the UI responsive."""
        import threading
        from PySide6.QtCore import QEventLoop
        box: dict = {}

        def work():
            try:
                box["v"] = fn()
            except Exception as e:      # reported in the UI thread
                box["e"] = e
        th = threading.Thread(target=work, daemon=True)
        th.start()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.message(label)
        try:
            while th.is_alive():
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
                th.join(0.02)
        finally:
            QApplication.restoreOverrideCursor()
            self.message("")
        if "e" in box:
            raise box["e"]
        return box.get("v")

    def run_source(self, path: str, quick: bool = False, note: str = ""):
        from ..websources import albumauto
        from ..websources import http as wshttp
        from ..websources import runner, srcfile
        from .dialogs.tagsources import (AdjustDialog, DiscogsTokenDialog, ResultsDialog,
                                         SearchDialog)
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        try:
            src = srcfile.load(path, os.path.splitext(os.path.basename(path))[0])
        except OSError as e:
            QMessageBox.warning(self, tr("Fehler"), str(e))
            return
        msg = runner.check_version(src)
        if msg:
            QMessageBox.warning(self, "PsyTags", msg)
            return
        if "discogs.com" in (src.get("indexurl") + src.get("albumurl")) \
                and not self.settings.value("tagsources/discogs_token", ""):
            if not DiscogsTokenDialog(self).exec():
                return
        self.settings.setValue("tagsources/last", path)
        self._update_last_source_tip()
        name = src.get("name") or src.name
        values = runner.prefill(src, tracks)
        rows: list = []
        row = None
        stage = "search"
        while True:
            if stage == "search":
                if not quick:
                    d = SearchDialog(src, tracks, self, values)
                    if not d.exec():
                        return
                    values = d.values()
                quick = False
                if not runner.has_index(src):
                    row, stage = None, "album"
                    continue
                try:
                    rows = self._background(tr("Suchergebnisse von {1} abrufen", name),
                                            lambda: runner.run_index(src, values))
                except (wshttp.FetchError, runner.ScriptError) as e:
                    if QMessageBox.warning(self, name, str(e), QMessageBox.StandardButton.Retry
                                           | QMessageBox.StandardButton.Cancel) \
                            == QMessageBox.StandardButton.Retry:
                        continue
                    return
                if values == runner.prefill(src, tracks) and albumauto.needs_second_search(rows, tracks):
                    # e.g. "Album (Bonus Tracks Edition)" when the database only knows "Album"
                    for second in albumauto.fallback_searches(src, tracks):
                        try:
                            more = self._background(tr("Suchergebnisse von {1} abrufen", name),
                                                    lambda: albumauto.search_rows(src, second))
                        except (wshttp.FetchError, runner.ScriptError):
                            more = []
                        if more:
                            rows, values = more, second
                            break
                if not rows:
                    if QMessageBox.information(
                            self, name, tr("Leider entsprechen keine Einträge den Suchkriterien."),
                            QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel) \
                            == QMessageBox.StandardButton.Retry:
                        continue
                    return
                rows = albumauto.digital_first(rows, len(tracks))
                stage = "results"
            if stage == "results":
                d = ResultsDialog(src, rows, self)
                if note:
                    d.setWindowTitle(f"{d.windowTitle()} – {note}")
                r = d.exec()
                if r == 2:
                    stage = "search"
                    continue
                if not r:
                    return
                row = d.selected()
                stage = "album"
            if stage == "album":
                url, prev = runner.album_target(src, row, values[0] if values else "")
                try:
                    album = self._background(tr("Metadaten von {1} abrufen", name),
                                             lambda: runner.run_album(src, url, prev))
                    cover = None
                    if album.cover_url:
                        try:
                            cover = self._background(tr("Cover laden"), lambda: wshttp.fetch_bytes(
                                runner.cover_download_url(album.cover_url)))
                        except Exception:
                            cover = None
                except (wshttp.FetchError, runner.ScriptError) as e:
                    if QMessageBox.warning(self, name, str(e), QMessageBox.StandardButton.Retry
                                           | QMessageBox.StandardButton.Cancel) \
                            == QMessageBox.StandardButton.Retry:
                        continue
                    return
                d = AdjustDialog(album, self.view.selected_tracks() or tracks, cover, self)
                r = d.exec()
                if r == 2:
                    stage = "results" if runner.has_index(src) else "search"
                    continue
                if not r:
                    return
                plan = d.plan()
                return self._finish_source_import(name, path, plan, cover if d.use_cover() else None, d.leftovers(),
                                                  complete=len(plan) == d.album.tracks)

    # ------------------------------------------------------------------ views
    def _fill_sort_menu(self):
        m = self.sort_menu
        m.clear()
        m.addAction(tr("&Zufällig"), lambda: self.view._header_clicked(0))
        m.addSeparator()
        for i, c in enumerate(self.model.columns, 1):
            a = m.addAction(tr(c.name).replace("&", ""), lambda _=False, i=i: self.view._header_clicked(i))
            a.setCheckable(True)
            a.setChecked(bool(self.model.sort_keys) and self.model.sort_keys[0][0] == i)

    def _fill_columns_menu(self):
        m = self.columns_menu
        m.clear()
        for c in self.model.all_columns:
            a = m.addAction(tr(c.name).replace("&", ""))
            a.setCheckable(True)
            a.setChecked(c.enabled)
            a.toggled.connect(lambda on, c=c: self._toggle_column(c, on))
        m.addSeparator()
        m.addAction(self.act_customize_cols)

    def _toggle_column(self, c, on):
        self.view.store_widths()
        c.enabled = on
        self.model.set_columns(self.model.all_columns)
        self.view.apply_widths()
        config.save_columns(self.model.all_columns)

    def autofit_columns(self):
        self.view.resizeColumnsToContents()
        self.view.setColumnWidth(0, 18)

    def customize_columns(self):
        from .dialogs.options import ColumnsDialog
        self.view.store_widths()
        d = ColumnsDialog(self.model.all_columns, self)
        if d.exec():
            config.save_columns(d.columns)
            self.model.set_columns(d.columns)
            self.view.apply_widths()

    def _lastfm_enabled(self) -> bool:
        return self.settings.value("lastfm/enabled", "false") in (True, "true")

    def _rebuild_panel(self):
        """Tag Panel from usrfields.ini; with Last.fm on, GENRE and MOOD get full-width rows."""
        fields = config.load_panel()
        if self._lastfm_enabled():
            fields = [f for f in fields if f.value.upper() not in ("GENRE", "MOOD")]
            fields += [config.PanelField(tr("Genres"), "GENRE", size=12, version=1),
                       config.PanelField(tr("Moods"), "MOOD", size=12, version=1)]
        self.panel.build(fields, config.load_custom_values())
        self.panel.set_directories(self.current_dir, self.dir_history)

    def lastfm_settings(self):
        from .dialogs.tagsources import LastfmDialog
        if LastfmDialog(self).exec():
            self._rebuild_panel()

    def start_lastfm(self, tracks, interactive: bool = True):
        """Start the Last.fm lookup in the background (one request set per album).
        Returns a job for finish_lastfm(), or None."""
        import concurrent.futures
        from ..websources import lastfm
        key = self.settings.value("lastfm/api_key", "")
        if not tracks:
            return None
        if not key:
            if interactive:
                QMessageBox.information(self, "Last.fm", tr("Bitte zuerst einen Last.fm-API-Key eintragen."))
                self.lastfm_settings()
            return None
        albums: dict[tuple[str, str], list[Track]] = {}
        for t in tracks:
            artist = (t.get("ALBUMARTIST") or t.get("ARTIST") or [""])[0]
            albums.setdefault((artist, (t.get("ALBUM") or [""])[0]), []).append(t)
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = ex.submit(lambda: {k: lastfm.album_genres(k[0], k[1], key) for k in albums})
        ex.shutdown(wait=False)
        return list(tracks), albums, future

    def fetch_lastfm(self, tracks) -> None:
        job = self.start_lastfm(tracks)
        if job is not None:
            self.finish_lastfm(job)

    def finish_lastfm(self, job, interactive: bool = True) -> str:
        """Write the genres of a finished lookup. Returns what went wrong, or ""."""
        from ..websources import lastfm
        tracks, albums, future = job
        try:
            found = self._background(tr("Genres von Last.fm abrufen"), future.result)
        except (lastfm.LastfmError, OSError) as e:
            if interactive:
                QMessageBox.warning(self, "Last.fm", str(e))
            return str(e).splitlines()[0]
        by_track = {id(t): found[k] for k, ts in albums.items() for t in ts}

        def apply(t):
            genres = by_track.get(id(t), [])
            if not genres:
                return False
            t.set("GENRE", genres)
        n = self._write(tr("Genres von Last.fm"), tracks, apply)
        self.panel.load(self.view.selected_tracks())
        self.message(tr("Last.fm: Genres für {1} von {2} Dateien", n, len(tracks)) if any(found.values())
                     else tr("Last.fm: keine passenden Genres gefunden"), 6000)
        return "" if any(found.values()) else tr("Last.fm: keine passenden Genres gefunden")

    # ------------------------------------------------------------------ moods from the audio
    def analyze_all_moods(self):
        self.analyze_moods(list(self.model.rows))

    def analyze_moods(self, tracks: list[Track]) -> bool:
        """Moods for each song from its audio; replaces MOOD, one undo step.
        False if the analysis could not run or was canceled."""
        from PySide6.QtCore import QEventLoop
        if not tracks:
            return True
        try:
            from .. import moodanalysis as ma
        except ImportError as e:
            QMessageBox.warning(self, "PsyTags", str(e))
            return False
        folder = os.path.join(config.data_dir(), "models")

        def prepare():
            ma.ensure_models(folder)
            return ma.Analyzer(folder)
        try:
            analyzer = self._background(tr("Mood-Modelle laden"), prepare)
        except (ma.MoodError, ImportError, OSError) as e:
            QMessageBox.warning(self, "PsyTags", str(e))
            return False
        dlg = _StayingProgress(tr("Moods analysieren ..."), len(tracks), self)
        dlg.setWindowTitle("PsyTags")
        progress, box = [0], {}

        def work():
            try:
                box["r"] = ma.analyze_files([t.path for t in tracks], analyzer.moods,
                                            on_progress=lambda n, _total: progress.__setitem__(0, n),
                                            should_stop=dlg.stop.is_set)
            except Exception as e:                  # reported in the UI thread
                box["e"] = e
        th = threading.Thread(target=work, daemon=True)
        th.start()
        while th.is_alive():
            dlg.setValue(progress[0])
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            th.join(0.02)
        canceled = dlg.stop.is_set()
        dlg.finish()
        if "e" in box:
            QMessageBox.warning(self, "PsyTags", str(box["e"]))
            return False
        result = box["r"]
        self._mood_done.update({id(t): t for t in tracks if t.path in result.found or t.path in result.empty})
        hits = [t for t in tracks if t.path in result.found]
        if hits:
            self._write(tr("Moods analysieren"), hits, lambda t: t.set("MOOD", result.found[t.path]))
            self.panel.load(self.view.selected_tracks())
        self.message(tr("Moods: {1} Dateien mit Moods, {2} ohne Ergebnis, {3} nicht lesbar",
                        len(hits), len(result.empty), len(result.failed)), 10000)
        return not canceled

    # ------------------------------------------------------------------ automatic album choice
    def _mb_tag_source(self) -> str:
        from ..sources import list_sources
        return next((p for name, p in list_sources() if name.replace("&", "").lower() == "musicbrainz"), "")

    def _load_mb_source(self):
        """(path, source) of the MusicBrainz tag source, or None after telling the user."""
        from ..websources import srcfile
        path = self._mb_tag_source()
        if not path:
            QMessageBox.warning(self, "PsyTags", tr("Die Tag-Quelle MusicBrainz ist nicht installiert."))
            return None
        try:
            return path, srcfile.load(path, os.path.splitext(os.path.basename(path))[0])
        except OSError as e:
            QMessageBox.warning(self, tr("Fehler"), str(e))
            return None

    def auto_musicbrainz(self) -> None:
        """Tag the selected album without dialogs when it is certain, else show the results."""
        from ..websources import albumauto
        from ..websources import http as wshttp
        from ..websources import runner
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        loaded = self._load_mb_source()
        if loaded is None:
            return
        path, src = loaded
        if len({(t.get("ALBUM") or [""])[0] for t in tracks}) != 1:
            self.run_source(path)
            return
        try:
            res = self._background(tr("MusicBrainz durchsuchen: {1}", albumauto.album_title(tracks)),
                                   lambda: albumauto.find_album(src, tracks))
        except (wshttp.FetchError, runner.ScriptError, OSError) as e:
            QMessageBox.warning(self, "MusicBrainz", str(e))
            return
        if res.match is None:
            self.run_source(path, quick=True, note=tr("Nicht sicher erkannt: {1}", res.reason))
            return
        self._import_match(src, path, res.match, interactive=True)
        self._auto_done.update({id(t): t for t in tracks})
        self.message(tr("MusicBrainz: {1} ({2}) automatisch gewählt, {3} Dateien",
                        res.album.value("ALBUM", 0), albumauto.release_year(res.match), len(res.match.mapping)), 10000)

    def _import_match(self, src, path: str, match, interactive: bool) -> tuple[str | None, str | None]:
        """Write a certain match; returns the outcome of the cover and genre steps."""
        from ..websources import albumauto
        from ..websources import http as wshttp
        from ..websources import runner
        album = match.release.key
        cover = None
        if album.cover_url:
            try:
                cover = self._background(tr("Cover laden"), lambda: wshttp.fetch_bytes(
                    runner.cover_download_url(album.cover_url)))
            except Exception:
                cover = None
        disabled = set(config.string_list(self.settings, "tagsources/disabled_fields"))
        return self._finish_source_import(src.get("name") or src.name, path, albumauto.plan_for(match, disabled),
                                          cover, match.leftover_keys, interactive, complete=True)

    def _finish_source_import(self, name: str, path: str, plan: list, cover: bytes | None,
                              leftovers: list, interactive: bool = True,
                              complete: bool = False) -> tuple[str | None, str | None]:
        """Shared end of every tag source import: write, order the album, number it (only when
        ``complete``, i.e. every track has its file), ask about files without a track, then
        cover source and genres. Returns (cover, genres): None did not run, "" worked, else why not."""
        from ..websources import albummatch
        use_cover = bool(cover) and self._cover_big_enough(cover, name)
        mime = "image/png" if cover and cover[:4] == b"\x89PNG" else "image/jpeg"
        values_by_track = {id(t): v for t, v in plan}

        def apply(t):
            vals = values_by_track.get(id(t))
            if vals is None:
                return False
            for k, v in albummatch.clean_import(vals, bool(t.get("MOOD"))).items():
                t.set(k, v)
            if use_cover:                       # the source's cover replaces the existing ones
                t.data.covers = [tags.Cover(cover, mime, 3, name)]
        written = [t for t, _ in plan]
        self._write(name, written, apply)
        self.panel.clear_dirty()                # the import replaces what was typed into the panel
        selection = self.view.selected_tracks()
        self.model.sort_album(written, last=leftovers)
        if complete:
            self._renumber(written)
        self.view.select_tracks(selection)
        self.panel.load(selection)
        if interactive and leftovers:
            self._offer_trash(leftovers)
            self.view.select_tracks([t for t in selection if os.path.exists(t.path)])
        # Last.fm runs while the cover source is searched; results are written after.
        job = self.start_lastfm(written, interactive) if self._lastfm_enabled() else None
        cover_result = self.fetch_cover_from_source(written, exclude=path, interactive=interactive)
        return cover_result, self.finish_lastfm(job, interactive) if job is not None else None

    def _renumber(self, tracks: list[Track]) -> None:
        """What Ctrl+K would write for this album, with the wizard's saved settings."""
        from .dialogs.numbering import NumberingWizard
        ordered = sorted(tracks, key=albumorder.sort_key)
        wizard = NumberingWizard(ordered, self)
        plan = wizard.plan()
        wizard.deleteLater()
        self._write(tr("Tracknummern-Assistent"), ordered,
                    lambda t: [t.set(k, v) for k, v in plan.get(id(t), {}).items()])

    def _trash_files(self, tracks: list[Track]) -> list[Track]:
        """Move to the recycle bin and drop from the list; returns the files that stayed."""
        from PySide6.QtCore import QFile
        for t in tracks:
            QFile.moveToTrash(t.path)
        self.model.remove_tracks([t for t in tracks if not os.path.exists(t.path)])
        self._update_status()
        return [t for t in tracks if os.path.exists(t.path)]

    def _offer_trash(self, tracks: list[Track]) -> None:
        names = "\n".join(t.filename for t in tracks)
        q = QMessageBox.question(self, "PsyTags",
                                 tr("Diese Dateien gehören zu keinem Track:\n\n{1}\n\nIn den Papierkorb verschieben?", names),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if q == QMessageBox.StandardButton.Yes:
            kept = self._trash_files(tracks)
            if kept:
                QMessageBox.warning(self, tr("Fehler"), "\n".join(t.filename for t in kept))

    def auto_all_albums(self) -> None:
        """Tag every album in the list that is certain; the others stay untouched and are
        listed at the end. No dialog interrupts the run."""
        from ..websources import albumauto
        loaded = self._load_mb_source()
        if loaded is None:
            return
        path, src = loaded
        todo = [g for g in albumauto.group_albums(list(self.model.rows)) if id(g[0]) not in self._auto_done]
        if not todo:
            self.message(tr("Alle Alben dieser Liste sind schon erledigt."), 6000)
            return
        if not self.analyze_moods([t for g in todo for t in g if id(t) not in self._mood_done]):
            return
        dlg = _StayingProgress("", len(todo), self)
        dlg.setWindowTitle(tr("Alle Alben automatisch"))
        entries = []
        try:
            for i, tracks in enumerate(todo):
                if dlg.stop.is_set():
                    break
                dlg.setLabelText(tr("{1} von {2}: {3}", i + 1, len(todo), albumauto.album_title(tracks)))
                dlg.setValue(i)
                entries.append(self._auto_one(src, path, tracks))
        finally:
            dlg.finish()
            self._last_batch = entries
            self._update_actions()
        self.show_batch_summary()

    def _auto_one(self, src, path: str, tracks: list[Track]):
        from ..websources import albumauto
        title = albumauto.album_title(tracks)
        try:
            res = self._background(tr("MusicBrainz durchsuchen: {1}", title),
                                   lambda: albumauto.find_album(src, tracks))
            if res.match is None:
                return albumauto.BatchEntry(title, tracks, False, res.reason)
            with self._undo_group(title):
                cover, genres = self._import_match(src, path, res.match, interactive=False)
        except Exception as e:                      # one album must not end the whole run
            return albumauto.BatchEntry(title, tracks, False, (str(e) or type(e).__name__).splitlines()[0])
        if self._group_errors:
            return albumauto.BatchEntry(title, tracks, False, tr("Schreibfehler: {1}", " · ".join(self._group_errors[:3])))
        self._auto_done.update({id(t): t for t in tracks})
        detail = " · ".join([albumauto.release_label(res.match)] + [n for n in (cover, genres) if n])
        return albumauto.BatchEntry(title, tracks, True, detail, list(res.match.leftover_keys), cover, genres)

    def show_batch_summary(self) -> None:
        from .dialogs.tagsources import BatchSummaryDialog
        if not self._last_batch:
            self.message(tr("Noch kein automatischer Lauf in dieser Sitzung."), 6000)
            return
        while True:
            d = BatchSummaryDialog(self._last_batch, self._trash_files, self)
            accepted = d.exec()
            entry, action = d.chosen, d.action
            d.deleteLater()
            if not accepted or entry is None:
                return
            self.view.select_tracks(entry.tracks)
            if action in ("cover", "genres"):       # back to the list afterwards
                (self._retry_cover if action == "cover" else self._retry_genres)(entry)
                continue
            path = self._mb_tag_source()
            outcome = self.run_source(path, quick=True, note=entry.detail) if path else None
            if outcome is not None:                 # saved: the album is no longer open
                entry.ok, (entry.cover, entry.genres) = True, outcome
                entry.detail = " · ".join([tr("Manuell getaggt")] + [n for n in outcome if n])
                self._auto_done.update({id(t): t for t in entry.tracks})
            return

    def _retry_genres(self, entry) -> None:
        """Last.fm once more for one finished album."""
        job = self.start_lastfm(entry.tracks)
        if job is None:
            return
        failed, entry.genres = entry.genres, self.finish_lastfm(job)
        entry.detail = entry.detail.replace(f" · {failed}", f" · {entry.genres}" if entry.genres else "")

    def _retry_cover(self, entry) -> None:
        """Cover source for one finished album, this time with its result list."""
        failed = entry.cover
        if self.fetch_cover_from_source(entry.tracks, manual=True) == "":
            entry.cover = ""
            entry.detail = entry.detail.replace(f" · {failed}", "")

    def customize_panel(self):
        from .dialogs.options import PanelDialog
        d = PanelDialog(config.load_panel(), self)
        if d.exec():
            config.save_panel(d.fields)
            self._rebuild_panel()

    def extended_tags(self):
        from .dialogs.extended import ExtendedTagsDialog
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        d = ExtendedTagsDialog(tracks, self)
        if d.exec():
            self._write(tr("Erweiterte Tags"), tracks, d.apply_to)
            self.panel.load(tracks)

    def apply_filter(self):
        text = self.filter_combo.currentText()
        sel = self.view.selected_tracks()
        self.model.set_filter(text)
        self.view.select_tracks([t for t in sel if t in self.model.rows])
        if text:
            h = [x for x in config.string_list(self.settings, "filter/history") if x != text]
            self.settings.setValue("filter/history", [text] + h[:29])
        self._update_status()

    def find(self):
        from .dialogs.find import FindDialog
        FindDialog(self).exec()

    # ------------------------------------------------------------------ files
    def remove_from_list(self):
        tracks = self.view.selected_tracks()
        if tracks:
            row = self.view.selected_rows()[0]
            self.model.remove_tracks(tracks)
            if self.model.rows:
                self.view.select_tracks([self.model.rows[min(row, len(self.model.rows) - 1)]])
            self._update_status()

    def delete_files(self, permanent: bool):
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        q = tr("Möchten Sie die {1} ausgewählte(n) Datei(en) endgültig löschen?", len(tracks)) if permanent \
            else tr("Möchten Sie die {1} ausgewählte(n) Datei(en) in den Papierkorb verschieben?", len(tracks))
        if QMessageBox.question(self, "PsyTags", q) != QMessageBox.StandardButton.Yes:
            return
        from PySide6.QtCore import QFile
        failed = []
        for t in tracks:
            ok = os.remove(t.path) is None if permanent else QFile.moveToTrash(t.path)
            if not ok:
                failed.append(t.filename)
        self.model.remove_tracks([t for t in tracks if not os.path.exists(t.path)])
        self._update_status()
        if failed:
            QMessageBox.warning(self, tr("Fehler"), "\n".join(failed))

    def open_in_file_manager(self):
        tracks = self.view.selected_tracks()
        if tracks and sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(tracks[0].path)])
            return
        if tracks:
            try:
                subprocess.Popen(["dbus-send", "--session", "--dest=org.freedesktop.FileManager1",
                                  "--type=method_call", "/org/freedesktop/FileManager1",
                                  "org.freedesktop.FileManager1.ShowItems",
                                  "array:string:" + ",".join(QUrl.fromLocalFile(t.path).toString()
                                                             for t in tracks[:50]), "string:"])
                return
            except OSError:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_dir or os.path.expanduser("~")))

    def play(self):
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        if len(tracks) == 1:
            QDesktopServices.openUrl(QUrl.fromLocalFile(tracks[0].path))
            return
        import tempfile
        fd, p = tempfile.mkstemp(suffix=".m3u8", prefix="psytags-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("#EXTM3U\n" + "\n".join(t.path for t in tracks) + "\n")
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def properties(self):
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        t = tracks[0]
        i = t.data.info
        lines = [t.path, "",
                 f"{tr('Format')}: {i.codec}", f"{tr('Länge')}: {fmt_length(i.length)}",
                 f"{tr('Bitrate')}: {i.bitrate} kbit/s {i.bitrate_mode}",
                 f"{tr('Samplerate')}: {i.samplerate} Hz", f"{tr('Kanäle')}: {i.channels} {i.mode}",
                 f"{tr('Tag')}: {', '.join(t.data.tag_types)}",
                 f"{tr('Größe')}: {fmt_size(t.size)} ({t.size} Bytes)"]
        QMessageBox.information(self, tr("Eigenschaften"), "\n".join(lines))

    # ------------------------------------------------------------------ cover
    def _cover_command(self, cmd: str):
        cv = self.panel.cover
        if cmd in ("add", "replace"):
            p, _ = QFileDialog.getOpenFileName(self, tr("Cover hinzu&fügen...").replace("&", ""),
                                               self.current_dir,
                                               tr("Bilder (*.jpg *.jpeg *.png *.bmp *.gif *.webp)"))
            if not p:
                return
            with open(p, "rb") as fh:
                data = fh.read()
            mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
            if p.lower().endswith((".bmp", ".gif", ".webp")):
                from PySide6.QtGui import QImage
                data, mime = image_to_bytes(QImage(p)), "image/jpeg"
            replace = cmd == "replace" or not cv.covers
            if cmd == "add" and cv.covers:
                r = QMessageBox.question(self, "PsyTags", tr("Möchten Sie bereits existierende Cover behalten?"),
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                         | QMessageBox.StandardButton.Cancel)
                if r == QMessageBox.StandardButton.Cancel:
                    return
                replace = r == QMessageBox.StandardButton.No
            cv.set_cover(data, mime, replace=replace)
            self.save_tags()
        elif cmd == "remove":
            cv.remove_current()
            self.save_tags()
        elif cmd == "extract":
            if not cv.covers:
                return
            c = cv.covers[cv.index]
            ext = ".png" if c.mime == "image/png" else ".jpg"
            t = self.view.selected_tracks()[0]
            p, _ = QFileDialog.getSaveFileName(self, tr("Cover &extrahieren...").replace("&", ""),
                                               os.path.join(t.folder, "folder" + ext))
            if p:
                with open(p, "wb") as fh:
                    fh.write(c.data)
        elif cmd in ("fetch", "fetch_mb"):
            path = self._manual_cover_source() if cmd == "fetch" else self._mb_cover_source()
            self.fetch_cover_from_source(self.view.selected_tracks(), path=path, manual=True)
        elif cmd == "preview":
            from .dialogs.cover import CoverPreview
            CoverPreview.show_for(self, cv)
        elif cmd == "adjust":
            from .dialogs.cover import adjust_cover
            if cv.covers:
                new = adjust_cover(self, cv.covers[cv.index])
                if new is not None:
                    cv.covers[cv.index] = new
                    cv._load()
                    cv.changed.emit()
                    self.save_tags()
        elif cmd == "manage":
            from .dialogs.covers import ManageCoversDialog
            tracks = self.view.selected_tracks()
            if tracks:
                d = ManageCoversDialog(tracks, self)
                if d.exec():
                    self._write(tr("Cover verwalten"), tracks, d.apply_to)
                    self.panel.load(tracks)

    # ------------------------------------------------------------------ misc
    def _context_menu(self, pos):
        m = QMenu(self)
        for a in (self.act_play, self.act_open_fm, self.act_save, self.act_remove, self.act_ext_tags,
                  self.act_cut, self.act_copy, self.act_paste):
            m.addAction(a)
        m.addSeparator()
        conv = m.addMenu(tr("&Konverter"))
        for a in (self.act_ttf, self.act_wizard):
            conv.addAction(a)
        src = m.addMenu(tr("Tag-&Quellen"))
        src.aboutToShow.connect(lambda: self._fill_sources_submenu(src))
        m.addAction(self.act_lastfm)
        m.addAction(tr("Moods analysieren (Auswahl)"), lambda: self.analyze_moods(self.view.selected_tracks()))
        m.addAction(self.act_auto_mb)
        m.addSeparator()
        for a in (self.act_remove_files, self.act_rename,
                  None, self.act_delete, None, self.act_props):
            m.addSeparator() if a is None else m.addAction(a)
        m.exec(pos)

    def _fill_sources_submenu(self, menu):
        menu.clear()
        self._add_source_entries(menu)

    def show_options(self):
        from .dialogs.options import OptionsDialog
        d = OptionsDialog(self.opts, self)
        if d.exec():
            self.opts = d.opts
            self.opts.save()

    def about(self):
        from .. import __version__
        QMessageBox.about(self, tr("Über PsyTags..."),
                          f"<b>PsyTags {__version__}</b><br>"
                          + tr("Tag-Editor für Linux, Bedienung nach dem Vorbild von Mp3tag."))


def QStandardPathsMusic() -> str:
    from PySide6.QtCore import QStandardPaths
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)

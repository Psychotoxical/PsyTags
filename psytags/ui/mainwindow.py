"""Main window: top bar with the workflow steps, file list, tag panel and status bar."""
from __future__ import annotations

import contextlib
import copy
import os
import threading
import time

from PySide6.QtCore import (QEvent, QObject, Qt, QThread, QTimer, QUrl, Signal)
from PySide6.QtGui import (QAction, QDesktopServices, QKeySequence, QShortcut)
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QHBoxLayout,
                               QLabel, QMainWindow, QMenu, QMessageBox, QProgressBar, QSizePolicy,
                               QDialog, QPushButton, QStatusBar, QVBoxLayout, QWidget)

from .. import albumorder, config, convert, longpath, namescheme, numbering, tags
from ..config import Options
from ..i18n import tr
from ..track import Track, fmt_size
from ..undo import Recorder, UndoStack
from .filelist import FileListModel, FileListView
from .topbar import TopBar
from .icons import icon
from .keys import extra_keys, mac_keys
from .persist import geometry_key
from .tagpanel import TagPanel, image_to_bytes

AUDIO_EXT = set(tags.SUPPORTED_EXTENSIONS)
LAYOUT_VERSION = 2                          # a saved window layout from another version is ignored


class _ScrollOnlyGuard(QObject):
    """While a run works on the list, the main window can only be scrolled: without this,
    a click or a shortcut could change the files the run is writing to."""
    BLOCKED = {QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick,
               QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride, QEvent.Type.ContextMenu,
               QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop}

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.Shortcut:                # the actions of the main window
            return obj.parent() is self.window
        if not isinstance(obj, QWidget) or obj.window() is not self.window:
            return False
        if kind == QEvent.Type.Close and obj is self.window:
            event.ignore()
            return True
        view = self.window.view
        bars = (view.verticalScrollBar(), view.horizontalScrollBar())
        if kind == QEvent.Type.Wheel:
            return obj is not view.viewport() and not any(obj is b for b in bars)
        return kind in self.BLOCKED and not any(obj is b for b in bars)


def _front_covers(tracks) -> list:
    return [[hash(c.data) for c in t.data.covers if c.type == 3] for t in tracks]


def statusbox_setting() -> str:
    from .statusbox import SETTING
    return SETTING


def duration_text(seconds: float) -> str:
    """12 s, 4 min 05 s, 1 h 02 min."""
    s = int(round(seconds))
    if s < 60:
        return tr("{1} s", s)
    if s < 3600:
        return tr("{1} min {2} s", s // 60, f"{s % 60:02d}")
    return tr("{1} h {2} min", s // 3600, f"{s % 3600 // 60:02d}")


def run_statistics(entries: list, seconds: float) -> str:
    done = sum(1 for e in entries if e.ok)
    files = sum(len(e.tracks) for e in entries)
    return tr("{1} Alben ({2} Dateien) in {3}: {4} erledigt, {5} offen",
              len(entries), files, duration_text(seconds), done, len(entries) - done)


def _genres_of(tracks) -> list:
    return [tuple(t.get("GENRE")) for t in tracks]


def _remember_covers(entry) -> None:
    """After a failed cover or genre step: any later change means it was settled another way."""
    entry.cover_seen = _front_covers(entry.tracks) if entry.cover else None
    entry.genres_seen = _genres_of(entry.tracks) if entry.genres else None


class _Canceled(Exception):
    """The user left a waiting window."""


def _store_front_cover(window, tracks, data: bytes, label: str, ask: bool, keep: bool = False) -> str:
    """Replace the front cover of ``tracks``; with ``keep`` only files without any cover get it.
    Returns "" or why not."""
    if not window._cover_big_enough(data, label, ask=ask):
        from PySide6.QtGui import QImage
        image = QImage.fromData(data)
        return tr("Cover von {1} zu klein ({2}x{3})", label, image.width(), image.height())
    new = tags.Cover(data, "image/png" if data[:4] == b"\x89PNG" else "image/jpeg", 3, label)

    def apply(t):
        if keep and t.data.covers:
            return False
        t.data.covers = [new] + [c for c in t.data.covers if c.type != 3]
    window._write(tr("Cover von {1}", label), tracks, apply)
    window.panel.load(window.view.selected_tracks())
    return ""


class _StayingProgress(QDialog):
    """Stays open and modal after Cancel until the running step has finished."""
    canceled = Signal()

    def __init__(self, text: str, maximum: int, parent):
        super().__init__(parent)
        self.stop = threading.Event()
        # Only the close button: minimizing or maximizing a progress window makes no sense.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint
                            | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.setFixedWidth(560)
        column = QVBoxLayout(self)
        column.setContentsMargins(22, 20, 22, 18)
        column.setSpacing(12)
        head = QHBoxLayout()
        self.title_label = QLabel(text)
        self.title_label.setObjectName("ProgressTitle")
        self.title_label.setWordWrap(True)
        self.count_label = QLabel()
        self.count_label.setObjectName("ProgressCount")
        head.addWidget(self.title_label, 1)
        head.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignTop)
        column.addLayout(head)
        self.bar = QProgressBar()
        self.bar.setObjectName("ProgressBar")
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setRange(0, max(1, maximum))
        column.addWidget(self.bar)
        self.activity_label = QLabel()
        self.activity_label.setObjectName("ProgressActivity")
        self.activity_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.activity_label.hide()
        column.addWidget(self.activity_label)
        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(150)
        self.activity_timer.timeout.connect(self.show_activity)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.hint_label = QLabel()
        self.hint_label.setObjectName("DialogSubtitle")
        self.hint_label.setWordWrap(True)
        self.hint_label.hide()
        row.addWidget(self.hint_label, 100)
        row.addStretch(1)
        self.cancel_button = QPushButton(tr("Abbrechen"))
        self.cancel_button.clicked.connect(lambda: self.canceled.emit())
        row.addWidget(self.cancel_button)
        column.addLayout(row)
        self.canceled.connect(self.request_stop)
        self.setValue(0)
        self._guard = _ScrollOnlyGuard(parent) if hasattr(parent, "view") else None
        if self._guard is not None:
            QApplication.instance().installEventFilter(self._guard)
        self.show()

    def setValue(self, value: int) -> None:
        total = self.bar.maximum()
        self.bar.setValue(value)
        self.count_label.setText(f"{tr('{1} von {2}', value, total)} · {value * 100 // total} %")

    def setLabelText(self, text: str) -> None:
        self.title_label.setText(text)

    def set_hint(self, text: str) -> None:
        self.hint_label.setText(text)
        self.hint_label.show()
        self.adjustSize()

    def follow_activity(self) -> None:
        """Show in small print which requests are running."""
        self.activity_label.show()
        self.activity_timer.start()

    def show_activity(self) -> None:
        from ..websources import http as wshttp
        now = wshttp.running()
        if now:                                 # between two requests the last one stays
            self.activity_label.setText(" · ".join(now))

    def request_stop(self):
        self.stop.set()
        self.cancel_button.setEnabled(False)
        self.setLabelText(tr("Wird abgebrochen ..."))

    def closeEvent(self, event):
        event.ignore()
        self.request_stop()

    def reject(self):
        self.request_stop()

    def finish(self):
        self.activity_timer.stop()
        if self._guard is not None:
            QApplication.instance().removeEventFilter(self._guard)
            self._guard = None
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
    current: "MainWindow | None" = None      # the window of the moment; a change of language or theme replaces it

    def __init__(self, start_paths: list[str] | None = None):
        super().__init__()
        from ..i18n import language
        from . import theme
        self.built_with = (language(), theme.CURRENT)
        self.opts = Options.load()
        self.settings = config.settings()
        self.undo = UndoStack()
        self._group_rec: Recorder | None = None    # one undo step across several writes
        self._group_errors: list[str] = []
        self._auto_done: dict[int, Track] = {}     # finished by the automatic run; holding the
                                                   # tracks keeps their ids from being reused
        self._mood_done: dict[int, Track] = {}     # analyzed in this list, no need to run again
        self._last_batch: list = []
        self._provider_problems: set[str] = set()
        self.current_dir = ""
        # isabs() also drops the single characters older versions stored by mistake.
        self.dir_history: list[str] = [d for d in config.string_list(self.settings, "dirs/history")
                                       if os.path.isabs(d)]
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
        self._build_actions()
        self._build_app_menu()
        self._build_topbar()
        self._build_statusbar()
        self._restore_state()
        self._update_actions()
        # Also persist while running, so nothing is lost if the session ends abruptly.
        self._autosave = QTimer(self)
        self._autosave.setInterval(20_000)
        self._autosave.timeout.connect(self.save_state)
        self._autosave.start()
        QApplication.instance().aboutToQuit.connect(self.save_state)

        if start_paths:
            QTimer.singleShot(0, lambda: self.load_paths(start_paths, False))

    # ------------------------------------------------------------------ layout
    def _build_panel(self):
        self.panel = TagPanel()
        self.panel.blank_comments = self.opts.drop_comments
        self._rebuild_panel()
        self.panel.changed.connect(self._update_actions)
        self.panel.save_requested.connect(self.save_by_user)
        self.panel.directory_chosen.connect(lambda d: self.load_paths([os.path.expanduser(d)], False))
        self.panel.cover.request.connect(self._cover_command)
        self.panel.cover.fetch_entries = self._cover_fetch_entries
        host = QWidget()
        host.setObjectName("PanelHost")
        host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(12, 10, 12, 4)
        title = QLabel(tr("Tag-Panel"))
        title.setObjectName("PanelTitle")
        self.panel_count = QLabel()
        self.panel_count.setObjectName("PanelCount")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.panel_count)
        column.addLayout(head)
        column.addWidget(self.panel, 1)
        self._panel_column = column             # the status box joins it with the status bar
        self.panel_dock = QDockWidget(tr("Tag-Panel"), self)
        self.panel_dock.setObjectName("TagPanel")
        self.panel_dock.setWidget(host)
        self.panel_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)     # Ctrl+Q hides it
        self.panel_dock.setTitleBarWidget(QWidget())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.panel_dock)

    def _build_topbar(self):
        self.topbar = TopBar(self)
        self.setMenuWidget(self.topbar)
        self.search = self.topbar.search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.apply_filter)
        self.search.textChanged.connect(lambda _: self._search_timer.start())

    def _build_app_menu(self):
        m = self.app_menu = QMenu(self)
        for a in (self.act_options, self.act_setup, self.act_ext_tags, self.act_panel):
            m.addAction(a)
        self.columns_menu = m.addMenu(tr("Spalte&n"))
        self.columns_menu.aboutToShow.connect(self._fill_columns_menu)
        self.view.header_menu.connect(lambda position: self.columns_menu.exec(position))
        m.addAction(self.act_customize_panel)
        m.addSeparator()
        self.sources_menu = m.addMenu(tr("&Taggen"))
        self.sources_menu.aboutToShow.connect(self._fill_sources_menu)
        m.addSeparator()
        for a in (self.act_open_cfg, self.act_help, self.act_about):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_exit)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_msg = QLabel(tr("Bereit"))
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setMaximumHeight(8)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.status_sel = QLabel()
        self.status_all = QLabel()
        sb.addWidget(self.status_msg, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.status_sel)
        sb.addPermanentWidget(self.status_all)
        from .statusbox import StatusBox, holder
        self.status_box = StatusBox(self.progress)
        self._status_holder = holder(self.status_box)
        self._panel_column.addWidget(self._status_holder)
        self.apply_status_box()
        self._update_status()

    def apply_status_box(self) -> None:
        """Messages in the box of the tag panel, or as before in the status bar."""
        from . import statusbox
        on = statusbox.enabled(self.settings)
        self._status_holder.setVisible(on)
        self.status_box.timer.start() if on else self.status_box.timer.stop()
        self.status_msg.setVisible(not on)
        self.progress.setMaximumWidth(0 if on else 200)     # the box shows the progress then

    # ------------------------------------------------------------------ actions
    def _act(self, text, slot=None, shortcut=None, tip="", icon_name=None, checkable=False,
             extra_shortcuts=()) -> QAction:
        a = QAction(tr(text), self)
        if icon_name:
            a.setIcon(icon(icon_name))
        keys = []
        if shortcut:
            keys.append(QKeySequence(mac_keys(shortcut)))
        keys += [QKeySequence(mac_keys(k)) for k in extra_shortcuts]
        keys += [QKeySequence(k) for k in extra_keys(shortcut or "")]
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
        self.act_save = A("Tag &speichern", self.save_by_user, "Ctrl+S", "Schreibt die Änderungen in die markierten Dateien.", "save")
        self.act_remove = A("Tag ent&fernen", self.remove_tags, "Ctrl+R", "Löscht alle Tags der markierten Dateien.", "remove")
        self.act_dir = A("Ordner öffnen...", self.choose_directory, "Ctrl+D", "Ersetzt die Liste durch einen anderen Ordner.", "folder-open")
        self.act_add_dir = A("Ordner hinzufügen...", self.add_directory, "Ctrl+H", "Lädt einen weiteren Ordner in die Liste.", "folder-add")
        self.act_options = A("&Optionen...", self.show_options, "Ctrl+O", "Öffnet die Einstellungen.", "options")
        self.act_setup = A("&Einrichtung...", self.show_setup)
        self.act_open_cfg = A("Einstellungsordner öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(config.config_dir())))
        self.act_exit = A("&Beenden", self.close, "Alt+F4", "Schließt PsyTags.")
        self.act_refresh = A("&Aktualisieren", self.refresh, "F5", "Liest die Dateien der Liste neu ein.", "refresh")
        # Edit
        self.act_undo = A("&Rückgängig", self.do_undo, "Ctrl+Z", "Nimmt den letzten Schritt zurück.", "undo",
                          extra_shortcuts=["Ctrl+Shift+Z"])
        self.act_redo = A("&Wiederholen", self.do_redo, "Ctrl+Y", "Holt den zuletzt zurückgenommenen Schritt zurück.", "redo")
        self.act_copy = A("K&opieren", self.copy, "Ctrl+C", "Legt den markierten Text oder die Tags der Datei in die Zwischenablage.")
        self.act_paste = A("&Einfügen", self.paste, "Ctrl+V", "Fügt den Inhalt der Zwischenablage ein.")
        self.act_find = A("S&uchen...", self.focus_search, "Ctrl+F", "Sucht in allen Spalten der Dateiliste.",
                          extra_shortcuts=["F3"])
        self.act_remove_files = A("E&ntfernen", self.remove_from_list, "Del", "Nimmt die markierten Dateien aus der Liste. Auf der Festplatte bleiben sie.")
        self.act_select_all = A("&Alle Dateien auswählen", self.view.selectAll, "Ctrl+A", "Markiert jede Datei in der Liste.")
        # Cover
        self.act_cover_add = A("Cover hinzu&fügen...", lambda: self._cover_command("add"), "Ctrl+Alt+A")
        self.act_cover_fetch = A("Cover holen", lambda: self.fetch_covers(), None,
                                 "Holt die Cover der ausgewählten Alben aus dem Cover Art Archive.")
        self.act_cover_fetch_all = A("Cover aller Alben holen", lambda: self.fetch_covers(list(self.model.rows)),
                                     None, "Holt die Cover aller Alben der Liste über die Cover-Quellen.")
        # View
        self.act_ext_tags = A("&Alle Felder...", self.extended_tags, "Alt+T", "Zeigt alle Felder der markierten Datei.", "extended")
        self.act_panel = self.panel_dock.toggleViewAction()
        self.act_panel.setText(tr("&Tag-Panel"))
        self.act_panel.setShortcut(QKeySequence(mac_keys("Ctrl+Q")))
        self.addAction(self.act_panel)
        self.act_customize_cols = A("Spalten anpassen...", self.customize_columns)
        self.act_customize_panel = A("Tag-Panel anpassen...", self.customize_panel)
        # Workflow
        self.act_ttf = A("Umbenennen...", self.rename_files, "Alt+1",
                         "Benennt die ausgewählten Dateien nach dem eingestellten Schema um.", "tag-filename")
        self.act_ttf_all = A("Alle Dateien umbenennen...", self.rename_all_files, None,
                             "Benennt alle Dateien der Liste nach dem eingestellten Schema um.", "tag-filename")
        self.act_numbers = A("Nummern schreiben", lambda: self.number_selected(), "Ctrl+K",
                             "Schreibt Track- und Discnummern der ausgewählten Alben.", "numbering")
        self.act_numbers_all = A("Nummern aller Alben schreiben", lambda: self.number_selected(list(self.model.rows)),
                                 None, "Schreibt Track- und Discnummern aller Alben der Liste.", "numbering")
        # Tag sources
        self.act_last_source = A("MusicBrainz durchsuchen", lambda: self.run_source(),
                                 "Ctrl+I", "Sucht bei MusicBrainz und zeigt die Trefferliste.", "web")
        self.act_last_source_quick = A("MusicBrainz durchsuchen (Schnell)",
                                       lambda: self.run_source(quick=True), "Ctrl+Shift+I")
        self.act_lastfm = A("Genres von Last.fm holen",
                            lambda: self.fetch_lastfm(self.view.selected_tracks()), "Ctrl+Shift+L",
                            "Holt Genres für die ausgewählten Dateien, ohne Tag-Quelle.",
                            "genres")
        self.act_lastfm_all = A("Genres aller Alben von Last.fm holen",
                                lambda: self.fetch_lastfm(list(self.model.rows)), None,
                                "Holt Genres für alle Dateien der Liste.", "genres")
        self.act_moods = A("Moods der Auswahl analysieren", self.analyze_selected_moods, "Ctrl+Shift+M",
                           "Ermittelt die Moods der ausgewählten Dateien aus dem Audio.", "moods")
        self.act_moods_all = A("Moods aller Dateien analysieren", self.analyze_all_moods, "Ctrl+Alt+M",
                               "Ermittelt die Moods aller Dateien in der Liste aus dem Audio.", "moods")
        self.act_auto_mb = A("MusicBrainz automatisch", self.auto_musicbrainz, "Ctrl+Shift+B",
                             "Taggt das markierte Album, wenn es sicher erkannt wird, sonst öffnet sich die Trefferliste.",
                             "auto-album")
        self.act_auto_mb_all = A("MusicBrainz für alle Alben", self.musicbrainz_all, None,
                                 "Taggt alle Alben der Liste ohne MusicBrainz-Album-ID, wenn sie sicher erkannt "
                                 "werden; Moods bleiben außen vor.", "auto-album")
        self.act_auto_all = A("Alle Alben automatisch", self.auto_all_albums, "Ctrl+Alt+B",
                              "Analysiert die Moods und taggt alle Alben der Liste; unsichere Alben bleiben unverändert.",
                              "auto-all")
        self.act_batch_summary = A("Übersicht des letzten Laufs...", self.show_batch_summary, None,
                                   "Zeigt das Ergebnis des letzten automatischen Laufs.", "batch-summary")
        # Tools / misc
        self.act_play = A("Abspielen", self.play, "F4", "Öffnet die markierten Dateien im Standard-Player.", extra_shortcuts=["Ctrl+Shift+T"])
        # Help
        self.act_help = A("&Hilfe", self.show_help, "F1", "", "help")
        self.act_about = A("Über PsyTags...", self.about)
        # Focus cycling between panes
        QShortcut(QKeySequence(mac_keys("Ctrl+Tab")), self, lambda: self._cycle_focus(1))
        QShortcut(QKeySequence(mac_keys("Ctrl+Shift+Tab")), self, lambda: self._cycle_focus(-1))

    def _restore_state(self):
        g = self.settings.value(geometry_key("window/geometry"))
        if g is not None:
            self.restoreGeometry(g)
        else:
            self.resize(1400, 850)
        s = self.settings.value("window/state")
        if s is not None:
            self.restoreState(s, LAYOUT_VERSION)
        w = self.settings.value("window/panel_width")
        if w:
            self.resizeDocks([self.panel_dock], [int(w)], Qt.Orientation.Horizontal)
        else:
            self.resizeDocks([self.panel_dock], [355], Qt.Orientation.Horizontal)

    STATUS_TIP_MS = 4000

    def event(self, e):
        # The description of a hovered button or menu entry: Qt keeps it in the status bar until
        # another one comes, so after a run the last one stood there for good. It goes by itself.
        if e.type() == QEvent.Type.StatusTip:
            tip = e.tip()
            if tip:
                self.statusBar().showMessage(tip, self.STATUS_TIP_MS)
            else:
                self.statusBar().clearMessage()
            return True
        return super().event(e)

    def closeEvent(self, e):
        if self.panel.dirty and self.panel.tracks and not self._save_or_drop(self.panel.tracks):
            e.ignore()
            return
        self.save_state()
        super().closeEvent(e)

    def save_state(self) -> None:
        """Persist everything the user arranged; called on close, on quit and periodically."""
        config.save_columns(self.model.all_columns)
        self._save_sort()
        if not self.isMinimized():
            self.settings.setValue(geometry_key("window/geometry"), self.saveGeometry())
            self.settings.setValue("window/state", self.saveState(LAYOUT_VERSION))
            if self.panel_dock.isVisible() and not self.panel_dock.isFloating():
                self.settings.setValue("window/panel_width", self.panel_dock.width())
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
            return f"{h:02d}:{rem // 60:02d}:{rem % 60:02d} · {fmt_size(sum(t.size for t in ts))}"
        chosen = tr("{1} ausgewählt", len(sel)) if sel else ""
        self.status_sel.setText(f"{chosen} · {seg(sel)}" if sel else "")
        self.panel_count.setText(chosen)
        count = f"{len(rows)}/{len(self.model.all)}" if self.model.filter_text else str(len(rows))
        self.status_all.setText(f"{tr('{1} Dateien', count)} · {seg(rows)}")

    def message(self, text: str, timeout: int = 0):
        """Show ``text``; with ``timeout`` (ms) it goes away again. A newer message ends the
        timeout of an older one, so a message meant to stay is never cleared by it."""
        if getattr(self, "_message_timer", None) is None:
            self._message_timer = QTimer(self)
            self._message_timer.setSingleShot(True)
            self._message_timer.timeout.connect(lambda: self._show_message(""))
        self._message_timer.stop()
        self._show_message(text)
        if timeout:
            self._message_timer.start(timeout)

    def _show_message(self, text: str) -> None:
        self.status_msg.setText(text or tr("Bereit"))
        self.status_box.show_message(text)

    def _update_actions(self):
        has_sel = bool(self.view.selectionModel().hasSelection())
        for a in (self.act_remove, self.act_copy, self.act_remove_files, self.act_ttf,
                  self.act_numbers, self.act_moods, self.act_ext_tags, self.act_play,
                  self.act_cover_add, self.act_cover_fetch, self.act_lastfm,
                  self.act_auto_mb):
            a.setEnabled(has_sel)
        for a in (self.act_auto_all, self.act_moods_all, self.act_ttf_all, self.act_auto_mb_all,
                  self.act_numbers_all, self.act_cover_fetch_all, self.act_lastfm_all):
            a.setEnabled(bool(self.model.rows))
        self.act_batch_summary.setEnabled(bool(self._last_batch))
        self.act_save.setEnabled(has_sel)
        self.act_undo.setEnabled(self.undo.can_undo())
        self.act_redo.setEnabled(self.undo.can_redo() or self.last_action is not None)

    # ------------------------------------------------------------------ loading
    def load_paths(self, paths: list[str], add: bool):
        paths = [os.path.abspath(p) for p in paths if p and os.path.exists(p)]
        if not paths:
            return
        if self.panel.dirty and self.panel.tracks and not self._save_or_drop(self.panel.tracks):
            return
        if not add:
            # Several folders dropped: the first one becomes the working directory.
            d = paths[0] if os.path.isdir(paths[0]) else os.path.dirname(paths[0])
            self._set_current_dir(d)
        if self._loader_thread is not None:
            self._loader.abort = True
            self._loader_thread.quit()
            self._loader_thread.wait()
        self.message(tr("Ordner wird gelesen"))
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
        self.settings.setValue("dirs/history", self.dir_history[:30])

    def _load_progress(self, i, n):
        self.progress.setMaximum(n)
        self.progress.setValue(i)
        self.message(tr("Dateien laden … {1} von {2}", i, n))

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
        d = QFileDialog.getExistingDirectory(self, tr("Ordner öffnen"), self.current_dir
                                             or os.path.expanduser("~"))
        if d:
            self.load_paths([d], False)

    def add_directory(self):
        d = QFileDialog.getExistingDirectory(self, tr("Ordner hinzufügen..."), self.current_dir
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

    # ------------------------------------------------------------------ selection
    def _selection_changed(self, *_):
        new = self.view.selected_tracks()
        if self.panel.dirty and self._panel_tracks and self.opts.save_on_selection_change \
                and [id(t) for t in new] != [id(t) for t in self._panel_tracks] \
                and not self._save_or_drop(self._panel_tracks):
            sm = self.view.selectionModel()          # stay where the inputs belong
            blocked = sm.blockSignals(True)
            self.view.select_tracks(self._panel_tracks, scroll=False)
            sm.blockSignals(blocked)
            self.view.viewport().update()
            return
        self._panel_tracks = new
        self.panel.load(new)
        self._update_status()
        self._update_actions()

    def _cycle_focus(self, d: int):
        order = [self.panel, self.search, self.view]
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
                self.message(tr("Tags schreiben … {1} von {2}", i, n))
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

    def _write_panel(self, tracks: list[Track], with_preset: bool = False) -> bool:
        """Write the panel inputs to ``tracks``. Returns False if a file failed;
        the inputs then stay dirty so they are not lost."""
        from ..websources import albummatch
        pending = self.panel.pending(with_preset)
        covers = self.panel.cover.covers if self.panel.covers_dirty else None

        def apply(t: Track):
            for name, value in pending.items():
                t.set(name, value or "")
            if with_preset and pending.get("COMMENT", "") is None:
                albummatch.drop_comments(t)
            if covers is not None:
                t.data.covers = list(covers)
        ok = self._write(tr("Tag speichern"), tracks, apply) == len(tracks)
        if ok:
            self.panel.clear_dirty()
        return ok

    def _save_or_drop(self, tracks: list[Track]) -> bool:
        """Save the panel inputs before the panel shows something else. True if it
        may go on: saved, or the user chose to drop the inputs after a failure."""
        with self._undo_group(tr("Tag speichern")):
            ok = self._write_panel(tracks)
        if ok:
            return True
        answer = QMessageBox.question(
            self, tr("Fehler"),
            tr("Die Eingaben ließen sich nicht speichern:") + "\n\n"
            + "\n".join(self._group_errors[:10]) + "\n\n" + tr("Eingaben verwerfen?"),
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard

    def save_by_user(self):
        """Ctrl+S or Enter: everything the panel shows, also the comment that starts out blank."""
        self.save_tags(True)

    def save_tags(self, with_preset: bool = False):
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        if self._write_panel(tracks, with_preset):
            self.panel.load(tracks)
            self.message(tr("Tag-Informationen gespeichert"), 3000)

    def remove_tags(self):
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        if QMessageBox.question(self, "PsyTags", tr("Alle Tags aus {1} Dateien löschen?",
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
        self.message(tr("Tag von {1} Datei(en) kopiert", len(tracks)), 3000)

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
        convert.fix_folder_case(moves)
        if remove_old_albums:
            self._trash_old_albums(moves)
        self._update_actions()

    def _trash_old_albums(self, moves: list[tuple[str, str]]) -> None:
        """The albums now live in their new folders: the old ones, with whatever is left in them
        (images, cue sheets, ...), go to the recycle bin."""
        from PySide6.QtCore import QFile
        leftovers = convert.emptied_album_folders(moves) + convert.leftovers_in_renamed_albums(moves)
        failed = [f for f in leftovers if not QFile.moveToTrash(f)]
        if len(leftovers) > len(failed):
            self.message(tr("{1} alte Ordner oder Dateien in den Papierkorb verschoben", len(leftovers) - len(failed)), 8000)
        if failed:
            QMessageBox.warning(self, tr("Fehler"), tr("Diese Ordner konnten nicht entfernt werden:\n{1}", "\n".join(failed)))

    # ------------------------------------------------------------------ actions
    # ------------------------------------------------------------------ tag sources
    def _fill_sources_menu(self):
        m = self.sources_menu
        m.clear()
        self._add_source_entries(m.addMenu(tr("&Manuell suchen")))
        self._add_cover_entries(m.addMenu(tr("Cover &holen")))
        m.addSeparator()
        for a in (self.act_moods, self.act_moods_all, self.act_auto_mb, self.act_auto_mb_all, self.act_auto_all,
                  self.act_batch_summary):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_lastfm)
        m.addAction(self.act_lastfm_all)

    def _cover_min_size(self) -> int:
        try:
            return int(self.settings.value("tagsources/cover_min_size", 1000))
        except (TypeError, ValueError):
            return 1000

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

    def _cover_fetch_entries(self) -> list[tuple[str, str]]:
        """(command, menu text) for the cover context menu."""
        if not self.view.selected_tracks():
            return []
        from ..websources import coverart
        out = [("fetch_mb", tr("Cover von {1} laden", coverart.NAME))]
        out += [(f"provider:{s.name}", tr("Cover von {1} laden", s.name))
                for s in self._cover_sources() if hasattr(s, "name")]
        return out

    def fetch_archive_cover(self, tracks, ask: bool = True,
                            ids: tuple[str, str] | None = None, keep: bool = False) -> str:
        """Front cover of one album from the Cover Art Archive; replaces the front cover.
        ``ask``: the user may take a too small cover anyway. ``ids`` (release, release group)
        default to the tags of the files. Returns "" if it worked, otherwise what went wrong."""
        from ..websources import coverart
        from ..websources import http as wshttp
        first = lambda name: (tracks[0].get(name) or [""])[0]
        release, group = ids or (first("MUSICBRAINZ_ALBUMID"), first("MUSICBRAINZ_RELEASEGROUPID"))
        if not (release or group):
            return tr("Keine MusicBrainz-ID")
        label = coverart.NAME
        try:
            data = self._background(tr("Cover von {1} laden", label), lambda: coverart.fetch_front(release, group))
        except wshttp.ServerError:
            return tr("{1} antwortet gerade nicht", label)
        except wshttp.FetchError as e:
            return str(e).splitlines()[0]
        if not data:
            return tr("Kein Cover bei {1} gefunden", label)
        return _store_front_cover(self, tracks, data, label, ask, keep)

    def _cover_sources(self) -> list:
        """The sources that are switched on, in order. Files are read anew, a bad one is reported once."""
        from ..websources import coverprovider
        providers, problems = coverprovider.discover()
        new = [p for p in problems if p not in self._provider_problems]
        if new:
            self._provider_problems.update(new)
            self.message(new[0], 10000)
        return coverprovider.active(providers)

    def fetch_cover_chain(self, tracks, ask: bool = True, ids: tuple[str, str] | None = None,
                          pick: bool = False, keep: bool = False) -> str:
        """The sources in their order until one delivers. ``pick``: a provider without a certain
        match shows its results. ``keep``: files that have a cover keep it.
        Returns "" if a cover was written, otherwise why not."""
        from ..websources import coverprovider
        reasons = []
        for source in self._cover_sources():
            if source == coverprovider.ARCHIVE:
                reason = self.fetch_archive_cover(tracks, ask, ids, keep=keep)
            else:
                reason = self.fetch_provider_cover(source, tracks, ask, pick, keep=keep)
            if not reason or reason == tr("Abgebrochen"):
                return reason
            reasons.append(reason)
        return "; ".join(reasons) or tr("Keine Cover-Quelle eingeschaltet")

    def fetch_provider_cover(self, provider, tracks, ask: bool = True, pick: bool = False, keep: bool = False) -> str:
        """Front cover of one album from a cover provider. Only a certain match is taken
        without asking; with ``pick`` the user chooses from the results otherwise.
        Returns "" if a cover was written, otherwise why not."""
        from types import SimpleNamespace
        from ..websources import coverfetch, coverprovider
        from ..websources import http as wshttp
        from .dialogs.tagsources import ResultsDialog
        first = lambda name: (tracks[0].get(name) or [""])[0]
        album, artist = first("ALBUM"), first("ALBUMARTIST") or first("ARTIST")
        name = provider.name
        wait = self._waiting if ask or pick else self._background
        try:
            rows = wait(tr("Cover-Suche bei {1}", name), lambda: coverprovider.search(provider, artist, album))
            if not rows:
                return tr("Kein Cover bei {1} gefunden", name)
            best = coverfetch.confident(coverfetch.rank(rows, album, artist, len(tracks)))
            row = best.row if best else None
            if row is None:
                if not pick:
                    return tr("Kein sicherer Treffer bei {1}", name)
                d = ResultsDialog(SimpleNamespace(name=name, index_columns=["Album", "Artist", "Tracks"]), rows, self)
                d.set_heading(tr("Cover von {1}", name), tr("Bitte das passende Album wählen"))
                row = d.selected() if d.exec() == 1 else None
                if row is None:
                    return tr("Abgebrochen")
            data = wait(tr("Cover von {1} laden", name), lambda: coverprovider.image(provider, row))
        except _Canceled:
            return tr("Abgebrochen")
        except (wshttp.FetchError, coverprovider.ProviderError) as e:
            return str(e).splitlines()[0]
        return _store_front_cover(self, tracks, data, name, ask, keep)

    def _waiting(self, label: str, fn):
        """Like _background, but with a visible window and Cancel; the answer of a call
        that was left behind is dropped. Raises _Canceled."""
        from PySide6.QtCore import QEventLoop
        box: dict = {}

        def work():
            try:
                box["v"] = fn()
            except Exception as e:      # reported in the UI thread
                box["e"] = e
        th = threading.Thread(target=work, daemon=True)
        th.start()
        dlg = _StayingProgress(label, 1, self)
        dlg.setWindowTitle("PsyTags")
        dlg.follow_activity()
        dlg.count_label.hide()
        dlg.bar.setRange(0, 0)                  # no steps to count
        try:
            while th.is_alive() and not dlg.stop.is_set():
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
                th.join(0.02)
            canceled = dlg.stop.is_set()
        finally:
            dlg.finish()
        if canceled:
            raise _Canceled()
        if "e" in box:
            raise box["e"]
        return box.get("v")

    def fetch_covers(self, tracks=None) -> None:
        """Cover step: every selected album (or each of ``tracks``) on its own, several ones in a
        progress window."""
        from ..websources import albumauto
        tracks = self.view.selected_tracks() if tracks is None else tracks
        if not tracks:
            return
        albums = albumauto.group_albums(tracks)
        several = len(albums) > 1
        dlg = None
        if several:
            dlg = _StayingProgress(tr("Cover holen ..."), len(albums), self)
            dlg.setWindowTitle("PsyTags")
            dlg.follow_activity()
        results = []
        try:
            with self._undo_group(tr("Cover holen")):
                for i, album in enumerate(albums):
                    if dlg:
                        if dlg.stop.is_set():
                            break
                        dlg.setLabelText(albumauto.album_title(album))
                        dlg.setValue(i)
                    results.append(self.fetch_cover_chain(album, ask=not several))
        finally:
            if dlg:
                dlg.finish()
        failed = [r for r in results if r]
        if not several and failed:
            self.message(failed[0], 8000)
        elif failed:
            self.message(tr("{1} von {2} Alben ohne Cover", len(failed), len(results)), 8000)
        else:
            self.message(tr("Cover geladen: {1}", len(results)), 6000)

    def fetch_cover_from_source(self, tracks, manual: bool = False,
                                interactive: bool = True) -> str | None:
        """Cover-only fetch from MusicBrainz; replaces the front cover.
        ``manual``: started by the user, so a too small cover may be taken after asking.
        Without ``interactive`` no dialog opens. Returns None if it did not run, "" if it
        worked, otherwise what went wrong."""
        from ..websources import coverart, coverfetch, musicbrainz
        from ..websources import http as wshttp
        from .dialogs.tagsources import ResultsDialog
        if not tracks:
            return None
        src = musicbrainz.Source()
        label = coverart.NAME
        try:
            rows, matches = self._background(tr("Cover-Suche bei {1}", label),
                                             lambda: coverfetch.search(src, tracks))
        except wshttp.FetchError as e:
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
        except (wshttp.FetchError, OSError) as e:
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
            d.set_heading(tr("Cover von {1}", label), tr("Bitte das passende Album wählen"))
            if d.exec() != 1 or d.selected() is None:
                return tr("Abgebrochen")
            row = d.selected()
            try:
                got = self._background(tr("Cover von {1} laden", label),
                                       lambda: coverfetch.fetch_cover(src, row))
            except (wshttp.FetchError, OSError) as e:
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
        new = tags.Cover(data, mime, 3, label)

        def apply(t):
            t.data.covers = [new] + [c for c in t.data.covers if c.type != 3]
        self._write(tr("Cover von {1}", label), tracks, apply)
        self.panel.load(self.view.selected_tracks())
        from PySide6.QtGui import QImage
        img = QImage.fromData(data)
        self.message(tr("Cover von {1}: {2}x{3}", label, img.width(), img.height()), 6000)
        return ""

    def _add_source_entries(self, m: QMenu) -> None:
        selected = bool(self.view.selected_tracks())
        a = m.addAction("MusicBrainz …", lambda _=False: self.run_source())
        a.setEnabled(selected)
        second = self._tag_fallback()
        if second is None:
            m.addAction(tr("Discogs (kein Token eingetragen)")).setEnabled(False)
        else:
            m.addAction(f"{second.name} …", lambda _=False: self.run_source(src=second)).setEnabled(selected)

    def _add_cover_entries(self, m: QMenu) -> None:
        """The cover sources: all in their order, or one of them."""
        m.addAction(tr("Alle Quellen der Reihe nach"), lambda: self.fetch_covers()).setEnabled(bool(self.view.selected_tracks()))
        m.addSeparator()
        for cmd, text in self._cover_fetch_entries():
            m.addAction(text, lambda _=False, cmd=cmd: self._cover_command(cmd))

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

    def run_source(self, quick: bool = False, note: str = "", src=None):
        """Search a tag source by hand, MusicBrainz unless ``src`` says otherwise:
        search form, result list, adjust dialog."""
        from ..websources import albumauto, coverart, musicbrainz
        from ..websources import http as wshttp
        from .dialogs.tagsources import AdjustDialog, ResultsDialog, SearchDialog
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        src = src or musicbrainz.Source()
        name = src.name
        values = src.prefill(tracks)
        rows: list = []
        row = None
        stage = "search"
        while True:
            if stage == "search":
                if not quick:
                    d = SearchDialog(src, values, self)
                    if not d.exec():
                        return
                    values = d.values()
                quick = False
                try:
                    rows = self._background(tr("Suche bei {1}", name),
                                            lambda: src.search(values))
                except wshttp.FetchError as e:
                    if QMessageBox.warning(self, name, str(e), QMessageBox.StandardButton.Retry
                                           | QMessageBox.StandardButton.Cancel) \
                            == QMessageBox.StandardButton.Retry:
                        continue
                    return
                if values == src.prefill(tracks) and albumauto.needs_second_search(rows, tracks):
                    # e.g. "Album (Bonus Tracks Edition)" when the database only knows "Album"
                    for second in albumauto.fallback_searches(src, tracks):
                        try:
                            more = self._background(tr("Suche bei {1}", name),
                                                    lambda: src.search(second))
                        except wshttp.FetchError:
                            more = []
                        if more:
                            rows, values = more, second
                            break
                if not rows:
                    if QMessageBox.information(
                            self, name, tr("Keine Treffer."),
                            QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel) \
                            == QMessageBox.StandardButton.Retry:
                        continue
                    return
                rows = albumauto.digital_first(rows, len(tracks), self.opts.prefer_digital)
                stage = "results"
            if stage == "results":
                d = ResultsDialog(src, rows, self)
                if note:
                    d.add_note(note)
                r = d.exec()
                if r == 2:
                    stage = "search"
                    continue
                if not r:
                    return
                row = d.selected()
                stage = "album"
            if stage == "album":
                try:
                    album = self._background(tr("Album von {1} laden", name), lambda: src.album(row))
                    cover = None
                    if album.cover_url:
                        try:
                            cover = self._background(tr("Cover laden"), lambda: src.cover(album))
                        except Exception:
                            cover = None
                except wshttp.FetchError as e:
                    if QMessageBox.warning(self, name, str(e), QMessageBox.StandardButton.Retry
                                           | QMessageBox.StandardButton.Cancel) \
                            == QMessageBox.StandardButton.Retry:
                        continue
                    return
                d = AdjustDialog(album, self.view.selected_tracks() or tracks, cover, self)
                r = d.exec()
                if r == 2:
                    stage = "results"
                    continue
                if not r:
                    return
                plan = d.plan()
                # the cover comes from the cover sources in their order, as in the automatic, unless
                # the user unticked the one shown; that one is taken only when the cover step is off
                declined = bool(cover) and not d.use_cover()
                chain = not declined and self.opts.auto_cover
                return self._finish_source_import(name, plan, cover if d.use_cover() and not chain else None,
                                                  d.leftovers(), complete=len(plan) == d.album.tracks,
                                                  archive=(coverart.ids_of(album) or ("", "")) if chain else ())

    # ------------------------------------------------------------------ views
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
        """Tag Panel from usrfields.ini; Genres and Moods always close it with full-width rows."""
        fields = [f for f in config.load_panel() if f.value.upper() not in ("GENRE", "MOOD")]
        fields += [config.PanelField(tr("Genres"), "GENRE", size=12, version=1),
                   config.PanelField(tr("Moods"), "MOOD", size=12, version=1)]
        self.panel.build(fields, config.load_custom_values())
        self.panel.set_directories(self.current_dir, self.dir_history)

    def lastfm_settings(self):
        self._open_options("lastfm")

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
    def analyze_selected_moods(self):
        self.analyze_moods(self.view.selected_tracks())

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
        level = self.opts.mood_level

        def work():
            try:
                box["r"] = ma.analyze_files([t.path for t in tracks], lambda path: analyzer.moods(path, level),
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
    def auto_musicbrainz(self) -> None:
        """Tag the selected album without dialogs when it is certain, else show the results."""
        from ..websources import albumauto, musicbrainz
        from ..websources import http as wshttp
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        groups = albumauto.group_albums(tracks)
        if len(groups) > 1 and len({albumauto.album_folder(g) for g in groups}) == len(groups):
            # several albums selected: one after the other, like the run over all albums
            self._run_albums(groups, tr("MusicBrainz für die Auswahl"), time.monotonic())
            return
        src = musicbrainz.Source()
        if len({(t.get("ALBUM") or [""])[0] for t in tracks}) != 1:
            self.run_source()
            return
        filled = self._fill_gaps(tracks)
        if filled is not None:
            self.message(filled.detail, 10000)
            return
        try:
            second = self._tag_fallback()
            used, res = self._background(tr("MusicBrainz durchsuchen: {1}", albumauto.album_title(tracks)),
                                         lambda: albumauto.find_with_fallback(src, second, tracks, self.opts.prefer_digital))
        except (wshttp.FetchError, OSError) as e:
            QMessageBox.warning(self, "MusicBrainz", str(e))
            return
        if res.match is None:
            self.run_source(quick=True, note=tr("Nicht sicher erkannt: {1}", res.reason))
            return
        self._import_match(used, res.match, interactive=True)
        self._auto_done.update({id(t): t for t in tracks})
        self.message(tr("{1}: {2} ({3}) automatisch gewählt, {4} Dateien", used.name,
                        res.album.value("ALBUM", 0), albumauto.release_year(res.match), len(res.match.mapping)), 10000)

    def _tag_fallback(self):
        """The source for albums MusicBrainz leaves open, None without a token."""
        from ..websources import discogs
        return discogs.from_settings()

    def _import_match(self, src, match, interactive: bool) -> tuple[str | None, str | None]:
        """Write a certain match; returns the outcome of the cover and genre steps."""
        from ..websources import albumauto, coverart
        album = match.release.key
        disabled = set(config.string_list(self.settings, "tagsources/disabled_fields"))
        return self._finish_source_import(src.name, albumauto.plan_for(match, disabled),
                                          None, match.leftover_keys, interactive, complete=True,
                                          archive=coverart.ids_of(album) or ("", ""))   # no IDs: the other cover sources

    def _finish_source_import(self, name: str, plan: list, cover: bytes | None,
                              leftovers: list, interactive: bool = True,
                              complete: bool = False,
                              archive: tuple[str, str] | None = None) -> tuple[str | None, str | None]:
        """Shared end of every tag source import: write, order the album, number it (only when
        ``complete``, i.e. every track has its file), ask about files without a track, then
        cover source and genres. Returns (cover, genres): None did not run, "" worked, else why not."""
        from ..websources import albummatch
        written = [t for t, _ in plan]
        # the automatic leaves files that have a cover alone if the user wants so; files without
        # one still get it
        keep = not interactive and not self.opts.replace_covers
        bare = {id(t) for t in written if not t.data.covers}
        use_cover = bool(cover) and (not keep or bool(bare)) and self._cover_big_enough(cover, name)
        mime = "image/png" if cover and cover[:4] == b"\x89PNG" else "image/jpeg"
        values_by_track = {id(t): v for t, v in plan}
        drop_comments = archive is not None and self.opts.drop_comments     # chosen by the automatic or from MusicBrainz

        def apply(t):
            vals = values_by_track.get(id(t))
            if vals is None:
                return False
            if drop_comments:
                albummatch.drop_comments(t)
            for k, v in albummatch.clean_import(vals, bool(t.get("MOOD")), self.opts.year_only).items():
                t.set(k, v)
            if use_cover and (not keep or id(t) in bare):     # the source's cover replaces the existing ones
                t.data.covers = [tags.Cover(cover, mime, 3, name)]
        saved = self._write(name, written, apply)
        self.panel.clear_dirty()                # the import replaces what was typed into the panel
        selection = self.view.selected_tracks()
        self.model.sort_album(written, last=leftovers)
        if complete and self.opts.auto_numbers:
            self._renumber(written)
        self.view.select_tracks(selection, scroll=interactive)     # a batch must not move the user's view
        self.panel.load(selection)
        if interactive and leftovers:
            self._offer_trash(leftovers)
            self.view.select_tracks([t for t in selection if os.path.exists(t.path)])
        # Last.fm runs while the cover is fetched; results are written after.
        job = self.start_lastfm(written, interactive) if self._lastfm_enabled() else None
        # No IDs: not from MusicBrainz. Empty: settled in the adjust dialog.
        run_chain = archive and self.opts.auto_cover and (not keep or bool(bare))
        cover_result = self.fetch_cover_chain(written, False, archive, keep=keep) if run_chain else None
        outcome = cover_result, self.finish_lastfm(job, interactive) if job is not None else None
        if interactive and saved == len(written):      # a file that could not be written leaves it open
            self._note_in_summary(name, written, outcome)
        return outcome

    def _note_in_summary(self, name: str, tracks: list, outcome: tuple) -> None:
        """An album of the last automatic run that was tagged by hand is no longer open, but only
        when the import took every one of its files."""
        ids = {id(t) for t in tracks}
        for entry in self._last_batch:
            if not entry.tracks or not all(id(t) in ids for t in entry.tracks):
                continue
            entry.ok, (entry.cover, entry.genres), entry.source = True, outcome, name
            origin = [tr("Von {1}", name)] if name != "MusicBrainz" else []
            entry.detail = " · ".join([tr("Manuell getaggt")] + origin + [n for n in outcome if n])
            _remember_covers(entry)
            self._auto_done.update({id(t): t for t in entry.tracks})

    def _renumber(self, tracks: list[Track]) -> None:
        """Write track and disc numbers of one album in the format set in the options."""
        ordered = sorted(tracks, key=albumorder.sort_key)
        plan = numbering.plan(ordered, numbering.NumberFormat.load())
        self._write(tr("Nummern schreiben"), ordered,
                    lambda t: [t.set(k, v) for k, v in plan.get(id(t), {}).items()])

    def number_selected(self, tracks=None) -> None:
        from ..websources import albumauto
        selection = self.view.selected_tracks()
        tracks = selection if tracks is None else tracks
        if not tracks:
            return
        with self._undo_group(tr("Nummern schreiben")):
            for album in albumauto.group_albums(tracks):
                self._renumber(album)
        self.view.select_tracks(selection)
        self.panel.load(selection)

    def rename_files(self) -> None:
        self._rename_with(self.view.selected_tracks)

    def rename_all_files(self) -> None:
        self._rename_with(lambda: list(self.model.rows))

    def _rename_with(self, tracks_of) -> None:
        from .dialogs.rename import RenameDialog
        tracks = tracks_of()
        if not tracks:
            return
        d = RenameDialog(tracks, self)
        if not d.exec():
            return
        tokens, cleanup = d.tokens(), d.cleanup() and namescheme.FOLDER in d.tokens()

        def run() -> None:
            self._rename([(t, namescheme.target_path(t, tokens)) for t in tracks_of()], tr("Umbenennen"),
                         remove_old_albums=cleanup)
        run()
        self.last_action = run

    def _trash_files(self, tracks: list[Track]) -> list[Track]:
        """Move to the recycle bin and drop from the list; returns the files that stayed."""
        from PySide6.QtCore import QFile
        for t in tracks:
            QFile.moveToTrash(t.path)
        kept = [t for t in tracks if os.path.exists(longpath.io(t.path))]
        self.model.remove_tracks([t for t in tracks if not any(t is k for k in kept)])
        self._update_status()
        return kept

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
        todo = [g for g in albumauto.group_albums(list(self.model.rows)) if id(g[0]) not in self._auto_done]
        if not todo:
            self.message(tr("Alle Alben dieser Liste sind schon erledigt."), 6000)
            return
        started = time.monotonic()
        if self.opts.auto_moods and not self.analyze_moods([t for g in todo for t in g if id(t) not in self._mood_done]):
            return
        self._run_albums(todo, tr("Alle Alben automatisch"), started)

    def musicbrainz_all(self) -> None:
        """The MusicBrainz step for every album of the list that has no release yet; added
        files of a tagged album take its values. No moods, no dialog during the run."""
        from ..websources import albumauto
        todo = [g for g in albumauto.group_albums(list(self.model.rows))
                if id(g[0]) not in self._auto_done and not all(t.get("MUSICBRAINZ_ALBUMID") for t in g)]
        if not todo:
            self.message(tr("Alle Alben dieser Liste haben schon eine MusicBrainz-Album-ID."), 6000)
            return
        self._run_albums(todo, tr("MusicBrainz für alle Alben"), time.monotonic())

    def _run_albums(self, todo: list, title: str, started: float) -> None:
        """Album by album with a progress window, then the statistics and the summary."""
        from ..websources import albumauto, musicbrainz
        src = musicbrainz.Source()
        dlg = _StayingProgress("", len(todo), self)
        dlg.follow_activity()
        dlg.setWindowTitle(title)
        dlg.set_hint(tr("MusicBrainz lässt nur eine Anfrage pro Sekunde zu. Je nach Tageszeit kann der Abruf "
                        "deshalb länger dauern."))
        entries = []
        try:
            for i, tracks in enumerate(todo):
                if dlg.stop.is_set():
                    break
                dlg.setLabelText(albumauto.album_title(tracks))
                dlg.setValue(i)
                entries.append(self._fill_gaps(tracks) or self._auto_one(src, tracks))
        finally:
            dlg.finish()
            self._last_batch = entries
            self._update_actions()
        self.message(run_statistics(entries, time.monotonic() - started))      # stays until the next message
        self.show_batch_summary()

    def _fill_gaps(self, tracks: list[Track]):
        """Files added to an album that is already tagged (bonus tracks, say) take its values
        from the other files; MusicBrainz is not asked. None when there is no such gap."""
        from ..websources import albumauto
        plan = albumauto.album_gaps(tracks)
        if not plan:
            return None
        title = albumauto.album_title(tracks)
        values = {id(t): v for t, v in plan}

        def apply(t: Track):
            for name, value in values[id(t)].items():
                t.set(name, value)
        files = [t for t, _values in plan]
        with self._undo_group(title):
            self._write(tr("Album-Werte übernehmen"), files, apply)
        if self._group_errors:
            return albumauto.BatchEntry(title, tracks, False, tr("Schreibfehler: {1}", " · ".join(self._group_errors[:3])))
        self._auto_done.update({id(t): t for t in tracks})
        return albumauto.BatchEntry(title, tracks, True,
                                    tr("Werte des Albums für {1} Dateien ohne Release übernommen", len(files)))

    def _auto_one(self, src, tracks: list[Track]):
        from ..websources import albumauto
        title = albumauto.album_title(tracks)
        try:
            second = self._tag_fallback()
            used, res = self._background(tr("MusicBrainz durchsuchen: {1}", title),
                                         lambda: albumauto.find_with_fallback(src, second, tracks, self.opts.prefer_digital))
            if res.match is None:
                return albumauto.BatchEntry(title, tracks, False, res.reason)
            with self._undo_group(title):
                cover, genres = self._import_match(used, res.match, interactive=False)
        except Exception as e:                      # one album must not end the whole run
            return albumauto.BatchEntry(title, tracks, False, (str(e) or type(e).__name__).splitlines()[0])
        if self._group_errors:
            return albumauto.BatchEntry(title, tracks, False, tr("Schreibfehler: {1}", " · ".join(self._group_errors[:3])))
        self._auto_done.update({id(t): t for t in tracks})
        origin = [tr("Von {1}", used.name)] if used is not src else []
        detail = " · ".join([albumauto.release_label(res.match)] + origin + albumauto.match_notes(res.match)
                            + [n for n in (cover, genres) if n])
        entry = albumauto.BatchEntry(title, tracks, True, detail, list(res.match.leftover_keys), cover, genres,
                                     source=used.name)
        _remember_covers(entry)
        return entry

    def show_batch_summary(self) -> None:
        from .dialogs.tagsources import BatchSummaryDialog
        if not self._last_batch:
            self.message(tr("Noch kein automatischer Lauf in dieser Sitzung."), 6000)
            return
        while True:
            self._notice_new_covers()
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
            if action == "musicbrainz":             # an album from Discogs: look at MusicBrainz once more
                self.run_source(quick=True, note=tr("Bisher von {1}", entry.source))
                return
            self.run_source(quick=True, note=entry.detail)     # a saved album updates its row
            return

    def _notice_new_covers(self) -> None:
        """A cover or genres that came another way since the run (context menu, a file) count as well."""
        for e in self._last_batch:
            if e.cover and e.cover_seen is not None and e.cover_seen != _front_covers(e.tracks):
                e.detail = e.detail.replace(f" · {e.cover}", "")
                e.cover, e.cover_seen = "", None
            if e.genres and e.genres_seen is not None and e.genres_seen != _genres_of(e.tracks):
                e.detail = e.detail.replace(f" · {e.genres}", "")
                e.genres, e.genres_seen = "", None

    def _retry_genres(self, entry) -> None:
        """Last.fm once more for one finished album."""
        job = self.start_lastfm(entry.tracks)
        if job is None:
            return
        failed, entry.genres = entry.genres, self.finish_lastfm(job)
        entry.detail = entry.detail.replace(f" · {failed}", f" · {entry.genres}" if entry.genres else "")

    def _retry_cover(self, entry) -> None:
        """The cover sources once more for one finished album; here the user may be asked."""
        failed, entry.cover = entry.cover, self.fetch_cover_chain(entry.tracks, pick=True)
        entry.detail = entry.detail.replace(f" · {failed}", f" · {entry.cover}" if entry.cover else "")

    def customize_panel(self):
        from .dialogs.options import PanelDialog
        d = PanelDialog(config.load_panel(), self)
        if d.exec():
            config.save_panel(d.fields)
            self.settings.setValue(statusbox_setting(), d.status_box.isChecked())
            self._rebuild_panel()
            self.apply_status_box()

    def extended_tags(self):
        from .dialogs.extended import ExtendedTagsDialog
        tracks = self.view.selected_tracks()
        if not tracks:
            return
        d = ExtendedTagsDialog(tracks, self)
        if d.exec():
            self._write(tr("Alle Felder"), tracks, d.apply_to)
            self.panel.load(tracks)

    def apply_filter(self):
        sel = self.view.selected_tracks()
        self.model.set_filter(self.search.text())
        self.view.select_tracks([t for t in sel if t in self.model.rows])
        self._update_status()

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    # ------------------------------------------------------------------ files
    def remove_from_list(self):
        tracks = self.view.selected_tracks()
        if tracks:
            row = self.view.selected_rows()[0]
            self.model.remove_tracks(tracks)
            if self.model.rows:
                self.view.select_tracks([self.model.rows[min(row, len(self.model.rows) - 1)]])
            else:
                # The model reset clears the selection without a signal: the panel would keep
                # showing the removed files.
                self._panel_tracks = []
                self.panel.load([])
                self._update_actions()
            self._update_status()

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

    # ------------------------------------------------------------------ cover
    def _cover_command(self, cmd: str):
        cv = self.panel.cover
        if cmd in ("add", "replace"):
            # A cover image usually lies next to the files: start in the folder of the selection
            folders = {t.folder for t in self.panel.tracks}
            start = folders.pop() if len(folders) == 1 else self.current_dir
            p, _ = QFileDialog.getOpenFileName(self, tr("Cover hinzu&fügen...").replace("&", ""),
                                               start,
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
                r = QMessageBox.question(self, "PsyTags", tr("Sollen die vorhandenen Cover bleiben?"),
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
        elif cmd == "fetch_mb":
            self.fetch_cover_from_source(self.view.selected_tracks(), manual=True)
        elif cmd.startswith("provider:"):
            source = next((s for s in self._cover_sources() if getattr(s, "name", "") == cmd[9:]), None)
            if source is not None:
                reason = self.fetch_provider_cover(source, self.view.selected_tracks(), True, True)
                if reason:
                    self.message(reason, 8000)
        elif cmd == "preview":
            from .dialogs.cover import CoverPreview
            CoverPreview.show_for(self, cv)

    # ------------------------------------------------------------------ misc
    def _context_menu(self, pos):
        m = QMenu(self)
        for a in (self.act_play, self.act_save, self.act_remove, self.act_ext_tags, self.act_copy, self.act_paste):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_ttf)
        m.addAction(self.act_ttf_all)
        m.addAction(self.act_numbers)
        src = m.addMenu(tr("&Manuell suchen"))
        src.aboutToShow.connect(lambda: self._fill_sources_submenu(src))
        covers = m.addMenu(tr("Cover &holen"))
        covers.aboutToShow.connect(lambda: (covers.clear(), self._add_cover_entries(covers)))
        m.addAction(self.act_lastfm)
        m.addAction(self.act_moods)
        m.addAction(self.act_moods_all)
        m.addAction(self.act_auto_mb)
        m.addSeparator()
        m.addAction(self.act_remove_files)
        m.exec(pos)

    def _fill_sources_submenu(self, menu):
        menu.clear()
        self._add_source_entries(menu)

    def show_help(self):
        from . import help as uihelp
        uihelp.HelpDialog(self).exec()

    def show_options(self):
        self._open_options()

    def show_setup(self):
        from .dialogs.setup import SetupDialog
        d = SetupDialog(self.opts, self)
        d.exec()
        self.opts = d.opts
        self.opts.save()
        self.apply_appearance(self.opts.language, self.opts.theme)

    def _open_options(self, tab: str = ""):
        from .dialogs.options import OptionsDialog
        d = OptionsDialog(self.opts, self, tab)
        if d.exec():
            self.opts = d.opts
            self.opts.save()
            self.panel.blank_comments = self.opts.drop_comments
            self.apply_appearance(self.opts.language, self.opts.theme)

    def apply_appearance(self, language: str, theme_name: str) -> "MainWindow":
        """Language and theme take effect at once. Every text is set when a widget is built,
        so a successor window is built and takes over the loaded files, the selection,
        the search and the undo history. Returns the window now in charge."""
        from ..i18n import set_language
        from . import icons, theme
        if (language, theme_name) == self.built_with:
            return self
        if self.panel.dirty and self.panel.tracks and not self._save_or_drop(self.panel.tracks):
            return self                       # stored anyway, so it applies at the next start
        set_language(language)
        if theme_name != theme.CURRENT:
            theme.apply_theme(QApplication.instance(), theme_name)
            icons.refresh_colors()
        reload = None
        if self._loader_thread is not None:   # a folder is still being read: read it again there
            reload = (self._loader.paths, self._loader.add)
            self._loader.abort = True
            self._loader_thread.quit()
            self._loader_thread.wait()
            self._loader_thread = None
        self.save_state()
        new = MainWindow()
        new.undo = self.undo
        new.tag_clipboard = self.tag_clipboard
        new._auto_done, new._mood_done = self._auto_done, self._mood_done
        new._last_batch, new._provider_problems = self._last_batch, self._provider_problems
        new.status_box.take_over(self.status_box)
        if self.current_dir:
            new._set_current_dir(self.current_dir)
        new.dir_history = self.dir_history
        new.model.set_tracks(self.model.all)
        new.view.apply_widths()
        new.search.setText(self.search.text())
        new._ipc_server = getattr(self, "_ipc_server", None)
        selected = self.view.selected_tracks()
        row = self.view.currentIndex().row()
        focus = self.model.rows[row] if 0 <= row < len(self.model.rows) else None
        new.show()
        if selected:
            new.view.select_tracks(selected, focus)
        new._selection_changed()
        new._update_actions()
        if reload:
            new.load_paths(*reload)
        MainWindow.current = new
        self._autosave.stop()
        with contextlib.suppress(RuntimeError, TypeError):
            QApplication.instance().aboutToQuit.disconnect(self.save_state)
        self.hide()
        self.deleteLater()
        return new

    def about(self):
        from .dialogs.about import AboutDialog
        AboutDialog(self).exec()


def QStandardPathsMusic() -> str:
    from PySide6.QtCore import QStandardPaths
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)

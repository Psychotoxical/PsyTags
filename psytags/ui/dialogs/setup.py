"""The assistant of the first start. Every page can be skipped and changed later in the options."""
from __future__ import annotations

import copy
import os
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from ... import config, moodanalysis as ma
from ...config import Options
from ...i18n import tr
from ...track import Track
from ...websources import discogs, http, lastfm
from .. import theme
from ..controls import NumberFormatEditor, Segmented, add_row
from .rename import SchemeEditor
from .tagsources import run_async

_PROGRESS_STEPS = 1000


def is_first_start() -> bool:
    """Nothing has ever been stored: an installation in use is left alone."""
    return not config.settings().allKeys()


def _example_track() -> Track:
    """A made-up song for the preview of the naming scheme."""
    track = Track(os.path.join(os.path.expanduser("~"), "Musik", tr("Neuer Ordner"), "track01.mp3"))
    for name, value in (("ALBUMARTIST", tr("Beispiel-Band")), ("ARTIST", tr("Beispiel-Band")), ("ALBUM", tr("Beispiel-Album")),
                        ("TITLE", tr("Beispiel-Titel")), ("YEAR", "2024"), ("TRACK", "03/12"), ("DISCNUMBER", "01/01")):
        track.set(name, value)
    return track


class SetupDialog(QDialog):
    def __init__(self, opts: Options, parent=None):
        super().__init__(parent)
        self.opts = copy.deepcopy(opts)
        self.setWindowTitle(tr("Einrichtung"))
        self.resize(760, 620)
        self.setMinimumSize(660, 520)
        self.download_thread: threading.Thread | None = None
        self._download_state = {"done": 0, "total": 1, "error": ""}
        self._jobs: list = []
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self.poll_download)
        self._pages = (("welcome", tr("Willkommen bei PsyTags"), self._welcome, None),
                       ("appearance", tr("Sprache und Design"), self._appearance, self._save_appearance),
                       ("lastfm", tr("Genres von Last.fm"), self._lastfm, self._save_lastfm),
                       ("discogs", tr("Zweite Quelle: Discogs"), self._discogs, self._save_discogs),
                       ("moods", tr("Mood-Analyse"), self._moods, None),
                       ("rename", tr("Umbenennen"), self._rename, lambda: self.scheme.save()),
                       ("numbers", tr("Nummern"), self._numbers, lambda: self.numbers.format().save()))
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head = QWidget()
        head.setObjectName("OptionsHeader")
        row = QHBoxLayout(head)
        row.setContentsMargins(30, 18, 30, 14)
        self.title_label = QLabel()
        self.title_label.setObjectName("DialogTitle")
        row.addWidget(self.title_label)
        row.addStretch(1)
        self.step_label = QLabel()
        self.step_label.setObjectName("DialogSubtitle")
        row.addWidget(self.step_label)
        root.addWidget(head)
        self.stack = QStackedWidget()
        self.stack.setObjectName("OptionsPage")
        for _key, _title, build, _save in self._pages:
            page = QWidget()
            page.setObjectName("OptionsPage")
            area = QVBoxLayout(page)
            area.setContentsMargins(30, 24, 30, 24)
            area.setSpacing(14)
            build(area)
            area.addStretch(1)
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)
        root.addWidget(self._footer())
        self._show_page(0)

    def _footer(self) -> QWidget:
        foot = QWidget()
        foot.setObjectName("OptionsFooter")
        row = QHBoxLayout(foot)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(8)
        self.skip_button = QPushButton(tr("Überspringen"))
        self.skip_button.setAutoDefault(False)
        self.skip_button.clicked.connect(self.skip)
        row.addWidget(self.skip_button)
        row.addStretch(1)
        self.back_button = QPushButton(tr("< &Zurück").replace("&", ""))
        self.back_button.setAutoDefault(False)
        self.back_button.clicked.connect(self.previous_page)
        row.addWidget(self.back_button)
        self.next_button = QPushButton()
        self.next_button.setObjectName("DialogPrimary")
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self.next_page)
        row.addWidget(self.next_button)
        return foot

    # ------------------------------------------------------------------ navigation
    def page_keys(self) -> list[str]:
        return [p[0] for p in self._pages]

    def current_page(self) -> str:
        return self._pages[self.stack.currentIndex()][0]

    def go_to(self, key: str) -> None:
        self._show_page(self.page_keys().index(key))

    def _show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.title_label.setText(self._pages[index][1])
        self.step_label.setText(tr("Schritt {1} von {2}", index + 1, len(self._pages)))
        self.back_button.setEnabled(index > 0)
        self.skip_button.setVisible(index > 0)
        self.next_button.setText(tr("Fertig") if index == len(self._pages) - 1 else tr("&Weiter >").replace("&", ""))

    def _advance(self) -> None:
        index = self.stack.currentIndex()
        if index == len(self._pages) - 1:
            self.accept()
        else:
            self._show_page(index + 1)

    def next_page(self) -> None:
        save = self._pages[self.stack.currentIndex()][3]
        if save is not None:
            save()
        self._advance()

    def skip(self) -> None:
        self._advance()

    def previous_page(self) -> None:
        self._show_page(max(self.stack.currentIndex() - 1, 0))

    def done(self, result: int) -> None:
        config.settings().setValue("setup/done", True)    # also when closed early: it never comes back by itself
        self._poll.stop()
        super().done(result)

    @staticmethod
    def _text(area: QVBoxLayout, text: str, name: str = "") -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        if name:
            label.setObjectName(name)
        area.addWidget(label)
        return label

    # ------------------------------------------------------------------ pages
    def _welcome(self, area: QVBoxLayout) -> None:
        self._text(area, tr("In wenigen Schritten ist alles eingerichtet. Jeden Schritt können Sie überspringen "
                            "und später in den Optionen ändern."))
        self._text(area, tr("Bitte zuerst nur an Kopien testen"), "SectionTitle")
        self._text(area, tr("PsyTags schreibt direkt in Ihre Musikdateien und benennt sie um. Probieren Sie alles zuerst "
                            "an Kopien einiger Alben aus, bevor Sie Ihren Ablauf festlegen."), "SetupWarning")

    def _appearance(self, area: QVBoxLayout) -> None:
        self.lang = Segmented()
        self.lang.addItem("Deutsch", "de")
        self.lang.addItem("English", "en")
        self.lang.select(self.opts.language, "de")
        add_row(area, tr("Sprache"), self.lang)
        self.theme_choice = Segmented()
        self.theme_choice.addItem("Mocha, " + tr("dunkel"), "mocha")
        self.theme_choice.addItem("Latte, " + tr("hell"), "latte")
        self.theme_choice.select(self.opts.theme, "mocha")
        self.theme_choice.as_swatches([theme.MOCHA, theme.LATTE])
        area.addWidget(self.theme_choice, 0, Qt.AlignmentFlag.AlignLeft)
        self._text(area, tr("Sprache und Design gelten nach einem Neustart."), "DialogSubtitle")

    def _save_appearance(self) -> None:
        self.opts.language, self.opts.theme = self.lang.currentData(), self.theme_choice.currentData()

    def _lastfm(self, area: QVBoxLayout) -> None:
        self._text(area, tr("PsyTags holt die Genres von Last.fm. Dafür brauchen Sie einen eigenen, kostenlosen Schlüssel."))
        link = self._text(area, tr("API-Key (kostenlos unter <a href='https://www.last.fm/api/account/create'>"
                                   "last.fm/api/account/create</a>):"))
        link.setOpenExternalLinks(True)
        self.lastfm_key, self.lastfm_check, self.lastfm_result = self._secret_row(
            area, config.settings().value("lastfm/api_key", ""), self.check_lastfm_key)
        self._text(area, tr("Ohne Schlüssel bleibt der Schritt Genres aus. Sie können ihn später in den Optionen eintragen."),
                   "DialogSubtitle")

    def _secret_row(self, area: QVBoxLayout, stored: str, check) -> tuple[QLineEdit, QPushButton, QLabel]:
        """Hidden input, button that tests it, line for the outcome."""
        row = QHBoxLayout()
        row.setSpacing(8)
        field = QLineEdit(stored)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        row.addWidget(field, 1)
        button = QPushButton(tr("Testen"))
        button.setAutoDefault(False)
        button.clicked.connect(check)
        row.addWidget(button)
        area.addLayout(row)
        return field, button, self._text(area, "", "DialogSubtitle")

    def _run_check(self, verify, button: QPushButton, result: QLabel, good: str, bad: str) -> None:
        def check() -> str:
            try:
                verify()
            except (lastfm.LastfmError, http.FetchError):
                return bad
            return good

        button.setEnabled(False)
        result.setText(tr("Wird geprüft ..."))

        def finished(message) -> None:
            button.setEnabled(True)
            result.setText(message or "")
        self._jobs.append(run_async(check, finished))

    def check_lastfm_key(self) -> None:
        key = self.lastfm_key.text().strip()
        if not key:
            self.lastfm_result.setText(tr("Bitte zuerst einen Last.fm-API-Key eintragen."))
            return
        self._run_check(lambda: lastfm.verify_key(key), self.lastfm_check, self.lastfm_result,
                        tr("Der Schlüssel funktioniert."),
                        tr("Der Schlüssel wurde nicht angenommen, oder Last.fm ist gerade nicht erreichbar."))

    def _save_lastfm(self) -> None:
        s = config.settings()
        key = self.lastfm_key.text().strip()
        s.setValue("lastfm/api_key", key)
        s.setValue("lastfm/enabled", bool(key))

    def _discogs(self, area: QVBoxLayout) -> None:
        self._text(area, tr("Findet MusicBrainz ein Album nicht, kann PsyTags bei Discogs nachsehen. Von dort kommen nur "
                            "Texte, keine Cover. Dafür brauchen Sie einen eigenen, kostenlosen Token."))
        link = self._text(area, tr("Discogs-Token (kostenlos unter <a href='https://www.discogs.com/settings/developers'>"
                                   "discogs.com/settings/developers</a>):"))
        link.setOpenExternalLinks(True)
        self.discogs_token, self.discogs_check, self.discogs_result = self._secret_row(
            area, config.settings().value(discogs.SETTING, ""), self.check_discogs_token)
        self._text(area, tr("Ohne Token bleibt es bei MusicBrainz. Sie können ihn später in den Optionen eintragen."),
                   "DialogSubtitle")

    def check_discogs_token(self) -> None:
        token = self.discogs_token.text().strip()
        if not token:
            self.discogs_result.setText(tr("Bitte zuerst einen Discogs-Token eintragen."))
            return
        self._run_check(lambda: discogs.verify_token(token), self.discogs_check, self.discogs_result,
                        tr("Der Token funktioniert."),
                        tr("Der Token wurde nicht angenommen, oder Discogs ist gerade nicht erreichbar."))

    def _save_discogs(self) -> None:
        config.settings().setValue(discogs.SETTING, self.discogs_token.text().strip())

    def _moods(self, area: QVBoxLayout) -> None:
        self._text(area, tr("Die Moods entstehen direkt aus dem Audio. Dafür braucht PsyTags zwei Modelle (20 MB) und das Programm ffmpeg."))
        self.ffmpeg_status = self._text(area, tr("ffmpeg ist vorhanden.") if ma.ffmpeg_available()
                                        else tr("ffmpeg wurde nicht gefunden. Für die Mood-Analyse muss es im PATH liegen."))
        self.model_status = self._text(area, "")
        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, _PROGRESS_STEPS)
        self.model_progress.setTextVisible(False)
        self.model_progress.hide()
        area.addWidget(self.model_progress)
        self.model_button = QPushButton(tr("Modelle laden"))
        self.model_button.setAutoDefault(False)
        self.model_button.clicked.connect(self.load_models)
        area.addWidget(self.model_button, 0, Qt.AlignmentFlag.AlignLeft)
        self._show_model_state()

    @staticmethod
    def _model_folder() -> str:
        return os.path.join(config.data_dir(), "models")

    def _show_model_state(self) -> None:
        ready = ma.models_present(self._model_folder())
        self.model_status.setText(tr("Die Modelle sind vorhanden.") if ready else tr("Die Modelle sind noch nicht geladen."))
        self.model_button.setVisible(not ready)
        self.model_button.setEnabled(True)

    def load_models(self) -> None:
        state = self._download_state
        state.update(done=0, total=1, error="")
        folder = self._model_folder()

        def report(done: int, total: int) -> None:
            state.update(done=done, total=total)

        def work() -> None:
            try:
                ma.ensure_models(folder, on_progress=report)
            except (ma.MoodError, OSError) as e:
                state["error"] = str(e)

        self.model_button.setEnabled(False)
        self.model_status.setText(tr("Modelle werden geladen ..."))
        self.model_progress.setValue(0)
        self.model_progress.show()
        self.download_thread = threading.Thread(target=work, daemon=True)
        self.download_thread.start()
        self._poll.start()

    def poll_download(self) -> None:
        state = self._download_state
        self.model_progress.setValue(int(_PROGRESS_STEPS * state["done"] / max(state["total"], 1)))
        if self.download_thread is None or self.download_thread.is_alive():
            return
        self._poll.stop()
        self.download_thread = None
        if state["error"]:
            self.model_progress.hide()
            self.model_status.setText(state["error"])
            self.model_button.setEnabled(True)
            return
        self.model_progress.setValue(_PROGRESS_STEPS)
        self._show_model_state()

    def _rename(self, area: QVBoxLayout) -> None:
        self.scheme = SchemeEditor([_example_track()])
        area.addWidget(self.scheme)

    def _numbers(self, area: QVBoxLayout) -> None:
        self.numbers = NumberFormatEditor()
        area.addWidget(self.numbers)

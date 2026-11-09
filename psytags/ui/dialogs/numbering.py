"""Auto-numbering wizard (Convert > Auto-numbering wizard, Ctrl+K)."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QGroupBox, QLabel, QSpinBox, QVBoxLayout)

from ... import config, script
from ...i18n import tr
from ..persist import bind_widgets, remember


def _disc_numbers(tracks) -> set[str]:
    """Distinct disc numbers ("1/2" and "01" both count as 1)."""
    out = set()
    for t in tracks:
        v = (t.get("DISCNUMBER") or [""])[0].partition("/")[0].strip().lstrip("0")
        if v:
            out.add(v)
    return out


class NumberingWizard(QDialog):
    def __init__(self, tracks, parent=None, per_folder: bool = False):
        super().__init__(parent)
        self.tracks = tracks
        s = config.settings()
        self.setWindowTitle(tr("Tracknummern-Assistent"))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Track- und Discnummern schreiben")))

        g = QGroupBox(tr("Tracknummer"))
        gl = QGridLayout(g)
        self.track_start = QSpinBox()
        self.track_start.setRange(0, 9999)
        self.track_start.setValue(int(s.value("numbering/track_start", 1)))
        gl.addWidget(QLabel(tr("Beginnen bei Tracknummer:")), 0, 0)
        gl.addWidget(self.track_start, 0, 1)
        self.track_total = QCheckBox(tr("Gesamtzahl der Tracks speichern"))
        self.track_total.setChecked(s.value("numbering/track_total", "false") in (True, "true"))
        self.track_total_n = QSpinBox()
        self.track_total_n.setRange(0, 9999)
        self.track_total_n.setValue(len(tracks))
        gl.addWidget(self.track_total, 1, 0)
        gl.addWidget(self.track_total_n, 1, 1)
        self.track_zeros = QCheckBox(tr("Führende Nullen für Tracknummern (01, 02, ...)"))
        self.track_zeros.setChecked(s.value("numbering/track_zeros", "true") in (True, "true"))
        gl.addWidget(self.track_zeros, 2, 0, 1, 2)
        self.reset_folder = QCheckBox(tr("Zähler bei jedem Verzeichnis zurücksetzen"))
        self.reset_folder.setChecked(per_folder or s.value("numbering/reset_folder", "false") in (True, "true"))
        gl.addWidget(self.reset_folder, 3, 0, 1, 2)
        lay.addWidget(g)

        g = QGroupBox(tr("Discnummer"))
        gl = QGridLayout(g)
        self.disc_on = QCheckBox(tr("Discnummern schreiben"))
        self.disc_on.setChecked(s.value("numbering/disc_on", "false") in (True, "true"))
        gl.addWidget(self.disc_on, 0, 0, 1, 2)
        self.disc_start = QSpinBox()
        self.disc_start.setRange(0, 999)
        self.disc_start.setValue(int(s.value("numbering/disc_start", 1)))
        gl.addWidget(QLabel(tr("Beginnen bei Discnummer:")), 1, 0)
        gl.addWidget(self.disc_start, 1, 1)
        self.disc_total = QCheckBox(tr("Gesamtzahl der Discs speichern"))
        gl.addWidget(self.disc_total, 2, 0, 1, 2)
        self.disc_zeros = QCheckBox(tr("Führende Nullen für Discnummern"))
        gl.addWidget(self.disc_zeros, 3, 0, 1, 2)
        self.next_dir = QCheckBox(tr("Nächste Disc bei Verzeichniswechsel"))
        gl.addWidget(self.next_dir, 4, 0, 1, 2)
        self.next_field_on = QCheckBox(tr("Nächste Disc bei Änderung von"))
        self.next_field = QComboBox()
        self.next_field.setEditable(True)
        self.next_field.addItems(["DISCNUMBER", "ALBUM", "ARTIST", "ALBUMARTIST", "YEAR"])
        gl.addWidget(self.next_field_on, 5, 0)
        gl.addWidget(self.next_field, 5, 1)
        self.reset_track_on_disc = QCheckBox(tr("Trackzähler bei nächster Disc zurücksetzen"))
        self.reset_track_on_disc.setChecked(True)
        gl.addWidget(self.reset_track_on_disc, 6, 0, 1, 2)
        lay.addWidget(g)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        bind_widgets(self, "numbering", ["track_start", "track_total", "track_zeros", "reset_folder",
                                         "disc_on", "disc_start", "disc_total", "disc_zeros",
                                         "next_dir", "next_field_on", "next_field",
                                         "reset_track_on_disc"])
        if per_folder:      # Ctrl+Shift+K: only for this run, not stored
            self.reset_folder.blockSignals(True)
            self.reset_folder.setChecked(True)
            self.reset_folder.blockSignals(False)
        self.track_total_n.setValue(len(tracks))
        if len(_disc_numbers(tracks)) > 1:
            # The files already belong to several discs: keep that split for this run
            # (not stored), e.g. 1-9 on disc 1/2 and 1-7 on disc 2/2.
            for w in (self.disc_on, self.next_field_on, self.next_field):
                w.blockSignals(True)
            self.disc_on.setChecked(True)
            self.next_field_on.setChecked(True)
            self.next_field.setCurrentText("DISCNUMBER")
            for w in (self.disc_on, self.next_field_on, self.next_field):
                w.blockSignals(False)
        remember(self, "numbering")

    def _group_value(self, t) -> str:
        """Value of the "next disc on change of" field; disc numbers compare by number only."""
        name = self.next_field.currentText().strip().strip("%")
        v = script.format(f"%{name}%", t)
        return v.partition("/")[0].strip().lstrip("0") if name.upper() == "DISCNUMBER" else v

    def plan(self) -> dict[int, dict[str, str]]:
        """Track id -> {TRACK: .., DISCNUMBER: ..} following File List order."""
        out: dict[int, dict[str, str]] = {}
        start = self.track_start.value()
        n_track = start
        disc = self.disc_start.value()
        prev_dir = prev_val = None
        groups: list[list] = [[]]
        entries = []
        for t in self.tracks:
            new_disc = False
            if prev_dir is not None:
                if self.reset_folder.isChecked() and t.folder != prev_dir:
                    n_track = start
                if self.disc_on.isChecked():
                    if self.next_dir.isChecked() and t.folder != prev_dir:
                        new_disc = True
                    if self.next_field_on.isChecked():
                        v = self._group_value(t)
                        if v != prev_val:
                            new_disc = True
            if new_disc:
                disc += 1
                groups.append([])
                if self.reset_track_on_disc.isChecked():
                    n_track = start
            entries.append((t, n_track, disc))
            groups[-1].append(t)
            prev_dir = t.folder
            prev_val = self._group_value(t) \
                if self.next_field_on.isChecked() else None
            n_track += 1
        # Group sizes for totals when counters reset per disc/folder.
        sizes: dict[int, int] = {}
        if self.reset_folder.isChecked() or (self.disc_on.isChecked() and self.reset_track_on_disc.isChecked()):
            for t, nt, d in entries:
                key = (t.folder if self.reset_folder.isChecked() else "", d)
                sizes[id(t)] = sum(1 for x, _, dd in entries
                                   if (x.folder if self.reset_folder.isChecked() else "", dd) == key)
        last_disc = entries[-1][2] if entries else disc
        for t, nt, d in entries:
            total = sizes.get(id(t), self.track_total_n.value())
            width = len(str(total + start - 1)) if self.track_zeros.isChecked() else 0
            width = max(width, 2) if self.track_zeros.isChecked() else 0
            tr_ = str(nt).zfill(width)
            if self.track_total.isChecked():
                tr_ += "/" + str(total).zfill(width)
            vals = {"TRACK": tr_}
            if self.disc_on.isChecked():
                dw = max(2, len(str(last_disc))) if self.disc_zeros.isChecked() else 0
                ds = str(d).zfill(dw)
                if self.disc_total.isChecked():
                    ds += "/" + str(last_disc).zfill(dw)
                vals["DISCNUMBER"] = ds
            out[id(t)] = vals
        return out

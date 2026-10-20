"""Search & replace, scheduler and variable explorer."""

from __future__ import annotations

import os
import uuid

from PySide6.QtCore import QDateTime, QTime, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QDockWidget,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget)

from ..i18n import tr

# ============================================================ search/replace


class SearchDialog(QDialog):
    find_requested = Signal(str, bool, bool, bool)          # text, backwards, case, whole fields
    replace_requested = Signal(str, str, bool, bool)        # find, replace, case, all

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Search & replace"))
        f = QFormLayout(self)
        self.find = QLineEdit()
        self.repl = QLineEdit()
        self.case = QCheckBox(tr("Match case"))
        f.addRow(tr("Find:"), self.find)
        f.addRow(tr("Replace with:"), self.repl)
        f.addRow("", self.case)
        row = QHBoxLayout()
        for text, slot in ((tr("Find previous"), lambda: self._find(True)), (tr("Find next"), lambda: self._find(False)),
                           (tr("Replace"), lambda: self._replace(False)), (tr("Replace all"), lambda: self._replace(True))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        f.addRow(row)
        hint = QLabel(tr("Searches values, labels and comments. Replace changes text parameters, labels and comments."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:gray")
        f.addRow(hint)

    def _find(self, back: bool):
        if self.find.text():
            self.find_requested.emit(self.find.text(), back, self.case.isChecked(), False)

    def _replace(self, all_: bool):
        if self.find.text():
            self.replace_requested.emit(self.find.text(), self.repl.text(), self.case.isChecked(), all_)


# ================================================================= scheduler

MODES = [("once", "Once"), ("daily", "Daily"), ("weekly", "Weekly"), ("startup", "When Actions Recorder starts")]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def describe_entry(e: dict) -> str:
    m = e.get("mode", "once")
    if m == "once":
        return e.get("at", "")
    if m == "daily":
        return tr("Daily") + " " + e.get("time", "")
    if m == "weekly":
        days = ", ".join(tr(DAYS[d]) for d in e.get("days", []))
        return f"{days} {e.get('time', '')}"
    return tr("When Actions Recorder starts")


class EntryDialog(QDialog):
    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Scheduled macro"))
        self.entry = dict(entry)
        f = QFormLayout(self)
        self.file = QLineEdit(entry.get("file", ""))
        b = QPushButton(tr("Browse…"))
        b.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.file, 1)
        row.addWidget(b)
        f.addRow(tr("Macro file:"), row)
        self.mode = QComboBox()
        for v, label in MODES:
            self.mode.addItem(tr(label), v)
        self.mode.setCurrentIndex(max(0, self.mode.findData(entry.get("mode", "once"))))
        f.addRow(tr("Run:"), self.mode)
        self.at = QDateTimeEdit(QDateTime.fromString(entry.get("at", ""), "yyyy-MM-dd HH:mm")
                                if entry.get("at") else QDateTime.currentDateTime().addSecs(300))
        self.at.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.at.setCalendarPopup(True)
        self.time = QTimeEdit(QTime.fromString(entry.get("time", "09:00"), "HH:mm"))
        self.time.setDisplayFormat("HH:mm")
        self.days = []
        drow = QHBoxLayout()
        for i, d in enumerate(DAYS):
            cb = QCheckBox(tr(d))
            cb.setChecked(i in entry.get("days", [0, 1, 2, 3, 4]))
            self.days.append(cb)
            drow.addWidget(cb)
        self.days_w = QWidget()
        self.days_w.setLayout(drow)
        self.repeat = QLineEdit(str(entry.get("repeat", "")))
        self.repeat.setPlaceholderText(tr("empty = use playback settings"))
        self.enabled = QCheckBox(tr("Enabled"))
        self.enabled.setChecked(entry.get("enabled", True))
        f.addRow(tr("Date and time:"), self.at)
        f.addRow(tr("Time:"), self.time)
        f.addRow(tr("Days:"), self.days_w)
        f.addRow(tr("Repeat:"), self.repeat)
        f.addRow("", self.enabled)
        self.form = f
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.mode.currentIndexChanged.connect(self._vis)
        self._vis()

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("Macro file"), self.file.text(),
                                           "Macro (*.macro *.json);;All files (*)")
        if p:
            self.file.setText(p)

    def _vis(self):
        m = self.mode.currentData()
        self.form.setRowVisible(2, m == "once")
        self.form.setRowVisible(3, m in ("daily", "weekly"))
        self.form.setRowVisible(4, m == "weekly")

    def _ok(self):
        if not os.path.exists(self.file.text()):
            QMessageBox.warning(self, tr("Schedule"), tr("Choose an existing macro file."))
            return
        self.entry.update(file=self.file.text(), mode=self.mode.currentData(),
                          at=self.at.dateTime().toString("yyyy-MM-dd HH:mm"),
                          time=self.time.time().toString("HH:mm"),
                          days=[i for i, cb in enumerate(self.days) if cb.isChecked()],
                          repeat=self.repeat.text().strip(), enabled=self.enabled.isChecked())
        self.entry.setdefault("id", uuid.uuid4().hex)
        self.accept()


class ScheduleDialog(QDialog):
    def __init__(self, entries: list[dict], current_file: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Macro Scheduler"))
        self.resize(720, 360)
        self.entries = [dict(e) for e in entries]
        self.current_file = current_file
        lay = QVBoxLayout(self)
        info = QLabel(tr("Scheduled macros run while Actions Recorder is open (it can be minimized to the tray). "
                         "Enable “Start on login” in the settings to run them after a restart."))
        info.setWordWrap(True)
        lay.addWidget(info)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Macro"), tr("When"), tr("Enabled")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        for text, slot in ((tr("Add…"), self._add), (tr("Edit…"), self._edit), (tr("Remove"), self._remove)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)
        self._fill()

    def _fill(self):
        self.table.setRowCount(len(self.entries))
        for r, e in enumerate(self.entries):
            self.table.setItem(r, 0, QTableWidgetItem(e.get("file", "")))
            self.table.setItem(r, 1, QTableWidgetItem(describe_entry(e)))
            self.table.setItem(r, 2, QTableWidgetItem("✔" if e.get("enabled", True) else ""))

    def _add(self):
        d = EntryDialog({"file": self.current_file or "", "mode": "once"}, self)
        if d.exec():
            self.entries.append(d.entry)
            self._fill()

    def _edit(self, *_):
        r = self.table.currentRow()
        if r < 0:
            return
        d = EntryDialog(self.entries[r], self)
        if d.exec():
            self.entries[r] = d.entry
            self._fill()

    def _remove(self):
        r = self.table.currentRow()
        if r >= 0:
            del self.entries[r]
            self._fill()


def entry_due(e: dict, now: QDateTime, last_check: QDateTime) -> bool:
    """True if ``e`` should fire in the interval (last_check, now]."""
    if not e.get("enabled", True):
        return False
    m = e.get("mode", "once")
    if m == "once":
        at = QDateTime.fromString(e.get("at", ""), "yyyy-MM-dd HH:mm")
        return at.isValid() and last_check < at <= now
    if m in ("daily", "weekly"):
        t = QTime.fromString(e.get("time", ""), "HH:mm")
        if not t.isValid():
            return False
        cand = QDateTime(now.date(), t)
        if not (last_check < cand <= now):
            return False
        return m == "daily" or (now.date().dayOfWeek() - 1) in e.get("days", [])
    return False


# ========================================================= variable explorer


class VariableExplorer(QDockWidget):
    def __init__(self, parent=None):
        super().__init__(tr("Variable Explorer"), parent)
        self.setObjectName("varExplorer")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Variable"), tr("Value")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setWidget(self.table)

    def set_values(self, values: dict) -> None:
        items = sorted((k, v) for k, v in values.items() if not k.startswith("_"))
        self.table.setRowCount(len(items))
        for r, (k, v) in enumerate(items):
            self.table.setItem(r, 0, QTableWidgetItem(k))
            s = str(v)
            it = QTableWidgetItem(s if len(s) < 500 else s[:500] + "…")
            it.setToolTip(s[:4000])
            self.table.setItem(r, 1, it)

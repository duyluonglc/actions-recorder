"""Target window: the bar above the step list and the dialog to choose the window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout)

from .. import winmgr
from ..i18n import tr
from ..macro import Target


class TargetBar(QFrame):
    """Shows which window the macro works in."""

    edit_clicked = Signal()
    clear_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("targetBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        self.icon = QLabel("🎯")
        self.text = QLabel()
        self.text.setObjectName("targetText")
        self.text.setTextFormat(Qt.RichText)
        self.edit = QPushButton()
        self.edit.setObjectName("flatButton")
        self.clear = QPushButton("✕")
        self.clear.setObjectName("flatButton")
        self.clear.setToolTip(tr("Remove the target window"))
        self.edit.clicked.connect(self.edit_clicked)
        self.clear.clicked.connect(self.clear_clicked)
        lay.addWidget(self.icon)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.edit)
        lay.addWidget(self.clear)
        self.set_target(None)

    def set_target(self, t: Target | None) -> None:
        if t is None:
            self.text.setText(f"<span style='color:gray'>{tr('Works anywhere on the screen')}</span>")
            self.edit.setText(tr("Choose a target window…"))
            self.clear.hide()
            return
        flags = []
        if t.relative:
            flags.append(tr("positions relative to the window"))
        if t.activate:
            flags.append(tr("brought to the front automatically"))
        self.text.setText(f"<b>{t.describe()}</b>"
                          + (f" <span style='color:gray'>· {' · '.join(flags)}</span>" if flags else ""))
        self.edit.setText(tr("Change…"))
        self.clear.show()


class TargetDialog(QDialog):
    """Choose the window a macro works in."""

    def __init__(self, target: Target | None, has_positions: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Target window"))
        self.setMinimumWidth(620)
        self.old = target
        self.has_positions = has_positions
        lay = QVBoxLayout(self)
        intro = QLabel(tr("The macro will work in this window: it is brought to the front before steps that use the "
                          "mouse, keyboard or screen, and positions are measured from its top-left corner — so the "
                          "macro keeps working when the window is moved or on another monitor."))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel("<b>" + tr("Open windows") + "</b>"))
        row.addStretch(1)
        self.pick_btn = QPushButton(tr("Pick by switching to it (3 s)"))
        self.pick_btn.clicked.connect(lambda: self._countdown(3))
        refresh = QPushButton(tr("Refresh"))
        refresh.clicked.connect(self._fill)
        row.addWidget(self.pick_btn)
        row.addWidget(refresh)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.setMinimumHeight(170)
        self.list.currentItemChanged.connect(self._chosen)
        lay.addWidget(self.list)

        form = QFormLayout()
        self.app = QLineEdit(target.app if target else "")
        self.app.setPlaceholderText(tr("e.g. Google Chrome, notepad, Excel"))
        self.title = QLineEdit(target.title if target else "")
        self.title.setPlaceholderText(tr("optional — leave empty if the title changes (documents, web pages)"))
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 600)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(max(1, (target.timeout_ms if target else 10000) // 1000))
        self.activate = QCheckBox(tr("Bring the window to the front when it is not active"))
        self.activate.setChecked(target.activate if target else True)
        self.relative = QCheckBox(tr("Measure positions from the window's top-left corner"))
        self.relative.setChecked(target.relative if target else True)
        self.convert = QCheckBox()
        self.convert.setChecked(True)
        form.addRow(tr("Application contains:"), self.app)
        form.addRow(tr("Window title contains:"), self.title)
        form.addRow(tr("Wait for the window up to:"), self.timeout)
        form.addRow("", self.activate)
        form.addRow("", self.relative)
        form.addRow("", self.convert)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for w in (self.app, self.title):
            w.textChanged.connect(self._update_convert)
        self.relative.toggled.connect(self._update_convert)
        self.origin: tuple[int, int] | None = None
        self._offer_convert = False
        self._fill()
        self._update_convert()

    # ------------------------------------------------------------- window list
    def _fill(self):
        self.list.clear()
        for w in winmgr.other_windows():
            size = f"{w.rect[2]}×{w.rect[3]}" if w.rect else ""
            it = QListWidgetItem(f"{w.app}  —  {w.title or tr('(no title)')}    {size}")
            it.setData(Qt.UserRole, w)
            self.list.addItem(it)

    def _chosen(self, item, _prev=None):
        if item is None:
            return
        w = item.data(Qt.UserRole)
        self.app.setText(w.app)
        self.title.setText(w.title)

    def _countdown(self, n: int):
        if n == 0:
            w = winmgr.active_window()
            import os
            if w is not None and w.pid != os.getpid():
                self.app.setText(w.app)
                self.title.setText(w.title)
            self.pick_btn.setText(tr("Pick by switching to it (3 s)"))
            self.pick_btn.setEnabled(True)
            self.raise_()
            self.activateWindow()
            return
        self.pick_btn.setEnabled(False)
        self.pick_btn.setText(tr("Switch to the window…") + f" {n}")
        QTimer.singleShot(1000, lambda: self._countdown(n - 1))

    # ------------------------------------------------------------- conversion
    def _update_convert(self, *_):
        """Offer to convert existing screen positions when relative positions are switched on/off."""
        was_rel = bool(self.old and self.old.relative)
        now_rel = self.relative.isChecked() and bool(self.app.text().strip() or self.title.text().strip())
        w = winmgr.find_window(self.app.text().strip(), self.title.text().strip()) \
            if (self.app.text().strip() or self.title.text().strip()) else None
        if w is None and was_rel and self.old:
            w = winmgr.find_window(self.old.app, self.old.title)
        self.origin = w.origin if (w is not None and w.rect) else None
        show = self.has_positions and was_rel != now_rel and self.origin is not None
        self._offer_convert = show
        self.convert.setVisible(show)
        if show:
            x, y = self.origin
            self.convert.setText(
                (tr("Convert the existing positions to this window (it is now at {x}, {y})") if now_rel else
                 tr("Convert the existing positions back to screen coordinates")).format(x=x, y=y))

    def _ok(self):
        if not (self.app.text().strip() or self.title.text().strip()):
            self.app.setFocus()
            return
        self.accept()

    def result_target(self) -> Target:
        return Target(self.app.text().strip(), self.title.text().strip(), self.activate.isChecked(),
                      self.relative.isChecked(), self.timeout.value() * 1000)

    def conversion(self) -> tuple[int, int] | None:
        """(dx, dy) to add to every position, or None."""
        if not (self._offer_convert and self.convert.isChecked() and self.origin):
            return None
        now_rel = self.relative.isChecked()
        x, y = self.origin
        return (-x, -y) if now_rel else (x, y)

"""Workspace widgets: header (transport bar), step library, inspector, empty state,
run-options popup."""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..actions import CATALOG, CATEGORIES, Action
from ..i18n import tr
from ..system import AFTER_ACTIONS
from .action_dialog import ActionEditor
from .icons import glyph, icon

from .steps import NEW_MIME

# Library content: category -> [(kind, extra params, title override)]
LIBRARY = {
    "mouse": [("click", {}, None), ("click", {"count": 2}, "Double-click"), ("click", {"button": "right"}, "Right-click"),
              ("mouse_move", {}, None), ("mouse_down", {}, None), ("mouse_up", {}, None), ("scroll", {}, None),
              ("find_image", {"then": "click"}, "Find image & click"), ("find_text", {"then": "click"},
                                                                          "Click on text (OCR)"),
              ("ai_find", {}, None)],
    "keys": [("type_text", {}, None), ("key_press", {}, None), ("key_press", {"combo": "ctrl+c"}, "Hotkey simulation"),
             ("key_down", {}, None), ("key_up", {}, None)],
    "wait": [("wait", {}, None), ("wait", {"random": True}, "Random wait"), ("wait_until", {}, None),
             ("wait_image", {}, None), ("wait_text", {}, None), ("wait_pixel", {}, None), ("wait_change", {}, None),
             ("wait_file", {}, None), ("wait_window", {}, None)],
    "find": [("find_image", {}, None), ("find_text", {}, None), ("capture_text", {}, None),
             ("capture_image", {}, None), ("read_barcode", {}, None), ("get_pixel", {}, None)],
    "vars": [("set_var", {}, None), ("calc", {}, None), ("read_list", {}, None), ("save_var", {}, None),
             ("web_scrape", {}, None)],
    "control": [("launch", {}, None), ("goto", {}, None), ("goto", {"count": "3"}, "Loop"), ("if", {}, None), ("run_macro", {}, None),
                ("execute", {}, None), ("focus", {}, None), ("message", {}, None), ("notify", {}, None),
                ("beep", {}, None), ("clipboard", {}, None), ("stop", {}, None), ("group", {}, None)],
    "ai": [("ai_prompt", {}, None), ("ai_image", {}, None), ("ai_find", {}, None)],
}
CATEGORY_TITLES = {"mouse": "Mouse", "keys": "Keyboard", "wait": "Waiting", "find": "Screen & OCR",
                   "vars": "Data & variables", "control": "Flow & system", "ai": "AI"}


# ==================================================================== header


class Header(QFrame):
    """Top transport bar: record / run / stop / pause + quick run settings."""

    def __init__(self):
        super().__init__()
        self.setObjectName("header")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(icon("app").pixmap(26, 26))
        title = QLabel("Actions Recorder")
        title.setObjectName("brand")
        lay.addWidget(logo)
        lay.addWidget(title)
        lay.addSpacing(18)
        self.record = self._pill("●  " + tr("Record"), "pillRecord")
        self.run = self._pill("▶  " + tr("Run"), "pillRun")
        self.stop = self._pill("■", "pillStop")
        self.pause = self._pill("❚❚", "pillStop")
        self.stop.setToolTip(tr("Stop"))
        self.pause.setToolTip(tr("Pause / resume"))
        for b in (self.record, self.run, self.stop, self.pause):
            lay.addWidget(b)
        lay.addSpacing(18)
        self.speed = QSpinBox()
        self.speed.setRange(1, 10000)
        self.speed.setSuffix(" %")
        self.speed.setToolTip(tr("Replay speed"))
        self.loops = QSpinBox()
        self.loops.setRange(0, 1_000_000)
        self.loops.setSpecialValueText("∞")
        self.loops.setToolTip(tr("How many times to run (∞ = until stopped)"))
        lay.addWidget(self._caption(tr("Speed")))
        lay.addWidget(self.speed)
        lay.addWidget(self._caption(tr("Loops")))
        lay.addWidget(self.loops)
        self.options = QToolButton()
        self.options.setText(tr("Run options") + " ▾")
        self.options.setObjectName("flat")
        lay.addWidget(self.options)
        lay.addStretch(1)
        self.schedule = self._flat("📅", tr("Scheduler"))
        self.variables = self._flat("𝑥", tr("Variables"))
        self.variables.setCheckable(True)
        self.settings = self._flat("⚙", tr("Settings"))
        self.support = self._flat("❤", tr("Support the project"))
        self.support.setStyleSheet("color:#e5484d")
        for b in (self.schedule, self.variables, self.settings, self.support):
            lay.addWidget(b)

    @staticmethod
    def _caption(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("caption")
        return lbl

    @staticmethod
    def _pill(text: str, name: str) -> "Pill":
        return Pill(text, name)

    def set_hotkeys(self, mapping: dict[str, str]) -> None:
        """Show the global shortcuts on the transport buttons."""
        from ..keys import shortcut_label
        for btn, key, label in ((self.record, "record_append", tr("Record / stop recording")),
                                (self.run, "play", tr("Run / stop running")),
                                (self.stop, "stop", tr("Stop")),
                                (self.pause, "pause", tr("Pause / resume"))):
            hk = shortcut_label(mapping.get(key, ""))
            btn.set_hint(hk if btn.show_hint else "")
            btn.setToolTip(f"{label}  ({hk})" if hk else label)

    @staticmethod
    def _flat(sym: str, tip: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName("flat")
        b.setText(sym)
        b.setToolTip(tip)
        b.setMinimumSize(QSize(34, 30))
        return b


class Pill(QPushButton):
    """Rounded button with an optional, dimmer shortcut hint after its text."""

    def __init__(self, text: str, name: str):
        super().__init__()
        self.setObjectName(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(30)
        self.show_hint = True
        lay = QHBoxLayout(self)
        side = 10 if name == "pillStop" else 14
        lay.setContentsMargins(side, 0, side, 0)
        lay.setSpacing(8)
        self.main = QLabel(text)
        self.main.setObjectName("pillText")
        self.hint = QLabel()
        self.hint.setObjectName("pillHint")
        for lbl in (self.main, self.hint):
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(lbl)
        self.hint.hide()
        self._sync()

    def setText(self, text: str) -> None:       # noqa: N802 (Qt naming)
        self.main.setText(text)
        self._sync()

    def text(self) -> str:
        return self.main.text()

    def set_hint(self, hint: str) -> None:
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))
        self._sync()

    def _sync(self) -> None:
        self.setMinimumWidth(self.layout().sizeHint().width())

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.EnabledChange:
            for lbl in (self.main, self.hint):
                lbl.setEnabled(self.isEnabled())


class RunOptions(QFrame):
    """Popup with the less frequently used run settings."""

    def __init__(self, store, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("popup")
        self.store = store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        head = QLabel(tr("Replay these kinds of steps"))
        head.setObjectName("sectionTitle")
        lay.addWidget(head)
        self.filters = {}
        for key, text in (("bar/mouse_moves", "Mouse movements"), ("bar/mouse_clicks", "Clicks and wheel"),
                          ("bar/keys", "Keyboard input"), ("bar/waits", "Pauses (Wait steps)"),
                          ("bar/focus", "Window switching")):
            cb = QCheckBox(tr(text))
            cb.setChecked(store.get(key))
            cb.toggled.connect(lambda on, k=key: store.set(k, on))
            self.filters[key] = cb
            lay.addWidget(cb)
        form = QFormLayout()
        self.path = QComboBox()
        for v, label in (("recorded", "As recorded"), ("straight", "Straight line"), ("natural", "Natural"),
                         ("jump", "Jump")):
            self.path.addItem(tr(label), v)
        self.path.setCurrentIndex(max(0, self.path.findData(store.get("bar/mouse_path"))))
        self.path.currentIndexChanged.connect(lambda: store.set("bar/mouse_path", self.path.currentData()))
        self.until = QLineEdit(store.get("bar/repeat_until"))
        self.until.setPlaceholderText(tr("HH:MM (optional)"))
        self.until.textChanged.connect(lambda t: store.set("bar/repeat_until", t.strip()))
        self.after = QComboBox()
        for v, label in AFTER_ACTIONS:
            self.after.addItem(tr(label), v)
        self.after.setCurrentIndex(max(0, self.after.findData(store.get("bar/after"))))
        self.after.currentIndexChanged.connect(lambda: store.set("bar/after", self.after.currentData()))
        self.notify = QCheckBox(tr("Notify when a run starts and ends"))
        self.notify.setChecked(store.get("bar/notifications"))
        self.notify.toggled.connect(lambda on: store.set("bar/notifications", on))
        form.addRow(tr("Cursor movement:"), self.path)
        form.addRow(tr("Keep looping until:"), self.until)
        form.addRow(tr("When finished:"), self.after)
        lay.addLayout(form)
        lay.addWidget(self.notify)

    def popup_at(self, anchor: QWidget) -> None:
        self.adjustSize()
        self.move(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        self.show()


# =================================================================== library


class LibraryTree(QTreeWidget):
    def mimeData(self, items):
        md = QMimeData()
        it = items[0] if items else None
        payload = it.data(0, Qt.UserRole) if it else None
        if payload:
            md.setData(NEW_MIME, json.dumps(payload).encode())
        return md

    def mimeTypes(self):
        return [NEW_MIME]


class Library(QWidget):
    insert_requested = Signal(str, dict)

    def __init__(self):
        super().__init__()
        self.setObjectName("library")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 4, 8)
        title = QLabel(tr("Step library"))
        title.setObjectName("panelTitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search steps…"))
        self.search.setClearButtonEnabled(True)
        self.tree = LibraryTree()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setDragEnabled(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setFrameShape(QFrame.NoFrame)
        self.tree.setIconSize(QSize(18, 18))
        hint = QLabel(tr("Double-click or drag a step into the list."))
        hint.setObjectName("caption")
        hint.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(self.search)
        lay.addWidget(self.tree, 1)
        lay.addWidget(hint)
        for cat, _title, gl in CATEGORIES:
            top = QTreeWidgetItem([tr(CATEGORY_TITLES.get(cat, _title))])
            top.setIcon(0, icon("mouse") if cat == "mouse" else glyph(gl))
            top.setFlags(Qt.ItemIsEnabled)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            for kind, extra, label in LIBRARY[cat]:
                spec = CATALOG[kind]
                it = QTreeWidgetItem([tr(label or spec.name)])
                it.setIcon(0, glyph(spec.icon))
                it.setData(0, Qt.UserRole, {"kind": kind, "extra": extra})
                it.setToolTip(0, tr(label or spec.name))
                top.addChild(it)
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self.tree.itemActivated.connect(self._activate)
        self.search.textChanged.connect(self._filter)

    def _activate(self, item, _col=0):
        d = item.data(0, Qt.UserRole)
        if d:
            self.insert_requested.emit(d["kind"], d["extra"])

    def _filter(self, text: str):
        q = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(top.childCount()):
                ch = top.child(j)
                vis = not q or q in ch.text(0).lower() or q in top.text(0).lower()
                ch.setHidden(not vis)
                any_visible |= vis
            top.setHidden(not any_visible)


# ================================================================= inspector


class Inspector(QWidget):
    applied = Signal(int, object)        # row, Action

    def __init__(self, store, marker):
        super().__init__()
        self.setObjectName("inspector")
        self.store, self.marker = store, marker
        self.row = -1
        self.origin_fn = lambda: None      # set by the window: target-window origin for relative positions
        self.editor: ActionEditor | None = None
        self.original: dict | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 8, 8)
        self.title = QLabel(tr("Step properties"))
        self.title.setObjectName("panelTitle")
        self.kind_label = QLabel()
        self.kind_label.setObjectName("inspectorKind")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.placeholder = QLabel(tr("Select a step to see and change its settings."))
        self.placeholder.setObjectName("caption")
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.placeholder)
        btns = QHBoxLayout()
        self.apply_btn = QPushButton(tr("Apply"))
        self.apply_btn.setObjectName("pillRun")
        self.revert_btn = QPushButton(tr("Revert"))
        self.test_slot = QHBoxLayout()
        btns.addLayout(self.test_slot)
        btns.addStretch(1)
        btns.addWidget(self.revert_btn)
        btns.addWidget(self.apply_btn)
        lay.addWidget(self.title)
        lay.addWidget(self.kind_label)
        lay.addWidget(self.scroll, 1)
        lay.addLayout(btns)
        self.apply_btn.clicked.connect(self.apply)
        self.revert_btn.clicked.connect(self.revert)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.apply)
        self._action: Action | None = None
        self._labels: list[str] = []
        self._hide: list = []
        self.show_action(-1, None, [])

    def show_action(self, row: int, action: Action | None, labels: list[str], hide=None) -> None:
        self.row = row
        self._action, self._labels, self._hide = action, labels, hide or []
        while self.test_slot.count():
            w = self.test_slot.takeAt(0).widget()
            if w:
                w.setParent(None)
        if action is None:
            self.editor = None
            self.original = None
            self.kind_label.setText("")
            self.placeholder = QLabel(tr("Select a step to see and change its settings."))
            self.placeholder.setObjectName("caption")
            self.placeholder.setWordWrap(True)
            self.placeholder.setAlignment(Qt.AlignCenter)
            self.scroll.setWidget(self.placeholder)
            self.apply_btn.setEnabled(False)
            self.revert_btn.setEnabled(False)
            return
        self.kind_label.setText(f"{action.spec.icon}  {action.name}   ·   #{row + 1}")
        self.editor = ActionEditor(action, labels, self.store, self.marker, self._hide, compact=True,
                                   origin=self.origin_fn)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 6, 0)
        hl.addWidget(self.editor)
        hl.addStretch(1)
        self.scroll.setWidget(holder)
        if self.editor.test_btn:
            self.test_slot.addWidget(self.editor.test_btn)
        self.original = action.to_dict()
        self.apply_btn.setEnabled(True)
        self.revert_btn.setEnabled(True)

    def dirty(self) -> bool:
        return self.editor is not None and self.editor.result_action().to_dict() != self.original

    def apply(self) -> bool:
        if self.editor is None or self.row < 0:
            return True
        if not self.dirty():
            return True
        if not self.editor.validate():
            return False
        a = self.editor.result_action()
        self.original = a.to_dict()
        self.applied.emit(self.row, a)
        return True

    def revert(self):
        if self._action is not None:
            self.show_action(self.row, self._action, self._labels, self._hide)


# =============================================================== empty state


class EmptyState(QWidget):
    record_clicked = Signal()
    open_clicked = Signal()
    add_clicked = Signal()
    recent_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("empty")
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(14)
        title = QLabel(tr("Automate anything you do with the mouse and keyboard"))
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        sub = QLabel(tr("Capture your actions once, fine-tune the steps, then let them run for you."))
        sub.setObjectName("caption")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        col.addWidget(title)
        col.addWidget(sub)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        for sym, text, desc, sig in (("●", tr("Capture actions"), tr("Record mouse and keyboard"), self.record_clicked),
                                     ("📂", tr("Open a file"), tr("Continue an existing macro"), self.open_clicked),
                                     ("＋", tr("Build step by step"), tr("Pick steps from the library"),
                                      self.add_clicked)):
            b = QPushButton(f"{sym}\n{text}\n{desc}")
            b.setObjectName("card")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumSize(240, 110)
            b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            b.clicked.connect(sig)
            cards.addWidget(b)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addLayout(cards)
        row.addStretch(1)
        col.addLayout(row)
        self.recent_title = QLabel(tr("Recently used"))
        self.recent_title.setObjectName("sectionTitle")
        self.recent = QListWidget()
        self.recent.setObjectName("recent")
        self.recent.setMaximumWidth(620)
        self.recent.setMaximumHeight(150)
        self.recent.setFrameShape(QFrame.NoFrame)
        self.recent.itemActivated.connect(lambda it: self.recent_clicked.emit(it.data(Qt.UserRole)))
        self.recent.itemClicked.connect(lambda it: self.recent_clicked.emit(it.data(Qt.UserRole)))
        rc = QVBoxLayout()
        rc.addWidget(self.recent_title)
        rc.addWidget(self.recent)
        rrow = QHBoxLayout()
        rrow.addStretch(1)
        rrow.addLayout(rc)
        rrow.addStretch(1)
        col.addSpacing(10)
        col.addLayout(rrow)
        outer.addLayout(col)
        outer.addStretch(2)

    def set_recent(self, paths: list[str]) -> None:
        paths = [p for p in paths if os.path.exists(p)][:6]
        self.recent.clear()
        for p in paths:
            it = QListWidgetItem(f"🗎  {os.path.basename(p)}    —    {os.path.dirname(p)}")
            it.setData(Qt.UserRole, p)
            it.setToolTip(p)
            self.recent.addItem(it)
        self.recent_title.setVisible(bool(paths))
        self.recent.setVisible(bool(paths))


__all__ = ["Header", "RunOptions", "Library", "Inspector", "EmptyState", "NEW_MIME", "Action"]

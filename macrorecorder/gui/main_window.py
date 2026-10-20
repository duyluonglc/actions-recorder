"""Main window: header transport bar, step library, step list and inspector."""

from __future__ import annotations

import json
import os
import sys
import threading

from PySide6.QtCore import (QDateTime, QItemSelection, QItemSelectionModel, QObject, QPoint, Qt, QTimer, QTranslator,
                            QUrl, Signal)
from PySide6.QtGui import QAction, QColor, QDesktopServices, QGuiApplication, QKeySequence, QPalette
from PySide6.QtWidgets import (QApplication, QFileDialog, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
                               QProgressDialog, QSplitter, QStackedWidget, QStyleFactory, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, FILE_EXT, __version__, system
from ..actions import CATALOG, CATEGORIES, Action
from ..engine import Engine, EngineUI
from ..i18n import set_language, tr
from ..macro import Macro, hidden_rows, optimize, scale_waits
from ..recorder import InputHub
from ..system import AFTER_ACTIONS
from .action_dialog import ActionDialog
from .icons import glyph, icon
from .. import links
from .onboarding import SetupDialog, SupportDialog, about_html, install_guide_url, missing_required_mac_permissions
from .overlays import Marker, StatusBar
from .panels import ScheduleDialog, SearchDialog, VariableExplorer, entry_due
from .settings_dialog import SettingsDialog
from .steps import StepList, StepModel
from .store import Store
from .workspace import CATEGORY_TITLES, LIBRARY, EmptyState, Header, Inspector, Library, RunOptions

FILE_FILTER = f"Macro (*{FILE_EXT} *.json);;All files (*)"
MAX_UNDO = 200
MIME_ACTIONS = "application/x-actionsrecorder-steps"
ACCENT = "#6d5ae6"
RECORD_RED = "#e5484d"


class GuiUI(QObject, EngineUI):
    """Bridges engine-thread callbacks to the Qt main thread."""
    sig_progress = Signal(int, int)
    sig_vars = Signal(dict)
    sig_notify = Signal(str, int)
    sig_finished = Signal(bool, object)
    sig_request = Signal(dict)

    def progress(self, index, cycle): self.sig_progress.emit(index, cycle)
    def variables(self, values): self.sig_vars.emit(values)
    def notify(self, text, index): self.sig_notify.emit(text, index)
    def finished(self, completed, error): self.sig_finished.emit(completed, error)

    def _ask(self, req: dict):
        req["event"] = threading.Event()
        self.sig_request.emit(req)
        req["event"].wait()
        return req.get("answer")

    def message_box(self, title, text, buttons):
        return self._ask({"type": "message", "title": title, "text": text, "buttons": buttons})

    def ask_input(self, prompt):
        return self._ask({"type": "input", "text": prompt})


class Bridge(QObject):
    hotkey = Signal(str)
    count = Signal(int)


def apply_theme(app: QApplication, theme: str) -> None:
    dark = theme == "dark"
    if theme == "system":
        try:
            dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except AttributeError:
            dark = False
    if dark and sys.platform != "darwin":
        app.setStyle(QStyleFactory.create("Fusion"))
        p = QPalette()
        base, text = QColor(30, 31, 36), QColor(232, 232, 236)
        p.setColor(QPalette.Window, QColor(38, 39, 45))
        p.setColor(QPalette.WindowText, text)
        p.setColor(QPalette.Base, base)
        p.setColor(QPalette.AlternateBase, QColor(44, 45, 52))
        p.setColor(QPalette.Text, text)
        p.setColor(QPalette.Button, QColor(48, 49, 56))
        p.setColor(QPalette.ButtonText, text)
        p.setColor(QPalette.Highlight, QColor(ACCENT))
        p.setColor(QPalette.HighlightedText, Qt.white)
        p.setColor(QPalette.ToolTipBase, base)
        p.setColor(QPalette.ToolTipText, text)
        p.setColor(QPalette.PlaceholderText, QColor(140, 140, 150))
        app.setPalette(p)
    elif sys.platform == "darwin":
        try:
            app.styleHints().setColorScheme({"dark": Qt.ColorScheme.Dark, "light": Qt.ColorScheme.Light}
                                            .get(theme, Qt.ColorScheme.Unknown))
        except AttributeError:
            pass
    app.setStyleSheet(f"""
        #header {{ border-bottom: 1px solid rgba(127,127,127,70); }}
        #brand {{ font-size: 15px; font-weight: 700; }}
        #caption {{ color: rgba(127,127,127,235); }}
        #panelTitle {{ font-weight: 700; font-size: 13px; padding: 2px 2px 4px 2px; }}
        #sectionTitle {{ font-weight: 600; }}
        #inspectorKind {{ color: {ACCENT}; font-weight: 600; padding-bottom: 4px; }}
        QPushButton#pillRecord, QPushButton#pillRun, QPushButton#pillStop {{
            border-radius: 15px; padding: 4px 16px; font-weight: 600; border: 1px solid transparent;
        }}
        QPushButton#pillRecord {{ background: {RECORD_RED}; color: white; }}
        QPushButton#pillRecord:hover {{ background: #f05a5f; }}
        QPushButton#pillRun {{ background: {ACCENT}; color: white; }}
        QPushButton#pillRun:hover {{ background: #7d6cf0; }}
        QPushButton#pillStop {{ background: rgba(127,127,127,45); color: palette(window-text); padding: 4px 12px; }}
        QPushButton#pillStop:hover {{ background: rgba(127,127,127,80); }}
        QPushButton#pillRecord:disabled, QPushButton#pillRun:disabled, QPushButton#pillStop:disabled {{
            background: rgba(127,127,127,30); color: rgba(127,127,127,160);
        }}
        QPushButton#pillRecord QLabel, QPushButton#pillRun QLabel {{ color: white; background: transparent; }}
        QPushButton#pillStop QLabel {{ color: palette(window-text); background: transparent; }}
        QLabel#pillText {{ font-weight: 600; }}
        QLabel#pillHint {{ font-size: 11px; font-weight: 500; padding: 1px 6px; border-radius: 7px;
                           background: rgba(255,255,255,40); }}
        QPushButton#pillRecord QLabel#pillHint, QPushButton#pillRun QLabel#pillHint {{ color: rgba(255,255,255,215); }}
        QPushButton QLabel:disabled {{ color: rgba(127,127,127,170); }}
        QPushButton QLabel#pillHint:disabled {{ background: rgba(127,127,127,25); }}
        QToolButton#flat {{ border: none; border-radius: 6px; padding: 4px 8px; font-size: 15px; }}
        QToolButton#flat:hover, QToolButton#flat:checked {{ background: rgba(127,127,127,50); }}
        QToolButton#flat::menu-indicator {{ image: none; }}
        #library QTreeWidget, #stepList, #recent {{ background: transparent; }}
        #library QTreeWidget::item {{ padding: 3px 2px; border-radius: 5px; }}
        #library QTreeWidget::item:hover {{ background: rgba(127,127,127,40); }}
        #stepList {{ border: none; }}
        #stepList::item:selected, #stepList::item:hover {{ background: transparent; }}
        #center {{ border-left: 1px solid rgba(127,127,127,60); border-right: 1px solid rgba(127,127,127,60); }}
        #emptyTitle {{ font-size: 20px; font-weight: 700; }}
        QPushButton#card {{
            border: 1px solid rgba(127,127,127,80); border-radius: 12px; padding: 14px; text-align: center;
            background: rgba(127,127,127,18); font-size: 13px;
        }}
        QPushButton#card:hover {{ border-color: {ACCENT}; background: rgba(109,90,230,30); }}
        #recent::item {{ padding: 5px; border-radius: 5px; }}
        #recent::item:hover {{ background: rgba(127,127,127,40); }}
        #popup {{ border: 1px solid rgba(127,127,127,90); border-radius: 8px; background: palette(window); }}
    """)


class MainWindow(QMainWindow):
    def __init__(self, store: Store, open_path: str | None = None, minimized: bool = False):
        super().__init__()
        self.store = store
        self.macro = Macro()
        self.path: str | None = None
        self.dirty = False
        self.undo_stack: list[list[Action]] = []
        self.redo_stack: list[list[Action]] = []
        self.record_at: int | None = None
        self.rec_paused = False
        self.last_notify_index = -1
        self.pending_after = "none"
        self.play_source: str | None = None       # file of a scheduled run
        self._quitting = False

        self.bridge = Bridge()
        self.bridge.hotkey.connect(self.on_hotkey)
        self.bridge.count.connect(lambda n: self.hub.recording and self.status_text(
            ("❚❚ " + tr("Recording paused") if self.rec_paused else "● " + tr("Recording")) + f" — {n} " + tr("events")))
        self.hub = InputHub(on_hotkey=self.bridge.hotkey.emit, on_count=self.bridge.count.emit)
        self.ui = GuiUI()
        self.ui.sig_progress.connect(self.on_progress)
        self.ui.sig_vars.connect(lambda v: self.vars_dock.set_values(v))
        self.ui.sig_notify.connect(self.on_notify)
        self.ui.sig_finished.connect(self.on_finished)
        self.ui.sig_request.connect(self.on_request)
        self.engine = Engine(self.ui)
        self.marker = Marker()
        self.status = StatusBar()
        self.status.stop_clicked.connect(lambda: self.stop(via_ui=True))
        self.status.pause_clicked.connect(self.toggle_pause)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon("app"))
        self.resize(1280, 760)
        self.setAcceptDrops(True)
        self._actions()
        self._menus()
        self._central()
        self._tray()
        self.vars_dock = VariableExplorer(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.vars_dock)
        self.vars_dock.hide()
        self.vars_dock.visibilityChanged.connect(self._vars_visible)
        self.search = SearchDialog(self)
        self.search.find_requested.connect(self.find_next)
        self.search.replace_requested.connect(self.replace)

        geo = store.raw("ui/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.apply_settings()
        self.hub.start()
        self.sched_last = QDateTime.currentDateTime()
        self.sched_timer = QTimer(self)
        self.sched_timer.timeout.connect(self.check_schedule)
        self.sched_timer.start(1000)
        self.refresh()
        if open_path:
            self.open_file(open_path)
        if minimized or store.get("ui/start_min"):
            if self.tray and self.tray.isVisible():
                QTimer.singleShot(0, self.hide)
            else:
                QTimer.singleShot(0, self.showMinimized)
        QTimer.singleShot(400, self.check_permissions)
        QTimer.singleShot(1500, self._run_startup_entries)

    # ================================================================ build
    def _act(self, text, slot, shortcut=None, ic=None, tip=None, checkable=False) -> QAction:
        a = QAction(tr(text).replace("&", "&&"), self)
        if ic is not None:
            a.setIcon(ic)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tr(tip))
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        self.addAction(a)
        return a

    def _actions(self):
        A = self._act
        self.a_new = A("New macro", self.new_macro, QKeySequence.New)
        self.a_open = A("Open…", self.open_dialog, QKeySequence.Open)
        self.a_save = A("Save", self.save, QKeySequence.Save)
        self.a_save_as = A("Save as…", self.save_as, QKeySequence.SaveAs)
        self.a_csv = A("Export step list (CSV)…", self.export_csv)
        self.a_shortcut = A("Create launcher file…", self.create_shortcut, None, None,
                            "Create a double-clickable file that runs this macro")
        self.a_settings = A("Preferences…", lambda: self.open_settings(), QKeySequence.Preferences)
        self.a_settings.setMenuRole(QAction.PreferencesRole)
        self.a_exit = A("Quit", self.quit_app, QKeySequence.Quit)
        self.a_exit.setMenuRole(QAction.QuitRole)

        self.a_play = A("Run", lambda: self.play(), "Ctrl+R")
        self.a_play_cursor = A("Run from selected step", lambda: self.play("cursor"), "Ctrl+Shift+R")
        self.a_play_sel = A("Run selected steps only", lambda: self.play("selection"))
        self.a_record = A("Record into this macro", lambda: self.record(new=False))
        self.a_record_new = A("Record a new macro", lambda: self.record(new=True))
        self.a_stop = A("Stop", lambda: self.stop(via_ui=True), "Ctrl+.")
        self.a_pause = A("Pause / resume", self.toggle_pause)

        self.a_edit = A("Edit step", self.edit_selected, "Ctrl+E")
        self.a_delete = A("Delete", self.delete_selected, QKeySequence.Delete)
        self.a_search = A("Find & replace…", self.show_search, QKeySequence.Find)
        self.a_find_next = A("Find next", lambda: self.search._find(False), QKeySequence.FindNext)
        self.a_undo = A("Undo", self.undo, QKeySequence.Undo)
        self.a_redo = A("Redo", self.redo, QKeySequence.Redo)
        self.a_cut = A("Cut", self.cut, QKeySequence.Cut)
        self.a_copy = A("Copy", self.copy, QKeySequence.Copy)
        self.a_paste = A("Paste", self.paste, QKeySequence.Paste)
        self.a_dup = A("Duplicate", self.duplicate, "Ctrl+D")
        self.a_toggle = A("Turn step on / off", self.toggle_enabled, "Ctrl+Shift+D")
        self.a_group = A("Put in a group…", self.group_selected, "Ctrl+G")
        self.a_ungroup = A("Remove group", self.ungroup_selected, "Ctrl+Shift+G")
        self.a_collapse = A("Fold / unfold all groups", self.toggle_all_groups)
        self.a_up = A("Move up", lambda: self.move_selected(-1), "Ctrl+Up")
        self.a_down = A("Move down", lambda: self.move_selected(1), "Ctrl+Down")
        self.a_optimize = A("Clean up steps…", self.optimize, None, None,
                            "Merge waits, drop redundant mouse moves, limit long waits")
        self.a_scale = A("Scale wait times…", self.scale)
        self.a_select_all = A("Select all", lambda: self.view.selectAll(), QKeySequence.SelectAll)

        self.a_schedule = A("Scheduler…", self.open_scheduler)
        self.a_vars = A("Variables", lambda on: self.vars_dock.setVisible(on), None, None, checkable=True)
        self.a_library = A("Step library", lambda on: self.library.setVisible(on), None, None, checkable=True)
        self.a_inspector = A("Step properties", lambda on: self.inspector.setVisible(on), None, None,
                             checkable=True)
        self.a_perm = A("Permissions…", lambda: self.check_permissions(force=True))
        self.a_tips = A("Troubleshooting…", self.show_tips)
        self.a_help = A("User guide", self.open_help, QKeySequence.HelpContents)
        self.a_about = A("About Actions Recorder", self.about)
        self.a_support = A("Support the project ❤…", lambda: SupportDialog(self).exec())
        self.a_website = A("Project page on GitHub", lambda: QDesktopServices.openUrl(QUrl(links.REPO_URL)))
        self.a_updates = A("Download the latest version", lambda: QDesktopServices.openUrl(QUrl(links.RELEASES_URL)))
        self.a_install = A("Installation & permissions guide",
                           lambda: QDesktopServices.openUrl(QUrl(install_guide_url())))
        self.a_about.setMenuRole(QAction.AboutRole)

    def _insert_menu(self, parent: QMenu | None = None) -> QMenu:
        m = QMenu(tr("Add step"), parent or self)
        for cat, title, gl in CATEGORIES:
            sub = m.addMenu(icon("mouse") if cat == "mouse" else glyph(gl), tr(CATEGORY_TITLES.get(cat, title)))
            for kind, extra, label in LIBRARY[cat]:
                spec = CATALOG[kind]
                act = sub.addAction(glyph(spec.icon), tr(label or spec.name).replace("&", "&&"))
                act.triggered.connect(lambda _=False, k=kind, e=extra: self.insert_new(k, e))
        return m

    def _menus(self):
        mb = self.menuBar()
        m = mb.addMenu(tr("File"))
        m.addActions([self.a_new, self.a_open])
        self.recent_menu = m.addMenu(tr("Open recent"))
        m.addSeparator()
        m.addActions([self.a_save, self.a_save_as])
        m.addSeparator()
        m.addActions([self.a_csv, self.a_shortcut])
        m.addSeparator()
        m.addActions([self.a_settings, self.a_exit])
        m = mb.addMenu(tr("Edit"))
        m.addActions([self.a_undo, self.a_redo])
        m.addSeparator()
        m.addActions([self.a_cut, self.a_copy, self.a_paste, self.a_dup, self.a_delete, self.a_select_all])
        m.addSeparator()
        m.addMenu(self._insert_menu(m))
        m.addActions([self.a_edit, self.a_up, self.a_down, self.a_toggle])
        m.addSeparator()
        m.addActions([self.a_group, self.a_ungroup, self.a_collapse])
        m.addSeparator()
        m.addActions([self.a_search, self.a_find_next, self.a_optimize, self.a_scale])
        m = mb.addMenu(tr("Run"))
        m.addActions([self.a_play, self.a_play_cursor, self.a_play_sel, self.a_pause, self.a_stop])
        m.addSeparator()
        m.addActions([self.a_record_new, self.a_record])
        m.addSeparator()
        m.addAction(self.a_schedule)
        m = mb.addMenu(tr("View"))
        m.addActions([self.a_library, self.a_inspector, self.a_vars])
        m = mb.addMenu(tr("Help"))
        m.addActions([self.a_help, self.a_install, self.a_tips, self.a_perm])
        m.addSeparator()
        m.addActions([self.a_website, self.a_updates, self.a_support])
        m.addSeparator()
        m.addAction(self.a_about)

    def _central(self):
        # header / transport bar
        h = Header()
        self.header = h
        h.record.clicked.connect(self._record_clicked)
        h.run.clicked.connect(self._run_clicked)
        h.stop.clicked.connect(lambda: self.stop(via_ui=True))
        h.pause.clicked.connect(self.toggle_pause)
        rec_menu = QMenu(self)
        rec_menu.addActions([self.a_record_new, self.a_record])
        self.header_rec_menu = rec_menu
        h.speed.setValue(self.store.get("bar/speed"))
        h.speed.valueChanged.connect(lambda v: self.store.set("bar/speed", v))
        h.loops.setValue(self.store.get("bar/repeat"))
        h.loops.valueChanged.connect(lambda v: self.store.set("bar/repeat", v))
        self.run_options = RunOptions(self.store, self)
        h.options.clicked.connect(lambda: self.run_options.popup_at(h.options))
        h.schedule.clicked.connect(self.open_scheduler)
        h.variables.toggled.connect(lambda on: self.vars_dock.setVisible(on))
        h.settings.clicked.connect(lambda: self.open_settings())
        h.support.clicked.connect(lambda: SupportDialog(self).exec())
        # filters live in the run-options popup; kept under the old name for other code
        self.filters = self.run_options.filters
        self.filters["bar/notifications"] = self.run_options.notify

        # three panes
        self.library = Library()
        self.library.insert_requested.connect(self.insert_new)
        self.model = StepModel()
        self.model.rows_dropped.connect(self.drop_rows)
        # the whole list was replaced (undo, open, new...): the inspector must not keep a stale step
        self.model.modelReset.connect(lambda: self.inspector.show_action(-1, None, []))
        self.model.new_dropped.connect(lambda k, e, row: self.insert_new(k, e, row))
        self.view = StepList(self.model)
        self.view.edit_requested.connect(self.edit_selected)
        self.view.delete_requested.connect(self.delete_selected)
        for a in (self.a_delete, self.a_cut, self.a_copy, self.a_paste, self.a_dup, self.a_toggle, self.a_group,
                  self.a_ungroup, self.a_up, self.a_down, self.a_select_all):
            self.removeAction(a)
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.view.addAction(a)
        self.view.doubleClicked.connect(self.on_double_click)
        self.view.clicked.connect(self.on_click)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.selectionModel().selectionChanged.connect(self.on_selection)
        self.empty = EmptyState()
        self.empty.record_clicked.connect(lambda: self.record(new=True))
        self.empty.open_clicked.connect(self.open_dialog)
        self.empty.add_clicked.connect(self._focus_library)
        self.empty.recent_clicked.connect(self.open_file)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.view)
        center = QWidget()
        center.setObjectName("center")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(6, 6, 6, 0)
        cl.addWidget(self.stack)
        self.inspector = Inspector(self.store, self.marker)
        self.inspector.applied.connect(self.apply_inspector)
        split = QSplitter()
        split.setChildrenCollapsible(False)
        split.addWidget(self.library)
        split.addWidget(center)
        split.addWidget(self.inspector)
        split.setStretchFactor(1, 1)
        split.setSizes([250, 650, 380])
        self.library.setMinimumWidth(200)
        self.inspector.setMinimumWidth(300)
        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(h)
        rl.addWidget(split, 1)
        self.setCentralWidget(root)
        self.a_library.setChecked(True)
        self.a_inspector.setChecked(True)
        self.count_label = QLabel()
        self.time_label = QLabel()
        self.statusBar().addWidget(self.count_label, 1)
        self.statusBar().addPermanentWidget(self.time_label)

    def _record_clicked(self):
        if self.hub.recording:
            self.stop(via_ui=True)
        elif self.macro.actions:
            self.header_rec_menu.exec(self.header.record.mapToGlobal(QPoint(0, self.header.record.height())))
        else:
            self.record(new=True)

    def _run_clicked(self):
        if self.engine.playing:
            self.engine.stop()
        else:
            self.play()

    def _focus_library(self):
        self.library.setVisible(True)
        self.library.search.setFocus()

    def _vars_visible(self, v: bool):
        self.a_vars.setChecked(v)
        self.header.variables.setChecked(v)

    def apply_inspector(self, row: int, action: Action):
        if 0 <= row < len(self.macro.actions):
            new = list(self.macro.actions)
            new[row] = action
            self.set_actions(new, [row])


    def _tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(icon("app"), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction(tr("Show window"), self.show_window)
        m.addSeparator()
        for a in (self.a_play, self.a_record, self.a_pause, self.a_stop):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_exit)
        self.tray.setContextMenu(m)
        self.tray_menu = m
        self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.messageClicked.connect(self.on_message_clicked)

    # ============================================================ settings
    def apply_settings(self):
        bad = self.hub.set_hotkeys(self.store.hotkeys())
        if bad:
            self.statusBar().showMessage(tr("Invalid hotkeys ignored:") + " " + ", ".join(bad), 6000)
        names = {"record_append": self.a_record, "stop": self.a_stop, "play": self.a_play,
                 "play_cursor": self.a_play_cursor, "play_selection": self.a_play_sel,
                 "record_new": self.a_record_new, "pause": self.a_pause}
        from ..keys import shortcut_label
        for n, a in names.items():
            hk = self.store.get(f"hotkey/{n}")
            base = a.text().split("\t")[0]
            a.setToolTip(f"{base}  ({shortcut_label(hk)})" if hk else base)
        self.header.set_hotkeys(self.store.hotkeys())
        if self.tray:
            self.tray.setVisible(self.store.get("ui/tray"))
        on_top = self.store.get("ui/on_top")
        if bool(self.windowFlags() & Qt.WindowStaysOnTopHint) != on_top:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, on_top)
            self.show()
        from .. import ocr
        ocr.set_language(self.store.get("ocr/language"))
        try:
            system.set_start_on_login(self.store.get("ui/start_login"))
        except Exception as e:
            self.statusBar().showMessage(f"Start on login: {e}", 6000)
        self._update_recent()

    def open_settings(self, page: int = 0):
        old_lang, old_theme = self.store.get("ui/language"), self.store.get("ui/theme")
        r = SettingsDialog(self.store, self, page).exec()
        if r:
            self.apply_settings()
            for key, cb in self.filters.items():
                cb.setChecked(self.store.get(key))
            if self.store.get("ui/theme") != old_theme:
                apply_theme(QApplication.instance(), self.store.get("ui/theme"))
            if self.store.get("ui/language") != old_lang or self.store.get("ui/theme") != old_theme:
                QMessageBox.information(self, APP_NAME, tr("Restart Actions Recorder to apply all changes."))

    # ================================================================ state
    @property
    def busy(self) -> bool:
        return self.hub.recording or self.engine.playing

    def refresh(self):
        name = os.path.basename(self.path) if self.path else tr("Untitled")
        self.setWindowTitle(f"{name}{' *' if self.dirty else ''} — {APP_NAME} {__version__}")
        n = len(self.macro.actions)
        self.count_label.setText(f"{n} " + tr("steps"))
        s = self.macro.duration_ms() // 1000
        self.time_label.setText(f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}")
        self.stack.setCurrentIndex(1 if (n or self.path or self.busy) else 0)
        if self.stack.currentIndex() == 0:
            self.empty.set_recent(self.store.recent())
        self.refresh_actions()

    def refresh_actions(self):
        rec, play = self.hub.recording, self.engine.playing
        busy = rec or play
        has = bool(self.macro.actions)
        sel = bool(self.selected_rows())
        for a in (self.a_play, self.a_play_cursor, self.a_play_sel):
            a.setEnabled(not busy and has)
        self.a_play_sel.setEnabled(not busy and sel)
        self.a_play_cursor.setEnabled(not busy and sel)
        self.a_record.setEnabled(not busy)
        self.a_record_new.setEnabled(not busy)
        self.a_stop.setEnabled(busy)
        self.a_pause.setEnabled(busy)
        for a in (self.a_new, self.a_open, self.a_paste):
            a.setEnabled(not busy)
        for a in (self.a_optimize, self.a_scale, self.a_collapse):
            a.setEnabled(not busy and has)
        for a in (self.a_edit, self.a_delete, self.a_cut, self.a_dup, self.a_toggle, self.a_group,
                  self.a_ungroup, self.a_up, self.a_down):
            a.setEnabled(not busy and sel)
        self.a_undo.setEnabled(not busy and bool(self.undo_stack))
        self.a_redo.setEnabled(not busy and bool(self.redo_stack))
        self.view.setEnabled(not rec)
        h = self.header
        h.record.setText("■  " + tr("Stop recording") if rec else "●  " + tr("Record"))
        h.record.setEnabled(not play)
        h.run.setText("■  " + tr("Stop") if play else "▶  " + tr("Run"))
        h.run.setEnabled(not rec and (has or play))
        h.stop.setEnabled(busy)
        h.pause.setEnabled(busy)
        self.inspector.setEnabled(not busy)

    def mark_dirty(self):
        self.dirty = True
        self.refresh()

    def apply_hidden(self):
        hid = hidden_rows(self.macro.actions)
        for r in range(len(self.macro.actions)):
            self.view.setRowHidden(r, r in hid)

    # ================================================================= undo
    def push_undo(self):
        self.undo_stack.append([a.copy() for a in self.macro.actions])
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def set_actions(self, actions: list[Action], select: list[int] | None = None, undoable: bool = True):
        if undoable:
            self.push_undo()
            self.dirty = True
        self.macro.actions = actions
        self.model.set_actions(self.macro.actions)
        self.apply_hidden()
        self.refresh()
        if select:
            self.select_rows(select)

    def undo(self):
        if self.undo_stack and not self.busy:
            self.redo_stack.append(self.macro.actions)
            self.macro.actions = self.undo_stack.pop()
            self.model.set_actions(self.macro.actions)
            self.apply_hidden()
            self.mark_dirty()

    def redo(self):
        if self.redo_stack and not self.busy:
            self.undo_stack.append(self.macro.actions)
            self.macro.actions = self.redo_stack.pop()
            self.model.set_actions(self.macro.actions)
            self.apply_hidden()
            self.mark_dirty()

    # ============================================================ selection
    def selected_rows(self) -> list[int]:
        sm = self.view.selectionModel()
        return sorted({i.row() for i in sm.selectedRows()}) if sm else []

    def select_rows(self, rows: list[int]):
        sm = self.view.selectionModel()
        sel = QItemSelection()
        for r in rows:
            if 0 <= r < len(self.macro.actions):
                sel.select(self.model.index(r), self.model.index(r))
        sm.select(sel, QItemSelectionModel.ClearAndSelect)
        if rows and 0 <= rows[0] < len(self.macro.actions):
            sm.setCurrentIndex(self.model.index(rows[0], 0), QItemSelectionModel.NoUpdate)
            self.view.scrollTo(self.model.index(rows[0], 0))

    def insert_pos(self) -> int:
        rows = self.selected_rows()
        return rows[-1] + 1 if rows else len(self.macro.actions)

    def on_selection(self, *_):
        self.refresh_actions()
        rows = self.selected_rows()
        new_row = rows[0] if len(rows) == 1 else -1
        insp = self.inspector
        if insp.row >= 0 and insp.row != new_row and insp.dirty() and insp.row < len(self.macro.actions):
            # keep unapplied edits when the user moves on to another step
            pending, r = insp.editor.result_action(), insp.row
            insp.show_action(-1, None, [])
            new = list(self.macro.actions)
            new[r] = pending
            self.set_actions(new, rows)
            return
        if new_row != insp.row or new_row < 0:
            insp.show_action(new_row, self.macro.actions[new_row] if new_row >= 0 else None, self.labels(),
                             [self])
        if len(rows) == 1 and self.store.get("ui/overlays") and not self.busy:
            a = self.macro.actions[rows[0]]
            if a.params.get("x") is not None and a.params.get("y") is not None:
                try:
                    self.marker.show_point(int(a.params["x"]), int(a.params["y"]), 1200)
                except (TypeError, ValueError):
                    pass
            elif a.kind == "mouse_path" and a.params.get("points"):
                q = a.params["points"][-1]
                self.marker.show_point(int(q[0]), int(q[1]), 1200)
            elif a.params.get("region"):
                self.marker.show_rect(*[int(v) for v in a.params["region"]], ms=1200)
            else:
                self.marker.hide()
        else:
            self.marker.hide()

    # ============================================================== editing
    def labels(self) -> list[str]:
        return self.macro.labels()

    def insert_new(self, kind: str, extra: dict | None = None, at: int | None = None):
        """Add a step with default settings; it is selected so it can be set up in the inspector."""
        if self.busy:
            return
        a = Action.new(kind, **(extra or {}))
        at = self.insert_pos() if at is None else at
        self.insert_actions([a, Action.new("group_end")] if kind == "group" else [a], at)
        self.select_rows([at])
        if a.spec.fields:
            self.edit_selected()

    def insert_actions(self, acts: list[Action], at: int | None = None):
        at = self.insert_pos() if at is None else at
        new = list(self.macro.actions)
        new[at:at] = acts
        self.set_actions(new, list(range(at, at + len(acts))))

    def on_click(self, idx):
        pass

    def on_double_click(self, idx):
        a = self.macro.actions[idx.row()]
        if a.kind == "group":
            self.push_undo()
            a.params["collapsed"] = not a.params.get("collapsed")
            self.model.refresh_rows([idx.row()])
            self.apply_hidden()
            self.mark_dirty()
        else:
            self.edit_selected()

    def edit_selected(self):
        """Open the selected step for editing: in the inspector, or a dialog if that panel is hidden."""
        rows = self.selected_rows()
        if not rows or self.busy:
            return
        r = rows[0]
        if self.inspector.isVisible() and self.inspector.editor is not None and self.inspector.row == r:
            ed = self.inspector.editor
            first = next((w for w in ed.widgets.values() if w.isVisible()), None)
            target = ed.label_edit
            for child in (first.findChildren(QWidget) if first else []):
                if child.focusPolicy() & Qt.TabFocus:
                    target = child
                    break
            target.setFocus()
            return
        dlg = ActionDialog(self.macro.actions[r], self.labels(), self.store, self.marker, self, hide=[self])
        if dlg.exec():
            new = list(self.macro.actions)
            new[r] = dlg.result_action()
            self.set_actions(new, [r])

    def delete_selected(self):
        rows = set(self.selected_rows())
        if not rows or self.busy:
            return
        if self.store.get("ui/confirm_delete") and QMessageBox.question(
                self, tr("Delete"), tr("Delete the selected actions?") + f" ({len(rows)})") != QMessageBox.Yes:
            return
        first = min(rows)
        new = [a for i, a in enumerate(self.macro.actions) if i not in rows]
        self.set_actions(new, [min(first, len(new) - 1)] if new else None)

    def copy(self):
        rows = self.selected_rows()
        if not rows:
            return
        from PySide6.QtCore import QMimeData
        data = json.dumps([self.macro.actions[r].to_dict() for r in rows], ensure_ascii=False)
        md = QMimeData()
        md.setData(MIME_ACTIONS, data.encode())
        md.setText("\n".join(f"{self.macro.actions[r].name}\t{self.macro.actions[r].describe()}" for r in rows))
        QApplication.clipboard().setMimeData(md)

    def cut(self):
        self.copy()
        self.delete_selected()

    def paste(self):
        md = QApplication.clipboard().mimeData()
        acts = []
        if md is not None and md.hasFormat(MIME_ACTIONS):
            acts = [Action.from_dict(d) for d in json.loads(bytes(md.data(MIME_ACTIONS)).decode())
                    if d.get("kind") in CATALOG]
        elif md is not None and md.hasText() and md.text():
            # pasting plain text inserts a Text action
            acts = [Action.new("type_text", text=md.text())]
        if acts and not self.busy:
            self.insert_actions(acts)

    def duplicate(self):
        rows = self.selected_rows()
        if rows:
            self.insert_actions([self.macro.actions[r].copy() for r in rows], rows[-1] + 1)

    def toggle_enabled(self):
        rows = self.selected_rows()
        if not rows:
            return
        new = [a.copy() for a in self.macro.actions]
        state = not all(new[r].enabled for r in rows)
        for r in rows:
            new[r].enabled = state
        self.set_actions(new, rows)

    def group_selected(self):
        rows = self.selected_rows()
        if not rows:
            return
        name, ok = QInputDialog.getText(self, tr("Group"), tr("Group name:"), text=tr("Group"))
        if not ok:
            return
        a, b = rows[0], rows[-1] + 1
        new = list(self.macro.actions)
        new[b:b] = [Action.new("group_end")]
        new[a:a] = [Action.new("group", name=name)]
        self.set_actions(new, [a])

    def ungroup_selected(self):
        rows = self.selected_rows()
        from ..macro import group_ranges
        ranges = group_ranges(self.macro.actions)
        drop = set()
        for s, e in ranges.items():
            if any(s <= r <= e for r in rows):
                drop.add(s)
                if self.macro.actions[e].kind == "group_end":
                    drop.add(e)
        if drop:
            self.set_actions([a for i, a in enumerate(self.macro.actions) if i not in drop])

    def toggle_all_groups(self):
        groups = [a for a in self.macro.actions if a.kind == "group"]
        if not groups:
            return
        state = not all(a.params.get("collapsed") for a in groups)
        new = [a.copy() for a in self.macro.actions]
        for a in new:
            if a.kind == "group":
                a.params["collapsed"] = state
        self.set_actions(new)

    def move_selected(self, d: int):
        rows = self.selected_rows()
        if not rows:
            return
        new = list(self.macro.actions)
        if (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == len(new) - 1):
            return
        for r in (rows if d < 0 else reversed(rows)):
            new[r], new[r + d] = new[r + d], new[r]
        self.set_actions(new, [r + d for r in rows])

    def drop_rows(self, rows: list[int], target: int):
        if self.busy or not rows:
            return
        moving = [self.macro.actions[r] for r in rows]
        rest = [a for i, a in enumerate(self.macro.actions) if i not in set(rows)]
        target -= sum(1 for r in rows if r < target)
        target = max(0, min(target, len(rest)))
        rest[target:target] = moving
        self.set_actions(rest, list(range(target, target + len(moving))))

    def optimize(self):
        v, ok = QInputDialog.getInt(self, tr("Optimize"),
                                    tr("Merges consecutive waits and mouse moves.\nLimit waits to (ms, 0 = no limit):"),
                                    0, 0, 3_600_000)
        if ok:
            rows = self.selected_rows()
            acts = self.macro.actions
            if len(rows) > 1:
                a, b = rows[0], rows[-1] + 1
                new = acts[:a] + optimize(acts[a:b], max_wait_ms=v) + acts[b:]
            else:
                new = optimize(acts, max_wait_ms=v)
            before = len(acts)
            self.set_actions(new)
            self.statusBar().showMessage(tr("Optimized:") + f" {before} → {len(new)}", 5000)

    def scale(self):
        v, ok = QInputDialog.getDouble(self, tr("Scale wait times"), tr("Multiply wait times by:"), 0.5, 0.01, 100, 2)
        if ok:
            rows = self.selected_rows()
            acts = self.macro.actions
            if len(rows) > 1:
                a, b = rows[0], rows[-1] + 1
                new = acts[:a] + scale_waits(acts[a:b], v) + acts[b:]
            else:
                new = scale_waits(acts, v)
            self.set_actions(new)

    def context_menu(self, pos):
        m = QMenu(self)
        m.addActions([self.a_edit, self.a_delete])
        m.addSeparator()
        m.addMenu(self._insert_menu(m))
        m.addSeparator()
        m.addActions([self.a_cut, self.a_copy, self.a_paste, self.a_dup])
        m.addSeparator()
        m.addActions([self.a_toggle, self.a_group, self.a_ungroup, self.a_collapse])
        m.addSeparator()
        m.addActions([self.a_play_cursor, self.a_play_sel, self.a_record])
        m.exec(self.view.viewport().mapToGlobal(pos))

    # =========================================================== search
    def show_search(self):
        self.search.show()
        self.search.raise_()
        self.search.find.setFocus()

    def _matches(self, a: Action, text: str, case: bool) -> bool:
        hay = " ".join([a.name, a.describe(), a.label, a.comment])
        return (text in hay) if case else (text.lower() in hay.lower())

    def find_next(self, text: str, back: bool, case: bool, _whole: bool):
        n = len(self.macro.actions)
        if not n:
            return
        rows = self.selected_rows()
        start = rows[0] if rows else (-1 if not back else n)
        rng = range(start - 1, start - 1 - n, -1) if back else range(start + 1, start + 1 + n)
        for i in rng:
            r = i % n
            if self._matches(self.macro.actions[r], text, case):
                if r in hidden_rows(self.macro.actions):
                    self.toggle_all_groups()
                self.select_rows([r])
                return
        self.statusBar().showMessage(tr("Not found:") + f" {text}", 4000)

    def replace(self, find: str, repl: str, case: bool, all_: bool):
        import re
        flags = 0 if case else re.I
        pat = re.compile(re.escape(find), flags)
        rows = range(len(self.macro.actions)) if all_ else self.selected_rows()
        new = [a.copy() for a in self.macro.actions]
        count = 0
        for r in rows:
            a = new[r]
            for k, v in list(a.params.items()):
                if isinstance(v, str) and pat.search(v):
                    a.params[k], n = pat.subn(repl, v)
                    count += n
            for attr in ("label", "comment"):
                v = getattr(a, attr)
                if pat.search(v):
                    nv, n = pat.subn(repl, v)
                    setattr(a, attr, nv)
                    count += n
        if count:
            self.set_actions(new, list(rows)[:1] if not all_ else None)
        self.statusBar().showMessage(tr("Replaced:") + f" {count}", 4000)
        if not all_:
            self.find_next(find, False, case, False)

    # ============================================================ recording
    def record(self, new: bool = False, from_hotkey: bool = False):
        if self.busy:
            return
        if new and self.macro.actions and self.dirty and not from_hotkey:
            r = QMessageBox.question(self, tr("Start new recording"), tr("Save changes to the current macro first?"),
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel or (r == QMessageBox.Save and not self.save()):
                return
        self.record_at = None if new else self.insert_pos()
        self.rec_paused = False
        if self.store.get("ui/hide_record"):
            self._hide_for_run()
        self.refresh_actions()
        QTimer.singleShot(0 if from_hotkey else 300, self._begin_record)

    def _begin_record(self):
        self.hub.start_recording(self.store.record_settings())
        self.status_text("● " + tr("Recording") + " — 0 " + tr("events"))
        self.refresh_actions()
        self.statusBar().showMessage(tr("Recording…"))

    def _finish_record(self, via_ui: bool):
        acts = self.hub.stop_recording(strip_last_click=via_ui)
        if self.record_at is None:
            self.push_undo()
            self.macro = Macro(acts)
            self.path = None
            self.macro.actions = acts
            self.model.set_actions(self.macro.actions)
            sel = [0] if acts else []
        else:
            new = list(self.macro.actions)
            new[self.record_at:self.record_at] = acts
            self.push_undo()
            self.macro.actions = new
            self.model.set_actions(new)
            sel = list(range(self.record_at, self.record_at + len(acts)))
        self.dirty = True
        self.apply_hidden()
        self._end_run()
        self.statusBar().showMessage(tr("Recorded actions:") + f" {len(acts)}", 5000)
        if sel:
            self.select_rows(sel)

    # ============================================================= playback
    def play(self, mode: str = "all", from_hotkey: bool = False, macro: Macro | None = None,
             settings=None, base_dir: str | None = None):
        if self.busy:
            return
        macro = macro or self.macro
        if not macro.actions:
            return
        start, end = 0, None
        rows = self.selected_rows()
        if mode == "cursor" and rows:
            start = rows[0]
        elif mode == "selection" and rows:
            start, end = rows[0], rows[-1] + 1
        s = settings or self.store.play_settings()
        self.pending_after = self.store.get("bar/after") if mode == "all" and (s.repeat or s.repeat_until) else "none"
        if self.store.get("ui/hide_play"):
            self._hide_for_run()
        self.hub.hotkeys_enabled = True
        self.refresh_actions()
        bd = base_dir if base_dir is not None else (os.path.dirname(self.path) if self.path else os.getcwd())

        def go():
            self.status_text("▶ " + tr("Playing…"))
            self.engine.play(macro, s, start, end, base_dir=bd)
            self.refresh_actions()
            self.statusBar().showMessage(tr("Playing…"))
            if self.filters["bar/notifications"].isChecked() and self.tray and self.tray.isVisible() \
                    and self.store.get("ui/notifications"):
                self.tray.showMessage(APP_NAME, tr("Playback started"), QSystemTrayIcon.Information, 1500)
        QTimer.singleShot(0 if from_hotkey else 350, go)

    def on_progress(self, i: int, cycle: int):
        if self.play_source:
            self.status_text(f"▶ {os.path.basename(self.play_source)} #{i + 1}")
            return
        self.model.set_current(i)
        if self.isVisible() and not self.isMinimized():
            self.view.scrollTo(self.model.index(i, 0))
        n = self.store.get("bar/repeat")
        loop = f" · {tr('cycle')} {cycle}" + (f"/{n}" if n else "")
        paused = f" ({tr('paused')})" if self.engine.paused else ""
        self.status_text(f"▶ {i + 1}/{len(self.macro.actions)}{loop}{paused}")

    def on_finished(self, completed: bool, error):
        self.model.set_current(-1)
        self.play_source = None
        self._end_run()
        if error:
            self.statusBar().showMessage(tr("Playback error:") + f" {error}", 10000)
            if self.store.get("ui/tips"):
                self.show_tips(error)
            else:
                QMessageBox.warning(self, tr("Playback error"), str(error))
            return
        self.statusBar().showMessage(tr("Playback finished") if completed else tr("Playback stopped"), 5000)
        if self.filters["bar/notifications"].isChecked() and self.tray and self.tray.isVisible() \
                and self.store.get("ui/notifications"):
            self.tray.showMessage(APP_NAME, tr("Playback finished") if completed else tr("Playback stopped"),
                                  QSystemTrayIcon.Information, 2500)
        if completed and self.pending_after != "none":
            self.after_playback(self.pending_after)

    def after_playback(self, action: str):
        label = tr(dict(AFTER_ACTIONS).get(action, action))
        dlg = QProgressDialog(tr("After playback:") + f" {label}\n" + tr("Cancel to keep working."),
                              tr("Cancel"), 0, 10, self)
        dlg.setWindowTitle(APP_NAME)
        dlg.setAutoClose(False)
        dlg.setValue(0)
        dlg.show()
        timer = QTimer(dlg)

        def tick():
            if dlg.wasCanceled():
                timer.stop()
                dlg.close()
                return
            dlg.setValue(dlg.value() + 1)
            if dlg.value() >= 10:
                timer.stop()
                dlg.close()
                if action == "close":
                    self.dirty = False
                    self.quit_app()
                else:
                    system.after_playback(action)
        timer.timeout.connect(tick)
        timer.start(1000)

    def on_notify(self, text: str, index: int):
        self.last_notify_index = index
        if self.tray and self.tray.isVisible() and self.store.get("ui/notifications"):
            self.tray.showMessage(APP_NAME, text, QSystemTrayIcon.Information, 4000)
        else:
            self.statusBar().showMessage(text, 6000)

    def on_message_clicked(self):
        if self.last_notify_index >= 0:
            self.show_window()
            self.select_rows([self.last_notify_index])

    def on_request(self, req: dict):
        try:
            if req["type"] == "message":
                box = QMessageBox()
                box.setWindowTitle(req["title"] or APP_NAME)
                box.setText(req["text"])
                box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                btns = {"ok": [("ok", QMessageBox.Ok)], "okcancel": [("ok", QMessageBox.Ok), ("cancel", QMessageBox.Cancel)],
                        "yesno": [("yes", QMessageBox.Yes), ("no", QMessageBox.No)],
                        "yesnocancel": [("yes", QMessageBox.Yes), ("no", QMessageBox.No),
                                        ("cancel", QMessageBox.Cancel)]}[req["buttons"]]
                buttons = {box.addButton(b): n for n, b in btns}
                copy_btn = box.addButton(tr("Copy text"), QMessageBox.HelpRole)
                while True:
                    box.exec()
                    if box.clickedButton() is copy_btn:
                        QApplication.clipboard().setText(req["text"])
                        continue
                    break
                req["answer"] = buttons.get(box.clickedButton(), "cancel")
            elif req["type"] == "input":
                text, ok = QInputDialog.getText(None, APP_NAME, req["text"])
                req["answer"] = text if ok else None
        finally:
            req["event"].set()

    # ======================================================= common control
    def stop(self, via_ui: bool = False):
        if self.hub.recording:
            self._finish_record(via_ui)
        elif self.engine.playing:
            self.engine.stop()

    def toggle_pause(self):
        if self.engine.playing:
            if self.engine.paused:
                self.engine.resume()
                self.status_text("▶ " + tr("Playing…"))
            else:
                self.engine.pause()
                self.status_text("❚❚ " + tr("Paused"))
        elif self.hub.recording:
            self.rec_paused = not self.rec_paused
            self.hub.set_paused(self.rec_paused)
            self.status_text(("❚❚ " + tr("Recording paused")) if self.rec_paused else ("● " + tr("Recording")))

    def on_hotkey(self, name: str):
        if name == "record_append":
            if self.hub.recording:
                self.stop()
            elif not self.engine.playing:
                self.record(new=False, from_hotkey=True)
        elif name == "record_new":
            if not self.busy:
                self.record(new=True, from_hotkey=True)
        elif name == "stop":
            self.stop()
        elif name == "play":
            if self.engine.playing:
                self.engine.stop()
            elif not self.hub.recording:
                self.play(from_hotkey=True)
        elif name == "play_cursor":
            if not self.busy:
                self.play("cursor", from_hotkey=True)
        elif name == "play_selection":
            if not self.busy:
                self.play("selection", from_hotkey=True)
        elif name == "pause":
            self.toggle_pause()
        elif name == "capture_pos":
            if not self.busy:
                from pynput.mouse import Controller
                x, y = Controller().position
                self.insert_actions([Action.new("click", x=int(x), y=int(y))])
                self.statusBar().showMessage(tr("Captured mouse position") + f" ({int(x)}, {int(y)})", 4000)
        elif name == "sample":
            from pynput.mouse import Controller

            from .. import screen
            x, y = Controller().position
            try:
                c = screen.pixel_color(int(x), int(y))
            except Exception:
                c = "?"
            text = f"{int(x)}, {int(y)}  {c}"
            QApplication.clipboard().setText(text)
            self.on_notify(tr("Copied to clipboard:") + " " + text, -1)

    def _hide_for_run(self):
        self._was_visible = self.isVisible() and not self.isMinimized()
        if self._was_visible:
            self.showMinimized()

    def _end_run(self):
        self.status.hide()
        if getattr(self, "_was_visible", False):
            self._was_visible = False
            self.show_window()
        if self.tray:
            self.tray.setToolTip(APP_NAME)
        self.refresh()

    def status_text(self, text: str):
        if self.store.get("ui/status_overlay"):
            self.status.show_text(text)
        if self.tray:
            self.tray.setToolTip(f"{APP_NAME} — {text}")

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ============================================================ scheduler
    def open_scheduler(self):
        d = ScheduleDialog(self.store.schedule(), self.path, self)
        if d.exec():
            self.store.set_schedule(d.entries)

    def check_schedule(self):
        now = QDateTime.currentDateTime()
        last, self.sched_last = self.sched_last, now
        for e in self.store.schedule():
            if entry_due(e, now, last):
                self.run_entry(e)

    def _run_startup_entries(self):
        for e in self.store.schedule():
            if e.get("enabled", True) and e.get("mode") == "startup":
                self.run_entry(e)

    def run_entry(self, e: dict):
        if self.busy:
            self.statusBar().showMessage(tr("Scheduled macro skipped (busy):") + f" {e.get('file')}", 8000)
            return
        try:
            m = Macro.load(e["file"])
        except Exception as ex:
            self.statusBar().showMessage(tr("Scheduled macro failed:") + f" {ex}", 8000)
            return
        s = self.store.play_settings()
        if str(e.get("repeat", "")).strip():
            try:
                s.repeat = int(e["repeat"])
                s.repeat_until = ""
            except ValueError:
                pass
        self.play_source = e["file"]
        self.play(from_hotkey=True, macro=m, settings=s, base_dir=os.path.dirname(e["file"]))

    # ================================================================ files
    def maybe_save(self) -> bool:
        if not self.dirty or not self.macro.actions:
            return True
        r = QMessageBox.question(self, APP_NAME, tr("Save changes to the current macro?"),
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def new_macro(self):
        if self.busy or not self.maybe_save():
            return
        self.macro = Macro()
        self.path = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.model.set_actions(self.macro.actions)
        self.dirty = False
        self.refresh()

    def open_dialog(self):
        if self.busy or not self.maybe_save():
            return
        p, _ = QFileDialog.getOpenFileName(self, tr("Open macro"), self.store.get("ui/last_dir") or os.path.expanduser("~"),
                                           FILE_FILTER)
        if p:
            self.open_file(p, ask=False)

    def open_file(self, path: str, ask: bool = True):
        if ask and (self.busy or not self.maybe_save()):
            return
        try:
            m = Macro.load(path)
        except Exception as e:
            QMessageBox.critical(self, tr("Open"), tr("Cannot open file:") + f"\n{path}\n\n{e}")
            return
        self.macro = m
        self.path = path
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.model.set_actions(m.actions)
        self.apply_hidden()
        self.dirty = False
        self.store.add_recent(path)
        self.store.set("ui/last_dir", os.path.dirname(path))
        self._update_recent()
        self.refresh()

    def save(self) -> bool:
        if not self.path:
            return self.save_as()
        try:
            self.macro.save(self.path)
        except Exception as e:
            QMessageBox.critical(self, tr("Save"), str(e))
            return False
        self.dirty = False
        self.store.add_recent(self.path)
        self._update_recent()
        self.refresh()
        self.statusBar().showMessage(tr("Saved") + f" {self.path}", 4000)
        return True

    def save_as(self) -> bool:
        start = self.path or os.path.join(self.store.get("ui/last_dir") or os.path.expanduser("~"), "macro" + FILE_EXT)
        p, _ = QFileDialog.getSaveFileName(self, tr("Save macro"), start, FILE_FILTER)
        if not p:
            return False
        if not os.path.splitext(p)[1]:
            p += FILE_EXT
        self.path = p
        self.store.set("ui/last_dir", os.path.dirname(p))
        return self.save()

    def export_csv(self):
        base = os.path.splitext(self.path)[0] if self.path else os.path.join(os.path.expanduser("~"), "macro")
        p, _ = QFileDialog.getSaveFileName(self, tr("Export CSV"), base + ".csv", "CSV (*.csv)")
        if p:
            self.macro.export_csv(p)
            self.statusBar().showMessage(tr("Saved") + f" {p}", 4000)

    def create_shortcut(self):
        if not self.path:
            QMessageBox.information(self, APP_NAME, tr("Save the macro first."))
            if not self.save_as():
                return
        repeat = self.store.get("bar/repeat")
        speed = self.store.get("bar/speed")
        cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "macrorecorder"]
        args = cmd + ["--play", self.path, "--repeat", str(repeat), "--speed", str(speed / 100)]
        base = os.path.splitext(self.path)[0]
        if sys.platform.startswith("win"):
            import subprocess
            target = base + ".bat"
            content = f'@echo off\r\n{subprocess.list2cmdline(args)}\r\n'
        else:
            import shlex
            target = base + ".command"
            content = "#!/bin/sh\n" + " ".join(shlex.quote(a) for a in args) + "\n"
        p, _ = QFileDialog.getSaveFileName(self, tr("Create shortcut"), target)
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        if not sys.platform.startswith("win"):
            os.chmod(p, 0o755)
        QMessageBox.information(self, APP_NAME, tr("Created. Double-click it to play the macro:") + f"\n{p}")

    def _update_recent(self):
        self.recent_menu.clear()
        for p in self.store.recent():
            self.recent_menu.addAction(os.path.basename(p), lambda p=p: self.open_file(p)).setToolTip(p)
        if self.stack.currentIndex() == 0:
            self.empty.set_recent(self.store.recent())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls and not self.busy:
            self.open_file(urls[0].toLocalFile())

    # ================================================================= help
    def open_help(self):
        QDesktopServices.openUrl(QUrl(links.USER_GUIDE_URL))

    def about(self):
        QMessageBox.about(self, tr("About"), about_html())

    def show_tips(self, error: str | None = None):
        tips = []
        e = (error or "").lower()
        if "image" in e:
            tips.append(tr("Image not found: lower the similarity, re-capture the image at the current screen "
                           "scaling, or limit the search area."))
        if "text" in e or "ocr" in e:
            tips.append(tr("Text not found: check the OCR language in Settings and make the search area tighter."))
        if "window" in e:
            tips.append(tr("Window not found: use a shorter part of the window title or the application name."))
        if "label" in e:
            tips.append(tr("A Go to / If action points to a label that does not exist. Labels are set in the "
                           "Label column."))
        if "ai" in e or "http" in e or "model" in e:
            tips.append(tr("AI error: check the provider, API key and model in Settings → AI."))
        tips += [tr("Clicks land in the wrong place? Make sure screen resolution and scaling are the same as "
                    "when recording, or enable relative mouse positions."),
                 tr("Playback too fast for the program? Add Wait actions or lower the playback speed."),
                 tr("Use “Wait for image” or “Wait for window” instead of fixed waits for robust macros.")]
        if sys.platform == "darwin":
            tips.append(tr("macOS: Accessibility, Input Monitoring and Screen Recording permissions are needed "
                           "(Help → Permissions)."))
        else:
            tips.append(tr("Windows: to control programs running as administrator, run Actions Recorder as "
                           "administrator too."))
        head = f"<p><b>{tr('Playback error')}:</b> {error}</p>" if error else ""
        QMessageBox.information(self, tr("Troubleshooting"), head + "<ul>" + "".join(f"<li>{t}</li>" for t in tips)
                                + "</ul>")

    def check_permissions(self, force: bool = False):
        """First-run setup; on macOS also whenever recording/replay permissions are missing."""
        if force or not self.store.get("ui/onboarded") or missing_required_mac_permissions():
            SetupDialog(self.store, self).exec()

    # ================================================================= quit
    def quit_app(self):
        if self.maybe_save():
            self._quitting = True
            self.engine.stop()
            self.hub.stop()
            self.store.set("ui/geometry", self.saveGeometry())
            self.status.close()
            self.marker.close()
            if self.tray:
                self.tray.hide()
            QApplication.quit()

    def closeEvent(self, e):
        if self._quitting:
            e.accept()
            return
        e.ignore()
        self.quit_app()


_STD_BUTTONS_VI = {
    "OK": "OK", "&OK": "&OK", "Cancel": "Huỷ", "&Cancel": "&Huỷ", "&Yes": "&Có", "Yes": "Có", "&No": "&Không",
    "No": "Không", "Save": "Lưu", "&Save": "&Lưu", "Discard": "Không lưu", "Don't Save": "Không lưu",
    "Close": "Đóng", "&Close": "&Đóng", "Apply": "Áp dụng", "Reset": "Đặt lại", "Restore Defaults": "Mặc định",
    "Yes to &All": "Có tất cả", "N&o to All": "Không tất cả", "Abort": "Huỷ bỏ", "Retry": "Thử lại",
    "Ignore": "Bỏ qua", "Help": "Trợ giúp", "Open": "Mở", "&Open": "&Mở",
}


class _StdButtonTranslator(QTranslator):
    """Translates Qt's built-in standard button texts (no .qm file needed)."""

    def translate(self, context, source, disambiguation=None, n=-1):
        if context in ("QPlatformTheme", "QDialogButtonBox", "QMessageBox", "QGnomeTheme", "QFileDialog"):
            return _STD_BUTTONS_VI.get(source, "")
        return ""


def install_qt_translator(app: QApplication) -> None:
    from ..i18n import language
    if language() == "vi":
        app._std_translator = _StdButtonTranslator(app)
        app.installTranslator(app._std_translator)


def run(open_path: str | None = None, minimized: bool = False) -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("ActionsRecorder")
    app.setWindowIcon(icon("app"))
    app.setQuitOnLastWindowClosed(False)
    store = Store()
    set_language(store.get("ui/language"))
    install_qt_translator(app)
    apply_theme(app, store.get("ui/theme"))
    win = MainWindow(store, open_path, minimized)
    if not (minimized or store.get("ui/start_min")):
        win.show()
    return app.exec()

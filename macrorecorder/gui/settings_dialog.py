"""Preferences window (tabbed)."""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import keys
from ..ai import PROVIDERS, AIConfig, list_models
from ..i18n import tr
from .hotkey_edit import HotkeyField
from .store import HOTKEYS, Store

LANGUAGES = [("auto", "Same as system"), ("en", "English"), ("vi", "Tiếng Việt")]
THEMES = [("system", "Follow system"), ("light", "Light"), ("dark", "Dark")]
OCR_LANGS = [("", "Automatic"), ("en-US", "English"), ("vi-VN", "Vietnamese"), ("fr-FR", "French"),
             ("de-DE", "German"), ("es-ES", "Spanish"), ("ja-JP", "Japanese"), ("ko-KR", "Korean"),
             ("zh-Hans", "Chinese (Simplified)"), ("zh-Hant", "Chinese (Traditional)")]


def _spin(lo, hi, val, suffix=""):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(val)
    if suffix:
        s.setSuffix(" " + suffix)
    s.setMaximumWidth(120)
    return s


def _amp(text: str) -> str:
    """Translate a group title; a literal & must be doubled for Qt."""
    return tr(text).replace("&", "&&")


def _note(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setObjectName("caption")
    return lbl


class SettingsDialog(QDialog):
    def __init__(self, store: Store, parent=None, page: int = 0):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(tr("Preferences"))
        self.resize(720, 560)
        self.checks: dict[str, QCheckBox] = {}
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        for title, w in ((tr("Capture"), self._capture()), (tr("Replay"), self._replay()),
                         (tr("Shortcuts"), self._shortcuts()), (tr("Appearance"), self._appearance()),
                         (tr("AI"), self._ai()), (tr("Text recognition"), self._ocr())):
            self.tabs.addTab(w, title)
        self.tabs.setCurrentIndex(page)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset = bb.addButton(tr("Restore defaults"), QDialogButtonBox.ResetRole)
        reset.clicked.connect(self._reset)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(bb)

    def _check(self, key: str, text: str) -> QCheckBox:
        cb = QCheckBox(tr(text))
        cb.setChecked(self.store.get(key))
        self.checks[key] = cb
        return cb

    # ---------------------------------------------------------- pages
    def _capture(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox(_amp("Pointer"))
        f = QFormLayout(g)
        f.addRow(self._check("record/paths", "Keep the full path the pointer travels"))
        self.min_move = _spin(0, 200, self.store.get("record/min_move"), "px")
        f.addRow(tr("Ignore movements smaller than:"), self.min_move)
        self.sens = QSlider(Qt.Horizontal)
        self.sens.setRange(0, 100)
        self.sens.setValue(self.store.get("record/sensitivity"))
        sens_lbl = QLabel(f"{self.sens.value()}%")
        self.sens.valueChanged.connect(lambda v: sens_lbl.setText(f"{v}%"))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Coarse")))
        row.addWidget(self.sens, 1)
        row.addWidget(QLabel(tr("Fine")))
        row.addWidget(sens_lbl)
        f.addRow(tr("Path detail:"), row)
        lay.addWidget(g)
        g = QGroupBox(_amp("Keyboard"))
        f = QFormLayout(g)
        f.addRow(self._check("record/combine_text", "Turn consecutive typing into a single Text step"))
        f.addRow(self._check("record/ignore_mod_repeat", "Skip auto-repeat of held Shift / Ctrl / Alt / Cmd"))
        lay.addWidget(g)
        g = QGroupBox(_amp("Timing & windows"))
        f = QFormLayout(g)
        self.min_wait = _spin(0, 60000, self.store.get("record/min_wait"), "ms")
        f.addRow(tr("Create a Wait step for pauses longer than:"), self.min_wait)
        f.addRow(self._check("record/focus", "Note when I switch to another window"))
        f.addRow(self._check("record/skip_off", "Don't record step types that are turned off in Run options"))
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _replay(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox(_amp("While a macro runs"))
        f = QFormLayout(g)
        for key, text in (("play/abort_key", "Stop when I press any key"),
                          ("play/abort_mouse", "Stop when I move the mouse"),
                          ("play/block_keys", "Ignore my keyboard so it cannot interfere")):
            f.addRow(self._check(key, text))
        lay.addWidget(g)
        g = QGroupBox(_amp("Positions & input"))
        f = QFormLayout(g)
        for key, text in (("play/relative", "Treat coordinates as relative to where the pointer starts"),
                          ("play/restore_windows", "Move and resize windows back to their recorded place"),
                          ("play/use_vk", "Send virtual key codes (helps with some games)")):
            f.addRow(self._check(key, text))
        lay.addWidget(g)
        g = QGroupBox(_amp("Between and after runs"))
        f = QFormLayout(g)
        f.addRow(self._check("play/restore_mouse", "Put the pointer back where it was"))
        f.addRow(self._check("play/reset_vars", "Start every loop with empty variables and lists"))
        self.repeat_delay = _spin(0, 3_600_000, self.store.get("play/repeat_delay"), "ms")
        f.addRow(tr("Pause between loops:"), self.repeat_delay)
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _shortcuts(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.addRow(_note(tr("Global shortcuts work in every application. Click a field and press the "
                          "keys you want.")))
        self.hk: dict[str, HotkeyField] = {}
        for name, label, _ in HOTKEYS:
            fld = HotkeyField(self.store.get(f"hotkey/{name}"))
            self.hk[name] = fld
            f.addRow(tr(label).replace("&", "&&"), fld)
        return w

    def _appearance(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox(_amp("Look"))
        f = QFormLayout(g)
        self.theme = QComboBox()
        for v, label in THEMES:
            self.theme.addItem(tr(label), v)
        self.theme.setCurrentIndex(max(0, self.theme.findData(self.store.get("ui/theme"))))
        f.addRow(tr("Theme:"), self.theme)
        self.lang = QComboBox()
        for v, label in LANGUAGES:
            self.lang.addItem(tr(label) if v == "auto" else label, v)
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.store.get("ui/language"))))
        f.addRow(tr("Language:"), self.lang)
        f.addRow(self._check("ui/overlays", "Highlight the selected step's position on screen"))
        f.addRow(self._check("ui/status_overlay", "Show a small floating panel while recording or running"))
        lay.addWidget(g)
        g = QGroupBox(_amp("Window"))
        f = QFormLayout(g)
        for key, text in (("ui/hide_record", "Minimize while recording"),
                          ("ui/hide_play", "Minimize while running"),
                          ("ui/on_top", "Keep above other windows"),
                          ("ui/start_min", "Start in the background"),
                          ("ui/start_login", "Launch automatically when I log in"),
                          ("ui/tray", "Show an icon in the tray / menu bar")):
            f.addRow(self._check(key, text))
        lay.addWidget(g)
        g = QGroupBox(_amp("Messages"))
        f = QFormLayout(g)
        for key, text in (("ui/notifications", "Show desktop notifications"),
                          ("ui/tips", "Offer hints when a run fails"),
                          ("ui/confirm_delete", "Ask before deleting steps")):
            f.addRow(self._check(key, text))
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _ai(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        info = QLabel(tr("AI actions use any OpenAI-compatible service. OpenRouter gives access to many "
                         "models (Gemini, Claude, GPT, DeepSeek, Llama …) with one key. Ollama or LM Studio "
                         "run models locally — no data leaves your computer."))
        info.setWordWrap(True)
        f.addRow(info)
        self.provider = QComboBox()
        for v, label, _ in PROVIDERS:
            self.provider.addItem(tr(label), v)
        self.provider.setCurrentIndex(max(0, self.provider.findData(self.store.get("ai/provider"))))
        self.base_url = QLineEdit(self.store.get("ai/base_url"))
        self.api_key = QLineEdit(self.store.get("ai/api_key"))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setCurrentText(self.store.get("ai/model"))
        self.model_filter = QLineEdit()
        self.model_filter.setPlaceholderText(tr("Search models…"))
        self.models: list[str] = []
        self.model_filter.textChanged.connect(self._filter_models)
        load = QPushButton(tr("Load model list"))
        load.clicked.connect(self._load_models)
        test = QPushButton(tr("Test connection"))
        test.clicked.connect(self._test_ai)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        f.addRow(tr("Provider:"), self.provider)
        f.addRow(tr("Server URL:"), self.base_url)
        f.addRow(tr("API key:"), self.api_key)
        f.addRow(tr("Model:"), self.model)
        row = QHBoxLayout()
        row.addWidget(self.model_filter, 1)
        row.addWidget(load)
        row.addWidget(test)
        f.addRow("", row)
        return w

    def _ocr(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.ocr_lang = QComboBox()
        for v, label in OCR_LANGS:
            self.ocr_lang.addItem(tr(label), v)
        self.ocr_lang.setCurrentIndex(max(0, self.ocr_lang.findData(self.store.get("ocr/language"))))
        f.addRow(tr("OCR language:"), self.ocr_lang)
        note = QLabel(tr("Text recognition uses the engine built into the operating system (Apple Vision on "
                         "macOS, Windows OCR on Windows). On Windows the language must be installed under "
                         "Settings → Time & language → Language."))
        note.setWordWrap(True)
        f.addRow(note)
        return w

    # ----------------------------------------------------------- AI helpers
    def _provider_changed(self):
        url = dict((p, u) for p, _, u in PROVIDERS).get(self.provider.currentData(), "")
        if url:
            self.base_url.setText(url)

    def _cfg(self) -> AIConfig:
        return AIConfig(self.provider.currentData(), self.base_url.text().strip(), self.api_key.text().strip(),
                        self.model.currentText().strip(), timeout=60)

    def _background(self, fn, done):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        box: dict = {}

        def work():
            try:
                box["r"] = fn()
            except Exception as e:
                box["e"] = str(e)
        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                QTimer.singleShot(100, poll)
                return
            QApplication.restoreOverrideCursor()
            if "e" in box:
                QMessageBox.warning(self, tr("AI"), box["e"])
            else:
                done(box["r"])
        poll()

    def _load_models(self):
        def done(models):
            self.models = models
            self._filter_models()
            QMessageBox.information(self, tr("AI"), tr("Models loaded:") + f" {len(models)}")
        self._background(lambda: list_models(self._cfg()), done)

    def _filter_models(self):
        cur = self.model.currentText()
        q = self.model_filter.text().lower()
        self.model.clear()
        self.model.addItems([m for m in self.models if q in m.lower()])
        self.model.setCurrentText(cur)

    def _test_ai(self):
        from ..ai import chat
        self._background(lambda: chat(self._cfg(), "Reply with the single word: OK", max_tokens=10),
                         lambda r: QMessageBox.information(self, tr("AI"), tr("Answer:") + f" {r}"))

    # -------------------------------------------------------------- save
    def _reset(self):
        if QMessageBox.question(self, tr("Restore defaults"), tr("Restore all settings to their defaults?")) \
                == QMessageBox.Yes:
            self.store.reset()
            self.done(2)

    def _save(self):
        seen = {}
        for name, fld in self.hk.items():
            v = fld.value()
            if not v:
                continue
            parsed = keys.parse_hotkey(v)
            if parsed is None:
                QMessageBox.warning(self, tr("Hotkeys"), tr("Invalid hotkey:") + f" {v}")
                return
            if parsed in seen:
                QMessageBox.warning(self, tr("Hotkeys"), tr("The same hotkey is used twice:") + f" {v}")
                return
            seen[parsed] = name
        s = self.store
        for key, cb in self.checks.items():
            s.set(key, cb.isChecked())
        s.set("record/min_move", self.min_move.value())
        s.set("record/sensitivity", self.sens.value())
        s.set("record/min_wait", self.min_wait.value())
        s.set("play/repeat_delay", self.repeat_delay.value())
        for name, fld in self.hk.items():
            s.set(f"hotkey/{name}", fld.value())
        s.set("ui/theme", self.theme.currentData())
        s.set("ui/language", self.lang.currentData())
        s.set("ai/provider", self.provider.currentData())
        s.set("ai/base_url", self.base_url.text().strip())
        s.set("ai/api_key", self.api_key.text().strip())
        s.set("ai/model", self.model.currentText().strip())
        s.set("ocr/language", self.ocr_lang.currentData())
        self.accept()

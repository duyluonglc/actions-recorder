"""Line edit that records a key combination when the user presses it."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

from ..actions import combo_display
from ..i18n import tr

MAC = sys.platform == "darwin"

_SPECIAL = {
    Qt.Key_Return: "enter", Qt.Key_Enter: "enter", Qt.Key_Escape: "esc", Qt.Key_Tab: "tab",
    Qt.Key_Backtab: "tab", Qt.Key_Backspace: "backspace", Qt.Key_Delete: "delete", Qt.Key_Insert: "insert",
    Qt.Key_Home: "home", Qt.Key_End: "end", Qt.Key_PageUp: "page_up", Qt.Key_PageDown: "page_down",
    Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Up: "up", Qt.Key_Down: "down",
    Qt.Key_Space: "space", Qt.Key_CapsLock: "caps_lock", Qt.Key_Print: "print_screen",
    Qt.Key_Pause: "pause", Qt.Key_Menu: "menu", Qt.Key_NumLock: "num_lock", Qt.Key_ScrollLock: "scroll_lock",
}
_MOD_KEYS = {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr}


def combo_from_event(e) -> str | None:
    key = e.key()
    mods = e.modifiers()
    names = []
    ctrl_flag, cmd_flag = (Qt.MetaModifier, Qt.ControlModifier) if MAC else (Qt.ControlModifier, Qt.MetaModifier)
    if mods & ctrl_flag:
        names.append("ctrl")
    if mods & Qt.AltModifier:
        names.append("alt")
    if mods & Qt.ShiftModifier:
        names.append("shift")
    if mods & cmd_flag:
        names.append("cmd")
    if key in _MOD_KEYS:
        if not names:
            return None
        return "+".join(names)            # a bare modifier (e.g. "shift")
    if Qt.Key_F1 <= key <= Qt.Key_F35:
        main = f"f{key - Qt.Key_F1 + 1}"
    elif key in _SPECIAL:
        main = _SPECIAL[key]
    elif 0x20 < key < 0x7F:
        main = chr(key).lower()
    else:
        t = e.text()
        if not t or not t.isprintable():
            return None
        main = t.lower()
    return "+".join(names + [main])


class KeyCaptureEdit(QLineEdit):
    """Read-only line edit that captures the next key combination."""

    changed = Signal(str)

    def __init__(self, value: str = "", placeholder: str = "", allow_text: bool = False):
        super().__init__()
        self._value = ""
        self._placeholder = placeholder or tr("None (click here to define)")
        self.allow_text = allow_text      # also accept typed combos like "ctrl+shift+x"
        self.setReadOnly(not allow_text)
        self.set_value(value)

    def value(self) -> str:
        if self.allow_text:
            return self.text().strip()
        return self._value

    def set_value(self, v: str) -> None:
        self._value = v or ""
        if self.allow_text:
            self.setText(self._value)
        else:
            self.setText(combo_display(self._value) if self._value else "")
            self.setPlaceholderText(self._placeholder)
        self.changed.emit(self._value)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        if not self.allow_text:
            self.setPlaceholderText(tr("Press the key combination…"))

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.setPlaceholderText(self._placeholder)

    def keyPressEvent(self, e):
        if self.allow_text and not (e.modifiers() & (Qt.ControlModifier | Qt.MetaModifier | Qt.AltModifier)) \
                and e.key() not in _SPECIAL and not (Qt.Key_F1 <= e.key() <= Qt.Key_F35):
            super().keyPressEvent(e)       # normal typing
            return
        combo = combo_from_event(e)
        if combo:
            self.set_value(combo)
        e.accept()

    def keyReleaseEvent(self, e):
        e.accept()


class HotkeyField(QWidget):
    """Hotkey capture with a clear (✕) button and a conflict warning (⚠)."""

    def __init__(self, value: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = KeyCaptureEdit(value)
        self.edit.setMinimumWidth(260)
        self.clear = QToolButton()
        self.clear.setText("✕")
        self.clear.setStyleSheet("color:#d6392b;border:none;font-size:15px;")
        self.clear.setToolTip(tr("Remove hotkey"))
        self.clear.clicked.connect(lambda: self.edit.set_value(""))
        self.warn = QLabel("⚠")
        self.warn.setStyleSheet("color:#e8a317;font-size:17px;")
        lay.addWidget(self.edit)
        lay.addWidget(self.clear)
        lay.addWidget(self.warn)
        lay.addStretch(1)
        self.edit.changed.connect(self._refresh)
        self._refresh(value)

    def value(self) -> str:
        return self.edit.value()

    def set_value(self, v: str) -> None:
        self.edit.set_value(v)

    def _refresh(self, v: str) -> None:
        self.clear.setVisible(bool(v))
        parts = v.split("+") if v else []
        risky = bool(v) and (len(parts) == 1 and len(parts[0]) == 1 or
                             (len(parts) == 2 and parts[0] in ("ctrl", "cmd") and len(parts[1]) == 1))
        self.warn.setVisible(risky)
        self.warn.setToolTip(tr("This hotkey may conflict with shortcuts of other programs.") if risky else "")

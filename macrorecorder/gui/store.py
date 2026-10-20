"""Typed access to persistent settings (QSettings) with defaults."""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings

from ..actions import FILTER_GROUPS
from ..ai import PROVIDERS, AIConfig
from ..engine import PlaySettings
from ..recorder import RecordSettings

HOTKEYS = [
    ("record_append", "Record into the current macro", "f9"),
    ("record_new", "Record a new macro", ""),
    ("stop", "Stop", "f11"),
    ("play", "Run / stop running", "f10"),
    ("play_cursor", "Run from the selected step", ""),
    ("play_selection", "Run only the selected steps", ""),
    ("pause", "Pause / resume", "f12"),
    ("capture_pos", "Insert a click at the pointer", ""),
    ("sample", "Copy pointer position & color", ""),
]

DEFAULTS: dict = {
    # recording
    "record/paths": True, "record/min_move": 5, "record/sensitivity": 90,
    "record/ignore_mod_repeat": True, "record/combine_text": True, "record/min_wait": 100,
    "record/focus": True, "record/skip_off": False,
    # playback (settings dialog)
    "play/block_keys": False, "play/abort_key": False, "play/abort_mouse": False,
    "play/restore_mouse": False, "play/restore_windows": False, "play/relative": False,
    "play/use_vk": False, "play/reset_vars": False, "play/repeat_delay": 0,
    # playback (ribbon)
    "bar/mouse_moves": True, "bar/mouse_clicks": True, "bar/keys": True, "bar/waits": True,
    "bar/focus": True, "bar/notifications": True, "bar/speed": 100, "bar/mouse_path": "recorded",
    "bar/repeat": 1, "bar/repeat_until": "", "bar/after": "none",
    # user interface
    "ui/confirm_delete": False, "ui/hide_record": False, "ui/hide_play": False,
    "ui/notifications": True, "ui/tips": True, "ui/overlays": True, "ui/start_min": False,
    "ui/start_login": False, "ui/on_top": False, "ui/theme": "system", "ui/language": "auto",
    "ui/tray": True, "ui/status_overlay": True, "ui/onboarded": False,
    # AI
    "ai/provider": "openrouter", "ai/base_url": "https://openrouter.ai/api/v1", "ai/api_key": "",
    "ai/model": "",
    # OCR
    "ocr/language": "",
    # scheduler
    "schedule/entries": "[]",
}
for _name, _label, _default in HOTKEYS:
    DEFAULTS[f"hotkey/{_name}"] = _default


# Earlier default shortcuts: a saved value equal to one of these is treated as
# "never customised" and follows the current default instead.
_OLD_DEFAULTS = {"record_append": {"ctrl+alt+r", "ctrl+r"}, "play": {"ctrl+alt+p", "ctrl+e"},
                 "stop": {"ctrl+alt+s", "ctrl+q"}, "play_cursor": {"ctrl+t"}}


class Store:
    def __init__(self, qs: QSettings | None = None):
        self.qs = qs or QSettings("ActionsRecorder", "ActionsRecorder")
        for name, old in _OLD_DEFAULTS.items():
            if self.qs.value(f"hotkey/{name}") in old:
                self.qs.remove(f"hotkey/{name}")

    def get(self, key: str):
        default = DEFAULTS.get(key)
        v = self.qs.value(key, default)
        if isinstance(default, bool):
            return v in (True, "true", "1", 1)
        if isinstance(default, int):
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return default
        return "" if v is None else v

    def set(self, key: str, value) -> None:
        self.qs.setValue(key, value)

    def raw(self, key: str, default=None):
        return self.qs.value(key, default)

    def reset(self) -> None:
        for k in DEFAULTS:
            self.qs.remove(k)

    # ------------------------------------------------------------ bundles
    def record_settings(self) -> RecordSettings:
        g = self.get
        return RecordSettings(record_paths=g("record/paths"), min_move_px=g("record/min_move"),
                              sensitivity=g("record/sensitivity"), ignore_mod_repeat=g("record/ignore_mod_repeat"),
                              combine_text=g("record/combine_text"), min_wait_ms=g("record/min_wait"),
                              record_focus=g("record/focus"),
                              skip=tuple(k for k in FILTER_GROUPS if g("record/skip_off") and not g(f"bar/{k}")))

    def play_settings(self) -> PlaySettings:
        g = self.get
        try:
            speed = float(self.qs.value("bar/speed", 100))
        except (TypeError, ValueError):
            speed = 100.0
        return PlaySettings(
            speed_pct=speed, mouse_path=g("bar/mouse_path"), repeat=g("bar/repeat"),
            repeat_until=g("bar/repeat_until"), repeat_delay_ms=g("play/repeat_delay"),
            filters={"mouse_moves": g("bar/mouse_moves"), "mouse_clicks": g("bar/mouse_clicks"),
                     "keys": g("bar/keys"), "waits": g("bar/waits"), "focus": g("bar/focus")},
            relative=g("play/relative"), use_vk=g("play/use_vk"), block_keys=g("play/block_keys"),
            abort_on_key=g("play/abort_key"), abort_on_mouse=g("play/abort_mouse"),
            restore_mouse=g("play/restore_mouse"), restore_windows=g("play/restore_windows"),
            reset_vars=g("play/reset_vars"), ai=self.ai_config())

    def ai_config(self) -> AIConfig:
        prov = self.get("ai/provider")
        base = self.get("ai/base_url") or dict((p, u) for p, _, u in PROVIDERS).get(prov, "")
        return AIConfig(provider=prov, base_url=base, api_key=self.get("ai/api_key"), model=self.get("ai/model"))

    def hotkeys(self) -> dict[str, str]:
        return {name: self.get(f"hotkey/{name}") for name, _, _ in HOTKEYS}

    def schedule(self) -> list[dict]:
        try:
            v = json.loads(self.get("schedule/entries") or "[]")
            return v if isinstance(v, list) else []
        except ValueError:
            return []

    def set_schedule(self, entries: list[dict]) -> None:
        self.set("schedule/entries", json.dumps(entries))

    def recent(self) -> list[str]:
        r = self.qs.value("ui/recent", []) or []
        return [r] if isinstance(r, str) else list(r)

    def add_recent(self, path: str) -> None:
        r = [p for p in self.recent() if p != path]
        r.insert(0, path)
        self.qs.setValue("ui/recent", r[:10])

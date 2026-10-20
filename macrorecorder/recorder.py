"""Global input capture (hotkeys + recording) and conversion of the raw input
stream into editable actions."""

from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from pynput import keyboard, mouse

from . import keys
from .actions import Action

BUTTON_NAMES = {mouse.Button.left: "left", mouse.Button.right: "right", mouse.Button.middle: "middle"}


@dataclass
class Raw:
    t: float          # ms since recording start
    kind: str         # move down up scroll kdown kup focus
    data: dict = field(default_factory=dict)


@dataclass
class RecordSettings:
    record_paths: bool = True
    min_move_px: int = 5
    sensitivity: int = 90            # 0..100 -> mouse sampling rate
    ignore_mod_repeat: bool = True
    combine_text: bool = True
    min_wait_ms: int = 100
    record_focus: bool = True
    record_clicks: bool = True
    record_keys: bool = True

    @property
    def sample_ms(self) -> float:
        return 5 + (100 - max(0, min(100, self.sensitivity))) * 0.95


class InputHub:
    """Owns the pynput listeners. Callbacks run in listener threads."""

    def __init__(self, on_hotkey: Callable[[str], None] | None = None,
                 on_count: Callable[[int], None] | None = None):
        self.on_hotkey = on_hotkey
        self.on_count = on_count
        self._hotkeys: dict[tuple[frozenset[str], str], str] = {}
        self._mods: set[str] = set()
        self._suppressed: set[str] = set()
        self._lock = threading.Lock()
        self._recording = False
        self._paused = False
        self._raw: list[Raw] = []
        self._t0 = 0.0
        self._pause_total = 0.0
        self._pause_start = 0.0
        self._last_move = 0.0
        self._opts = RecordSettings()
        self._kb: keyboard.Listener | None = None
        self._mouse: mouse.Listener | None = None
        self._focus_thread: threading.Thread | None = None
        self.hotkeys_enabled = True

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._kb is None:
            self._kb = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
            self._kb.daemon = True
            self._kb.start()

    def stop(self) -> None:
        if self._kb:
            self._kb.stop()
            self._kb = None
        self._stop_mouse()
        self._recording = False

    def set_hotkeys(self, mapping: dict[str, str]) -> list[str]:
        bad, hk = [], {}
        for name, text in mapping.items():
            parsed = keys.parse_hotkey(text)
            if parsed is None:
                if text:
                    bad.append(name)
                continue
            hk[parsed] = name
        self._hotkeys = hk
        return bad

    # ----------------------------------------------------------- recording
    @property
    def recording(self) -> bool:
        return self._recording

    def _now(self) -> float:
        return (time.perf_counter() - self._t0 - self._pause_total) * 1000.0

    def start_recording(self, opts: RecordSettings) -> None:
        with self._lock:
            self._opts = opts
            self._raw = []
            self._t0 = time.perf_counter()
            self._pause_total = 0.0
            self._paused = False
            self._last_move = -1e9
            self._recording = True
        self._mouse = mouse.Listener(on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll)
        self._mouse.daemon = True
        self._mouse.start()
        if opts.record_focus:
            self._focus_thread = threading.Thread(target=self._poll_focus, daemon=True)
            self._focus_thread.start()

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            if paused and not self._paused:
                self._pause_start = time.perf_counter()
            elif not paused and self._paused:
                self._pause_total += time.perf_counter() - self._pause_start
            self._paused = paused

    @property
    def paused(self) -> bool:
        return self._paused

    def stop_recording(self, strip_last_click: bool = False) -> list[Action]:
        with self._lock:
            self._recording = False
            raw = self._raw
            self._raw = []
        self._stop_mouse()
        if strip_last_click:
            raw = strip_trailing_click(raw)
        return build_actions(raw, self._opts)

    def _stop_mouse(self) -> None:
        if self._mouse:
            self._mouse.stop()
            self._mouse = None

    def _add(self, kind: str, **data) -> None:
        with self._lock:
            if not self._recording or self._paused:
                return
            self._raw.append(Raw(self._now(), kind, data))
            n = len(self._raw)
        if self.on_count:
            self.on_count(n)

    def _poll_focus(self) -> None:
        from . import winmgr
        last = None
        me = os.getpid()
        while self._recording:
            try:
                w = winmgr.active_window()
            except Exception:
                w = None
            if w is not None and w.pid != me:
                key = (w.app, w.title)
                if key != last and not self._paused:
                    last = key
                    rect = ",".join(str(v) for v in w.rect) if w.rect else ""
                    self._add("focus", app=w.app, title=w.title, rect=rect)
            time.sleep(0.25)

    # ------------------------------------------------- listener callbacks
    def _on_press(self, key, injected: bool = False) -> None:
        ks, vk = keys.encode(key)
        mod = keys.mod_of(ks)
        if injected:
            return
        if mod:
            self._mods.add(mod)
        elif self.hotkeys_enabled:
            name = self._hotkeys.get((frozenset(self._mods), keys.hotkey_token(key)))
            if name:
                self._suppressed.add(ks)
                self._fire(name)
                return
        if self._recording and self._opts.record_keys:
            self._add("kdown", key=ks, vk=vk)

    def _on_release(self, key, injected: bool = False) -> None:
        ks, vk = keys.encode(key)
        mod = keys.mod_of(ks)
        if injected:
            return
        if mod:
            self._mods.discard(mod)
        if ks in self._suppressed:
            self._suppressed.discard(ks)
            return
        if self._recording and self._opts.record_keys:
            self._add("kup", key=ks, vk=vk)

    def _fire(self, name: str) -> None:
        if self.on_hotkey:
            try:
                self.on_hotkey(name)
            except Exception:
                import traceback
                traceback.print_exc()

    def _on_move(self, x, y, injected: bool = False) -> None:
        if injected or not self._recording:
            return
        now = time.perf_counter() * 1000
        if now - self._last_move < self._opts.sample_ms:
            return
        self._last_move = now
        self._add("move", x=int(x), y=int(y))

    def _on_click(self, x, y, button, pressed, injected: bool = False) -> None:
        if injected or not self._opts.record_clicks:
            return
        self._add("down" if pressed else "up", x=int(x), y=int(y), button=BUTTON_NAMES.get(button, "left"))

    def _on_scroll(self, x, y, dx, dy, injected: bool = False) -> None:
        if injected or not self._opts.record_clicks:
            return
        self._add("scroll", x=int(x), y=int(y), dx=int(dx), dy=int(dy))


# =========================================================== raw -> actions

def strip_trailing_click(raw: list[Raw]) -> list[Raw]:
    """Recording stopped by clicking our own UI: drop that click and the path to it."""
    raw = list(raw)
    for kind in ("up", "down"):
        for i in range(len(raw) - 1, -1, -1):
            if raw[i].kind == kind:
                del raw[i]
                break
    while raw and raw[-1].kind in ("move", "focus"):
        raw.pop()
    return raw


def build_actions(raw: list[Raw], o: RecordSettings) -> list[Action]:
    b = _Builder(o)
    b.run(raw)
    return b.out


class _Builder:
    CLICK_MS = 500
    CLICK_PX = 4

    def __init__(self, o: RecordSettings):
        self.o = o
        self.out: list[Action] = []
        self.last_t: float | None = None
        self.mods: dict[str, dict] = {}       # mod -> {"used":bool, "emitted":bool}
        self.held_keys: set[str] = set()      # non-modifier keys emitted as key_down
        self.consumed_up: dict[str, int] = {}  # key -> pending key-ups to swallow
        self.buttons: set[str] = set()
        self.last_click_t = -1e9
        self.text_open = False

    # -------------------------------------------------------- emitting
    def emit(self, a: Action, t: float, t_end: float | None = None, join_text: bool = False) -> None:
        if not join_text:
            self.text_open = False
        if self.last_t is not None:
            gap = t - self.last_t
            if gap >= self.o.min_wait_ms:
                self.out.append(Action.new("wait", ms=str(int(round(gap)))))
        self.out.append(a)
        self.last_t = t if t_end is None else t_end

    def press_mods_for_mouse(self, t: float) -> None:
        for m, st in self.mods.items():
            if not st["emitted"]:
                self.emit(Action.new("key_down", combo=m), t)
                st["emitted"] = st["used"] = True

    # ------------------------------------------------------------ main
    def run(self, raw: list[Raw]) -> None:
        i = 0
        n = len(raw)
        # ignore releases that belong to whatever started the recording
        while i < n and raw[i].kind in ("kup", "up"):
            i += 1
        while i < n:
            e = raw[i]
            k = e.kind
            if k == "move":
                j = i
                while j < n and raw[j].kind == "move":
                    j += 1
                self.moves(raw[i:j])
                i = j
                continue
            if k == "down":
                i = self.mouse_down(raw, i)
                continue
            if k == "up":
                if e.data["button"] in self.buttons:
                    self.buttons.discard(e.data["button"])
                    self.emit(Action.new("mouse_up", button=e.data["button"], x=e.data["x"], y=e.data["y"]), e.t)
                i += 1
                continue
            if k == "scroll":
                i = self.scroll(raw, i)
                continue
            if k == "focus":
                if self.o.record_focus:
                    self.emit(Action.new("focus", app=e.data.get("app", ""), title=e.data.get("title", ""),
                                         rect=e.data.get("rect", "")), e.t)
                i += 1
                continue
            if k == "kdown":
                self.key_down(raw, i)
            elif k == "kup":
                self.key_up(e)
            i += 1
        # balance modifiers that are still down
        end_t = raw[-1].t if raw else 0
        for m, st in list(self.mods.items()):
            if st["emitted"]:
                self.emit(Action.new("key_up", combo=m), end_t)
        for tok in list(self.held_keys):
            self.emit(Action.new("key_up", combo=tok), end_t)
        for btn in list(self.buttons):
            self.emit(Action.new("mouse_up", button=btn), end_t)

    # ------------------------------------------------------------ mouse
    def moves(self, run: list[Raw]) -> None:
        if not (self.o.record_paths or self.buttons):
            return
        pts = [run[0]]
        for r in run[1:-1]:
            if math.dist((pts[-1].data["x"], pts[-1].data["y"]), (r.data["x"], r.data["y"])) >= self.o.min_move_px:
                pts.append(r)
        if len(run) > 1:
            pts.append(run[-1])
        if len(pts) == 1:
            r = pts[0]
            self.emit(Action.new("mouse_move", x=r.data["x"], y=r.data["y"]), r.t)
            return
        t0 = pts[0].t
        points = [[r.data["x"], r.data["y"], int(round(r.t - t0))] for r in pts]
        self.emit(Action.new("mouse_path", points=points), t0, pts[-1].t)

    def mouse_down(self, raw: list[Raw], i: int) -> int:
        e = raw[i]
        btn, x, y = e.data["button"], e.data["x"], e.data["y"]
        self.press_mods_for_mouse(e.t)
        # look for the matching release; a window-focus change caused by this very
        # click (it often lands between press and release) must not split it
        j = i + 1
        focus: list[Raw] = []
        while j < len(raw) and raw[j].kind in ("move", "focus"):
            if raw[j].kind == "focus":
                focus.append(raw[j])
            j += 1
        if j < len(raw) and raw[j].kind == "up" and raw[j].data["button"] == btn:
            up = raw[j]
            moved = max([math.dist((x, y), (r.data["x"], r.data["y"])) for r in raw[i + 1:j + 1]
                         if r.kind in ("move", "up")] or [0])
            if up.t - e.t <= self.CLICK_MS and moved <= self.CLICK_PX:
                prev = self.out[-1] if self.out else None
                if (prev is not None and prev.kind == "click" and prev.params.get("button") == btn
                        and int(prev.params.get("count", 1)) < 3 and prev.params.get("x") is not None
                        and abs(prev.params["x"] - x) <= self.CLICK_PX
                        and abs(prev.params["y"] - y) <= self.CLICK_PX
                        and e.t - self.last_click_t <= self.CLICK_MS):
                    prev.params["count"] = int(prev.params.get("count", 1)) + 1
                    self.last_t = up.t
                else:
                    self.emit(Action.new("click", button=btn, x=x, y=y, count=1), e.t, up.t)
                self.last_click_t = up.t
                if self.o.record_focus:
                    for f in focus:
                        self.out.append(Action.new("focus", app=f.data.get("app", ""), title=f.data.get("title", ""),
                                                   rect=f.data.get("rect", "")))
                return j + 1
        self.buttons.add(btn)
        self.emit(Action.new("mouse_down", button=btn, x=x, y=y), e.t)
        return i + 1

    def scroll(self, raw: list[Raw], i: int) -> int:
        e = raw[i]
        dx, dy = e.data["dx"], e.data["dy"]
        j = i + 1
        last = e.t
        while (j < len(raw) and raw[j].kind == "scroll" and raw[j].t - last < 300
               and abs(raw[j].data["x"] - e.data["x"]) <= 2 and abs(raw[j].data["y"] - e.data["y"]) <= 2
               and (raw[j].data["dy"] > 0) == (dy > 0)):
            dx += raw[j].data["dx"]
            dy += raw[j].data["dy"]
            last = raw[j].t
            j += 1
        self.press_mods_for_mouse(e.t)
        self.emit(Action.new("scroll", dx=dx, dy=dy, x=e.data["x"], y=e.data["y"]), e.t, last)
        return j

    # --------------------------------------------------------- keyboard
    def key_down(self, raw: list[Raw], i: int) -> None:
        e = raw[i]
        ks, vk = e.data["key"], e.data.get("vk")
        mod = keys.mod_of(ks)
        if mod:
            if mod in self.mods:
                if self.o.ignore_mod_repeat:
                    return
            self.mods[mod] = {"used": False, "emitted": False, "t": e.t}
            return
        token = keys.base_token(ks, vk)
        if token in self.held_keys:
            return            # auto-repeat of a held key
        combo_mods = [m for m in ("ctrl", "alt", "cmd") if m in self.mods and not self.mods[m]["emitted"]]
        shift = "shift" in self.mods and not self.mods["shift"]["emitted"]
        # held for a long time with nothing else happening -> key down / key up
        up_t = None
        repeats = 0
        for r in raw[i + 1:]:
            if r.kind == "kup" and r.data["key"] == ks:
                up_t = r.t
                break
            if r.kind == "kdown" and r.data["key"] == ks:
                repeats += 1
            elif r.kind not in ("kdown", "kup", "move"):
                break
        if up_t is not None and repeats == 0 and up_t - e.t > 600 and not combo_mods:
            for m in combo_mods + (["shift"] if shift else []):
                self.mods[m]["used"] = True
            self.emit(Action.new("key_down", combo=token), e.t)
            self.held_keys.add(token)
            return
        self.consumed_up[ks] = self.consumed_up.get(ks, 0) + 1
        is_char = len(ks) == 1 and ks.isprintable()
        if combo_mods:
            tok = (keys.vk_to_char(vk) or token).lower() if (is_char or ks.startswith("vk:")) else token
            mods = combo_mods + (["shift"] if shift else [])
            for m in mods:
                self.mods[m]["used"] = True
            self._press("+".join(sorted(mods, key=keys.MODS.index) + [tok]), e.t)
            return
        if is_char and self.o.combine_text:
            if shift:
                self.mods["shift"]["used"] = True
            prev = self.out[-1] if self.out else None
            gap = e.t - (self.last_t or e.t)
            if self.text_open and prev is not None and prev.kind == "type_text" and gap < self.o.min_wait_ms:
                prev.params["text"] += ks
                self.last_t = e.t
            else:
                self.emit(Action.new("type_text", text=ks), e.t, join_text=True)
                self.text_open = True
            return
        if shift and not is_char:
            self.mods["shift"]["used"] = True
            token = "shift+" + token
        elif shift:
            self.mods["shift"]["used"] = True
        self._press(token, e.t)

    def _press(self, combo: str, t: float) -> None:
        prev = self.out[-1] if self.out else None
        if (prev is not None and prev.kind == "key_press" and prev.params.get("combo") == combo
                and self.last_t is not None and t - self.last_t < self.o.min_wait_ms):
            prev.params["count"] = int(prev.params.get("count", 1)) + 1
            self.last_t = t
            return
        self.emit(Action.new("key_press", combo=combo, count=1), t)

    def key_up(self, e: Raw) -> None:
        ks, vk = e.data["key"], e.data.get("vk")
        mod = keys.mod_of(ks)
        if mod:
            st = self.mods.pop(mod, None)
            if st is None:
                return
            if st["emitted"]:
                self.emit(Action.new("key_up", combo=mod), e.t)
            elif not st["used"]:
                self._press(mod, st["t"])
            return
        token = keys.base_token(ks, vk)
        if token in self.held_keys:
            self.held_keys.discard(token)
            self.emit(Action.new("key_up", combo=token), e.t)
            return
        if self.consumed_up.get(ks):
            self.consumed_up[ks] -= 1

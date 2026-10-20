"""Playback engine: interprets a macro (runs in a background thread)."""

from __future__ import annotations

import datetime as dt
import math
import os
import random
import re
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field

from pynput import keyboard, mouse

from . import keys, system, winmgr
from .actions import FILTER_GROUPS, Action
from .expr import compare, evaluate, number, substitute
from .macro import Macro, Target

# steps that act on the screen, mouse or keyboard: the target window must be ready for them
TARGET_KINDS = {"click", "mouse_down", "mouse_up", "mouse_move", "mouse_path", "scroll", "type_text", "key_press",
                "key_down", "key_up", "wait_image", "wait_text", "wait_pixel", "wait_change", "find_image",
                "find_text", "capture_text", "capture_image", "read_barcode", "get_pixel", "ai_image", "ai_find"}

BUTTONS = {"left": mouse.Button.left, "right": mouse.Button.right, "middle": mouse.Button.middle}
PASTE_MOD = keyboard.Key.cmd if sys.platform == "darwin" else keyboard.Key.ctrl


@dataclass
class PlaySettings:
    speed_pct: float = 100.0
    mouse_path: str = "recorded"        # recorded / straight / natural / jump
    repeat: int = 1                     # 0 = forever
    repeat_until: str = ""              # "HH:MM" -> repeat until this time of day
    repeat_delay_ms: int = 0
    filters: dict = field(default_factory=lambda: {k: True for k in FILTER_GROUPS})
    relative: bool = False
    use_vk: bool = False
    block_keys: bool = False
    abort_on_key: bool = False
    abort_on_mouse: bool = False
    restore_mouse: bool = False
    restore_windows: bool = False
    reset_vars: bool = False
    ai: object = None                   # ai.AIConfig

    @property
    def factor(self) -> float:
        return 100.0 / max(1.0, self.speed_pct)


class EngineUI:
    """Callbacks into the host (GUI or console). Called from the engine thread."""

    def progress(self, index: int, cycle: int) -> None: ...
    def variables(self, values: dict) -> None: ...
    def message_box(self, title: str, text: str, buttons: str) -> str: return "ok"
    def ask_input(self, prompt: str) -> str | None: return ""
    def notify(self, text: str, index: int) -> None: print(text)
    def finished(self, completed: bool, error: str | None) -> None: ...


class Stop(Exception):
    """Playback cancelled (user stop, abort key, Cancel button)."""


class Finish(Stop):
    """Macro ended on purpose ("Stop playback" action, end of a data list)."""


class EngineError(Exception):
    def __init__(self, msg: str, index: int = -1):
        super().__init__(msg)
        self.index = index


class Engine:
    def __init__(self, ui: EngineUI | None = None):
        self.ui = ui or EngineUI()
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._thread: threading.Thread | None = None
        self.mouse = mouse.Controller()
        self.kb = keyboard.Controller()
        self.vars: dict[str, str] = {}
        self._held_keys: set = set()
        self._held_buttons: set = set()
        self._lists: dict[str, tuple[list[str], int]] = {}
        self._listeners: list = []
        self._last_var_push = 0.0
        self.current_index = -1
        self.offset = (0, 0)
        self.target: Target | None = None
        self.target_win = None

    # ----------------------------------------------------------- control
    @property
    def playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def paused(self) -> bool:
        return not self._resume.is_set()

    def play(self, macro: Macro, s: PlaySettings, start: int = 0, end: int | None = None,
             base_dir: str = "", keep_vars: bool = True) -> None:
        if self.playing:
            return
        self._stop.clear()
        self._resume.set()
        if not keep_vars:
            self.vars = {}
        self._thread = threading.Thread(target=self._run, args=(macro.copy(), s, start, end, base_dir),
                                        daemon=True, name="macro-engine")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._resume.set()

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------ timing
    def sleep(self, seconds: float) -> None:
        """Interruptible, pause-aware sleep. Raises Stop."""
        end = time.perf_counter() + max(0.0, seconds)
        while True:
            if not self._resume.is_set():
                t = time.perf_counter()
                self._resume.wait()
                end += time.perf_counter() - t
            if self._stop.is_set():
                raise Stop
            left = end - time.perf_counter()
            if left <= 0:
                return
            time.sleep(min(left, 0.02) if left > 0.003 else 0)

    def check(self) -> None:
        if not self._resume.is_set():
            self._resume.wait()
        if self._stop.is_set():
            raise Stop

    # --------------------------------------------------------------- run
    def _run(self, macro: Macro, s: PlaySettings, start: int, end: int | None, base_dir: str) -> None:
        completed, error = False, None
        self.s = s
        self.base_dir = base_dir
        start_pos = self.mouse.position
        self._start_listeners(s)
        try:
            self.offset = (0, 0)
            self.target = macro.target
            self.target_win = None
            if self.target is None and s.relative:
                first = next((a for a in macro.actions if a.params.get("x") is not None), None)
                if first is None:
                    first = next((a for a in macro.actions if a.kind == "mouse_path" and a.params.get("points")), None)
                    fx, fy = (first.params["points"][0][:2] if first else (None, None))
                else:
                    fx, fy = first.params["x"], first.params["y"]
                if fx is not None:
                    cx, cy = self.mouse.position
                    self.offset = (int(cx) - int(fx), int(cy) - int(fy))
            until = None
            if s.repeat_until:
                try:
                    h, m = [int(v) for v in s.repeat_until.split(":")[:2]]
                    now = dt.datetime.now()
                    until = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if until <= now:
                        until += dt.timedelta(days=1)
                except ValueError:
                    until = None
            cycle = 0
            while True:
                cycle += 1
                if s.reset_vars and cycle > 1:
                    self.vars = {}
                    self._lists.clear()
                self.vars["repeat"] = str(cycle)
                self._exec_list(macro.actions, cycle, start if cycle == 1 else 0, end, depth=0)
                if until is not None:
                    if dt.datetime.now() >= until:
                        break
                elif s.repeat and cycle >= s.repeat:
                    break
                if s.repeat_delay_ms:
                    self.sleep(s.repeat_delay_ms / 1000 * s.factor)
            completed = True
        except Finish:
            completed = True
        except Stop:
            pass
        except EngineError as e:
            error = f"#{e.index + 1}: {e}" if e.index >= 0 else str(e)
        except Exception as e:  # pragma: no cover - unexpected
            import traceback
            traceback.print_exc()
            error = f"#{self.current_index + 1}: {type(e).__name__}: {e}"
        finally:
            self._stop_listeners()
            self._release_all()
            if s.restore_mouse:
                try:
                    self.mouse.position = start_pos
                except Exception:
                    pass
            self.ui.variables(dict(self.vars))
            self.ui.finished(completed, error)

    def _exec_list(self, actions: list[Action], cycle: int, start: int, end: int | None, depth: int) -> None:
        labels = {}
        for i, a in enumerate(actions):
            if a.label and a.label not in labels:
                labels[a.label] = i
        counters: dict[int, int] = {}
        pc = start
        stop_at = len(actions) if end is None else min(end, len(actions))
        steps = 0
        while pc < stop_at:
            self.check()
            a = actions[pc]
            if depth == 0:
                self.current_index = pc
            if not a.enabled or not self._passes_filter(a):
                pc += 1
                continue
            if depth == 0:
                self.ui.progress(pc, cycle)
            if self.target is not None and a.kind in TARGET_KINDS:
                self.ensure_target()
            try:
                jump = self._exec(a, labels, counters, pc, cycle, depth)
            except (Stop, EngineError):
                raise
            except Exception as e:
                raise EngineError(f"{a.name}: {e}", pc if depth == 0 else -1) from e
            self._push_vars()
            if jump is None:
                pc += 1
            else:
                if jump not in labels:
                    raise EngineError(f"Label not found: {jump}", pc if depth == 0 else -1)
                pc = labels[jump]
            steps += 1
            if steps % 200 == 0:
                time.sleep(0)    # let other threads breathe in tight loops

    def _passes_filter(self, a: Action) -> bool:
        for group, kinds in FILTER_GROUPS.items():
            if a.kind in kinds and not self.s.filters.get(group, True):
                return False
        return True

    def _push_vars(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_var_push > 0.2:
            self._last_var_push = now
            self.ui.variables(dict(self.vars))

    # ------------------------------------------------------------ helpers
    def sub(self, v) -> str:
        return substitute(v, self.vars)

    def num(self, v, default: float = 0.0) -> float:
        return number(v, self.vars, default)

    def pos(self, a: Action) -> tuple[int, int] | None:
        x, y = a.params.get("x"), a.params.get("y")
        if x is None or y is None or x == "" or y == "":
            return None
        return int(self.num(x)) + self.offset[0], int(self.num(y)) + self.offset[1]

    def move_to(self, p: tuple[int, int] | None) -> None:
        if p is not None:
            self.mouse.position = p

    def glide(self, target: tuple[int, int], duration: float, natural: bool) -> None:
        sx, sy = self.mouse.position
        tx, ty = target
        steps = max(2, int(duration / 0.01))
        if natural:
            mx, my = (sx + tx) / 2, (sy + ty) / 2
            d = math.dist((sx, sy), (tx, ty))
            cx = mx + random.uniform(-0.25, 0.25) * d
            cy = my + random.uniform(-0.25, 0.25) * d
        for i in range(1, steps + 1):
            t = i / steps
            t = t * t * (3 - 2 * t)
            if natural:
                x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * tx
                y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * ty
            else:
                x, y = sx + (tx - sx) * t, sy + (ty - sy) * t
            self.mouse.position = (int(x), int(y))
            self.sleep(duration / steps)
        self.mouse.position = target

    def tap(self, combo: str, count: int = 1) -> None:
        mods, key = keys.parse_combo(combo)
        key = self._vk(key)
        for n in range(max(1, count)):
            for m in mods:
                self.kb.press(m)
            self.kb.press(key)
            self.kb.release(key)
            for m in reversed(mods):
                self.kb.release(m)
            if n + 1 < count:
                self.sleep(0.03)

    def _vk(self, key):
        """'Always use virtual key codes': on Windows send chars as VK presses."""
        if not (self.s.use_vk and sys.platform.startswith("win")):
            return key
        if isinstance(key, keyboard.KeyCode) and key.char and key.vk is None:
            import ctypes
            r = ctypes.windll.user32.VkKeyScanW(ord(key.char))
            if r != -1 and not (r >> 8) & 0xFE:
                return keyboard.KeyCode.from_vk(r & 0xFF)
        return key

    def type_text(self, text: str, human: bool) -> None:
        for ch in text:
            self.check()
            if ch == "\n":
                self.tap("enter")
            elif ch == "\t":
                self.tap("tab")
            else:
                k = self._vk(keyboard.KeyCode.from_char(ch))
                if k is not None and k.vk is not None and k.char is None:
                    self.kb.press(k)
                    self.kb.release(k)
                else:
                    self.kb.type(ch)
            if human:
                self.sleep(random.uniform(0.04, 0.17) * self.s.factor)
            else:
                self.sleep(0.004)

    def screen_region(self, a: Action):
        r = a.params.get("region")
        if not r:
            if self.target is not None and self.target.relative and self.target_win is not None \
                    and self.target_win.rect:
                return list(self.target_win.rect)      # "whole screen" = the whole target window
            return None
        r = [int(self.num(v)) for v in r]
        if self.target is not None and self.target.relative:
            r[0] += self.offset[0]
            r[1] += self.offset[1]
        return r

    def ensure_target(self) -> None:
        """Make sure the target window exists (waiting for it if needed), bring it
        to the front, and use its top-left corner as the coordinate origin."""
        t = self.target
        w = winmgr.refresh(self.target_win) if self.target_win is not None else None
        if w is None or not w.matches(t.app, t.title):
            found: list = []

            def test():
                win = winmgr.find_window(t.app, t.title)
                if win is not None:
                    found.append(win)
                return win is not None
            if not self.poll(test, max(1, t.timeout_ms), 0.25):
                raise EngineError(f"Target window not found: {t.describe()}", self.current_index)
            w = found[-1]
        if t.activate and not winmgr.is_active(w):
            winmgr.activate(w)
            self.sleep(0.25)
            w = winmgr.refresh(w) or w
        self.target_win = w
        if t.relative and w.rect:
            self.offset = w.origin

    def fail(self, a: Action, what: str) -> str | None:
        of = a.params.get("on_fail", "continue")
        if of == "stop":
            raise EngineError(what, self.current_index)
        if of == "goto":
            return self.sub(a.params.get("fail_label", ""))
        return None

    def poll(self, test, timeout_ms: float, interval: float = 0.25) -> bool:
        """Run ``test`` until it returns True or timeout (0 = forever)."""
        end = None if timeout_ms <= 0 else time.monotonic() + timeout_ms / 1000
        while True:
            if test():
                return True
            if end is not None and time.monotonic() >= end:
                return False
            self.sleep(interval)

    def then(self, a: Action, p: tuple[int, int]) -> str | None:
        """Shared tail of find_image / find_text / ai_find."""
        x, y = p
        x += int(a.params.get("off_x", 0) or 0)
        y += int(a.params.get("off_y", 0) or 0)
        # variables use the macro's coordinate system so they can feed later click steps
        rel = self.offset if (self.target is not None and self.target.relative) else (0, 0)
        if a.params.get("var_x"):
            self.vars[a.params["var_x"]] = str(x - rel[0])
        if a.params.get("var_y"):
            self.vars[a.params["var_y"]] = str(y - rel[1])
        then = a.params.get("then", "click")
        if then != "none":
            self.move_to((x, y))
        if then == "click":
            self.mouse.click(mouse.Button.left, 1)
        elif then == "double":
            self.mouse.click(mouse.Button.left, 2)
        elif then == "right":
            self.mouse.click(mouse.Button.right, 1)
        lbl = a.params.get("found_label")
        return self.sub(lbl) if lbl else None

    def resolve_path(self, path: str) -> str:
        path = os.path.expanduser(self.sub(path))
        if path and not os.path.isabs(path) and self.base_dir:
            return os.path.join(self.base_dir, path)
        return path

    # ------------------------------------------------------------ actions
    def _exec(self, a: Action, labels: dict, counters: dict, pc: int, cycle: int, depth: int) -> str | None:
        k, p = a.kind, a.params
        s = self.s
        if k == "click":
            pos = self.pos(a)
            if pos is not None:
                w = int(p.get("wiggle", 0) or 0)
                if w:
                    pos = (pos[0] + random.randint(-w, w), pos[1] + random.randint(-w, w))
                if s.mouse_path in ("straight", "natural") and not s.filters.get("mouse_moves", True):
                    self.glide(pos, 0.25 * s.factor, s.mouse_path == "natural")
                self.move_to(pos)
            self.mouse.click(BUTTONS.get(p.get("button", "left"), mouse.Button.left), max(1, int(p.get("count", 1))))
        elif k in ("mouse_down", "mouse_up"):
            self.move_to(self.pos(a))
            b = BUTTONS.get(p.get("button", "left"), mouse.Button.left)
            if k == "mouse_down":
                self.mouse.press(b)
                self._held_buttons.add(b)
            else:
                self.mouse.release(b)
                self._held_buttons.discard(b)
        elif k == "mouse_move":
            pos = self.pos(a)
            if pos and s.mouse_path in ("straight", "natural"):
                self.glide(pos, 0.2 * s.factor, s.mouse_path == "natural")
            self.move_to(pos)
        elif k == "mouse_path":
            pts = p.get("points") or []
            if not pts:
                return None
            ox, oy = self.offset
            pts = [(int(q[0]) + ox, int(q[1]) + oy, int(q[2]) if len(q) > 2 else 0) for q in pts]
            mode = s.mouse_path
            if mode == "jump":
                self.move_to(pts[-1][:2])
            elif mode in ("straight", "natural"):
                self.glide(pts[-1][:2], max(0.05, pts[-1][2] / 1000 * s.factor), mode == "natural")
            else:
                t0 = time.perf_counter()
                for x, y, t in pts:
                    target = t0 + t / 1000 * s.factor
                    self.sleep(target - time.perf_counter())
                    self.mouse.position = (x, y)
        elif k == "scroll":
            self.move_to(self.pos(a))
            self.mouse.scroll(int(p.get("dx", 0) or 0), int(p.get("dy", 0) or 0))
        elif k == "type_text":
            text = self.sub(p.get("text", ""))
            if p.get("method") == "paste":
                old = system.get_clipboard()
                system.set_clipboard(text)
                self.sleep(0.05)
                self.tap(("cmd" if sys.platform == "darwin" else "ctrl") + "+v")
                self.sleep(0.25)
                system.set_clipboard(old)
            else:
                self.type_text(text, bool(p.get("human")))
        elif k == "key_press":
            self.tap(self.sub(p.get("combo", "")), int(self.num(p.get("count", 1), 1)))
        elif k in ("key_down", "key_up"):
            mods, key = keys.parse_combo(self.sub(p.get("combo", "")))
            key = self._vk(key)
            if k == "key_down":
                for m in mods + [key]:
                    self.kb.press(m)
                    self._held_keys.add(m)
            else:
                for m in [key] + list(reversed(mods)):
                    self.kb.release(m)
                    self._held_keys.discard(m)
        elif k == "wait":
            ms = self.num(p.get("ms", 0))
            if p.get("random"):
                hi = self.num(p.get("max_ms", ms))
                ms = random.uniform(min(ms, hi), max(ms, hi))
            self.sleep(ms / 1000 * s.factor)
        elif k == "wait_until":
            try:
                parts = [int(v) for v in self.sub(p.get("time", "")).split(":")]
                parts += [0] * (3 - len(parts))
                now = dt.datetime.now()
                target = now.replace(hour=parts[0], minute=parts[1], second=parts[2], microsecond=0)
                if target < now:
                    target += dt.timedelta(days=1)
            except ValueError:
                raise EngineError(f"Invalid time: {p.get('time')}", pc)
            while dt.datetime.now() < target:
                self.sleep(min(0.5, (target - dt.datetime.now()).total_seconds()))
        elif k == "wait_image":
            from . import screen
            want = p.get("appear", "appear") == "appear"
            sim = float(p.get("confidence", 90)) / 100
            ok = self.poll(lambda: (screen.find_image(p["image"], self.screen_region(a), sim)[0] is not None) == want,
                           self.num(p.get("timeout", 0)))
            if not ok:
                return self.fail(a, "Image wait timed out")
        elif k == "wait_text":
            from . import ocr, screen
            want = p.get("appear", "appear") == "appear"
            text = self.sub(p.get("text", ""))
            ok = self.poll(lambda: (ocr.find_text(screen.grab(self.screen_region(a)), text) is not None) == want,
                           self.num(p.get("timeout", 0)), 0.5)
            if not ok:
                return self.fail(a, "Text wait timed out")
        elif k == "wait_pixel":
            from . import screen
            pos = self.pos(a) or tuple(int(v) for v in self.mouse.position)
            color, tol = p.get("color", "#ffffff"), float(p.get("tolerance", 10) or 0)
            ok = self.poll(lambda: screen.color_distance(screen.pixel_color(*pos), color) <= tol,
                           self.num(p.get("timeout", 0)), 0.1)
            if not ok:
                return self.fail(a, "Pixel wait timed out")
        elif k == "wait_change":
            from . import screen
            region = self.screen_region(a)
            base = screen.grab(region).img
            thr = float(p.get("threshold", 2) or 0) / 100
            ok = self.poll(lambda: screen.changed_fraction(base, screen.grab(region).img) > thr,
                           self.num(p.get("timeout", 0)), 0.25)
            if not ok:
                return self.fail(a, "No screen change")
        elif k == "wait_file":
            path = self.resolve_path(p.get("path", ""))
            ev = p.get("event", "created")
            exists0, stamp0 = system.file_state(path)

            def test():
                ex, st = system.file_state(path)
                if ev == "created":
                    return ex
                if ev == "deleted":
                    return not ex
                return ex and (not exists0 or st != stamp0)
            if not self.poll(test, self.num(p.get("timeout", 0)), 0.25):
                return self.fail(a, "File wait timed out")
        elif k == "wait_window":
            title = self.sub(p.get("title", ""))

            def test():
                w = winmgr.active_window()
                return w is not None and w.matches("", title)
            if not self.poll(test, self.num(p.get("timeout", 0))):
                return self.fail(a, "Window wait timed out")
        elif k == "find_image":
            from . import screen
            sim = float(p.get("confidence", 90)) / 100
            found: list = []

            def test():
                pos, _ = screen.find_image(p["image"], self.screen_region(a), sim)
                if pos:
                    found.append(pos)
                return bool(pos)
            if not p.get("image"):
                raise EngineError("No image defined", pc)
            if self.poll(test, max(1, self.num(p.get("timeout", 0))), 0.25):
                return self.then(a, found[-1])
            return self.fail(a, "Image not found")
        elif k == "find_text":
            from . import ocr, screen
            text = self.sub(p.get("text", ""))
            found = []

            def test():
                pos = ocr.find_text(screen.grab(self.screen_region(a)), text)
                if pos:
                    found.append(pos)
                return bool(pos)
            if self.poll(test, max(1, self.num(p.get("timeout", 0))), 0.5):
                return self.then(a, found[-1])
            return self.fail(a, f"Text not found: {text}")
        elif k == "capture_text":
            from . import ocr, screen
            self.vars[p.get("var", "text")] = ocr.read_text(screen.grab(self.screen_region(a)))
        elif k == "capture_image":
            from . import screen
            shot = screen.grab(self.screen_region(a))
            png = screen.png_bytes(shot.img)
            if p.get("target") == "clipboard":
                system.set_clipboard_image(png)
            else:
                path = self.resolve_path(p.get("path", "screenshot.png"))
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(png)
                self.vars["last_screenshot"] = path
        elif k == "read_barcode":
            from . import screen
            codes = screen.read_codes(screen.grab(self.screen_region(a)).img)
            if codes:
                self.vars[p.get("var", "code")] = codes[0]
            else:
                return self.fail(a, "No barcode found")
        elif k == "get_pixel":
            from . import screen
            pos = self.pos(a) or tuple(int(v) for v in self.mouse.position)
            self.vars[p.get("var", "color")] = screen.pixel_color(*pos)
        elif k == "set_var":
            src, val, name = p.get("source", "value"), p.get("value", ""), p.get("var", "v")
            if src == "expr":
                self.vars[name] = str(evaluate(val, self.vars))
            elif src == "clipboard":
                self.vars[name] = system.get_clipboard()
            elif src == "mouse":
                x, y = self.mouse.position
                self.vars[name] = f"{int(x)},{int(y)}"
                self.vars[name + "_x"], self.vars[name + "_y"] = str(int(x)), str(int(y))
            elif src == "random":
                m = re.match(r"\s*(-?\d+)\s*[-–,]\s*(-?\d+)\s*$", self.sub(val))
                lo, hi = (int(m.group(1)), int(m.group(2))) if m else (0, 100)
                self.vars[name] = str(random.randint(min(lo, hi), max(lo, hi)))
            elif src == "input":
                ans = self.ui.ask_input(self.sub(val) or name)
                if ans is None:
                    raise Stop
                self.vars[name] = ans
            else:
                self.vars[name] = self.sub(val)
        elif k == "calc":
            self.vars[p.get("var", "n")] = str(evaluate(p.get("expr", ""), self.vars))
        elif k == "read_list":
            return self._read_list(a)
        elif k == "save_var":
            val = str(self.vars.get(p.get("var", ""), ""))
            if p.get("target") == "clipboard":
                system.set_clipboard(val)
            else:
                path = self.resolve_path(p.get("path", ""))
                with open(path, "a" if p.get("append", True) else "w", encoding="utf-8") as f:
                    f.write(val + ("\n" if p.get("append", True) else ""))
        elif k == "web_scrape":
            self.vars[p.get("var", "web")] = self._scrape(a)
        elif k == "goto":
            target = self.sub(p.get("target", ""))
            n = int(self.num(p.get("count", 0)))
            if n <= 0:
                return target
            c = counters.get(pc, 0)
            if c < n:
                counters[pc] = c + 1
                return target
            counters[pc] = 0          # loop finished; reset for the next time we get here
        elif k == "if":
            ok = compare(self.sub(p.get("left", "")), p.get("op", "=="), self.sub(p.get("right", "")))
            lbl = p.get("then_label") if ok else p.get("else_label")
            return self.sub(lbl) if lbl else None
        elif k == "run_macro":
            if depth >= 10:
                raise EngineError("Embedded macros nested too deeply", pc)
            path = self.resolve_path(p.get("path", ""))
            sub = Macro.load(path)
            old = self.base_dir, self.target, self.target_win, self.offset
            self.base_dir = os.path.dirname(os.path.abspath(path))
            if sub.target is not None:          # an embedded macro may work in its own window
                self.target, self.target_win = sub.target, None
            try:
                self._exec_list(sub.actions, cycle, 0, None, depth + 1)
            finally:
                self.base_dir, self.target, self.target_win, self.offset = old
        elif k == "launch":
            cmd = self.sub(p.get("command", ""))
            if not cmd:
                raise EngineError("No program given", pc)
            system.open_target(cmd, self.sub(p.get("args", "")), False)
            if p.get("wait", "window") == "window":
                name = self.sub(p.get("window", "")) or system.program_name(cmd)
                found: list = []

                def test():
                    win = winmgr.find_window("", name)
                    if win is not None:
                        found.append(win)
                    return win is not None
                if not self.poll(test, self.num(p.get("timeout", 30000)), 0.3):
                    return self.fail(a, f"Window did not appear: {name}")
                win = found[-1]
                winmgr.activate(win)
                if self.target is not None and win.matches(self.target.app, self.target.title):
                    self.target_win = winmgr.refresh(win) or win
                self.sleep(self.num(p.get("settle", 500)) / 1000)
        elif k == "execute":
            system.open_target(self.sub(p.get("command", "")), self.sub(p.get("args", "")), bool(p.get("wait")))
        elif k == "focus":
            app, title = self.sub(p.get("app", "")), self.sub(p.get("title", ""))
            found = []

            def test():
                w = winmgr.find_window(app, title)
                if w:
                    found.append(w)
                return w is not None
            if not self.poll(test, self.num(p.get("timeout", 5000)), 0.2):
                return self.fail(a, f"Window not found: {app} {title}".strip())
            w = found[-1]
            winmgr.activate(w)
            if p.get("rect") and (p.get("restore") or s.restore_windows):
                try:
                    winmgr.set_rect(w, [int(v) for v in str(p["rect"]).split(",")])
                except ValueError:
                    pass
            self.sleep(0.1)
        elif k == "message":
            ans = self.ui.message_box(self.sub(p.get("title", "")), self.sub(p.get("text", "")),
                                      p.get("buttons", "ok"))
            lbl = {"ok": p.get("yes_label"), "yes": p.get("yes_label"), "no": p.get("no_label"),
                   "cancel": p.get("cancel_label")}.get(ans)
            if ans == "cancel" and not lbl:
                raise Stop
            return self.sub(lbl) if lbl else None
        elif k == "notify":
            self.ui.notify(self.sub(p.get("text", "")), pc if depth == 0 else -1)
        elif k == "beep":
            system.beep()
        elif k == "clipboard":
            system.set_clipboard(self.sub(p.get("text", "")))
        elif k == "stop":
            raise Finish
        elif k in ("group", "group_end"):
            pass
        elif k == "ai_prompt":
            from . import ai
            self.vars[p.get("var", "ai")] = ai.chat(s.ai, self.sub(p.get("prompt", "")))
        elif k == "ai_image":
            from . import ai, screen
            f = self.resolve_path(p.get("file", "")) if p.get("file") else ""
            if f:
                with open(f, "rb") as fh:
                    png = fh.read()
            else:
                png = screen.png_bytes(screen.grab(self.screen_region(a)).img)
            self.vars[p.get("var", "ai")] = ai.chat(s.ai, self.sub(p.get("prompt", "")), png)
        elif k == "ai_find":
            from . import ai, screen
            shot = screen.grab(None)
            img = shot.img
            f = 1.0
            if img.shape[1] > 1600:                 # keep requests small
                import cv2
                f = 1600 / img.shape[1]
                img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            res = ai.find_object(s.ai, screen.png_bytes(img), img.shape[1], img.shape[0],
                                 self.sub(p.get("description", "")))
            if res is None:
                return self.fail(a, "AI did not find the object")
            return self.then(a, shot.to_logical(res[0] / f, res[1] / f))
        else:
            raise EngineError(f"Unknown action: {k}", pc)
        return None

    def _read_list(self, a: Action) -> str | None:
        p = a.params
        path = self.resolve_path(p.get("path", ""))
        key = f"{path}|{p.get('var')}"
        if key not in self._lists:
            with open(path, encoding="utf-8-sig") as f:
                lines = [ln.rstrip("\r\n") for ln in f if ln.strip()]
            self._lists[key] = (lines, 0)
        lines, idx = self._lists[key]
        if not lines:
            raise EngineError("List file is empty", self.current_index)
        if p.get("mode") == "random":
            self.vars[p.get("var", "line")] = random.choice(lines)
            return None
        if idx >= len(lines):
            end = p.get("end", "stop")
            if end == "restart":
                idx = 0
            elif end == "goto":
                self._lists[key] = (lines, 0)
                return self.sub(p.get("end_label", ""))
            else:
                raise Finish
        line = lines[idx]
        self.vars[p.get("var", "line")] = line
        # CSV columns are also available as {var_1}, {var_2}, ...
        if "," in line or ";" in line:
            import csv
            sep = ";" if line.count(";") > line.count(",") else ","
            for n, col in enumerate(next(csv.reader([line], delimiter=sep)), 1):
                self.vars[f"{p.get('var', 'line')}_{n}"] = col
        self.vars[p.get("var", "line") + "_index"] = str(idx + 1)
        self._lists[key] = (lines, idx + 1)
        return None

    def _scrape(self, a: Action) -> str:
        p = a.params
        req = urllib.request.Request(self.sub(p.get("url", "")),
                                     headers={"User-Agent": "Mozilla/5.0 (ActionsRecorder)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            html = r.read().decode(charset, "replace")
        method, pattern = p.get("method", "regex"), self.sub(p.get("pattern", ""))
        if method == "text":
            import html as h
            text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
            text = h.unescape(re.sub(r"<[^>]+>", " ", text))
            return re.sub(r"\s+", " ", text).strip()
        if method == "xpath":
            try:
                import lxml.html
            except ImportError:
                raise EngineError("XPath needs the 'lxml' package (pip install lxml)", self.current_index)
            res = lxml.html.fromstring(html).xpath(pattern)
            if not res:
                return ""
            r0 = res[0]
            return r0.text_content().strip() if hasattr(r0, "text_content") else str(r0)
        m = re.search(pattern, html, re.S | re.I)
        if not m:
            return ""
        return m.group(1) if m.groups() else m.group(0)

    # --------------------------------------------------- input guards
    def _start_listeners(self, s: PlaySettings) -> None:
        self._listeners = []
        if s.abort_on_key or s.block_keys:
            kwargs = {}
            holder: dict = {}

            def on_press(key, injected=False):
                if not injected and s.abort_on_key:
                    self.stop()
            if s.block_keys:
                if sys.platform.startswith("win"):
                    def flt(msg, data):
                        if not (data.flags & 0x10) and "l" in holder:   # not injected -> swallow
                            if s.abort_on_key:
                                self.stop()
                            holder["l"].suppress_event()
                        return True
                    kwargs["win32_event_filter"] = flt
                elif sys.platform == "darwin":
                    import Quartz
                    me = os.getpid()

                    def intercept(event_type, event):
                        src = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID)
                        if src == me:
                            return event
                        if s.abort_on_key:
                            self.stop()
                        return None
                    kwargs["darwin_intercept"] = intercept
            lst = keyboard.Listener(on_press=on_press, **kwargs)
            holder["l"] = lst
            lst.daemon = True
            lst.start()
            self._listeners.append(lst)
        if s.abort_on_mouse:
            def on_move(x, y, injected=False):
                if not injected:
                    self.stop()
            lst = mouse.Listener(on_move=on_move)
            lst.daemon = True
            lst.start()
            self._listeners.append(lst)

    def _stop_listeners(self) -> None:
        for lst in self._listeners:
            try:
                lst.stop()
            except Exception:
                pass
        self._listeners = []

    def _release_all(self) -> None:
        for k in list(self._held_keys):
            try:
                self.kb.release(k)
            except Exception:
                pass
        self._held_keys.clear()
        for b in list(self._held_buttons):
            try:
                self.mouse.release(b)
            except Exception:
                pass
        self._held_buttons.clear()

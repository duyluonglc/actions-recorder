import json
import os
import tempfile
import time
import unittest

from pynput import keyboard, mouse

from macrorecorder import keys
from macrorecorder.actions import CATALOG, Action
from macrorecorder.engine import Engine, EngineUI, PlaySettings
from macrorecorder.expr import compare, evaluate, substitute
from macrorecorder.macro import Macro, hidden_rows, optimize, scale_waits
from macrorecorder.recorder import Raw, RecordSettings, build_actions, strip_trailing_click


class FakeMouse:
    def __init__(self, log):
        self.log = log
        self._pos = (0, 0)

    @property
    def position(self):
        return self._pos

    @position.setter
    def position(self, p):
        self._pos = (int(p[0]), int(p[1]))
        self.log.append(("move", self._pos))

    def press(self, b): self.log.append(("press", b))
    def release(self, b): self.log.append(("release", b))
    def click(self, b, n=1): self.log.append(("click", b, n, self._pos))
    def scroll(self, dx, dy): self.log.append(("scroll", dx, dy))


class FakeKeyboard:
    def __init__(self, log):
        self.log = log

    def press(self, k): self.log.append(("kdown", k))
    def release(self, k): self.log.append(("kup", k))
    def type(self, s): self.log.append(("type", s))


class UI(EngineUI):
    def __init__(self, answer="ok"):
        self.answer = answer
        self.done = None
        self.notes = []
        self.progressed = []

    def progress(self, i, c): self.progressed.append(i)
    def message_box(self, t, x, b): return self.answer
    def notify(self, text, i): self.notes.append(text)
    def finished(self, ok, err): self.done = (ok, err)


def run(actions, settings=None, ui=None, **kw):
    ui = ui or UI()
    log = []
    e = Engine(ui)
    e.mouse, e.kb = FakeMouse(log), FakeKeyboard(log)
    e.play(Macro(actions), settings or PlaySettings(), **kw)
    e.wait(10)
    return e, ui, log


class TestExpr(unittest.TestCase):
    def test_substitute(self):
        self.assertEqual(substitute("a {x} {{y}} {nope}", {"x": 5}), "a 5 {y} {nope}")
        self.assertEqual(len(substitute("{date}", {})), 10)

    def test_evaluate(self):
        v = {"n": "4", "s": "ab"}
        self.assertEqual(evaluate("{n} * 2 + 1", v), 9)
        self.assertEqual(evaluate("n / 8", v), 0.5)
        self.assertEqual(evaluate("{s} + 'c'", v), "abc")
        self.assertEqual(evaluate("max(1, {n}, 3)", v), 4)
        self.assertEqual(evaluate("dist(0,0,3,4)", v), 5)
        self.assertTrue(evaluate("{n} > 3 and {n} < 5", v))
        with self.assertRaises(ValueError):
            evaluate("__import__('os')", v)

    def test_compare(self):
        self.assertTrue(compare("10", ">", "9"))          # numeric, not string
        self.assertTrue(compare("Hello", "contains", "ell"))
        self.assertTrue(compare(" ", "empty", ""))
        self.assertFalse(compare("a", "==", "b"))


class TestKeys(unittest.TestCase):
    def test_combo(self):
        mods, k = keys.parse_combo("ctrl+shift+s")
        self.assertEqual(mods, [keyboard.Key.ctrl, keyboard.Key.shift])
        self.assertEqual(k, keyboard.KeyCode.from_char("s"))
        self.assertEqual(keys.parse_combo("enter")[1], keyboard.Key.enter)
        self.assertEqual(keys.parse_combo("ctrl++")[1], keyboard.KeyCode.from_char("+"))
        self.assertEqual(keys.parse_combo("vk:65")[1], keyboard.KeyCode.from_vk(65))
        self.assertFalse(keys.valid_combo("foo+x"))
        self.assertEqual(keys.parse_hotkey("Ctrl+R"), (frozenset({"ctrl"}), "r"))
        self.assertEqual(keys.base_token("Key.ctrl_l"), "ctrl")


class TestMacro(unittest.TestCase):
    def test_roundtrip_all_kinds(self):
        m = Macro([Action.new(k) for k in CATALOG])
        m.actions[0].label, m.actions[0].comment, m.actions[1].enabled = "start", "hi", False
        m2 = Macro.from_json(m.to_json())
        self.assertEqual([a.to_dict() for a in m.actions], [a.to_dict() for a in m2.actions])
        for a in m2.actions:
            self.assertIsInstance(a.describe(), str)

    def test_v1_conversion(self):
        v1 = {"events": [{"kind": "mouse_click", "delay": 500, "x": 1, "y": 2, "button": "left"},
                         {"kind": "key_press", "key": "Key.enter"}, {"kind": "type_text", "text": "hi"}]}
        m = Macro.from_json(json.dumps(v1))
        self.assertEqual([a.kind for a in m.actions], ["wait", "click", "key_press", "type_text"])
        self.assertEqual(m.actions[2].params["combo"], "enter")

    def test_groups_and_optimize(self):
        acts = [Action.new("group", collapsed=True), Action.new("wait", ms="5"), Action.new("group_end"),
                Action.new("wait", ms="100"), Action.new("wait", ms="200")]
        self.assertEqual(hidden_rows(acts), {1, 2})
        out = optimize(acts[3:], max_wait_ms=250)
        self.assertEqual([a.params["ms"] for a in out], ["250"])
        self.assertEqual(scale_waits(acts[3:], 0.5)[1].params["ms"], "100")

    def test_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.csv")
            Macro([Action.new("click", x=1, y=2)]).export_csv(p)
            with open(p, encoding="utf-8-sig") as f:
                self.assertIn("Mouse click", f.read())


def R(t, kind, **d):
    return Raw(t, kind, d)


class TestBuilder(unittest.TestCase):
    def build(self, raw, **kw):
        return build_actions(raw, RecordSettings(**kw))

    def test_click_double_and_wait(self):
        raw = [R(0, "move", x=0, y=0), R(20, "move", x=50, y=0), R(40, "move", x=100, y=0),
               R(1000, "down", x=100, y=0, button="left"), R(1050, "up", x=100, y=0, button="left"),
               R(1150, "down", x=100, y=0, button="left"), R(1200, "up", x=100, y=0, button="left")]
        acts = self.build(raw)
        self.assertEqual([a.kind for a in acts], ["mouse_path", "wait", "click"])
        self.assertEqual(acts[0].params["points"][-1], [100, 0, 40])
        self.assertEqual(acts[1].params["ms"], "960")
        self.assertEqual(acts[2].params["count"], 2)

    def test_focus_change_inside_click(self):
        # the window switch caused by the click arrives between press and release
        raw = [R(0, "down", x=420, y=245, button="left"), R(40, "focus", app="Safari", title="x", rect=""),
               R(60, "up", x=420, y=245, button="left")]
        acts = self.build(raw)
        self.assertEqual([a.kind for a in acts], ["click", "focus"])

    def test_no_paths(self):
        raw = [R(0, "move", x=0, y=0), R(20, "move", x=50, y=0),
               R(30, "down", x=50, y=0, button="right"), R(60, "up", x=50, y=0, button="right")]
        acts = self.build(raw, record_paths=False)
        self.assertEqual([a.kind for a in acts], ["click"])
        self.assertEqual(acts[0].params["button"], "right")

    def test_drag(self):
        raw = [R(0, "down", x=0, y=0, button="left"), R(100, "move", x=50, y=50), R(200, "move", x=90, y=90),
               R(300, "up", x=90, y=90, button="left")]
        acts = self.build(raw, record_paths=False, min_wait_ms=1000)
        self.assertEqual([a.kind for a in acts], ["mouse_down", "mouse_path", "mouse_up"])

    def test_text_and_combo(self):
        raw = [R(0, "kdown", key="H"), R(10, "kup", key="H"), R(50, "kdown", key="i"), R(60, "kup", key="i"),
               R(2000, "kdown", key="Key.ctrl_l"), R(2050, "kdown", key="Key.ctrl_l"),
               R(2100, "kdown", key="vk:8", vk=8), R(2150, "kup", key="vk:8", vk=8), R(2200, "kup", key="Key.ctrl_l"),
               R(2300, "kdown", key="Key.enter"), R(2310, "kup", key="Key.enter"),
               R(2320, "kdown", key="Key.enter"), R(2330, "kup", key="Key.enter")]
        acts = self.build(raw)
        self.assertEqual([a.kind for a in acts], ["type_text", "wait", "key_press", "wait", "key_press"])
        self.assertEqual(acts[0].params["text"], "Hi")
        import sys
        if sys.platform == "darwin":
            self.assertEqual(acts[2].params["combo"], "ctrl+c")    # mac vk 8 = 'c'
        self.assertEqual((acts[4].params["combo"], acts[4].params["count"]), ("enter", 2))

    def test_shift_tab_hold_and_ctrl_click(self):
        raw = [R(0, "kdown", key="Key.shift"), R(10, "kdown", key="Key.tab"), R(20, "kup", key="Key.tab"),
               R(30, "kup", key="Key.shift"),
               R(500, "kdown", key="w"), R(1500, "kup", key="w"),
               R(2000, "kdown", key="Key.ctrl"), R(2050, "down", x=5, y=5, button="left"),
               R(2080, "up", x=5, y=5, button="left"), R(2100, "kup", key="Key.ctrl")]
        acts = self.build(raw, min_wait_ms=10000)
        self.assertEqual([(a.kind, a.params.get("combo")) for a in acts],
                         [("key_press", "shift+tab"), ("key_down", "w"), ("key_up", "w"),
                          ("key_down", "ctrl"), ("click", None), ("key_up", "ctrl")])

    def test_strip_ui_click_and_hotkey_modifier(self):
        raw = [R(0, "kup", key="Key.ctrl"), R(10, "kdown", key="a"), R(20, "kup", key="a"),
               R(500, "kdown", key="Key.ctrl"),                       # ctrl of the stop hotkey
               R(600, "move", x=1, y=1), R(700, "down", x=1, y=1, button="left"),
               R(750, "up", x=1, y=1, button="left")]
        acts = build_actions(strip_trailing_click(raw), RecordSettings())
        self.assertEqual([a.kind for a in acts], ["type_text"])


class TestEngine(unittest.TestCase):
    def test_basic_and_speed(self):
        acts = [Action.new("click", x=10, y=20, count=2), Action.new("wait", ms="200"),
                Action.new("key_press", combo="ctrl+a"), Action.new("type_text", text="ok"),
                Action.new("scroll", dy=-2)]
        t = time.perf_counter()
        e, ui, log = run(acts, PlaySettings(speed_pct=200))
        self.assertLess(time.perf_counter() - t, 1.5)   # generous for slow CI machines
        self.assertEqual(ui.done, (True, None))
        self.assertIn(("click", mouse.Button.left, 2, (10, 20)), log)
        self.assertIn(("kdown", keyboard.Key.ctrl), log)
        self.assertEqual([x[1] for x in log if x[0] == "type"], ["o", "k"])

    def test_loop_vars_if(self):
        acts = [Action.new("set_var", var="n", value="0"),
                Action.new("calc", var="n", expr="{n} + 1"),
                Action.new("goto", target="top", count="4"),
                Action.new("if", left="{n}", op="==", right="5", then_label="yes", else_label="no"),
                Action.new("notify", text="no"),
                Action.new("stop"),
                Action.new("notify", text="n={n}")]
        acts[1].label = "top"
        acts[4].label = "no"
        acts[6].label = "yes"
        e, ui, log = run(acts)
        self.assertEqual(ui.done, (True, None))
        self.assertEqual(ui.notes, ["n=5"])
        self.assertEqual(e.vars["n"], "5")

    def test_message_box_branch_and_disabled_and_filters(self):
        acts = [Action.new("message", buttons="yesno", yes_label="Y", no_label="N"),
                Action.new("notify", text="Y"), Action.new("stop"),
                Action.new("notify", text="N"), Action.new("mouse_move", x=1, y=1),
                Action.new("notify", text="disabled")]
        acts[1].label, acts[3].label = "Y", "N"
        acts[5].enabled = False
        s = PlaySettings()
        s.filters["mouse_moves"] = False
        e, ui, log = run(acts, s, UI(answer="no"))
        self.assertEqual(ui.notes, ["N"])
        self.assertNotIn(("move", (1, 1)), log)

    def test_read_list_csv_and_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.csv")
            with open(p, "w") as f:
                f.write("a,1\nb,2\n")
            acts = [Action.new("read_list", path=p, var="row", end="stop"), Action.new("notify", text="{row_1}")]
            e, ui, _ = run(acts, PlaySettings(repeat=0))
            self.assertEqual(ui.notes, ["a", "b"])
            self.assertEqual(ui.done, (True, None))

    def test_embed_and_save_var(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "sub.macro")
            Macro([Action.new("set_var", var="x", value="from sub")]).save(sub)
            out = os.path.join(d, "out.txt")
            acts = [Action.new("run_macro", path=sub), Action.new("save_var", var="x", path=out)]
            e, ui, _ = run(acts, PlaySettings(repeat=2))
            with open(out) as f:
                self.assertEqual(f.read(), "from sub\nfrom sub\n")

    def test_missing_label_reports_error(self):
        e, ui, _ = run([Action.new("goto", target="nowhere")])
        self.assertFalse(ui.done[0])
        self.assertIn("nowhere", ui.done[1])

    def test_stop_releases_keys(self):
        ui = UI()
        log = []
        e = Engine(ui)
        e.mouse, e.kb = FakeMouse(log), FakeKeyboard(log)
        e.play(Macro([Action.new("key_down", combo="shift"), Action.new("wait", ms="5000")]), PlaySettings())
        time.sleep(0.2)
        e.stop()
        e.wait(2)
        self.assertIn(("kup", keyboard.Key.shift), log)
        self.assertEqual(ui.done, (False, None))

    def test_relative_and_path_modes(self):
        acts = [Action.new("mouse_path", points=[[100, 100, 0], [110, 100, 30], [120, 100, 60]])]
        log = []
        e = Engine(UI())
        e.mouse, e.kb = FakeMouse(log), FakeKeyboard(log)
        e.mouse._pos = (0, 0)
        e.play(Macro(acts), PlaySettings(relative=True, mouse_path="jump"))
        e.wait(5)
        self.assertEqual([x[1] for x in log if x[0] == "move"], [(20, 0)])


if __name__ == "__main__":
    unittest.main()


class FakeWindows:
    """Stand-in for macrorecorder.winmgr: one window that can move / appear later."""

    def __init__(self, rect=(100, 50, 800, 600), app="Notepad", title="notes.txt", appear_after=0.0):
        from macrorecorder.winmgr import WinInfo
        self.win = WinInfo(app, title, rect, handle=1, pid=4242, wid=7)
        self.active = False
        self.activations = 0
        self.t0 = time.monotonic()
        self.appear_after = appear_after

    def install(self, test):
        from macrorecorder import winmgr
        for name in ("find_window", "refresh", "is_active", "activate"):
            orig = getattr(winmgr, name)
            setattr(winmgr, name, getattr(self, name))
            test.addCleanup(setattr, winmgr, name, orig)

    def visible(self):
        return time.monotonic() - self.t0 >= self.appear_after

    def find_window(self, app="", title=""):
        return self.win if self.visible() and self.win.matches(app, title) else None

    def refresh(self, w):
        return self.win if self.visible() else None

    def is_active(self, w):
        return self.active

    def activate(self, w):
        self.active = True
        self.activations += 1
        return True


class TestTargetWindow(unittest.TestCase):
    def test_relative_click_and_activation(self):
        from macrorecorder.macro import Target
        fw = FakeWindows(rect=(100, 50, 800, 600))
        fw.install(self)
        m = Macro([Action.new("click", x=10, y=20), Action.new("set_var", var="a", value="1"),
                   Action.new("click", x=30, y=40)], target=Target("Notepad"))
        ui, log = UI(), []
        e = Engine(ui)
        e.mouse, e.kb = FakeMouse(log), FakeKeyboard(log)
        fw.win.rect = (100, 50, 800, 600)
        e.play(m, PlaySettings())
        time.sleep(0.05)
        e.wait(10)
        self.assertEqual(ui.done, (True, None))
        clicks = [x for x in log if x[0] == "click"]
        self.assertEqual(clicks[0][3], (110, 70))           # window origin + relative position
        self.assertEqual(clicks[1][3], (130, 90))
        self.assertEqual(fw.activations, 1)                  # activated once, then it stays in front

    def test_window_moved_between_steps(self):
        from macrorecorder.macro import Target
        fw = FakeWindows(rect=(0, 0, 500, 500))
        fw.install(self)
        fw.active = True

        class MoveUI(UI):
            def progress(self, i, c):
                if i == 1:
                    fw.win.rect = (300, 200, 500, 500)
        log = []
        e = Engine(MoveUI())
        e.mouse, e.kb = FakeMouse(log), FakeKeyboard(log)
        e.play(Macro([Action.new("click", x=5, y=5), Action.new("click", x=5, y=5)], target=Target("Notepad")),
               PlaySettings())
        e.wait(10)
        self.assertEqual([x[3] for x in log if x[0] == "click"], [(5, 5), (305, 205)])

    def test_missing_target_window_fails_clearly(self):
        from macrorecorder.macro import Target
        fw = FakeWindows(appear_after=99)
        fw.install(self)
        ui = UI()
        e = Engine(ui)
        e.mouse, e.kb = FakeMouse([]), FakeKeyboard([])
        e.play(Macro([Action.new("click", x=1, y=1)], target=Target("Notepad", timeout_ms=300)), PlaySettings())
        e.wait(10)
        self.assertFalse(ui.done[0])
        self.assertIn("Target window not found", ui.done[1])

    def test_launch_waits_for_window(self):
        from macrorecorder import system
        fw = FakeWindows(appear_after=0.6, app="TextEdit", title="Untitled")
        fw.install(self)
        launched = []
        orig = system.open_target
        system.open_target = lambda c, a="", w=False: launched.append((c, a))
        self.addCleanup(setattr, system, "open_target", orig)
        ui, log = UI(), []
        e = Engine(ui)
        e.mouse, e.kb = FakeMouse(log), FakeKeyboard(log)
        t = time.monotonic()
        e.play(Macro([Action.new("launch", command="/Applications/TextEdit.app", settle="0"),
                      Action.new("notify", text="ready")]), PlaySettings())
        e.wait(10)
        self.assertEqual(ui.done, (True, None))
        self.assertEqual(launched, [("/Applications/TextEdit.app", "")])
        self.assertGreaterEqual(time.monotonic() - t, 0.55)   # waited for the window
        self.assertEqual(fw.activations, 1)
        self.assertEqual(ui.notes, ["ready"])

    def test_launch_timeout_jumps_to_marker(self):
        from macrorecorder import system
        fw = FakeWindows(appear_after=99)
        fw.install(self)
        orig = system.open_target
        system.open_target = lambda *a, **k: None
        self.addCleanup(setattr, system, "open_target", orig)
        acts = [Action.new("launch", command="foo", timeout="300", on_fail="goto", fail_label="nope"),
                Action.new("notify", text="started"), Action.new("stop"), Action.new("notify", text="failed")]
        acts[3].label = "nope"
        ui = UI()
        e = Engine(ui)
        e.mouse, e.kb = FakeMouse([]), FakeKeyboard([])
        e.play(Macro(acts), PlaySettings())
        e.wait(10)
        self.assertEqual(ui.notes, ["failed"])

    def test_target_roundtrip_and_shift(self):
        from macrorecorder.macro import Target, shift_positions
        m = Macro([Action.new("click", x=110, y=70),
                   Action.new("mouse_path", points=[[100, 50, 0], [120, 60, 30]]),
                   Action.new("find_image", region=[100, 50, 40, 40]), Action.new("click")],
                  target=Target("Chrome", "Orders", activate=False))
        m2 = Macro.from_json(m.to_json())
        self.assertEqual(m2.target.to_dict(), m.target.to_dict())
        rel = shift_positions(m2.actions, -100, -50)
        self.assertEqual((rel[0].params["x"], rel[0].params["y"]), (10, 20))
        self.assertEqual(rel[1].params["points"], [[0, 0, 0], [20, 10, 30]])
        self.assertEqual(rel[2].params["region"], [0, 0, 40, 40])
        self.assertIsNone(rel[3].params.get("x"))          # "current position" stays as it is


class TestRecorderTarget(unittest.TestCase):
    def test_positions_recorded_relative_to_window(self):
        from macrorecorder.macro import Target
        from macrorecorder.recorder import InputHub
        fw = FakeWindows(rect=(200, 100, 800, 600))
        fw.install(self)
        hub = InputHub()
        hub.start_recording(RecordSettings(record_focus=False), Target("Notepad"))
        try:
            hub._on_click(250, 130, mouse.Button.left, True)
            hub._on_click(250, 130, mouse.Button.left, False)
        finally:
            acts = hub.stop_recording()
        self.assertEqual([(a.kind, a.params.get("x"), a.params.get("y")) for a in acts], [("click", 50, 30)])

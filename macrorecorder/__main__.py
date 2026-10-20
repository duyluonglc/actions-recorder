"""Entry point.

    macrorecorder                      open the GUI
    macrorecorder file.macro           open the GUI with a macro loaded
    macrorecorder --minimized          start in the tray (used by "Start on login")
    macrorecorder --play file.macro    play a macro without the GUI (Esc aborts)
"""

from __future__ import annotations

import argparse
import os
import sys


def _play_headless(args) -> int:
    if sys.platform.startswith("win"):
        try:   # use real pixel coordinates on scaled displays
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    from pynput import keyboard

    from .engine import Engine, EngineUI, PlaySettings
    from .macro import Macro

    result = {}

    class ConsoleUI(EngineUI):
        def notify(self, text, index):
            print(text)

        def message_box(self, title, text, buttons):
            print(f"[{title}] {text}")
            return "yes" if buttons.startswith("yes") else "ok"

        def ask_input(self, prompt):
            try:
                return input(prompt + ": ")
            except EOFError:
                return None

        def finished(self, completed, error):
            result["ok"], result["error"] = completed, error

    macro = Macro.load(args.play)
    eng = Engine(ConsoleUI())
    s = PlaySettings(speed_pct=args.speed * 100, repeat=args.repeat, relative=args.relative)
    if args.skip_moves:
        s.filters["mouse_moves"] = False
    try:
        from .gui.store import Store
        s.ai = Store().ai_config()
    except Exception:
        pass
    esc = keyboard.Listener(on_press=lambda k, *a: eng.stop() if k == keyboard.Key.esc else None)
    esc.daemon = True
    esc.start()
    print(f"Playing {args.play} ({len(macro)} actions, repeat={args.repeat or 'forever'}, "
          f"speed={args.speed}x). Press Esc to stop.")
    eng.play(macro, s, base_dir=os.path.dirname(os.path.abspath(args.play)))
    try:
        while eng.playing:
            eng.wait(0.2)
    except KeyboardInterrupt:
        eng.stop()
        eng.wait()
    if result.get("error"):
        print("Error:", result["error"], file=sys.stderr)
        return 1
    if result.get("ok") and args.after:
        from .system import after_playback
        after_playback(args.after)
    return 0


def _self_test(out_path: str | None) -> int:
    """Check that the (packaged) app can load everything. Used by CI and for support requests."""
    import platform
    import traceback

    from . import __version__
    lines = [f"Actions Recorder {__version__}", f"OS: {platform.platform()} ({platform.machine()})",
             f"Python: {sys.version.split()[0]}  frozen={getattr(sys, 'frozen', False)}"]
    ok = True

    def check(name: str, fn, required: bool = True):
        nonlocal ok
        try:
            detail = fn()
            lines.append(f"[ok]   {name}" + (f": {detail}" if detail else ""))
        except Exception as e:
            lines.append(f"[{'FAIL' if required else 'warn'}] {name}: {type(e).__name__}: {e}")
            if required:
                ok = False
                lines.append(traceback.format_exc())

    from importlib import import_module

    def qt():
        import_module("PySide6.QtWidgets")
        return import_module("PySide6").__version__

    def cv():
        import cv2
        import numpy
        return f"opencv {cv2.__version__}, numpy {numpy.__version__}"

    def inputs():
        import_module("pynput.keyboard")
        import_module("pynput.mouse")
        return ""

    def core():
        from .actions import Action
        from .engine import Engine, EngineUI, PlaySettings
        from .macro import Macro
        res = {}

        class UI(EngineUI):
            def finished(self, completed, error):
                res["r"] = (completed, error)
        e = Engine(UI())
        e.play(Macro([Action.new("set_var", var="a", value="20"), Action.new("calc", var="b", expr="{a} * 2 + 2")]),
               PlaySettings())
        e.wait(10)
        if res.get("r") != (True, None) or e.vars.get("b") != "42":
            raise RuntimeError(f"engine result {res.get('r')} vars {e.vars}")
        return "engine ok"

    def screen():
        from . import screen as scr
        return f"capture scale {scr.grab([0, 0, 4, 4]).scale:g}"

    def ocr_engine():
        if sys.platform == "darwin":
            import_module("Vision")
            return "Apple Vision"
        if sys.platform.startswith("win"):
            from winrt.windows.media.ocr import OcrEngine
            eng = OcrEngine.try_create_from_user_profile_languages()
            return "Windows OCR" + ("" if eng is not None else " (no OCR language installed)")
        import_module("pytesseract")
        return "tesseract"

    check("Qt (PySide6)", qt)
    check("OpenCV", cv)
    check("pynput", inputs)
    check("macro engine", core)
    check("screen capture", screen, required=False)
    check("text recognition", ocr_engine, required=False)
    lines.append("RESULT: " + ("OK" if ok else "FAILED"))
    text = "\n".join(lines)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="macrorecorder", description="Record and replay mouse & keyboard macros.")
    ap.add_argument("file", nargs="?", help="macro file to open")
    ap.add_argument("--play", metavar="FILE", help="play FILE without opening the window")
    ap.add_argument("--repeat", type=int, default=1, help="repetitions for --play (0 = forever)")
    ap.add_argument("--speed", type=float, default=1.0, help="speed multiplier for --play")
    ap.add_argument("--skip-moves", action="store_true", help="--play: ignore mouse movements")
    ap.add_argument("--relative", action="store_true", help="--play: relative to cursor position")
    ap.add_argument("--after", choices=["lock", "sleep", "logout", "restart", "shutdown"],
                    help="--play: do this after a successful playback")
    ap.add_argument("--minimized", action="store_true", help="start minimized to the tray")
    ap.add_argument("--self-test", nargs="?", const="", metavar="REPORT_FILE",
                    help="check that all components load, print (or write) a report and exit")
    args = ap.parse_args(argv)
    if args.self_test is not None:
        return _self_test(args.self_test or None)
    if args.play:
        return _play_headless(args)
    from .gui.main_window import run
    return run(args.file, args.minimized)


if __name__ == "__main__":
    sys.exit(main())

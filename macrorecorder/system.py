"""OS helpers: clipboard, launching programs, beep, post-playback actions,
start-on-login."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")


# ------------------------------------------------------------------ clipboard
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _u = ctypes.WinDLL("user32", use_last_error=True)
    _k = ctypes.WinDLL("kernel32", use_last_error=True)
    _u.GetClipboardData.restype = wintypes.HANDLE
    _u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    _u.SetClipboardData.restype = wintypes.HANDLE
    _u.OpenClipboard.argtypes = [wintypes.HWND]
    _k.GlobalAlloc.restype = wintypes.HGLOBAL
    _k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _k.GlobalLock.restype = wintypes.LPVOID
    _k.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    def _open():
        import time
        for _ in range(20):
            if _u.OpenClipboard(None):
                return True
            time.sleep(0.02)
        return False

    def _set(fmt: int, data: bytes) -> None:
        if not _open():
            raise OSError("Clipboard busy")
        try:
            _u.EmptyClipboard()
            h = _k.GlobalAlloc(0x0002, len(data))
            p = _k.GlobalLock(h)
            ctypes.memmove(p, data, len(data))
            _k.GlobalUnlock(h)
            _u.SetClipboardData(fmt, h)
        finally:
            _u.CloseClipboard()

    def get_clipboard() -> str:
        if not _open():
            return ""
        try:
            h = _u.GetClipboardData(13)
            if not h:
                return ""
            p = _k.GlobalLock(h)
            try:
                return ctypes.wstring_at(p)
            finally:
                _k.GlobalUnlock(h)
        finally:
            _u.CloseClipboard()

    def set_clipboard(text: str) -> None:
        _set(13, (text + "\0").encode("utf-16-le"))

    def set_clipboard_image(png: bytes) -> None:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        ok, bmp = cv2.imencode(".bmp", img)
        _set(8, bmp.tobytes()[14:])          # CF_DIB = BMP without file header

elif IS_MAC:
    def get_clipboard() -> str:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        v = NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)
        return str(v) if v is not None else ""

    def set_clipboard(text: str) -> None:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)

    def set_clipboard_image(png: bytes) -> None:
        from AppKit import NSPasteboard, NSPasteboardTypePNG
        from Foundation import NSData
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setData_forType_(NSData.dataWithBytes_length_(png, len(png)), NSPasteboardTypePNG)

else:  # pragma: no cover
    def get_clipboard() -> str:
        try:
            return subprocess.run(["xclip", "-o", "-selection", "clipboard"], capture_output=True,
                                  text=True).stdout
        except OSError:
            return ""

    def set_clipboard(text: str) -> None:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True)

    def set_clipboard_image(png: bytes) -> None:
        subprocess.run(["xclip", "-selection", "clipboard", "-t", "image/png"], input=png)


# --------------------------------------------------------------------- launch

def open_target(command: str, args: str = "", wait: bool = False) -> int | None:
    """Run a program, or open a file / URL with its default application."""
    command = command.strip()
    extra = shlex.split(args, posix=not IS_WIN) if args else []
    is_url = "://" in command or command.startswith("mailto:")
    if IS_MAC and command.rstrip("/").endswith(".app"):
        argv = ["open", "-a", command] + (["-W"] if wait else []) + (["--args"] + extra if extra else [])
    elif is_url or (os.path.exists(command) and not _is_program(command)):
        # documents, folders and URLs open with their default application
        if IS_WIN and not wait:
            os.startfile(command)  # type: ignore[attr-defined]
            return None
        argv = (["cmd", "/c", "start", "/wait", "", command] if IS_WIN else
                ["open"] + (["-W"] if wait else []) + [command] if IS_MAC else ["xdg-open", command])
    elif os.path.exists(command) or shutil.which(command):
        argv = [command] + extra
    elif IS_MAC:
        # a bare application name such as "Calculator" or "Google Chrome"
        argv = ["open", "-a", command] + (["-W"] if wait else []) + (["--args"] + extra if extra else [])
    elif IS_WIN and not wait:
        # names registered under "App Paths" (chrome, excel, …) are found by the shell
        os.startfile(command, arguments=args) if args else os.startfile(command)  # type: ignore[attr-defined]
        return None
    else:
        argv = [command] + extra
    p = subprocess.Popen(argv)
    return p.wait() if wait else None


def program_name(command: str) -> str:
    """Best guess of the application / process name a command starts
    (``/Applications/Google Chrome.app`` → ``Google Chrome``, ``C:\\x\\notepad.exe`` → ``notepad``)."""
    c = command.strip().strip('"').rstrip("/\\")
    if "://" in c:
        return ""
    base = re.split(r"[\\/]", c)[-1]
    for ext in (".app", ".exe", ".lnk", ".bat", ".cmd"):
        if base.lower().endswith(ext):
            return base[:-len(ext)]
    return base


def _is_program(path: str) -> bool:
    if IS_WIN:
        return path.lower().endswith((".exe", ".bat", ".cmd", ".com"))
    return os.path.isfile(path) and os.access(path, os.X_OK)


def beep() -> None:
    if IS_WIN:
        import winsound
        winsound.MessageBeep()
    elif IS_MAC:
        try:
            from AppKit import NSBeep
            NSBeep()
        except Exception:
            sys.stdout.write("\a")
    else:
        sys.stdout.write("\a")
        sys.stdout.flush()


# --------------------------------------------------------- after playback

AFTER_ACTIONS = [("none", "No action"), ("close", "Close Actions Recorder"), ("lock", "Lock computer"),
                 ("sleep", "Stand-by / sleep"), ("logout", "Log out"), ("restart", "Restart"),
                 ("shutdown", "Shut down")]


def after_playback(action: str) -> None:
    if action in ("none", "close", ""):
        return
    if IS_WIN:
        cmds = {
            "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
            "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "logout": ["shutdown", "/l"],
            "restart": ["shutdown", "/r", "/t", "0"],
            "shutdown": ["shutdown", "/s", "/t", "0"],
        }
    elif IS_MAC:
        se = 'tell application "System Events" to '
        cmds = {
            "lock": ["osascript", "-e", se + 'keystroke "q" using {control down, command down}'],
            "sleep": ["pmset", "sleepnow"],
            "logout": ["osascript", "-e", se + "log out"],
            "restart": ["osascript", "-e", se + "restart"],
            "shutdown": ["osascript", "-e", se + "shut down"],
        }
    else:
        cmds = {"lock": ["loginctl", "lock-session"], "sleep": ["systemctl", "suspend"],
                "logout": ["loginctl", "terminate-user", os.environ.get("USER", "")],
                "restart": ["systemctl", "reboot"], "shutdown": ["systemctl", "poweroff"]}
    if action in cmds:
        subprocess.Popen(cmds[action])


# ----------------------------------------------------------- start on login

def _launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        exe = sys.executable
        if IS_MAC and ".app/Contents/MacOS/" in exe:
            return ["open", "-a", exe.split(".app/")[0] + ".app", "--args", "--minimized"]
        return [exe, "--minimized"]
    return [sys.executable, "-m", "macrorecorder", "--minimized"]


def set_start_on_login(enabled: bool) -> None:
    if IS_WIN:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                             winreg.KEY_SET_VALUE)
        try:
            if enabled:
                cmd = subprocess.list2cmdline(_launch_command())
                winreg.SetValueEx(key, "ActionsRecorder", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, "ActionsRecorder")
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    elif IS_MAC:
        import plistlib
        path = os.path.expanduser("~/Library/LaunchAgents/com.actionsrecorder.app.plist")
        if enabled:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                plistlib.dump({"Label": "com.actionsrecorder.app", "ProgramArguments": _launch_command(),
                               "RunAtLoad": True}, f)
        elif os.path.exists(path):
            os.remove(path)


def file_state(path: str) -> tuple[bool, float]:
    try:
        st = os.stat(path)
        return True, st.st_mtime + st.st_size * 1e-9
    except OSError:
        return False, 0.0

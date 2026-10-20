"""Window management: which window is active, bring a window to the front,
move/resize it. Implemented for Windows (user32 via ctypes) and macOS
(AppKit / Quartz / System Events)."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class WinInfo:
    app: str
    title: str
    rect: tuple[int, int, int, int] | None = None   # x, y, w, h
    handle: object = None                           # hwnd (Windows) / pid (macOS)
    pid: int = 0

    def matches(self, app: str = "", title: str = "") -> bool:
        if app and app.lower() not in self.app.lower():
            return False
        if title and title.lower() not in (self.title or "").lower() \
                and title.lower() not in self.app.lower():
            return False
        return True


# ===================================================================== Windows
if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.BOOL]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _info(hwnd) -> WinInfo:
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = ""
        h = kernel32.OpenProcess(0x1000, False, pid.value)
        if h:
            size = wintypes.DWORD(1024)
            pbuf = ctypes.create_unicode_buffer(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
                app = os.path.splitext(os.path.basename(pbuf.value))[0]
            kernel32.CloseHandle(h)
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return WinInfo(app, buf.value, (r.left, r.top, r.right - r.left, r.bottom - r.top), hwnd, pid.value)

    def active_window() -> WinInfo | None:
        hwnd = user32.GetForegroundWindow()
        return _info(hwnd) if hwnd else None

    def list_windows() -> list[WinInfo]:
        out = []

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                out.append(_info(hwnd))
            return True
        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return out

    def activate(w: WinInfo) -> bool:
        hwnd = w.handle
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        # pressing Alt lets a background process take the foreground
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))

    def set_rect(w: WinInfo, rect) -> None:
        x, y, ww, hh = rect
        user32.MoveWindow(w.handle, int(x), int(y), int(ww), int(hh), True)

# ======================================================================= macOS
elif sys.platform == "darwin":

    def _cg_windows():
        import Quartz
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        return Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []

    def _rect(d) -> tuple[int, int, int, int] | None:
        b = d.get("kCGWindowBounds")
        if not b:
            return None
        return int(b["X"]), int(b["Y"]), int(b["Width"]), int(b["Height"])

    def active_window() -> WinInfo | None:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        pid = app.processIdentifier()
        name = str(app.localizedName() or "")
        for d in _cg_windows():
            if d.get("kCGWindowOwnerPID") == pid and d.get("kCGWindowLayer", 0) == 0:
                return WinInfo(name, str(d.get("kCGWindowName") or ""), _rect(d), pid, pid)
        return WinInfo(name, "", None, pid, pid)

    def list_windows() -> list[WinInfo]:
        out = []
        for d in _cg_windows():
            if d.get("kCGWindowLayer", 0) != 0:
                continue
            out.append(WinInfo(str(d.get("kCGWindowOwnerName") or ""), str(d.get("kCGWindowName") or ""),
                               _rect(d), d.get("kCGWindowOwnerPID"), d.get("kCGWindowOwnerPID") or 0))
        return out

    def _osa(script: str) -> None:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)

    def activate(w: WinInfo) -> bool:
        from AppKit import NSRunningApplication
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(w.handle)
        if app is None:
            return False
        ok = bool(app.activateWithOptions_(1 << 1))     # NSApplicationActivateIgnoringOtherApps
        if w.title:
            t = w.title.replace('"', '\\"')
            n = w.app.replace('"', '\\"')
            _osa(f'tell application "System Events" to tell process "{n}" to '
                 f'perform action "AXRaise" of (first window whose name contains "{t}")')
        return ok

    def set_rect(w: WinInfo, rect) -> None:
        x, y, ww, hh = [int(v) for v in rect]
        n = w.app.replace('"', '\\"')
        _osa(f'tell application "System Events" to tell process "{n}" to tell window 1\n'
             f'set position to {{{x}, {y}}}\nset size to {{{ww}, {hh}}}\nend tell')

# ======================================================================= other
else:  # pragma: no cover
    def active_window():
        return None

    def list_windows():
        return []

    def activate(w):
        return False

    def set_rect(w, rect):
        pass


def find_window(app: str = "", title: str = "") -> WinInfo | None:
    act = active_window()
    if act and act.matches(app, title):
        return act
    for w in list_windows():
        if w.matches(app, title):
            return w
    return None


__all__ = ["WinInfo", "active_window", "list_windows", "activate", "set_rect", "find_window"]

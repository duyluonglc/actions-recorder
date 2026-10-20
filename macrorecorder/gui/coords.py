"""Conversion between Qt widget coordinates and the input coordinates used by
pynput / mss ("native").

* macOS: both use points, so they are identical.
* Windows (per-monitor DPI aware): Qt keeps each screen's native top-left but
  divides sizes by the scale factor; native = top_left + local * dpr.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication, QScreen

SCALED = sys.platform.startswith("win")


def _factor(screen: QScreen) -> float:
    return screen.devicePixelRatio() if SCALED else 1.0


def native_rect(screen: QScreen) -> tuple[int, int, int, int]:
    g = screen.geometry()
    f = _factor(screen)
    return g.x(), g.y(), int(round(g.width() * f)), int(round(g.height() * f))


def to_native(screen: QScreen, p: QPoint) -> tuple[int, int]:
    g = screen.geometry()
    f = _factor(screen)
    return int(round(g.x() + (p.x() - g.x()) * f)), int(round(g.y() + (p.y() - g.y()) * f))


def screen_for_native(x: int, y: int) -> QScreen:
    for s in QGuiApplication.screens():
        nx, ny, nw, nh = native_rect(s)
        if nx <= x < nx + nw and ny <= y < ny + nh:
            return s
    return QGuiApplication.primaryScreen()


def to_qt(x: int, y: int) -> QPoint:
    s = screen_for_native(x, y)
    g = s.geometry()
    f = _factor(s)
    return QPoint(int(round(g.x() + (x - g.x()) / f)), int(round(g.y() + (y - g.y()) / f)))


def rect_to_qt(x: int, y: int, w: int, h: int) -> QRect:
    f = _factor(screen_for_native(x, y))
    p = to_qt(x, y)
    return QRect(p.x(), p.y(), max(1, int(round(w / f))), max(1, int(round(h / f))))

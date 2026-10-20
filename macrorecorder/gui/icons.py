"""Icons drawn in code (no image assets needed)."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF

PLAY = QColor("#7cc6a0")
RECORD = QColor("#f08c8c")
STOP = QColor("#a9d3f0")
PAUSE = QColor("#f5c26b")


def _canvas(size: int = 64):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    return pm, p


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    pm, p = _canvas()
    if name == "play":
        p.setPen(QPen(PLAY.darker(150), 2))
        p.setBrush(PLAY)
        p.drawPolygon(QPolygonF([QPointF(14, 8), QPointF(58, 32), QPointF(14, 56)]))
    elif name == "record":
        p.setPen(QPen(RECORD.darker(150), 2))
        p.setBrush(RECORD)
        p.drawEllipse(QRectF(8, 8, 48, 48))
    elif name == "stop":
        p.setPen(QPen(STOP.darker(150), 2))
        p.setBrush(STOP)
        p.drawRect(QRectF(10, 10, 44, 44))
    elif name == "pause":
        p.setPen(QPen(PAUSE.darker(150), 2))
        p.setBrush(PAUSE)
        p.drawRect(QRectF(12, 10, 14, 44))
        p.drawRect(QRectF(38, 10, 14, 44))
    elif name == "mouse":
        from PySide6.QtGui import QGuiApplication, QPalette
        fg = QGuiApplication.palette().color(QPalette.WindowText)
        p.setPen(QPen(fg, 3.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(16, 6, 32, 52), 16, 16)
        p.drawLine(QPointF(16, 26), QPointF(48, 26))
        p.drawLine(QPointF(32, 6), QPointF(32, 26))
        p.setBrush(QColor("#3e8ee8"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(18, 8, 13, 17), 6, 6)
    elif name == "app":
        paint_app(p)
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=None)
def glyph(text: str, color: str = "") -> QIcon:
    """Icon from an emoji / symbol. Plain symbols take the theme's text color."""
    pm, p = _canvas()
    f = QFont()
    f.setPixelSize(46)
    p.setFont(f)
    if not color:
        from PySide6.QtGui import QGuiApplication, QPalette
        color = QGuiApplication.palette().color(QPalette.WindowText).name()
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, 64, 64), Qt.AlignCenter, text)
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=None)
def arrow_file(color: str) -> str:
    """Small ▾ arrow as a PNG file (style sheets can only load images from files)."""
    import os
    import tempfile
    path = os.path.join(tempfile.gettempdir(), f"actionsrecorder_arrow_{color.lstrip('#')}.png")
    pm = QPixmap(20, 20)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon(QPolygonF([QPointF(4, 7), QPointF(16, 7), QPointF(10, 14)]))
    p.end()
    pm.save(path)
    return path.replace("\\", "/")


def paint_app(p: QPainter) -> None:
    """Actions Recorder logo on a 64×64 canvas: violet tile, white pointer with a dotted trail."""
    from PySide6.QtGui import QLinearGradient
    g = QLinearGradient(0, 0, 64, 64)
    g.setColorAt(0, QColor("#7c6cf2"))
    g.setColorAt(1, QColor("#4b3bc4"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 15, 15)
    p.setBrush(QColor(255, 255, 255, 150))
    for i, (x, y) in enumerate(((13, 47), (19, 41), (25, 35))):
        r = 2.2 + i * 0.6
        p.drawEllipse(QPointF(x, y), r, r)
    p.setBrush(QColor("white"))
    p.drawPolygon(QPolygonF([QPointF(30, 14), QPointF(52, 33), QPointF(42, 34), QPointF(47, 45),
                             QPointF(42, 47), QPointF(37, 36), QPointF(30, 42)]))
    p.setBrush(QColor("#ff5a5f"))
    p.drawEllipse(QPointF(49, 15), 5, 5)


def app_pixmap(size: int) -> QPixmap:
    """The logo rendered sharply at any size (for .icns / .ico files)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 64, size / 64)
    paint_app(p)
    p.end()
    return pm

"""On-screen helpers: area/point picker, action markers, floating status bar."""

from __future__ import annotations

from PySide6.QtCore import QEventLoop, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from .. import screen as scr
from ..i18n import tr
from . import coords
from .icons import icon


# ------------------------------------------------------------------ picker

class _PickWindow(QWidget):
    done = Signal(object)

    def __init__(self, qscreen, shot: scr.Shot, mode: str):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.qscreen, self.shot, self.mode = qscreen, shot, mode
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(qscreen.geometry())
        img = shot.img
        h, w = img.shape[:2]
        self.pix = QPixmap.fromImage(QImage(img.data, w, h, img.strides[0], QImage.Format_BGR888).copy())
        self.start: QPoint | None = None
        self.cur = QPoint()

    def showEvent(self, e):
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.done.emit(None)

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.done.emit(None)
            return
        self.start = e.position().toPoint()
        self.cur = self.start
        if self.mode in ("point", "color"):
            self._finish()

    def mouseMoveEvent(self, e):
        self.cur = e.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, e):
        if self.mode == "region" and self.start is not None:
            self.cur = e.position().toPoint()
            r = QRect(self.start, self.cur).normalized()
            if r.width() > 3 and r.height() > 3:
                self._finish()
            else:
                self.start = None
                self.update()

    def _native(self, p: QPoint) -> tuple[int, int]:
        return coords.to_native(self.qscreen, p + self.qscreen.geometry().topLeft())

    def _finish(self):
        if self.mode == "region":
            r = QRect(self.start, self.cur).normalized()
            x0, y0 = self._native(r.topLeft())
            x1, y1 = self._native(r.bottomRight())
            self.done.emit({"rect": [x0, y0, x1 - x0 + 1, y1 - y0 + 1]})
        else:
            x, y = self._native(self.cur)
            crop = self.shot.crop_logical(x, y, 1, 1)
            color = "#000000"
            if crop.size:
                b, g, r = crop[0, 0][:3]
                color = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
            self.done.emit({"pos": [x, y], "color": color})

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.pix)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))
        pen = QPen(QColor("#ff3b30"), 2)
        if self.mode == "region" and self.start is not None:
            r = QRect(self.start, self.cur).normalized()
            src = QRect(int(r.x() * self.pix.width() / self.width()), int(r.y() * self.pix.height() / self.height()),
                        int(r.width() * self.pix.width() / self.width()),
                        int(r.height() * self.pix.height() / self.height()))
            p.drawPixmap(r, self.pix, src)
            p.setPen(pen)
            p.drawRect(r)
        else:
            p.setPen(QPen(QColor(255, 59, 48, 160), 1))
            p.drawLine(0, self.cur.y(), self.width(), self.cur.y())
            p.drawLine(self.cur.x(), 0, self.cur.x(), self.height())
        p.setPen(Qt.white)
        hint = {"region": tr("Drag to select an area — Esc to cancel"),
                "point": tr("Click a position — Esc to cancel"),
                "color": tr("Click to pick a color — Esc to cancel")}[self.mode]
        nx, ny = self._native(self.cur)
        p.fillRect(QRect(10, 10, 430, 26), QColor(0, 0, 0, 170))
        p.drawText(QRect(16, 10, 430, 26), Qt.AlignVCenter, f"{hint}   ({nx}, {ny})")


def pick(mode: str, hide: list[QWidget] | None = None):
    """Let the user pick on screen. mode: region / point / color.

    Returns ``{"rect": [x,y,w,h], "shot": Shot}`` / ``{"pos": [x,y], "color": "#rrggbb"}``
    in native coordinates, or None when cancelled."""
    # Make our windows invisible without hide(): hiding a dialog that runs
    # exec() would end its event loop and close it.
    hidden = [w for w in (hide or []) if w is not None and w.isVisible()]
    for w in hidden:
        w.setWindowOpacity(0.0)
    QApplication.processEvents()
    loop = QEventLoop()
    QTimer.singleShot(250, loop.quit)       # let windows disappear before the screenshot
    loop.exec()
    result: dict = {}
    windows = []
    shots = {}
    try:
        for s in QGuiApplication.screens():
            shot = scr.grab(list(coords.native_rect(s)))
            shots[s] = shot
            w = _PickWindow(s, shot, mode)
            windows.append(w)
        loop = QEventLoop()

        def finish(val, src=None):
            if val is not None:
                result.update(val)
            loop.quit()
        for w in windows:
            w.done.connect(finish)
            w.show()
        loop.exec()
    finally:
        for w in windows:
            w.close()
        for w in hidden:
            w.setWindowOpacity(1.0)
            w.raise_()
            w.activateWindow()
    if not result:
        return None
    if "rect" in result:
        x, y = result["rect"][:2]
        s = coords.screen_for_native(x, y)
        result["shot"] = shots.get(s) or scr.grab(result["rect"])
    return result


# ---------------------------------------------------------------- markers

class Marker(QWidget):
    """Transparent click-through marker showing where an action acts."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.kind = "point"
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def show_point(self, x: int, y: int, ms: int = 0) -> None:
        self.kind = "point"
        p = coords.to_qt(x, y)
        self.setGeometry(p.x() - 22, p.y() - 22, 45, 45)
        self._show(ms)

    def show_rect(self, x: int, y: int, w: int, h: int, ms: int = 0) -> None:
        self.kind = "rect"
        self.setGeometry(coords.rect_to_qt(x, y, w, h).adjusted(-3, -3, 3, 3))
        self._show(ms)

    def _show(self, ms: int) -> None:
        self.show()
        self.raise_()
        self.update()
        if ms:
            self.hide_timer.start(ms)
        else:
            self.hide_timer.stop()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#ff3b30"), 3))
        if self.kind == "point":
            p.drawEllipse(self.rect().adjusted(4, 4, -4, -4))
            c = self.rect().center()
            p.drawLine(c.x() - 6, c.y(), c.x() + 6, c.y())
            p.drawLine(c.x(), c.y() - 6, c.x(), c.y() + 6)
        else:
            p.drawRect(self.rect().adjusted(2, 2, -2, -2))


# ---------------------------------------------------------- status overlay

class StatusBar(QFrame):
    stop_clicked = Signal()
    pause_clicked = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setObjectName("status")
        self.setStyleSheet("#status{background:rgba(28,30,38,235);border-radius:10px;}"
                           "QLabel{color:white;font-weight:600;padding:0 6px;}"
                           "QToolButton{border:none;padding:4px;border-radius:6px;}"
                           "QToolButton:hover{background:rgba(255,255,255,40);}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self.label = QLabel()
        self.label.setMinimumWidth(220)
        self.pause_btn = QToolButton()
        self.pause_btn.setIcon(icon("pause"))
        self.pause_btn.clicked.connect(self.pause_clicked)
        self.stop_btn = QToolButton()
        self.stop_btn.setIcon(icon("stop"))
        self.stop_btn.clicked.connect(self.stop_clicked)
        for w in (self.label, self.pause_btn, self.stop_btn):
            lay.addWidget(w)
        self._drag = None
        self._placed = False

    def show_text(self, text: str) -> None:
        self.label.setText(text)
        if not self.isVisible():
            self.adjustSize()
            if not self._placed:
                g = QGuiApplication.primaryScreen().availableGeometry()
                self.move(g.right() - self.width() - 24, g.top() + 24)
                self._placed = True
            self.show()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

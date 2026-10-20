"""Render README screenshots with a clean demo macro (no personal data).

    python tools/screenshots.py            # writes docs/screenshots/*.png (macOS look when run on a Mac)

Windows are rendered off-screen, so nothing appears on your desktop.
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "screenshots")

from PySide6.QtCore import QPoint, QRectF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from macrorecorder.actions import Action  # noqa: E402
from macrorecorder.gui import main_window as mw  # noqa: E402
from macrorecorder.gui import onboarding  # noqa: E402
from macrorecorder.gui.settings_dialog import SettingsDialog  # noqa: E402
from macrorecorder.gui.store import Store  # noqa: E402
from macrorecorder.i18n import set_language  # noqa: E402


def pump(sec=0.25):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


DEMO_VI = {"bring the browser to the front": "đưa trình duyệt lên trước",
           "Fill in the order form": "Điền form đơn hàng", "New order": "Đơn mới",
           "wait until the form is loaded": "chờ form tải xong", "save": "lưu",
           "Order {row_1} needs approval ({total})": "Đơn {row_1} cần duyệt ({total})",
           "Orders – Admin": "Đơn hàng – Quản trị"}


def demo_macro(lang: str = "en") -> list[Action]:
    def t(text: str) -> str:
        return DEMO_VI.get(text, text) if lang == "vi" else text

    def a(kind, label="", comment="", **p):
        p = {k: t(v) if isinstance(v, str) else v for k, v in p.items()}
        comment = t(comment)
        act = Action.new(kind, **p)
        act.label, act.comment = label, comment
        return act
    return [
        a("focus", app="Google Chrome", title="Orders – Admin", comment="bring the browser to the front"),
        a("read_list", label="next_row", path="orders.csv", var="row", end="stop"),
        a("group", name="Fill in the order form", color="#6d5ae6"),
        a("find_text", text="New order", then="click", timeout="5000"),
        a("wait_image", appear="appear", timeout="10000",
          image=None, comment="wait until the form is loaded"),
        a("click", x=640, y=312),
        a("type_text", text="{row_1}"),
        a("key_press", combo="tab"),
        a("type_text", text="{row_2}", human=True),
        a("group_end"),
        a("calc", var="total", expr="{row_3} * 1.1"),
        a("if", left="{total}", op=">", right="1000", then_label="approval", else_label=""),
        a("key_press", combo="ctrl+s", comment="save"),
        a("wait", ms="800", random=True, max_ms="1500"),
        a("goto", target="next_row"),
        a("notify", label="approval", text="Order {row_1} needs approval ({total})"),
    ]


def framed(img: QImage, title: str, dark: bool) -> QImage:
    """Put a rendered window into a macOS-like frame with a soft shadow."""
    bar, pad, radius = 30, 36, 12
    w, h = img.width(), img.height()
    dpr = img.devicePixelRatio() or 1.0
    lw, lh = w / dpr, h / dpr
    out = QImage(int((lw + pad * 2) * dpr), int((lh + bar + pad * 2) * dpr), QImage.Format_ARGB32_Premultiplied)
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(pad, pad, lw, lh + bar)
    for i in range(14, 0, -1):                       # shadow
        c = QColor(0, 0, 0, int(5 + (14 - i) * 1.2))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(rect.adjusted(-i, -i + 6, i, i + 6), radius + i, radius + i)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.setClipPath(path)
    p.fillRect(rect, QColor("#2b2c31") if dark else QColor("#ececee"))
    for i, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        p.setBrush(QColor(col))
        p.drawEllipse(QRectF(pad + 14 + i * 20, pad + 9, 12, 12))
    f = QFont()
    f.setPointSizeF(12.5)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#b9bac1") if dark else QColor("#4a4b52"))
    p.drawText(QRectF(pad, pad, lw, bar), Qt.AlignCenter, title)
    p.drawImage(QRectF(pad, pad + bar, lw, lh), img)
    p.end()
    return out


def grab(widget) -> QImage:
    # an off-screen window may get a top "safe area" margin from macOS; leave it out
    top = widget.contentsMargins().top()
    if top:
        from PySide6.QtCore import QRect
        return widget.grab(QRect(0, top, widget.width(), widget.height() - top)).toImage()
    return widget.grab().toImage()


def save(img: QImage, name: str):
    os.makedirs(OUT, exist_ok=True)
    img.save(os.path.join(OUT, name))
    print("wrote", name)


def shoot(lang: str, theme: str):
    set_language(lang)
    mw.install_qt_translator(app)
    mw.apply_theme(app, theme)
    dark = theme == "dark"
    suffix = f"{lang}-{theme}"
    tmp = tempfile.mkdtemp()
    store = Store(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
    store.set("ui/tray", False)
    store.set("ui/onboarded", True)
    store.set("ui/start_login", False)
    mw.MainWindow.check_permissions = lambda self, force=False: None
    mw.MainWindow._run_startup_entries = lambda self: None
    w = mw.MainWindow(store)
    w.hub.stop()
    w.sched_timer.stop()
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.resize(1320, 760)
    w.move(200, 200)
    w.show()
    pump()

    # empty state
    save(framed(grab(w), "Actions Recorder", dark), f"empty-{suffix}.png")

    # main window with the demo macro, a step selected
    w.path = os.path.join(tmp, "orders.macro")
    w.set_actions(demo_macro(lang), [6], undoable=False)
    w.dirty = False
    w.refresh()
    pump()
    save(framed(grab(w), "orders.macro — Actions Recorder", dark), f"main-{suffix}.png")

    # run options popup composited onto the window
    w.select_rows([3])
    pump()
    pop = w.run_options
    pop.setAttribute(Qt.WA_DontShowOnScreen)
    pop.adjustSize()
    pop.show()
    pump()
    base = grab(w)
    painter = QPainter(base)
    anchor = w.header.options.mapTo(w, QPoint(0, w.header.options.height() + 4)) - QPoint(0, w.contentsMargins().top())
    painter.drawImage(anchor, grab(pop))
    painter.end()
    pop.hide()
    save(framed(base, "orders.macro — Actions Recorder", dark), f"run-options-{suffix}.png")

    # preferences
    sd = SettingsDialog(store, w, 2)
    sd.setAttribute(Qt.WA_DontShowOnScreen)
    sd.show()
    pump()
    save(framed(grab(sd), sd.windowTitle(), dark), f"preferences-{suffix}.png")
    sd.close()

    # first-run permissions (macOS) — shown as a user who still has to allow two permissions
    onboarding.mac_permission_status = lambda: {"accessibility": True, "input": False, "screen": False}
    sw = onboarding.SetupDialog(store, w)
    sw.setAttribute(Qt.WA_DontShowOnScreen)
    sw.show()
    pump()
    save(framed(grab(sw), sw.windowTitle(), dark), f"setup-{suffix}.png")
    if hasattr(sw, "timer"):
        sw.timer.stop()
    sw.close()
    w._quitting = True
    w.close()


if __name__ == "__main__":
    if len(sys.argv) == 3:
        shoot(sys.argv[1], sys.argv[2])
    else:
        # one process per variant: macOS' native menu bar does not like several
        # main windows being created and destroyed in the same process
        import subprocess
        for lang, theme in (("en", "dark"), ("en", "light"), ("vi", "dark")):
            subprocess.run([sys.executable, os.path.abspath(__file__), lang, theme], check=True)

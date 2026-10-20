"""Render the app logo to assets/ (icon.png, icon.ico, and icon.icns on macOS).

Run with:  python tools/make_icons.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication([])
from macrorecorder.gui.icons import app_pixmap  # noqa: E402

out = os.path.join(ROOT, "assets")
os.makedirs(out, exist_ok=True)
app_pixmap(1024).save(os.path.join(out, "icon.png"))
app_pixmap(256).save(os.path.join(out, "icon.ico"), "ICO")
if sys.platform == "darwin":
    tmp = tempfile.mkdtemp()
    iconset = os.path.join(tmp, "icon.iconset")
    os.makedirs(iconset)
    for s in (16, 32, 128, 256, 512):
        app_pixmap(s).save(os.path.join(iconset, f"icon_{s}x{s}.png"))
        app_pixmap(s * 2).save(os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(out, "icon.icns")], check=True)
    shutil.rmtree(tmp)
print("icons written to", out)

"""Screen capture and image analysis (OpenCV + mss).

All public coordinates are *logical* screen coordinates (the ones pynput uses).
Screenshots may be at a higher pixel density (Retina / HiDPI); ``Shot`` keeps
the scale so results can be mapped back.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def _mss():
    import mss
    return mss.MSS() if hasattr(mss, "MSS") else mss.mss()


@dataclass
class Shot:
    img: np.ndarray          # BGR
    left: int                # logical origin
    top: int
    scale: float             # pixels per logical unit

    def to_logical(self, px: float, py: float) -> tuple[int, int]:
        return int(round(self.left + px / self.scale)), int(round(self.top + py / self.scale))

    def crop_logical(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        s = self.scale
        x0, y0 = int((x - self.left) * s), int((y - self.top) * s)
        return self.img[max(0, y0):max(0, y0) + int(h * s), max(0, x0):max(0, x0) + int(w * s)]


def desktop_rect() -> tuple[int, int, int, int]:
    with _mss() as m:
        mon = m.monitors[0]
        return mon["left"], mon["top"], mon["width"], mon["height"]


def grab(region=None) -> Shot:
    """Capture ``region`` = [x, y, w, h] (logical) or the whole virtual desktop."""
    with _mss() as m:
        if region:
            x, y, w, h = [int(v) for v in region]
            mon = {"left": x, "top": y, "width": max(1, w), "height": max(1, h)}
        else:
            mon = dict(m.monitors[0])
        raw = m.grab(mon)
        img = np.asarray(raw)[:, :, :3].copy()     # BGRA -> BGR
        scale = raw.size[0] / mon["width"] if mon["width"] else 1.0
        return Shot(img, mon["left"], mon["top"], scale)


# ---------------------------------------------------------------- encoding

def encode_image(img: np.ndarray, scale: float) -> dict:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("PNG encoding failed")
    return {"png": base64.b64encode(buf.tobytes()).decode("ascii"), "scale": scale,
            "w": int(img.shape[1]), "h": int(img.shape[0])}


def decode_image(data: dict) -> tuple[np.ndarray, float]:
    raw = base64.b64decode(data["png"])
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    return img, float(data.get("scale", 1.0))


def png_bytes(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


# ------------------------------------------------------------------ search

def find_image(template: dict, region=None, similarity: float = 0.9, shot: Shot | None = None):
    """Locate ``template`` on screen. Returns ((x, y) logical centre, score) or (None, best)."""
    tmpl, tscale = decode_image(template)
    shot = shot or grab(region)
    if abs(tscale - shot.scale) > 0.01:
        f = shot.scale / tscale
        tmpl = cv2.resize(tmpl, (max(1, int(tmpl.shape[1] * f)), max(1, int(tmpl.shape[0] * f))),
                          interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)
    hay = shot.img
    if tmpl.shape[0] > hay.shape[0] or tmpl.shape[1] > hay.shape[1]:
        return None, 0.0
    res = cv2.matchTemplate(hay, tmpl, cv2.TM_CCOEFF_NORMED)
    _, best, _, loc = cv2.minMaxLoc(res)
    if best < similarity:
        return None, float(best)
    cx, cy = loc[0] + tmpl.shape[1] / 2, loc[1] + tmpl.shape[0] / 2
    return shot.to_logical(cx, cy), float(best)


def pixel_color(x: int, y: int) -> str:
    shot = grab([x, y, 1, 1])
    b, g, r = shot.img[0, 0][:3]
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def color_distance(c1: str, c2: str) -> float:
    def rgb(c):
        c = c.lstrip("#")
        return [int(c[i:i + 2], 16) for i in (0, 2, 4)]
    a, b = rgb(c1), rgb(c2)
    return max(abs(a[i] - b[i]) for i in range(3))


def changed_fraction(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return 1.0
    diff = cv2.absdiff(a, b)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    return float(np.count_nonzero(gray > 24)) / gray.size


def read_codes(img: np.ndarray) -> list[str]:
    """Decode QR codes and 1-D barcodes in an image."""
    out: list[str] = []
    try:
        ok, texts, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(img)
        if ok:
            out += [t for t in texts if t]
    except Exception:
        pass
    try:
        if hasattr(cv2, "barcode"):
            res = cv2.barcode.BarcodeDetector().detectAndDecode(img)
            texts = res[1] if len(res) >= 2 else []
            if isinstance(texts, str):
                texts = [texts]
            out += [t for t in texts if t]
    except Exception:
        pass
    return out

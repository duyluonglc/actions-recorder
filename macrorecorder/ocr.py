"""Text recognition using the OS engine: Apple Vision on macOS, Windows.Media.Ocr
on Windows. Falls back to Tesseract (pytesseract) when installed."""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np

from .screen import Shot, png_bytes


@dataclass
class Box:
    text: str
    x: float
    y: float
    w: float
    h: float
    words: list | None = None       # list[Box] when the engine gives word boxes
    finder: object = None           # engine-specific substring locator


class OCRUnavailable(RuntimeError):
    pass


_language = ""


def set_language(lang: str) -> None:
    """BCP-47 tag such as ``en-US`` or ``vi-VN``; empty = system default."""
    global _language
    _language = lang or ""


def _prep(img: np.ndarray) -> tuple[np.ndarray, float]:
    import cv2
    h = img.shape[0]
    if h < 60:      # tiny regions recognise far better when enlarged
        f = 60 / max(1, h)
        f = min(f, 4.0)
        return cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC), f
    return img, 1.0


# ------------------------------------------------------------------- macOS

def _mac(img: np.ndarray) -> list[Box]:
    import Vision
    from Foundation import NSData, NSMakeRange
    data = png_bytes(img)
    ns = NSData.dataWithBytes_length_(data, len(data))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(ns, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    if _language:
        req.setRecognitionLanguages_([_language])
    try:
        req.setAutomaticallyDetectsLanguage_(not _language)
    except Exception:
        pass
    handler.performRequests_error_([req], None)
    h, w = img.shape[:2]
    out: list[Box] = []

    def conv(bb):
        return (bb.origin.x * w, (1 - bb.origin.y - bb.size.height) * h, bb.size.width * w, bb.size.height * h)

    for obs in req.results() or []:
        cands = obs.topCandidates_(1)
        if not cands:
            continue
        cand = cands[0]
        text = str(cand.string())

        def finder(start, length, cand=cand):
            r, _ = cand.boundingBoxForRange_error_(NSMakeRange(start, length), None)
            return conv(r.boundingBox()) if r is not None else None

        out.append(Box(text, *conv(obs.boundingBox()), finder=finder))
    return out


# ----------------------------------------------------------------- Windows

def _win(img: np.ndarray) -> list[Box]:
    import asyncio

    import cv2
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    async def run():
        bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        h, w = bgra.shape[:2]
        writer = DataWriter()
        writer.write_bytes(bgra.tobytes())
        bmp = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8, w, h)
        engine = None
        if _language:
            from winrt.windows.globalization import Language
            engine = OcrEngine.try_create_from_language(Language(_language))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise OCRUnavailable("No OCR language installed in Windows")
        return await engine.recognize_async(bmp)

    res = asyncio.run(run())
    out: list[Box] = []
    for line in res.lines:
        words = []
        for wd in line.words:
            r = wd.bounding_rect
            words.append(Box(wd.text, r.x, r.y, r.width, r.height))
        if not words:
            continue
        x0 = min(b.x for b in words)
        y0 = min(b.y for b in words)
        x1 = max(b.x + b.w for b in words)
        y1 = max(b.y + b.h for b in words)
        out.append(Box(line.text, x0, y0, x1 - x0, y1 - y0, words=words))
    return out


# --------------------------------------------------------------- tesseract

def _tess(img: np.ndarray) -> list[Box]:
    import pytesseract
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    lines: dict = {}
    for i, t in enumerate(d["text"]):
        if not t.strip():
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        lines.setdefault(key, []).append(Box(t, d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
    out = []
    for words in lines.values():
        x0 = min(b.x for b in words)
        y0 = min(b.y for b in words)
        x1 = max(b.x + b.w for b in words)
        y1 = max(b.y + b.h for b in words)
        out.append(Box(" ".join(b.text for b in words), x0, y0, x1 - x0, y1 - y0, words=words))
    return out


def recognize(img: np.ndarray) -> list[Box]:
    """OCR an image. Returns line boxes in the image's pixel coordinates."""
    big, f = _prep(img)
    engines = []
    if sys.platform == "darwin":
        engines.append(_mac)
    elif sys.platform.startswith("win"):
        engines.append(_win)
    engines.append(_tess)
    last = None
    for eng in engines:
        try:
            boxes = eng(big)
            break
        except ImportError as e:
            last = e
            continue
    else:
        raise OCRUnavailable(f"No OCR engine available ({last})")
    if f != 1.0:
        for b in boxes:
            b.x, b.y, b.w, b.h = b.x / f, b.y / f, b.w / f, b.h / f
            for wd in b.words or []:
                wd.x, wd.y, wd.w, wd.h = wd.x / f, wd.y / f, wd.w / f, wd.h / f
            if b.finder:
                orig = b.finder
                b.finder = (lambda s, n, orig=orig:
                            (lambda r: tuple(v / f for v in r) if r else None)(orig(s, n)))
    return boxes


def read_text(shot: Shot) -> str:
    return "\n".join(b.text for b in recognize(shot.img))


def find_text(shot: Shot, text: str, case: bool = False) -> tuple[int, int] | None:
    """Logical screen position of the centre of ``text`` in the screenshot."""
    needle = text if case else text.lower()
    if not needle:
        return None
    for b in recognize(shot.img):
        hay = b.text if case else b.text.lower()
        idx = hay.find(needle)
        if idx < 0:
            continue
        rect = None
        if b.finder:
            try:
                rect = b.finder(idx, len(needle))
            except Exception:
                rect = None
        if rect is None and b.words:
            # words covering the match
            pos, sel = 0, []
            for wd in b.words:
                start = hay.find(wd.text if case else wd.text.lower(), pos)
                end = start + len(wd.text)
                if start >= 0 and end > idx and start < idx + len(needle):
                    sel.append(wd)
                if start >= 0:
                    pos = end
            if sel:
                x0 = min(w.x for w in sel)
                y0 = min(w.y for w in sel)
                x1 = max(w.x + w.w for w in sel)
                y1 = max(w.y + w.h for w in sel)
                rect = (x0, y0, x1 - x0, y1 - y0)
        if rect is None:
            # proportional estimate inside the line box
            n = max(1, len(b.text))
            rect = (b.x + b.w * idx / n, b.y, b.w * len(needle) / n, b.h)
        x, y, w, h = rect
        return shot.to_logical(x + w / 2, y + h / 2)
    return None

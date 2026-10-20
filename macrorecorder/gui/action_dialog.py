"""Insert / edit dialog for any action, generated from the catalogue."""

from __future__ import annotations

import threading

from pynput import mouse
from PySide6.QtCore import QRegularExpression, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from .. import keys
from ..actions import CATALOG, Action, Field
from ..i18n import tr
from . import overlays
from .hotkey_edit import KeyCaptureEdit

VAR_RE = QRegularExpression(r"[A-Za-z_][A-Za-z0-9_]*")

# field -> (controlling field, allowed values)
VISIBLE_IF = {
    "fail_label": ("on_fail", {"goto"}),
    "max_ms": ("random", {True}),
    "end_label": ("end", {"goto"}),
    "rect": ("restore", {True}),
    "right": ("op", {"==", "!=", "<", ">", "<=", ">=", "contains", "not_contains"}),
    "value": ("source", {"value", "expr", "random", "input"}),
}
VISIBLE_IF_KIND = {
    ("capture_image", "path"): ("target", {"file"}),
    ("save_var", "path"): ("target", {"file"}),
    ("save_var", "append"): ("target", {"file"}),
}
TESTABLE = {"find_image", "wait_image", "find_text", "wait_text", "capture_text", "read_barcode", "get_pixel",
            "wait_pixel", "web_scrape", "ai_prompt", "ai_image", "ai_find", "calc", "focus", "wait_window"}


class FieldWidget(QWidget):
    def __init__(self, f: Field, dlg: "ActionDialog"):
        super().__init__()
        self.f, self.dlg = f, dlg
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)

    def get(self, params: dict) -> None: ...
    def set(self, params: dict) -> None: ...
    def value(self):
        d: dict = {}
        self.get(d)
        return d.get(self.f.name)


class IntW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QSpinBox()
        self.w.setRange(-1_000_000, 1_000_000)
        self.lay.addWidget(self.w)
        self.lay.addStretch(1)

    def get(self, p): p[self.f.name] = self.w.value()
    def set(self, p): self.w.setValue(int(p.get(self.f.name, self.f.default) or 0))


class StrW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QLineEdit()
        if f.type == "var":
            self.w.setValidator(QRegularExpressionValidator(VAR_RE))
            self.w.setPlaceholderText(tr("variable name"))
        if f.type == "num":
            self.w.setPlaceholderText(tr("number, {variable} or expression"))
        self.lay.addWidget(self.w)

    def get(self, p): p[self.f.name] = self.w.text()
    def set(self, p): self.w.setText(str(p.get(self.f.name, self.f.default) or ""))


class TextW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QPlainTextEdit()
        self.w.setMinimumHeight(90)
        self.lay.addWidget(self.w)

    def get(self, p): p[self.f.name] = self.w.toPlainText()
    def set(self, p): self.w.setPlainText(str(p.get(self.f.name, self.f.default) or ""))


class BoolW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QCheckBox()
        self.lay.addWidget(self.w)
        self.lay.addStretch(1)
        self.w.toggled.connect(dlg.update_visibility)

    def get(self, p): p[self.f.name] = self.w.isChecked()
    def set(self, p): self.w.setChecked(bool(p.get(self.f.name, self.f.default)))


class ChoiceW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QComboBox()
        for val, label in f.options or []:
            self.w.addItem(tr(label), val)
        self.lay.addWidget(self.w)
        self.lay.addStretch(1)
        self.w.currentIndexChanged.connect(dlg.update_visibility)

    def get(self, p): p[self.f.name] = self.w.currentData()

    def set(self, p):
        i = self.w.findData(p.get(self.f.name, self.f.default))
        self.w.setCurrentIndex(max(0, i))


class LabelW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QComboBox()
        self.w.setEditable(True)
        self.w.addItem("")
        self.w.addItems(dlg.labels)
        self.lay.addWidget(self.w)

    def get(self, p): p[self.f.name] = self.w.currentText().strip()
    def set(self, p): self.w.setCurrentText(str(p.get(self.f.name, self.f.default) or ""))


class ComboW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = KeyCaptureEdit(allow_text=True)
        self.w.setPlaceholderText(tr("Press keys here or type, e.g. ctrl+shift+s"))
        names = QComboBox()
        names.addItem(tr("Special keys…"))
        names.addItems(keys.key_names())
        names.activated.connect(lambda i: i > 0 and self.w.set_value(names.itemText(i)))
        self.lay.addWidget(self.w, 1)
        self.lay.addWidget(names)

    def get(self, p): p[self.f.name] = self.w.value()
    def set(self, p): self.w.set_value(str(p.get(self.f.name, self.f.default) or ""))


class TimeW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QTimeEdit()
        self.w.setDisplayFormat("HH:mm:ss")
        self.lay.addWidget(self.w)
        self.lay.addStretch(1)

    def get(self, p): p[self.f.name] = self.w.time().toString("HH:mm:ss")

    def set(self, p):
        t = QTime.fromString(str(p.get(self.f.name, self.f.default) or "12:00:00"), "HH:mm:ss")
        self.w.setTime(t if t.isValid() else QTime(12, 0))


class FileW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QLineEdit()
        b = QPushButton(tr("Browse…"))
        b.clicked.connect(self.browse)
        self.lay.addWidget(self.w, 1)
        self.lay.addWidget(b)

    def browse(self):
        save = self.dlg.kind in ("capture_image", "save_var")
        fn = QFileDialog.getSaveFileName if save else QFileDialog.getOpenFileName
        path, _ = fn(self, tr("Choose file"), self.w.text())
        if path:
            self.w.setText(path)

    def get(self, p): p[self.f.name] = self.w.text()
    def set(self, p): self.w.setText(str(p.get(self.f.name, self.f.default) or ""))


class ColorW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.w = QLineEdit()
        self.w.setMaximumWidth(110)
        self.sw = QLabel()
        self.sw.setFixedSize(26, 22)
        pickb = QPushButton(tr("Pick from screen"))
        pickb.clicked.connect(self.pick)
        dlgb = QPushButton("…")
        dlgb.setMaximumWidth(34)
        dlgb.clicked.connect(self.choose)
        for x in (self.w, self.sw, pickb, dlgb):
            self.lay.addWidget(x)
        self.lay.addStretch(1)
        self.w.textChanged.connect(self.refresh)

    def refresh(self):
        self.sw.setStyleSheet(f"background:{self.w.text()};border:1px solid gray;")

    def pick(self):
        r = overlays.pick("color", self.dlg.hide_list())
        if r:
            self.w.setText(r["color"])
            if self.dlg.kind == "wait_pixel" and "pos" in self.dlg.widgets:
                self.dlg.widgets["pos"].set_screen_xy(*r["pos"])

    def choose(self):
        c = QColorDialog.getColor(QColor(self.w.text()), self)
        if c.isValid():
            self.w.setText(c.name())

    def get(self, p): p[self.f.name] = self.w.text().strip() or "#000000"

    def set(self, p):
        self.w.setText(str(p.get(self.f.name, self.f.default) or "#000000"))
        self.refresh()


class PosW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.cur = QCheckBox(tr("Current mouse position"))
        self.x = QSpinBox()
        self.y = QSpinBox()
        for s in (self.x, self.y):
            s.setRange(-100000, 100000)
        pickb = QPushButton(tr("Pick on screen"))
        pickb.clicked.connect(self.pick)
        delay = QPushButton(tr("Capture in 3 s"))
        delay.clicked.connect(lambda: self.countdown(delay))
        mark = QPushButton("👁")
        mark.setToolTip(tr("Show on screen"))
        mark.setMaximumWidth(34)
        mark.clicked.connect(self.mark)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        if f.optional:
            col.addWidget(self.cur)
        nums = QHBoxLayout()
        for x in (QLabel("X"), self.x, QLabel("Y"), self.y, mark):
            nums.addWidget(x)
        nums.addStretch(1)
        btns = QHBoxLayout()
        btns.addWidget(pickb)
        btns.addWidget(delay)
        btns.addStretch(1)
        col.addLayout(nums)
        col.addLayout(btns)
        self.lay.addLayout(col)
        self.cur.toggled.connect(lambda on: [w.setEnabled(not on) for w in (self.x, self.y)])

    def set_xy(self, x, y):
        self.cur.setChecked(False)
        self.x.setValue(int(x))
        self.y.setValue(int(y))

    def set_screen_xy(self, x, y):
        """A point picked on screen; stored relative to the target window if needed."""
        o = self.dlg.origin_fn() or (0, 0)
        self.set_xy(int(x) - o[0], int(y) - o[1])

    def pick(self):
        r = overlays.pick("point", self.dlg.hide_list())
        if r:
            self.set_screen_xy(*r["pos"])

    def countdown(self, btn, n=3):
        if n == 0:
            x, y = mouse.Controller().position
            self.set_screen_xy(x, y)
            btn.setText(tr("Capture in 3 s"))
            btn.setEnabled(True)
            return
        btn.setEnabled(False)
        btn.setText(f"{n}…")
        QTimer.singleShot(1000, lambda: self.countdown(btn, n - 1))

    def mark(self):
        if not self.cur.isChecked():
            o = self.dlg.origin_fn() or (0, 0)
            self.dlg.marker.show_point(self.x.value() + o[0], self.y.value() + o[1], 1500)

    def get(self, p):
        if self.f.optional and self.cur.isChecked():
            p["x"] = p["y"] = None
        else:
            p["x"], p["y"] = self.x.value(), self.y.value()

    def set(self, p):
        x, y = p.get("x"), p.get("y")
        if x is None or y is None:
            self.cur.setChecked(self.f.optional)
            if not self.f.optional:
                self.x.setValue(0)
                self.y.setValue(0)
        else:
            self.set_xy(x, y)


class RegionW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.whole = QCheckBox(tr("Whole screen"))
        self.spins = []
        for _ in range(4):
            s = QSpinBox()
            s.setRange(-100000, 100000)
            self.spins.append(s)
        selb = QPushButton(tr("Select area"))
        selb.clicked.connect(self.pick)
        mark = QPushButton("👁")
        mark.setMaximumWidth(34)
        mark.setToolTip(tr("Show on screen"))
        mark.clicked.connect(self.mark)
        col = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(self.whole)
        top.addWidget(selb)
        top.addWidget(mark)
        top.addStretch(1)
        nums = QHBoxLayout()
        for lbl, s in zip(("X", "Y", "W", "H"), self.spins):
            nums.addWidget(QLabel(lbl))
            nums.addWidget(s)
        nums.addStretch(1)
        col.addLayout(top)
        col.addLayout(nums)
        self.lay.addLayout(col)
        self.whole.toggled.connect(lambda on: [s.setEnabled(not on) for s in self.spins])

    def set_rect(self, r):
        self.whole.setChecked(False)
        for s, v in zip(self.spins, r):
            s.setValue(int(v))

    def pick(self):
        r = overlays.pick("region", self.dlg.hide_list())
        if r:
            o = self.dlg.origin_fn() or (0, 0)
            x, y, w, h = r["rect"]
            self.set_rect([x - o[0], y - o[1], w, h])

    def mark(self):
        if not self.whole.isChecked():
            o = self.dlg.origin_fn() or (0, 0)
            x, y, w, h = [s.value() for s in self.spins]
            self.dlg.marker.show_rect(x + o[0], y + o[1], w, h, ms=1500)

    def get(self, p):
        p["region"] = None if self.whole.isChecked() else [s.value() for s in self.spins]

    def set(self, p):
        r = p.get("region")
        if r:
            self.set_rect(r)
        else:
            self.whole.setChecked(True)


class ImageW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.data = None
        self.preview = QLabel(tr("(no image)"))
        self.preview.setMinimumSize(160, 70)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("border:1px dashed gray;")
        cap = QPushButton(tr("Capture from screen"))
        cap.clicked.connect(self.capture)
        load = QPushButton(tr("Load file…"))
        load.clicked.connect(self.load)
        col = QVBoxLayout()
        col.addWidget(cap)
        col.addWidget(load)
        col.addStretch(1)
        self.lay.addWidget(self.preview, 1)
        self.lay.addLayout(col)

    def show_preview(self):
        if not self.data:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(tr("(no image)"))
            return
        from ..screen import decode_image
        img, _ = decode_image(self.data)
        h, w = img.shape[:2]
        pm = QPixmap.fromImage(QImage(img.data, w, h, img.strides[0], QImage.Format_BGR888).copy())
        self.preview.setPixmap(pm.scaled(300, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def capture(self):
        r = overlays.pick("region", self.dlg.hide_list())
        if not r:
            return
        from ..screen import encode_image
        x, y, w, h = r["rect"]
        shot = r["shot"]
        crop = shot.crop_logical(x, y, w, h)
        if crop.size == 0:
            return
        self.data = encode_image(crop, shot.scale)
        self.show_preview()

    def load(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Load image"), "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        import cv2
        import numpy as np
        img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return
        from ..screen import encode_image, grab
        self.data = encode_image(img, grab([0, 0, 1, 1]).scale)
        self.show_preview()

    def get(self, p): p[self.f.name] = self.data

    def set(self, p):
        self.data = p.get(self.f.name)
        self.show_preview()


class PointsW(FieldWidget):
    def __init__(self, f, dlg):
        super().__init__(f, dlg)
        self.pts = []
        self.l = QLabel()
        self.lay.addWidget(self.l)

    def get(self, p): p[self.f.name] = self.pts

    def set(self, p):
        self.pts = p.get(self.f.name) or []
        self.l.setText(f"{len(self.pts)} {tr('points')}" + (
            f", {self.pts[-1][2]} ms" if self.pts and len(self.pts[-1]) > 2 else ""))


WIDGETS = {"int": IntW, "num": StrW, "str": StrW, "var": StrW, "text": TextW, "bool": BoolW, "choice": ChoiceW,
           "label": LabelW, "combo": ComboW, "key": ComboW, "time": TimeW, "file": FileW, "color": ColorW,
           "pos": PosW, "region": RegionW, "image": ImageW, "points": PointsW}


class ActionEditor(QWidget):
    """Form for one step. Embedded in the inspector panel and in ActionDialog."""

    changed = Signal()

    def __init__(self, action: Action, labels: list[str], store, marker, hide=None, parent=None,
                 compact: bool = False, origin=None):
        super().__init__(parent)
        self.compact = compact
        # callable -> (x, y) of the target window when positions are window-relative, else None
        self.origin_fn = origin or (lambda: None)
        self.action = action.copy()
        self.kind = action.kind
        self.labels = labels
        self.store = store
        self.marker = marker
        self._hide = hide or []
        spec = CATALOG[self.kind]
        self.form = QFormLayout()
        self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        # narrow panels: put each label above its field
        self.form.setRowWrapPolicy(QFormLayout.WrapAllRows if compact else QFormLayout.WrapLongRows)
        self.widgets: dict[str, FieldWidget] = {}
        self.rows: dict[str, int] = {}
        for f in spec.fields:
            w = WIDGETS[f.type](f, self)
            self.widgets[f.name] = w
            self.rows[f.name] = self.form.rowCount()
            lbl = QLabel(tr(f.label))
            lbl.setWordWrap(True)          # long labels must not widen the narrow inspector
            self.form.addRow(lbl, w)
        self.label_edit = QLineEdit(action.label)
        self.label_edit.setPlaceholderText(tr("name that other steps can jump to"))
        self.comment_edit = QLineEdit(action.comment)
        self.enabled_cb = QCheckBox(tr("Enabled"))
        self.enabled_cb.setChecked(action.enabled)
        self.form.addRow(tr("Marker"), self.label_edit)
        self.form.addRow(tr("Note"), self.comment_edit)
        self.form.addRow("", self.enabled_cb)
        for w in self.widgets.values():
            w.set(self.action.params)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self.form)
        self.test_btn = None
        if self.kind in TESTABLE:
            self.test_btn = QPushButton(tr("Test"))
            self.test_btn.clicked.connect(self.test)
        self.update_visibility()

    def hide_list(self):
        return [self.window()] + [w for w in self._hide if w is not self.window()]

    def params(self) -> dict:
        p = dict(self.action.params)
        for w in self.widgets.values():
            w.get(p)
        return p

    def update_visibility(self, *_):
        if not hasattr(self, "widgets"):
            return
        p = {}
        for w in self.widgets.values():
            w.get(p)
        for name, row in self.rows.items():
            rule = VISIBLE_IF_KIND.get((self.kind, name)) or VISIBLE_IF.get(name)
            if rule and rule[0] in p:
                self.form.setRowVisible(row, p[rule[0]] in rule[1])

    def validate(self) -> bool:
        p = self.params()
        if self.kind in ("key_press", "key_down", "key_up"):
            if not keys.valid_combo(p.get("combo", "")):
                QMessageBox.warning(self, tr("Invalid key"),
                                    tr("Press a key combination in the field or type one like ctrl+shift+s."))
                return False
        if self.kind in ("find_image", "wait_image") and not p.get("image"):
            QMessageBox.warning(self, tr("No image"), tr("Capture an image from the screen first."))
            return False
        if self.kind == "goto" and not p.get("target"):
            QMessageBox.warning(self, tr("Missing marker"), tr("Choose the marker to jump to."))
            return False
        return True

    def result_action(self) -> Action:
        return Action(self.kind, self.params(), self.label_edit.text().strip(), self.comment_edit.text(),
                      self.enabled_cb.isChecked())

    # ------------------------------------------------------------ testing
    def test(self):
        a = self.result_action()
        a.enabled = True
        o = self.origin_fn()
        if o:                                   # window-relative → screen coordinates for the test
            from ..macro import shift_positions
            a = shift_positions([a], o[0], o[1])[0]
        self.test_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        box: dict = {}

        def work():
            try:
                box["result"] = run_test(a, self.store)
            except Exception as e:
                box["error"] = f"{type(e).__name__}: {e}"

        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                QTimer.singleShot(100, poll)
                return
            QApplication.restoreOverrideCursor()
            self.test_btn.setEnabled(True)
            if "error" in box:
                QMessageBox.warning(self, tr("Test"), box["error"])
                return
            text, point = box["result"]
            if point:
                self.marker.show_point(point[0], point[1], 2500)
            QMessageBox.information(self, tr("Test"), text)
        poll()


class ActionDialog(QDialog):
    def __init__(self, action: Action, labels: list[str], store, marker, parent=None, hide=None, origin=None):
        super().__init__(parent)
        spec = CATALOG[action.kind]
        self.setWindowTitle(f"{spec.icon}  {tr(spec.name)}")
        self.setMinimumWidth(640)
        self.editor = ActionEditor(action, labels, store, marker, hide, self, origin=origin)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(lambda: self.editor.validate() and self.accept())
        bb.rejected.connect(self.reject)
        if self.editor.test_btn:
            bb.addButton(self.editor.test_btn, QDialogButtonBox.ActionRole)
        lay = QVBoxLayout(self)
        lay.addWidget(self.editor)
        lay.addWidget(bb)

    def result_action(self) -> Action:
        return self.editor.result_action()


def run_test(a: Action, store) -> tuple[str, tuple | None]:
    """Execute the detection part of an action once, without side effects."""
    from .. import ocr, screen, winmgr
    from ..expr import evaluate
    p = a.params
    region = p.get("region")
    if a.kind in ("find_image", "wait_image"):
        pos, score = screen.find_image(p["image"], region, float(p.get("confidence", 90)) / 100)
        if pos:
            return tr("Found at") + f" ({pos[0]}, {pos[1]}) — {tr('similarity')} {score:.0%}", pos
        return tr("Not found. Best similarity:") + f" {score:.0%}", None
    if a.kind in ("find_text", "wait_text"):
        pos = ocr.find_text(screen.grab(region), p.get("text", ""))
        if pos:
            return tr("Found at") + f" ({pos[0]}, {pos[1]})", pos
        return tr("Text not found. Recognized text:") + "\n\n" + ocr.read_text(screen.grab(region))[:1500], None
    if a.kind == "capture_text":
        return ocr.read_text(screen.grab(region))[:3000] or tr("(no text)"), None
    if a.kind == "read_barcode":
        codes = screen.read_codes(screen.grab(region).img)
        return "\n".join(codes) if codes else tr("No barcode found"), None
    if a.kind in ("get_pixel", "wait_pixel"):
        x, y = p.get("x"), p.get("y")
        if x is None:
            x, y = mouse.Controller().position
        c = screen.pixel_color(int(x), int(y))
        return f"({int(x)}, {int(y)}) = {c}", (int(x), int(y))
    if a.kind == "calc":
        return f"{p.get('expr')} = {evaluate(p.get('expr', ''), {})}", None
    if a.kind in ("focus", "wait_window"):
        w = winmgr.find_window(p.get("app", ""), p.get("title", ""))
        return (f"{w.app} — {w.title}" if w else tr("Window not found")), None
    if a.kind in ("web_scrape", "ai_prompt", "ai_image", "ai_find"):
        from ..engine import Engine, EngineUI, PlaySettings
        from ..macro import Macro
        e = Engine(EngineUI())
        s = PlaySettings(ai=store.ai_config())
        if a.kind == "ai_find":
            a.params.update(then="none", var_x="_test_x", var_y="_test_y", found_label="",
                            on_fail="continue")
        res: dict = {}

        class UI(EngineUI):
            def finished(self, ok, err):
                res["err"] = err
        e.ui = UI()
        e.play(Macro([a]), s)
        e.wait(180)
        if res.get("err"):
            raise RuntimeError(res["err"])
        if a.kind == "ai_find":
            if "_test_x" in e.vars:
                pt = (int(e.vars["_test_x"]), int(e.vars["_test_y"]))
                return tr("Found at") + f" {pt}", pt
            return tr("Not found"), None
        return str(e.vars.get(p.get("var", ""), ""))[:3000], None
    return "", None

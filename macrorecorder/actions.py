"""Action catalogue: every action type, its parameters and how it is shown.

A macro is a list of :class:`Action`. Each action has a ``kind`` (key into
``CATALOG``), a ``params`` dict, and the per-row columns of the editor:
``label`` (jump target), ``comment`` and ``enabled``.

Numeric parameters of type ``"num"`` are stored as strings so they may hold
variables or expressions (``"{x} + 10"``), evaluated at playback time.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .i18n import tr

# ---------------------------------------------------------------- field spec


@dataclass
class Field:
    name: str
    type: str                 # int num str text bool choice key combo pos region image color label file var time
    default: Any = None
    label: str = ""
    options: list | None = None   # for "choice": list of (value, label)
    optional: bool = False        # pos/region may be empty (= current cursor / whole screen)
    hint: str = ""


@dataclass
class Kind:
    kind: str
    name: str
    category: str
    fields: list[Field] = field(default_factory=list)
    icon: str = ""

    def defaults(self) -> dict:
        out = {}
        for f in self.fields:
            if f.type == "pos":
                out["x"], out["y"] = (None, None) if f.optional else (0, 0)
            elif f.type == "region":
                out["region"] = None
            else:
                out[f.name] = copy.deepcopy(f.default)
        return out


BUTTONS = [("left", "Left"), ("right", "Right"), ("middle", "Middle")]
THEN_ACTIONS = [("click", "Click"), ("double", "Double-click"), ("right", "Right-click"),
                ("move", "Move mouse"), ("none", "Nothing")]
ON_FAIL = [("continue", "Continue"), ("stop", "Stop macro"), ("goto", "Jump to marker")]
MOUSE_PATHS = [("recorded", "As recorded"), ("straight", "Straight line"),
               ("natural", "Natural"), ("jump", "Jump")]


def _timeout_fields(default_ms: int = 10000) -> list[Field]:
    return [
        Field("timeout", "num", str(default_ms), "Timeout (ms, 0 = forever)"),
        Field("on_fail", "choice", "continue", "On timeout", ON_FAIL),
        Field("fail_label", "label", "", "On timeout, jump to"),
    ]


def _store_fields() -> list[Field]:
    return [
        Field("var_x", "var", "", "Store X in variable"),
        Field("var_y", "var", "", "Store Y in variable"),
        Field("found_label", "label", "", "If found, jump to"),
    ]


CATEGORIES = [
    ("mouse", "Mouse", "👆"),
    ("keys", "Text/key", "⌨"),
    ("wait", "Wait", "⏱"),
    ("find", "Image/OCR", "🔍"),
    ("vars", "Variables", "𝑥"),
    ("control", "Misc", "🧰"),
    ("ai", "AI", "✨"),
]

_K: list[Kind] = [
    # ------------------------------------------------------------- mouse
    Kind("click", "Mouse click", "mouse", [
        Field("button", "choice", "left", "Button", BUTTONS),
        Field("count", "int", 1, "Clicks (2 = double-click)"),
        Field("pos", "pos", None, "Position", optional=True),
        Field("wiggle", "int", 0, "Random wiggle (px)"),
    ], "👆"),
    Kind("mouse_down", "Mouse down", "mouse", [
        Field("button", "choice", "left", "Button", BUTTONS),
        Field("pos", "pos", None, "Position", optional=True),
    ], "⤓"),
    Kind("mouse_up", "Mouse up", "mouse", [
        Field("button", "choice", "left", "Button", BUTTONS),
        Field("pos", "pos", None, "Position", optional=True),
    ], "⤒"),
    Kind("mouse_move", "Mouse move", "mouse", [Field("pos", "pos", None, "Position")], "➚"),
    Kind("mouse_path", "Mouse path", "mouse", [Field("points", "points", [], "Points")], "〰"),
    Kind("scroll", "Mouse wheel", "mouse", [
        Field("dy", "int", -3, "Vertical (negative = down)"),
        Field("dx", "int", 0, "Horizontal"),
        Field("pos", "pos", None, "Position", optional=True),
    ], "⇕"),
    Kind("ai_find", "AI find object", "mouse", [
        Field("description", "text", "", "Describe the object"),
        Field("then", "choice", "click", "Then", THEN_ACTIONS),
        *_store_fields(),
        Field("on_fail", "choice", "continue", "If not found", ON_FAIL),
        Field("fail_label", "label", "", "If not found, jump to"),
    ], "✨"),
    # -------------------------------------------------------------- keys
    Kind("type_text", "Text", "keys", [
        Field("text", "text", "", "Text ({variables} allowed)"),
        Field("method", "choice", "keys", "Output", [("keys", "Key by key"), ("paste", "Via clipboard")]),
        Field("human", "bool", False, "Human typing simulation"),
    ], "🔤"),
    Kind("key_press", "Key press", "keys", [
        Field("combo", "combo", "enter", "Key / hotkey (e.g. ctrl+shift+s)"),
        Field("count", "int", 1, "Times"),
    ], "⌨"),
    Kind("key_down", "Key down", "keys", [Field("combo", "combo", "shift", "Key")], "⬇"),
    Kind("key_up", "Key up", "keys", [Field("combo", "combo", "shift", "Key")], "⬆"),
    # -------------------------------------------------------------- wait
    Kind("wait", "Wait", "wait", [
        Field("ms", "num", "1000", "Time (ms)"),
        Field("random", "bool", False, "Random time"),
        Field("max_ms", "num", "2000", "Maximum (ms) for random"),
    ], "⏱"),
    Kind("wait_until", "Wait until time", "wait", [Field("time", "time", "12:00:00", "Time (HH:MM:SS)")], "🕛"),
    Kind("wait_image", "Wait for image", "wait", [
        Field("image", "image", None, "Image"),
        Field("appear", "choice", "appear", "Wait until", [("appear", "Appears"), ("disappear", "Disappears")]),
        Field("confidence", "int", 90, "Similarity (%)"),
        Field("region", "region", None, "Search area", optional=True),
        *_timeout_fields(),
    ], "🖼"),
    Kind("wait_text", "Wait for text (OCR)", "wait", [
        Field("text", "str", "", "Text"),
        Field("appear", "choice", "appear", "Wait until", [("appear", "Appears"), ("disappear", "Disappears")]),
        Field("region", "region", None, "Search area", optional=True),
        *_timeout_fields(),
    ], "🔡"),
    Kind("wait_pixel", "Wait for pixel color", "wait", [
        Field("pos", "pos", None, "Position"),
        Field("color", "color", "#ffffff", "Color"),
        Field("tolerance", "int", 10, "Tolerance"),
        *_timeout_fields(),
    ], "🎨"),
    Kind("wait_change", "Wait for screen change", "wait", [
        Field("region", "region", None, "Screen area", optional=True),
        Field("threshold", "int", 2, "Sensitivity (% changed)"),
        *_timeout_fields(60000),
    ], "📺"),
    Kind("wait_file", "Wait for file", "wait", [
        Field("path", "file", "", "File"),
        Field("event", "choice", "created", "Wait until",
              [("created", "Created"), ("deleted", "Deleted"), ("modified", "Modified")]),
        *_timeout_fields(60000),
    ], "📄"),
    Kind("wait_window", "Wait for window", "wait", [
        Field("title", "str", "", "Window title / app contains"),
        *_timeout_fields(),
    ], "🪟"),
    # -------------------------------------------------------- find/capture
    Kind("find_image", "Find image on screen", "find", [
        Field("image", "image", None, "Image"),
        Field("confidence", "int", 90, "Similarity (%)"),
        Field("region", "region", None, "Search area", optional=True),
        Field("timeout", "num", "5000", "Search for up to (ms)"),
        Field("then", "choice", "click", "When found", THEN_ACTIONS),
        Field("off_x", "int", 0, "Click offset X"),
        Field("off_y", "int", 0, "Click offset Y"),
        *_store_fields(),
        Field("on_fail", "choice", "continue", "If not found", ON_FAIL),
        Field("fail_label", "label", "", "If not found, jump to"),
    ], "🖼"),
    Kind("find_text", "Find text (OCR)", "find", [
        Field("text", "str", "", "Text"),
        Field("region", "region", None, "Search area", optional=True),
        Field("timeout", "num", "5000", "Search for up to (ms)"),
        Field("then", "choice", "click", "When found", THEN_ACTIONS),
        *_store_fields(),
        Field("on_fail", "choice", "continue", "If not found", ON_FAIL),
        Field("fail_label", "label", "", "If not found, jump to"),
    ], "🔡"),
    Kind("capture_text", "Capture text (OCR)", "find", [
        Field("region", "region", None, "Screen area", optional=True),
        Field("var", "var", "text", "Store in variable"),
    ], "📝"),
    Kind("capture_image", "Capture screenshot", "find", [
        Field("region", "region", None, "Screen area", optional=True),
        Field("target", "choice", "file", "Save to", [("file", "File"), ("clipboard", "Clipboard")]),
        Field("path", "file", "screenshot_{date}_{time}.png", "File"),
    ], "📷"),
    Kind("read_barcode", "Read barcode / QR code", "find", [
        Field("region", "region", None, "Screen area", optional=True),
        Field("var", "var", "code", "Store in variable"),
        Field("on_fail", "choice", "continue", "If not found", ON_FAIL),
        Field("fail_label", "label", "", "If not found, jump to"),
    ], "▦"),
    Kind("get_pixel", "Get pixel color", "find", [
        Field("pos", "pos", None, "Position", optional=True),
        Field("var", "var", "color", "Store in variable"),
    ], "🎨"),
    # ----------------------------------------------------------- variables
    Kind("set_var", "Set variable", "vars", [
        Field("var", "var", "v", "Variable"),
        Field("source", "choice", "value", "Value from",
              [("value", "Text"), ("expr", "Calculation"), ("clipboard", "Clipboard"),
               ("mouse", "Mouse position (x,y)"), ("random", "Random number"), ("input", "Ask user")]),
        Field("value", "text", "", "Text / expression / range (e.g. 1-100)"),
    ], "𝑥"),
    Kind("calc", "Calculate", "vars", [
        Field("var", "var", "n", "Result variable"),
        Field("expr", "str", "{n} + 1", "Expression"),
    ], "🧮"),
    Kind("read_list", "Read line from list file", "vars", [
        Field("path", "file", "", "Text / CSV file"),
        Field("var", "var", "line", "Store line in variable"),
        Field("mode", "choice", "next", "Line", [("next", "Next line"), ("random", "Random line")]),
        Field("end", "choice", "stop", "After the last line",
              [("stop", "Stop macro"), ("restart", "Start over"), ("goto", "Jump to marker")]),
        Field("end_label", "label", "", "Then jump to"),
    ], "📃"),
    Kind("save_var", "Save variable", "vars", [
        Field("var", "var", "v", "Variable"),
        Field("target", "choice", "file", "Save to", [("file", "File"), ("clipboard", "Clipboard")]),
        Field("path", "file", "", "File"),
        Field("append", "bool", True, "Append to file"),
    ], "💾"),
    Kind("web_scrape", "Read from web page", "vars", [
        Field("url", "str", "https://", "URL"),
        Field("method", "choice", "regex", "Extract with", [("regex", "Regular expression"), ("xpath", "XPath"),
                                                              ("text", "Whole page text")]),
        Field("pattern", "str", "<title>(.*?)</title>", "Pattern"),
        Field("var", "var", "web", "Store in variable"),
    ], "🌐"),
    # ------------------------------------------------------------- control
    Kind("goto", "Jump / Loop", "control", [
        Field("target", "label", "", "Marker"),
        Field("count", "num", "0", "Repeat count (0 = always jump)"),
    ], "↩"),
    Kind("if", "Condition (if / else)", "control", [
        Field("left", "str", "{v}", "Value"),
        Field("op", "choice", "==", "Condition",
              [("==", "="), ("!=", "≠"), ("<", "<"), (">", ">"), ("<=", "≤"), (">=", "≥"),
               ("contains", "contains"), ("not_contains", "does not contain"),
               ("empty", "is empty"), ("not_empty", "is not empty")]),
        Field("right", "str", "", "Compare with"),
        Field("then_label", "label", "", "If true, jump to (empty = next step)"),
        Field("else_label", "label", "", "If false, jump to (empty = next step)"),
    ], "⑂"),
    Kind("run_macro", "Run another macro file", "control", [Field("path", "file", "", "Macro file")], "📎"),
    Kind("execute", "Execute program / open", "control", [
        Field("command", "str", "", "Program, file or URL"),
        Field("args", "str", "", "Arguments"),
        Field("wait", "bool", False, "Wait until it exits"),
    ], "▶"),
    Kind("focus", "Focus window", "control", [
        Field("app", "str", "", "Application"),
        Field("title", "str", "", "Window title contains"),
        Field("restore", "bool", False, "Restore window position & size"),
        Field("rect", "str", "", "Window rect x,y,w,h"),
        *_timeout_fields(5000),
    ], "🪟"),
    Kind("message", "Message box", "control", [
        Field("title", "str", "Actions Recorder", "Title"),
        Field("text", "text", "", "Message ({variables} allowed)"),
        Field("buttons", "choice", "ok", "Buttons",
              [("ok", "OK"), ("okcancel", "OK / Cancel"), ("yesno", "Yes / No"), ("yesnocancel", "Yes / No / Cancel")]),
        Field("yes_label", "label", "", "OK / Yes → marker"),
        Field("no_label", "label", "", "No → marker"),
        Field("cancel_label", "label", "", "Cancel → marker (empty = stop)"),
    ], "💬"),
    Kind("notify", "Notification", "control", [Field("text", "str", "", "Text")], "🔔"),
    Kind("beep", "Beep", "control", [], "🔊"),
    Kind("clipboard", "Set clipboard", "control", [Field("text", "text", "", "Text")], "📋"),
    Kind("stop", "Stop playback", "control", [], "⏹"),
    Kind("group", "Group", "control", [
        Field("name", "str", "Group", "Name"),
        Field("color", "color", "#3e63dd", "Color"),
        Field("collapsed", "bool", False, "Collapsed"),
    ], "▣"),
    Kind("group_end", "End of group", "control", [], "▫"),
    # ------------------------------------------------------------------ AI
    Kind("ai_prompt", "AI prompt", "ai", [
        Field("prompt", "text", "", "Prompt ({variables} allowed)"),
        Field("var", "var", "ai", "Store answer in variable"),
    ], "✨"),
    Kind("ai_image", "AI analyze screen", "ai", [
        Field("prompt", "text", "Describe what you see.", "Question"),
        Field("region", "region", None, "Screen area", optional=True),
        Field("file", "file", "", "…or image file"),
        Field("var", "var", "ai", "Store answer in variable"),
    ], "👁"),
]

CATALOG: dict[str, Kind] = {k.kind: k for k in _K}

FILTER_GROUPS = {
    "mouse_moves": {"mouse_move", "mouse_path"},
    "mouse_clicks": {"click", "mouse_down", "mouse_up", "scroll"},
    "keys": {"type_text", "key_press", "key_down", "key_up"},
    "waits": {"wait"},
    "focus": {"focus"},
}


# -------------------------------------------------------------------- action


@dataclass
class Action:
    kind: str
    params: dict = field(default_factory=dict)
    label: str = ""
    comment: str = ""
    enabled: bool = True

    @classmethod
    def new(cls, kind: str, **params) -> "Action":
        p = CATALOG[kind].defaults()
        p.update(params)
        return cls(kind, p)

    def p(self, name: str, default=None):
        v = self.params.get(name)
        if v is None:
            for f in CATALOG[self.kind].fields:
                if f.name == name:
                    return f.default if default is None else default
            return default
        return v

    def to_dict(self) -> dict:
        d: dict = {"kind": self.kind}
        if self.params:
            d["params"] = self.params
        if self.label:
            d["label"] = self.label
        if self.comment:
            d["comment"] = self.comment
        if not self.enabled:
            d["enabled"] = False
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(d["kind"], dict(d.get("params", {})), d.get("label", ""), d.get("comment", ""),
                   d.get("enabled", True))

    def copy(self) -> "Action":
        return Action(self.kind, copy.deepcopy(self.params), self.label, self.comment, self.enabled)

    @property
    def spec(self) -> Kind:
        return CATALOG[self.kind]

    @property
    def name(self) -> str:
        return tr(self.spec.name)

    # ------------------------------------------------------------- display
    def describe(self) -> str:
        k, p = self.kind, self.params

        def pos(empty=None):
            if p.get("x") is None or p.get("y") is None:
                return empty if empty is not None else tr("current position")
            return f"({p['x']}, {p['y']})"

        def region():
            r = p.get("region")
            return tr("whole screen") if not r else f"[{r[0]}, {r[1]} {r[2]}×{r[3]}]"

        def fail():
            of = p.get("on_fail", "continue")
            if of == "goto":
                return f" → {p.get('fail_label', '')}"
            return "" if of == "continue" else " → " + tr("stop")

        btn = tr({"left": "Left", "right": "Right", "middle": "Middle"}.get(p.get("button", "left"), "Left"))
        btn_l = tr({"left": "left", "right": "right", "middle": "middle"}.get(p.get("button", "left"), "left"))
        if k == "click":
            c = int(p.get("count", 1) or 1)
            what = {1: tr("click"), 2: tr("double-click")}.get(c, f"{c}× " + tr("click"))
            text = tr("{button} {action}").format(button=btn_l, action=what)
            return f"{text[:1].upper()}{text[1:]} {pos()}"
        if k in ("mouse_down", "mouse_up"):
            return f"{btn} {pos()}"
        if k == "mouse_move":
            return pos()
        if k == "mouse_path":
            pts = p.get("points") or []
            if not pts:
                return ""
            dur = pts[-1][2] if len(pts[-1]) > 2 else 0
            return (f"({pts[0][0]}, {pts[0][1]}) → ({pts[-1][0]}, {pts[-1][1]}), "
                    f"{len(pts)} {tr('points')}, {dur} ms")
        if k == "scroll":
            return f"{p.get('dy', 0):+d}" + (f", ↔ {p.get('dx'):+d}" if p.get("dx") else "") + \
                (f" {pos('')}" if p.get("x") is not None else "")
        if k == "type_text":
            t = (p.get("text") or "").replace("\n", "⏎").replace("\t", "⇥")
            return f"\"{t[:80]}{'…' if len(t) > 80 else ''}\""
        if k in ("key_press", "key_down", "key_up"):
            s = combo_display(p.get("combo", ""))
            n = int(p.get("count", 1) or 1) if k == "key_press" else 1
            return s + (f" × {n}" if n > 1 else "")
        if k == "wait":
            if p.get("random"):
                return f"{p.get('ms')}–{p.get('max_ms')} ms ({tr('random')})"
            return f"{p.get('ms')} ms"
        if k == "wait_until":
            return p.get("time", "")
        if k == "wait_image":
            return f"{tr('Appears') if p.get('appear') != 'disappear' else tr('Disappears')}, {region()}{fail()}"
        if k == "wait_text":
            return f"\"{p.get('text', '')}\" {tr('Appears') if p.get('appear') != 'disappear' else tr('Disappears')}{fail()}"
        if k == "wait_pixel":
            return f"{pos()} = {p.get('color')}{fail()}"
        if k == "wait_change":
            return region() + fail()
        if k == "wait_file":
            return f"{p.get('path', '')} — {tr(p.get('event', 'created').capitalize())}{fail()}"
        if k == "wait_window":
            return f"\"{p.get('title', '')}\"{fail()}"
        if k in ("find_image", "find_text"):
            what = tr("image") if k == "find_image" else f"\"{p.get('text', '')}\""
            then = dict(THEN_ACTIONS).get(p.get("then", "click"), "")
            return f"{what} → {tr(then)}, {region()}{fail()}"
        if k == "ai_find":
            d = (p.get("description") or "").replace("\n", " ")
            return f"\"{d[:60]}\" → {tr(dict(THEN_ACTIONS).get(p.get('then', 'click'), ''))}{fail()}"
        if k in ("capture_text", "read_barcode"):
            return f"{region()} → {{{p.get('var', '')}}}"
        if k == "capture_image":
            return f"{region()} → {tr('Clipboard') if p.get('target') == 'clipboard' else p.get('path', '')}"
        if k == "get_pixel":
            return f"{pos()} → {{{p.get('var', '')}}}"
        if k == "set_var":
            src = p.get("source", "value")
            val = p.get("value", "")
            if src == "clipboard":
                val = tr("Clipboard")
            elif src == "mouse":
                val = tr("Mouse position (x,y)")
            elif src == "random":
                val = f"{tr('random')} {val}"
            elif src == "input":
                val = f"{tr('Ask user')}: {val}"
            return f"{{{p.get('var', '')}}} = {str(val)[:80]}"
        if k == "calc":
            return f"{{{p.get('var', '')}}} = {p.get('expr', '')}"
        if k == "read_list":
            return f"{p.get('path', '')} → {{{p.get('var', '')}}}"
        if k == "save_var":
            tgt = tr("Clipboard") if p.get("target") == "clipboard" else p.get("path", "")
            return f"{{{p.get('var', '')}}} → {tgt}"
        if k == "web_scrape":
            return f"{p.get('url', '')} → {{{p.get('var', '')}}}"
        if k == "goto":
            n = str(p.get("count", "0"))
            return f"→ {p.get('target', '')}" + (f"  ({n}×)" if n not in ("", "0") else "")
        if k == "if":
            op = dict(CATALOG["if"].fields[1].options).get(p.get("op", "=="), "=")
            right = "" if p.get("op") in ("empty", "not_empty") else f" \"{p.get('right', '')}\""
            t = p.get("then_label") or "↓"
            e = p.get("else_label") or "↓"
            return f"\"{p.get('left', '')}\" {tr(op)}{right} ? {t} : {e}"
        if k in ("run_macro",):
            return p.get("path", "")
        if k == "execute":
            return f"{p.get('command', '')} {p.get('args', '')}".strip()
        if k == "focus":
            return " — ".join(x for x in (p.get("app", ""), p.get("title", "")) if x) + fail()
        if k == "message":
            return (p.get("text") or "").replace("\n", " ")[:80]
        if k in ("notify",):
            return p.get("text", "")
        if k == "clipboard":
            return (p.get("text") or "").replace("\n", " ")[:80]
        if k == "group":
            return p.get("name", "")
        if k in ("ai_prompt", "ai_image"):
            return (p.get("prompt") or "").replace("\n", " ")[:70] + f" → {{{p.get('var', '')}}}"
        return ""

    def duration_ms(self) -> int:
        if self.kind == "wait":
            try:
                return int(float(self.params.get("ms", 0)))
            except (TypeError, ValueError):
                return 0
        if self.kind == "mouse_path":
            pts = self.params.get("points") or []
            return int(pts[-1][2]) if pts and len(pts[-1]) > 2 else 0
        return 0


def combo_display(combo: str) -> str:
    parts = [x for x in (combo or "").split("+") if x]
    if combo.endswith("++"):
        parts.append("+")
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": "Cmd", "space": "Space", " ": "Space"}
    out = []
    for x in parts:
        if x in names:
            out.append(names[x])
        elif len(x) == 1:
            out.append(x.upper())
        else:
            out.append(x.replace("_", " ").title())
    return "+".join(out)

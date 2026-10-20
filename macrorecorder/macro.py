"""Macro container: list of actions + file IO (JSON ``.macro``) + CSV export."""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field

from . import __version__
from .actions import CATALOG, Action

PLATFORM = "darwin" if sys.platform == "darwin" else ("win32" if sys.platform.startswith("win") else "linux")


@dataclass
class Macro:
    actions: list[Action] = field(default_factory=list)
    platform: str = PLATFORM

    def to_json(self) -> str:
        return json.dumps({
            "format": "macrorecorder", "version": 2, "app": __version__, "platform": self.platform,
            "actions": [a.to_dict() for a in self.actions],
        }, indent=1, ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "Macro":
        data = json.loads(s)
        if isinstance(data, list):
            data = {"actions": data}
        if "events" in data:                       # format v1 (first version of this app)
            return cls(_convert_v1(data["events"]), data.get("platform", PLATFORM))
        acts = []
        for d in data.get("actions", []):
            if d.get("kind") in CATALOG:
                acts.append(Action.from_dict(d))
        return cls(acts, data.get("platform", PLATFORM))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "Macro":
        with open(path, encoding="utf-8-sig") as f:
            return cls.from_json(f.read())

    def copy(self) -> "Macro":
        return Macro([a.copy() for a in self.actions], self.platform)

    def duration_ms(self) -> int:
        return sum(a.duration_ms() for a in self.actions if a.enabled)

    def labels(self) -> list[str]:
        return [a.label for a in self.actions if a.label]

    def __len__(self) -> int:
        return len(self.actions)

    def export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["#", "Action", "Value", "Label", "Comment", "Enabled"])
            for i, a in enumerate(self.actions, 1):
                w.writerow([i, a.name, a.describe(), a.label, a.comment, "yes" if a.enabled else "no"])


def _convert_v1(events: list[dict]) -> list[Action]:
    """v1 stored per-event delays; turn them into explicit Wait actions."""
    out: list[Action] = []
    for e in events:
        d = int(e.get("delay", 0) or 0)
        k = e.get("kind")
        if d >= 20 and k != "wait":
            out.append(Action.new("wait", ms=str(d)))
        pos = {"x": e.get("x"), "y": e.get("y")}
        if k == "mouse_move":
            out.append(Action.new("mouse_move", **pos))
        elif k in ("mouse_down", "mouse_up"):
            out.append(Action.new(k, button=e.get("button", "left"), **pos))
        elif k == "mouse_click":
            out.append(Action.new("click", button=e.get("button", "left"), count=e.get("count", 1), **pos))
        elif k == "scroll":
            out.append(Action.new("scroll", dx=e.get("dx", 0), dy=e.get("dy", 0), **pos))
        elif k in ("key_down", "key_up", "key_press"):
            from .keys import base_token
            tok = base_token(e.get("key", ""), e.get("vk"))
            a = Action.new(k, combo=tok)
            if k == "key_press":
                a.params["count"] = e.get("count", 1)
            out.append(a)
        elif k == "type_text":
            out.append(Action.new("type_text", text=e.get("text", "")))
        elif k == "wait":
            out.append(Action.new("wait", ms=str(d)))
        elif k == "comment":
            a = Action.new("notify", text="")
            a.enabled = False
            a.comment = e.get("text", "")
            out.append(a)
    return out


# ------------------------------------------------------------ edit helpers

def group_ranges(actions: list[Action]) -> dict[int, int]:
    """Map group-start index -> index of its matching group_end (or last row)."""
    out: dict[int, int] = {}
    stack: list[int] = []
    for i, a in enumerate(actions):
        if a.kind == "group":
            stack.append(i)
        elif a.kind == "group_end" and stack:
            out[stack.pop()] = i
    for s in stack:
        out[s] = len(actions) - 1
    return out


def hidden_rows(actions: list[Action]) -> set[int]:
    """Rows hidden because they are inside a collapsed group."""
    hidden: set[int] = set()
    for start, end in group_ranges(actions).items():
        if actions[start].params.get("collapsed"):
            hidden.update(range(start + 1, end + 1))
    return hidden


def optimize(actions: list[Action], min_wait_ms: int = 0, max_wait_ms: int = 0,
             drop_moves: bool = False) -> list[Action]:
    """Remove redundant mouse moves, merge adjacent waits, clamp waits."""
    out: list[Action] = []
    for a in actions:
        a = a.copy()
        if drop_moves and a.kind in ("mouse_move", "mouse_path") and not a.label:
            continue
        if a.kind == "wait" and not a.params.get("random") and not a.label:
            try:
                ms = int(float(a.params.get("ms", 0)))
            except (TypeError, ValueError):
                out.append(a)
                continue
            if out and out[-1].kind == "wait" and not out[-1].params.get("random"):
                try:
                    ms += int(float(out[-1].params.get("ms", 0)))
                    out.pop()
                except (TypeError, ValueError):
                    pass
            if max_wait_ms and ms > max_wait_ms:
                ms = max_wait_ms
            if ms < min_wait_ms:
                continue
            a.params["ms"] = str(ms)
        # consecutive mouse moves: keep the last one only
        if a.kind == "mouse_move" and out and out[-1].kind == "mouse_move" and not out[-1].label:
            out.pop()
        out.append(a)
    return out


def scale_waits(actions: list[Action], factor: float) -> list[Action]:
    out = []
    for a in actions:
        a = a.copy()
        if a.kind == "wait":
            for key in ("ms", "max_ms"):
                try:
                    a.params[key] = str(max(0, int(round(float(a.params.get(key, 0)) * factor))))
                except (TypeError, ValueError):
                    pass
        elif a.kind == "mouse_path":
            a.params["points"] = [[p[0], p[1], int(p[2] * factor)] for p in a.params.get("points", [])]
        out.append(a)
    return out

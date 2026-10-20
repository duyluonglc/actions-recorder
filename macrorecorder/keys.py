"""Keys: conversion between pynput keys and the text form used in macros.

Raw recorded key encoding (``encode``):
  * ``"Key.<name>"``  – a named key (``Key.enter``, ``Key.ctrl_l`` ...)
  * a single character – a printable key
  * ``"vk:<n>"``       – a key without a printable character

Combo encoding used by actions and hotkeys: ``"ctrl+shift+s"``, ``"enter"``,
``"f5"``, ``"a"``, ``"vk:65"``. Modifiers: ctrl, alt, shift, cmd (cmd = Windows key
on Windows).
"""

from __future__ import annotations

import sys

from pynput.keyboard import Key, KeyCode

MOD_GROUP = {
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
}
MODS = ("ctrl", "alt", "shift", "cmd")
MOD_KEYS = {"ctrl": Key.ctrl, "alt": Key.alt, "shift": Key.shift, "cmd": Key.cmd}
ALIASES = {"control": "ctrl", "option": "alt", "opt": "alt", "command": "cmd", "win": "cmd",
           "super": "cmd", "meta": "cmd", "escape": "esc", "return": "enter", "del": "delete",
           "pgup": "page_up", "pgdn": "page_down", "ins": "insert", "spacebar": "space",
           "bksp": "backspace", "back": "backspace"}


def encode(key) -> tuple[str, int | None]:
    """pynput key -> (key string, vk)."""
    if isinstance(key, Key):
        return f"Key.{key.name}", getattr(key.value, "vk", None)
    if isinstance(key, KeyCode):
        vk, ch = key.vk, key.char
        if ch is not None and len(ch) == 1 and ch.isprintable():
            return ch, vk
        if vk is not None:
            return f"vk:{vk}", vk
        return ch or "", vk
    return str(key), None


def is_modifier(key: str | None) -> bool:
    return bool(key) and key.startswith("Key.") and key[4:] in MOD_GROUP


def mod_of(key: str) -> str | None:
    return MOD_GROUP.get(key[4:]) if key and key.startswith("Key.") else None


# macOS ANSI virtual key codes for printable keys (used when a modifier such
# as Ctrl turns the reported character into a control code).
_MAC_VK_CHARS = dict(zip(
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
     24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 37, 38, 39, 40, 41, 42, 43, 44,
     45, 46, 47, 50],
    ["a", "s", "d", "f", "h", "g", "z", "x", "c", "v", "b", "q", "w", "e", "r", "y", "t",
     "1", "2", "3", "4", "6", "5", "=", "9", "7", "-", "8", "0", "]", "o", "u", "[", "i",
     "p", "l", "j", "'", "k", ";", "\\", ",", "/", "n", "m", ".", "`"]))


def vk_to_char(vk: int | None) -> str | None:
    if vk is None:
        return None
    if sys.platform == "darwin":
        return _MAC_VK_CHARS.get(vk)
    if sys.platform.startswith("win"):
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
            return chr(vk).lower()
    return None


def base_token(key: str, vk: int | None = None) -> str:
    """Raw key string -> combo token without modifiers (``Key.enter`` -> ``enter``)."""
    if key.startswith("Key."):
        name = key[4:]
        return MOD_GROUP.get(name, name)
    ch = vk_to_char(vk)
    if key.startswith("vk:") or (len(key) == 1 and not key.isprintable()):
        return ch or key
    return key


# ------------------------------------------------------------------- combos

def split_combo(combo: str) -> tuple[list[str], str]:
    """``"ctrl+shift+s"`` -> (["ctrl","shift"], "s"). A literal plus is ``"ctrl++"``."""
    combo = combo or ""
    if combo == "+":
        return [], "+"
    trailing_plus = combo.endswith("++")
    parts = [p.strip() for p in combo.strip("+").split("+")] if not trailing_plus else \
        [p.strip() for p in combo[:-2].split("+")] + ["+"]
    parts = [p for p in parts if p != ""]
    if not parts:
        return [], ""
    norm = []
    for p in parts:
        low = p.lower() if len(p) > 1 else p
        norm.append(ALIASES.get(low, low))
    mods = [p for p in norm[:-1]]
    main = norm[-1]
    return mods, main


def token_to_key(token: str):
    """Combo token -> pynput key."""
    if token in MOD_KEYS:
        return MOD_KEYS[token]
    if token.startswith("vk:"):
        return KeyCode.from_vk(int(token[3:]))
    if token.startswith("Key."):
        token = token[4:]
    if len(token) == 1:
        return KeyCode.from_char(token)
    if token == "space":
        return Key.space
    try:
        return Key[token]
    except KeyError:
        raise ValueError(f"Unknown key: {token!r}")


def parse_combo(combo: str):
    """-> (list of modifier pynput keys, main pynput key)."""
    mods, main = split_combo(combo)
    if not main:
        raise ValueError("Empty key")
    for m in mods:
        if m not in MOD_KEYS:
            raise ValueError(f"Unknown modifier: {m!r}")
    return [MOD_KEYS[m] for m in mods], token_to_key(main)


def valid_combo(combo: str) -> bool:
    try:
        parse_combo(combo)
        return True
    except ValueError:
        return False


def key_names() -> list[str]:
    return sorted({MOD_GROUP.get(k.name, k.name) for k in Key})


# ------------------------------------------------------------------ hotkeys

def parse_hotkey(text: str) -> tuple[frozenset[str], str] | None:
    """``"ctrl+shift+f8"`` -> ({"ctrl","shift"}, "f8"). None if empty/invalid."""
    text = (text or "").strip()
    if not text:
        return None
    mods, main = split_combo(text.lower())
    if not main or any(m not in MODS for m in mods):
        return None
    try:
        token_to_key(main)
    except ValueError:
        return None
    return frozenset(mods), main


def hotkey_token(key) -> str:
    """Pressed pynput key -> token comparable with ``parse_hotkey`` output."""
    s, vk = encode(key)
    t = base_token(s, vk)
    return t.lower() if len(t) == 1 else t


def hotkey_display(text: str) -> str:
    from .actions import combo_display
    return combo_display(text) if text else ""


_MAC_SYMBOLS = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}
_MAC_KEYS = {"enter": "↩", "esc": "⎋", "tab": "⇥", "space": "Space", "backspace": "⌫", "delete": "⌦",
             "up": "↑", "down": "↓", "left": "←", "right": "→"}


def shortcut_label(text: str) -> str:
    """Compact, platform-style label: ``⌃⌥R`` on macOS, ``Ctrl+Alt+R`` elsewhere."""
    if not text:
        return ""
    if sys.platform != "darwin":
        return hotkey_display(text)
    mods, main = split_combo(text)
    order = [m for m in ("ctrl", "alt", "shift", "cmd") if m in mods]
    key = _MAC_KEYS.get(main, main.upper() if len(main) <= 3 else main.replace("_", " ").title())
    return "".join(_MAC_SYMBOLS[m] for m in order) + key

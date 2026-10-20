"""Variables ``{name}`` and a small, safe expression evaluator."""

from __future__ import annotations

import ast
import datetime as _dt
import math
import operator
import os
import random
import re

_VAR = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_.:]*)\}")


def builtin(name: str, variables: dict):
    now = _dt.datetime.now()
    if name == "date":
        return now.strftime("%Y-%m-%d")
    if name == "time":
        return now.strftime("%H-%M-%S")
    if name == "datetime":
        return now.strftime("%Y-%m-%d %H:%M:%S")
    if name == "timestamp":
        return str(int(now.timestamp()))
    if name == "random":
        return str(random.randint(0, 999999))
    if name in ("mouse_x", "mouse_y"):
        try:
            from pynput.mouse import Controller
            x, y = Controller().position
            return str(int(x if name == "mouse_x" else y))
        except Exception:
            return "0"
    if name == "clipboard":
        from .system import get_clipboard
        return get_clipboard()
    if name.startswith("env:"):
        return os.environ.get(name[4:], "")
    return None


def substitute(text, variables: dict) -> str:
    """Replace ``{name}`` with variable values. ``{{``/``}}`` give literal braces.
    Unknown names are left untouched."""
    if text is None:
        return ""
    text = str(text)
    if "{" not in text and "}" not in text:
        return text

    def rep(m: re.Match) -> str:
        tok = m.group(0)
        if tok == "{{":
            return "{"
        if tok == "}}":
            return "}"
        name = m.group(1)
        if name in variables:
            return str(variables[name])
        b = builtin(name, variables)
        return tok if b is None else str(b)

    return _VAR.sub(rep, text)


# ------------------------------------------------------------------- evaluator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.Gt: operator.gt,
        ast.LtE: operator.le, ast.GtE: operator.ge}
_FUNCS = {
    "abs": abs, "min": min, "max": max, "round": round, "int": lambda x: int(float(x)),
    "float": float, "str": str, "len": len, "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
    "random": lambda a=0, b=100: random.randint(int(a), int(b)),
    "upper": lambda s: str(s).upper(), "lower": lambda s: str(s).lower(),
    "trim": lambda s: str(s).strip(), "replace": lambda s, a, b: str(s).replace(str(a), str(b)),
    "dist": lambda x1, y1, x2, y2: math.hypot(float(x2) - float(x1), float(y2) - float(y1)),
}


class ExprError(ValueError):
    pass


def _num(v):
    if isinstance(v, (int, float)):
        return v
    try:
        f = float(str(v).strip())
        return int(f) if f.is_integer() and "." not in str(v) else f
    except ValueError:
        return v


def _eval(node, variables):
    if isinstance(node, ast.Expression):
        return _eval(node.body, variables)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in variables:
            return _num(variables[node.id])
        if node.id in ("pi", "e"):
            return getattr(math, node.id)
        if node.id in ("True", "False"):
            return node.id == "True"
        raise ExprError(f"Unknown variable: {node.id}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
        v = _eval(node.operand, variables)
        return -_num(v) if isinstance(node.op, ast.USub) else (not v if isinstance(node.op, ast.Not) else _num(v))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        a, b = _eval(node.left, variables), _eval(node.right, variables)
        if isinstance(node.op, ast.Add) and (isinstance(a, str) or isinstance(b, str)):
            na, nb = _num(a), _num(b)
            if isinstance(na, (int, float)) and isinstance(nb, (int, float)):
                return na + nb
            return f"{a}{b}"
        a, b = _num(a), _num(b)
        if isinstance(node.op, ast.Pow) and abs(b) > 1000:
            raise ExprError("Exponent too large")
        return _BIN[type(node.op)](a, b)
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v, variables) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, variables)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, variables)
            if type(op) not in _CMP:
                raise ExprError("Unsupported comparison")
            l2, r2 = _num(left), _num(right)
            if isinstance(l2, (int, float)) and isinstance(r2, (int, float)):
                ok = _CMP[type(op)](l2, r2)
            else:
                ok = _CMP[type(op)](str(left), str(right))
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _eval(node.body if _eval(node.test, variables) else node.orelse, variables)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        args = [_eval(a, variables) for a in node.args]
        if node.func.id in ("abs", "min", "max", "round", "sqrt", "floor", "ceil", "dist"):
            args = [_num(a) for a in args]
        return _FUNCS[node.func.id](*args)
    raise ExprError("Unsupported expression")


def evaluate(expr, variables: dict):
    """Evaluate an expression. ``{var}`` placeholders are substituted first, and
    bare variable names may also be used directly (``n * 2``)."""
    src = str(expr if expr is not None else "").strip()
    if src == "":
        return ""
    # Substitute {var}; quote non-numeric values so they stay strings.
    def rep(m: re.Match) -> str:
        tok = m.group(0)
        if tok in ("{{", "}}"):
            return tok[0]
        name = m.group(1)
        val = variables.get(name)
        if val is None:
            val = builtin(name, variables)
        if val is None:
            return tok
        n = _num(val)
        return repr(n) if isinstance(n, (int, float)) else repr(str(val))
    src = _VAR.sub(rep, src)
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        raise ExprError(f"Invalid expression: {expr}")
    v = _eval(tree, variables)
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        v = int(v)
    return v


def number(expr, variables: dict, default: float = 0.0) -> float:
    try:
        v = evaluate(expr, variables)
        return float(v) if v != "" else default
    except (ExprError, ValueError, TypeError, ZeroDivisionError):
        try:
            return float(substitute(expr, variables))
        except (TypeError, ValueError):
            return default


def compare(left: str, op: str, right: str) -> bool:
    if op == "empty":
        return str(left).strip() == ""
    if op == "not_empty":
        return str(left).strip() != ""
    if op == "contains":
        return str(right).lower() in str(left).lower()
    if op == "not_contains":
        return str(right).lower() not in str(left).lower()
    a, b = _num(left), _num(right)
    if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        a, b = str(left), str(right)
    return {"==": operator.eq, "!=": operator.ne, "<": operator.lt, ">": operator.gt,
            "<=": operator.le, ">=": operator.ge}[op](a, b)

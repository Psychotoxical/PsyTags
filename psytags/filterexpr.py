"""Mp3tag filter expressions.

  <field> HAS <text>        substring, case-insensitive
  <field> IS <text>         whole value equals
  <field> MATCHES <regex>
  <field> GREATER/LESS <n>  numeric compare
  <field> PRESENT / MISSING
  NOT, AND, OR, parentheses. Field may be written as `artist` or `%artist%`;
  `"..."` quotes text. Plain words without operators match any field.
"""
from __future__ import annotations

import re
from typing import Callable

from . import script

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"]|"")*)"|([^\s()"]+))')
OPS = {"HAS", "IS", "MATCHES", "GREATER", "LESS", "PRESENT", "MISSING", "ABSENT", "EQUAL", "EQUALS"}


def _tokens(s: str) -> list[tuple[str, str]]:
    out = []
    pos = 0
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        if m.group(1):
            out.append(("(", "("))
        elif m.group(2):
            out.append((")", ")"))
        elif m.group(3) is not None:
            out.append(("str", m.group(3).replace('""', '"')))
        elif m.group(4):
            out.append(("word", m.group(4)))
    return out


def _value(track, fld: str) -> str:
    if "%" in fld or "$" in fld:
        return script.format(fld, track)
    if fld.upper() in ("_ALL", "ALL", "*"):
        return " ".join(" ".join(v) for v in track.fields.values()) + " " + track.filename
    return "\\\\".join(track.field(fld))


def _all_text(track) -> str:
    parts = [track.filename, track.folder]
    for v in track.fields.values():
        parts.extend(v)
    return "\n".join(parts).lower()


class _Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self, upper=True):
        if self.i >= len(self.t):
            return None
        k, v = self.t[self.i]
        return v.upper() if (upper and k == "word") else v

    def next(self):
        self.i += 1
        return self.t[self.i - 1]

    def parse(self):
        e = self.or_()
        return e

    def or_(self):
        left = self.and_()
        while self.peek() == "OR":
            self.next()
            right = self.and_()
            left = (lambda a, b: lambda t: a(t) or b(t))(left, right)
        return left

    def and_(self):
        left = self.not_()
        while True:
            p = self.peek()
            if p == "AND":
                self.next()
            elif p is None or p in ("OR", ")"):
                return left
            right = self.not_()
            left = (lambda a, b: lambda t: a(t) and b(t))(left, right)

    def not_(self):
        if self.peek() == "NOT":
            self.next()
            e = self.not_()
            return lambda t: not e(t)
        return self.atom()

    def atom(self):
        if self.i >= len(self.t):
            return lambda t: True
        k, v = self.t[self.i]
        if k == "(":
            self.next()
            e = self.or_()
            if self.peek() == ")":
                self.next()
            return e
        self.next()
        op = self.peek()
        if k in ("word", "str") and op in OPS:
            self.next()
            fld = v
            if op in ("PRESENT", "MISSING", "ABSENT"):
                want = op == "PRESENT"
                return lambda t, f=fld: bool(_value(t, f)) == want
            # Unquoted values run up to the next keyword: `artist IS Hidden Orchestra OR ...`
            parts = []
            while self.i < len(self.t):
                k2, v2 = self.t[self.i]
                if k2 in ("(", ")") or (k2 == "word" and v2 in ("AND", "OR")):
                    break
                parts.append(v2)
                self.next()
                if k2 == "str":
                    break
            return _compare(fld, op, " ".join(parts))
        word = v.lower()
        return lambda t: word in _all_text(t)


def _compare(fld: str, op: str, arg: str) -> Callable:
    if op == "HAS":
        words = arg.casefold().split() or [arg.casefold()]
        return lambda t: all(w in _value(t, fld).casefold() for w in words)
    if op == "IS":
        a = arg.casefold()
        return lambda t: any(v.casefold() == a for v in
                             (t.field(fld) if "%" not in fld and "$" not in fld else [_value(t, fld)]))
    if op == "MATCHES":
        try:
            rx = re.compile(arg, re.IGNORECASE)
        except re.error:
            return lambda t: False
        return lambda t: bool(rx.search(_value(t, fld)))
    if op in ("EQUAL", "EQUALS"):
        try:
            target = int(float(arg.replace(",", ".")))
        except ValueError:
            return lambda t: False

        def eq(t):
            m = re.match(r"\s*-?\d+", _value(t, fld))
            return bool(m) and int(m.group(0)) == target
        return eq
    sign = 1 if op == "GREATER" else -1
    try:
        n = float(arg.replace(",", "."))
    except ValueError:
        n = 0.0

    def cmp(t):
        m = re.match(r"\s*-?\d+(?:[.,]\d+)?", _value(t, fld))
        if not m:
            return False
        x = float(m.group(0).replace(",", "."))
        return (x - n) * sign > 0
    return cmp


def compile_filter(text: str) -> Callable:
    toks = _tokens(text)
    if not toks:
        return lambda t: True
    return _Parser(toks).parse()

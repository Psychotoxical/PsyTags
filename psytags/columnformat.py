"""What a column of the file list shows.

  %field%                 first value of a tag field or placeholder
  [ ... ]                 optional part: dropped when no field inside has a value
  $meta_sep(field,sep)    all values of a field, joined by sep
  $num(value,digits)      leading number of value, filled with zeros
"""
from __future__ import annotations

import re
from typing import Protocol


class Context(Protocol):
    def field(self, name: str) -> list[str]: ...


_CALL = re.compile(r"\$(meta_sep|num)\(", re.IGNORECASE)


def format(src: str, ctx: Context) -> str:
    return _Reader(src, ctx).sequence("")[0]


class _Reader:
    def __init__(self, text: str, ctx: Context):
        self.text, self.ctx, self.i = text, ctx, 0

    def sequence(self, stops: str) -> tuple[str, bool]:
        """(text, whether a field in it had a value) up to one of the ``stops``."""
        s, out, found, depth = self.text, [], False, 0
        while self.i < len(s):
            c = s[self.i]
            if "," in stops:                         # arguments: \, \( \) \\ and balanced ( ) are text
                if c == "\\" and s[self.i + 1:self.i + 2] in (",", "(", ")", "\\"):
                    out.append(s[self.i:self.i + 2])
                    self.i += 2
                    continue
                if c == "(":
                    depth += 1
                elif c == ")" and depth:
                    depth -= 1
                    out.append(c)
                    self.i += 1
                    continue
            if c in stops and not (c == "," and depth):
                break
            piece, hit = self._piece(c)
            out.append(piece)
            found = found or hit
        return "".join(out), found

    def _piece(self, c: str) -> tuple[str, bool]:
        s = self.text
        if c == "%" and s.find("%", self.i + 1) != -1:
            end = s.find("%", self.i + 1)
            values = self.ctx.field(s[self.i + 1:end])
            self.i = end + 1
            value = values[0] if values else ""
            return value, bool(value)
        if c == "[":
            self.i += 1
            body, found = self.sequence("]")
            self.i += 1                              # past the ]
            return (body, True) if found else ("", False)
        call = _CALL.match(s, self.i) if c == "$" else None
        if call:
            self.i = call.end()
            return self._call(call.group(1).lower())
        self.i += 1
        return c, False

    def _call(self, name: str) -> tuple[str, bool]:
        args: list[tuple[str, bool]] = []
        while self.i < len(self.text):
            args.append(self.sequence(",)"))
            at_end = self.text[self.i:self.i + 1] != ","
            self.i += 1
            if at_end:
                break
        first, first_found = args[0] if args else ("", False)
        second = args[1][0] if len(args) > 1 else ""
        if name == "num":
            number = re.match(r"\s*(\d+)", first)
            digits = re.match(r"\s*(\d+)", second)
            return str(int(number.group(1)) if number else 0).zfill(int(digits.group(1)) if digits else 0), first_found
        joined = (second if len(args) > 1 else ", ").join(self.ctx.field(first.strip("%")))
        return joined, bool(joined)

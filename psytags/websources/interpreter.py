"""Interpreter for Mp3tag Web Sources Framework parser scripts.

See docs/spec/websources.md (sections 2, 5, 6, 8). Undocumented points follow the
recommendations given there; they are marked "spec rec." below.
"""
from __future__ import annotations

import datetime
import json
import re

from .. import script as fmt_script


class ScriptError(Exception):
    def __init__(self, msg: str, line: int = 0):
        super().__init__(f"{msg} (Zeile {line})" if line else msg)
        self.line = line


# ---------------------------------------------------------------------------
# Lexing

_NUM = re.compile(r"-?\d+")


def _tokenize(line: str, lineno: int) -> list:
    """Split parameters: "quoted strings" (\\" and \\\\ escapes, other backslashes kept)
    and bare integers. A '#' outside quotes starts a trailing comment."""
    out: list = []
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c.isspace():
            i += 1
            continue
        if c == "#":
            break
        if c == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise ScriptError("end of line in quote", lineno)
                ch = line[i]
                if ch == "\\" and i + 1 < n and line[i + 1] in '"\\':
                    buf.append(line[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    break
                buf.append(ch)
                i += 1
            out.append("".join(buf))
            continue
        j = i
        while j < n and not line[j].isspace():
            j += 1
        tok = line[i:j]
        if not _NUM.fullmatch(tok):
            raise ScriptError(f"'{tok}' is not numeric", lineno)
        out.append(int(tok))
        i = j
    return out


def compile_script(lines: list[str]) -> list[tuple[str, list, int]]:
    prog = []
    for no, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"([A-Za-z_]+)\s*(.*)$", s)
        if not m:
            raise ScriptError(f"unknown command: {s}", no)
        cmd = m.group(1).lower()
        if cmd not in COMMANDS:
            raise ScriptError(f"unknown command: {m.group(1)}", no)
        prog.append((cmd, _tokenize(m.group(2), no), no))
    _match_blocks(prog)
    return prog


_IF = {"if", "ifnot", "ifoutput", "ifnotoutput", "ifgreater", "ifless", "ifvar", "ifnotvar"}
COMMANDS = _IF | {
    "else", "endif", "do", "while", "exit",
    "findline", "findlinenocase", "findinline", "gotoline", "gotochar", "moveline", "movechar",
    "skipchars", "joinlines", "joinuntil",
    "replace", "regexpreplace", "killtag", "unspace", "insert", "use", "useformat",
    "outputto", "say", "sayrest", "sayall", "sayuntil", "sayuntilml", "saynchars", "saynextnumber",
    "saynextword", "sayregexp", "sayoutput", "saynewline", "saydate", "sayduration", "sayformat",
    "sayvar", "set", "incoutput", "decoutput", "trim", "debug", "debugwriteinput", "savedata",
    "json", "json_select", "json_select_object", "json_unselect_object", "json_select_array",
    "json_select_many", "json_select_many_count", "json_foreach", "json_foreach_reverse",
    "json_foreach_end", "json_foreach_continue", "json_foreach_counter",
}


def _match_blocks(prog) -> None:
    """Annotate if/else/endif, do/while and json_foreach/_end with jump targets."""
    stack: list[tuple[str, int]] = []
    for i, (cmd, args, no) in enumerate(prog):
        if cmd in _IF:
            stack.append(("if", i))
        elif cmd == "else":
            if not stack or stack[-1][0] != "if":
                raise ScriptError("command 'else' without 'if'", no)
            stack.append(("else", i))
        elif cmd == "endif":
            if not stack or stack[-1][0] not in ("if", "else"):
                raise ScriptError("command 'endif' without 'if'", no)
            kind, j = stack.pop()
            if kind == "else":
                _, k = stack.pop()
                prog[k] = (*prog[k][:2], prog[k][2], {"else": j, "end": i})
                prog[j] = (*prog[j][:2], prog[j][2], {"end": i})
            else:
                prog[j] = (*prog[j][:2], prog[j][2], {"else": None, "end": i})
        elif cmd == "do":
            if any(k == "do" for k, _ in stack):
                raise ScriptError("nesting of do command not allowed", no)
            stack.append(("do", i))
        elif cmd == "while":
            if not stack or stack[-1][0] != "do":
                raise ScriptError("command 'while' without 'do'", no)
            _, j = stack.pop()
            prog[i] = (*prog[i][:2], prog[i][2], {"do": j})
        elif cmd in ("json_foreach", "json_foreach_reverse"):
            stack.append(("foreach", i))
        elif cmd == "json_foreach_end":
            if not stack or stack[-1][0] != "foreach":
                raise ScriptError("json_foreach_end without json_foreach", no)
            _, j = stack.pop()
            prog[j] = (*prog[j][:2], prog[j][2], {"end": i})
            prog[i] = (*prog[i][:2], prog[i][2], {"start": j})
    if stack:
        raise ScriptError(f"incomplete '{stack[-1][0]}' commands found", prog[stack[-1][1]][2])


# ---------------------------------------------------------------------------
# JSON helpers

class _Num(str):
    """Numbers keep their original lexeme (spec rec.)."""


def _parse_json(text: str):
    dec = json.JSONDecoder(parse_float=_Num, parse_int=_Num)
    text = text.lstrip()
    obj, _ = dec.raw_decode(text)
    return obj


def _render(v) -> str:
    if v is None or isinstance(v, (dict, list)):
        return ""
    if v is True:
        return "1"
    if v is False:
        return "0"
    return str(v)


class _Frame:
    __slots__ = ("start", "end", "items", "keys", "index", "depth", "saved")

    def __init__(self, start, end, items, keys, saved):
        self.start, self.end, self.items, self.keys = start, end, items, keys
        self.index = 0
        self.depth = 0
        self.saved = saved


# ---------------------------------------------------------------------------

class Interpreter:
    def __init__(self, text: str, variables: dict[str, str] | None = None,
                 current_url: str = "", current_preview: str = ""):
        self.raw = text
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.li = 0
        self.cur = self.lines[0] if self.lines else ""
        self.pos = 0
        self.outputs: dict[str, list] = {}          # lower name -> [name, text]
        self.current = "Output"
        self.trim = True
        self.vars = variables or {}
        self.special = {"currenturl": current_url, "currentpreview": current_preview}
        self.json_on = False
        self.json_used = False
        self.stack: list = []
        self.frames: list[_Frame] = []
        self._saved_text = None

    # -- buffers ---------------------------------------------------------------
    def out(self, name: str) -> str:
        k = name.lower()
        if k in self.special:
            return self.special[k]
        return self.outputs.get(k, ["", ""])[1]

    def _append(self, text: str) -> None:
        if not text:
            return
        k = self.current.lower()
        if k not in self.outputs:
            self.outputs[k] = [self.current, ""]
        self.outputs[k][1] += text

    def _say_input(self, text: str) -> None:
        self._append(text.strip() if self.trim else text)

    def _expand(self, s):
        # %name% in string parameters refers to outputs (only existing ones, spec rec.)
        if not isinstance(s, str) or "%" not in s:
            return s

        def rep(m):
            v = self.out(m.group(1))
            return v if v or m.group(1).lower() in self.special else m.group(0)
        return re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", rep, s)

    # -- line handling ---------------------------------------------------------
    def _goto_line(self, i: int) -> None:
        self.li = i
        self.cur = self.lines[i] if 0 <= i < len(self.lines) else ""
        self.pos = 0

    def _emit(self, text: str) -> None:
        """JSON commands put their result on the (current) input line."""
        self.cur = text
        self.pos = 0

    @property
    def rest(self) -> str:
        return self.cur[self.pos:]

    # -- JSON --------------------------------------------------------------------
    @property
    def obj(self):
        return self.stack[-1] if self.stack else None

    @property
    def floor(self) -> int:
        return self.frames[-1].depth if self.frames else 1

    def _lookup(self, key: str):
        o = self.obj
        if key == "":
            return o
        if isinstance(o, dict):
            return o.get(key)
        return None      # selecting a key on a scalar/array element yields null

    # -- execution ---------------------------------------------------------------
    def run(self, prog, max_steps: int = 2_000_000) -> None:
        pc = 0
        steps = 0
        do_count = 0
        n = len(prog)
        while pc < n:
            steps += 1
            if steps > max_steps:
                raise ScriptError("script did not terminate")
            entry = prog[pc]
            cmd, args, no = entry[0], entry[1], entry[2]
            meta = entry[3] if len(entry) > 3 else None
            args = [self._expand(a) for a in args]
            try:
                jump = self._exec(cmd, args, meta, pc)
            except ScriptError as e:
                if not e.line:
                    raise ScriptError(str(e), no) from None
                raise
            except (IndexError, TypeError, ValueError) as e:
                raise ScriptError(f"{cmd}: {e}", no) from None
            if jump == "exit":
                return
            if cmd == "while" and jump is not None:
                do_count += 1
                limit = args[1] if len(args) > 1 else 0
                if limit and do_count >= limit:
                    jump = None
                    do_count = 0
            if jump is None:
                pc += 1
            else:
                pc = jump

    def _cond(self, meta, ok: bool):
        if ok:
            return None
        if meta.get("else") is not None:
            return meta["else"] + 1
        return meta["end"] + 1

    def _exec(self, cmd, a, meta, pc):  # noqa: C901 (dispatch table)
        S = lambda i, d="": a[i] if i < len(a) and isinstance(a[i], str) else d  # noqa: E731
        N = lambda i, d=0: a[i] if i < len(a) and isinstance(a[i], int) else d   # noqa: E731

        # --- conditionals / loops
        if cmd in ("if", "ifnot"):
            s = S(0)
            hit = (self.rest == "") if s == "" else self.rest.startswith(s)
            return self._cond(meta, hit if cmd == "if" else not hit)
        if cmd in ("ifoutput", "ifnotoutput"):
            has = bool(self.out(S(0)))
            return self._cond(meta, has if cmd == "ifoutput" else not has)
        if cmd in ("ifgreater", "ifless"):
            m = re.match(r"\s*[+-]?\d+", self.rest)
            if not m:
                return self._cond(meta, False)
            v = int(m.group(0))
            return self._cond(meta, v > N(0) if cmd == "ifgreater" else v < N(0))
        if cmd in ("ifvar", "ifnotvar"):
            eq = str(self.vars.get(S(0), "")) == S(1)
            return self._cond(meta, eq if cmd == "ifvar" else not eq)
        if cmd == "else":
            return meta["end"] + 1
        if cmd == "endif":
            return None
        if cmd == "do":
            return None
        if cmd == "while":
            s = S(0)
            hit = self.rest.startswith(s) if s else self.rest == ""
            return meta["do"] + 1 if hit else None
        if cmd == "exit":
            return "exit"

        # --- navigation
        if cmd in ("findline", "findlinenocase"):
            s, occ, noerr = S(0), max(1, N(1, 1)), N(2) == 1
            nocase = cmd == "findlinenocase"
            needle = s.lower() if nocase else s
            found = 0
            i, start = self.li, self.pos
            while i < len(self.lines):
                hay = self.cur if i == self.li else self.lines[i]
                if nocase:
                    hay = hay.lower()
                if needle in hay[start:]:
                    found += 1
                    if found == occ:
                        self._goto_line(i)
                        return None
                i += 1
                start = 0
            if noerr:
                self._goto_line(len(self.lines))     # past the end (spec rec.)
                return None
            raise ScriptError(f"text not found: {s}")
        if cmd == "findinline":
            s, occ, noerr = S(0), max(1, N(1, 1)), N(2) == 1
            p = self.pos
            for _ in range(occ):
                idx = self.cur.find(s, p)
                if idx < 0:
                    if noerr:
                        return None
                    raise ScriptError(f"text not found: {s}")
                p = idx + len(s)
            self.pos = p
            return None
        if cmd == "gotoline":
            n = N(0)
            if not 1 <= n <= len(self.lines):
                raise ScriptError("line does not exist")
            self._goto_line(n - 1)
            return None
        if cmd == "gotochar":
            self.pos = max(0, min(N(0) - 1, len(self.cur)))
            return None
        if cmd == "moveline":
            t = self.li + N(0)
            if not 0 <= t < len(self.lines):
                if N(1) == 1:
                    self._goto_line(len(self.lines) if t >= 0 else 0)
                    return None
                raise ScriptError("line does not exist")
            self._goto_line(t)
            return None
        if cmd == "movechar":
            self.pos = max(0, min(self.pos + N(0), len(self.cur)))
            return None
        if cmd == "skipchars":
            chars = S(0)
            while self.pos < len(self.cur) and self.cur[self.pos] in chars:
                self.pos += 1
            return None
        if cmd == "joinlines":
            n = N(0)
            end = len(self.lines) if n < 0 else min(len(self.lines), self.li + 1 + n)
            joined = self.cur + "".join(self.lines[self.li + 1:end])
            self.lines[self.li:end] = [joined]
            self.cur = joined
            return None
        if cmd == "joinuntil":
            s = S(0)
            end = self.li
            while end < len(self.lines) - 1 and s not in (self.cur if end == self.li else self.lines[end]):
                end += 1
            joined = self.cur + "".join(self.lines[self.li + 1:end + 1])
            self.lines[self.li:end + 1] = [joined]
            self.cur = joined
            return None

        # --- input modification (current line only)
        if cmd == "replace":
            if S(0):
                self.cur = self.cur.replace(S(0), S(1))
            return None
        if cmd == "regexpreplace":
            try:
                self.cur = re.sub(_py_regex(S(0)), fmt_script.mp3tag_regex_repl(S(1)), self.cur)
            except re.error as e:
                raise ScriptError(f"regular expression error: {e}")
            self.pos = min(self.pos, len(self.cur))
            return None
        if cmd == "killtag":
            tag = S(0)
            pat = r"<[^>]*>" if tag == "*" else rf"</?{re.escape(tag)}\b[^>]*>"
            self.cur = re.sub(pat, S(1), self.cur, flags=re.IGNORECASE)
            self.pos = min(self.pos, len(self.cur))
            return None
        if cmd == "unspace":
            self.cur = self.cur.strip()
            self.pos = min(self.pos, len(self.cur))
            return None
        if cmd == "insert":
            self.cur = self.cur[:self.pos] + S(0) + self.cur[self.pos:]
            return None
        if cmd == "use":
            self._emit(S(0))
            return None
        if cmd == "useformat":
            self._emit(self._format(S(0), N(1) == 1))
            return None

        # --- output
        if cmd == "outputto":
            self.current = S(0)
            return None
        if cmd == "say":
            self._append(S(0))
            return None
        if cmd == "sayrest":
            self._say_input(self.rest)
            self.pos = len(self.cur)
            return None
        if cmd == "sayall":
            self._say_input(self.rest + "".join("\r\n" + l for l in self.lines[self.li + 1:]))
            return None
        if cmd == "sayuntil":
            s = S(0)
            idx = self.cur.find(s, self.pos) if s else -1
            if idx < 0:
                self._say_input(self.rest)
                self.pos = len(self.cur)
            else:
                self._say_input(self.cur[self.pos:idx])
                self.pos = idx
            return None
        if cmd == "sayuntilml":
            s = S(0)
            buf = []
            while True:
                idx = self.cur.find(s, self.pos) if s else -1
                if idx >= 0:
                    buf.append(self.cur[self.pos:idx])
                    self.pos = idx
                    break
                buf.append(self.rest)
                if self.li + 1 >= len(self.lines):
                    self.pos = len(self.cur)
                    break
                self._goto_line(self.li + 1)
            self._say_input("\r\n".join(buf))
            return None
        if cmd == "saynchars":
            n = N(0)
            if n >= 0:
                t = self.cur[self.pos:self.pos + n]
                self.pos = min(len(self.cur), self.pos + n)
            else:
                t = self.cur[max(0, self.pos + n):self.pos]
            self._say_input(t)
            return None
        if cmd == "saynextnumber":
            m = re.compile(r"[+-]*\d[\d.,]*").search(self.cur, self.pos)
            if m:
                self._say_input(m.group(0))
                self.pos = m.end()
            return None
        if cmd == "saynextword":
            m = re.compile(r"\w+").search(self.cur, self.pos)
            if m:
                self._say_input(m.group(0))
                self.pos = m.end()
            return None
        if cmd == "sayregexp":
            seg = self.rest
            stop = S(2) if len(a) > 2 else None
            if stop:
                idx = seg.find(stop)
                if idx < 0:
                    return None
                seg = seg[:idx]
            sep = S(1, " ") if len(a) > 1 else " "
            try:
                found = [m.group(0) for m in re.finditer(_py_regex(S(0)), seg)]
            except re.error as e:
                raise ScriptError(f"regular expression error: {e}")
            self._append(sep.join(found))
            return None
        if cmd == "sayoutput":
            self._append(self.out(S(0)))
            return None
        if cmd == "saynewline":
            self._append("\r\n")
            return None
        if cmd == "saydate":
            m = re.match(r"\s*-?\d+(\.\d+)?", self.rest)
            if m:
                v = float(m.group(0)) / (1000 if S(0) == "ms" else 1)
                self._append(datetime.datetime.fromtimestamp(v, datetime.timezone.utc).strftime("%Y-%m-%d"))
            return None
        if cmd == "sayduration":
            m = re.match(r"\s*-?\d+(\.\d+)?", self.rest)
            if m:
                v = float(m.group(0))
                unit = S(0)
                secs = v / 1000 if unit == "ms" else v * 60 if unit == "m" else v
                self._append(_duration(secs, N(1) == 1, N(2) == 1))
            return None
        if cmd == "sayformat":
            self._append(self._format(S(0), N(1) == 1))
            return None
        if cmd == "sayvar":
            self._append(str(self.vars.get(S(0), "")))
            return None
        if cmd == "set":
            name, val = S(0), S(1)
            if val:
                self.outputs[name.lower()] = [name, val]
            else:
                self.outputs.pop(name.lower(), None)
            return None
        if cmd == "incoutput":
            self.current = self.current + S(0)
            return None
        if cmd == "decoutput":
            self.current = self.current[:-1]
            return None
        if cmd == "trim":
            v = S(0).lower()
            if v not in ("on", "off"):
                raise ScriptError("use either on or off as parameter")
            self.trim = v == "on"
            return None
        if cmd in ("debug", "debugwriteinput", "savedata"):
            return None

        # --- JSON
        if cmd == "json":
            on = S(0).lower() == "on"
            if on:
                text = self.cur if S(1).lower() == "current" else self.raw
                try:
                    root = _parse_json(text)
                except ValueError as e:
                    raise ScriptError(f"JSON parse error: {e}")
                self._saved_text = (self.li, self.cur, self.pos)
                self.json_on = self.json_used = True
                self.stack = [root]
                self.frames = []
                self._emit("")
            else:
                self.json_on = False
                self.stack, self.frames = [], []
                if self._saved_text:
                    self.li, self.cur, self.pos = self._saved_text
            return None
        if not self.json_on and cmd.startswith("json_"):
            raise ScriptError("JSON mode is not enabled")
        if cmd == "json_select":
            self._emit(_render(self._lookup(S(0))))
            return None
        if cmd == "json_select_object":
            v = self._lookup(S(0))
            if isinstance(v, dict):
                self.stack.append(v)
                self._emit(S(0))
            else:
                self._emit("")
            return None
        if cmd == "json_unselect_object":
            if len(self.stack) > self.floor:
                self.stack.pop()
            return None
        if cmd == "json_select_array":
            arr = self._lookup(S(0))
            if not isinstance(arr, list):
                self._emit("")
                return None
            n = N(1, 1)
            if n == -1:
                self._emit(S(2).join(_render(e) for e in arr))
            elif 1 <= n <= len(arr):
                e = arr[n - 1]
                if isinstance(e, dict):
                    self.stack.append(e)
                    self._emit("")
                else:
                    self._emit(_render(e))
            else:
                self._emit("")
            return None
        if cmd in ("json_select_many", "json_select_many_count"):
            arr = self._lookup(S(0))
            key = S(1)
            vals = []
            if isinstance(arr, list):
                for e in arr:
                    if key:
                        v = _render(e.get(key)) if isinstance(e, dict) else ""
                    else:
                        v = _render(e)
                    vals.append(v)
            if cmd == "json_select_many_count":
                incl = N(2) == 1
                if not key:
                    self._emit(str(len(arr) if isinstance(arr, list) else 0))
                else:
                    self._emit(str(len([v for v in vals if v or incl])))
                return None
            if N(5) != 1:
                vals = [v for v in vals if v]
            if N(4) > 0:
                vals = vals[:N(4)]
            sep = S(2)
            last = S(3) if len(a) > 3 and isinstance(a[3], str) else sep
            text = sep.join(vals[:-1]) + last + vals[-1] if len(vals) > 1 else "".join(vals)
            self._emit(text)
            return None
        if cmd in ("json_foreach", "json_foreach_reverse"):
            v = self._lookup(S(0))
            if isinstance(v, dict):
                keys, items = list(v.keys()), list(v.values())
            elif isinstance(v, list):
                keys, items = None, list(v)
            else:
                keys, items = None, []
            if cmd == "json_foreach_reverse":
                items.reverse()
                if keys:
                    keys.reverse()
            self._emit(str(len(items)))
            if not items:                       # Mp3tag 3.36: body not run for empty arrays
                return meta["end"] + 1
            f = _Frame(pc, meta["end"], items, keys, len(self.stack))
            self.frames.append(f)
            self._enter(f)
            return None
        if cmd == "json_foreach_end" or cmd == "json_foreach_continue":
            if not self.frames:
                raise ScriptError("json_foreach_end without json_foreach")
            f = self.frames[-1]
            f.index += 1
            if f.index < len(f.items):
                self._enter(f)
                return f.start + 1
            self.frames.pop()
            del self.stack[f.saved:]
            return None if cmd == "json_foreach_end" else f.end + 1
        if cmd == "json_foreach_counter":
            if not self.frames:
                raise ScriptError("use only in json_foreach and json_foreach_reverse")
            f = self.frames[-1]
            if f.keys is not None:
                self._emit(str(f.keys[f.index]))
            else:
                self._emit(str(f.index + 1).zfill(N(0)))
            return None
        raise ScriptError(f"unknown command: {cmd}")

    def _enter(self, f: _Frame) -> None:
        del self.stack[f.saved:]
        self.stack.append(f.items[f.index])
        f.depth = len(self.stack)
        self._emit(str(len(f.items)))

    def _format(self, fmt: str, only_current: bool) -> str:
        interp = self

        class Ctx:
            _script_vars: dict = {}

            def field(self, name):
                n = name.lower()
                if n == "_current":
                    return [interp.cur] if interp.cur else []
                if only_current:
                    return []
                v = interp.out(n)
                return [v] if v else []
        return fmt_script.format(fmt, Ctx())

    # -- results ------------------------------------------------------------------
    def output_items(self) -> list[tuple[str, str]]:
        return [(name, text) for name, text in self.outputs.values()]


def _py_regex(rx: str) -> str:
    # Boost/Perl -> Python: possessive/atomic constructs are rare; \Q..\E unsupported.
    return rx


def _duration(secs: float, hours: bool, ms: bool) -> str:
    total = int(secs)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    out = f"{h}:{m:02d}:{s:02d}" if hours else f"{h * 60 + m}:{s:02d}"
    if ms:
        out += f".{int(round((secs - total) * 1000)):03d}"
    return out

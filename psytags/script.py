"""Mp3tag-compatible format strings / scripting.

Syntax:
  %field%        value of a tag field or placeholder (first value of multi-value fields)
  $func(a,b,..)  scripting function
  [ ... ]        optional section: dropped when every field referenced inside is empty
  '...'          literal text ('' for a single quote)

Values carry a truth flag (like foobar2000 title formatting, which Mp3tag
follows): a field reference is true when the field is non-empty, boolean
functions return empty text with a truth flag, $if & co. test that flag.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Protocol


class Context(Protocol):
    def field(self, name: str) -> list[str]: ...


@dataclass
class Val:
    text: str = ""
    truth: bool = False

    def __str__(self) -> str:
        return self.text


FALSE = Val("", False)
TRUE = Val("", True)


# ---------------------------------------------------------------------------
# Parser -> tiny AST

class Lit(str):
    pass


@dataclass
class Field:
    name: str


@dataclass
class Call:
    name: str
    args: list[list]


@dataclass
class Opt:
    body: list


class ParseError(ValueError):
    pass


def parse(src: str) -> list:
    nodes, pos = _parse_seq(src, 0, ())
    if pos != len(src):
        raise ParseError(f"Unexpected '{src[pos]}' at {pos}")
    return nodes


def _parse_seq(s: str, i: int, stops: tuple[str, ...]) -> tuple[list, int]:
    out: list = []
    buf: list[str] = []

    def flush():
        if buf:
            out.append(Lit("".join(buf)))
            buf.clear()

    in_args = "," in stops
    depth = 0
    while i < len(s):
        c = s[i]
        if in_args:
            # Inside function arguments: \, \( \) are literal (passed on to e.g. $regexp),
            # and bare parentheses must balance, so `$regexp(x,^(\w+) y,$1)` works.
            if c == "\\" and i + 1 < len(s) and s[i + 1] in ",()\\":
                buf.append(s[i:i + 2])
                i += 2
                continue
            if c == "(":
                depth += 1
            elif c == ")" and depth:
                depth -= 1
                buf.append(c)
                i += 1
                continue
        if c in stops and not (c == "," and depth):
            break
        if c == "'":
            j = s.find("'", i + 1)
            if j == -1:
                buf.append(s[i + 1:])
                i = len(s)
                continue
            if j == i + 1:
                buf.append("'")
            else:
                buf.append(s[i + 1:j])
            i = j + 1
        elif c == "%":
            j = s.find("%", i + 1)
            if j == -1:
                buf.append(s[i:])
                i = len(s)
                continue
            flush()
            out.append(Field(s[i + 1:j]))
            i = j + 1
        elif c == "$":
            m = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)\(", s[i:])
            if not m:
                if s.startswith("$$", i):
                    buf.append("$")
                    i += 2
                else:
                    buf.append("$")
                    i += 1
                continue
            flush()
            name = m.group(1).lower()
            i += m.end()
            args: list[list] = []
            if i < len(s) and s[i] == ")":
                i += 1
            else:
                while True:
                    arg, i = _parse_seq(s, i, (",", ")"))
                    args.append(arg)
                    if i >= len(s):
                        raise ParseError(f"Missing ')' for ${name}")
                    if s[i] == ")":
                        i += 1
                        break
                    i += 1  # ','
            out.append(Call(name, args))
        elif c == "[":
            flush()
            body, i = _parse_seq(s, i + 1, ("]",))
            if i < len(s):
                i += 1
            out.append(Opt(body))
        else:
            buf.append(c)
            i += 1
    flush()
    return out, i


# ---------------------------------------------------------------------------
# Evaluation

_cache: dict[str, list] = {}


def compile_(src: str) -> list:
    nodes = _cache.get(src)
    if nodes is None:
        try:
            nodes = parse(src)
        except ParseError:
            nodes = [Lit(src)]
        if len(_cache) > 2000:
            _cache.clear()
        _cache[src] = nodes
    return nodes


def format(src: str, ctx: Context) -> str:
    return _eval_seq(compile_(src), ctx).text


def evaluate(src: str, ctx: Context) -> Val:
    return _eval_seq(compile_(src), ctx)


class _Track:
    """Tracks whether an optional section referenced any non-empty field."""
    __slots__ = ("found", "any")

    def __init__(self):
        self.found = False
        self.any = False


def _eval_seq(nodes: list, ctx: Context, tr: _Track | None = None) -> Val:
    parts: list[str] = []
    truth = False
    for n in nodes:
        v = _eval(n, ctx, tr)
        parts.append(v.text)
        truth = truth or v.truth
    return Val("".join(parts), truth)


def _eval(n, ctx: Context, tr: _Track | None) -> Val:
    if isinstance(n, Lit):
        return Val(str(n), False)
    if isinstance(n, Field):
        vals = ctx.field(n.name)
        text = vals[0] if vals else ""
        if tr is not None:
            tr.any = True
            if text:
                tr.found = True
        return Val(text, bool(text))
    if isinstance(n, Opt):
        sub = _Track()
        v = _eval_seq(n.body, ctx, sub)
        if sub.found:
            if tr is not None:
                tr.any = True
                tr.found = True
            return Val(v.text, True)
        return FALSE
    if isinstance(n, Call):
        fn = FUNCTIONS.get(n.name)
        if fn is None:
            return Val(f"${n.name}(" + ",".join(_eval_seq(a, ctx).text for a in n.args) + ")")
        if n.name in LAZY:
            return fn(ctx, [lambda a=a: _eval_seq(a, ctx, tr) for a in n.args])
        args = [_eval_seq(a, ctx, tr) for a in n.args]
        v = fn(ctx, args)
        # $meta(), $meta_sep() and $list() count as placeholders inside [...]
        if tr is not None and n.name in ("meta", "meta_sep", "list"):
            tr.any = True
            if v.text:
                tr.found = True
        return v
    raise TypeError(n)


# ---------------------------------------------------------------------------
# Helpers

def _num(v) -> float:
    s = (v.text if isinstance(v, Val) else str(v)).strip()
    m = re.match(r"[-+]?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else 0.0


def _int(v) -> int:
    return int(_num(v))


def _fmt_num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else repr(x)


def _t(args, i, default="") -> str:
    return args[i].text if i < len(args) else default


def _s(text: str, *srcs: Val) -> Val:
    return Val(text, any(a.truth for a in srcs) if srcs else bool(text))


def _caps(text: str, sep_chars: str, lower_rest: bool) -> str:
    out = []
    cap_next = True
    for ch in text:
        if cap_next and ch.isalpha():
            out.append(ch.upper())
            cap_next = False
        else:
            out.append(ch.lower() if lower_rest and ch.isalpha() else ch)
        if ch in sep_chars or ch.isspace():
            cap_next = True
        elif ch.isalnum():
            cap_next = False
    return "".join(out)


# Words always start after whitespace; $caps(x,y) adds the characters of y.
CAPS_SEPARATORS = ""


# ---------------------------------------------------------------------------
# Function table. Signature: f(ctx, args) -> Val. Lazy functions get thunks.

FUNCTIONS: dict[str, Callable] = {}
LAZY = {"if", "if2", "if3", "ifgreater", "iflonger", "ifequal", "and", "or", "select"}


def fn(*names: str, lazy: bool = False):
    def deco(f):
        for n in names:
            FUNCTIONS[n] = f
            if lazy:
                LAZY.add(n)
        return f
    return deco


# -- control flow -----------------------------------------------------------

@fn("if")
def _if(ctx, a):
    if a and a[0]().truth:
        return a[1]() if len(a) > 1 else FALSE
    return a[2]() if len(a) > 2 else FALSE


@fn("if2")
def _if2(ctx, a):
    v = a[0]()
    return v if v.truth else (a[1]() if len(a) > 1 else FALSE)


@fn("if3")
def _if3(ctx, a):
    for th in a[:-1]:
        v = th()
        if v.truth:
            return v
    return a[-1]() if a else FALSE


@fn("ifgreater")
def _ifgreater(ctx, a):
    return a[2]() if _num(a[0]()) > _num(a[1]()) else a[3]()


@fn("iflonger")
def _iflonger(ctx, a):
    return a[2]() if len(a[0]().text) > _int(a[1]()) else a[3]()


@fn("ifequal")
def _ifequal(ctx, a):
    return a[2]() if _num(a[0]()) == _num(a[1]()) else a[3]()


@fn("select")
def _select(ctx, a):
    n = _int(a[0]())
    return a[n]() if 1 <= n < len(a) else FALSE


@fn("and")
def _and(ctx, a):
    return TRUE if all(th().truth for th in a) else FALSE


@fn("or")
def _or(ctx, a):
    return TRUE if any(th().truth for th in a) else FALSE


@fn("not")
def _not(ctx, a):
    return FALSE if a and a[0].truth else TRUE


@fn("xor")
def _xor(ctx, a):
    return TRUE if sum(1 for v in a if v.truth) % 2 == 1 else FALSE


@fn("eql", "stricmp")
def _eql(ctx, a):
    return TRUE if _t(a, 0).casefold() == _t(a, 1).casefold() else FALSE


@fn("neql")
def _neql(ctx, a):
    return FALSE if _t(a, 0).casefold() == _t(a, 1).casefold() else TRUE


@fn("strcmp")
def _strcmp(ctx, a):
    return TRUE if _t(a, 0) == _t(a, 1) else FALSE


def _cmp(op):
    def f(ctx, a):
        return TRUE if len(a) >= 2 and op(_int(a[0]), _int(a[1])) else FALSE
    return f


FUNCTIONS["grtr"] = FUNCTIONS["greater"] = _cmp(lambda x, y: x > y)
FUNCTIONS["less"] = _cmp(lambda x, y: x < y)
FUNCTIONS["geql"] = _cmp(lambda x, y: x >= y)
FUNCTIONS["leql"] = _cmp(lambda x, y: x <= y)


@fn("odd")
def _odd(ctx, a):
    return TRUE if _int(a[0]) % 2 == 1 else FALSE


@fn("even")
def _even(ctx, a):
    return TRUE if _int(a[0]) % 2 == 0 else FALSE


@fn("longer")
def _longer(ctx, a):
    return TRUE if len(_t(a, 0)) > len(_t(a, 1)) else FALSE


@fn("isdigit")
def _isdigit(ctx, a):
    return TRUE if _t(a, 0)[:1].isdigit() else FALSE


@fn("upper")
def _upper(ctx, a):
    return _s(_t(a, 0).upper(), *a[:1])


@fn("lower")
def _lower(ctx, a):
    return _s(_t(a, 0).lower(), *a[:1])


@fn("caps")
def _capsf(ctx, a):
    return _s(_caps(_t(a, 0), _t(a, 1, CAPS_SEPARATORS), True), *a[:1])


@fn("caps2")
def _caps2(ctx, a):
    return _s(_caps(_t(a, 0), _t(a, 1, CAPS_SEPARATORS), False), *a[:1])


@fn("caps3")
def _caps3(ctx, a):
    t = _t(a, 0)
    return _s(t[:1].upper() + t[1:].lower(), *a[:1])


@fn("left")
def _left(ctx, a):
    return _s(_t(a, 0)[:max(0, _int(a[1]))], *a[:1])


@fn("right")
def _right(ctx, a):
    n = max(0, _int(a[1]))
    t = _t(a, 0)
    return _s(t[-n:] if n else "", *a[:1])


@fn("mid")
def _mid(ctx, a):
    t, start = _t(a, 0), max(1, _int(a[1]))
    n = _int(a[2]) if len(a) > 2 else 1
    return _s(t[start - 1:start - 1 + n], *a[:1])


@fn("ord")
def _ord(ctx, a):
    t = _t(a, 0)
    return Val(str(ord(t[0])) if t else "0", True)


@fn("dedup")
def _dedup(ctx, a):
    sep = _t(a, 1, ",")
    ci = _t(a, 2) == "1"
    out, seen = [], set()
    for part in _t(a, 0).split(sep) if sep else [_t(a, 0)]:
        k = part.casefold() if ci else part
        if k not in seen:
            seen.add(k)
            out.append(part)
    return _s(sep.join(out), *a[:1])


@fn("distance")
def _distance(ctx, a):
    x, y = _t(a, 0), _t(a, 1)
    prev = list(range(len(y) + 1))
    for i, cx in enumerate(x, 1):
        cur = [i]
        for j, cy in enumerate(y, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cx != cy)))
        prev = cur
    return Val(str(prev[-1]), True)


@fn("sort")
def _sortf(ctx, a):
    sep = _t(a, 1, ",")
    parts = _t(a, 0).split(sep) if sep else [_t(a, 0)]

    def key(s):
        return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower())
                for t in re.split(r"(\d+)", s) if t]
    return _s(sep.join(sorted(parts, key=key)), *a[:1])


@fn("folderdepth")
def _folderdepth(ctx, a):
    parts = [p for p in re.split(r"[\\/]", _t(a, 0)) if p and not re.fullmatch(r"[A-Za-z]:", p)]
    return Val(str(len(parts)), True)


@fn("fmtnum")
def _fmtnum(ctx, a):
    n = _int(a[0]) if a else 0
    return Val(f"{n:,}".replace(",", "."), True)


@fn("fmtduration")
def _fmtduration(ctx, a):
    x = _num(a[0]) if a else 0.0
    unit = _t(a, 1, "s") or "s"
    secs = x * 60 if unit == "m" else x / 1000 if unit == "ms" else x
    show_h, show_ms = _t(a, 2) == "1", _t(a, 3) == "1"
    total = int(secs)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    out = f"{h}:{m:02d}:{s:02d}" if show_h else f"{h * 60 + m}:{s:02d}"
    if show_ms:
        out += f".{int(round((secs - total) * 1000)):03d}"
    return Val(out, True)


@fn("rand")
def _rand(ctx, a):
    import random
    return Val(str(random.randint(0, 32767)), True)


@fn("uuid")
def _uuid(ctx, a):
    import uuid
    return Val(str(uuid.uuid4()), True)


@fn("getenv")
def _getenv(ctx, a):
    import os
    name = _t(a, 0)
    if name.upper() in ("MP3TAGAPPDATA", "PSYTAGAPPDATA"):
        from .config import config_dir
        v = config_dir()
    elif name.upper() in ("MP3TAGAPP", "PSYTAGAPP"):
        v = os.path.dirname(os.path.abspath(__file__))
    else:
        v = os.environ.get(name, "")
    return Val(v, bool(v))


# (name, value format string) of the visible File List columns; set by the UI.
COLUMNS: list[tuple[str, str]] = []


@fn("columnnames")
def _columnnames(ctx, a):
    pre, post = _t(a, 0), _t(a, 1)
    return Val("".join(pre + n + post for n, _ in COLUMNS), bool(COLUMNS))


@fn("columnvalues")
def _columnvalues(ctx, a):
    pre, post = _t(a, 0), _t(a, 1)
    if "columnvalues" in (fmt for _, fmt in COLUMNS):
        return FALSE
    return Val("".join(pre + format(v, ctx) + post for _, v in COLUMNS), bool(COLUMNS))


@fn("len")
def _len(ctx, a):
    return Val(str(len(_t(a, 0))), True)


@fn("trim")
def _trim(ctx, a):
    if len(a) > 1 and a[1].text:
        return _s(_t(a, 0).strip(a[1].text), *a[:1])
    return _s(_t(a, 0).strip(), *a[:1])


@fn("trimleft", "triml")
def _triml(ctx, a):
    return _s(_t(a, 0).lstrip(_t(a, 1) or None), *a[:1])


@fn("trimright", "trimr")
def _trimr(ctx, a):
    return _s(_t(a, 0).rstrip(_t(a, 1) or None), *a[:1])


@fn("replace")
def _replace(ctx, a):
    t = _t(a, 0)
    for i in range(1, len(a) - 1, 2):
        if a[i].text:
            t = t.replace(a[i].text, a[i + 1].text)
    return _s(t, *a[:1])


def mp3tag_regex_repl(repl: str) -> str:
    """Mp3tag uses $1..$9 for groups; Python uses \\1."""
    out = re.sub(r"\\(?![0-9gnrt])", r"\\\\", repl)
    return re.sub(r"\$(\d)", r"\\\1", out)


@fn("regexp")
def _regexp(ctx, a):
    # 4th parameter: 1 = ignore case (default), 0 = case-sensitive
    flags = 0 if (len(a) > 3 and a[3].text.strip() == "0") else re.IGNORECASE
    try:
        t = re.sub(_t(a, 1), mp3tag_regex_repl(_t(a, 2)), _t(a, 0), flags=flags)
    except re.error:
        t = _t(a, 0)
    return _s(t, *a[:1])


@fn("strstr")
def _strstr(ctx, a):
    return Val(str(_t(a, 0).find(_t(a, 1)) + 1), True)


@fn("strrstr")
def _strrstr(ctx, a):
    return Val(str(_t(a, 0).rfind(_t(a, 1)) + 1), True)


@fn("strchr")
def _strchr(ctx, a):
    return Val(str(_t(a, 0).find(_t(a, 1)[:1]) + 1), True)


@fn("strrchr")
def _strrchr(ctx, a):
    return Val(str(_t(a, 0).rfind(_t(a, 1)[:1]) + 1), True)


@fn("repeat")
def _repeat(ctx, a):
    return Val(_t(a, 0) * max(0, _int(a[1])), True)


@fn("pad")
def _pad(ctx, a):
    t = _t(a, 0)
    ch = _t(a, 2, " ")[:1] or " "
    return _s(t.ljust(_int(a[1]), ch), *a[:1])


@fn("cutLeft", "cutleft")
def _cutleft(ctx, a):
    return _s(_t(a, 0)[_int(a[1]):], *a[:1])


@fn("cutRight", "cutright")
def _cutright(ctx, a):
    n = _int(a[1])
    t = _t(a, 0)
    return _s(t[:-n] if n else t, *a[:1])


@fn("reverse")
def _reverse(ctx, a):
    return _s(_t(a, 0)[::-1], *a[:1])


@fn("num")
def _numf(ctx, a):
    t = _t(a, 0)
    m = re.match(r"\s*(\d+)", t)
    n = int(m.group(1)) if m else 0
    return _s(str(n).zfill(max(0, _int(a[1]))), *a[:1])


@fn("char")
def _char(ctx, a):
    try:
        return Val(chr(_int(a[0])), True)
    except (ValueError, OverflowError):
        return FALSE


@fn("ansi")
def _ansi(ctx, a):
    return _s(_t(a, 0).encode("cp1252", "replace").decode("cp1252"), *a[:1])


@fn("validate")
def _validate(ctx, a):
    # Backslash is kept (folder separator); a drive spec like D: keeps its colon.
    rep = _t(a, 1)
    t = _t(a, 0)
    drive = t[:2] if re.match(r"[A-Za-z]:", t) else ""
    return _s(drive + re.sub(r'[/:*?"<>|\n\r\t]', lambda m: rep, t[len(drive):]), *a[:1])


@fn("sortname")
def _sortname(ctx, a):
    t = _t(a, 0)
    parts = t.rsplit(" ", 1)
    return _s(f"{parts[1]}, {parts[0]}" if len(parts) == 2 else t, *a[:1])


@fn("abbr")
def _abbr(ctx, a):
    words = re.findall(r"[\w']+", _t(a, 0))
    return _s("".join(w[0] for w in words), *a[:1])


@fn("crc")
def _crc(ctx, a):
    import zlib
    return Val("%08X" % (zlib.crc32(_t(a, 0).encode("utf-8")) & 0xFFFFFFFF), True)


@fn("lng")
def _lng(ctx, a):
    return Val(str(len(_t(a, 0).encode("utf-8"))), True)


@fn("removeDiacritics", "removediacritics")
def _rmdia(ctx, a):
    t = unicodedata.normalize("NFKD", _t(a, 0))
    return _s("".join(c for c in t if not unicodedata.combining(c)), *a[:1])


@fn("urlencode")
def _urlencode(ctx, a):
    from urllib.parse import quote
    return _s(quote(_t(a, 0), safe=""), *a[:1])


@fn("hex")
def _hex(ctx, a):
    return Val("%X" % _int(a[0]), True)


@fn("put", "puts")
def _put(ctx, a):
    _vars(ctx)[_t(a, 0)] = _t(a, 1)
    return Val(_t(a, 1), True)


@fn("get")
def _get(ctx, a):
    v = _vars(ctx).get(_t(a, 0), "")
    return Val(v, bool(v))


def _vars(ctx) -> dict:
    d = getattr(ctx, "_script_vars", None)
    if d is None:
        d = {}
        try:
            ctx._script_vars = d
        except AttributeError:
            pass
    return d


# -- arithmetic -------------------------------------------------------------

def _arith(op):
    def f(ctx, a):
        try:
            return Val(_fmt_num(op(*[_int(x) for x in a])), True)
        except (ZeroDivisionError, TypeError, ValueError):
            return Val("0", True)
    return f


def _fold(op):
    def f(*x):
        acc = x[0]
        for y in x[1:]:
            acc = op(acc, y)
        return acc
    return f


FUNCTIONS["add"] = _arith(lambda *x: sum(x))
FUNCTIONS["sub"] = _arith(_fold(lambda x, y: x - y))
FUNCTIONS["mul"] = _arith(_fold(lambda x, y: x * y))
FUNCTIONS["div"] = _arith(_fold(lambda x, y: int(x / y)))
FUNCTIONS["mod"] = _arith(lambda x, y: int(math.fmod(x, y)))
FUNCTIONS["neg"] = _arith(lambda x: -x)
FUNCTIONS["max"] = _arith(lambda *x: max(x))
FUNCTIONS["min"] = _arith(lambda *x: min(x))


@fn("fmtDate", "fmtdate")
def _fmtdate(ctx, a):
    import datetime
    try:
        ts = datetime.datetime.fromtimestamp(_num(a[1]))
    except (OSError, OverflowError, ValueError):
        return FALSE
    fmt = _t(a, 0)
    # Mp3tag uses yyyy-MM-dd HH:mm:ss style tokens.
    for k, v in (("yyyy", "%Y"), ("yy", "%y"), ("MM", "%m"), ("dd", "%d"),
                 ("HH", "%H"), ("mm", "%M"), ("ss", "%S")):
        fmt = fmt.replace(k, v)
    return Val(ts.strftime(fmt), True)


# -- multi-value fields -----------------------------------------------------

def _values(ctx, name: str) -> list[str]:
    return ctx.field(name.strip("%"))


@fn("meta")
def _meta(ctx, a):
    vals = _values(ctx, _t(a, 0))
    if len(a) > 1:
        i = _int(a[1])
        v = vals[i] if 0 <= i < len(vals) else ""
    else:
        v = ", ".join(vals)
    return Val(v, bool(v))


@fn("meta_sep")
def _meta_sep(ctx, a):
    vals = _values(ctx, _t(a, 0))
    sep = _t(a, 1, ", ")
    if len(a) > 2 and len(vals) > 1:
        v = sep.join(vals[:-1]) + _t(a, 2) + vals[-1]
    else:
        v = sep.join(vals)
    return Val(v, bool(v))


@fn("meta_num")
def _meta_num(ctx, a):
    return Val(str(len(_values(ctx, _t(a, 0)))), True)


@fn("list")
def _list(ctx, a):
    """$list(x,y,z,v): for every stored field: x + NAME + y + values (joined by v) + z."""
    fields = getattr(ctx, "fields", None) or {}
    pre, mid, post = _t(a, 0), _t(a, 1), _t(a, 2)
    sep = _t(a, 3, ",") if len(a) > 3 else ","
    v = "".join(f"{pre}{k}{mid}{sep.join(vals)}{post}" for k, vals in sorted(fields.items()))
    return Val(v, bool(v))


@fn("filename")
def _filename(ctx, a):
    import os
    t = _t(a, 0).replace("\\", "/")
    return _s(os.path.splitext(os.path.basename(t))[0], *a[:1])


@fn("ext")
def _ext(ctx, a):
    import os
    return _s(os.path.splitext(_t(a, 0))[1].lstrip("."), *a[:1])


@fn("directory")
def _directory(ctx, a):
    parts = [p for p in re.split(r"[\\/]", _t(a, 0)) if p]
    n = _int(a[1]) if len(a) > 1 else 1
    if parts and "." in parts[-1]:
        parts = parts[:-1]
    return Val(parts[-n] if 0 < n <= len(parts) else "", True)


@fn("tag")
def _tagf(ctx, a):
    return Val(", ".join(ctx.field("_TAG")), True)

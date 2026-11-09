"""Track and disc numbers of one album, in the format chosen in the options."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

from . import config


@dataclass
class NumberFormat:
    track_zeros: bool = True
    track_total: bool = True
    disc_on: bool = True
    disc_zeros: bool = True
    disc_total: bool = True

    @classmethod
    def load(cls) -> "NumberFormat":
        s = config.settings()
        return cls(**{f.name: s.value(f"numbering/{f.name}", f.default) in (True, "true") for f in fields(cls)})

    def save(self) -> None:
        s = config.settings()
        for name, value in asdict(self).items():
            s.setValue(f"numbering/{name}", value)


def _number(n: int, total: int, zeros: bool, with_total: bool) -> str:
    width = max(2, len(str(total))) if zeros else 0
    text = str(n).zfill(width)
    return f"{text}/{str(total).zfill(width)}" if with_total else text


def _disc_of(track) -> str:
    """"1/2" and "01" both count as disc 1; empty if the file names no disc."""
    return (track.get("DISCNUMBER") or [""])[0].partition("/")[0].strip().lstrip("0")


def plan(tracks: list, fmt: NumberFormat) -> dict[int, dict[str, str]]:
    """Track id -> new TRACK and DISCNUMBER, for the files of one album in album order. Files
    that already belong to several discs keep that split and count from 1 on each disc."""
    several = len({_disc_of(t) for t in tracks if _disc_of(t)}) > 1
    discs: list[list] = []
    previous = None
    for t in tracks:
        disc = _disc_of(t)
        if not discs or (several and disc != previous):
            discs.append([])
        discs[-1].append(t)
        previous = disc
    out: dict[int, dict[str, str]] = {}
    for d, group in enumerate(discs, 1):
        for n, t in enumerate(group, 1):
            values = {"TRACK": _number(n, len(group), fmt.track_zeros, fmt.track_total)}
            if fmt.disc_on or several:
                values["DISCNUMBER"] = _number(d, len(discs), fmt.disc_zeros, fmt.disc_total)
            out[id(t)] = values
    return out


def example(fmt: NumberFormat) -> tuple[str, str]:
    """How track 3 of 12 on disc 1 of 2 would look; the disc is empty if it is not written."""
    return (_number(3, 12, fmt.track_zeros, fmt.track_total),
            _number(1, 2, fmt.disc_zeros, fmt.disc_total) if fmt.disc_on else "")

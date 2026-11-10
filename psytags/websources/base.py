"""What every tag source delivers, whatever its server looks like."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Album:
    fields: dict[str, list[str]] = field(default_factory=dict)  # per-track lists or 1 common value
    per_track: set[str] = field(default_factory=set)
    tracks: int = 0
    lengths: list[str] = field(default_factory=list)
    cover_url: str = ""

    def value(self, name: str, i: int) -> str:
        vals = self.fields.get(name, [])
        if name not in self.per_track:
            return vals[0] if vals else ""
        return vals[i] if i < len(vals) else ""


class TagSource(Protocol):
    name: str
    search_fields: tuple[str, ...]      # labels of the search form
    index_columns: tuple[str, ...]      # columns of the result list

    def prefill(self, tracks: list, album: str | None = None) -> list[str]:
        """The search form filled from the tags; ``album`` replaces the album title."""

    def search(self, values: list[str]) -> list[dict[str, str]]:
        """One row per release found. Raises http.FetchError."""

    def album(self, row: dict[str, str]) -> Album:
        """The full release behind a row. Raises http.FetchError."""

    def cover(self, album: Album) -> bytes | None:
        """The front cover of a release, None if it has none."""

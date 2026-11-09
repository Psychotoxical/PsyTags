"""Undo/redo for tag writes and renames."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from . import convert


@dataclass
class _Change:
    track: object
    before_path: str
    after_path: str
    before_fields: dict
    after_fields: dict
    before_covers: list
    after_covers: list


@dataclass
class Operation:
    label: str
    changes: list[_Change] = field(default_factory=list)


class Recorder:
    """Collects before-states, then completes them with after-states."""

    def __init__(self, label: str):
        self.op = Operation(label)
        self._before: dict[int, tuple] = {}

    def before(self, track) -> None:
        if id(track) not in self._before:
            self._before[id(track)] = (track, track.path, copy.deepcopy(track._saved.fields),
                                       list(track._saved.covers))

    def finish(self) -> Operation | None:
        for track, path, fields, covers in self._before.values():
            c = _Change(track, path, track.path, fields, copy.deepcopy(track._saved.fields),
                        covers, list(track._saved.covers))
            if c.before_path != c.after_path or c.before_fields != c.after_fields \
                    or c.before_covers != c.after_covers:
                self.op.changes.append(c)
        return self.op if self.op.changes else None


class UndoStack:
    def __init__(self, limit: int = 100):
        self.undo_ops: list[Operation] = []
        self.redo_ops: list[Operation] = []
        self.limit = limit

    def push(self, op: Operation | None) -> None:
        if op is None:
            return
        self.undo_ops.append(op)
        del self.undo_ops[:-self.limit]
        self.redo_ops.clear()

    def can_undo(self) -> bool:
        return bool(self.undo_ops)

    def can_redo(self) -> bool:
        return bool(self.redo_ops)

    def undo(self, opts) -> Operation | None:
        """Undo the last operation. On error the stacks stay unchanged and
        already reverted files are restored before the exception propagates."""
        if not self.undo_ops:
            return None
        op = self.undo_ops[-1]
        _apply(op, opts, forward=False)
        self.undo_ops.pop()
        self.redo_ops.append(op)
        return op

    def redo(self, opts) -> Operation | None:
        if not self.redo_ops:
            return None
        op = self.redo_ops[-1]
        _apply(op, opts, forward=True)
        self.redo_ops.pop()
        self.undo_ops.append(op)
        return op


def _apply_change(c: _Change, opts, forward: bool) -> None:
    t = c.track
    target_path = c.after_path if forward else c.before_path
    fields = c.after_fields if forward else c.before_fields
    covers = c.after_covers if forward else c.before_covers
    if t.path != target_path:
        convert.rename(t, target_path)
    if t._saved.fields != fields or t._saved.covers != covers:
        t.data.fields = copy.deepcopy(fields)
        t.data.covers = list(covers)
        try:
            t.save(id3_version=opts.id3_version, write_id3v1=opts.write_id3v1,
                   keep_mtime=opts.keep_mtime)
        except Exception:
            t.revert()
            raise


def _apply(op: Operation, opts, forward: bool) -> None:
    """Apply all changes of ``op``; roll back the finished ones if one fails."""
    changes = op.changes if forward else list(reversed(op.changes))
    done: list[_Change] = []
    try:
        for c in changes:
            done.append(c)
            _apply_change(c, opts, forward)
    except Exception:
        for c in reversed(done):
            try:
                _apply_change(c, opts, not forward)
            except Exception:
                pass                          # best effort; report the original error
        raise

"""Low-level GEDCOM lexing and tree building (spec 5.5.1 §1).

A GEDCOM file is a flat list of lines::

    level [@xref@] TAG [value]

Hierarchy is expressed purely by the integer ``level``. ``CONC``/``CONT`` lines
continue the *value* of their parent (concatenation / new line respectively).
This module turns raw text into a forest of :class:`GedNode` records (the level-0
lines) with nested children, which the reader then interprets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# level, optional xref, tag, optional value
_LINE_RE = re.compile(r"^(\d+)\s+(@[^@]+@\s+)?([A-Za-z0-9_]+)(?:\s(.*))?$")


@dataclass
class GedLine:
    level: int
    tag: str
    xref: str | None = None
    value: str = ""


@dataclass
class GedNode:
    """A GEDCOM structure: a tag with a value and nested sub-structures."""

    level: int
    tag: str
    xref: str | None = None
    value: str = ""
    children: list[GedNode] = field(default_factory=list)

    def first(self, tag: str) -> GedNode | None:
        """First direct child with ``tag``, or None."""
        for child in self.children:
            if child.tag == tag:
                return child
        return None

    def all(self, tag: str) -> list[GedNode]:
        """All direct children with ``tag``."""
        return [c for c in self.children if c.tag == tag]

    def value_of(self, tag: str, default: str | None = None) -> str | None:
        """Value of the first direct child with ``tag`` (stripped), else ``default``."""
        node = self.first(tag)
        if node is None:
            return default
        return node.value or default


def tokenize(text: str) -> list[GedLine]:
    """Split GEDCOM text into structured lines, skipping blanks and the BOM."""
    text = text.lstrip("﻿")
    lines: list[GedLine] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = _LINE_RE.match(raw.rstrip("\r\n"))
        if not m:
            # Tolerate malformed lines rather than aborting the whole import.
            continue
        level = int(m.group(1))
        xref = m.group(2).strip() if m.group(2) else None
        tag = m.group(3)
        value = m.group(4) or ""
        lines.append(GedLine(level=level, tag=tag, xref=xref, value=value))
    return lines


def build_forest(lines: list[GedLine]) -> list[GedNode]:
    """Assemble tokenized lines into a forest of level-0 records.

    ``CONC`` (concatenate) and ``CONT`` (continue on a new line) fold into the
    value of the nearest enclosing non-continuation node.
    """
    roots: list[GedNode] = []
    # stack[i] is the currently-open node at level i.
    stack: list[GedNode] = []

    for line in lines:
        if line.tag in ("CONC", "CONT"):
            # Continuation applies to the node one level up (its parent).
            if not stack:
                continue
            parent = stack[min(line.level, len(stack)) - 1]
            parent.value += ("\n" if line.tag == "CONT" else "") + line.value
            continue

        node = GedNode(level=line.level, tag=line.tag, xref=line.xref, value=line.value)
        # Trim the stack back to this node's parent depth.
        del stack[line.level :]
        if line.level == 0:
            roots.append(node)
        else:
            if not stack:
                # Orphan sub-record with no parent; treat as a root defensively.
                roots.append(node)
            else:
                stack[line.level - 1].children.append(node)
        stack.append(node)

    return roots


def parse_records(text: str) -> list[GedNode]:
    """Convenience: text → forest of level-0 records."""
    return build_forest(tokenize(text))

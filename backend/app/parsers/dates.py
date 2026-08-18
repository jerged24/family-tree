"""Best-effort parsing of GEDCOM date strings into a sortable ``date``.

The original GEDCOM string is always preserved verbatim on the Event; this only
produces a ``date_sort`` value for ordering. Approximation/range qualifiers
(``ABT``, ``EST``, ``BEF``, ``AFT``, ``BET x AND y`` …) are tolerated by taking
the first concrete day/month/year found.
"""

from __future__ import annotations

import re
from datetime import date

_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

_DATE_RE = re.compile(
    r"(?:(?P<day>\d{1,2})\s+)?(?:(?P<mon>[A-Z]{3})\s+)?(?P<year>\d{3,4})",
    re.IGNORECASE,
)


def parse_gedcom_date(value: str | None) -> date | None:
    """Return a sortable date from a GEDCOM DATE value, or ``None`` if unparseable."""
    if not value:
        return None
    m = _DATE_RE.search(value)
    if not m:
        return None
    year = int(m.group("year"))
    month = _MONTHS.get((m.group("mon") or "").upper(), 1)
    day = int(m.group("day")) if m.group("day") else 1
    try:
        return date(year, month, day)
    except ValueError:
        # e.g. day out of range for the month — fall back to the first of the month.
        try:
            return date(year, month, 1)
        except ValueError:
            return None

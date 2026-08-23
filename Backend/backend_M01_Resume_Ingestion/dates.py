"""Date ranges, in the forms Indian student resumes actually use (§3.2.3).

*"Dates in Indian resumes are chaotic: `Jan'25`, `01/2025`, `2025-Present`,
`Jan 2025 - Apr 2025`, `Spring 2025`, `2 months`."*

── Why this is its own module ─────────────────────────────────────────────────

Two places need it and they need it to agree. `entities.py` reads ranges to
build the education and role timeline; `claims.py` reads them to find gaps and
reversed ranges. Two regexes drifted apart once already — a format one accepted
and the other did not meant a gap flag firing against a timeline that did not
contain the dates it was talking about.

── The two-digit year rule ────────────────────────────────────────────────────

`Jan'25` and `2022-26` are both extremely common and both need a century
guessed. The guess is 20xx, unconditionally, and that is safe here for a reason
specific to this module: these are current students. A resume saying `'99` means
1999 to nobody who is applying for a campus placement in 2026.

The apostrophe is REQUIRED on a two-digit start (`Jan'25`, never `Jan 25`) but
optional on a two-digit end (`2022-26`), because the start already established
that this is a year range. Without that asymmetry, `Section 12 - 15` parses as
a date range.

── Three shapes, and why they are not one ─────────────────────────────────────

`RANGE`     a period with two ends. The only shape that can produce a gap.
`SINGLE`    a point: "Spring 2025". It dates a thing; it does not span one.
`DURATION`  a length: "2 months". It has no position on a timeline at all.

Collapsing the last two into `RANGE` is the tempting simplification and it is
wrong in a way a student would see: a duration with an invented start date puts
a fabricated period into the gap check, and the output of that is a red flag
shown to somebody about something they never wrote.
"""

from __future__ import annotations

import re
from datetime import date

_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()

#: A year: four digits, or two with an apostrophe.
_Y_START = r"(?:19|20)\d{2}|'\d{2}"
#: An end year may drop the apostrophe — the start has already established that
#: we are reading years.
_Y_END = r"(?:19|20)\d{2}|'?\d{2}"

OPEN_ENDED = frozenset({"present", "current", "now", "ongoing", "till date", "date"})

#: Month names, long and short. Spelled out rather than `[A-Za-z]{3,9}` — that
#: shorthand absorbs whatever word happens to precede the year, so
#: `B.Tech CSE 2022-26` produced a range whose `raw` was "CSE 2022-26". The
#: parse was right (an unknown month falls back to January) and the field shown
#: to a student was not, which is the worse half.
_MONTH_NAMES = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)

#: Seasons, which §3.2.3 names ("Spring 2025"). Indian academic calendars use
#: them loosely, so each maps to the month a term of that name usually starts —
#: an approximation, and a far better one than "no date at all", which is what
#: these produced before and which scores as `recency = 0.5`.
_SEASONS: dict[str, int] = {
    "spring": 1,
    "summer": 5,
    "monsoon": 7,
    "autumn": 8,
    "fall": 8,
    "winter": 11,
}
_SEASON_NAMES = "|".join(_SEASONS)

#: One range. Month names are optional on both ends, which is what makes
#: `2022 - 2026` and `Jan 2025 - Apr 2025` the same pattern.
RANGE = re.compile(
    r"(?P<m1>(?:" + _MONTH_NAMES + r"|" + _SEASON_NAMES + r")\.?[ \t]*)?"
    r"(?P<y1>" + _Y_START + r")"
    r"[ \t]*(?:-|–|—|to|until|through)[ \t]*"
    r"(?P<m2>(?:" + _MONTH_NAMES + r"|" + _SEASON_NAMES + r")\.?[ \t]*)?"
    r"(?P<y2>" + _Y_END + r"|present|current|now|ongoing|till[ \t]+date)",
    re.IGNORECASE,
)

#: A single season or month with a year and no range: "Spring 2025".
#:
#: Word-bounded at both ends, or the `Jan 2025` inside `Jan 2025 - Apr 2025`
#: matches too and one range silently becomes extra dates. Callers that read
#: both should run `RANGE` first and skip anything it already covered —
#: `singles()` below does exactly that.
SINGLE = re.compile(
    r"\b(?P<m>" + _SEASON_NAMES + r"|" + _MONTH_NAMES + r")\.?[ \t]+"
    r"(?P<y>(?:19|20)\d{2})\b",
    re.IGNORECASE,
)

#: A bare duration: "2 months", "6 weeks". See the module docstring for why it
#: never becomes a range.
DURATION = re.compile(
    r"\b(?P<n>\d{1,2})[ \t]*(?P<unit>weeks?|months?|years?)\b",
    re.IGNORECASE,
)


def year(raw: str) -> int:
    """`"2025"`, `"'25"` and `"25"` all to 2025.

    See the module docstring for why the century is not guessed from anything:
    a two-digit year on a student resume is this century, and a rule that tries
    to be cleverer is a rule that gets one wrong silently.
    """
    digits = raw.strip().lstrip("'")
    value = int(digits)
    return value if value > 100 else 2000 + value


def month_index(name: str | None) -> int:
    """1-12 from a month or season name, or 1 when there is not one.

    January is the fallback rather than "unknown" because every consumer wants
    a comparable date. A range given only as years is a range over whole years,
    and treating it as starting in January is what a person reading it assumes.
    """
    if not name:
        return 1
    cleaned = name.strip().rstrip(".").casefold()
    if cleaned in _SEASONS:
        return _SEASONS[cleaned]
    key = cleaned[:3]
    return _MONTHS.index(key) + 1 if key in _MONTHS else 1


def duration_months(text: str) -> int | None:
    """`"2 months"` as a count of months, or None. Never a date."""
    match = DURATION.search(text)
    if match is None:
        return None
    count = int(match.group("n"))
    unit = match.group("unit").casefold()
    if unit.startswith("week"):
        return max(1, round(count / 4.3))
    if unit.startswith("year"):
        return count * 12
    return count


def singles(text: str) -> list[re.Match[str]]:
    """Every dated point that is not already part of a range.

    The overlap check is the whole function: without it "Jan 2025 - Apr 2025"
    reports one range and two extra points, and the timeline gains two events
    that never happened.
    """
    covered = [(m.start(), m.end()) for m in RANGE.finditer(text)]
    return [
        match
        for match in SINGLE.finditer(text)
        if not any(start < match.end() and end > match.start() for start, end in covered)
    ]


def is_open_ended(raw: str) -> bool:
    return re.sub(r"\s+", " ", raw.strip().casefold()) in OPEN_ENDED


def bounds(match: re.Match[str], today: date) -> tuple[date, date]:
    """(start, end) for a matched range. An open end is `today`."""
    start = date(year(match.group("y1")), month_index(match.group("m1")), 1)
    tail = match.group("y2")
    end = today if is_open_ended(tail) else date(year(tail), month_index(match.group("m2")), 1)
    return start, end

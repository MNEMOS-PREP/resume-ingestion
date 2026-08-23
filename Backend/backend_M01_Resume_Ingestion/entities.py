"""Entities: who this is, where they studied, and what they have done.

Spec: M01 §5, FR-1.6 — "name, contact (stored separately, PII-classed),
education, dates, institutions, roles".

The contact half lives in `claims.py` because it is inseparable from redaction;
this file is the rest. Same deterministic rule as the claim scorer, for the
same reason: a student has to be able to look at what we extracted and point at
the line it came from.

── What is deliberately not attempted ──────────────────────────────────────────

No name-from-anywhere heuristic. The name is taken from the first non-empty
line of the document when that line looks like a name, and left `None`
otherwise. Guessing wrong here is worse than not guessing: the name is what a
placement cell matches a student by, and a confident wrong one is harder to
notice than a missing one.

Dates are extracted with the range they came from rather than normalised into a
career timeline. A resume that lists overlapping internships is not an error to
be resolved; it is a fact to be reported, and M01 reports facts.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from backend_M01_Resume_Ingestion import dates

# ---------------------------------------------------------------------------
#  Contracts
# ---------------------------------------------------------------------------


class DateRange(BaseModel):
    raw: str
    start_year: int
    end_year: int | None = None
    #: True when the resume said "Present"/"Current" rather than a year.
    ongoing: bool = False
    start: int
    end: int


class EducationEntry(BaseModel):
    institution: str | None = None
    degree: str | None = None
    #: Whatever grade notation the resume used, verbatim: "8.1", "82%", "3.7".
    grade: str | None = None
    dates: DateRange | None = None
    line: str
    start: int
    end: int


class RoleEntry(BaseModel):
    title: str | None = None
    organisation: str | None = None
    dates: DateRange | None = None
    line: str
    start: int
    end: int


class DatedPoint(BaseModel):
    """A date with no span: "Spring 2025", "Jun 2024".

    Separate from `dates` on purpose. Only a RANGE can produce a timeline gap,
    and folding a point into the range list by giving it an invented end date
    manufactures gaps that are not on the resume — a red flag shown to a
    student about something they never wrote.
    """

    raw: str
    year: int
    month: int
    start: int
    end: int


class Duration(BaseModel):
    """A length with no position: "2 months", "6 weeks".

    Kept because "Internship, 2 months" is a real and common way to describe a
    role, and losing it means the role looks undated. It never becomes a range
    for the same reason `DatedPoint` does not.
    """

    raw: str
    months: int
    start: int
    end: int


class Entities(BaseModel):
    name: str | None = None
    education: list[EducationEntry] = Field(default_factory=list)
    roles: list[RoleEntry] = Field(default_factory=list)
    #: Periods with two ends. The only list the gap check reads.
    dates: list[DateRange] = Field(default_factory=list)
    dated_points: list[DatedPoint] = Field(default_factory=list)
    durations: list[Duration] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
#  Patterns
# ---------------------------------------------------------------------------

#: Shared with claims.py, deliberately. Two regexes drifted apart once, and a
#: format one accepted and the other did not meant a gap flag firing against a
#: timeline that did not contain the dates it was talking about.
_DATE_RANGE = dates.RANGE

_DEGREE = re.compile(
    r"\b(?:B\.?\s?Tech|B\.?\s?E\.?|B\.?\s?Sc|B\.?\s?C\.?A|BBA|B\.?Com|"
    r"M\.?\s?Tech|M\.?\s?E\.?|M\.?\s?Sc|M\.?C\.?A|MBA|Ph\.?\s?D|Diploma)"
    r"(?:\s+(?:in\s+)?[A-Za-z&/ ]{2,40})?",
    re.IGNORECASE,
)

#: A grade, in whichever notation the resume used. Anchored on the word so
#: "12k-node graph" is not read as a CGPA.
_GRADE = re.compile(
    r"\b(?:CGPA|GPA|SGPA|Percentage|Marks|Score)\b[\s:=-]*(?P<v>\d{1,3}(?:\.\d{1,2})?%?)"
    r"|(?P<v2>\d{1,3}(?:\.\d{1,2})?)\s*(?:/\s*(?:10|100|4)\b)"
    r"|(?P<v3>\d{2,3}%)",
    re.IGNORECASE,
)

#: An institution name, on ONE line.
#:
#: `\s` matches a newline, so the original pattern happily swallowed the
#: heading above the name: the EDUCATION section of a real resume produced the
#: institution "EDUCATION\nAmrita Vishwa Vidyapeetham". A name is a thing a
#: placement cell displays and matches a student by, so a heading inside it is
#: not cosmetic.
_INSTITUTION = re.compile(
    r"\b[A-Z][A-Za-z.&'-]*(?:[ \t]+[A-Z][A-Za-z.&'-]*)*[ \t]+"
    r"(?:University|Institute|College|School|Academy|Vidyapeetham|Vishwa[ \t]+Vidyapeetham)"
    r"(?:[ \t]+of[ \t]+[A-Z][A-Za-z ]+)?"
)

_ROLE_TITLE = re.compile(
    r"\b(?:Software|Backend|Frontend|Full[- ]?stack|Data|Machine Learning|ML|AI|DevOps|"
    r"QA|Research|Product|Business|Marketing|Design)?\s*"
    r"(?:Engineer|Developer|Intern|Internship|Analyst|Scientist|Manager|Consultant|"
    r"Trainee|Associate|Assistant|Lead|Architect|Designer|Researcher)"
    # "Software Engineer Intern" is one title, not a title beside a noun.
    r"(?:\s+(?:Intern|Internship|Trainee|Lead|Manager))?\b",
    re.IGNORECASE,
)

#: A line that plausibly holds a person's name: two to four capitalised words,
#: no digits, no punctuation beyond a dot or hyphen. Everything else is left
#: alone rather than guessed at.
_NAME_LINE = re.compile(r"^[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3}$")

_NOT_A_NAME = frozenset(
    {
        "curriculum vitae",
        "resume",
        "cv",
        "personal details",
        "contact details",
    }
)


def _date_range(text: str, base: int) -> DateRange | None:
    match = _DATE_RANGE.search(text)
    if not match:
        return None
    tail = match.group("y2")
    ongoing = dates.is_open_ended(tail)
    return DateRange(
        raw=match.group(0).strip(),
        start_year=dates.year(match.group("y1")),
        end_year=None if ongoing else dates.year(tail),
        ongoing=ongoing,
        start=base + match.start(),
        end=base + match.end(),
    )


def _grade(text: str) -> str | None:
    match = _GRADE.search(text)
    if not match:
        return None
    return match.group("v") or match.group("v2") or match.group("v3")


def extract_entities(text: str, sections: list) -> Entities:
    """Name, education, roles and every date range, with offsets.

    `sections` are `ResumeSection` models from `claims.segment`; education and
    role lines are read from the sections that claim to hold them, so a project
    bullet mentioning "University" does not become a degree.
    """
    entities = Entities()

    # --- name: first line, only if it looks like one --------------------
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.casefold() in _NOT_A_NAME:
            continue
        if _NAME_LINE.match(stripped) and len(stripped) <= 60:
            entities.name = stripped
        break

    by_kind: dict[str, list] = {}
    for section in sections:
        by_kind.setdefault(section.kind, []).append(section)

    def lines_of(kind: str):
        for section in by_kind.get(kind, []):
            base = section.span.start
            offset = 0
            for line in section.span.text.splitlines(keepends=True):
                stripped = line.strip()
                if stripped:
                    yield base + offset + line.index(stripped), stripped
                offset += len(line)

    # --- education ------------------------------------------------------
    for start, line in lines_of("education"):
        degree = _DEGREE.search(line)
        institution = _INSTITUTION.search(line)
        # Not `dates` — that name is the module, and shadowing it here made
        # `dates.singles` below resolve to a `DateRange`.
        span = _date_range(line, start)
        if not (degree or institution or span):
            continue
        entities.education.append(
            EducationEntry(
                institution=institution.group(0).strip() if institution else None,
                degree=degree.group(0).strip() if degree else None,
                grade=_grade(line),
                dates=span,
                line=line,
                start=start,
                end=start + len(line),
            )
        )

    # --- roles ----------------------------------------------------------
    for kind in ("experience", "projects"):
        for start, line in lines_of(kind):
            title = _ROLE_TITLE.search(line)
            if not title:
                continue
            organisation = _INSTITUTION.search(line)
            entities.roles.append(
                RoleEntry(
                    title=title.group(0).strip(),
                    organisation=organisation.group(0).strip() if organisation else None,
                    dates=_date_range(line, start),
                    line=line,
                    start=start,
                    end=start + len(line),
                )
            )

    # --- every date range anywhere, and every institution ---------------
    for match in _DATE_RANGE.finditer(text):
        found = _date_range(match.group(0), match.start())
        if found:
            entities.dates.append(found)

    # Points and lengths (§3.2.3). `dates.singles` skips anything already
    # inside a range, so "Jan 2025 - Apr 2025" does not also report two points.
    for match in dates.singles(text):
        entities.dated_points.append(
            DatedPoint(
                raw=match.group(0).strip(),
                year=dates.year(match.group("y")),
                month=dates.month_index(match.group("m")),
                start=match.start(),
                end=match.end(),
            )
        )

    for match in dates.DURATION.finditer(text):
        months = dates.duration_months(match.group(0))
        if months is not None:
            entities.durations.append(
                Duration(
                    raw=match.group(0).strip(),
                    months=months,
                    start=match.start(),
                    end=match.end(),
                )
            )

    seen: set[str] = set()
    for match in _INSTITUTION.finditer(text):
        value = match.group(0).strip()
        if value.casefold() not in seen:
            seen.add(value.casefold())
            entities.institutions.append(value)

    return entities

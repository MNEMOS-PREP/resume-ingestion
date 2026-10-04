"""The student's library: everything they have had on a resume, kept (2026-10-04).

── Why it exists ─────────────────────────────────────────────────────────────

Two requests, one answer. Deleting a resume should remove the document and its
analysis — and NOT the projects, skills, achievements and certifications in it,
because those are the record of how the student has progressed. And editing a
line or starting a new resume should mean picking from what they already wrote,
not retyping it.

So every upload adds its items here — experience and project lines, achievements,
certifications, education, skills — de-duplicated per student, kept when a resume
is deleted, and edited or removed by the student directly.

── What it promises ──────────────────────────────────────────────────────────

- **Nothing personal.** Items are read from the REDACTED text, and any masked run
  is stripped, so a contact detail can never become an item.
- **Each resume is read once.** At upload (or at confirmation, for a parse the
  student had to check), or the first time the library opens for a resume that
  predates it. So an item the student removes stays removed until a NEW upload
  contains it; reading the same resume again would quietly bring it back and the
  remove button would be a lie.
- **A reading only adds.** It adds items and widens their sources; it never
  rewrites or removes what the student wrote.
- **Their better wording wins.** A line the student improves on the review page
  replaces its old wording here, so the next resume starts from the good version.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from sqlmodel import Session, select

from backend_M01_Resume_Ingestion import headings
from backend_M01_Resume_Ingestion.claims import segment_bullets
from backend_M01_Resume_Ingestion.entities import _GRADE
from backend_M01_Resume_Ingestion.models import LibraryItem, LibrarySynced, Resume
from backend_M01_Resume_Ingestion.review import skill_name
from backend_M01_Resume_Ingestion.revisions import normalise

#: In the order a resume reads, and the order the library lists them.
KINDS = ("experience", "project", "achievement", "certification", "education", "skill")


class Draft(NamedTuple):
    """An item read off a resume, before it meets the library."""

    kind: str
    text: str
    context: str = ""
    user_written: bool = False


_MASK = "█"
_MASKED_RUN = re.compile(rf"\s*{_MASK}+\s*")

#: "Eﬀicient" → "Efficient". A PDF's ligatures are one character on the page and
#: two in a sentence someone pastes into a new resume.
_LIGATURES = str.maketrans(
    {chr(c): unicodedata.normalize("NFKC", chr(c)) for c in range(0xFB00, 0xFB07)}
)

#: "[GitHub]", "[Certificate]", "[Badge]": a hyperlink's visible text. The link
#: itself did not survive extraction, so the label alone is noise in a new resume.
_LINK_LABEL = re.compile(r"\s*\[[A-Z][A-Za-z.&/ -]{0,24}\]")

#: "radiomics- guided": a word the page broke at its hyphen, joined back with a
#: space when the bullet's lines were. Not before "and"/"or"/"to", where a
#: student wrote the hyphen on purpose ("pre- and post-processing"). Only in
#: the library: a claim's text must keep matching its span, so it stays as read.
_BROKEN_HYPHEN = re.compile(r"(?<=[A-Za-z])- (?!(?:and|or|to)\b)(?=[a-z])")

#: The scale after a grade: the " / 10" in "CGPA: 9.62 / 10".
_SCALE = re.compile(r"\s*/\s*\d{1,3}(?:\.\d+)?")

#: A line with no word in it: a lone bullet glyph, a rule, a page number.
_WORDLESS = re.compile(r"^[^A-Za-z]*(?:[A-Za-z][^A-Za-z]*)?$")

#: Words that make a line a credential rather than an accomplishment, used ONLY
#: inside a section headed as both ("Achievements & Certifications"), where the
#: heading cannot say which each line is. A lexicon is the fallback the
#: no-hardcoding rule allows here: a wrong guess changes a label, the library
#: shows the two kinds together, and the student can move an item in one click.
_CREDENTIAL = re.compile(
    r"\b(?:certif\w*|credential\w*|licen[cs]e\w*|courses?|associate|professional|"
    r"practitioner|specialist|speciali[sz]ation|nanodegree|foundations?)\b",
    re.IGNORECASE,
)


def clean(text: str) -> str:
    """An item as the student would paste it: no masks, ligatures, link labels or echoes."""
    out = _MASKED_RUN.sub(" ", text).translate(_LIGATURES)
    out = _LINK_LABEL.sub("", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = _BROKEN_HYPHEN.sub("-", out)
    # A part that repeats the end of the part before it is the extractor reading
    # one text box twice: "… AI Foundations Associate (2025) | Foundations
    # Associate (2025)".
    parts: list[str] = []
    for part in (p.strip() for p in out.split(" | ")):
        if part and not any(kept.casefold().endswith(part.casefold()) for kept in parts):
            parts.append(part)
    out = " | ".join(parts)
    # A separator left dangling by a masked link: "Cortexa |" → "Cortexa".
    out = re.sub(r"(?:\s*[|·•,;:]\s*)+$", "", out)
    out = re.sub(r"^(?:\s*[|·•,;:]\s*)+", "", out)
    return out.strip()


def _heading_line(text: str, section: dict[str, Any]) -> tuple[str, int]:
    """The section's heading line and where its body starts.

    Section spans can start a line or two early and carry the tail of the section
    before, so only what follows the heading belongs to this one. No heading
    found: no heading text, and the body is the whole span.
    """
    start, end = section["span"]["start"], section["span"]["end"]
    offset = start
    for line in text[start:end].splitlines(keepends=True):
        if line.strip() and headings.lookup(line.strip()) is not None:
            return line.strip(), offset + len(line)
        offset += len(line)
    return "", start


def _words(phrases: tuple[str, ...]) -> set[str]:
    return {word for phrase in phrases for word in phrase.split() if word != "and"}


#: Words that put a heading in each kind, derived from M01's own heading lexicon.
_ACHIEVEMENT_WORDS = _words(headings.SECTION_HEADINGS["achievements"]) | _words(
    headings.SECTION_HEADINGS["publications"]
)
_CERTIFICATION_WORDS = _words(headings.SECTION_HEADINGS["certifications"])


def _kind_for(section: dict[str, Any], heading: str, line: str) -> str | None:
    """Which library kind a line in this section is, or None for none."""
    kind = section["kind"]
    if kind == "experience":
        return "experience"
    if kind == "projects":
        return "project"
    if kind not in {"achievements", "certifications", "publications"}:
        return None
    words = set(headings.normalise(heading).split())
    if words & _ACHIEVEMENT_WORDS and words & _CERTIFICATION_WORDS:
        # Both in one section: the heading can't say which this line is.
        bare = _LINK_LABEL.sub("", line)
        return "certification" if _CREDENTIAL.search(bare) or "[Badge]" in line else "achievement"
    return "certification" if kind == "certifications" else "achievement"


def _title(lines: list[str]) -> str:
    """Lines above a group of bullets, as one title. A line that starts lower-case
    continues the one above it ("… Manuscript" / "sent for review"); otherwise
    they are separate facts about one thing (a role, then its employer)."""
    out = ""
    for line in lines:
        if not out:
            out = line
        elif line[:1].islower():
            out = f"{out} {line}"
        else:
            out = f"{out} · {line}"
    return clean(out)[:160]


def _claim_contexts(text: str, resume: Resume) -> dict[str, str]:
    """Claim id → the title of the group it sits in.

    Read from the GAPS between claims, which M01's spans make exact: whatever
    lies between one claim's end and the next claim's start that is not a bullet
    glyph or a heading is the next group's title. An empty gap means the same
    group as the claim above.
    """
    by_section: dict[str, list[dict[str, Any]]] = {}
    for claim in resume.claims or []:
        by_section.setdefault(str(claim.get("section_id")), []).append(claim)
    sections = {str(s["id"]): s for s in resume.sections or []}
    out: dict[str, str] = {}
    for section_id, claims in by_section.items():
        section = sections.get(section_id)
        if section is None:
            continue
        _, cursor = _heading_line(text, section)
        title = ""
        for claim in sorted(claims, key=lambda c: (c.get("span") or {}).get("start", 0)):
            span = claim.get("span") or {}
            gap = text[cursor : span.get("start", cursor)]
            lines = [
                line.strip()
                for line in gap.splitlines()
                if line.strip()
                and not _WORDLESS.match(line.strip())
                and headings.lookup(line.strip()) is None
            ]
            if lines:
                title = _title(lines[-3:])
            out[str(claim.get("id"))] = title
            cursor = max(cursor, span.get("end", cursor))
    return out


def _skills(text: str, resume: Resume) -> list[str]:
    """Every skill the student LISTED, read off the skills lines themselves.

    Structural, not the mention extractor's output: that keeps the names it
    recognises, and on a real resume it stopped at "Libraries:" — React, Django,
    FastAPI and Docker were listed and never reached the library. A skills line
    is a label and a list; the list is the skills.
    """
    names: list[str] = []
    for section in resume.sections or []:
        if section["kind"] != "skills":
            continue
        start, end = section["span"]["start"], section["span"]["end"]
        joined = ""
        for raw in text[start:end].splitlines():
            line = raw.strip()
            if not line:
                continue
            # "Multi-" / "modal Learning": a word the page broke in two.
            joined = f"{joined}{line}" if joined.endswith("-") else f"{joined}\n{line}"
        for line in joined.splitlines():
            if not line:
                continue
            label, sep, rest = line.partition(":")
            if not sep and headings.lookup(line) is not None:
                continue  # the heading itself
            body = rest if sep and len(label) <= 32 else line
            for name in re.split(r"\s*[,;|•·]\s*", body):
                name = clean(name)
                if 1 <= len(name) <= 40 and re.search(r"[A-Za-z]", name):
                    names.append(name)
    # The extractor's mentions still count, for skills listed somewhere this
    # read does not reach (a summary's "Skills: …" line).
    for mention in resume.skill_mentions or []:
        if mention.get("context") == "skills_list":
            name = clean(skill_name(str(mention.get("surface", ""))))
            if name:
                names.append(name)
    return names


def _education(text: str, resume: Resume) -> list[str]:
    """One line per degree: what, where, when, and the grade.

    The parser reads a degree and its institution as two entries when they sit
    on two lines, and finds a grade only on the degree's own line — "CGPA: 9.62
    / 10" on a line of its own was dropped. Both are put back here: an entry with
    no institution takes the next entry's, and a short line below it that holds a
    grade (by M01's own grade pattern) is its grade.
    """
    merged: list[dict[str, Any]] = []
    for entry in (resume.entities or {}).get("education", []) or []:
        if (
            merged
            and not merged[-1].get("institution")
            and entry.get("institution")
            and not entry.get("degree")
        ):
            merged[-1] = {
                **merged[-1],
                "institution": entry["institution"],
                "end": entry.get("end"),
            }
            continue
        merged.append(dict(entry))
    section_ends = [s["span"]["end"] for s in resume.sections or [] if s["kind"] == "education"]
    out: list[str] = []
    for index, entry in enumerate(merged):
        dates = entry.get("dates") or {}
        start_year, end_year = dates.get("start_year"), dates.get("end_year")
        if start_year and dates.get("ongoing"):
            years = f"{start_year}–present"
        elif start_year and end_year:
            years = f"{start_year}–{end_year}"
        else:
            years = str(end_year or start_year or "")
        grade = ""
        if entry.get("grade"):
            line = entry.get("line") or ""
            found = _GRADE.search(line)
            if found:
                # With its scale: "CGPA: 9.62 / 10", not "CGPA: 9.62". A line
                # the library composed reads back as the item it came from.
                scale = _SCALE.match(line, found.end())
                grade = line[found.start() : scale.end() if scale else found.end()].strip()
            else:
                grade = str(entry["grade"])
        else:
            after = entry.get("end") or 0
            stop = merged[index + 1].get("start") if index + 1 < len(merged) else None
            if stop is None:
                stop = min((e for e in section_ends if e >= after), default=after + 120)
            for line in text[after:stop].splitlines():
                if line.strip() and len(line.strip()) <= 40 and _GRADE.search(line):
                    grade = line.strip()
                    break
        parts = [entry.get("degree"), entry.get("institution"), years, grade]
        joined = ", ".join(p for p in parts if p)
        out.append(clean(joined or entry.get("line") or ""))
    return out


def extract(resume: Resume) -> list[Draft]:
    """Every item one resume contributes."""
    text = resume.redacted_text or ""
    sections = {str(s["id"]): s for s in resume.sections or []}
    headings_of = {sid: _heading_line(text, s)[0] for sid, s in sections.items()}
    out: list[Draft] = []

    # Experience, project, achievement and publication lines are the claims M01
    # already isolated — in their current wording, so a line the student
    # improved is kept as they wrote it.
    contexts = _claim_contexts(text, resume)
    sections_with_claims: set[str] = set()
    for claim in resume.claims or []:
        section_id = str(claim.get("section_id"))
        section = sections.get(section_id)
        if section is None:
            continue
        kind = _kind_for(section, headings_of[section_id], claim["text"])
        if kind is None:
            continue
        sections_with_claims.add(section_id)
        context = (
            contexts.get(str(claim.get("id")), "") if kind in {"experience", "project"} else ""
        )
        out.append(Draft(kind, clean(claim["text"]), context, bool(claim.get("user_edited"))))

    # Certifications are not claims, so their section is read line by line.
    for section_id, section in sections.items():
        if section_id in sections_with_claims:
            continue
        if section["kind"] not in {"achievements", "certifications", "publications"}:
            continue
        heading, body_start = _heading_line(text, section)
        body = text[body_start : section["span"]["end"]]
        lines = [line for _, line in segment_bullets(body, body_start)] or [
            line.strip() for line in body.splitlines() if line.strip()
        ]
        for line in lines:
            kind = _kind_for(section, heading, line)
            if kind is not None:
                out.append(Draft(kind, clean(line)))

    out += [Draft("education", line) for line in _education(text, resume)]
    out += [Draft("skill", name) for name in _skills(text, resume)]
    return [
        d
        for d in out
        if d.text
        and _MASK not in d.text
        # "C" and "R" are skills; a one-letter line anywhere else is a glyph.
        and (d.kind == "skill" or not _WORDLESS.match(d.text))
    ]


def find(session: Session, candidate_id: uuid.UUID, kind: str, key: str) -> LibraryItem | None:
    return session.exec(
        select(LibraryItem)
        .where(LibraryItem.candidate_id == candidate_id)
        .where(LibraryItem.kind == kind)
        .where(LibraryItem.key == key)
    ).first()


def add_drafts(
    session: Session, candidate_id: uuid.UUID, drafts: list[Draft], *, source: str | None
) -> list[LibraryItem]:
    """Add what is new, widen the sources of what is not. Returns the items added."""
    now = datetime.now(UTC)
    added: list[LibraryItem] = []
    # One reading's items share a moment; a microsecond apiece keeps them in
    # the order the resume had them, which is the order a student reads.
    tick = 0
    seen: set[tuple[str, str]] = set()
    for draft in drafts:
        key = normalise(draft.text)
        if not key or (draft.kind, key) in seen:
            continue
        seen.add((draft.kind, key))
        row = find(session, candidate_id, draft.kind, key)
        if row is None:
            row = LibraryItem(
                candidate_id=candidate_id,
                kind=draft.kind,
                text=draft.text,
                context=draft.context,
                key=key,
                sources=[source] if source else [],
                user_written=draft.user_written,
                first_seen=now + timedelta(microseconds=tick),
                last_seen=now,
            )
            tick += 1
            session.add(row)
            added.append(row)
            continue
        if source and source not in row.sources:
            row.sources = [*row.sources, source]
        if not row.context and draft.context:
            row.context = draft.context
        row.last_seen = now
        session.add(row)
    # Visible to the next query in this session, which de-duplicates against it.
    session.flush()
    return added


def is_synced(session: Session, resume_id: uuid.UUID) -> bool:
    return session.get(LibrarySynced, resume_id) is not None


def sync(session: Session, resume: Resume) -> int:
    """Read one resume into its student's library — once. Returns how many items were new."""
    if is_synced(session, resume.id):
        return 0
    added = add_drafts(session, resume.candidate_id, extract(resume), source=str(resume.id))
    session.add(LibrarySynced(resume_id=resume.id, candidate_id=resume.candidate_id))
    return len(added)


def backfill(session: Session, candidate_id: uuid.UUID) -> int:
    """Read the resumes that arrived before the library existed (or before they were confirmed)."""
    added = 0
    for resume in session.exec(select(Resume).where(Resume.candidate_id == candidate_id)).all():
        if resume.parse_status == "ready" and not is_synced(session, resume.id):
            added += sync(session, resume)
    return added


def reword(session: Session, resume: Resume, old_text: str, new_text: str) -> None:
    """A line the student improved on one resume: the library keeps the improvement.

    The old wording's item moves to the new wording when this resume was its
    only source; when another resume still says it the old way, that item stays
    for that resume and the new wording is a new item beside it. Either way the
    title it sat under comes along.
    """
    if not is_synced(session, resume.id):
        return  # its reading, when it happens, takes the current wording
    old_key, new_key, source = normalise(old_text), normalise(new_text), str(resume.id)
    if not new_key or old_key == new_key:
        return
    old = next(
        (
            row
            for kind in ("experience", "project", "achievement")
            if (row := find(session, resume.candidate_id, kind, old_key)) is not None
        ),
        None,
    )
    if old is None:
        return  # removed from the library already; the student's choice stands
    text = clean(new_text)
    existing = find(session, resume.candidate_id, old.kind, new_key)
    if old.sources in ([source], []) and existing is None:
        old.text, old.key, old.user_written = text, new_key, True
        session.add(old)
        return
    if source in old.sources:
        old.sources = [s for s in old.sources if s != source]
        session.add(old)
    if existing is None:
        add_drafts(
            session,
            resume.candidate_id,
            [Draft(old.kind, text, old.context, user_written=True)],
            source=source,
        )
    elif source not in existing.sources:
        existing.sources = [*existing.sources, source]
        session.add(existing)


def edit(
    session: Session, item: LibraryItem, *, text: str | None, context: str | None, kind: str | None
) -> LibraryItem:
    """The student's change to one item. Rewording into a duplicate merges the two."""
    if kind is not None:
        item.kind = kind
    if context is not None:
        item.context = clean(context)[:160]
    if text is not None:
        item.text = clean(text)
        item.key = normalise(item.text)
        item.user_written = True
    duplicate = session.exec(
        select(LibraryItem)
        .where(LibraryItem.candidate_id == item.candidate_id)
        .where(LibraryItem.kind == item.kind)
        .where(LibraryItem.key == item.key)
        .where(LibraryItem.id != item.id)
    ).first()
    if duplicate is not None:
        item.sources = [*item.sources, *(s for s in duplicate.sources if s not in item.sources)]
        item.first_seen = min(item.first_seen, duplicate.first_seen)
        item.context = item.context or duplicate.context
        session.delete(duplicate)
        item.last_seen = max(item.last_seen, duplicate.last_seen)
    session.add(item)
    return item

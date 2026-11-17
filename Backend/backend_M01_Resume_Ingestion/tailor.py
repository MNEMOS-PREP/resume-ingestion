"""Tailored copies: one resume, reworded for one job, without touching the original.

── Why a copy (2026-11-17) ──────────────────────────────────────────────────────

The review page (`review.py`) edits a resume in place: a fix is a `PATCH` on the
claim, and the resume a student uploaded is the resume they then have. That is
right for "fix my resume", and wrong for "make a version of my resume for this
job". A student applying to three postings wants three versions, and wording a
bullet towards one company's stack must not quietly reword it for the other two.

So a tailored resume is its own row, made from a resume at one moment and
belonging to one target (M02's job description id, opaque here). The resume it
came from is never written by anything in this file, and two tailored copies
share nothing: each holds its own blocks and its own history.

── Blocks, not claims ───────────────────────────────────────────────────────────

A claim is a bullet M01 can score. A resume also has a name, headings, a role
line with its dates, a skills line, a summary paragraph — and a job match
touches those as often as bullets ("put Docker in your skills line"). So the
copy is the whole document as BLOCKS, each one line or paragraph of the page,
each pointing back at the characters of the original it came from (`span`). A
claim's block carries its `claim_id`, so M01's scoring and M02's evidence can
both still name it.

The text of a block is the original's words with the PAGE's artefacts taken out:
line breaks inside a wrapped bullet, the hyphen a typesetter put in "detec-
tion", and the ligature glyph a PDF extracts for "ff". Nothing else changes.

── The contact block stays where it is ──────────────────────────────────────────

A block holding masked characters (the email, the phone, a profile link) is
LOCKED: it can be hidden or moved, never retyped, because its text on screen is
the masked copy (FR-1.17). The PDF a student downloads for themselves has the
real characters, read from `raw_text` at the same offsets; every image of a page
has them painted out, exactly as the original page renders do.

── The PDF is generated, so it can be trusted ───────────────────────────────────

The file is laid out here from the blocks, line by line, which is what lets the
preview and the download be the same bytes and lets every block say which
rectangles of which page it occupies — the claim-to-requirement trace lands on
the exact line. It keeps the original's page size, margins, body size and
serif-or-sans; it cannot keep its exact typeface (a PDF embeds only the glyphs
it used), and it does not pretend to.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from backend_M01_Resume_Ingestion.claims import _BULLET_LINE, _heading_kind

#: The character `claims.redact` masks with. A run of it is contact detail.
MASK = "█"

#: A blank only the student can fill, as on the review page. A line with one
#: is not saved — `review.BLANK`'s rule, applied to tailored blocks too.
BLANK = re.compile(r"\[[^\[\]]+\]")


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
#  Storage
# ---------------------------------------------------------------------------


class TailoredResume(SQLModel, table=True):
    """One resume, worded for one target. The source resume is never written."""

    __tablename__ = "m01_tailored"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    resume_id: uuid.UUID = Field(index=True)
    candidate_id: uuid.UUID = Field(index=True)
    label: str = ""
    #: What it is tailored FOR. `jd` + M02's job description id today; opaque
    #: here on purpose, so M01 never has to know what a posting looks like.
    target_kind: str = Field(default="jd")
    target_ref: str = Field(default="", index=True)
    blocks: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    #: Page size, margins, body size and family, read off the original file.
    style: dict = Field(default_factory=dict, sa_column=Column(JSON))
    #: The newest revision's number. 0 is "as made from the resume".
    revision: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class TailoredRevision(SQLModel, table=True):
    """Every change, with the whole document as it stood after it.

    A full snapshot per revision rather than a diff: a resume is a few
    kilobytes, and "restore version 4" is then a copy rather than a replay
    that one bad revision could break for every version after it.
    """

    __tablename__ = "m01_tailored_revisions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tailored_id: uuid.UUID = Field(index=True)
    n: int
    #: created | edit | hide | show | insert | move | restore
    action: str
    block_id: str | None = None
    before: str | None = None
    after: str | None = None
    #: `manual`, or what proposed it — `jd:<suggestion key>` from M02.
    source: str = Field(default="manual")
    #: Why, in the words of whatever proposed it. Kept with the change so the
    #: history can answer "why does this line read like this?" months later.
    note: str | None = None
    blocks: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
#  Display text from the page's text
# ---------------------------------------------------------------------------

_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}

#: What follows a typesetter's hyphen when it split ONE word ("detec-tion",
#: "observ-ability"). Anything else after a line-end hyphen was a real
#: compound ("persistence-aware", "radiomics-guided") and keeps its hyphen.
_WORD_TAIL = re.compile(
    r"(?:tions?|sions?|ments?|ities|ity|abilit(?:y|ies)|ibilit(?:y|ies)|ings?|ed|ally|al|"
    r"ances?|ences?|ness|ives?|ous|ures?|able|ible|ly|ers?|ors?|ists?|isms?|i[sz]ed|i[sz]es?|"
    r"i[sz]ations?|ology|ations?|ated|ating|ators?|ics?|ical)\b"
)

_HYPHEN_BREAK = re.compile(r"-[ \t]*\n\s*")

#: A prefix a typesetter split from its word: "pre-diction", "multi-modal",
#: "sub-system". Joined only before a consonant — "re-engineered" and
#: "co-author" keep the hyphen they were written with.
_PREFIXES = frozenset(
    {"pre", "multi", "sub", "inter", "intra", "non", "semi", "over", "under", "trans"}
)


def flatten(source: str) -> tuple[str, list[int]]:
    """One line of display text from a wrapped run of the page's text.

    Returns the text and, for every character of it, the offset in `source`
    it came from. The map is what lets the real contact details be read back
    out of `raw_text` at exactly the places the masked copy has `█`.
    """
    out: list[str] = []
    index: list[int] = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch == "-" and i > 0 and source[i - 1].isalpha():
            brk = _HYPHEN_BREAK.match(source, i)
            if brk:
                rest = source[brk.end() : brk.end() + 16]
                head = re.search(r"[A-Za-z]+$", source[max(0, i - 12) : i])
                prefix = bool(
                    head
                    and head.group(0).lower() in _PREFIXES
                    and rest[:1].islower()
                    and rest[:1] not in "aeiou"
                )
                if prefix or (rest[:1].islower() and _WORD_TAIL.match(rest)):
                    i = brk.end()
                    continue
                out.append("-")
                index.append(i)
                i = brk.end()
                continue
        if ch.isspace():
            j = i
            while j < n and source[j].isspace():
                j += 1
            if out and j < n:
                out.append(" ")
                index.append(i)
            i = j
            continue
        ligature = _LIGATURES.get(ch)
        if ligature:
            for part in ligature:
                out.append(part)
                index.append(i)
            i += 1
            continue
        out.append(ch)
        index.append(i)
        i += 1
    return "".join(out), index


def revealed_from(redacted: str, raw: str, span: tuple[int, int]) -> str:
    """The display text of a masked span, with the real characters restored.

    Only for a LOCKED block, whose text is exactly `flatten(redacted[span])`:
    re-flattening the redacted slice gives the same index map, and each masked
    character is replaced by the raw character at the same offset — `raw_text`
    and `redacted_text` are the same length character for character.
    """
    start, end = span
    flat, index = flatten(redacted[start:end])
    if MASK not in flat:
        return flat
    source = raw[start:end]
    return "".join(
        source[at] if ch == MASK and at < len(source) else ch
        for ch, at in zip(flat, index, strict=True)
    )


# ---------------------------------------------------------------------------
#  Blocks
# ---------------------------------------------------------------------------

_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_WHEN = rf"(?:{_MONTH}\s+)?(?:19|20)\d{{2}}"
#: A date range at the END of a line — how a role, a degree or a project
#: states its dates on most templates, right-aligned on the page.
_DATE_TAIL = re.compile(
    rf"\s+(?P<date>{_WHEN}\s*(?:[–—-]|to)\s*(?:{_WHEN}|Present|Current|Now|Ongoing|Till\s+date)"
    rf"|{_MONTH}\s+(?:19|20)\d{{2}})\s*$",
    re.IGNORECASE,
)

#: Sections whose blocks fall into ENTRIES — a role, a degree, a project — each
#: a title line with its bullets under it, moved as one.
_ENTRY_SECTIONS = frozenset(
    {"experience", "projects", "education", "achievements", "publications", "extras", "unknown"}
)

#: "Programming: Python, C" — a label the PDF sets in bold.
LABEL = re.compile(r"^(?P<label>[A-Z][A-Za-z0-9 &/+().'-]{1,32}):\s")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _lines(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """(start, end) of every line in text[start:end], newline excluded."""
    out: list[tuple[int, int]] = []
    at = start
    while at < end:
        stop = text.find("\n", at, end)
        if stop == -1:
            stop = end
        out.append((at, stop))
        at = stop + 1
    return out


def build_blocks(
    *,
    redacted: str,
    sections: list[dict],
    claims: list[dict],
) -> list[dict]:
    """The resume as the blocks a tailored copy is edited in.

    Each block: `id`, `kind` (name · contact · heading · entry · subtitle ·
    bullet · text), `section` (the section kind), `section_id`, `group` (the
    entry it belongs to), `text`, `original`, `aside` (an entry's dates),
    `claim_id`, `span` into the original text, and the flags `masked`,
    `hidden`, `added`.
    """
    text = redacted
    ordered = sorted(
        (s for s in sections if isinstance(s.get("span"), dict)),
        key=lambda s: s["span"]["start"],
    )
    runs = sorted(
        (c for c in claims if isinstance(c.get("span"), dict)),
        key=lambda c: c["span"]["start"],
    )

    regions: list[tuple[int, int, str, str | None]] = []
    first = ordered[0]["span"]["start"] if ordered else len(text)
    if first > 0 and text[:first].strip():
        regions.append((0, first, "contact", None))
    for index, section in enumerate(ordered):
        start = section["span"]["start"]
        end = ordered[index + 1]["span"]["start"] if index + 1 < len(ordered) else len(text)
        regions.append((start, end, str(section.get("kind", "unknown")), str(section.get("id"))))
    if not regions and text.strip():
        regions.append((0, len(text), "unknown", None))

    blocks: list[dict[str, Any]] = []
    counter = 0

    def make(kind: str, section: str, section_id: str | None, start: int, end: int, **extra: Any):
        nonlocal counter
        counter += 1
        block: dict[str, Any] = {
            "id": f"b{counter:02d}",
            "kind": kind,
            "section": section,
            "section_id": section_id,
            "group": None,
            "text": "",
            "original": "",
            "aside": None,
            "claim_id": None,
            "span": [start, end],
            "masked": False,
            "hidden": False,
            "added": False,
        }
        block.update(extra)
        blocks.append(block)
        return block

    def finish(block: dict) -> None:
        start, end = block["span"]
        if block.get("claim_text") is not None:
            display = block.pop("claim_text")
        else:
            display, _ = flatten(text[start:end])
        aside = None
        if block["kind"] in {"entry", "text", "subtitle"}:
            found = _DATE_TAIL.search(display)
            if found and found.start() > 3 and MASK not in found.group("date"):
                aside = found.group("date").strip()
                display = display[: found.start()].rstrip(" |,·–-")
                if block["kind"] == "text":
                    block["kind"] = "entry"
        block["text"] = display
        block["original"] = display
        block["aside"] = aside
        block["masked"] = MASK in display

    claim_at = 0
    for region_start, region_end, kind, section_id in regions:
        lines = _lines(text, region_start, region_end)
        seen_text = False
        current: dict[str, Any] | None = None
        skip_until = region_start
        for line_start, line_end in lines:
            line = text[line_start:line_end]
            if not line.strip() or line_end <= skip_until:
                continue

            # A claim that starts on this line is one block, however many lines
            # it wraps across — and its words are the claim's, so an edit the
            # student made on the review page carries into the copy.
            while claim_at < len(runs) and runs[claim_at]["span"]["start"] < line_start:
                claim_at += 1
            if claim_at < len(runs) and runs[claim_at]["span"]["start"] < line_end:
                claim = runs[claim_at]
                claim_at += 1
                if current is not None:
                    finish(current)
                start, end = claim["span"]["start"], claim["span"]["end"]
                current = make(
                    "bullet",
                    kind,
                    section_id,
                    start,
                    end,
                    claim_id=str(claim.get("id")),
                    claim_text=(
                        " ".join(str(claim.get("text", "")).split())
                        if claim.get("user_edited")
                        else None
                    ),
                )
                finish(current)
                current = None
                skip_until = end
                seen_text = True
                continue

            stripped = line.strip()
            if kind == "contact":
                if current is not None:
                    finish(current)
                current = make(
                    "contact" if seen_text else "name", kind, section_id, line_start, line_end
                )
                finish(current)
                current = None
                seen_text = True
                continue

            # A heading line on its own. "Libraries: OpenCV, spaCy" can open a
            # section too (the parser splits there), but it is a line of the
            # page, not a heading to print in bold capitals.
            if not seen_text and not LABEL.match(stripped) and _heading_kind(stripped) is not None:
                current = make("heading", kind, section_id, line_start, line_end)
                finish(current)
                current = None
                seen_text = True
                continue
            seen_text = True

            bullet = _BULLET_LINE.match(line)
            if bullet:
                if current is not None:
                    finish(current)
                current = make(
                    "bullet", kind, section_id, line_start + bullet.start("body"), line_end
                )
                continue

            if current is not None and _continues(current, text, line, kind):
                current["span"][1] = line_end
                continue

            if current is not None:
                finish(current)
            label = "text"
            if blocks and blocks[-1]["kind"] == "entry" and kind in _ENTRY_SECTIONS:
                label = "subtitle"
            current = make(label, kind, section_id, line_start, line_end)
        if current is not None:
            finish(current)

    _promote_entries(blocks)
    _assign_groups(blocks)
    return blocks


def _continues(block: dict, text: str, line: str, section: str) -> bool:
    """Whether `line` is the wrapped tail of `block` rather than a new line."""
    if block["kind"] not in {"bullet", "text", "subtitle"}:
        return False
    first_line_start = text.rfind("\n", 0, block["span"][0]) + 1
    first_line_end = text.find("\n", block["span"][0])
    first_line = text[first_line_start : first_line_end if first_line_end != -1 else len(text)]
    so_far = text[block["span"][0] : block["span"][1]].rstrip()
    body = line.strip()
    if section == "summary" and block["kind"] == "text":
        return True
    if LABEL.match(body):
        return False
    if block["kind"] == "bullet" and _indent(line) >= _indent(first_line) + 2:
        return True
    if so_far.endswith(("-", ",", "&", "/")):
        return True
    return body[:1].islower()


def _promote_entries(blocks: list[dict]) -> None:
    """A title line followed by bullets is an entry, dated or not."""
    for index, block in enumerate(blocks):
        if block["kind"] != "text" or block["section"] not in _ENTRY_SECTIONS:
            continue
        following = blocks[index + 1] if index + 1 < len(blocks) else None
        if following is None or following["section_id"] != block["section_id"]:
            continue
        # "ClarityStack: Multi-Model Knowledge Platform | github…" is a project
        # title even though it starts like a label: what follows decides.
        if following["kind"] in {"bullet", "subtitle"}:
            block["kind"] = "entry"


def _assign_groups(blocks: list[dict]) -> None:
    section_id: object = object()
    group: str | None = None
    for block in blocks:
        if block["section_id"] != section_id:
            section_id, group = block["section_id"], None
        if block["kind"] == "entry":
            group = block["id"]
        block["group"] = group if block["kind"] not in {"heading", "name", "contact"} else None


def editable(block: dict) -> bool:
    """Whether a student may retype this block. Masked text never is."""
    return not block.get("masked") and block.get("kind") not in {"name"}


def header_name(blocks: Iterable[dict]) -> str | None:
    for block in blocks:
        if block.get("kind") == "name" and not block.get("masked"):
            return str(block.get("text") or "").strip() or None
    return None


# ---------------------------------------------------------------------------
#  Style, read off the original
# ---------------------------------------------------------------------------

DEFAULT_STYLE: dict[str, Any] = {
    "page": [595.28, 841.89],  # A4, the paper Indian placement cells print on
    "margin": [48.0, 40.0, 48.0, 40.0],  # left, top, right, bottom
    "size": 10.5,
    "family": "sans",
    "source": "default",
}

_SERIF = re.compile(
    r"times|serif|roman|cmr|lmroman|georgia|garamond|cambria|palatino|book|minion|charter|"
    r"tinos|libertin|baskerville|caslon|didot|bodoni|merriweather|lora|crimson|ptserif",
    re.IGNORECASE,
)


def detect_style(pdf: bytes | None) -> dict[str, Any]:
    """Page size, margins, body size and family of the uploaded file.

    Defaults for a pasted resume or anything this cannot read. Margins are
    clamped: a resume set edge to edge would print with its text cut off.
    """
    style = dict(DEFAULT_STYLE)
    if not pdf:
        return style
    try:
        import pymupdf
    except ImportError:
        return style
    try:
        with pymupdf.open(stream=pdf, filetype="pdf") as document:
            page = document[0]
            width, height = page.rect.width, page.rect.height
            fonts: Counter[str] = Counter()
            sizes: Counter[float] = Counter()
            x0s: list[float] = []
            x1s: list[float] = []
            y0s: list[float] = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        count = len(span["text"].strip())
                        if not count:
                            continue
                        fonts[str(span["font"])] += count
                        sizes[round(float(span["size"]) * 2) / 2] += count
                        x0s.append(span["bbox"][0])
                        x1s.append(span["bbox"][2])
                        y0s.append(span["bbox"][1])
    except Exception:  # noqa: BLE001 - an unreadable file falls back to defaults
        return style
    if not sizes:
        return style
    body = sizes.most_common(1)[0][0]
    serif = sum(c for f, c in fonts.items() if _SERIF.search(f) and "sans" not in f.lower())
    left = min(x0s)
    right = width - max(x1s)
    top = min(y0s)
    clamp = lambda v: round(min(max(v, 28.0), 72.0), 1)  # noqa: E731
    style.update(
        page=[round(width, 2), round(height, 2)],
        margin=[clamp(left), clamp(top), clamp(right), clamp(top)],
        size=min(max(float(body), 9.0), 12.0),
        family="serif" if serif > sum(fonts.values()) / 2 else "sans",
        source="original",
    )
    return style


# ---------------------------------------------------------------------------
#  Layout
# ---------------------------------------------------------------------------

_FONTS = {
    "sans": ("helv", "hebo", "heit"),
    "serif": ("tiro", "tibo", "tiit"),
}


@dataclass
class Rendered:
    pdf: bytes
    pages: list[tuple[float, float]]
    #: block id -> one entry per laid-out line: page, rect, and the character
    #: range of the block's text that line shows.
    boxes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass
class _Token:
    text: str
    start: int
    font: Any
    width: float


def _tokens(text: str, fonts: list[tuple[int, Any]], size: float) -> list[_Token]:
    """Words of `text` with their offsets, each in the font that covers it.

    `fonts` is [(from_offset, font)], ascending — a bold label, then regular.
    """

    def font_at(at: int):
        chosen = fonts[0][1]
        for start, font in fonts:
            if at >= start:
                chosen = font
        return chosen

    out: list[_Token] = []
    for match in re.finditer(r"\S+", text):
        word, start = match.group(0), match.start()
        font = font_at(start)
        out.append(_Token(word, start, font, font.text_length(word, fontsize=size)))
    return out


def _wrap(tokens: list[_Token], widths: Any, size: float) -> list[list[_Token]]:
    """Greedy wrap. `widths` is one width, or a function of the line number —
    narrower for the lines that sit beside the photo."""
    lines: list[list[_Token]] = []
    line: list[_Token] = []
    used = 0.0
    for token in tokens:
        width = widths(len(lines)) if callable(widths) else widths
        space = token.font.text_length(" ", fontsize=size) if line else 0.0
        if line and used + space + token.width > width:
            lines.append(line)
            line, used, space = [], 0.0, 0.0
            width = widths(len(lines)) if callable(widths) else widths
        if not line and token.width > width:
            # A single run longer than the line (a URL): break it by characters.
            piece, piece_start = "", token.start
            for offset, ch in enumerate(token.text):
                trial = piece + ch
                if piece and token.font.text_length(trial, fontsize=size) > width:
                    lines.append(
                        [
                            _Token(
                                piece,
                                piece_start,
                                token.font,
                                token.font.text_length(piece, fontsize=size),
                            )
                        ]
                    )
                    piece, piece_start = ch, token.start + offset
                else:
                    piece = trial
            token = _Token(
                piece, piece_start, token.font, token.font.text_length(piece, fontsize=size)
            )
        line.append(token)
        used += space + token.width
    if line:
        lines.append(line)
    return lines


class _Page:
    def __init__(self, document, style: dict[str, Any]):
        import pymupdf

        self.pymupdf = pymupdf
        width, height = style["page"]
        self.page = document.new_page(width=width, height=height)
        self.writer = pymupdf.TextWriter(self.page.rect)
        self.number = document.page_count
        self.rects: list[tuple[float, float, float, float]] = []

    def write(self, x: float, baseline: float, text: str, font, size: float) -> None:
        if text:
            self.writer.append((x, baseline), text, font=font, fontsize=size)

    def bar(self, rect: tuple[float, float, float, float]) -> None:
        self.rects.append(rect)

    def close(self) -> None:
        self.writer.write_text(self.page, color=(0, 0, 0))
        for rect in self.rects:
            self.page.draw_rect(
                self.pymupdf.Rect(*rect), color=(0, 0, 0), fill=(0, 0, 0), overlay=True
            )


def render(
    blocks: list[dict],
    style: dict[str, Any] | None = None,
    *,
    reveal: dict[str, str] | None = None,
    print_contact: bool = False,
    title: str | None = None,
    photo: bytes | None = None,
) -> Rendered:
    """Lay the blocks out as a PDF.

    `reveal` maps a masked block's id to its real text, and lines are always
    MEASURED against it, so the page breaks the same way whoever it is for.
    With `print_contact` those characters are printed — the student's own
    download. Without it each one is a filled bar and the real characters are
    nowhere in the file, which is what every rendered image is made from
    (FR-1.17): the preview and the download differ in those pixels and no
    others.
    """
    import pymupdf

    style = {**DEFAULT_STYLE, **(style or {})}
    regular_name, bold_name, italic_name = _FONTS.get(style["family"], _FONTS["sans"])
    regular, bold, italic = (
        pymupdf.Font(regular_name),
        pymupdf.Font(bold_name),
        pymupdf.Font(italic_name),
    )
    size = float(style["size"])
    width, height = style["page"]
    left, top, right, bottom = style["margin"]
    column = width - left - right
    leading = 1.19

    document = pymupdf.open()
    pages: list[_Page] = []
    boxes: dict[str, list[dict[str, Any]]] = {}
    state = {"y": top, "page": None}

    def page() -> _Page:
        if state["page"] is None:
            state["page"] = _Page(document, style)
            pages.append(state["page"])
            state["y"] = top
        return state["page"]

    def need(height_needed: float) -> None:
        page()
        if state["y"] + height_needed > height - bottom and state["y"] > top + 1:
            state["page"].close()
            state["page"] = None
            page()

    def shown(block: dict) -> tuple[str, str]:
        """(text to measure and print, mask pattern) for one block."""
        text = block.get("text") or ""
        if block.get("masked"):
            real = (reveal or {}).get(block["id"])
            if real is not None and len(real) == len(text):
                return real, text
            return text, text
        return text, ""

    def draw_line(
        p: _Page,
        tokens: list[_Token],
        x: float,
        baseline: float,
        fsize: float,
        mask: str,
        printable: bool,
        stretch: float = 0.0,
    ) -> float:
        """Draw one wrapped line; returns its right edge. `stretch` is the
        extra width each gap between words takes when the line is justified."""
        cursor = x
        for index, token in enumerate(tokens):
            if index:
                cursor += token.font.text_length(" ", fontsize=fsize) + stretch
            if not mask:
                p.write(cursor, baseline, token.text, token.font, fsize)
                cursor += token.width
                continue
            # A token with masked characters: print the clear runs, and either
            # the real characters (download) or a bar (every image).
            run_start = 0
            pattern = mask[token.start : token.start + len(token.text)]
            while run_start < len(token.text):
                hidden = pattern[run_start] == MASK if run_start < len(pattern) else False
                run_end = run_start
                while run_end < len(token.text) and (
                    (pattern[run_end] == MASK if run_end < len(pattern) else False) == hidden
                ):
                    run_end += 1
                piece = token.text[run_start:run_end]
                piece_width = token.font.text_length(piece, fontsize=fsize)
                if hidden and not printable:
                    p.bar(
                        (
                            cursor,
                            baseline - fsize * 0.78,
                            cursor + piece_width,
                            baseline + fsize * 0.2,
                        )
                    )
                else:
                    p.write(cursor, baseline, piece, token.font, fsize)
                cursor += piece_width
                run_start = run_end
        return cursor

    beside_photo: dict[str, Any] = {"page": None, "bottom": 0.0, "reserve": 0.0}

    def paragraph(
        block: dict,
        *,
        fsize: float,
        fonts: list[tuple[int, Any]],
        indent: float = 0.0,
        align: str = "left",
        aside: str | None = None,
        aside_font=None,
        before: float = 0.0,
        justify: bool = False,
        right: float = 0.0,
    ) -> None:
        text, mask = shown(block)
        printable = print_contact and block["id"] in (reveal or {})
        if not text.strip():
            return
        aside_width = (
            (aside_font or regular).text_length(aside, fontsize=fsize) + 12 if aside else 0.0
        )
        line_height = fsize * leading
        first_line_y = state["y"] + before

        def width_at(number: int) -> float:
            """The column for line `number`: narrower while it is beside the photo."""
            y = first_line_y + number * line_height
            beside = (
                beside_photo["reserve"]
                if state["page"] is beside_photo["page"] and y < beside_photo["bottom"]
                else 0.0
            )
            return column - max(right, beside)

        wrapped = _wrap(
            _tokens(text, fonts, fsize), lambda n: width_at(n) - indent - aside_width, fsize
        )
        state["y"] += before
        placed: list[dict[str, Any]] = []
        for number, tokens in enumerate(wrapped):
            width = width_at(number)
            need(line_height)
            p = page()
            baseline = state["y"] + fsize * 0.92
            line_width = sum(t.width for t in tokens) + sum(
                t.font.text_length(" ", fontsize=fsize) for t in tokens[1:]
            )
            x = left + indent
            if align == "center":
                x = left + (width - line_width) / 2
            # Justified like the typeset original, except a paragraph's last
            # line, and never into gaps wide enough to read as missing words.
            stretch = 0.0
            if justify and number < len(wrapped) - 1 and len(tokens) > 1:
                gap = ((width - indent - aside_width) - line_width) / (len(tokens) - 1)
                stretch = gap if 0 < gap < fsize else 0.0
            right_edge = draw_line(p, tokens, x, baseline, fsize, mask, printable, stretch)
            if number == 0 and aside:
                aside_x = left + width - (aside_font or regular).text_length(aside, fontsize=fsize)
                p.write(aside_x, baseline, aside, aside_font or regular, fsize)
                right_edge = max(right_edge, left + width)
            start = tokens[0].start
            end = tokens[-1].start + len(tokens[-1].text)
            placed.append(
                {
                    "page": p.number,
                    "rect": [
                        round(x - 1.5, 2),
                        round(state["y"], 2),
                        round(right_edge + 1.5, 2),
                        round(state["y"] + line_height, 2),
                    ],
                    "start": start,
                    "end": end,
                }
            )
            state["y"] += line_height
        boxes[block["id"]] = placed

    # A heading with nothing visible under it (up to the next heading) is not
    # printed on its own. Positional, not by section id: the parser can split
    # one printed section in two ("SKILLS" then "Languages: Python").
    empty_headings: set[str] = set()
    for index, block in enumerate(blocks):
        if block.get("kind") != "heading":
            continue
        following = []
        for later in blocks[index + 1 :]:
            if later.get("kind") == "heading":
                break
            following.append(later)
        if not any(not b.get("hidden") and (b.get("text") or "").strip() for b in following):
            empty_headings.add(block["id"])
    visible = [b for b in blocks if not b.get("hidden") and b["id"] not in empty_headings]

    # The student's picture, top right of the first page as most photo resumes
    # set it (2026-11-17). The header then reads left-aligned beside it, and
    # the body starts below whichever of the two ends lower.
    header_right = 0.0
    if photo:
        try:
            pixmap = pymupdf.Pixmap(photo)
            aspect = pixmap.width / pixmap.height if pixmap.height else 1.0
        except Exception:  # noqa: BLE001 - a picture that will not open is left out
            pixmap, aspect = None, 1.0
        if pixmap is not None:
            box_h = size * 6.8
            box_w = box_h * min(max(aspect, 0.7), 1.3)
            first = page()
            rect = pymupdf.Rect(left + column - box_w, top, left + column, top + box_h)
            first.page.insert_image(rect, stream=photo, keep_proportion=True)
            boxes["photo"] = [
                {"page": first.number, "rect": [round(v, 2) for v in rect], "start": 0, "end": 0}
            ]
            header_right = box_w + 14
            beside_photo.update(page=first, bottom=top + box_h + 4, reserve=header_right)

    previous: str | None = None
    for block in visible:
        kind = block.get("kind")
        if kind == "name":
            paragraph(
                block,
                fsize=size * 1.75,
                fonts=[(0, bold)],
                align="left" if header_right else "center",
                right=header_right,
            )
            state["y"] += 1
        elif kind == "contact":
            paragraph(
                block,
                fsize=size * 0.95,
                fonts=[(0, regular)],
                align="left" if header_right else "center",
                right=header_right,
            )
        elif kind == "heading":
            before = size * (0.7 if previous else 0)
            heading_size = size * 1.1
            need(before + heading_size * leading + size * leading * 2)
            paragraph(block, fsize=heading_size, fonts=[(0, bold)], before=before)
            p = page()
            rule_y = state["y"] - heading_size * 0.12
            # A rule that would run under the photo stops short of it.
            rule_end = (
                left
                + column
                - (
                    beside_photo["reserve"]
                    if p is beside_photo["page"] and rule_y < beside_photo["bottom"]
                    else 0.0
                )
            )
            p.page.draw_line((left, rule_y), (rule_end, rule_y), color=(0, 0, 0), width=0.6)
            state["y"] += 1.5
        elif kind == "entry":
            before = size * 0.3 if previous not in {"heading", None} else 0.0
            need(before + size * leading * 2)
            paragraph(
                block,
                fsize=size,
                fonts=[(0, bold)],
                aside=block.get("aside"),
                aside_font=regular,
                before=before,
            )
        elif kind == "subtitle":
            paragraph(
                block, fsize=size, fonts=[(0, italic)], aside=block.get("aside"), aside_font=italic
            )
        elif kind == "bullet":
            text = block.get("text") or ""
            if not text.strip():
                continue
            need(size * leading)
            p = page()
            p.write(left + 3, state["y"] + size * 0.92, "•", regular, size)
            paragraph(block, fsize=size, fonts=[(0, regular)], indent=13.0, justify=True)
        else:
            text = block.get("text") or ""
            label = LABEL.match(text)
            fonts = [(0, bold), (label.end(), regular)] if label else [(0, regular)]
            paragraph(
                block,
                fsize=size,
                fonts=fonts,
                aside=block.get("aside"),
                aside_font=regular,
                justify=block.get("section") == "summary",
            )
        previous = kind

    if state["page"] is None and not pages:
        page()
    if state["page"] is not None:
        state["page"].close()

    sizes = [(round(float(width), 2), round(float(height), 2)) for _ in pages]
    if title:
        document.set_metadata({"title": title, "creator": "MNEMOS Prep", "producer": "MNEMOS Prep"})
    try:
        # Only the glyphs used: a whole embedded Times is ~350 KB per file.
        document.subset_fonts()
    except Exception:  # noqa: BLE001 - a bigger file is still the right file
        pass
    data = document.tobytes(garbage=3, deflate=True)
    document.close()
    return Rendered(pdf=data, pages=sizes, boxes=boxes)


# ---------------------------------------------------------------------------
#  Changes
# ---------------------------------------------------------------------------


class BlockPatch(BaseModel):
    """What a student (or a suggestion they accepted) changes about one block."""

    text: str | None = None
    aside: str | None = None
    hidden: bool | None = None
    #: `manual`, or `jd:<suggestion key>` when a suggestion was applied.
    source: str = "manual"
    note: str | None = None


class BlockInsert(BaseModel):
    """A line the student supplies — never one this module writes for them."""

    after: str
    text: str
    kind: str = "bullet"
    source: str = "manual"
    note: str | None = None


class BlockMove(BaseModel):
    """Move a block — or, for an entry, the entry with everything under it."""

    block_id: str
    #: Put it before this block. None puts it at the end of its section.
    before: str | None = None
    source: str = "manual"
    note: str | None = None


class ChangeRefused(ValueError):
    """A change that would break a rule this file holds. The message is shown."""


def _clean(text: str) -> str:
    return " ".join(text.split())


def apply_patch(
    blocks: list[dict], block_id: str, patch: BlockPatch
) -> tuple[list[dict], str, str | None, str | None]:
    """The blocks after `patch`, plus (action, before, after) for the history."""
    out = [dict(b) for b in blocks]
    target = next((b for b in out if b["id"] == block_id), None)
    if target is None:
        raise KeyError(block_id)

    if patch.text is not None:
        text = _clean(patch.text)
        if not editable(target):
            raise ChangeRefused(
                "This line holds your contact details, which are masked on screen — it can be "
                "hidden or moved, not retyped here."
            )
        if not text:
            raise ChangeRefused("A line can't be empty — hide it instead.")
        if BLANK.search(text):
            raise ChangeRefused(
                "Fill every [blank] with your own facts first — a line with one isn't saved."
            )
        before, after = target["text"], text
        if before == after and patch.aside is None:
            raise ChangeRefused("That is already what the line says.")
        target["text"] = text
        if patch.aside is not None:
            target["aside"] = _clean(patch.aside) or None
        return out, "edit", before, after

    if patch.aside is not None:
        before, after = target.get("aside"), _clean(patch.aside) or None
        target["aside"] = after
        return out, "edit", before, after

    if patch.hidden is not None:
        if target["kind"] == "name":
            raise ChangeRefused("Your name stays on the page.")
        target["hidden"] = bool(patch.hidden)
        if target["kind"] == "entry":
            # An entry hides with everything under it, and comes back the same way.
            for block in out:
                if block.get("group") == target["id"]:
                    block["hidden"] = bool(patch.hidden)
        return out, "hide" if patch.hidden else "show", target["text"], None

    raise ChangeRefused("Nothing to change.")


def insert_block(blocks: list[dict], insert: BlockInsert) -> tuple[list[dict], dict]:
    out = [dict(b) for b in blocks]
    index = next((i for i, b in enumerate(out) if b["id"] == insert.after), None)
    if index is None:
        raise KeyError(insert.after)
    text = _clean(insert.text)
    if not text:
        raise ChangeRefused("Write the line first.")
    if BLANK.search(text):
        raise ChangeRefused(
            "Fill every [blank] with your own facts first — a line with one isn't saved."
        )
    if insert.kind not in {"bullet", "text"}:
        raise ChangeRefused("Only a bullet or a plain line can be added.")
    anchor = out[index]
    # After an entry, a new bullet goes after the entry's last line, not between
    # the title and its subtitle.
    group = anchor["id"] if anchor["kind"] == "entry" else anchor.get("group")
    if group is not None:
        while index + 1 < len(out) and out[index + 1].get("group") == group:
            index += 1
    block = {
        "id": f"n{uuid.uuid4().hex[:6]}",
        "kind": insert.kind,
        "section": anchor.get("section"),
        "section_id": anchor.get("section_id"),
        "group": group,
        "text": text,
        "original": "",
        "aside": None,
        "claim_id": None,
        "span": None,
        "masked": False,
        "hidden": False,
        "added": True,
    }
    out.insert(index + 1, block)
    return out, block


def move_block(blocks: list[dict], move: BlockMove) -> list[dict]:
    """Move a block, or a whole entry, within its own section."""
    out = [dict(b) for b in blocks]
    target = next((b for b in out if b["id"] == move.block_id), None)
    if target is None:
        raise KeyError(move.block_id)
    if target["kind"] in {"name", "contact", "heading"}:
        raise ChangeRefused("That line stays where it is.")
    if target["kind"] == "entry":
        unit = [b for b in out if b["id"] == target["id"] or b.get("group") == target["id"]]
    else:
        unit = [target]
    ids = {b["id"] for b in unit}
    rest = [b for b in out if b["id"] not in ids]
    if move.before is None:
        section_last = max(
            (i for i, b in enumerate(rest) if b.get("section_id") == target.get("section_id")),
            default=len(rest) - 1,
        )
        at = section_last + 1
    else:
        anchor = next((i for i, b in enumerate(rest) if b["id"] == move.before), None)
        if anchor is None:
            raise KeyError(move.before)
        if rest[anchor].get("section_id") != target.get("section_id"):
            raise ChangeRefused("A line moves within its own section.")
        at = anchor
    return rest[:at] + unit + rest[at:]


def edited_count(blocks: Iterable[dict]) -> int:
    return sum(
        1
        for b in blocks
        if b.get("added") or b.get("hidden") or (b.get("text") or "") != (b.get("original") or "")
    )


def original_photo(pdf: bytes | None) -> bytes | None:
    """The photo printed on page 1 of the uploaded resume, as a PNG, or None.

    The fallback when the student has not set a picture in Settings: a resume
    that carried a photo keeps it when tailored. Only an image that looks like
    a photo of a person on a resume does — in the top third of the page, close
    to square, at least an inch across — so a logo or a QR code is not taken
    for one.
    """
    if not pdf:
        return None
    try:
        import pymupdf
    except ImportError:
        return None
    try:
        with pymupdf.open(stream=pdf, filetype="pdf") as document:
            page = document[0]
            best: tuple[float, int] | None = None
            for image in page.get_images(full=True):
                xref = image[0]
                try:
                    rect = page.get_image_bbox(image)
                except Exception:  # noqa: BLE001 - an image with no placement is not a photo
                    continue
                if rect.is_empty or rect.y0 > page.rect.height / 3:
                    continue
                ratio = rect.width / rect.height if rect.height else 0
                area = rect.width * rect.height
                if not 0.6 <= ratio <= 1.4 or rect.width < 50 or rect.height < 50:
                    continue
                if best is None or area > best[0]:
                    best = (area, xref)
            if best is None:
                return None
            pixmap = pymupdf.Pixmap(document, best[1])
            if pixmap.alpha:
                pixmap = pymupdf.Pixmap(pixmap, 0)
            if pixmap.colorspace is not None and pixmap.colorspace.n not in (1, 3):
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
            # A scanned photo is often 1-2 MB; a resume prints it an inch wide.
            while min(pixmap.width, pixmap.height) > 700:
                pixmap.shrink(1)
            return pixmap.tobytes("jpg", jpg_quality=88)
    except Exception:  # noqa: BLE001 - an unreadable file simply has no photo to offer
        return None

"""Claims: what the resume asserts, and how defensible each assertion is.

Spec: plan_in_depth/M01_Resume_Ingestion.md §5 (data contracts), FR-1.5, FR-1.6,
FR-1.8, FR-1.9, FR-1.10, FR-1.13, FR-1.17.

── Why this module is deterministic ────────────────────────────────────────────

Every score and every probe here is computed from the text by rule, not by a
model. Three reasons, in order of how much they matter:

1. **The platform's test rule.** No test opens a socket, so the 685-test suite
   runs offline on a marker's laptop with no API key. A claim pipeline that
   needs a model to produce a `specificity` score cannot be tested that way,
   and an untested scorer is one nobody can show is not arbitrary.

2. **A score you cannot explain is a score a student cannot argue with.**
   `ownership_clarity` here is "does this bullet say I, we, or nothing", which
   is inspectable and appealable. "The model said 0.4" is neither.

3. **It is honest about what M01 is.** This module reads claims; it does not
   test them. The scores are properties of the SENTENCE - is it specific, is it
   checkable, does it say who did the work - never judgements of the student.

An LLM pass belongs on top of this, not instead of it: FR-1.19's STAR rewrite
is explicitly on-request and generative, and that is the right shape for one.

── The span is the point ───────────────────────────────────────────────────────

`SourceSpan` is called "the atom of traceability - everything downstream cites
one of these" in the spec. Offsets here index the ORIGINAL text, never the
redacted copy, so a span can always be re-verified against the stored artifact
by offset. That is the same mechanism M13 uses for evidence, and it is why the
contact block is redacted for display rather than stripped from storage: strip
it and every offset after it moves.
"""

from __future__ import annotations

import difflib
import logging
import re
import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal, NamedTuple, Protocol

from pydantic import BaseModel, Field

from backend_M01_Resume_Ingestion import config, dates, headings

log = logging.getLogger("uvicorn.error")


class Geometry(Protocol):
    """Whatever can turn an offset range back into a page and a box.

    `documents.Document` satisfies this. Stated as a protocol so claims.py does
    not import the PDF layer: the paste path has no geometry at all and must
    not drag PyMuPDF in behind it.
    """

    def geometry_for(
        self, start: int, end: int
    ) -> tuple[int, tuple[float, float, float, float] | None]: ...

    #: Offset of a line's first character -> how that line is set. Empty for a
    #: source with no typography, which is every source except a PDF.
    line_styles: dict[int, Any]


# ---------------------------------------------------------------------------
#  Contracts (spec §5)
# ---------------------------------------------------------------------------

SectionKind = Literal[
    "contact",
    "summary",
    "education",
    "experience",
    "projects",
    "skills",
    "achievements",
    "certifications",
    "publications",
    "extras",
    "unknown",
]

ClaimType = Literal["built", "improved", "led", "researched", "achieved", "used", "learned"]
RiskBand = Literal["strong", "vague", "risky"]


class SourceSpan(BaseModel):
    """The atom of traceability. Everything downstream cites one of these."""

    artifact_id: uuid.UUID
    page: int = 1
    start: int
    end: int
    #: Populated only for PDFs with a text layer. Pasted text has no geometry,
    #: and inventing one would put a highlight box on a page that does not
    #: exist.
    bbox: tuple[float, float, float, float] | None = None
    text: str


class ResumeSection(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    kind: SectionKind
    span: SourceSpan
    confidence: float
    user_corrected: bool = False


class Quantifier(BaseModel):
    raw: str
    value: float
    unit: str | None = None
    metric_hint: str | None = None
    span: SourceSpan


class ClaimProbe(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    claim_id: uuid.UUID
    depth: Literal[0, 1, 2, 3]
    question: str
    expects: list[str]
    rationale: str
    generated_by: str


class ResumeClaim(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    resume_id: uuid.UUID
    section_id: uuid.UUID
    span: SourceSpan
    text: str
    claim_type: ClaimType
    subject_concepts: list[str] = Field(default_factory=list)
    quantifiers: list[Quantifier] = Field(default_factory=list)
    specificity: float
    verifiability: float
    ownership_clarity: float
    recency: float
    risk_score: float
    risk_band: RiskBand
    linked_repo_id: uuid.UUID | None = None
    prominence: float
    user_edited: bool = False
    probes: list[ClaimProbe] = Field(default_factory=list)


class RedFlag(BaseModel):
    kind: Literal[
        "timeline_gap",
        "chronology_conflict",
        "claim_skill_mismatch",
        "unverifiable_superlative",
        "title_inflation",
        "duplicate_project",
    ]
    severity: Literal["info", "notable", "serious"]
    explanation: str
    spans: list[SourceSpan] = Field(default_factory=list)
    suggested_answer: str | None = None


class ContactBlock(BaseModel):
    """PII, stored apart and never returned with the resume (FR-1.17).

    Kept at all because identity needs it: a placement cell has to know whose
    resume this is. Nothing else does, so nothing else receives it.
    """

    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    #: Character ranges of the original text that hold the above, so the
    #: display copy can be redacted without moving any other offset.
    spans: list[tuple[int, int]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
#  Section segmentation (FR-1.5)
# ---------------------------------------------------------------------------

#: A line that is mostly just a heading, which is what a heading looks like in
#: every resume template that is not a table. The lexicon it is matched against
#: lives in `headings.py` — shared with `extract.py`, because a heading known to
#: one and not the other is a section labelled right whose skills are invisible.
_HEADING_LINE = re.compile(r"^\s*[-*•·]?\s*([A-Za-z][A-Za-z0-9 /&,'’.-]{2,44})\s*:?\s*$")

#: The same heading with its content on the same line — `Skills: Python, SQL`.
#: The shape a one-page resume uses, and one where the heading is doing two
#: jobs at once.
#:
#: Gated on an EXACT lexicon hit, never a partial one, and that is the whole
#: safety of it. A partial match would make "Languages Known: Tamil, English"
#: a skills section on the strength of the word "languages", and turn every
#: `Label: value` line in a PERSONAL DETAILS block — "Date of Birth:",
#: "Percentage:" — into a candidate. Requiring the label to be a heading the
#: lexicon knows exactly is what keeps that to the lines that really are
#: headings.
_INLINE_HEADING_LINE = re.compile(r"^\s*[-*•·]?\s*([A-Za-z][A-Za-z0-9 /&]{2,40}?)\s*:\s*(\S.*)$")

#: §3.2.2: *"A 'bullet' isn't a bullet. Real resumes use •, -, ▪, ‣, o,
#: numbers, or nothing at all (line breaks only). Bullet detection is a
#: line-classification problem, not a character match."*
#:
#: The glyph set is the easy half. The `o` form is the one that catches people
#: out: Word autoformats a lowercase o into a bullet and exports it as the
#: letter, so it has to be recognised — but only when followed by a space and a
#: capital, or every line starting with the word "on" becomes a bullet.
_BULLET_GLYPH = r"[-*•·▪▫●○◦‣▸►»→–—+]"
_BULLET_LINE = re.compile(
    rf"^(?P<indent>\s*)(?:{_BULLET_GLYPH}|\d{{1,2}}[.)]|[oO](?=\s+[A-Z]))\s+(?P<body>.*\S)\s*$"
)

#: A continuation of the bullet above: indented further than the marker, and
#: not itself a bullet. This is the hanging indent §6.5.1 asks for.
_CONTINUATION = re.compile(r"^(?P<indent>[ \t]{2,})(?P<body>\S.*\S|\S)\s*$")

#: EC-1.10's fallback. A paragraph-style resume has no markers at all, so
#: sentences become the unit. Split on terminal punctuation followed by a
#: capital, which keeps "3.5 CGPA" and "Node.js" intact.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

#: Below this many characters a "sentence" is a fragment — a heading that lost
#: its newline, a date, a stray initial — and not a claim anybody can defend.
_MIN_CLAIM_CHARS = 25

#: A line that is mostly redaction marks is not a claim.
#:
#: Two things mask text before claims are extracted: the contact block
#: (FR-1.17) and the injection filter (§6.7). Both preserve length, which is
#: what keeps every offset valid — and it also means a bullet that was entirely
#: an injection attempt survives as a bullet-shaped run of blocks. Left in, it
#: becomes a scored claim with three generated probes about nothing, sitting on
#: the student's Claim Map. A legitimate student never sees this; the one who
#: tried it gets no feedback either way, which is what §6.7 asks for.
_MASK_TOLERANCE = 0.4


def _is_readable(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    masked = stripped.count("█")
    return masked / len(stripped) <= _MASK_TOLERANCE


def _heading_kind(line: str) -> tuple[SectionKind, float] | None:
    """(kind, confidence) if this line is a section heading.

    The lexicon lookup is in `headings.py`; what is decided here is the
    CONFIDENCE, because that is a property of how the line is set rather than of
    which words are in it. §6.3 lists ALL CAPS and "< 5 words" among its
    heuristics: both are corroboration a template gives you for free, and
    neither is a requirement — plenty of resumes write headings in title case.
    """
    # A bullet is never a heading.
    #
    # `_HEADING_LINE` tolerates a leading glyph because some templates set
    # headings as `• EDUCATION`, and the cost of that tolerance was this: the
    # bullet "- Built internal tooling for the platform team" partial-matched
    # `tooling` and started a SKILLS section in the middle of an experience
    # block, stranding every bullet after it. It escaped the golden set only
    # because the fixture bullets happened to be longer than the 45-character
    # cap, which is not a guard, it is a coincidence.
    if _BULLET_LINE.match(line):
        return None

    match = _HEADING_LINE.match(line)
    if match:
        found = headings.lookup(match.group(1))
        if found is None:
            return None
        kind, confidence = found
        stripped = line.strip()
        words = len(stripped.split())

        # A PARTIAL lexicon hit needs the line to look like a heading on its
        # own terms. §6.3's "< 5 words" heuristic is what separates the
        # heading "Tools" from the sentence "built internal tooling for the
        # platform team", which contains the same word and means nothing like
        # it. An exact hit is trusted at any length — "Positions of
        # Responsibility" is five words and unambiguous.
        if confidence < 0.85 and words > 4:
            return None

        if confidence >= 0.85 and (stripped.isupper() or words <= 4):
            confidence = 0.95
        return kind, confidence

    inline = _INLINE_HEADING_LINE.match(line)
    if inline:
        found = headings.lookup(inline.group(1))
        # Exact hits only — see `_INLINE_HEADING_LINE`. A partial match here
        # turns every `Label: value` line into a section boundary.
        if found is not None and found[1] >= 0.85:
            # Below a standalone heading's confidence on purpose: the line is
            # doing two jobs, so it is weaker evidence of a section boundary
            # than a line that does nothing else.
            return found[0], 0.75
    return None


def _is_typographic_heading(
    line: str,
    style: Any,
    lines: list[str],
    index: int,
) -> bool:
    """A heading the lexicon does not know, recognised by how it is set (§6.3).

    Deliberately strict, because a false heading splits a section in half and
    strands every bullet after it. Four of §6.3's signals have to agree: set
    like a heading (bold or noticeably larger), short, not ending in sentence
    punctuation, and followed by a blank line or a bullet.

    A line that is merely bold is not enough — a bolded job title inside an
    experience block is bold, short, and not a heading.
    """
    if style is None or not style.looks_like_a_heading:
        return False

    stripped = line.strip()
    if not stripped or len(stripped.split()) > 4 or len(stripped) > 40:
        return False
    if stripped[-1] in ".,;:!?":
        return False
    if _BULLET_LINE.match(line):
        return False
    # A heading introduces something. A bolded last line introduces nothing.
    following = lines[index + 1 : index + 3]
    if not following:
        return False
    return any(not f.strip() or _BULLET_LINE.match(f) for f in following)


def segment(
    text: str,
    artifact_id: uuid.UUID,
    *,
    geometry: Geometry | None = None,
    confidence_penalty: float = 0.0,
) -> list[ResumeSection]:
    """Split the resume into sections, each with a confidence.

    A resume with no recognisable headings is not an error: it produces one
    `unknown` section covering the whole document at low confidence, which is
    the honest description of "we could not tell what any of this is".

    `confidence_penalty` is how much less certain everything in this document
    is — 0.15 when it came out of OCR (§6.2.6). Applied once, here, rather than
    remembered by each caller.
    """

    def _make(kind: SectionKind, start: int, end: int, confidence: float) -> ResumeSection:
        page, bbox = geometry.geometry_for(start, end) if geometry else (1, None)
        return ResumeSection(
            kind=kind,
            confidence=round(max(0.0, confidence - confidence_penalty), 3),
            span=SourceSpan(
                artifact_id=artifact_id,
                page=page,
                start=start,
                end=end,
                bbox=bbox,
                text=text[start:end],
            ),
        )

    styles = getattr(geometry, "line_styles", None) or {}

    lines = text.splitlines(keepends=True)
    marks: list[tuple[int, SectionKind, float]] = []
    offset = 0
    for index, line in enumerate(lines):
        found = _heading_kind(line)
        if found:
            kind, confidence = found
            # §6.3 scores a candidate heading on seven signals, of which the
            # lexicon is one. When the document carries type, a line SET like a
            # heading corroborates the lexicon hit and raises the confidence.
            style = styles.get(offset)
            if style is not None and style.looks_like_a_heading:
                confidence = min(0.98, confidence + 0.1)
            marks.append((offset, kind, confidence))
        elif _is_typographic_heading(line, styles.get(offset), lines, index):
            # The other half, and the reason the typographic tier is worth
            # having at all: a heading the lexicon has never seen is invisible
            # to a lexicon-only matcher however obviously it is set, and every
            # resume template invents one. `unknown` rather than a guessed kind
            # — we can see it is a heading and we cannot see what of.
            marks.append((offset, "unknown", 0.55))
        offset += len(line)

    if not marks:
        return [_make("unknown", 0, len(text), 0.2)]

    sections: list[ResumeSection] = []

    # Anything before the first heading is the header block: name and contact.
    if marks[0][0] > 0:
        sections.append(_make("contact", 0, marks[0][0], 0.5))

    for index, (start, kind, confidence) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        sections.append(_make(kind, start, end, confidence))

    return sections


# ---------------------------------------------------------------------------
#  Contact block (FR-1.6 entity slice, FR-1.17 PII)
# ---------------------------------------------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
#: Indian mobile numbers with or without +91, and generic 10+ digit runs.
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{5}[\s-]?\d{5}|\+?\d{10,13}")
#: Bare domains count. "github.com/priyash" is the most useful identifier on a
#: student resume and it carries no scheme, so a pattern anchored on http://
#: leaves the one link that matters unredacted.
_LINK = re.compile(
    r"(?:https?://|www\.)[^\s,;)\]]+"
    r"|(?:[A-Za-z0-9-]+\.)+(?:com|org|net|io|dev|in|co|me|ai|app|edu|xyz)"
    r"(?:/[^\s,;)\]]*)?",
    re.IGNORECASE,
)


def extract_contact(text: str) -> ContactBlock:
    """Emails, phones and links, with the ranges they occupy.

    Links are contact-classed too. A GitHub URL is the most useful thing on a
    resume for M03 and it is still an identifier, so it is stored with the
    contact block and released deliberately rather than rendered by default.
    """
    block = ContactBlock()
    for pattern, bucket in ((_EMAIL, block.emails), (_PHONE, block.phones), (_LINK, block.links)):
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            if not value:
                continue
            bucket.append(value)
            block.spans.append((match.start(), match.end()))
    return block


def redact(text: str, block: ContactBlock) -> str:
    """The display copy: contact removed, every other offset unmoved.

    Same length as the original, character for character, because a span
    recorded against the original has to keep pointing at the same words in
    the copy a student is shown.
    """
    if not block.spans:
        return text
    chars = list(text)
    for start, end in block.spans:
        for i in range(start, min(end, len(chars))):
            chars[i] = "█"
    return "".join(chars)


# ---------------------------------------------------------------------------
#  Quantifiers (spec §5)
# ---------------------------------------------------------------------------

_QUANTIFIER = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|percent|ms|milliseconds?|seconds?|s\b|minutes?|hours?|x\b|"
    r"k\b|m\b|lakhs?|crores?|users?|requests?|queries|records?|rows?|nodes?|"
    r"people|members?|students?|teams?)",
    re.IGNORECASE,
)

_METRIC_HINTS: tuple[tuple[str, str], ...] = (
    ("accuracy", "accuracy"),
    ("precision", "accuracy"),
    ("recall", "accuracy"),
    ("f1", "accuracy"),
    ("latency", "latency"),
    ("response time", "latency"),
    ("query time", "latency"),
    ("throughput", "throughput"),
    ("requests", "throughput"),
    ("team of", "team size"),
    ("users", "scale"),
    ("cost", "cost"),
    ("revenue", "revenue"),
)


def _metric_hint(context: str) -> str | None:
    low = context.casefold()
    for needle, hint in _METRIC_HINTS:
        if needle in low:
            return hint
    return None


def extract_quantifiers(text: str, base: int, artifact_id: uuid.UUID) -> list[Quantifier]:
    out: list[Quantifier] = []
    for match in _QUANTIFIER.finditer(text):
        raw = match.group(0)
        unit = (match.group("unit") or "").strip().lower() or None
        window = text[max(0, match.start() - 40) : match.end() + 40]
        out.append(
            Quantifier(
                raw=raw,
                value=float(match.group("value")),
                unit=unit,
                metric_hint=_metric_hint(window),
                span=SourceSpan(
                    artifact_id=artifact_id,
                    start=base + match.start(),
                    end=base + match.end(),
                    text=raw,
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
#  Claims (FR-1.8) and their defensibility (FR-1.9)
# ---------------------------------------------------------------------------

_CLAIM_VERBS: tuple[tuple[ClaimType, tuple[str, ...]], ...] = (
    ("led", ("led", "managed", "mentored", "coordinated", "headed", "supervised", "owned")),
    ("improved", ("improved", "optimised", "optimized", "reduced", "increased", "cut", "sped")),
    ("researched", ("researched", "studied", "investigated", "analysed", "analyzed", "published")),
    ("achieved", ("achieved", "won", "ranked", "awarded", "secured", "qualified", "selected")),
    ("built", ("built", "created", "developed", "designed", "implemented", "engineered", "wrote")),
    ("used", ("used", "worked with", "applied", "utilised", "utilized", "leveraged")),
    ("learned", ("learned", "learnt", "studied", "completed", "trained")),
)

_FIRST_PERSON = re.compile(r"\b(?:i|my|me)\b", re.IGNORECASE)
_TEAM_VOICE = re.compile(r"\b(?:we|our|us|team)\b", re.IGNORECASE)
_SUPERLATIVE = re.compile(
    r"\b(?:best|world[- ]class|cutting[- ]edge|state[- ]of[- ]the[- ]art|revolutionary|"
    r"seamless|robust|scalable|highly optimi[sz]ed|expert|guru|ninja|rockstar)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def classify(text: str) -> ClaimType:
    low = text.casefold()
    for claim_type, verbs in _CLAIM_VERBS:
        for verb in verbs:
            if re.search(rf"\b{re.escape(verb)}\b", low):
                return claim_type
    return "used"


def _recency(text: str, today: date) -> float:
    """1.0 for this year, decaying to the floor over five years.

    No year in the bullet is `RECENCY_UNDATED` and NOT 0.0. "We do not know
    when" is not the same claim as "this is old", and the whole platform turns
    on that distinction.
    """
    years = [int(m.group(0)) for m in _YEAR.finditer(text)]
    if not years:
        return config.RECENCY_UNDATED
    age = max(0, today.year - max(years))
    return max(config.RECENCY_FLOOR, 1.0 - config.RECENCY_DECAY_PER_YEAR * age)


def prominence_of(
    *,
    section_kind: str,
    bullet_index: int,
    start: int,
    document_length: int,
) -> float:
    """How visible this bullet is (§6.6).

        prominence = 0.5·(1 - vertical position)
                   + 0.3·section weight
                   + 0.2·is first bullet in its group

    Not a term in `risk_score`, and `config.py` carries the argument for why at
    length: the band is a property of the sentence, the ordering is a property
    of the page, and folding one into the other means a badly written bullet
    stops being badly written by moving down the page. This drives the Claim
    Map order and §2.3 "the one thing to fix first" card.
    """
    position = (start / document_length) if document_length else 0.0
    weight = config.SECTION_WEIGHT.get(section_kind, config.SECTION_WEIGHT_DEFAULT)
    return round(
        config.PROMINENCE_POSITION * (1.0 - min(1.0, position))
        + config.PROMINENCE_SECTION * weight
        + config.PROMINENCE_FIRST_BULLET * (1.0 if bullet_index == 0 else 0.0),
        3,
    )


def score_claim(
    text: str,
    *,
    quantifiers: list[Quantifier],
    concepts: list[str],
    has_link: bool,
    prominence: float,
    today: date,
) -> dict[str, float]:
    """The four defensibility axes, and the composite risk.

    Each is a property of the sentence, computed from it, and each one can be
    pointed at in the text — which is what makes the band appealable.
    """
    words = text.split()

    # Specificity: named technology, hard numbers, and enough sentence to say
    # something. A bullet with a concept AND a number is the strong shape.
    specificity = 0.0
    if concepts:
        specificity += config.SPECIFICITY_CONCEPT
    if quantifiers:
        specificity += config.SPECIFICITY_QUANTIFIER
    if len(words) >= config.SPECIFICITY_MIN_WORDS:
        specificity += config.SPECIFICITY_LENGTH
    specificity = min(1.0, specificity)

    # Verifiability: is there anything behind it a person could check?
    verifiability = config.VERIFIABILITY_FLOOR
    if has_link:
        verifiability += config.VERIFIABILITY_LINK
    if quantifiers:
        verifiability += config.VERIFIABILITY_QUANTIFIER
    if concepts:
        verifiability += config.VERIFIABILITY_CONCEPT
    verifiability = min(1.0, verifiability)

    # Ownership: "I" is clearest, "we" is shared, neither is passive voice with
    # nobody in it. Deliberately blunt, because it has to be explainable.
    if _FIRST_PERSON.search(text):
        ownership = config.OWNERSHIP_FIRST_PERSON
    elif _TEAM_VOICE.search(text):
        ownership = config.OWNERSHIP_TEAM
    else:
        # A bare verb-led bullet ("Built a route planner") is the resume
        # convention and reads as first person, so it is not punished to the
        # floor.
        ownership = (
            config.OWNERSHIP_VERB_LED
            if re.match(r"^\s*[A-Z][a-z]+ed\b|^\s*[A-Z][a-z]+t\b", text)
            else config.OWNERSHIP_PASSIVE
        )

    recency = _recency(text, today)

    # Composite. Specificity and verifiability carry it because they are what
    # an interviewer probes; recency is a modifier, not a verdict. Weights live
    # in config.py so the calibration is one file rather than four call sites.
    axes = {
        "specificity": specificity,
        "verifiability": verifiability,
        "ownership_clarity": ownership,
        "recency": recency,
    }
    risk = 1.0 - sum(config.RISK_WEIGHTS[name] * value for name, value in axes.items())
    risk = round(max(0.0, min(1.0, risk)), 3)

    return {
        "specificity": round(specificity, 3),
        "verifiability": round(verifiability, 3),
        "ownership_clarity": round(ownership, 3),
        "recency": round(recency, 3),
        "risk_score": risk,
        "prominence": round(prominence, 3),
    }


def band(risk: float) -> RiskBand:
    if risk <= config.BAND_STRONG_MAX:
        return "strong"
    if risk <= config.BAND_VAGUE_MAX:
        return "vague"
    return "risky"


# ---------------------------------------------------------------------------
#  Probes (FR-1.10)
# ---------------------------------------------------------------------------

PROBE_VERSION = "m01-probes@1.0.0"

_DEPTH_RATIONALE = {
    0: "Openers establish that you can describe your own work without notes.",
    1: "The mechanism question is where a claim you did not build starts to thin out.",
    2: "Trade-off questions separate a decision you made from one you inherited.",
    3: "The what-if is the depth probe: it cannot be answered from memory of the README.",
}


#: How to ask about a claim, by what kind of claim it is.
#:
#: §6.7's ladder is depth 0-3 — what, how, why, what-if — and its worked
#: example is an engineering one. Applied to every bullet regardless, that
#: example's phrasing produces "How did you implement this project?" about a
#: student who coordinated a technical festival, and "walk me through what you
#: built" about someone who won a scholarship. The ladder is right; the nouns
#: were not, and a question that does not fit the bullet reads as the system
#: not having listened - which is exactly what §2.3 says loses Rahul.
#:
#: `{subject}` is the concept the bullet names, or a fallback phrase. Each
#: family supplies the same four depths, so escalation is unchanged.
class ProbeFamily(NamedTuple):
    """One phrasing family: a fallback subject, and a question at each depth."""

    fallback: str
    ladder: dict[int, tuple[str, list[str]]]


_PROBE_FAMILIES: dict[str, ProbeFamily] = {
    "engineering": ProbeFamily(
        "this project",
        {
            0: (
                "Walk me through {subject} — what did you actually build, in your own words?",
                ["scope of the work", "what was yours versus the team's"],
            ),
            1: (
                "How did you implement {subject}? Take me through the approach you chose.",
                ["a concrete mechanism for {subject}", "why this approach over the obvious one"],
            ),
            2: (
                "What was the hardest trade-off in {subject}, and what did you give up?",
                ["a named alternative", "the cost of the choice"],
            ),
            3: (
                "If the input to {subject} grew a hundredfold tomorrow, what breaks first?",
                ["the actual bottleneck", "what they would change", "what they would measure"],
            ),
        },
    ),
    "leadership": ProbeFamily(
        "this",
        {
            0: (
                "What was the situation when you took this on, and what did you own?",
                ["the state they inherited", "which decisions were theirs to make"],
            ),
            1: (
                "How did you split the work across the team, and how did you track it?",
                ["a concrete method", "how they knew whether it was on course"],
            ),
            2: (
                "Tell me about a disagreement inside the team. How did it end?",
                ["a specific disagreement", "what they actually did", "the outcome"],
            ),
            3: (
                "If two people had walked out a week before the deadline, what would you have done?",
                ["what they would drop", "who they would ask", "what they would tell the group"],
            ),
        },
    ),
    "achievement": ProbeFamily(
        "this",
        {
            0: (
                "What was the format, and what were you actually judged on?",
                ["the format", "the criteria", "the field they were up against"],
            ),
            1: (
                "What did you do differently from the people who did not place?",
                ["a specific choice", "why it mattered"],
            ),
            2: (
                "What was the weakest part of your entry, and did the judges find it?",
                ["a real weakness", "self-awareness about it"],
            ),
            3: (
                "If you entered the same thing again next month, what would you change?",
                ["a concrete change", "why that one first"],
            ),
        },
    ),
    "research": ProbeFamily(
        "this work",
        {
            0: (
                "What question were you trying to answer, and why that one?",
                ["the question", "why it was worth asking"],
            ),
            1: (
                "What was your baseline, and how did you decide the comparison was fair?",
                ["a named baseline", "how the comparison was controlled"],
            ),
            2: (
                "What result would have told you the idea was wrong?",
                ["a falsifiable condition", "whether they checked for it"],
            ),
            3: (
                "Someone reruns this on a different dataset and it does not hold. What broke?",
                ["which assumption is load-bearing", "what they would test first"],
            ),
        },
    ),
    "learning": ProbeFamily(
        "this",
        {
            0: (
                "What does {subject} let you do that you could not do before?",
                ["a concrete capability", "where they used it"],
            ),
            1: (
                "Where does {subject} stop being the right tool?",
                ["a real limit", "what they would use instead"],
            ),
            2: (
                "Explain {subject} to someone in first year, in two sentences.",
                ["an accurate explanation", "no borrowed jargon"],
            ),
            3: (
                "What is the part of {subject} you still find confusing?",
                ["an honest gap", "what they have tried in order to close it"],
            ),
        },
    ),
}

#: Claim type to family. `built`, `improved` and `used` keep the engineering
#: phrasing, which is what the ladder was written against.
_FAMILY_FOR: dict[ClaimType, str] = {
    "built": "engineering",
    "improved": "engineering",
    "used": "engineering",
    "led": "leadership",
    "achieved": "achievement",
    "researched": "research",
    "learned": "learning",
}


#: Every verb the classifier knows, flattened. A capitalised run that starts
#: with one of these is a sentence opener ("Built a route planner"), not the
#: name of the thing being claimed.
_ALL_VERBS = frozenset(verb for _, verbs in _CLAIM_VERBS for verb in verbs)

#: Two or more capitalised words in a row: "Crop Disease Detection", "Smart
#: India Hackathon". This is what a project is actually called on a resume, and
#: it is the most specific handle a deterministic reader can get on a bullet.
_PROPER_RUN = re.compile(r"\b[A-Z][\w+#.]*(?:[ -][A-Z][\w+#.]*)+")

#: What follows the verb, up to the point the sentence turns into circumstance.
_OBJECT_END = re.compile(
    r"\b(?:using|with|for|to|that|which|in|on|at|by|from|and|so|through|via|"
    r"achieving|resulting|reducing|increasing|improving)\b|[,;:.()]",
    re.IGNORECASE,
)
_ARTICLE = re.compile(r"^(?:an?|the|my|our|its|their)\s+", re.IGNORECASE)


def subject_of(text: str, fallback: str) -> str:
    """What this bullet is ABOUT, in words taken from the bullet itself.

    ── The bug this exists to fix ──────────────────────────────────────────────

    The subject used to be `concept_labels[0]`, falling back to a family noun
    when nothing resolved. On a resume where the ontology maps little — which
    is every resume while M04 is down, and most of them while it is up — every
    risky claim got the same fallback, and so the same three questions,
    verbatim. Six risky bullets produced eighteen near-identical lines, and the
    one card that HAD a concept ("How did you implement Routing?") proved the
    template was fine and the noun was not.

    Generated output that repeats itself reads as generated. §2.3's whole
    argument is that a question has to look like it came from what the student
    wrote, so the fallback is now taken from the sentence rather than from a
    constant — the project's name if the bullet names one, otherwise what the
    verb acts on.

    Still deterministic, still explainable, and still wrong sometimes: a
    subject read off the wrong noun asks an odd question, which is a far
    cheaper failure than asking the same question six times.
    """
    for match in _PROPER_RUN.finditer(text):
        run = match.group(0)
        if run.split()[0].casefold() in _ALL_VERBS:
            continue
        # An all-caps heading fragment is a layout artefact, not a name.
        if run.isupper() and len(run) > 24:
            continue
        return run

    low = text.casefold()
    for _claim_type, verbs in _CLAIM_VERBS:
        for verb in verbs:
            match = re.search(rf"\b{re.escape(verb)}\b", low)
            if match is None:
                continue
            tail = text[match.end() :].strip()
            stop = _OBJECT_END.search(tail)
            phrase = (tail[: stop.start()] if stop else tail).strip()
            phrase = _ARTICLE.sub("", phrase).strip(" -–—")
            words = phrase.split()
            if not words or len(words) > 4 or not any(w[0].isalpha() for w in words):
                continue
            # "route planner" needs the article back to sit inside "how did you
            # implement ___?"; "Crop Disease Detection" does not.
            return phrase if phrase[0].isupper() else f"the {phrase}"

    return fallback


def probes_for(claim: ResumeClaim, *, concept_labels: list[str]) -> list[ClaimProbe]:
    """One to three questions, at escalating depth (FR-1.10).

    Grounded in the bullet's own nouns, numbers AND verb, so a student can see
    that the question came from what they wrote rather than from a generic
    bank. Depth 0 is only issued for a weak claim — asking someone to restate a
    strong, specific bullet wastes the first question of an interview.
    """
    family = _PROBE_FAMILIES[_FAMILY_FOR.get(claim.claim_type, "engineering")]
    # A resolved concept still wins — it is the thing downstream can test — but
    # the fallback is now the bullet's own subject rather than a constant, so
    # two claims that map to nothing no longer get the same three questions.
    subject = concept_labels[0] if concept_labels else subject_of(claim.text, family.fallback)
    number = claim.quantifiers[0] if claim.quantifiers else None
    out: list[ClaimProbe] = []

    def add(depth: Literal[0, 1, 2, 3], question: str, expects: list[str]) -> None:
        out.append(
            ClaimProbe(
                claim_id=claim.id,
                depth=depth,
                question=question,
                expects=expects,
                rationale=_DEPTH_RATIONALE[depth],
                generated_by=PROBE_VERSION,
            )
        )

    def from_family(depth: Literal[0, 1, 2, 3]) -> None:
        question, expects = family.ladder[depth]
        add(
            depth,
            question.format(subject=subject),
            [item.format(subject=subject) for item in expects],
        )

    if claim.risk_band != "strong":
        from_family(0)

    from_family(1)

    if number is not None:
        # A number the student quoted outranks the family's depth-2 question in
        # every family: it is the one thing on the bullet they are certain to be
        # asked about, and quoting it back is what makes the probe theirs.
        add(
            2,
            f"You quote {number.raw}. How was that measured, and what was it before?",
            ["the measurement method", "the baseline", "what changed to move it"],
        )
    else:
        from_family(2)

    if claim.risk_band == "risky" or claim.specificity >= 0.8:
        from_family(3)

    return out[:3]


# ---------------------------------------------------------------------------
#  Red flags (FR-1.13)
# ---------------------------------------------------------------------------

#: Shared with entities.py — one definition of what a date range is.
_DATE_RANGE = dates.RANGE


#: A leadership or seniority claim. Flagged only when the bullet says nothing
#: about the size of what was led — the claim is not the problem, the absence
#: of anything under it is.
_INFLATED_TITLE = re.compile(
    r"\b(?:lead|led|head(?:ed)?|chief|principal|senior|architect|founder|co-founder|"
    r"director|manager|managed|spearheaded|owner\s+of|in\s+charge\s+of)\b",
    re.IGNORECASE,
)

#: What makes a leadership claim checkable: a number of people, a duration, or
#: a named deliverable.
_TEAM_EVIDENCE = re.compile(
    r"\b(?:team\s+of\s+\d+|\d+\s+(?:people|members?|engineers?|developers?|interns?|"
    r"students?|juniors?)|\d+\s*(?:-|\s)?(?:person|member))\b",
    re.IGNORECASE,
)

#: Words carried by every project bullet regardless of subject. Left in, two
#: unrelated bullets look similar merely for being resume prose.
_PROJECT_STOPWORDS = frozenset(
    """
    a an the and or of for with using to in on at by from built build created create
    developed develop designed design implemented implement made make worked work
    project application app system tool platform website web service model based
    that this it its as into over under across via use used
    """.split()
)


def _shape(text: str) -> set[str]:
    """The content words of a bullet, for comparing one bullet against another."""
    words = re.findall(r"[A-Za-z][A-Za-z+#.]*", text.casefold())
    return {w for w in words if w not in _PROJECT_STOPWORDS and len(w) > 2}


def _duplicate_groups(claims: list[ResumeClaim]) -> list[list[ResumeClaim]]:
    """Claims that describe the same piece of work, grouped (§6.8).

    Two signals, both required, because either alone is noisy: the content
    words overlap heavily (Jaccard), AND the sentences themselves are similar
    as sequences. A resume with four CNN projects trips the first and not the
    second, which is the correct answer — four CNN projects are four projects.

    ── Why this returns GROUPS and not pairs ───────────────────────────────

    It returned pairs, and that was a defect with teeth. Pair output is
    quadratic in the size of a cluster: a document with n near-identical
    bullets produces n(n-1)/2 flags, each carrying two full `SourceSpan`s with
    their verbatim text. Two thousand repeated lines — which is a plausible
    thing for someone to paste, and a trivial thing for someone to paste on
    purpose — produced roughly two million flags and 1.4 GB of JSON, and the
    insert failed with "string or blob too big" after eighty seconds of CPU.

    Grouping makes the output linear in the number of distinct pieces of work,
    which is what a student is actually being told about: "these four bullets
    are the same project", once. The comparison is still bounded on top of
    that, because the grouping pass itself is quadratic in claim count.
    """
    considered = claims[: config.DUPLICATE_MAX_CLAIMS_COMPARED]
    shapes = [(claim, _shape(claim.text)) for claim in considered]

    #: Group index per claim, single-linkage: a claim joins the first group it
    #: matches, so A~B and B~C puts all three together without comparing A to C.
    groups: list[list[int]] = []
    group_of: dict[int, int] = {}

    for index, (claim, shape) in enumerate(shapes):
        if not shape:
            continue
        for other in range(index):
            other_claim, other_shape = shapes[other]
            if not other_shape:
                continue
            union = shape | other_shape
            overlap = len(shape & other_shape) / len(union)
            if overlap < 0.5:
                continue
            ratio = difflib.SequenceMatcher(
                None, claim.text.casefold(), other_claim.text.casefold()
            ).ratio()
            if ratio < config.DUPLICATE_TITLE_SIMILARITY and not (overlap >= 0.75 and ratio >= 0.6):
                continue
            target = group_of.get(other)
            if target is None:
                target = len(groups)
                groups.append([other])
                group_of[other] = target
            groups[target].append(index)
            group_of[index] = target
            break

    return [[considered[i] for i in group] for group in groups]


def find_red_flags(
    text: str,
    claims: list[ResumeClaim],
    artifact_id: uuid.UUID,
    *,
    today: date,
    listed_concepts: list[str] | None = None,
) -> list[RedFlag]:
    """Gaps, chronology conflicts and unbacked superlatives.

    Every explanation is written to be read by the student and none of them
    accuse: a gap is a thing to have an answer ready for, not a finding.
    """
    flags: list[RedFlag] = []

    # --- date ranges: gaps and reversed ranges ---------------------------
    ranges: list[tuple[date, date, int, int]] = []  # (start, end, char_from, char_to)
    for match in _DATE_RANGE.finditer(text):
        start, end = dates.bounds(match, today)
        ranges.append((start, end, match.start(), match.end()))

        if end < start:
            flags.append(
                RedFlag(
                    kind="chronology_conflict",
                    severity="notable",
                    explanation=(
                        f"This date range runs backwards: {match.group(0).strip()}. "
                        "Most likely a typo, but an interviewer reading closely will spot it."
                    ),
                    spans=[
                        SourceSpan(
                            artifact_id=artifact_id,
                            start=match.start(),
                            end=match.end(),
                            text=match.group(0),
                        )
                    ],
                    suggested_answer="Fix the dates before the interview; nothing to explain.",
                )
            )

    ranges.sort(key=lambda r: r[0])
    for (_a_start, a_end, a_from, a_to), (b_start, _b_end, b_from, b_to) in zip(
        ranges, ranges[1:], strict=False
    ):
        months = (b_start.year - a_end.year) * 12 + (b_start.month - a_end.month)
        if months > 6:
            flags.append(
                RedFlag(
                    kind="timeline_gap",
                    severity="info",
                    explanation=(
                        f"There is a {months}-month gap between "
                        f"{a_end.strftime('%b %Y')} and {b_start.strftime('%b %Y')}. "
                        "Gaps are normal. Being unable to account for one is what costs you."
                    ),
                    spans=[
                        SourceSpan(
                            artifact_id=artifact_id,
                            start=a_from,
                            end=a_to,
                            text=text[a_from:a_to],
                        ),
                        SourceSpan(
                            artifact_id=artifact_id,
                            start=b_from,
                            end=b_to,
                            text=text[b_from:b_to],
                        ),
                    ],
                    suggested_answer=(
                        "Have one sentence ready: what you were doing and what you got out of it."
                    ),
                )
            )

    # --- superlatives with nothing behind them ---------------------------
    for claim in claims:
        match = _SUPERLATIVE.search(claim.text)
        if match and not claim.quantifiers:
            flags.append(
                RedFlag(
                    kind="unverifiable_superlative",
                    severity="notable",
                    explanation=(
                        f'"{match.group(0)}" is a claim with no number behind it. '
                        "An interviewer will ask what it means, and the honest answer is "
                        "usually smaller than the word."
                    ),
                    spans=[claim.span],
                    suggested_answer=("Replace the adjective with the measurement, or drop it."),
                )
            )

    # --- the same project claimed twice (EC / §6.8) ----------------------
    #
    # A project in both PROJECTS and EXPERIENCE is normal and honest — it was
    # an internship project. It is worth flagging anyway, because a panel
    # reading two entries counts two pieces of work and asks about both, and
    # the student needs to have decided which framing they are telling.
    for group in _duplicate_groups(claims)[: config.DUPLICATE_MAX_GROUPS]:
        count = len(group)
        flags.append(
            RedFlag(
                kind="duplicate_project",
                severity="info",
                explanation=(
                    f"{count} bullets describe what looks like the same piece of work. "
                    "That is fine if it was — an internship project belongs in both "
                    "places — but decide which one you are going to talk about, "
                    "because you will be asked about each as though they were separate."
                ),
                # The first two are enough to show what was matched; carrying
                # all of them makes a fifty-bullet cluster a fifty-span flag.
                spans=[claim.span for claim in group[:2]],
                suggested_answer=(
                    "Say it once, in the section where it is strongest, and reference "
                    "it from the other."
                ),
            )
        )

    # --- a title the bullet does not support -----------------------------
    for claim in claims:
        match = _INFLATED_TITLE.search(claim.text)
        if not match:
            continue
        if _TEAM_EVIDENCE.search(claim.text) or claim.quantifiers:
            continue
        flags.append(
            RedFlag(
                kind="title_inflation",
                severity="notable",
                explanation=(
                    f'This bullet claims "{match.group(0)}" without saying what you led '
                    "or how many people were involved. An interviewer will ask both, and "
                    "a title with nothing under it is worse than no title."
                ),
                spans=[claim.span],
                suggested_answer=(
                    "Name the size of the thing: how many people, for how long, and "
                    "which decisions were actually yours."
                ),
            )
        )

    # --- a skill claimed nowhere but the skills list ---------------------
    body_concepts = {c for claim in claims for c in claim.subject_concepts}
    listed_only = [c for c in (listed_concepts or []) if c not in body_concepts]
    if listed_only:
        flags.append(
            RedFlag(
                kind="claim_skill_mismatch",
                severity="info",
                explanation=(
                    f"{len(listed_only)} skill(s) appear only in your skills list and in no "
                    "project or experience bullet. A skill with no story attached is the "
                    "easiest thing on a resume to get caught on."
                ),
                suggested_answer=(
                    "Either attach it to something you built, or take it off the list."
                ),
            )
        )

    return flags


# ---------------------------------------------------------------------------
#  The pipeline
# ---------------------------------------------------------------------------


def segment_bullets(body: str, base: int) -> list[tuple[int, str]]:
    """(offset, text) for every bullet in a section body.

    A line classifier, not a character match (§3.2.2). Markered lines start a
    bullet; a more-indented line that follows one continues it (the hanging
    indent of §6.5.1); a bare line breaks the run.

    A continuation is joined with a single space and the bullet SPAN is
    extended to cover it, which means the recorded span still slices out of the
    source verbatim only up to the first newline. So the returned text is the
    joined form and the caller records the span over the ORIGINAL range — see
    `_span_for` — keeping AC-1.1 true for wrapped bullets.
    """
    bullets: list[tuple[int, str]] = []
    offset = 0
    marker_indent: int | None = None

    for line in body.splitlines(keepends=True):
        match = _BULLET_LINE.match(line)
        if match:
            inner = match.group("body")
            bullets.append((base + offset + line.index(inner), inner))
            marker_indent = len(match.group("indent"))
        elif bullets and marker_indent is not None:
            continuation = _CONTINUATION.match(line.rstrip("\r\n"))
            if continuation and len(continuation.group("indent")) > marker_indent:
                start, text = bullets[-1]
                bullets[-1] = (start, f"{text} {continuation.group('body')}")
            elif not line.strip():
                marker_indent = None
        offset += len(line)

    return bullets


def segment_sentences(body: str, base: int) -> list[tuple[int, str]]:
    """EC-1.10 — a resume written in paragraphs still has claims in it.

    Sentence-level fallback, used only when a section has no bullet markers at
    all. Short fragments are dropped: a heading that lost its newline is not a
    claim, and generating a probe for one is how the Claim Map stops being
    trusted.
    """
    out: list[tuple[int, str]] = []
    for block_offset, block in _blocks(body):
        cursor = 0
        for sentence in _SENTENCE_END.split(block):
            index = block.index(sentence, cursor)
            cursor = index + len(sentence)
            stripped = sentence.strip()
            if len(stripped) < _MIN_CLAIM_CHARS:
                continue
            lead = sentence.index(stripped)
            out.append((base + block_offset + index + lead, stripped))
    return out


def _blocks(body: str) -> list[tuple[int, str]]:
    """Non-empty line runs, with their offset into `body`."""
    out: list[tuple[int, str]] = []
    offset = 0
    for line in body.splitlines(keepends=True):
        if line.strip():
            out.append((offset, line.rstrip()))
        offset += len(line)
    return out


def extract_claims(
    text: str,
    resume_id: uuid.UUID,
    sections: list[ResumeSection],
    *,
    concepts_for: Any,
    today: date | None = None,
    geometry: Geometry | None = None,
) -> list[ResumeClaim]:
    """Every bullet in an experience/project/achievement section, as a claim.

    Skills-list lines are not claims. "Python" asserts nothing that can be
    probed; the bullet that says what was built with it does.

    `geometry` is the parsed document when there was one. It turns each span
    into a page and a rectangle, which is what §8.3 click-a-claim-highlight-
    the-PDF needs. Pasted text has none, and every bbox is then `None` rather
    than a plausible-looking zero rectangle on a page that does not exist.
    """
    today = today or datetime.now(UTC).date()
    claim_sections = {"experience", "projects", "achievements", "publications", "unknown"}
    claims: list[ResumeClaim] = []
    document_length = len(text)

    def _span(start: int, body: str) -> SourceSpan:
        # The span covers the ORIGINAL range, so a wrapped bullet whose text was
        # joined with a space still resolves: `verify_spans` compares on
        # collapsed whitespace, the same normalisation ai_core.evidence uses.
        end = min(document_length, start + len(body))
        if text[start:end] != body:
            # A joined continuation. Walk forward over the source until the
            # collapsed forms match, so the recorded range covers every line.
            probe = start + len(body)
            while probe <= document_length and _collapse(text[start:probe]) != _collapse(body):
                probe += 1
            end = min(probe, document_length)
        page, bbox = geometry.geometry_for(start, end) if geometry else (1, None)
        return SourceSpan(
            artifact_id=resume_id, page=page, start=start, end=end, bbox=bbox, text=body
        )

    for section in sections:
        if section.kind not in claim_sections:
            continue

        base = section.span.start
        body = section.span.text
        units = segment_bullets(body, base) or segment_sentences(body, base)

        for index, (start, bullet) in enumerate(units):
            if not _is_readable(bullet):
                continue
            span = _span(start, bullet)
            quantifiers = extract_quantifiers(bullet, start, resume_id)
            concept_labels, concept_ids = concepts_for(bullet)

            scores = score_claim(
                bullet,
                quantifiers=quantifiers,
                concepts=concept_ids,
                has_link=bool(_LINK.search(bullet)),
                prominence=prominence_of(
                    section_kind=section.kind,
                    bullet_index=index,
                    start=start,
                    document_length=document_length,
                ),
                today=today,
            )
            claim = ResumeClaim(
                resume_id=resume_id,
                section_id=section.id,
                span=span,
                text=bullet,
                claim_type=classify(bullet),
                subject_concepts=concept_ids,
                quantifiers=quantifiers,
                risk_band=band(scores["risk_score"]),
                **scores,
            )
            claim.probes = probes_for(claim, concept_labels=concept_labels)
            claims.append(claim)

    return claims


_WHITESPACE = re.compile(r"\s+")


def _collapse(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def verify_spans(text: str, claims: list[ResumeClaim]) -> list[ResumeClaim]:
    """Drop any claim whose span does not resolve (§6.5.4, AC-1.1 [GATE]).

    *"Every returned span must verbatim-match the source text at the given
    offsets. Mismatch → repair by fuzzy-locating the quote; if that fails, drop
    the claim and log. **Never store a claim whose span doesn't resolve.**"*

    Repair first, because a span that is off by the leading whitespace of a
    wrapped line is a good claim with a bad offset, and throwing it away costs
    the student a real bullet. Only an unlocatable quote is dropped.

    Whitespace is collapsed before comparison — the same and only normalisation
    `ai_core.evidence.normalise_quote` permits — because a bullet re-joined
    across a line break is the same words in the same order.
    """
    kept: list[ResumeClaim] = []
    for claim in claims:
        span = claim.span
        if _collapse(text[span.start : span.end]) == _collapse(span.text):
            kept.append(claim)
            continue

        found = text.find(claim.text)
        if found == -1:
            log.warning(
                "M01 dropped a claim whose span did not resolve: [%d:%d]", span.start, span.end
            )
            continue
        claim.span = span.model_copy(update={"start": found, "end": found + len(claim.text)})
        kept.append(claim)
    return kept

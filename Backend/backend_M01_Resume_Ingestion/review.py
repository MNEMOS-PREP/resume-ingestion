"""The resume review: what to fix, line by line, and the document as you fix it.

── What it is (2026-10-04) ──────────────────────────────────────────────────────

A student asked for what paid resume checkers sell — a list of checks, each
line that fails one, a suggested fix they can apply, and their document
updating as they go — without the paywall. Everything here is computed from
what this module already extracts (claims, their scores, red flags, skill
mentions, sections, the contact block), by rule, so every finding can be
traced to the words it is about and argued with.

── What it deliberately is not ─────────────────────────────────────────────────

**There is no overall score.** §2.3 forbids "ATS score: 62" and §15 decision 1
recommends there is never a total on these screens: a single number is the
most memorable thing on a page and the least defensible, and it is the moment
this module becomes one more ATS checker. The review reports COUNTS — "7 of 11
checks passed", "3 lines to fix" — each of which is a list the student can open.

**Fixes never invent facts.** §15 decision 2: a resume the student did not
write is a resume they cannot defend. A suggestion either removes words (a
filler adjective, a leading "I") or leaves a [blank] where only the student
knows the fact — the client will not save a line that still has one. The
model-backed rewrite stays where it was: on request, per claim, restructuring
and never adding (`rewrite.suggest_grounded`).

── The checks, in the order a panel would hit them ─────────────────────────────

  defend    risky        lines a panel asks first and that are hard to defend
            flags        timeline gaps, chronology, title inflation… (§6.8)
            ownership    "we" with no "I": whose work was it?
  impact    numbers      experience/project bullets with no number at all
            verbs        "worked on", "responsible for" as the opening words
  clarity   filler       "robust", "seamless", "various"… quoted back
            pronouns     a bullet that starts with "I"
            length       bullets a reader skims (too long) or that say nothing
  complete  skills_used  skills listed and never used in a bullet
            sections     education, experience or projects, skills
            contact      an email and a phone a recruiter can use
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend_M01_Resume_Ingestion.claims import ResumeClaim
from backend_M01_Resume_Ingestion.rewrite import FILLER, WEAK_OPENER, suggest

Group = Literal["defend", "impact", "clarity", "complete"]

#: A blank only the student can fill: `[the number]`. The client refuses to
#: save a line that still contains one.
BLANK = re.compile(r"\[[^\[\]]+\]")

#: Sections whose bullets are claims of work, where a number is expected.
_WORK_SECTIONS = frozenset({"experience", "projects", "achievements"})

#: Past this many words a bullet is skimmed, not read.
LONG_BULLET_WORDS = 35
#: Under this many it cannot say what was done and what came of it.
SHORT_BULLET_WORDS = 5

_DIGIT = re.compile(r"\d")
_TEAM_WORDS = re.compile(r"\b(?:we|our|us|the team)\b", re.IGNORECASE)
_LEADING_I = re.compile(r"^\s*I\s+(?=\w)")


class ReviewIssue(BaseModel):
    """One line (or one gap) that fails one check."""

    #: Stable across reloads, so an ignored issue stays ignored.
    id: str
    check: str
    claim_id: str | None = None
    #: The section kind it sits in, for "in Projects".
    section: str | None = None
    original: str
    #: Why it matters, in one or two sentences that quote the student's words.
    problem: str
    #: The line as it could read. Words removed, or [blanks] for facts only the
    #: student has. None when there is no honest text fix — the student edits.
    suggestion: str | None = None
    blanks: int = 0
    #: For a red flag: what to say if a panel asks.
    answer: str | None = None
    spans: list[dict[str, Any]] = Field(default_factory=list)


class ReviewCheck(BaseModel):
    id: str
    title: str
    group: Group
    #: What it looks for, in one line.
    looks_for: str
    passed: bool
    #: How many things it looked at — bullets, sections, skills.
    looked_at: int
    issues: list[ReviewIssue] = Field(default_factory=list)


class DocumentSegment(BaseModel):
    """A run of the document. A claim's run carries its id and, once the
    student has edited it, the edited words."""

    text: str
    claim_id: str | None = None
    edited: bool = False


class ResumeReview(BaseModel):
    resume_id: str
    filename: str | None = None
    #: Whether the original pages can be shown (a PDF whose file is stored).
    has_original: bool = False
    checks: list[ReviewCheck]
    passed: int
    total: int
    open_issues: int
    #: Risk bands, as the Claim Map counts them.
    bands: dict[str, int]
    edited: int
    document: list[DocumentSegment]


# ---------------------------------------------------------------------------
#  Text fixes that only remove words
# ---------------------------------------------------------------------------


def takes_an(word: str) -> bool:
    """Whether 'an' goes before this word — by sound, not spelling.

    Acronyms are read letter by letter ("an API", "an SQL query", "a GPU");
    "uni-", "use-" and "one" start with a consonant sound ("a university"), and
    a silent h does not ("an hour").
    """
    if len(word) > 1 and word.isupper():
        return word[0] in "AEFHILMNORSX"
    lower = word.lower()
    if lower.startswith(("uni", "use", "usa", "usu", "uti", "eu", "one", "once")):
        return False
    if lower.startswith(("hour", "honest", "honor", "honour", "heir")):
        return True
    return lower[:1] in {"a", "e", "i", "o", "u"}


#: Where a removed word was, until the article before it has been reconsidered.
_GONE = "\x00"


def _tidy(text: str) -> str:
    out = re.sub(r"\s+([,.;:])", r"\1", text)  # "a , b" → "a, b"
    out = re.sub(r",\s*(?=[,.;:])", "", out)  # ", ," / ",." → one mark
    out = re.sub(r"\b(a|an|the|A|An|The)\s*,\s*", r"\1 ", out)  # "a, platform" → "a platform"
    out = re.sub(r"^\s*[,;:]\s*", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out[:1].upper() + out[1:] if out else out


def without_filler(text: str) -> str:
    """The bullet with every filler adjective removed, punctuation tidied.

    Only an article that stood before a removed word is reconsidered ("a
    robust API" → "an API"); every other "a" and "an" in the line is the
    student's, and is left exactly as written.
    """
    marked = FILLER.sub(_GONE, text)

    def reconsider(match: re.Match[str]) -> str:
        article, word = match.group(1), match.group(3)
        right = "an" if takes_an(word) else "a"
        if article[0].isupper():
            right = right.capitalize()
        return f"{right} {word}"

    marked = re.sub(rf"\b([Aa]n?)((?:[\s,]*{_GONE})+[\s,]*)(\w+)", reconsider, marked)
    return _tidy(marked.replace(_GONE, ""))


def without_leading_i(text: str) -> str:
    """'I built a parser' → 'Built a parser'."""
    out = _LEADING_I.sub("", text, count=1)
    return out[:1].upper() + out[1:] if out else out


def with_strong_opener(text: str) -> str | None:
    """'Worked on the payments service' → '[What you did] the payments service'.

    A gerund left behind ('Responsible for writing tests') goes with it, since
    the blank replaces the whole action.
    """
    match = WEAK_OPENER.match(text)
    if not match:
        return None
    rest = text[match.end() :].lstrip()
    first, _, tail = rest.partition(" ")
    if first.lower().endswith("ing") and len(first) > 4:
        rest = tail
    return f"[What you did — e.g. Built, Led, Cut] {rest}".rstrip()


#: An achievement (a patent, a paper, a rank) is checked by its evidence, not by a
#: before-and-after: "from 420 ms to 95 ms" means nothing appended to "patent filed".
EVIDENCE_BLANK = "[the evidence — application number, rank, or where it's published]"

#: Past this many words a line has no room for three blanks; it gets the one
#: that matters most (the result) and the length check says the rest.
_ROOM_FOR_BLANKS = 28


def with_result_blank(text: str, claim_type: str | None = None) -> str:
    """The student's own sentence, with a place for the number it is missing."""
    base = text.rstrip().rstrip(".")
    if claim_type == "achieved":
        return f"{base} — {EVIDENCE_BLANK}."
    return f"{base}, [the result, with a number — e.g. from 420 ms to 95 ms, or 2,000 users]."


def with_missing_slots(claim: dict[str, Any]) -> str:
    """The student's own sentence, with a blank for each STAR part it lacks.

    `rewrite.suggest` already knows which parts are present (action, task,
    result, scale). Its skeleton throws the student's words away — "Built
    [what exactly] for the thing you built" about a line that named its stack
    — so the review keeps the sentence and asks only for what is missing.
    """
    if claim.get("claim_type") == "achieved":
        return with_result_blank(claim["text"], "achieved")
    slots = {s.slot: s.present for s in suggest(ResumeClaim.model_validate(claim)).slots}
    text = claim["text"]
    if not slots.get("action", True):
        text = with_strong_opener(text) or text
    base = text.rstrip().rstrip(".")
    roomy = len(base.split()) <= _ROOM_FOR_BLANKS
    if roomy and not slots.get("task", True):
        base += " — [why: the problem it solved]"
    if not slots.get("result", True):
        base += ", [what measurably changed — with a number]"
    if roomy and not slots.get("situation", True):
        base += " across [the scale — data size, users, or team]"
    return base + "."


def skill_name(surface: str) -> str:
    """'Programming: Python' → 'Python'. A list's category label is not the skill."""
    return surface.rsplit(":", 1)[-1].strip()


def named_in(name: str, text: str) -> bool:
    """Whether `name` appears in `text` as a word — 'C' must not match 'CNN'."""
    return re.search(rf"(?<![\w+#.]){re.escape(name)}(?![\w+#])", text, re.IGNORECASE) is not None


def blanks_in(text: str | None) -> int:
    return len(BLANK.findall(text or ""))


# ---------------------------------------------------------------------------
#  The review
# ---------------------------------------------------------------------------


def _risky_reason(claim: dict[str, Any]) -> str:
    parts = {
        "specificity": "it doesn't say exactly what you built or how",
        "verifiability": "nothing in it is measured, so a panel can't check that it worked",
        "ownership_clarity": "it doesn't say which part was yours",
    }
    weakest = min(parts, key=lambda key: claim.get(key, 1.0))
    return parts[weakest]


def _issue(check: str, claim: dict[str, Any], section: str | None, **fields: Any) -> ReviewIssue:
    suggestion = fields.pop("suggestion", None)
    return ReviewIssue(
        id=f"{check}:{claim['id']}",
        check=check,
        claim_id=str(claim["id"]),
        section=section,
        original=claim["text"],
        suggestion=suggestion,
        blanks=blanks_in(suggestion),
        spans=[claim["span"]] if claim.get("span") else [],
        **fields,
    )


def build_review(
    *,
    resume_id: str,
    filename: str | None,
    text: str,
    sections: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    red_flags: list[dict[str, Any]],
    skill_mentions: list[dict[str, Any]],
    has_original: bool,
    contact: dict[str, bool],
) -> ResumeReview:
    """Every check over one resume, and the document with the student's edits in it."""
    kind_of = {str(s["id"]): s["kind"] for s in sections}

    def section_of(claim: dict[str, Any]) -> str | None:
        return kind_of.get(str(claim.get("section_id")))

    # Most visible first, as the Claim Map orders them (§6.6).
    ordered = sorted(
        claims, key=lambda c: c.get("prominence", 0) * c.get("risk_score", 0), reverse=True
    )
    work = [c for c in ordered if section_of(c) in _WORK_SECTIONS]

    checks: list[ReviewCheck] = []

    # ── defend ──────────────────────────────────────────────────────────────
    risky = []
    for claim in ordered:
        if claim.get("risk_band") != "risky":
            continue
        risky.append(
            _issue(
                "risky",
                claim,
                section_of(claim),
                problem=(
                    "This is a line a panel will ask about early, and as written it is hard "
                    f"to defend: {_risky_reason(claim)}."
                ),
                suggestion=with_missing_slots(claim),
            )
        )
    checks.append(
        ReviewCheck(
            id="risky",
            title="Lines you'd struggle to defend",
            group="defend",
            looks_for="Prominent claims that are vague, uncheckable or unclear about who did the work.",
            passed=not risky,
            looked_at=len(claims),
            issues=risky,
        )
    )

    flags = []
    for index, flag in enumerate(red_flags):
        if flag.get("kind") == "claim_skill_mismatch":
            continue  # the skills_used check lists these one by one
        spans = flag.get("spans") or []
        flags.append(
            ReviewIssue(
                id=f"flags:{index}:{flag.get('kind')}",
                check="flags",
                original=" … ".join(s.get("text", "") for s in spans) or flag.get("kind", ""),
                problem=flag.get("explanation", ""),
                answer=flag.get("suggested_answer"),
                spans=spans,
            )
        )
    checks.append(
        ReviewCheck(
            id="flags",
            title="Things a panel will notice",
            group="defend",
            looks_for="Timeline gaps, dates that disagree, inflated titles, repeated projects.",
            passed=not flags,
            looked_at=len(red_flags),
            issues=flags,
        )
    )

    ownership = [
        _issue(
            "ownership",
            claim,
            section_of(claim),
            problem=(
                "It says what the team did. A panel's first question will be what YOU did — "
                "name your part, e.g. 'Built the ranking model in a 4-person team'."
            ),
        )
        for claim in work
        if _TEAM_WORDS.search(claim["text"]) and claim.get("ownership_clarity", 1.0) < 0.6
    ]
    checks.append(
        ReviewCheck(
            id="ownership",
            title="Whose work was it?",
            group="defend",
            looks_for="Bullets that say 'we' or 'the team' and never say what you did.",
            passed=not ownership,
            looked_at=len(work),
            issues=ownership,
        )
    )

    # ── impact ──────────────────────────────────────────────────────────────
    numbers = [
        _issue(
            "numbers",
            claim,
            section_of(claim),
            problem=(
                "There is no number in it, so there is nothing to show it worked. A result "
                "with a number is what a panel remembers — and the first thing they test."
            ),
            suggestion=with_result_blank(claim["text"], claim.get("claim_type")),
        )
        for claim in work
        # A count ("4 endpoints", "23 agent nodes") is a number; the line is
        # flagged only when it has none at all, which is what the card says.
        if not _DIGIT.search(claim["text"])
    ]
    checks.append(
        ReviewCheck(
            id="numbers",
            title="Bullets with no number",
            group="impact",
            looks_for="Experience and project bullets with no measured result.",
            passed=not numbers,
            looked_at=len(work),
            issues=numbers,
        )
    )

    verbs = []
    for claim in work:
        fixed = with_strong_opener(claim["text"])
        if fixed is None:
            continue
        opener = WEAK_OPENER.match(claim["text"])
        verbs.append(
            _issue(
                "verbs",
                claim,
                section_of(claim),
                problem=(
                    f'It opens with "{opener.group(0).strip() if opener else ""}", which says '
                    "you were near the work, not what you did. Start with the action."
                ),
                suggestion=fixed,
            )
        )
    checks.append(
        ReviewCheck(
            id="verbs",
            title="Weak opening words",
            group="impact",
            looks_for='Bullets that open with "worked on", "responsible for", "helped with".',
            passed=not verbs,
            looked_at=len(work),
            issues=verbs,
        )
    )

    # ── clarity ─────────────────────────────────────────────────────────────
    filler = []
    for claim in ordered:
        found = sorted({m.group(0) for m in FILLER.finditer(claim["text"])}, key=str.casefold)
        if not found:
            continue
        quoted = ", ".join(f'"{word}"' for word in found)
        filler.append(
            _issue(
                "filler",
                claim,
                section_of(claim),
                problem=(
                    f"{quoted} {'says' if len(found) == 1 else 'say'} nothing a panel can check. "
                    "A number or the name of the technique does that job better."
                ),
                suggestion=without_filler(claim["text"]),
            )
        )
    checks.append(
        ReviewCheck(
            id="filler",
            title="Filler words",
            group="clarity",
            looks_for='Adjectives that sound good and prove nothing: "robust", "seamless", "various".',
            passed=not filler,
            looked_at=len(claims),
            issues=filler,
        )
    )

    pronouns = [
        _issue(
            "pronouns",
            claim,
            section_of(claim),
            problem="Resume bullets drop the 'I' — the line is already about you.",
            suggestion=without_leading_i(claim["text"]),
        )
        for claim in ordered
        if _LEADING_I.match(claim["text"])
    ]
    checks.append(
        ReviewCheck(
            id="pronouns",
            title="Bullets that start with 'I'",
            group="clarity",
            looks_for="First-person pronouns at the start of a bullet.",
            passed=not pronouns,
            looked_at=len(claims),
            issues=pronouns,
        )
    )

    length = []
    for claim in work:
        words = len(claim["text"].split())
        if words > LONG_BULLET_WORDS:
            problem = (
                f"At {words} words it gets skimmed, not read. Lead with the result and cut "
                "the rest to one line — or split it into two bullets."
            )
        elif words < SHORT_BULLET_WORDS:
            problem = "It's too short to say what you did and what came of it."
        else:
            continue
        length.append(_issue("length", claim, section_of(claim), problem=problem))
    checks.append(
        ReviewCheck(
            id="length",
            title="Bullets that run long — or say too little",
            group="clarity",
            looks_for=f"Bullets over {LONG_BULLET_WORDS} words or under {SHORT_BULLET_WORDS}.",
            passed=not length,
            looked_at=len(work),
            issues=length,
        )
    )

    # ── complete ────────────────────────────────────────────────────────────
    # A skill is "used" when any experience or project line NAMES it. The
    # mention extractor only recognises some names in prose, so trusting its
    # contexts alone called Python unused on a resume full of Django and
    # FastAPI work. The label a list puts in front ("Programming: Python") is
    # not part of the name.
    work_text = " ".join(c["text"] for c in work)
    by_skill: dict[str, list[dict[str, Any]]] = {}
    for mention in skill_mentions:
        name = skill_name(str(mention.get("surface", "")))
        if name:
            by_skill.setdefault(name.casefold(), []).append({**mention, "surface": name})
    unused = [
        mentions[0]
        for mentions in by_skill.values()
        if all(m.get("context") == "skills_list" for m in mentions)
        and not named_in(mentions[0]["surface"], work_text)
    ]
    # One card, not one per skill: a long skills list produced twenty cards that
    # buried every other finding, and the fix is one decision — work the ones
    # you can into a project line, and be ready to answer for the rest.
    names = [str(m.get("surface", "")) for m in unused]
    skills_used = (
        [
            ReviewIssue(
                id="skills_used:all",
                check="skills_used",
                section="skills",
                original=", ".join(names),
                problem=(
                    f"{len(names)} skill{'s' if len(names) != 1 else ''} appear only in your "
                    f'skills list. Expect "Where did you use {names[0]}?" — put the ones you '
                    "really used into a project or job line, and be ready to answer for the rest."
                ),
                spans=[m["span"] for m in unused if m.get("span")],
            )
        ]
        if names
        else []
    )
    checks.append(
        ReviewCheck(
            id="skills_used",
            title="Skills you list but never use",
            group="complete",
            looks_for="Skills that appear only in the skills list, in no project or job.",
            passed=not skills_used,
            looked_at=len(by_skill),
            issues=skills_used,
        )
    )

    kinds = {s["kind"] for s in sections}
    missing_sections = []
    if "education" not in kinds:
        missing_sections.append(("education", "No education section was found."))
    if not kinds & {"experience", "projects"}:
        missing_sections.append(
            (
                "work",
                "No experience or projects section was found — the part a panel asks about most.",
            )
        )
    if "skills" not in kinds:
        missing_sections.append(("skills", "No skills section was found."))
    checks.append(
        ReviewCheck(
            id="sections",
            title="The sections a panel looks for",
            group="complete",
            looks_for="Education, experience or projects, and skills.",
            passed=not missing_sections,
            looked_at=3,
            issues=[
                ReviewIssue(
                    id=f"sections:{kind}",
                    check="sections",
                    original="",
                    problem=problem
                    + " If it's there, the heading may be unusual — correct it on the read-back.",
                )
                for kind, problem in missing_sections
            ],
        )
    )

    contact_missing = [
        (what, label)
        for what, label in (("email", "an email address"), ("phone", "a phone number"))
        if not contact.get(what)
    ]
    checks.append(
        ReviewCheck(
            id="contact",
            title="Contact details",
            group="complete",
            looks_for="An email and a phone number a recruiter can use.",
            passed=not contact_missing,
            looked_at=2,
            issues=[
                ReviewIssue(
                    id=f"contact:{what}",
                    check="contact",
                    section="contact",
                    original="",
                    problem=f"We couldn't find {label} — a recruiter who wants you can't reach you.",
                )
                for what, label in contact_missing
            ],
        )
    )

    bands = {"strong": 0, "vague": 0, "risky": 0}
    for claim in claims:
        bands[claim.get("risk_band", "vague")] = bands.get(claim.get("risk_band", "vague"), 0) + 1

    return ResumeReview(
        resume_id=resume_id,
        filename=filename,
        has_original=has_original,
        checks=checks,
        passed=sum(1 for c in checks if c.passed),
        total=len(checks),
        open_issues=sum(len(c.issues) for c in checks),
        bands=bands,
        edited=sum(1 for c in claims if c.get("user_edited")),
        document=document_segments(text, claims),
    )


def document_segments(text: str, claims: list[dict[str, Any]]) -> list[DocumentSegment]:
    """The document in order, each claim's run marked and, once edited, replaced.

    Spans index the original text, and `redacted_text` is the same length
    character for character, so slicing it is safe and keeps the contact block
    masked. Overlapping spans (which a parser should not produce) are skipped
    rather than allowed to duplicate text.
    """
    runs = sorted(
        (c for c in claims if c.get("span")),
        key=lambda c: (c["span"]["start"], c["span"]["end"]),
    )
    out: list[DocumentSegment] = []
    at = 0
    for claim in runs:
        start, end = claim["span"]["start"], claim["span"]["end"]
        if start < at or end > len(text) or start >= end:
            continue
        if start > at:
            out.append(DocumentSegment(text=text[at:start]))
        edited = bool(claim.get("user_edited"))
        out.append(
            DocumentSegment(
                text=claim["text"] if edited else text[start:end],
                claim_id=str(claim["id"]),
                edited=edited,
            )
        )
        at = end
    if at < len(text):
        out.append(DocumentSegment(text=text[at:]))
    return out

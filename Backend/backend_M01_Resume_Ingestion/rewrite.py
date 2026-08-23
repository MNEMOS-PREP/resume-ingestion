"""STAR rewrite suggestions for weak claims (FR-1.19).

── Two constraints from the spec, and they pull against each other ────────────

FR-1.19: *"Generate an auto-STAR rewrite suggestion for weak claims, shown only
on request."*

§15 Open decision 2: *"Auto-apply STAR rewrites? Recommendation: **no** —
suggest only. A resume the student did not write is a resume they cannot
defend, which is the exact failure this module exists to prevent."*

So this produces a suggestion and never a replacement. It is reached only by an
explicit `POST .../rewrite`, nothing stores its output on the claim, and the
response says in the student facing text what is missing rather than handing
over a finished sentence to paste. The most useful thing a rewrite can do here
is show the SHAPE of a defensible bullet and name the four facts only the
student has.

── Why it is a template rather than a model call ──────────────────────────────

A model would write a better sentence. It would also invent the dataset size,
because that is what fills a template slot when the fact is absent, and a
student who pastes an invented number into their resume walks into exactly the
interview this module exists to prevent. A slot the student must fill is
strictly better than a slot a model filled plausibly.

When the §6.5 model pass lands, the right shape for it is to propose PHRASING
for facts the student has supplied — never to supply the facts.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from backend_M01_Resume_Ingestion.claims import ResumeClaim

#: What a defensible bullet has, in the order a reader wants it. Each entry is
#: (slot, question the student answers, how we detect it is already there).
_STAR_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("action", "What did you actually build or change?", "verb"),
    ("task", "What problem made it necessary?", "context"),
    ("result", "What measurably changed?", "quantifier"),
    ("situation", "How big was it — data, users, team, duration?", "scope"),
)

_SCOPE = re.compile(
    r"\b\d[\d,.]*\s*(?:k|m|gb|mb|tb|users?|records?|rows?|images?|samples?|nodes?|"
    r"requests?|queries|students?|people|members?|weeks?|months?)\b|"
    r"\bteam\s+of\s+\d+|\bdataset\s+of\b",
    re.IGNORECASE,
)
_CONTEXT = re.compile(
    r"\b(?:because|since|to\s+(?:reduce|cut|improve|support|handle|enable)|"
    r"which\s+(?:let|allowed|meant)|so\s+that|after|when|for\s+a\b)\b",
    re.IGNORECASE,
)
_WEAK_VERB = re.compile(
    r"^\s*(?:worked\s+on|helped\s+with|was\s+involved\s+in|participated\s+in|"
    r"assisted\s+(?:with|in)|responsible\s+for|part\s+of)\b",
    re.IGNORECASE,
)

#: The adjectives that read as filler to an interviewer. Named individually so
#: the advice can quote the student word back at them (§2.3 microcopy: show the
#: consequence, not a label).
_FILLER = re.compile(
    r"\b(?:world[- ]class|cutting[- ]edge|state[- ]of[- ]the[- ]art|seamless|robust|"
    r"scalable|revolutionary|innovative|efficient|user[- ]friendly|various|several|"
    r"multiple|successfully)\b",
    re.IGNORECASE,
)


class RewriteSlot(BaseModel):
    """One thing a defensible bullet needs, and whether this one has it."""

    slot: str
    present: bool
    prompt: str
    #: The words in the bullet that satisfy it, when it is satisfied. Evidence
    #: for the tick, so a student can disagree with it.
    evidence: str | None = None


class RewriteSuggestion(BaseModel):
    """A shape to write into, never a sentence to paste.

    `suggestion` is a skeleton with the student facts left as bracketed blanks.
    That is on purpose: a filled-in sentence is a sentence they did not write.
    """

    claim_id: str
    original: str
    suggestion: str
    slots: list[RewriteSlot] = Field(default_factory=list)
    #: The single change with the most effect, stated as an action.
    first_fix: str
    #: Filler adjectives found, quoted back.
    drop_words: list[str] = Field(default_factory=list)
    #: Restated every time, because this is the screen where a student is most
    #: tempted to paste something they cannot defend.
    caveat: str = (
        "This is a shape, not a sentence to copy. Fill the brackets with your own "
        "numbers — a bullet you did not write is a bullet you cannot defend, which "
        "is the exact thing this module is trying to save you from."
    )


def _has(claim: ResumeClaim, detector: str) -> tuple[bool, str | None]:
    text = claim.text
    if detector == "quantifier":
        return bool(claim.quantifiers), claim.quantifiers[0].raw if claim.quantifiers else None
    if detector == "scope":
        match = _SCOPE.search(text)
        return bool(match), match.group(0) if match else None
    if detector == "context":
        match = _CONTEXT.search(text)
        return bool(match), match.group(0) if match else None
    # "verb": a strong one. "Worked on" is grammatically a verb and tells an
    # interviewer nothing about what the student did.
    weak = _WEAK_VERB.match(text)
    if weak:
        return False, weak.group(0).strip()
    return True, text.split()[0] if text.split() else None


def suggest(claim: ResumeClaim, *, concept_labels: list[str] | None = None) -> RewriteSuggestion:
    """A STAR skeleton for one claim, plus what is missing and what to fix first."""
    subject = (concept_labels or [None])[0] or "the thing you built"

    slots = []
    for slot, prompt, detector in _STAR_SLOTS:
        present, evidence = _has(claim, detector)
        slots.append(RewriteSlot(slot=slot, present=present, prompt=prompt, evidence=evidence))

    missing = [s for s in slots if not s.present]
    drop = sorted({m.group(0) for m in _FILLER.finditer(claim.text)}, key=str.casefold)

    action_slot = next(s for s in slots if s.slot == "action")
    if not action_slot.present:
        first_fix = (
            f'Replace "{action_slot.evidence}" with what you personally did. '
            "It is the first thing on the line and it currently says nothing."
        )
    elif not any(s.slot == "result" and s.present for s in slots):
        first_fix = (
            "Add the number. A claim with no measurement is the first thing a panel "
            "attacks, and you are the only person who has it."
        )
    elif drop:
        first_fix = (
            f'Drop "{drop[0]}" and put the measurement in its place — the adjective is '
            "doing the work a number should be doing."
        )
    elif missing:
        first_fix = missing[0].prompt
    else:
        first_fix = (
            "Nothing structural is missing. Make sure you can say out loud how each "
            "number was measured."
        )

    verb = claim.text.split()[0] if claim.text.split() else "Built"
    if not action_slot.present:
        verb = "Built"

    suggestion = (
        f"{verb} [what exactly] for {subject} using [the approach you chose], "
        f"[which problem it solved], improving [metric] from [before] to [after] "
        f"across [scale — data size, users, or duration]."
    )

    return RewriteSuggestion(
        claim_id=str(claim.id),
        original=claim.text,
        suggestion=suggestion,
        slots=slots,
        first_fix=first_fix,
        drop_words=drop,
    )

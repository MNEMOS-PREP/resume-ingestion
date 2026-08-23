"""Surface forms: what the document actually says, before anything resolves it.

── The bug this file exists to fix ─────────────────────────────────────────────

The previous extraction ran the wrong way round. It walked M04's 120 concepts
and regex-matched each concept's name and aliases against the document, which
means it could only ever return things that were already in the ontology. Two
consequences, both bad, both measured before this was written:

  1. Anything the student wrote that is not an ontology concept was INVISIBLE.
     The ontology holds interview concepts - binary search, normalisation,
     asking clarifying questions - not technologies. A SKILLS line reading
     "Python, Java, C++, React, Node.js, Docker, Kubernetes, AWS, TensorFlow,
     PyTorch, PostgreSQL, MongoDB, Git, Linux" produced `parsed_skills: []`,
     byte-identical to submitting an empty string.

  2. `unresolved_skills` was structurally unreachable. Labels only entered the
     loop by coming FROM M04, and were then handed back to M04 to resolve, so
     they resolved by construction. The module's stated promise - "skills the
     ontology cannot map are kept rather than dropped" - could never fire,
     because nothing was ever detected to keep. The frontend has always had a
     hatched group ready to render those. It has never had one to render.

So extraction now reads the document first and resolves second, which is the
order the specification describes and the only order in which "we could not
map this" is a thing the module is able to say.

── Ambiguity, and why single words are treated differently ─────────────────────

Scanning prose for ontology aliases is still useful - a project bullet saying
"using dynamic programming" is real evidence - but 25 of the ontology's aliases
are also ordinary English words. Measured against the live ontology, the old
scan produced:

    "Full stack developer. Class of 2026. Worked within the scope of a team."
        -> Classes and Objects, Functions and Scope, Stacks

    "A solid communicator who avoids guessing."
        -> SOLID Principles, Handling What You Don't Know

Those are not near-misses; they are requirements invented out of adjectives,
and downstream they would become interview questions. The rule here is
structural rather than a hand-maintained blocklist that drifts as the ontology
grows: a MULTI-WORD alias may match anywhere, because "dynamic programming" in
running text means what it says, while a SINGLE-WORD alias that is also an
everyday English word may only be matched where the document is enumerating -
inside a skills or requirements list, where "stack" is a claim and not an
adjective.
"""

from __future__ import annotations

import re
from typing import Any

from ai_core.concepts import normalise_alias

from backend_M01_Resume_Ingestion import headings
from backend_M01_Resume_Ingestion.normalise import key as skill_key

#: Longer than this and it is a sentence, not a skill. Five words admits
#: "object oriented programming in java" and rejects a project bullet.
MAX_WORDS = 5

#: Headings that introduce an enumeration. The list is deliberately about the
#: SHAPE of the document rather than about any one resume template - every one
#: of these is a word that means "what follows is a list".
#:
#: It lives in `headings.py` and is shared with the section segmenter. It used
#: to be a private copy here, and the two drifted: "COMPUTER PROFICIENCY",
#: "AREAS OF INTEREST" and "RELEVANT COURSEWORK" were in neither, and adding
#: them to only one would have produced the subtler half of the bug - the
#: section labelled correctly and every skill under it invisible, because
#: nothing told this file that a list followed.
_HEADINGS: tuple[str, ...] = tuple(sorted(headings.ENUMERATING, key=lambda h: -len(h)))

#: A heading is the whole line ("SKILLS"), or a label with an explicit
#: separator ("Required: Python, SQL"). Without the separator requirement,
#: "Preferred candidates will have a degree" parses as a list of one skill
#: called "candidates will have a degree".
#:
#: Longest-first alternation, because Python's `|` is first-match-wins: with
#: "skills" ahead of "technical skills", `Technical Skills` matched the shorter
#: branch and the line failed the anchor.
_HEADING_RE = re.compile(
    r"^\s*(?:[-*•·]\s*)?(" + "|".join(re.escape(h) for h in _HEADINGS) + r")"
    r"\s*(?:[:–\-]\s*(.*))?\s*$",
    re.IGNORECASE,
)

#: Commas, semicolons, pipes and bullets separate list items. NOT the forward
#: slash: "CI/CD" and "TCP/IP" are single names far more often than
#: "React/Angular" is two, and a wrong split is a fabricated skill.
#: A sentence boundary ends a list item too - "SQL and data structures. Docker
#: is a plus" is two requirements. Matched as a period FOLLOWED BY SPACE, so
#: "Node.js", "B.Tech" and ".NET" survive intact.
_DELIMITERS = re.compile(r"[,;|•·]|\.\s+")

#: "strong Python" is a claim about Python. Strip the adverbial run-up so the
#: label that reaches the resolver is the thing being claimed.
_LEADING_NOISE = re.compile(
    r"^(?:and|or|either|both|any\s+of|one\s+of|at\s+least|with|in|using|strong|"
    r"solid|good|excellent|deep|basic|advanced|"
    r"working|solid\s+grasp\s+of|hands[-\s]?on|proficiency\s+(?:in|with)|"
    r"proficient\s+(?:in|with)|experience\s+(?:with|in|of)|familiarity\s+with|"
    r"knowledge\s+of|understanding\s+of|exposure\s+to|expertise\s+in|"
    r"comfortable\s+with|fluent\s+in|grasp\s+of)\s+",
    re.IGNORECASE,
)

_TRAILING_NOISE = re.compile(
    r"\s*(?:\((?:optional|preferred|a\s+plus|nice\s+to\s+have|good\s+to\s+have)\)|"
    r"is\s+a\s+plus|a\s+plus|is\s+required|required|preferred|optional|"
    r"is\s+a\s+must|a\s+must|etc\.?|and\s+more|or\s+similar|or\s+equivalent)\s*$",
    re.IGNORECASE,
)

#: Leading bullet glyphs and trailing punctuation, stripped.
#:
#: The leading dot is conditional: `.NET` keeps it, `. NET` does not. A dot
#: bound directly to a word is part of the name, and handing the student back
#: "NET" when they wrote ".NET" is the read-back contradicting their own
#: document — the failure this module cares most about. The golden set does not
#: catch this on its own, because `normalise_alias` folds the dot away and the
#: two forms compare equal; only the surface string differs, and the surface
#: string is what they see.
_PUNCT_EDGES = re.compile(r"^(?:[\s\-–•·:;]|\.(?![A-Za-z0-9]))+|[\s.:;,]+$")

#: Eligibility, not skill. "Must have 2+ years" and "B.Tech with 7.0 CGPA" are
#: real requirements and they belong in a structured eligibility field - which
#: is a separate, unbuilt FR. Filing them under skills would put a number the
#: ontology can never resolve into the "we could not map this" list forever.
_ELIGIBILITY = re.compile(
    r"\b\d+\s*\+?\s*(?:years?|yrs?|months?)\b|\bcgpa\b|\bb\.?\s?tech\b|"
    r"\bdegree\b|\bmust\s+have\b|\bminimum\b|\bgraduat\w*\b|\bbatch\s+of\b",
    re.IGNORECASE,
)

#: Fragments that are never a skill however they are punctuated.
_NOISE_FORMS = frozenset(
    {"", "etc", "and", "or", "others", "more", "n a", "na", "tbd", "various", "any"}
)

#: Ontology aliases that are also ordinary English. A single-word alias in this
#: set is only trusted inside an enumeration, never in running prose. Derived
#: from the live 120-concept ontology and kept a little wider than today's
#: collisions, so a new alias does not silently start matching adjectives.
_COMMON_ENGLISH = frozenset(
    """
    solid class classes scope stack stacks interface interfaces grid certificate
    guessing pace precision security functions keys memory state search sort merge
    views tables lists sets processes joins extends array arrays heap heaps
    structuring threads tuning exceptions tries pointers index indexes scheduling
    """.split()
)


def prose_safe_alias(alias: str) -> bool:
    """May this alias be matched in running prose, or only inside a list?

    Multi-word aliases carry their own disambiguation. Single words do not, and
    the everyday ones are how "a solid communicator" became a SOLID Principles
    requirement.
    """
    normalised = normalise_alias(alias)
    if not normalised:
        return False
    if " " in normalised:
        return True
    return normalised not in _COMMON_ENGLISH


def _clean(fragment: str) -> str:
    """One raw list item to the label a resolver should be asked about."""
    text = _PUNCT_EDGES.sub("", fragment)
    # Repeat: "strong hands-on experience with Python" peels one layer per pass.
    for pattern in (_LEADING_NOISE, _TRAILING_NOISE):
        while True:
            stripped = pattern.sub("", text).strip()
            if stripped == text:
                break
            text = stripped
    return _PUNCT_EDGES.sub("", text).strip()


def _acceptable(label: str) -> bool:
    if normalise_alias(label) in _NOISE_FORMS:
        return False
    if _ELIGIBILITY.search(label):
        return False
    words = label.split()
    if not words or len(words) > MAX_WORDS:
        return False
    # A fragment with no letters at all is a date, a percentage or a phone
    # number that survived the split.
    return any(ch.isalpha() for ch in label)


def _split_conjunctions(label: str) -> list[str]:
    """ "SQL and data structures" -> the whole, plus each side.

    Both are kept. Which one survives is decided after resolution, by the
    caller, because "Transactions and ACID" is a real concept name and
    "SQL and data structures" is two - and only the resolver knows which.
    """
    parts = re.split(r"\s+(?:and|or)\s+", label, flags=re.IGNORECASE)
    if len(parts) < 2:
        return []
    return [p.strip() for p in parts if p.strip() and len(p.split()) <= 3]


def _list_lines(text: str) -> list[str]:
    """The lines of the document that are enumerating something."""
    lines = text.splitlines()
    out: list[str] = []
    in_list = False

    for line in lines:
        if not line.strip():
            in_list = False
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            remainder = (heading.group(2) or "").strip()
            if remainder:
                # "Required: Python, SQL" - the list is on the heading line.
                out.append(remainder)
                in_list = False
            else:
                # "SKILLS" alone - the list is on the lines that follow.
                in_list = True
            continue

        if in_list:
            # A prose bullet under a skills heading is still prose; a line with
            # no delimiter and more than MAX_WORDS words is a sentence.
            if _DELIMITERS.search(line) or len(line.split()) <= MAX_WORDS:
                out.append(line)
            else:
                in_list = False

    return out


def extract_surface_forms(text: str) -> list[str]:
    """Every skill-shaped phrase the document actually contains, in order.

    These are the STUDENT'S words, not the ontology's. Some will resolve to a
    concept and some will not, and the ones that do not are the whole point:
    they are what `unresolved_skills` was always meant to hold.
    """
    seen: set[str] = set()
    forms: list[str] = []

    def add(label: str) -> None:
        cleaned = _clean(label)
        if not _acceptable(cleaned):
            return
        # `skill_key`, not `normalise_alias`: the latter strips punctuation, so
        # a SKILLS line reading "C, C++, C#" deduplicated to a single entry and
        # two of the three languages vanished from the student's own read-back.
        dedup = skill_key(cleaned)
        if dedup in seen:
            return
        seen.add(dedup)
        forms.append(cleaned)

    for line in _list_lines(text):
        for fragment in _DELIMITERS.split(line):
            cleaned = _clean(fragment)
            if not _acceptable(cleaned):
                continue
            add(cleaned)
            for part in _split_conjunctions(cleaned):
                add(part)

    return forms


def scan_prose(text: str, concepts: list[dict[str, Any]]) -> set[str]:
    """Concept names whose name or an unambiguous alias appears in the text.

    This is the old behaviour, kept because it is genuinely useful, minus the
    part that invented requirements out of adjectives.
    """
    found: set[str] = set()
    haystack = text.lower()

    for concept in concepts:
        name = concept.get("name") or ""
        candidates = [name, *concept.get("aliases", [])]
        for candidate in candidates:
            if not candidate or not prose_safe_alias(candidate):
                continue
            if re.search(rf"\b{re.escape(candidate.lower())}\b", haystack):
                found.add(name)
                break

    return found


def drop_redundant(unresolved: list[str], resolved: list[str]) -> list[str]:
    """Remove a conjunction phrase once its parts are carrying the meaning.

    `_split_conjunctions` deliberately keeps the whole phrase AND its parts,
    because only the resolver can tell "Transactions and ACID" (one concept)
    from "SQL and data structures" (two). Once it has spoken, a long phrase
    that is fully represented by shorter entries is noise on the student's
    screen - "Docker and Kubernetes" next to "Docker" and "Kubernetes" reads
    as a parser stutter rather than as two requirements.

    Two ways a phrase becomes redundant:

      · it contains a label that resolved, so the resolved one is the claim;
      · every one of its conjunction parts is present in its own right.
    """
    kept: list[str] = []
    resolved_keys = [normalise_alias(r) for r in resolved]
    all_keys = {normalise_alias(x) for x in [*resolved, *unresolved]}

    for label in unresolved:
        key = normalise_alias(label)

        if any(r and r != key and r in key for r in resolved_keys):
            continue

        parts = [normalise_alias(p) for p in _split_conjunctions(label)]
        if parts and all(p in all_keys for p in parts):
            continue

        kept.append(label)

    return kept

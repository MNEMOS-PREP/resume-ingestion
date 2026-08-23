"""`SkillMention`: a skill, where it was written, and how sure we are of its id.

Spec §5 (data contract), §6.4 (normalisation order), FR-1.7, EC-1.12.

── The distinction this file exists to preserve ───────────────────────────────

§6.4, verbatim: *"a skill appearing only in a skills list gets
`context=skills_list` and is treated as a claim of familiarity; the same skill
inside a project description gets `context=project_tech` and is a claim of use.
M5 asks much harder questions about the latter. This distinction is cheap and
it is what makes the interview feel targeted."*

Cheap is right — it is which section the offset falls in — and it is the
difference between "have you used Docker?" and "why did you containerise that
service rather than ship a binary?". A flat `list[str]` of skills, which is
what this module carried before, cannot express it at all.

── The normalisation ORDER is the whole algorithm ─────────────────────────────

§6.4, and it is ordered for a reason:

    1. exact alias match                                   → confidence 1.00
    2. token ≤ 2 chars: ONLY exact match allowed. Stop.     (guards R, C, Go)
    3. fuzzy alias match (WRatio ≥ 92)                      → confidence 0.85
    4. embedding NN (cosine ≥ 0.86)                         → confidence 0.75
    5. unmapped → keep the surface form, queue for review

Step 2 is the one that gets dropped by whoever reimplements this, and it is
load-bearing: without it "R" fuzzy-matches "React" and a student who listed a
statistics language is asked about a frontend framework. Steps 3 and 4 need
`rapidfuzz` and an embedding service respectively; both are absent here, and
their absence is REPORTED (`mapping_method` is never guessed) rather than
papered over with a looser exact match.

── The unmapped queue is a feature ────────────────────────────────────────────

§6.4: *"The unmapped queue is a feature, not debt — it is how the ontology
learns what students actually write."*  So an unmapped mention keeps its
surface form, its span and its context, and is countable. `unmapped_report()`
is what a weekly ontology review reads.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from ai_core.concepts import normalise_alias
from pydantic import BaseModel, Field

from backend_M01_Resume_Ingestion import config
from backend_M01_Resume_Ingestion.claims import ResumeSection, SourceSpan

#: §5 names five methods: alias_exact, alias_fuzzy, embedding, llm, user. Two
#: more are here, and both are honesty rather than scope creep:
#:
#: `unmapped`   — the spec's step 5 outcome. §5 models it as `concept_id=None`,
#:                which leaves `mapping_method` naming a method that did not
#:                run. Saying so is better than picking one.
#:
#: `offline_alias` — an exact hit against M01's own five-entry fallback table
#:                while M04 is unreachable. It is not `alias_exact`: that means
#:                the ONTOLOGY confirmed the concept exists, and this table has
#:                not. It is emphatically not `llm` — no model ran, and
#:                labelling a hardcoded lookup as a model output is the exact
#:                confusion this module exists to prevent. Downstream, an id is
#:                a licence to test a student on it, and one nobody confirmed
#:                has to be visibly different from one M04 resolved.
MappingMethod = Literal[
    "alias_exact",
    "alias_fuzzy",
    "embedding",
    "llm",
    "user",
    "offline_alias",
    "unmapped",
]
SkillContext = Literal["skills_list", "project_tech", "experience_body", "education"]

#: Which context a section kind implies. `project_tech` and `experience_body`
#: are both claims of USE; the split is kept because M05 weights a shipped
#: internship differently from a course project.
_CONTEXT_BY_SECTION: dict[str, SkillContext] = {
    "skills": "skills_list",
    "projects": "project_tech",
    "experience": "experience_body",
    "education": "education",
    "certifications": "education",
    "publications": "experience_body",
    "achievements": "experience_body",
}

#: A mention outside any recognised section. Treated as the weakest claim
#: rather than dropped: it is on the resume, so it is a claim of something.
DEFAULT_CONTEXT: SkillContext = "skills_list"

#: How much weight a claim of use carries over a claim of familiarity. Read by
#: the claim scorer and by anything downstream deciding how hard to probe.
CONTEXT_STRENGTH: dict[SkillContext, float] = {
    "experience_body": 1.00,
    "project_tech": 0.85,
    "education": 0.50,
    "skills_list": 0.35,
}


class SkillMention(BaseModel):
    """One skill, as written, resolved as far as we can honestly resolve it."""

    surface: str
    concept_id: str | None = None
    mapping_method: MappingMethod = "unmapped"
    mapping_confidence: float = 0.0
    span: SourceSpan
    context: SkillContext = DEFAULT_CONTEXT
    #: EC-1.12: a skill listed fourteen times is one mention with a count, not
    #: fourteen mentions. Deduplicated per (concept, context), so the same
    #: skill in the skills list AND in a project stays two mentions — which is
    #: the entire point of `context`.
    occurrences: int = 1
    #: True when a student added or confirmed this, not the parser (FR-1.12).
    user_added: bool = False

    @property
    def is_mapped(self) -> bool:
        return self.concept_id is not None

    @property
    def claim_strength(self) -> float:
        """How strong a claim this mention is, before anyone tests it."""
        return round(CONTEXT_STRENGTH.get(self.context, 0.35) * self.mapping_confidence, 3)


def context_for(offset: int, sections: list[ResumeSection]) -> SkillContext:
    """Which section an offset falls in, as a skill context."""
    for section in sections:
        if section.span.start <= offset < section.span.end:
            return _CONTEXT_BY_SECTION.get(section.kind, DEFAULT_CONTEXT)
    return DEFAULT_CONTEXT


def guard_short_token(label: str) -> bool:
    """§6.4 step 2: may this label be matched by anything other than an exact rule?

    `R` is a language and `React` is not it. `C` is a language and `C++`, `C#`
    and the word "c" are not it. Two characters is where a fuzzy matcher stops
    being able to tell, so at that length only an exact alias hit counts —
    everything else must return unmapped rather than guess.
    """
    return len(normalise_alias(label).replace(" ", "")) > config.SHORT_TOKEN_MAX_CHARS


def find_mentions(
    text: str,
    labels: list[str],
    resume_id: uuid.UUID,
    sections: list[ResumeSection],
    *,
    resolved: dict[str, str],
    sources: dict[str, str],
) -> list[SkillMention]:
    """Every place each label is written, as `SkillMention`s (FR-1.7).

    `labels` are the surface forms extraction already found; `resolved` and
    `sources` are what the resolver said about them. This function does not
    resolve anything — it locates, contextualises and deduplicates, which is
    the part that needs the document.
    """
    by_key: dict[tuple[str, str], SkillMention] = {}

    for label in labels:
        concept_id = resolved.get(label)
        source = sources.get(label, "")
        method: MappingMethod
        if concept_id is None:
            method, confidence = "unmapped", 0.0
        elif source == "m04":
            method, confidence = "alias_exact", config.MAPPING_CONFIDENCE["alias_exact"]
        else:
            # An id the offline table produced while M04 was unreachable. See
            # the note on `MappingMethod`: not `alias_exact`, because nothing
            # confirmed the concept exists, and not `llm`, because no model ran.
            method, confidence = "offline_alias", config.MAPPING_CONFIDENCE["offline_alias"]

        for match in re.finditer(rf"\b{re.escape(label)}\b", text, re.IGNORECASE):
            context = context_for(match.start(), sections)
            key = (concept_id or normalise_alias(label), context)
            existing = by_key.get(key)
            if existing is not None:
                existing.occurrences += 1
                continue
            by_key[key] = SkillMention(
                surface=match.group(0),
                concept_id=concept_id,
                mapping_method=method,
                mapping_confidence=confidence,
                context=context,
                span=SourceSpan(
                    artifact_id=resume_id,
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                ),
            )

    return sorted(by_key.values(), key=lambda m: m.span.start)


def unmapped_report(mentions: list[SkillMention]) -> list[dict]:
    """The weekly ontology review queue (§6.4).

    Ordered by how often students wrote it, because that is the order in which
    adding a concept is worth someone fifteen minutes.
    """
    counts: dict[str, dict] = {}
    for mention in mentions:
        if mention.is_mapped:
            continue
        key = normalise_alias(mention.surface)
        entry = counts.setdefault(
            key, {"surface": mention.surface, "occurrences": 0, "contexts": set()}
        )
        entry["occurrences"] += mention.occurrences
        entry["contexts"].add(mention.context)

    return sorted(
        (
            {
                "surface": entry["surface"],
                "occurrences": entry["occurrences"],
                "contexts": sorted(entry["contexts"]),
            }
            for entry in counts.values()
        ),
        key=lambda entry: (-entry["occurrences"], entry["surface"]),
    )


class SkillSummary(BaseModel):
    """What a screen needs about the skills on one resume."""

    mentions: list[SkillMention] = Field(default_factory=list)
    mapped: int = 0
    unmapped: int = 0
    #: concept_id -> strongest context it was claimed in. What M05 reads when
    #: deciding how hard to probe a concept.
    claimed_use: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def of(cls, mentions: list[SkillMention]) -> SkillSummary:
        claimed: dict[str, str] = {}
        for mention in mentions:
            if not mention.concept_id:
                continue
            current = claimed.get(mention.concept_id)
            if current is None or CONTEXT_STRENGTH[mention.context] > CONTEXT_STRENGTH[current]:  # type: ignore[index]
                claimed[mention.concept_id] = mention.context
        return cls(
            mentions=mentions,
            mapped=sum(1 for m in mentions if m.is_mapped),
            unmapped=sum(1 for m in mentions if not m.is_mapped),
            claimed_use=claimed,
        )

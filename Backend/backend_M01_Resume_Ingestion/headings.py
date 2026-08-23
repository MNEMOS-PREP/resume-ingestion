"""The heading lexicon (§6.3), in one place.

    ~120 variants: "Technical Skills", "Academic Projects", "Areas of
    Interest", "Position of Responsibility" — the Indian-resume vocabulary
    specifically.

── Why this is its own module ─────────────────────────────────────────────────

There were two lexicons, and they disagreed. `claims.py` held one for section
segmentation; `extract.py` held another for deciding which lines are
enumerating a list. A heading in one and not the other fails in a way that is
genuinely hard to read from the outside:

  · in the SECTION lexicon only  → the section is labelled correctly and every
    skill under it is invisible, because nothing told the extractor that
    "COMPUTER PROFICIENCY" introduces a list;
  · in the ENUMERATION lexicon only → the skills come out and the section they
    came from is labelled `contact`, so `context` is wrong on every one of them
    and M05 asks a familiarity question about something the student built.

The golden set caught both at once: adding the Indian vocabulary moved section
F1 and skill recall together, which is the tell that they were one bug.

── The two lists are orthogonal, and that is deliberate ───────────────────────

`SECTION_HEADINGS` says what a section IS. `ENUMERATING` says whether what
follows is a list. "Relevant Coursework" is `education` and *is* a list.
"Work Experience" is `experience` and is not. Collapsing them into one table
would force a choice that is wrong for one of those two.

── What is deliberately absent ────────────────────────────────────────────────

"Languages Known". On an Indian resume that heading is followed by Tamil,
Hindi and English, and treating it as a skills list puts three spoken languages
into the concept ontology queue for ever. "Programming Languages" is here;
the bare-spoken-language sense is not, and the difference is the word that
disambiguates it.
"""

from __future__ import annotations

from typing import Literal

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

#: Heading text (normalised: lowercase, no punctuation) -> section kind.
#:
#: Ordered longest-phrase-first within each kind is NOT required — the matcher
#: does an exact pass across every kind before any partial pass, precisely so
#: that "Research Experience" resolves to `experience` rather than to
#: `publications` on the strength of starting with "research".
SECTION_HEADINGS: dict[SectionKind, tuple[str, ...]] = {
    "education": (
        "education",
        "educational qualifications",
        "educational qualification",
        "educational details",
        "educational background",
        "academic details",
        "academic qualifications",
        "academic background",
        "academic profile",
        "academic record",
        "academics",
        "qualifications",
        "scholastics",
        "scholastic record",
        "coursework",
        "relevant coursework",
        "related coursework",
        "courses",
        "subjects studied",
        "education and training",
    ),
    "experience": (
        "experience",
        "work experience",
        "working experience",
        "professional experience",
        "industry experience",
        "relevant experience",
        "research experience",
        "teaching experience",
        "employment",
        "employment history",
        "work history",
        "career history",
        "internship",
        "internships",
        "internship experience",
        "industrial training",
        "industrial exposure",
        "in-plant training",
        "trainings",
        "positions held",
        # A position of responsibility is a ROLE, not a hobby.
        #
        # These sat under `extras` and the consequence was silent: `extras` is
        # not a claim-bearing section, so a student who led a 200-person
        # technical festival got no claim, no probe and no score for it. On an
        # Indian campus resume that is one of the two or three things a panel
        # reliably asks about. §5's `SectionKind` has no better slot, and
        # `experience` is where an interviewer looks for a title, a duration
        # and a team.
        #
        # Hobbies, interests and co-curricular activities stay in `extras`,
        # because a bullet reading "Reading, cricket" is not a claim anyone can
        # defend and generating a probe for it makes the Claim Map untrustworthy.
        "position of responsibility",
        "positions of responsibility",
        "leadership",
        "leadership experience",
        "volunteer experience",
    ),
    "projects": (
        "projects",
        "personal projects",
        "academic projects",
        "selected projects",
        "technical projects",
        "mini projects",
        "mini project",
        "major projects",
        "major project",
        "key projects",
        "project work",
        "projects undertaken",
        "project experience",
        "capstone project",
    ),
    "skills": (
        "skills",
        "skill set",
        "technical skills",
        "core skills",
        "key skills",
        "soft skills",
        "it skills",
        "software skills",
        "computer skills",
        "computer proficiency",
        "computer knowledge",
        "technical proficiency",
        "technical competencies",
        "technical expertise",
        "core competencies",
        "competencies",
        "areas of expertise",
        "areas of interest",
        "area of interest",
        "expertise",
        "technologies",
        "technology",
        "technologies used",
        "tech stack",
        "tools",
        "tooling",
        "tools and technologies",
        "languages",
        "programming languages",
        "frameworks",
        "libraries",
        "platforms",
    ),
    "achievements": (
        "achievements",
        "achievement",
        "awards",
        "awards and achievements",
        "honors",
        "honours",
        "honors and awards",
        "accomplishments",
        "academic achievements",
        "scholastic achievements",
        "accolades",
        "recognitions",
        "prizes",
    ),
    "certifications": (
        "certifications",
        "certification",
        "certificates",
        "professional certifications",
        "courses and certifications",
        "online courses",
        "licenses",
        "licences",
        "credentials",
    ),
    "publications": (
        "publications",
        "papers",
        "research",
        "research papers",
        "research work",
        "journal publications",
        "conference papers",
        "patents",
    ),
    "summary": (
        "summary",
        "career summary",
        "professional summary",
        "executive summary",
        "profile",
        "career profile",
        "objective",
        "career objective",
        "professional objective",
        "about me",
        "about",
        "overview",
        "introduction",
    ),
    "contact": (
        "contact",
        "contact details",
        "contact information",
        "personal details",
        "personal information",
        "personal profile",
        "personal data",
        "particulars",
    ),
    "extras": (
        "extracurricular",
        "extra curricular",
        "extra curricular activities",
        "extracurricular activities",
        "co curricular activities",
        "cocurricular activities",
        "activities",
        "responsibilities",
        "volunteering",
        "community service",
        "social service",
        "interests",
        "hobbies",
        "hobbies and interests",
        "personal interests",
        "memberships",
        "affiliations",
        "additional information",
        "miscellaneous",
        "references",
        "declaration",
    ),
}

#: Headings after which the document is ENUMERATING — a comma or newline
#: separated list of skill-shaped items rather than prose.
#:
#: Mostly the `skills` block, plus the coursework headings (which are
#: `education` sections holding a list) and the requirement vocabulary a job
#: description uses — `extract.py` is shared with the JD side of the platform
#: and both read this.
ENUMERATING: frozenset[str] = frozenset(
    {
        *SECTION_HEADINGS["skills"],
        "coursework",
        "relevant coursework",
        "related coursework",
        "courses",
        "subjects studied",
        # A job description enumerating what it wants.
        "requirements",
        "required",
        "required skills",
        "must have",
        "must haves",
        "nice to have",
        "good to have",
        "preferred",
        "preferred skills",
        "qualifications",
        "you will need",
        "what we are looking for",
    }
)


def normalise(text: str) -> str:
    """A heading line to its lookup key.

    Ampersands become "and" and punctuation goes, because "Tools & Technologies",
    "Tools and Technologies" and "TOOLS/TECHNOLOGIES" are one heading written
    three ways and a lexicon that holds all three is a lexicon nobody maintains.
    """
    lowered = text.strip().casefold().replace("&", " and ").replace("/", " and ")
    kept = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in lowered)
    return " ".join(kept.split())


#: Built once: every variant, flattened, for the exact-match pass.
_EXACT: dict[str, SectionKind] = {
    normalise(variant): kind for kind, variants in SECTION_HEADINGS.items() for variant in variants
}

#: Longest first, so "research experience" is tried before "research".
_PARTIAL: list[tuple[str, SectionKind]] = sorted(
    ((normalise(v), k) for k, vs in SECTION_HEADINGS.items() for v in vs),
    key=lambda pair: -len(pair[0]),
)


def lookup(text: str) -> tuple[SectionKind, float] | None:
    """(kind, confidence) for a heading line, or None.

    Two passes, and the order is load-bearing. An exact match anywhere in the
    lexicon beats a partial match everywhere: matching kind-by-kind meant
    "Research Experience" hit `publications` on the strength of starting with
    "research" and never reached the exact `experience` entry, because whichever
    kind happened to be earlier in the dict won.
    """
    key = normalise(text)
    if not key:
        return None

    kind = _EXACT.get(key)
    if kind is not None:
        return kind, 0.85

    for variant, candidate in _PARTIAL:
        # Whole words only: "about" must not fire on "roundabout", and a
        # one-word variant must not match a fragment of a longer heading.
        if key.startswith(f"{variant} ") or key.endswith(f" {variant}") or f" {variant} " in key:
            return candidate, 0.6
    return None


def is_enumerating(text: str) -> bool:
    """Does a list follow this heading?"""
    return normalise(text) in {normalise(h) for h in ENUMERATING}


#: Precomputed, because `is_enumerating` is called per line of every document.
_ENUMERATING_KEYS = frozenset(normalise(h) for h in ENUMERATING)


def enumerating_keys() -> frozenset[str]:
    return _ENUMERATING_KEYS


def variant_count() -> int:
    """How many heading variants the lexicon holds. §6.3 asks for ~120."""
    return sum(len(variants) for variants in SECTION_HEADINGS.values())

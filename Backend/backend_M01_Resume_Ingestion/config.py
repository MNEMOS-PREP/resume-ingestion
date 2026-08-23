"""Every tunable number in the module, in one file.

Spec §6.6: *"Thresholds are config in `packages/ingestion/config.py` and tuned
once on 100 labelled resumes — do not scatter magic numbers through the code."*

That instruction is worth more than it looks. A threshold inlined at its use
site gets nudged by whoever is looking at the bullet that annoyed them today,
and the calibration nobody re-ran is the one that decides which claims a
student is told to worry about. Here they are visible together, and a change
to one is a change somebody has to justify against the rest.

── Why `PARSER_VERSION` is here too ───────────────────────────────────────────

Every stored claim carries the version of the code that produced it. When a
weight below moves, yesterday's rows are not silently reinterpreted under
today's rule: they say which rule they were scored under, and a re-parse is a
thing you can ask for rather than a thing that happens to you.
"""

from __future__ import annotations

#: Bumped whenever anything in this file changes, or the extraction changes
#: shape. Stored on every resume row (`parser_version`).
PARSER_VERSION = "m01-parser@1.0.0"

# ---------------------------------------------------------------------------
#  Intake (§6.1, FR-1.1)
# ---------------------------------------------------------------------------

#: Spec §6.1. A resume above this is not a resume.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: "a 12-page 'resume' is a CV; warn and parse the first 6" (§6.1).
MAX_PAGES = 6

#: Below this many characters the text layer is treated as absent and the OCR
#: path is taken (FR-1.16). A scanned PDF typically yields a handful of
#: header-metadata characters rather than zero, which is why this is not `== 0`.
MIN_TEXT_LAYER_CHARS = 100

# ---------------------------------------------------------------------------
#  Layout (§6.2, FR-1.4)
# ---------------------------------------------------------------------------

#: Histogram bins across the page width for column detection.
COLUMN_BINS = 20

#: A gutter must be at least this fraction of the page width to be a column
#: boundary rather than the space between two words.
COLUMN_MIN_GAP_FRACTION = 0.08

#: ...and the text either side of it must span at least this fraction of the
#: page height. A gap that only exists for three lines is a heading indent.
COLUMN_MIN_VERTICAL_COVERAGE = 0.60

#: Two words belong to the same line when their vertical centres are within
#: this multiple of the median line height (§6.2.3).
LINE_MERGE_TOLERANCE = 0.5

#: Everything read out of an OCR pass is less trustworthy than everything read
#: out of a text layer, and the whole document says so (§6.2.6).
OCR_CONFIDENCE_PENALTY = 0.15

#: Below this, the confirmation screen warns the student to check the reading
#: order themselves (EC-1.1).
COLUMN_CONFIDENCE_WARN_BELOW = 0.50

# ---------------------------------------------------------------------------
#  Defensibility (§6.6, FR-1.9)
# ---------------------------------------------------------------------------

#: Weights of the four axes in the composite. They sum to 1.0, and a change
#: that breaks that is a bug rather than a tuning choice.
RISK_WEIGHTS: dict[str, float] = {
    "specificity": 0.35,
    "verifiability": 0.30,
    "ownership_clarity": 0.20,
    "recency": 0.15,
}

#: risk <= STRONG_MAX is strong; <= VAGUE_MAX is vague; above is risky.
BAND_STRONG_MAX = 0.40
BAND_VAGUE_MAX = 0.62

#: Specificity components (§6.6). A bullet naming a technology AND a number is
#: the shape that survives being asked about.
SPECIFICITY_CONCEPT = 0.40
SPECIFICITY_QUANTIFIER = 0.40
SPECIFICITY_LENGTH = 0.20
SPECIFICITY_MIN_WORDS = 8

#: Verifiability (§6.6). The floor is not zero: a bullet with nothing behind it
#: can still be checked by asking the person who wrote it.
VERIFIABILITY_FLOOR = 0.15
VERIFIABILITY_LINK = 0.50
VERIFIABILITY_QUANTIFIER = 0.20
VERIFIABILITY_CONCEPT = 0.15

#: Ownership (§6.6). A bare verb-led bullet is the resume convention and reads
#: as first person, so it is not punished to the floor.
OWNERSHIP_FIRST_PERSON = 0.90
OWNERSHIP_VERB_LED = 0.70
OWNERSHIP_TEAM = 0.50
OWNERSHIP_PASSIVE = 0.45

#: Recency decays 0.16/year from 1.0, floored at 0.20. No date at all is 0.5 —
#: "we do not know when" is not the same claim as "this is old".
RECENCY_DECAY_PER_YEAR = 0.16
RECENCY_FLOOR = 0.20
RECENCY_UNDATED = 0.50

# ---------------------------------------------------------------------------
#  Prominence (§6.6)
# ---------------------------------------------------------------------------
#
#  Deliberately NOT a multiplier on `risk_score`.
#
#  The spec writes `risk_score = prominence * (1 - ...)`, and the sentence that
#  follows explains what it is for: "A vague bullet buried at the bottom of
#  page 2 is not a risk. A vague bullet that is the first line of the first
#  project is a *serious* risk, because it is what the interviewer reads
#  first."  That is a statement about which claim to show the student FIRST,
#  and it is used as one: `prominence * risk_score` orders the Claim Map and
#  picks §2.3's "the one thing to fix first" card.
#
#  Folding it into the band instead would mean a badly written bullet stops
#  being badly written by moving down the page, and the student who scrolls to
#  it is told it is fine. The band is a property of the sentence; the ordering
#  is a property of the page. Keeping them apart is what lets both be true.

#: 0.5·(1 - vertical position) + 0.3·section weight + 0.2·first-in-group.
PROMINENCE_POSITION = 0.50
PROMINENCE_SECTION = 0.30
PROMINENCE_FIRST_BULLET = 0.20

#: How much the interviewer cares that a claim is in this section at all.
SECTION_WEIGHT: dict[str, float] = {
    "experience": 1.00,
    "projects": 0.90,
    "publications": 0.75,
    "achievements": 0.60,
    "education": 0.40,
    "extras": 0.25,
    "unknown": 0.50,
}
SECTION_WEIGHT_DEFAULT = 0.50

# ---------------------------------------------------------------------------
#  Red flags (§6.8, FR-1.13)
# ---------------------------------------------------------------------------

#: Months between two dated periods before it is worth having an answer ready.
TIMELINE_GAP_MONTHS = 6

#: Title similarity AND date overlap, both, before two entries are one project.
DUPLICATE_TITLE_SIMILARITY = 0.85

#: Duplicate detection compares every claim against every earlier one, so the
#: pass is quadratic in claim count. A real resume has fewer than forty
#: bullets; a pasted document with two thousand is either a mistake or an
#: attempt, and neither deserves four million string comparisons. Claims beyond
#: this are still extracted, scored and probed — they are simply not searched
#: for duplicates, which is the cheapest thing on the page to give up.
DUPLICATE_MAX_CLAIMS_COMPARED = 80

#: At most this many duplicate groups reported. Past a handful the finding is
#: not "you listed this project twice", it is "this document repeats itself",
#: and one sentence says that better than fifty flags do.
DUPLICATE_MAX_GROUPS = 5

# ---------------------------------------------------------------------------
#  Skill normalisation (§6.4, FR-1.7)
# ---------------------------------------------------------------------------

#: Confidence attached to each mapping method, so a downstream consumer can
#: apply its own bar rather than trusting every id equally.
MAPPING_CONFIDENCE: dict[str, float] = {
    "alias_exact": 1.00,
    "alias_fuzzy": 0.85,
    "embedding": 0.75,
    "llm": 0.60,
    "user": 1.00,
    # An exact hit against M01's own five-entry fallback table, with M04
    # unreachable. Below `alias_fuzzy` on purpose: a fuzzy hit against the real
    # ontology is a mapping to a concept that is known to exist, and this is a
    # mapping to one nobody has confirmed. See `skills.MappingMethod`.
    "offline_alias": 0.55,
}

#: §6.4 step 2: a token of this length or shorter may ONLY match exactly.
#: This is what stops "R" matching "React" and "C" matching "C++".
SHORT_TOKEN_MAX_CHARS = 2

"""§6.4's five-step skill normalisation, in the order the spec gives it.

    1. Exact match against alias table (case/whitespace/punct-normalised)  1.00
    2. If token length ≤ 2 chars: ONLY exact match allowed. Stop.   (R, C, Go)
    3. Fuzzy match (rapidfuzz WRatio ≥ 92) against aliases                 0.85
    4. Embedding NN against concept names+aliases, cosine ≥ 0.86           0.75
    5. Unmapped → store surface form, queue for the weekly ontology review

*"This order is the whole algorithm."*

── Step 2 is the one that gets dropped ────────────────────────────────────────

And it is load-bearing. `R` is a statistics language; at WRatio it is an 80%
match for `React` and a 90% match for `Ruby`. Without the guard a student who
listed R gets asked about a frontend framework, which is the "system was not
listening" failure §2.3 says loses the confident student. So at two characters
or fewer, an exact hit is the only hit — everything else returns unmapped, and
unmapped is a perfectly good answer.

── Why fuzzy is bounded so tightly ────────────────────────────────────────────

WRatio ≥ 92 is high, and it is high deliberately. §13 wants precision ≥ 0.95
and recall ≥ 0.85 — precision is the harder target and the more damaging miss,
because an invented skill becomes an interview question about something the
student never claimed. A loose threshold buys recall by spending precision, and
the confirmation screen already recovers recall for free: a student adds a
missed skill in fifteen seconds, and never notices one we silently invented.

Two further guards on top of the threshold:

· **length ratio** — "Java" and "JavaScript" score 90 on WRatio and are not the
  same skill. A candidate more than half again as long as the query is refused
  however well it scores.
· **first letter** — a fuzzy hit that does not start the same way is almost
  always a coincidence at this threshold, and cheap to reject.

── Step 4 is absent, and says so ──────────────────────────────────────────────

Embedding nearest-neighbour needs a platform embedding service that does not
exist. `mapping_method` is never `"embedding"`, so nothing downstream can
mistake a fuzzy hit for a semantic one — the absence is reported, not papered
over by loosening step 3 to cover for it.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import NamedTuple

from backend_M01_Resume_Ingestion import config

log = logging.getLogger("uvicorn.error")

ALIAS_FILE = Path(__file__).resolve().parent / "aliases.yaml"

#: Characters that are part of a name rather than punctuation around it.
#:
#: `ai_core.concepts.normalise_alias` strips punctuation, which is right for an
#: ontology label and catastrophic here: it folds `C`, `C#` and `C++` onto the
#: single key `c`, so whichever landed in the table last answered for all three
#: and a student who wrote C++ was asked about C#. `.NET` loses its dot the same
#: way. So the table is keyed on a normalisation that keeps `+`, `#` and `.`,
#: and only the surrounding punctuation is folded away.
_SIGNIFICANT = frozenset("+#.")


def key(text: str) -> str:
    """Lookup key for the alias table. Keeps `+`, `#` and `.`; folds the rest."""
    kept = [ch if (ch.isalnum() or ch in _SIGNIFICANT) else " " for ch in text.strip().casefold()]
    return " ".join("".join(kept).split())


def _letters_only(text: str) -> str:
    """The name with every non-letter removed — how LONG is it, really?

    `C++` and `C#` are one-letter names wearing punctuation, and they belong in
    the same exact-match-only class as `C` and `R`. Measuring them at three
    characters would let them reach the fuzzy step, which is precisely where
    one-letter names go wrong.
    """
    return "".join(ch for ch in text.casefold() if ch.isalnum())


#: §6.4 step 3. Deliberately high — see the module docstring.
FUZZY_THRESHOLD = 92

#: A candidate this much longer than the query is a different word, whatever it
#: scores. "Java" → "JavaScript" is the case this exists for.
MAX_LENGTH_RATIO = 1.5


class Match(NamedTuple):
    """One resolution attempt, and how it was reached."""

    canonical: str | None
    method: str
    confidence: float

    @property
    def mapped(self) -> bool:
        return self.canonical is not None


UNMAPPED = Match(None, "unmapped", 0.0)


@functools.lru_cache(maxsize=1)
def alias_table() -> dict[str, str]:
    """normalised alias -> canonical name.

    Built once. Every canonical name is also an alias of itself, so an exact
    match on the name never has to fall through to the fuzzy step.
    """
    try:
        import yaml
    except ImportError:  # pragma: no cover - PyYAML ships with the core dep
        log.warning("M01 PyYAML missing; the alias table is unavailable")
        return {}

    if not ALIAS_FILE.exists():
        log.warning("M01 alias table not found at %s", ALIAS_FILE)
        return {}

    raw = yaml.safe_load(ALIAS_FILE.read_text(encoding="utf-8")) or {}
    table: dict[str, str] = {}
    for canonical, aliases in raw.items():
        table[key(canonical)] = canonical
        for alias in aliases or []:
            alias_key = key(str(alias))
            if not alias_key:
                continue
            if alias_key in table and table[alias_key] != canonical:
                # Two canonical names claiming one spelling is a curation bug,
                # and a silent last-write-wins is how a resume's "CV" becomes
                # Computer Vision on one deploy and Curriculum Vitae on the next.
                log.warning(
                    "M01 alias %r claimed by both %r and %r; keeping the first",
                    alias,
                    table[alias_key],
                    canonical,
                )
                continue
            table[alias_key] = canonical
    return table


def is_short(label: str) -> bool:
    """§6.4 step 2: at this length, only an exact match is allowed.

    Measured in LETTERS, so `C#` and `C++` join `C` and `R` in the exact-only
    class rather than sneaking past on their punctuation.
    """
    return len(_letters_only(label)) <= config.SHORT_TOKEN_MAX_CHARS


def resolve(label: str) -> Match:
    """One surface form to a canonical name, by §6.4's ladder."""
    lookup = key(label)
    if not lookup:
        return UNMAPPED

    table = alias_table()

    # Step 1 — exact.
    canonical = table.get(lookup)
    if canonical is not None:
        return Match(canonical, "alias_exact", config.MAPPING_CONFIDENCE["alias_exact"])

    # Step 2 — stop here for short tokens. `R` must not reach the fuzzy step.
    if is_short(label):
        return UNMAPPED

    # Step 3 — fuzzy.
    return _fuzzy(lookup, table)

    # Step 4 — embedding. Absent: see the module docstring.


# The parameter is `lookup`, not `key`: `key` is the module-level function
# above, and shadowing it here is one refactor away from a silent bug.
def _fuzzy(lookup: str, table: dict[str, str]) -> Match:
    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        # Reported, not silently skipped: a deployment without rapidfuzz has
        # measurably worse recall and should be able to find that out.
        log.info("M01 rapidfuzz not installed; §6.4 step 3 is skipped")
        return UNMAPPED

    hits = process.extract(lookup, table.keys(), scorer=fuzz.WRatio, limit=5)
    for candidate, score, _ in hits:
        if score < FUZZY_THRESHOLD:
            break
        if len(candidate) > len(lookup) * MAX_LENGTH_RATIO:
            continue  # "Java" is not "JavaScript"
        if candidate[:1] != lookup[:1]:
            continue  # a coincidence at this threshold, near enough always
        return Match(table[candidate], "alias_fuzzy", config.MAPPING_CONFIDENCE["alias_fuzzy"])
    return UNMAPPED


def canonical_names() -> list[str]:
    """Every canonical name the table knows, for a resolver to ask M04 about."""
    return sorted(set(alias_table().values()))

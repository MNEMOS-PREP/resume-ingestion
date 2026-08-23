"""Corrections as ground truth (FR-1.12), and re-upload diffs (FR-1.15).

── Why corrections outrank the parser ──────────────────────────────────────────

The parser is a regex pass over a document with no schema. It will read a
section wrong, and when it does the student is the authority - they wrote the
thing. So a correction is not a suggestion the parser weighs; it is applied,
and the corrected field is stamped `user_corrected` / `user_edited` so nothing
downstream mistakes it for a machine reading.

Corrections follow the CONTENT, not the row. They are keyed by
`(candidate_id, content_sha256)`, so re-uploading the same file re-applies
every fix the student already made. Keying them to the resume id instead would
mean correcting the same mis-read heading on every upload, which is how a
correction feature stops being used.

── What a diff is for ──────────────────────────────────────────────────────────

"3 new claims, 1 removed" is the spec's phrasing. The comparison is on claim
TEXT rather than on claim id, because ids are per-parse and every id changes on
re-upload - a diff keyed on them would report a totally rewritten resume every
time somebody fixed a typo.
"""

from __future__ import annotations

import re
from typing import Any

_WHITESPACE = re.compile(r"\s+")

#: What may be corrected, and on which target. A field not on this map is
#: rejected rather than written: the alternative is an endpoint that can set
#: any attribute on any row.
#:
#: `claim.present` is the delete path (EC-1.17: *"User deletes every claim in
#: the editor — allowed; product continues resume-free"*). Modelled as a field
#: rather than as a DELETE verb so it goes through the same audit log as every
#: other disagreement: a student removing a claim we invented is the single
#: most informative correction there is, and AC-1.7 should count it.
#:
#: `entity.dates` is §2.3 Screen 3's fourth editable target — "sections,
#: bullets, skills, and dates". A mis-read date was the one thing a student
#: could not fix, and it drives both the timeline-gap flag and `recency`.
ALLOWED: dict[str, frozenset[str]] = {
    "section": frozenset({"kind"}),
    "claim": frozenset({"text", "claim_type", "present"}),
    "skill": frozenset({"present"}),
    "entity": frozenset({"dates"}),
}


def normalise(text: str) -> str:
    """Comparison key for a claim: case and whitespace do not make it new."""
    return _WHITESPACE.sub(" ", text or "").strip().casefold()


def _correct_date(entities: dict, index: str, value: str | None) -> tuple[bool, str | None]:
    """Replace one extracted date range with the student's own (FR-1.11).

    The typed value goes through the SAME parser that read the document, so a
    corrected date and a parsed one are indistinguishable downstream. Accepting
    a free string instead would mean the timeline-gap rule had to handle two
    shapes, and the one a human typed is the one it would get wrong.

    A value that will not parse is refused rather than stored: a date nothing
    can compare is worse than the mis-read it replaced, because the mis-read at
    least still fires the gap check.
    """
    from backend_M01_Resume_Ingestion import dates

    ranges = entities.get("dates")
    if not isinstance(ranges, list):
        return False, None
    try:
        position = int(index)
        current = ranges[position]
    except (ValueError, IndexError, TypeError):
        return False, None

    if not value or not value.strip():
        # Striking a date the parser invented is a correction too.
        ranges.pop(position)
        return True, current.get("raw")

    match = dates.RANGE.search(value)
    if match is None:
        return False, current.get("raw")

    tail = match.group("y2")
    ongoing = dates.is_open_ended(tail)
    ranges[position] = {
        **current,
        "raw": match.group(0).strip(),
        "start_year": dates.year(match.group("y1")),
        "end_year": None if ongoing else dates.year(tail),
        "ongoing": ongoing,
        "user_corrected": True,
    }
    return True, current.get("raw")


def apply_correction(
    sections: list[dict],
    claims: list[dict],
    parsed_skills: list[str],
    unresolved_skills: list[str],
    resolved_concepts: dict[str, str],
    *,
    target: str,
    target_id: str,
    field: str,
    value: str | None,
    entities: dict | None = None,
) -> tuple[bool, str | None]:
    """Apply one correction in place. Returns (applied, old_value)."""
    if field not in ALLOWED.get(target, frozenset()):
        return False, None

    if target == "section":
        for section in sections:
            if str(section.get("id")) == target_id:
                old = section.get("kind")
                section["kind"] = value
                section["user_corrected"] = True
                return True, old
        return False, None

    if target == "claim":
        for index, claim in enumerate(claims):
            if str(claim.get("id")) != target_id:
                continue
            if field == "present":
                # EC-1.17. Removed outright rather than flagged hidden: a claim
                # the student says is not theirs must not reach M05 or M06 at
                # all, and a `hidden` flag is a thing four downstream readers
                # would each have to remember to honour.
                if (value or "").casefold() in {"true", "1", "yes"}:
                    return False, "true"
                claims.pop(index)
                return True, "true"
            old = claim.get(field)
            claim[field] = value
            claim["user_edited"] = True
            return True, str(old) if old is not None else None
        return False, None

    if target == "entity":
        # §2.3 Screen 3's fourth editable target. `target_id` is the index into
        # `entities["dates"]`, and `value` is the corrected range as the student
        # would write it — parsed here so a typed date and a read one are the
        # same shape downstream.
        return _correct_date(entities or {}, target_id, value)

    # target == "skill": the student adding one we missed, or striking one we
    # invented. Either way it lands in `unresolved_skills` — M01 does not get
    # to mint a concept_id, and a student-added skill has no ontology mapping
    # until M04 says so.
    label = target_id
    present = (value or "").casefold() in {"true", "1", "yes"}
    was = label in parsed_skills

    if present and not was:
        parsed_skills.append(label)
        unresolved_skills.append(label)
        return True, "false"
    if not present and was:
        parsed_skills.remove(label)
        if label in unresolved_skills:
            unresolved_skills.remove(label)
        resolved_concepts.pop(label, None)
        return True, "true"
    return False, str(was).casefold()


def diff_claims(before: list[dict], after: list[dict]) -> dict[str, Any]:
    """What changed between two parses of a candidate's resume.

    `changed` holds claims whose text survived but whose risk band moved — a
    bullet the student rewrote to add a number is the single most useful thing
    a re-upload can report, and text-only comparison would call it unchanged.
    """
    before_by_text = {normalise(c["text"]): c for c in before}
    after_by_text = {normalise(c["text"]): c for c in after}

    added = [c for key, c in after_by_text.items() if key not in before_by_text]
    removed = [c for key, c in before_by_text.items() if key not in after_by_text]

    changed = []
    for key, new in after_by_text.items():
        old = before_by_text.get(key)
        if old and old.get("risk_band") != new.get("risk_band"):
            changed.append(
                {
                    "text": new["text"],
                    "risk_band_before": old.get("risk_band"),
                    "risk_band_after": new.get("risk_band"),
                }
            )

    return {
        "added": [{"text": c["text"], "risk_band": c.get("risk_band")} for c in added],
        "removed": [{"text": c["text"], "risk_band": c.get("risk_band")} for c in removed],
        "changed": changed,
        "summary": (
            f"{len(added)} new claim{'s' if len(added) != 1 else ''}, "
            f"{len(removed)} removed, {len(changed)} re-banded"
        ),
    }

"""The claim pipeline: sections, claims, scores, probes, flags, and PII.

Spec: M01 §5, §13. FR-1.5, FR-1.6, FR-1.8, FR-1.9, FR-1.10, FR-1.13, FR-1.17,
FR-1.18, and the storage-key half of FR-1.2.

Three of these carry the `gate` marker because the spec marks the criteria
they cover as release-blocking. Before this file `pytest -m gate` collected
nothing in this repository, which is why "no gates in M01 or M02" was on the
platform debt list.
"""

import uuid
from datetime import date

import pytest
from backend_M01_Resume_Ingestion.claims import band, extract_quantifiers, score_claim

RESUME = """PRIYA SHARMA
priya.sharma@example.com | +91 98765 43210 | github.com/priyash

EDUCATION
Amrita Vishwa Vidyapeetham, B.Tech CSE, 2022 - 2026, CGPA 8.1

PROJECTS
- Built a route planner in Python using dynamic programming; cut average query time from 380ms to 45ms on a 12k-node graph.
- Led a team of 4 to ship a REST API with FastAPI and PostgreSQL serving 50k requests/day.
- Worked on a world-class seamless blockchain platform.

SKILLS
Python, Java, SQL, Docker, Kubernetes, React
"""


def _ingest(client, text=RESUME):
    res = client.post(
        "/v1/resumes/ingest",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
#  FR-1.5 - sections
# ---------------------------------------------------------------------------


def test_sections_are_segmented_with_a_confidence(client, m04_up):
    m04_up()
    kinds = {s["kind"]: s for s in _ingest(client)["sections"]}

    assert {"education", "projects", "skills"} <= set(kinds)
    for section in kinds.values():
        assert 0.0 <= section["confidence"] <= 1.0
        assert section["span"]["end"] > section["span"]["start"]


def test_a_resume_with_no_headings_is_one_low_confidence_section(client, m04_up):
    """Not an error.

    "We could not tell what any of this is" is a real answer, and saying it at
    0.2 confidence is more useful than guessing a section kind at 0.9.
    """
    m04_up()
    sections = _ingest(client, "Some prose with no headings at all in it.")["sections"]

    assert len(sections) == 1
    assert sections[0]["kind"] == "unknown"
    assert sections[0]["confidence"] < 0.5


# ---------------------------------------------------------------------------
#  FR-1.8 - claims, and the span that makes them traceable
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_every_claim_span_verbatim_resolves(client, m04_up):
    """AC-1.1 [GATE] - target 100%.

    The span is "the atom of traceability: everything downstream cites one of
    these". A span that does not resolve at its own offsets is a citation to
    text that is not there, which is exactly what M13 re-verifies by checksum
    to prevent. Same rule, one module earlier.
    """
    m04_up()
    data = _ingest(client)
    # The response carries the redacted copy, which is the same length as the
    # original character for character - that is what makes offsets portable.
    source = data["redacted_text"]

    assert data["claims"], "a resume with three project bullets produced no claims"
    for claim in data["claims"]:
        span = claim["span"]
        assert source[span["start"] : span["end"]] == span["text"]
        for quantifier in claim["quantifiers"]:
            qspan = quantifier["span"]
            assert source[qspan["start"] : qspan["end"]] == qspan["text"]


def test_bullets_become_claims_and_skills_lines_do_not(client, m04_up):
    """A skills line asserts nothing probeable.

    "Python" is not a claim anyone can be asked to defend. The bullet that says
    what was built with it is.
    """
    m04_up()
    claims = _ingest(client)["claims"]

    assert len(claims) == 3
    assert all("Python," not in c["text"] for c in claims)


def test_claim_type_comes_from_the_verb(client, m04_up):
    m04_up()
    types = [c["claim_type"] for c in _ingest(client)["claims"]]

    assert "improved" in types
    assert "led" in types


# ---------------------------------------------------------------------------
#  FR-1.9 - defensibility
# ---------------------------------------------------------------------------


def test_a_vague_bullet_scores_worse_than_a_specific_one(client, m04_up):
    """The point of the four axes.

    These two bullets are different claims, and a student should be able to see
    which one will not survive being asked about.
    """
    m04_up()
    claims = {c["claim_type"]: c for c in _ingest(client)["claims"]}

    specific = claims["improved"]
    vague = claims["used"]

    assert specific["risk_band"] == "strong"
    assert vague["risk_band"] == "risky"
    assert specific["specificity"] > vague["specificity"]
    assert specific["verifiability"] > vague["verifiability"]


def test_quantifiers_are_extracted_with_units(client, m04_up):
    m04_up()
    claims = {c["claim_type"]: c for c in _ingest(client)["claims"]}
    raws = [q["raw"] for q in claims["improved"]["quantifiers"]]

    assert "380ms" in raws
    assert "45ms" in raws


def test_recency_with_no_date_is_a_half_not_a_zero(client, m04_up):
    """Rule 3, one level down.

    "We do not know when you did this" is not the same claim as "this is old",
    and scoring it 0.0 would quietly make every undated bullet look stale.
    """
    m04_up()
    data = _ingest(client, "PROJECTS\n- Built a parser in Python using recursion.\n")

    assert data["claims"][0]["recency"] == 0.5


# ---------------------------------------------------------------------------
#  FR-1.10 - probes
# ---------------------------------------------------------------------------


def test_probes_escalate_and_are_grounded_in_the_bullet(client, m04_up):
    m04_up()
    claims = {c["claim_type"]: c for c in _ingest(client)["claims"]}
    probes = claims["improved"]["probes"]

    assert 1 <= len(probes) <= 3
    assert [p["depth"] for p in probes] == sorted(p["depth"] for p in probes)
    # The measurement probe quotes the student's own number back at them.
    assert any("380ms" in p["question"] for p in probes)
    for probe in probes:
        assert probe["expects"]
        assert probe["rationale"]
        assert probe["generated_by"].startswith("m01-probes@")


def test_a_weak_claim_gets_the_opening_probe_and_a_strong_one_does_not(client, m04_up):
    """Asking someone to restate a specific, numbered bullet wastes the first
    question of an interview."""
    m04_up()
    claims = {c["claim_type"]: c for c in _ingest(client)["claims"]}

    assert min(p["depth"] for p in claims["used"]["probes"]) == 0
    assert min(p["depth"] for p in claims["improved"]["probes"]) > 0


# ---------------------------------------------------------------------------
#  FR-1.13 - red flags
# ---------------------------------------------------------------------------


def test_a_superlative_with_no_number_is_flagged(client, m04_up):
    m04_up()
    flags = _ingest(client)["red_flags"]
    kinds = {f["kind"] for f in flags}

    assert "unverifiable_superlative" in kinds
    for flag in flags:
        assert flag["explanation"]
        # Non-judgemental: these are things to have an answer ready for.
        assert "lying" not in flag["explanation"].casefold()


def test_a_backwards_date_range_is_flagged(client, m04_up):
    m04_up()
    data = _ingest(client, "EXPERIENCE\n- Intern, Jun 2025 - Jan 2024, did things.\n")

    assert any(f["kind"] == "chronology_conflict" for f in data["red_flags"])


# ---------------------------------------------------------------------------
#  FR-1.17 - PII
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_the_contact_block_never_rides_along_with_the_resume(client, m04_up):
    """AC-1.9 - zero PII in any model call.

    Enforced by construction: `raw_text` is on the table and is not on
    `ResumeOut`, so no response can carry it and no caller has to remember to
    strip it. The redacted copy is what a screen or a model sees.
    """
    m04_up()
    data = _ingest(client)

    assert "raw_text" not in data
    body = str(data)
    assert "priya.sharma@example.com" not in body
    assert "98765" not in body
    assert "github.com/priyash" not in body


def test_redaction_preserves_every_offset(client, m04_up):
    """Masking rather than deleting, because deleting moves every span that
    comes after the contact block."""
    m04_up()
    data = _ingest(client)

    assert len(data["redacted_text"]) == len(RESUME)


def test_contact_is_released_only_by_its_own_route(client, m04_up):
    m04_up()
    data = _ingest(client)

    contact = client.get("/v1/resumes/" + data["id"] + "/contact").json()
    assert contact["emails"] == ["priya.sharma@example.com"]
    assert contact["phones"] and "98765" in contact["phones"][0]


# ---------------------------------------------------------------------------
#  FR-1.2 (storage key) and FR-1.18 (budget)
# ---------------------------------------------------------------------------


def test_the_same_resume_twice_has_the_same_digest(client, m04_up):
    m04_up()
    first, second = _ingest(client), _ingest(client)

    assert first["content_sha256"] == second["content_sha256"]
    assert len(first["content_sha256"]) == 64
    assert first["id"] != second["id"]


@pytest.mark.gate
def test_parse_completes_inside_the_budget(client, m04_up):
    """AC-1.6 - p95 end-to-end under 25 s for two pages without OCR.

    Recorded per ingest rather than asserted once, so the number on the row is
    the evidence and a regression shows up as data rather than as a feeling.
    """
    m04_up()
    data = _ingest(client)

    assert data["parse_ms"] > 0
    assert data["parse_ms"] < 25_000


# ---------------------------------------------------------------------------
#  Quantifiers the old pattern could not see
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("macro-F1: 0.897", "macro-F1: 0.897"),
        ("F1 of 0.897", "F1 of 0.897"),
        ("accuracy = 0.92", "accuracy = 0.92"),
        ("0.897 macro-F1", "0.897 macro-F1"),
        ("AUC of 0.81", "AUC of 0.81"),
        ("Dice 0.88 on the validation split", "Dice 0.88"),
        # The hyphen case: `\s*` cannot cross it, so every compound-adjective
        # measurement on a real resume was invisible.
        ("within a 72-hour window", "72-hour"),
    ],
)
def test_a_measurement_without_a_unit_is_still_a_measurement(text, expected):
    """A bare decimal is only a number when a metric names it.

    `macro-F1: 0.897` is the most important fact on the bullet, and the old
    pattern required a unit — so a student with a measured ML result was told
    "there is no number in it and nothing named an interviewer can hold on to".
    """
    found = extract_quantifiers(text, 0, uuid.uuid4())

    assert [q.raw for q in found] == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "B.Tech CSE, 2022 - 2026, CGPA 8.1",
        "DeBERTa-v3 pipeline",
        "version 3.11 of Python",
        "Recall 2024",
    ],
)
def test_a_year_or_a_version_is_not_a_measurement(text):
    """The other side of the line, and the expensive one.

    A fabricated quantifier RAISES `specificity` and `verifiability` for a
    claim that has not earned it — so matching any decimal would make every
    bullet with a version number look better defended than it is.
    """
    assert extract_quantifiers(text, 0, uuid.uuid4()) == []


def test_a_metric_phrase_is_one_quantifier_not_two():
    """Overlaps resolve to the longer match.

    The depth-2 probe quotes `raw` back — "You quote macro-F1: 0.897. How was
    that measured?" — and "You quote 0.897" is a question about nothing.
    """
    found = extract_quantifiers("achieving macro-F1: 0.897 overall", 0, uuid.uuid4())

    assert len(found) == 1
    assert found[0].raw == "macro-F1: 0.897"
    assert found[0].value == 0.897


def test_an_unreadable_number_costs_the_claim_a_whole_risk_band():
    """Why this is a scoring bug and not a copy bug.

    `specificity` and `verifiability` both read the quantifier list, and the
    band falls out of both. A bullet whose measurement we cannot see is banded
    as though it has none — and `fix_first` picks the most prominent RISKY
    claim, so this puts the wrong bullet in "the one thing to fix first".
    """
    text = "Developed a DeBERTa pipeline for complaint classification (macro-F1: 0.897)."
    rid = uuid.uuid4()
    today = date.today()

    with_number = score_claim(
        text,
        quantifiers=extract_quantifiers(text, 0, rid),
        concepts=[],
        has_link=False,
        prominence=0.8,
        today=today,
    )
    blind = score_claim(
        text, quantifiers=[], concepts=[], has_link=False, prominence=0.8, today=today
    )

    assert with_number["specificity"] > blind["specificity"]
    assert with_number["verifiability"] > blind["verifiability"]
    assert band(with_number["risk_score"]) != band(blind["risk_score"])

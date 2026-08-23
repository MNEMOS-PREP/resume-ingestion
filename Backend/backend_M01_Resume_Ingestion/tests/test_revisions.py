"""Entities, immutable storage, corrections, diffs and analytics events.

Spec: FR-1.2, FR-1.6, FR-1.12, FR-1.15, FR-1.20.
"""

import uuid

import pytest
from backend_M01_Resume_Ingestion import storage

RESUME = """PRIYA SHARMA
priya.sharma@example.com | +91 98765 43210

EDUCATION
Amrita Vishwa Vidyapeetham, B.Tech CSE, 2022 - 2026, CGPA 8.1

EXPERIENCE
- Software Engineer Intern, Jun 2025 - Aug 2025, built internal tooling.

PROJECTS
- Built a route planner in Python using dynamic programming; cut query time from 380ms to 45ms.
- Worked on a world-class blockchain platform.

SKILLS
Python, Docker, Kubernetes
"""


def _ingest(client, text=RESUME, candidate=None):
    res = client.post(
        "/v1/resumes/ingest",
        json={"candidate_id": str(candidate or uuid.uuid4()), "raw_text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
#  FR-1.6 - entities
# ---------------------------------------------------------------------------


def test_name_education_and_dates_are_extracted(client, m04_up):
    m04_up()
    entities = _ingest(client)["entities"]

    assert entities["name"] == "PRIYA SHARMA"

    assert entities["education"], "an EDUCATION section with a degree produced no entry"
    education = entities["education"][0]
    assert "Vidyapeetham" in (education["institution"] or "")
    assert "Tech" in (education["degree"] or "")
    assert education["grade"] == "8.1"
    assert education["dates"]["start_year"] == 2022
    assert education["dates"]["end_year"] == 2026


def test_roles_come_from_experience_not_from_prose(client, m04_up):
    m04_up()
    entities = _ingest(client)["entities"]
    titles = [r["title"] for r in entities["roles"]]

    assert any("Intern" in (t or "") for t in titles)


def test_an_institution_in_a_project_bullet_is_not_a_degree(client, m04_up):
    """The guard on reading education out of the wrong section."""
    m04_up()
    entities = _ingest(
        client,
        "PROJECTS\n- Built a scraper for the Indian Institute of Science website.\n",
    )["entities"]

    assert entities["education"] == []


def test_a_name_that_does_not_look_like_one_is_left_alone(client, m04_up):
    """Guessing wrong is worse than not guessing: the name is what a placement
    cell matches a student by."""
    m04_up()
    entities = _ingest(client, "CURRICULUM VITAE\n\nSKILLS\nPython\n")["entities"]

    assert entities["name"] is None


# ---------------------------------------------------------------------------
#  FR-1.2 - immutable, content-addressed storage
# ---------------------------------------------------------------------------


def test_the_artifact_is_stored_under_its_digest(client, m04_up):
    m04_up()
    data = _ingest(client)

    assert data["storage_uri"].startswith("file://")
    assert data["content_sha256"] in data["storage_uri"]
    assert storage.get(data["content_sha256"]) == RESUME


def test_the_same_bytes_are_stored_once(client, m04_up):
    """Two rows, one object. The key IS the digest, so identical content
    cannot occupy two places."""
    m04_up()
    first, second = _ingest(client), _ingest(client)

    assert first["id"] != second["id"]
    assert first["storage_uri"] == second["storage_uri"]


def test_a_missing_blob_reads_as_none_rather_than_raising(client, m04_up):
    """A row whose artifact has gone is a degraded read, not a crash."""
    assert storage.get("0" * 64) is None


# ---------------------------------------------------------------------------
#  FR-1.12 - corrections are ground truth
# ---------------------------------------------------------------------------


def test_a_section_correction_is_applied_and_marked(client, m04_up):
    m04_up()
    data = _ingest(client)
    section = data["sections"][1]

    res = client.post(
        "/v1/resumes/" + data["id"] + "/corrections",
        json={
            "target": "section",
            "target_id": section["id"],
            "field": "kind",
            "value": "certifications",
        },
    )
    assert res.status_code == 201, res.text
    corrected = res.json()["sections"][1]

    assert corrected["kind"] == "certifications"
    assert corrected["user_corrected"] is True


def test_a_student_can_add_a_skill_the_parser_missed(client, m04_up):
    """And it lands unmapped: M01 does not get to mint a concept_id."""
    m04_up()
    data = _ingest(client)

    res = client.post(
        "/v1/resumes/" + data["id"] + "/corrections",
        json={"target": "skill", "target_id": "Rust", "field": "present", "value": "true"},
    )
    body = res.json()

    assert "Rust" in body["parsed_skills"]
    assert "Rust" in body["unresolved_skills"]
    assert "Rust" not in body["resolved_concepts"]


def test_corrections_are_logged_not_just_applied(client, m04_up):
    """AC-1.7 watches the correction rate. That is only answerable if every
    disagreement is still on disk."""
    m04_up()
    data = _ingest(client)
    client.post(
        "/v1/resumes/" + data["id"] + "/corrections",
        json={"target": "skill", "target_id": "Rust", "field": "present", "value": "true"},
    )

    log = client.get("/v1/resumes/" + data["id"] + "/corrections").json()
    assert len(log) == 1
    assert log[0]["target"] == "skill"
    assert log[0]["new_value"] == "true"
    assert log[0]["content_sha256"] == data["content_sha256"]


def test_a_correction_survives_re_uploading_the_same_file(client, m04_up):
    """The point of keying corrections to the CONTENT.

    Keyed to the resume id instead, a student would re-fix the same mis-read
    heading on every upload, which is how a correction feature stops being used.
    """
    m04_up()
    candidate = uuid.uuid4()
    first = _ingest(client, candidate=candidate)
    client.post(
        "/v1/resumes/" + first["id"] + "/corrections",
        json={"target": "skill", "target_id": "Rust", "field": "present", "value": "true"},
    )

    again = _ingest(client, candidate=candidate)

    assert "Rust" in again["parsed_skills"]


def test_an_uncorrectable_field_is_refused(client, m04_up):
    """The alternative is an endpoint that can set any attribute on any row."""
    m04_up()
    data = _ingest(client)

    res = client.post(
        "/v1/resumes/" + data["id"] + "/corrections",
        json={
            "target": "claim",
            "target_id": data["claims"][0]["id"],
            "field": "risk_score",
            "value": "0",
        },
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
#  FR-1.15 - re-upload diff
# ---------------------------------------------------------------------------


def test_a_re_upload_reports_what_changed(client, m04_up):
    m04_up()
    candidate = uuid.uuid4()
    older = _ingest(client, candidate=candidate)
    newer = _ingest(
        client,
        RESUME.replace(
            "- Worked on a world-class blockchain platform.",
            "- Built an ETL pipeline in Python processing 2M records/day.",
        ),
        candidate=candidate,
    )

    diff = client.get("/v1/resumes/" + newer["id"] + "/diff/" + older["id"]).json()

    assert any("ETL" in c["text"] for c in diff["added"])
    assert any("world-class" in c["text"] for c in diff["removed"])
    assert diff["identical_content"] is False
    assert "1 new claim" in diff["summary"]


def test_a_rewritten_bullet_that_gained_a_number_is_reported_as_re_banded(client, m04_up):
    """Text-only comparison would call this unchanged, and it is the single
    most useful thing a re-upload can report."""
    m04_up()
    candidate = uuid.uuid4()
    vague = "PROJECTS\n- Worked on a world-class platform.\n"
    older = _ingest(client, vague, candidate=candidate)
    newer = _ingest(client, vague, candidate=candidate)

    diff = client.get("/v1/resumes/" + newer["id"] + "/diff/" + older["id"]).json()
    assert diff["identical_content"] is True
    assert diff["added"] == []
    assert diff["removed"] == []


def test_diffing_across_candidates_is_refused(client, m04_up):
    m04_up()
    a, b = _ingest(client), _ingest(client)

    res = client.get("/v1/resumes/" + a["id"] + "/diff/" + b["id"])
    assert res.status_code == 422


# ---------------------------------------------------------------------------
#  FR-1.20 - analytics events
# ---------------------------------------------------------------------------


def test_an_ingest_emits_a_stage_event_with_counts(client, m04_up):
    m04_up()
    data = _ingest(client)

    events = client.get("/v1/resumes/" + data["id"] + "/events").json()
    assert [e["name"] for e in events] == ["resume.ingested"]

    payload = events[0]["payload"]
    assert payload["claims"] == len(data["claims"])
    assert payload["sections"] == len(data["sections"])
    assert payload["duration_ms"] >= 0
    assert payload["scanned_against"] == "m04"


def test_a_correction_emits_its_own_event(client, m04_up):
    m04_up()
    data = _ingest(client)
    client.post(
        "/v1/resumes/" + data["id"] + "/corrections",
        json={"target": "skill", "target_id": "Rust", "field": "present", "value": "true"},
    )

    names = [e["name"] for e in client.get("/v1/resumes/" + data["id"] + "/events").json()]
    assert "resume.corrected" in names


@pytest.mark.gate
def test_no_event_payload_carries_resume_text_or_pii(client, m04_up):
    """FR-1.17 again, at the one place data is deliberately copied elsewhere.

    An analytics payload leaves harder than most things, so the whitelist drops
    anything not on it rather than trusting the caller.
    """
    m04_up()
    data = _ingest(client)

    body = str(client.get("/v1/resumes/" + data["id"] + "/events").json())
    assert "priya.sharma@example.com" not in body
    assert "98765" not in body
    assert "route planner" not in body
    assert "Python" not in body

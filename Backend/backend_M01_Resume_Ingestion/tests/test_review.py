"""The resume review (`review.py`, 2026-10-04).

Three promises are pinned here, because each is what makes the review different
from the paid checkers it was asked to replace:

- It never gives a total. Counts only — §15 decision 1.
- A fix never adds a fact. It removes words, or it leaves a [blank] for a fact
  only the student has — §15 decision 2.
- An edit to a bullet is re-scored and shows in the document at once, which is
  what makes it a live editor rather than a report.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M01_Resume_Ingestion.app import app
from backend_M01_Resume_Ingestion.review import (
    BLANK,
    build_review,
    document_segments,
    takes_an,
    with_result_blank,
    with_strong_opener,
    without_filler,
    without_leading_i,
)
from backend_M01_Resume_Ingestion.router import get_db
from fastapi.testclient import TestClient

RESUME = """PRIYA SHARMA
priya.sharma@example.com | +91 98765 43210

EDUCATION
Amrita Vishwa Vidyapeetham, B.Tech CSE, 2022 - 2026, CGPA 8.1

EXPERIENCE
Software Engineering Intern, Acme Analytics, May 2025 - Jul 2025
- Worked on the payments service to improve performance.
- Built a Redis cache for the product catalogue, cutting p95 latency from 420 ms to 95 ms.

PROJECTS
- Developed a robust, scalable ride-matching platform for students.
- I built a geohash index so matching runs in O(log n) for 2,000+ riders.

SKILLS
Python, Redis, Kubernetes
"""


# ---------------------------------------------------------------------------
#  Fixes that only remove words, or leave a blank
# ---------------------------------------------------------------------------


def test_filler_goes_and_the_article_before_it_is_reconsidered():
    assert (
        without_filler("Developed a robust, scalable ride-matching platform.")
        == "Developed a ride-matching platform."
    )
    assert without_filler("Built a robust API for the team.") == "Built an API for the team."
    assert without_filler("Successfully shipped a robust, user-friendly app.") == "Shipped an app."


def test_an_article_the_student_wrote_is_never_touched():
    # Only the article that stood before a removed word is reconsidered —
    # "a university" and "a user" are the student's, and they are right.
    assert (
        without_filler("Built a seamless tool for a university and a user group.")
        == "Built a tool for a university and a user group."
    )


def test_a_or_an_by_sound():
    assert takes_an("API") and takes_an("SQL") and not takes_an("GPU")
    assert not takes_an("university") and not takes_an("user") and takes_an("hour")
    assert takes_an("efficient") and not takes_an("scalable")


def test_a_weak_opener_becomes_a_blank_not_a_guess():
    fixed = with_strong_opener("Worked on the payments service to improve performance.")
    assert fixed is not None
    assert fixed.endswith("the payments service to improve performance.")
    assert BLANK.search(fixed), "the student names the action; we do not"
    # The gerund left behind goes with the opener.
    gerund = with_strong_opener("Responsible for writing unit tests for modules.")
    assert gerund is not None and "writing" not in gerund
    assert with_strong_opener("Built a cache.") is None


def test_a_missing_number_is_a_blank_in_the_students_own_sentence():
    fixed = with_result_blank("Built a Redis cache for the catalogue.")
    assert fixed.startswith("Built a Redis cache for the catalogue,")
    assert len(BLANK.findall(fixed)) == 1


def test_a_hard_to_defend_line_keeps_its_own_words(client, m04_up):
    """The STAR skeleton threw the student's words away; the review keeps the
    sentence and adds a blank only for each part it is missing."""
    m04_up()
    review = _review(client, _ingest(client)["id"])
    for issue in _check(review, "risky")["issues"]:
        kept = BLANK.sub("", issue["suggestion"])
        # The end of the sentence always survives; only a weak opener is
        # replaced (by a blank), and that is the verbs check's job too.
        tail = " ".join(issue["original"].rstrip(".").split()[-4:])
        assert tail in kept, f"lost the student's words: {issue['suggestion']!r}"
        assert issue["blanks"] >= 1


def test_a_leading_i_is_dropped():
    assert without_leading_i("I built a parser in Rust.") == "Built a parser in Rust."


# ---------------------------------------------------------------------------
#  The review over a real ingest
# ---------------------------------------------------------------------------


def _ingest(client, text=RESUME):
    res = client.post(
        "/v1/resumes/ingest", json={"candidate_id": str(uuid.uuid4()), "raw_text": text}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _review(client, resume_id):
    res = client.get(f"/v1/resumes/{resume_id}/review")
    assert res.status_code == 200, res.text
    return res.json()


def _check(review, check_id):
    return next(c for c in review["checks"] if c["id"] == check_id)


def test_the_review_counts_and_never_totals(client, m04_up):
    m04_up()
    review = _review(client, _ingest(client)["id"])
    assert review["total"] == len(review["checks"]) >= 10
    assert review["passed"] == sum(1 for c in review["checks"] if c["passed"])
    assert review["open_issues"] == sum(len(c["issues"]) for c in review["checks"])
    # No score, under any name a screen could put in a ring.
    assert not {"score", "overall", "percent", "grade"} & set(review)


def test_each_check_finds_what_it_says(client, m04_up):
    m04_up()
    review = _review(client, _ingest(client)["id"])

    verbs = _check(review, "verbs")
    assert [i["original"] for i in verbs["issues"]] == [
        "Worked on the payments service to improve performance."
    ]
    assert verbs["issues"][0]["blanks"] >= 1

    filler = _check(review, "filler")
    assert filler["issues"], "robust and scalable are filler"
    assert filler["issues"][0]["suggestion"] == "Developed a ride-matching platform for students."
    assert filler["issues"][0]["blanks"] == 0, "removing words needs no blank"

    pronouns = _check(review, "pronouns")
    assert pronouns["issues"][0]["suggestion"].startswith("Built a geohash index")

    numbers = _check(review, "numbers")
    originals = {i["original"] for i in numbers["issues"]}
    assert "Worked on the payments service to improve performance." in originals
    assert not any("420 ms" in o for o in originals), "a bullet with a number passes"

    assert _check(review, "contact")["passed"], "email and phone are both on it"
    assert _check(review, "sections")["passed"]


def test_skills_listed_and_never_used_are_named(client, m04_up):
    m04_up()
    review = _review(client, _ingest(client)["id"])
    skills = _check(review, "skills_used")
    # One card for the lot, with every unused skill named in it.
    assert len(skills["issues"]) == 1
    named = {s.strip().casefold() for s in skills["issues"][0]["original"].split(",")}
    assert "kubernetes" in named, "Kubernetes is in the list and in no bullet"
    assert "redis" not in named, "Redis is used in the experience bullet"


def test_no_suggestion_invents_a_fact(client, m04_up):
    """Every suggestion either keeps the student's words with some removed, or
    marks the missing fact as a [blank]. None adds a digit that was not there."""
    m04_up()
    review = _review(client, _ingest(client)["id"])
    for check in review["checks"]:
        for issue in check["issues"]:
            suggestion = issue["suggestion"]
            if not suggestion:
                continue
            without_blanks = BLANK.sub("", suggestion)
            new_digits = set(filter(str.isdigit, without_blanks)) - set(
                filter(str.isdigit, issue["original"])
            )
            assert not new_digits, f"{check['id']} added {new_digits}: {suggestion!r}"


def test_an_applied_fix_is_rescored_and_shows_in_the_document(client, m04_up):
    m04_up()
    resume = _ingest(client)
    before = _review(client, resume["id"])
    issue = _check(before, "filler")["issues"][0]

    edited = client.patch(
        f"/v1/resumes/{resume['id']}/claims/{issue['claim_id']}",
        json={"field": "text", "value": issue["suggestion"]},
    )
    assert edited.status_code == 200, edited.text

    after = _review(client, resume["id"])
    assert not _check(after, "filler")["issues"], "the fix cleared the check"
    assert after["edited"] == 1
    segment = next(s for s in after["document"] if s["claim_id"] == issue["claim_id"])
    assert segment["edited"] and segment["text"] == issue["suggestion"]
    # The rest of the document is untouched, and still masked.
    assert "priya.sharma@example.com" not in "".join(s["text"] for s in after["document"])


def test_the_document_is_the_text_with_edits_in_place():
    text = "AB-claim-one-CD-claim-two-EF"
    claims = [
        {"id": "1", "text": "claim-one", "span": {"start": 3, "end": 12}},
        {
            "id": "2",
            "text": "CLAIM TWO, edited",
            "span": {"start": 16, "end": 25},
            "user_edited": True,
        },
    ]
    segments = document_segments(text, claims)
    assert "".join(s.text for s in segments) == "AB-claim-one-CD-CLAIM TWO, edited-EF"
    assert [s.claim_id for s in segments] == [None, "1", None, "2", None]
    assert [s.edited for s in segments if s.claim_id] == [False, True]


def test_a_missing_section_and_contact_are_issues():
    review = build_review(
        resume_id="r",
        filename=None,
        text="",
        sections=[{"id": "s1", "kind": "education"}],
        claims=[],
        red_flags=[],
        skill_mentions=[],
        has_original=False,
        contact={"email": True, "phone": False},
    )
    sections = next(c for c in review.checks if c.id == "sections")
    assert {i.id for i in sections.issues} == {"sections:work", "sections:skills"}
    contact = next(c for c in review.checks if c.id == "contact")
    assert [i.id for i in contact.issues] == ["contact:phone"]


@pytest.fixture(name="as_student")
def as_student_fixture(session):
    """A client that is one named student and nobody else (as in test_access)."""

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    def _client(candidate_id: str) -> TestClient:
        return TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(candidate_id)})

    yield _client
    app.dependency_overrides.clear()


def test_a_stranger_cannot_read_someone_elses_review(as_student, m04_up):
    m04_up()
    owner = str(uuid.uuid4())
    created = as_student(owner).post(
        "/v1/resumes/from-text", json={"candidate_id": owner, "raw_text": RESUME}
    )
    assert created.status_code == 201, created.text
    resume_id = created.json()["id"]
    assert as_student(owner).get(f"/v1/resumes/{resume_id}/review").status_code == 200
    stranger = as_student(str(uuid.uuid4())).get(f"/v1/resumes/{resume_id}/review")
    assert stranger.status_code == 403

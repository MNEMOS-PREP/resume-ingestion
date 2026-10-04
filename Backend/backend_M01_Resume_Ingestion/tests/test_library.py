"""The student's library (`library.py`, 2026-10-04).

Two requests, pinned together because one structure answers both:

- Deleting a resume removes the document and its analysis — NOT the projects,
  skills, achievements and certifications in it. Those are the student's record
  of progress.
- Editing a line or starting a new resume means picking from what the student
  already wrote. So the library holds their items, cleaned, titled and kept up
  to date with the wording they improved.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M01_Resume_Ingestion.app import app
from backend_M01_Resume_Ingestion.library import clean
from backend_M01_Resume_Ingestion.models import LibraryItem, LibrarySynced
from backend_M01_Resume_Ingestion.router import get_db
from fastapi.testclient import TestClient
from sqlmodel import select

RESUME = """ASHA VERMA
asha.verma@example.com | +91 91234 56789

EDUCATION
B.Tech in Computer Science 2022 – 2026
Amrita Vishwa Vidyapeetham, Coimbatore
CGPA: 8.7 / 10

EXPERIENCE
Machine Learning Intern Jan 2025 – Mar 2025
Acme Analytics, Bengaluru
- Built a churn model in Python for 40,000 customers, lifting retention 6%.
- Wrote a feature store on Redis that cut training time from 3 hours to 40 minutes.

PROJECTS
Campus Ride Share
- Built a geohash index so matching runs in O(log n) for 2,000+ riders.
Exam Planner
- Developed a scheduler in C that resolved 300 timetable clashes.

ACHIEVEMENTS & CERTIFICATIONS
- Ranked 12th of 900 teams at Smart India Hackathon 2024 [Certificate]
- AWS Certified Cloud Practitioner (2024) [Badge]

SKILLS
Languages: Python, C, SQL
Machine Learning: PyTorch, Scikit-learn, Multi-
modal Learning
Tools: Redis, Docker
"""

#: The same student, a later version: one project gone, one line reworded.
LATER = RESUME.replace(
    "Exam Planner\n- Developed a scheduler in C that resolved 300 timetable clashes.\n", ""
).replace("lifting retention 6%", "lifting 90-day retention by 6 points")


def _ingest(client, candidate_id: str, text: str = RESUME) -> dict:
    res = client.post("/v1/resumes/ingest", json={"candidate_id": candidate_id, "raw_text": text})
    assert res.status_code == 201, res.text
    return res.json()


def _library(client, candidate_id: str) -> list[dict]:
    res = client.get(f"/v1/resumes/candidate/{candidate_id}/library")
    assert res.status_code == 200, res.text
    return res.json()["items"]


def _of(items: list[dict], kind: str) -> list[dict]:
    return [i for i in items if i["kind"] == kind]


def _texts(items: list[dict], kind: str) -> list[str]:
    return [i["text"] for i in _of(items, kind)]


# ---------------------------------------------------------------------------
#  What an upload puts in
# ---------------------------------------------------------------------------


def test_an_upload_fills_the_library_with_every_kind(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    items = _library(client, candidate)

    assert any(t.startswith("Built a churn model") for t in _texts(items, "experience"))
    assert any(t.startswith("Built a geohash index") for t in _texts(items, "project"))
    assert any(t.startswith("Developed a scheduler in C") for t in _texts(items, "project"))
    assert _texts(items, "achievement") == [
        "Ranked 12th of 900 teams at Smart India Hackathon 2024"
    ]
    assert _texts(items, "certification") == ["AWS Certified Cloud Practitioner (2024)"]
    (education,) = _texts(items, "education")
    assert "Amrita Vishwa Vidyapeetham" in education
    # A grade on a line of its own is the degree's grade.
    assert "CGPA: 8.7 / 10" in education


def test_a_line_keeps_the_title_it_sat_under(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    items = _library(client, candidate)

    def title(start: str) -> str:
        return next(i["context"] for i in items if i["text"].startswith(start))

    assert title("Built a geohash index").startswith("Campus Ride Share")
    assert title("Developed a scheduler").startswith("Exam Planner")
    # A role and its employer on two lines are one title.
    churn = title("Built a churn model")
    assert "Machine Learning Intern" in churn and "Acme Analytics" in churn


def test_skills_are_read_off_the_list_labels_and_wraps_included(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    skills = _texts(_library(client, candidate), "skill")
    for name in ("Python", "C", "SQL", "PyTorch", "Multi-modal Learning", "Redis", "Docker"):
        assert name in skills, f"{name} missing from {skills}"
    # The category label is not a skill; the same skill twice is one item.
    assert "Languages" not in skills and "Tools" not in skills
    assert skills.count("Python") == 1


def test_nothing_personal_becomes_an_item(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    everything = " ".join(i["text"] + " " + i["context"] for i in _library(client, candidate))
    assert "asha.verma@example.com" not in everything
    assert "91234" not in everything
    assert "█" not in everything


def test_an_item_reads_the_way_it_should_be_pasted():
    # A ligature from the PDF, a link's leftover label, an echoed text box.
    assert clean("Designed an EﬀicientNet pipeline [GitHub]") == "Designed an EfficientNet pipeline"
    assert (
        clean(
            "Oracle AI Foundations Associate (2025) [Badge] | Foundations Associate (2025) [Badge]"
        )
        == "Oracle AI Foundations Associate (2025)"
    )
    assert clean("Cortexa: Agentic Platform | ████████") == "Cortexa: Agentic Platform"
    # A word the page broke at its hyphen is one word again; a hyphen the
    # student meant is left alone.
    assert clean("radiomics- guided feature fusion") == "radiomics-guided feature fusion"
    assert clean("pre- and post-processing") == "pre- and post-processing"
    # A blank the student has not filled is lower-case and long; it stays.
    assert "[the result" in clean("Built X, [the result, with a number].")


# ---------------------------------------------------------------------------
#  Deleting a resume keeps its items
# ---------------------------------------------------------------------------


def test_deleting_a_resume_keeps_its_items_and_where_they_came_from(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    resume = _ingest(client, candidate)
    before = _library(client, candidate)
    assert before

    assert client.delete(f"/v1/resumes/{resume['id']}").status_code == 204
    assert client.get(f"/v1/resumes/candidate/{candidate}").json() == []

    after = _library(client, candidate)
    assert [i["text"] for i in after] == [i["text"] for i in before]
    # "It was on the August version" stays part of the record.
    assert all(resume["id"] in i["sources"] for i in after)


def test_a_resume_from_before_the_library_is_read_in_before_it_goes(client, session, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    resume = _ingest(client, candidate)
    # As if it had been uploaded before the library existed.
    for row in session.exec(select(LibraryItem)).all():
        session.delete(row)
    for row in session.exec(select(LibrarySynced)).all():
        session.delete(row)
    session.commit()

    assert client.delete(f"/v1/resumes/{resume['id']}").status_code == 204
    assert _texts(_library(client, candidate), "certification") == [
        "AWS Certified Cloud Practitioner (2024)"
    ]


def test_a_resume_from_before_the_library_is_read_in_when_it_opens(client, session, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    for row in session.exec(select(LibraryItem)).all():
        session.delete(row)
    for row in session.exec(select(LibrarySynced)).all():
        session.delete(row)
    session.commit()

    assert _texts(_library(client, candidate), "certification") == [
        "AWS Certified Cloud Practitioner (2024)"
    ]


def test_deleting_the_active_resume_makes_the_newest_remaining_one_active(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    first = _ingest(client, candidate)
    second = _ingest(client, candidate, LATER)
    listed = {r["id"]: r for r in client.get(f"/v1/resumes/candidate/{candidate}").json()}
    assert listed[second["id"]]["is_active"] and not listed[first["id"]]["is_active"]

    assert client.delete(f"/v1/resumes/{second['id']}").status_code == 204
    (remaining,) = client.get(f"/v1/resumes/candidate/{candidate}").json()
    assert remaining["id"] == first["id"] and remaining["is_active"]


def test_a_failed_upload_never_becomes_the_current_resume(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    good = _ingest(client, candidate)
    second = _ingest(client, candidate, LATER)
    failed = client.post(
        "/v1/resumes",
        data={"candidate_id": candidate},
        files={"file": ("cv.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "")},
    )
    assert failed.status_code == 415

    assert client.delete(f"/v1/resumes/{second['id']}").status_code == 204
    active = [r for r in client.get(f"/v1/resumes/candidate/{candidate}").json() if r["is_active"]]
    assert [r["id"] for r in active] == [good["id"]]


def test_uploading_an_older_version_again_makes_it_current(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    first = _ingest(client, candidate)
    _ingest(client, candidate, LATER)
    again = _ingest(client, candidate)
    assert again["id"] == first["id"], "the same document is the same row (EC-1.8)"
    active = [
        r["id"] for r in client.get(f"/v1/resumes/candidate/{candidate}").json() if r["is_active"]
    ]
    assert active == [first["id"]]


def test_two_versions_are_one_library(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    first = _ingest(client, candidate)
    second = _ingest(client, candidate, LATER)
    items = _library(client, candidate)
    geohash = next(i for i in items if i["text"].startswith("Built a geohash index"))
    # On both versions: one item, two sources.
    assert set(geohash["sources"]) == {first["id"], second["id"]}
    # The project the later version dropped is still the student's.
    assert any(t.startswith("Developed a scheduler in C") for t in _texts(items, "project"))
    assert len([t for t in _texts(items, "skill") if t == "Python"]) == 1


# ---------------------------------------------------------------------------
#  The student's own changes
# ---------------------------------------------------------------------------


def test_a_line_improved_on_the_review_page_is_improved_in_the_library(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    resume = _ingest(client, candidate)
    claim = next(c for c in resume["claims"] if c["text"].startswith("Built a churn model"))
    better = (
        "Built a churn model in Python for 40,000 customers, lifting 90-day retention by 6 points."
    )
    res = client.patch(
        f"/v1/resumes/{resume['id']}/claims/{claim['id']}", json={"field": "text", "value": better}
    )
    assert res.status_code == 200, res.text

    experience = _of(_library(client, candidate), "experience")
    texts = [i["text"] for i in experience]
    assert better in texts
    assert not any("lifting retention 6%" in t for t in texts), "the old wording stayed"
    improved = next(i for i in experience if i["text"] == better)
    assert improved["user_written"]
    assert "Acme Analytics" in improved["context"]


def test_a_student_adds_what_no_resume_says_yet(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    url = f"/v1/resumes/candidate/{candidate}/library"
    added = client.post(
        url, json={"kind": "certification", "text": "  TensorFlow Developer Certificate (2026) "}
    )
    assert added.status_code == 201, added.text
    item = added.json()
    assert item["text"] == "TensorFlow Developer Certificate (2026)"
    assert item["user_written"] and item["sources"] == []

    again = client.post(
        url, json={"kind": "certification", "text": "tensorflow developer certificate (2026)"}
    )
    assert again.json()["id"] == item["id"], "the same thing twice is one item"
    assert len(_library(client, candidate)) == 1


def test_a_student_rewords_retitles_and_moves_an_item(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    item = next(i for i in _library(client, candidate) if i["kind"] == "achievement")
    url = f"/v1/resumes/candidate/{candidate}/library/{item['id']}"
    res = client.patch(url, json={"text": "Ranked 12th of 900 teams, Smart India Hackathon 2024"})
    assert res.status_code == 200, res.text
    assert res.json()["user_written"]
    moved = client.patch(url, json={"kind": "certification"}).json()
    assert moved["kind"] == "certification"


def test_rewording_into_an_item_already_there_merges_them(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    url = f"/v1/resumes/candidate/{candidate}/library"
    one = client.post(url, json={"kind": "skill", "text": "Postgres"}).json()
    client.post(url, json={"kind": "skill", "text": "PostgreSQL"})
    merged = client.patch(f"{url}/{one['id']}", json={"text": "PostgreSQL"})
    assert merged.status_code == 200
    assert _texts(_library(client, candidate), "skill") == ["PostgreSQL"]


def test_a_removed_item_stays_removed_until_a_new_upload_says_it(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    item = next(
        i for i in _library(client, candidate) if i["text"].startswith("Developed a scheduler")
    )
    url = f"/v1/resumes/candidate/{candidate}/library/{item['id']}"
    assert client.delete(url).status_code == 204

    # The same document again is not a new upload (EC-1.8): it is not read twice.
    _ingest(client, candidate)
    assert not any(
        t.startswith("Developed a scheduler")
        for t in _texts(_library(client, candidate), "project")
    )

    # A new version that still lists it is new evidence, and brings it back.
    _ingest(client, candidate, RESUME + "\nInterests: chess\n")
    assert any(
        t.startswith("Developed a scheduler")
        for t in _texts(_library(client, candidate), "project")
    )


def test_a_resume_built_from_the_library_adds_nothing_new_to_it(client, m04_up):
    """Library → "Build a new resume" → checked as a resume → library: the same
    items, each now with one more source. A near-copy (a grade without its
    "/ 10") would make the library grow every time it was used."""
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    before = _library(client, candidate)

    composed = ["EDUCATION", *_texts(before, "education"), ""]
    for kind, heading in (("experience", "EXPERIENCE"), ("project", "PROJECTS")):
        composed.append(heading)
        last = None
        for item in _of(before, kind):
            if item["context"] != last:
                composed.append(item["context"])
                last = item["context"]
            composed.append(f"- {item['text']}")
        composed.append("")
    composed += ["ACHIEVEMENTS", *(f"- {t}" for t in _texts(before, "achievement")), ""]
    composed += ["CERTIFICATIONS", *(f"- {t}" for t in _texts(before, "certification")), ""]
    composed += ["SKILLS", ", ".join(_texts(before, "skill"))]
    _ingest(client, candidate, "\n".join(composed))

    after = _library(client, candidate)
    assert sorted((i["kind"], i["text"]) for i in after) == sorted(
        (i["kind"], i["text"]) for i in before
    )


def test_clearing_the_library_is_not_undone_by_opening_it(client, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    _ingest(client, candidate)
    assert client.delete(f"/v1/resumes/candidate/{candidate}/library").status_code == 204
    assert _library(client, candidate) == []


# ---------------------------------------------------------------------------
#  Whose it is
# ---------------------------------------------------------------------------


@pytest.fixture(name="as_student")
def as_student_fixture(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    def _client(candidate_id: str) -> TestClient:
        return TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(candidate_id)})

    yield _client
    app.dependency_overrides.clear()


def test_a_stranger_cannot_read_or_change_someone_elses_library(as_student, m04_up):
    m04_up()
    owner, stranger = str(uuid.uuid4()), str(uuid.uuid4())
    _ingest(as_student(owner), owner)
    items = _library(as_student(owner), owner)
    target = items[0]["id"]

    assert as_student(stranger).get(f"/v1/resumes/candidate/{owner}/library").status_code == 403
    # Their own library's address with someone else's item: not found, and
    # nothing changes.
    own_url = f"/v1/resumes/candidate/{stranger}/library/{target}"
    assert as_student(stranger).patch(own_url, json={"text": "mine now"}).status_code == 404
    assert as_student(stranger).delete(own_url).status_code == 404
    assert _library(as_student(owner), owner)[0]["text"] == items[0]["text"]

"""Who may read whose resume (Platform_Core `ai_core.identity`).

Every other test file in this module runs as an admin, on purpose — they are
about parsing, scoring and provenance, and putting authorisation scaffolding in
two hundred of them would mean the first person to get it slightly wrong
"fixes" it by weakening the check. This is the file that sends real student
principals, and it is the only one that should.

── What was true until now ─────────────────────────────────────────────────────

Nothing. `candidate_id` arrived from the caller and was trusted, so changing a
UUID in a URL returned another student's resume, their claims, and — through
`GET /contact` — their name, email and phone number. That route has its own
audit tag *specifically* so "who saw this student's phone number" is
answerable, and the answer was "anyone who guessed a UUID".
"""

from __future__ import annotations

import uuid

import pytest
from backend_M01_Resume_Ingestion.app import app
from backend_M01_Resume_Ingestion.router import get_db
from fastapi.testclient import TestClient

RESUME = """PRIYA SHARMA
priya.sharma@example.com | +91 98765 43210

PROJECTS
- Built a route planner in Python using dynamic programming.
"""


@pytest.fixture(name="as_student")
def as_student_fixture(session):
    """A client that is one named student and nobody else."""

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    def _client(candidate_id: str) -> TestClient:
        return TestClient(
            app, headers={"X-Role": "student", "X-Candidate-Id": str(candidate_id)}
        )

    yield _client
    app.dependency_overrides.clear()


@pytest.fixture(name="anonymous")
def anonymous_fixture(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _own_resume(as_student, candidate_id: str) -> str:
    res = as_student(candidate_id).post(
        "/v1/resumes/from-text",
        json={"candidate_id": candidate_id, "raw_text": RESUME},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ---------------------------------------------------------------------------
#  A student and their own record
# ---------------------------------------------------------------------------


def test_a_student_can_read_their_own_resume(as_student, m04_up):
    m04_up()
    me = str(uuid.uuid4())
    resume_id = _own_resume(as_student, me)

    assert as_student(me).get(f"/v1/resumes/{resume_id}").status_code == 200


# ---------------------------------------------------------------------------
#  The attack that worked yesterday
# ---------------------------------------------------------------------------


@pytest.mark.gate
@pytest.mark.parametrize(
    "path",
    [
        "/v1/resumes/{rid}",
        "/v1/resumes/{rid}/claims",
        "/v1/resumes/{rid}/red-flags",
        "/v1/resumes/{rid}/skills",
        # The sharpest one. Name, email, phone.
        "/v1/resumes/{rid}/contact",
        "/v1/resumes/{rid}/corrections",
        "/v1/resumes/{rid}/events",
        "/v1/resumes/{rid}/stream",
    ],
)
def test_changing_the_uuid_in_the_url_no_longer_works(as_student, m04_up, path):
    """The whole hole, on every route that used to have it.

    Parametrised rather than written once because the failure this guards
    against is a route being ADDED without the check — and a router-level
    dependency is what makes that impossible, so this asserts the dependency is
    still there rather than that eight handlers each remembered.
    """
    m04_up()
    victim = str(uuid.uuid4())
    attacker = str(uuid.uuid4())
    resume_id = _own_resume(as_student, victim)

    res = as_student(attacker).get(path.format(rid=resume_id))

    assert res.status_code == 403, f"{path} leaked to another student"
    assert "not your record" in res.json()["detail"]


@pytest.mark.gate
def test_a_student_cannot_list_another_students_resumes(as_student, m04_up):
    """The path names the candidate directly rather than a resume."""
    m04_up()
    victim = str(uuid.uuid4())
    _own_resume(as_student, victim)

    res = as_student(str(uuid.uuid4())).get(f"/v1/resumes/candidate/{victim}")

    assert res.status_code == 403


@pytest.mark.gate
def test_a_student_cannot_write_to_another_students_resume(as_student, m04_up):
    """Reads are the obvious half. A correction, a deletion or a share grant
    on somebody else's resume is the more surprising one."""
    m04_up()
    victim = str(uuid.uuid4())
    resume_id = _own_resume(as_student, victim)
    attacker = as_student(str(uuid.uuid4()))

    assert attacker.post(f"/v1/resumes/{resume_id}/confirm").status_code == 403
    assert attacker.delete(f"/v1/resumes/{resume_id}").status_code == 403
    assert (
        attacker.post(
            f"/v1/resumes/{resume_id}/share", json={"grantee": "me", "days": 90}
        ).status_code
        == 403
    )


@pytest.mark.gate
def test_a_student_cannot_upload_a_resume_as_somebody_else(as_student, m04_up):
    """The one check the router-level dependency cannot make.

    `candidate_id` arrives in the BODY here, which a dependency reading
    `request.path_params` cannot see — so `_ingest` checks it, at the only
    place both entry points pass through. Without it this is a WRITE leak, and
    the resume would then legitimately belong to the victim.
    """
    m04_up()
    victim = str(uuid.uuid4())

    res = as_student(str(uuid.uuid4())).post(
        "/v1/resumes/from-text",
        json={"candidate_id": victim, "raw_text": RESUME},
    )

    assert res.status_code == 403


# ---------------------------------------------------------------------------
#  Anonymous
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_anonymous_gets_nothing_and_is_told_why(as_student, anonymous, m04_up):
    """Fail closed, and loudly.

    Not an empty list — that is the failure mode that survives review, because
    it looks exactly like a student who has not uploaded anything yet.
    """
    m04_up()
    victim = str(uuid.uuid4())
    resume_id = _own_resume(as_student, victim)

    res = anonymous.get(f"/v1/resumes/{resume_id}")

    assert res.status_code == 403
    assert "signed in" in res.json()["detail"]


# ---------------------------------------------------------------------------
#  What stays open, and why that is correct
# ---------------------------------------------------------------------------


def test_the_deployment_routes_are_not_candidate_scoped(anonymous):
    """`/deps`, `/capabilities` and `/quality` are about this DEPLOYMENT.

    `/quality` is aggregate by construction — counts, rates and failure codes,
    with nobody named — which is exactly what §15 decision 4 proposes staff
    should see by default. Gating it would make an operator log in to find out
    whether the parser is working.
    """
    assert anonymous.get("/v1/capabilities").status_code == 200
    assert anonymous.get("/v1/deps").status_code == 200
    assert anonymous.get("/v1/quality").status_code == 200
    assert anonymous.get("/health").status_code == 200

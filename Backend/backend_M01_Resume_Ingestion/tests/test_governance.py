"""Retention, disclosure and the object store (§15 decisions 3–4, FR-1.2).

Two of these are **decisions nobody has made yet**, and that is the point. A
system with no retention mechanism has decided "keep it forever"; one with no
share gate has decided "anyone may look". Building the mechanism before the
decision is what stops the default from being the answer.

So what is tested here is the SHAPE, and specifically that it fails closed.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from backend_M01_Resume_Ingestion import objectstore, retention
from backend_M01_Resume_Ingestion.retention import Disclosure, ShareGrant


def _ingest(client, text="PROJECTS\n- Built a route planner in Python.\n", candidate=None):
    res = client.post(
        "/v1/resumes/from-text",
        json={"candidate_id": str(candidate or uuid.uuid4()), "raw_text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
#  §15 decision 4 — who sees a student's claims
# ---------------------------------------------------------------------------


def test_a_viewer_with_no_grant_sees_aggregate_only(client, m04_up):
    """The default, and it is the safe one rather than the convenient one.

    §15's proposal is "aggregate only by default; individual view requires the
    student's explicit share". A default that fails open would decide the
    question by accident, before the placement cell has been asked.
    """
    m04_up()
    data = _ingest(client)

    body = client.get(f"/v1/resumes/{data['id']}/disclosure?viewer=officer-7").json()

    assert body["disclosure"] == Disclosure.aggregate_only.value
    assert body["may_see_individual_claims"] is False


def test_a_student_always_sees_their_own(client, m04_up):
    m04_up()
    candidate = uuid.uuid4()
    data = _ingest(client, candidate=candidate)

    body = client.get(f"/v1/resumes/{data['id']}/disclosure?viewer={candidate}").json()
    assert body["disclosure"] == Disclosure.self_access.value


def test_a_share_opens_it_and_a_revoke_closes_it(client, m04_up):
    m04_up()
    data = _ingest(client)
    resume_id = data["id"]

    client.post(f"/v1/resumes/{resume_id}/share", json={"grantee": "officer-7", "days": 90})
    granted = client.get(f"/v1/resumes/{resume_id}/disclosure?viewer=officer-7").json()
    assert granted["disclosure"] == Disclosure.shared_by_student.value

    assert client.delete(f"/v1/resumes/{resume_id}/share/officer-7").json()["revoked"] == 1
    revoked = client.get(f"/v1/resumes/{resume_id}/disclosure?viewer=officer-7").json()
    assert revoked["disclosure"] == Disclosure.aggregate_only.value


def test_a_grant_is_to_one_person_not_to_everyone(client, m04_up):
    """A boolean on the resume cannot express this, which is why it is a row."""
    m04_up()
    data = _ingest(client)
    client.post(f"/v1/resumes/{data['id']}/share", json={"grantee": "officer-7"})

    other = client.get(f"/v1/resumes/{data['id']}/disclosure?viewer=officer-9").json()
    assert other["disclosure"] == Disclosure.aggregate_only.value


def test_a_grant_expires():
    """ "I shared it for the placement drive" is not "for ever"."""
    past = ShareGrant(
        resume_id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        grantee="officer-7",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    assert past.active() is False

    live = ShareGrant(
        resume_id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        grantee="officer-7",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    assert live.active() is True


def test_a_revoked_grant_keeps_its_trace(client, m04_up, session):
    """Recorded, not deleted.

    A student who shared and then withdrew has a right to know it was
    withdrawn, and a row removed from the table cannot tell them that.
    """
    from sqlmodel import select

    m04_up()
    data = _ingest(client)
    client.post(f"/v1/resumes/{data['id']}/share", json={"grantee": "officer-7"})
    client.delete(f"/v1/resumes/{data['id']}/share/officer-7")

    grants = session.exec(select(ShareGrant)).all()
    assert len(grants) == 1
    assert grants[0].revoked_at is not None


# ---------------------------------------------------------------------------
#  §15 decision 3 — how long the artifact is kept
# ---------------------------------------------------------------------------


def test_the_retention_policy_is_readable_not_buried(client, m04_up):
    """ "How long do you keep my resume?" is a question a student is entitled to
    ask, and an answer that requires reading the source is not an answer."""
    m04_up()
    data = _ingest(client)

    policy = client.get(f"/v1/resumes/{data['id']}/disclosure?viewer=x").json()["retention"]

    assert policy["retention_days"] > 0
    assert policy["deletable_on_request"] is True
    # Honest about its own status: the ethics committee has not signed this off.
    assert policy["decided"] is False
    assert "ethics" in policy["rationale"] or "§15" in policy["rationale"]


def test_expiry_is_computed_from_the_creation_date():
    created = date(2026, 1, 1)
    assert retention.expires_on(created, days=30) == date(2026, 1, 31)
    assert retention.is_expired(created, today=date(2026, 2, 1), days=30) is True
    assert retention.is_expired(created, today=date(2026, 1, 15), days=30) is False


def test_expiry_is_a_tombstone_not_a_silent_delete(client, m04_up):
    """`ai_core.evidence` separates "deleted on purpose" from "never existed"
    precisely so a student's past scores do not rewrite themselves when a
    retention job runs. The policy says which one expiry is."""
    m04_up()
    data = _ingest(client)
    policy = client.get(f"/v1/resumes/{data['id']}/disclosure?viewer=x").json()["retention"]

    assert policy["expiry_is_a_tombstone"] is True


# ---------------------------------------------------------------------------
#  FR-1.2 — the object store seam
# ---------------------------------------------------------------------------


def test_the_local_store_is_the_default(monkeypatch):
    monkeypatch.delenv("M01_OBJECT_STORE", raising=False)
    assert objectstore.configured() is False
    assert objectstore.from_env() is None


def test_a_misconfigured_store_falls_back_rather_than_refusing_to_start(monkeypatch):
    """An operator who set three of the four variables should get a working
    module and a loud log, not a platform that will not boot. The local store
    is a correct fallback and every artifact in it is still content-addressed.
    """
    monkeypatch.setenv("M01_OBJECT_STORE", "s3")
    monkeypatch.delenv("M01_S3_BUCKET", raising=False)

    assert objectstore.configured() is True
    assert objectstore.from_env() is None


def test_the_virus_scan_gap_is_reported_not_stubbed(client):
    """§6.1 asks for a ClamAV pass before parsing. There is not one.

    A stubbed `scanned: true` on a file nothing scanned is worse than the
    honest absence, because it is the flag somebody later trusts.
    """
    assert objectstore.scan_required() is True
    assert client.get("/v1/quality").json()["virus_scan"] is False


def test_the_quality_report_says_which_store_is_in_use(client):
    body = client.get("/v1/quality").json()
    assert body["object_store"] in {"local", "s3"}
    assert "retention" in body

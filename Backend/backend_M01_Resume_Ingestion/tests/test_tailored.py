"""Tailored copies (`tailor.py`, `tailored_api.py`, 2026-11-17).

What is pinned here is what a student would lose trust over:

- The resume they uploaded never changes, whatever they do to a copy.
- Two copies for two jobs never touch each other.
- Every change is a revision, and any revision can be brought back.
- The PDF is generated from the latest revision; the student's own download
  prints their contact details and nothing else ever does.
- A reworded line never gains a number, or a tool, the line did not have.
"""

from __future__ import annotations

import uuid

import pytest
from backend_M01_Resume_Ingestion import llm, tailor
from backend_M01_Resume_Ingestion.app import app
from backend_M01_Resume_Ingestion.rewrite import new_terms, reword_for_requirement
from backend_M01_Resume_Ingestion.router import get_db
from backend_M01_Resume_Ingestion.tailored_api import safe_filename
from fastapi.testclient import TestClient

pymupdf = pytest.importorskip("pymupdf")

RESUME = """PRIYA SHARMA
priya.sharma@example.com | +91 98765 43210

SUMMARY
Final-year CSE student who builds backend services and likes measuring
what they change.

EDUCATION
B.Tech in Computer Science 2022 – 2026
Amrita Vishwa Vidyapeetham, Kollam
CGPA: 8.1 / 10

EXPERIENCE
Software Engineering Intern May 2025 – Jul 2025
Acme Analytics, Bengaluru
- Worked on the payments service to improve performance.
- Built a Redis cache for the product catalogue, cutting p95 latency from 420 ms
  to 95 ms.

PROJECTS
Ride Match | Course project
- Developed a ride-matching platform for students using Python and Flask.
- Wrote a geohash index so matching runs in O(log n) for 2,000+ riders.
Notes Search
- Indexed 10,000 lecture notes with Elasticsearch for full-text search.

SKILLS
Languages: Python, Java, SQL
Tools: Redis, Flask, Git
"""


def _ingest(client: TestClient, candidate: str | None = None) -> dict:
    candidate = candidate or str(uuid.uuid4())
    res = client.post("/v1/resumes/from-text", json={"candidate_id": candidate, "raw_text": RESUME})
    assert res.status_code == 201, res.text
    return res.json()


def _copy(client: TestClient, resume_id: str, target: str = "jd-1") -> dict:
    res = client.post(
        f"/v1/resumes/{resume_id}/tailored",
        json={"label": "Acme · SDE", "target_kind": "jd", "target_ref": target},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _block(copy: dict, kind: str, contains: str) -> dict:
    return next(b for b in copy["blocks"] if b["kind"] == kind and contains in b["text"])


# ---------------------------------------------------------------------------
#  The page's text, made readable
# ---------------------------------------------------------------------------


def test_a_typesetters_hyphen_is_joined_and_a_real_one_kept():
    assert tailor.flatten("semantic conflict detec-\n      tion, and")[0] == (
        "semantic conflict detection, and"
    )
    assert (
        tailor.flatten("a persistence-\n   aware framework")[0] == "a persistence-aware framework"
    )
    assert tailor.flatten("risk pre-\n  diction")[0] == "risk prediction"
    assert tailor.flatten("re-\n  engineered")[0] == "re-engineered"


def test_ligatures_become_letters_and_the_map_still_points_home():
    text, index = tailor.flatten("Eﬀicient  Net")
    assert text == "Efficient Net"
    assert len(index) == len(text)
    assert index[1] == index[2] == 1  # both f's came from the one ligature


def test_masked_text_is_restored_only_from_the_same_offsets():
    raw = "PRIYA\npriya@example.com | 98765"
    red = "PRIYA\n█████████████████ | █████"
    assert tailor.revealed_from(red, raw, (6, len(raw))) == "priya@example.com | 98765"


# ---------------------------------------------------------------------------
#  Making a copy
# ---------------------------------------------------------------------------


def test_a_copy_is_the_whole_document_as_blocks(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])

    kinds = [b["kind"] for b in copy["blocks"]]
    assert kinds[0] == "name" and copy["name"] == "PRIYA SHARMA"
    assert "heading" in kinds and "bullet" in kinds and "entry" in kinds

    role = _block(copy, "entry", "Software Engineering Intern")
    assert role["aside"] == "May 2025 – Jul 2025"
    cache = _block(copy, "bullet", "Redis cache")
    assert "\n" not in cache["text"] and cache["claim_id"]
    # The contact line is locked: masked on screen, so it cannot be retyped.
    contact = next(b for b in copy["blocks"] if b["kind"] == "contact")
    assert contact["masked"] and contact["locked"]
    assert copy["edited"] == 0 and copy["revision"] == 0


def test_asking_twice_for_the_same_job_returns_the_same_copy(client, m04_up):
    m04_up()
    resume = _ingest(client)
    first = _copy(client, resume["id"], "jd-1")
    again = _copy(client, resume["id"], "jd-1")
    other = _copy(client, resume["id"], "jd-2")
    assert again["id"] == first["id"]
    assert other["id"] != first["id"]


# ---------------------------------------------------------------------------
#  Changes
# ---------------------------------------------------------------------------


def test_editing_a_copy_never_touches_the_resume_or_another_copy(client, m04_up):
    m04_up()
    resume = _ingest(client)
    one = _copy(client, resume["id"], "jd-1")
    two = _copy(client, resume["id"], "jd-2")
    weak = _block(one, "bullet", "Worked on the payments")

    res = client.patch(
        f"/v1/resumes/{resume['id']}/tailored/{one['id']}/blocks/{weak['id']}",
        json={"text": "Improved the payments service's performance.", "source": "jd:abc"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["revision"] == 1 and res.json()["edited"] == 1

    untouched = client.get(f"/v1/resumes/{resume['id']}").json()
    assert untouched["redacted_text"] == resume["redacted_text"]
    assert untouched["claims"] == resume["claims"]

    other = client.get(f"/v1/resumes/{resume['id']}/tailored/{two['id']}").json()
    assert _block(other, "bullet", "payments")["text"].startswith("Worked on")


def test_a_contact_line_or_a_blank_is_refused_with_a_reason(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    base = f"/v1/resumes/{resume['id']}/tailored/{copy['id']}/blocks"
    contact = next(b for b in copy["blocks"] if b["kind"] == "contact")
    bullet = _block(copy, "bullet", "Worked on")

    locked = client.patch(f"{base}/{contact['id']}", json={"text": "someone@else.com"})
    assert locked.status_code == 422 and "contact" in locked.json()["detail"]

    blank = client.patch(f"{base}/{bullet['id']}", json={"text": "Cut latency by [how much]."})
    assert blank.status_code == 422 and "blank" in blank.json()["detail"]


def test_two_tabs_cannot_overwrite_each_other(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    url = (
        f"/v1/resumes/{resume['id']}/tailored/{copy['id']}/blocks/"
        + (_block(copy, "bullet", "Worked on")["id"])
    )
    assert client.patch(url, json={"text": "First edit.", "expect_revision": 0}).status_code == 200
    stale = client.patch(url, json={"text": "Second edit.", "expect_revision": 0})
    assert stale.status_code == 409


def test_every_change_is_a_revision_and_any_can_come_back(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    base = f"/v1/resumes/{resume['id']}/tailored/{copy['id']}"
    bullet = _block(copy, "bullet", "Worked on")

    client.patch(f"{base}/blocks/{bullet['id']}", json={"text": "Edit one.", "note": "why one"})
    client.patch(f"{base}/blocks/{bullet['id']}", json={"text": "Edit two."})

    history = client.get(f"{base}/revisions").json()
    assert [r["n"] for r in history] == [2, 1, 0]
    assert history[1]["before"].startswith("Worked on") and history[1]["after"] == "Edit one."
    assert history[1]["note"] == "why one"

    restored = client.post(f"{base}/restore", json={"n": 1}).json()
    assert restored["revision"] == 3
    assert next(b for b in restored["blocks"] if b["id"] == bullet["id"])["text"] == "Edit one."
    # Nothing after it was lost: version 2 is still in the history.
    assert [r["n"] for r in client.get(f"{base}/revisions").json()][:2] == [3, 2]


def test_an_entry_hides_moves_and_comes_back_whole(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    base = f"/v1/resumes/{resume['id']}/tailored/{copy['id']}"
    ride = _block(copy, "entry", "Ride Match")
    notes = _block(copy, "entry", "Notes Search")

    moved = client.post(f"{base}/move", json={"block_id": notes["id"], "before": ride["id"]}).json()
    order = [b["id"] for b in moved["blocks"]]
    assert order.index(notes["id"]) < order.index(ride["id"])
    # Its bullet travelled with it.
    notes_bullet = _block(moved, "bullet", "Elasticsearch")
    assert order.index(notes_bullet["id"]) == order.index(notes["id"]) + 1

    hidden = client.patch(f"{base}/blocks/{ride['id']}", json={"hidden": True}).json()
    ride_lines = [b for b in hidden["blocks"] if b["group"] == ride["id"]]
    assert ride_lines and all(b["hidden"] for b in ride_lines)

    across = client.post(
        f"{base}/move",
        json={"block_id": ride["id"], "before": _block(copy, "heading", "SKILLS")["id"]},
    )
    assert across.status_code == 422


def test_a_new_line_is_the_students_own_and_lands_under_its_entry(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    base = f"/v1/resumes/{resume['id']}/tailored/{copy['id']}"
    ride = _block(copy, "entry", "Ride Match")

    added = client.post(
        f"{base}/blocks", json={"after": ride["id"], "text": "Deployed it on Docker for 3 clubs."}
    ).json()
    new = next(b for b in added["blocks"] if b["added"])
    order = [b["id"] for b in added["blocks"]]
    last_of_ride = max(i for i, b in enumerate(added["blocks"]) if b["group"] == ride["id"])
    assert order.index(new["id"]) == last_of_ride and new["group"] == ride["id"]

    empty = client.post(f"{base}/blocks", json={"after": ride["id"], "text": "  "})
    assert empty.status_code == 422


# ---------------------------------------------------------------------------
#  The PDF
# ---------------------------------------------------------------------------


def test_the_layout_places_every_visible_block(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    layout = client.get(f"/v1/resumes/{resume['id']}/tailored/{copy['id']}/layout").json()
    assert layout["pages"] and layout["pages"][0]["width"] == pytest.approx(595.28)
    for block in copy["blocks"]:
        assert block["id"] in layout["boxes"], block
        for box in layout["boxes"][block["id"]]:
            x0, y0, x1, y1 = box["rect"]
            assert 0 <= x0 < x1 <= 595.28 and 0 <= y0 < y1 <= 841.89


def test_an_edit_reaches_the_pdf(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    base = f"/v1/resumes/{resume['id']}/tailored/{copy['id']}"
    bullet = _block(copy, "bullet", "Worked on")
    client.patch(
        f"{base}/blocks/{bullet['id']}", json={"text": "Profiled the payments service end to end."}
    )

    pdf = client.get(f"{base}/pdf").content
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        text = " ".join(page.get_text() for page in document)
    assert "Profiled the payments service" in " ".join(text.split())
    assert "Worked on the payments" not in " ".join(text.split())


def test_only_the_student_downloads_their_contact_details(client, session, m04_up):
    m04_up()
    candidate = str(uuid.uuid4())
    resume = _ingest(client, candidate)
    copy = _copy(client, resume["id"])
    url = f"/v1/resumes/{resume['id']}/tailored/{copy['id']}/pdf?filename=priya"

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    student = TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": candidate})
    own = student.get(url)
    assert own.status_code == 200 and own.headers["x-contact"] == "printed"
    with pymupdf.open(stream=own.content, filetype="pdf") as document:
        assert "priya.sharma@example.com" in document[0].get_text()

    staff = client.get(url)  # the fixture's admin
    assert staff.headers["x-contact"] == "masked"
    with pymupdf.open(stream=staff.content, filetype="pdf") as document:
        assert "priya.sharma@example.com" not in document[0].get_text()
        assert "98765" not in document[0].get_text()


def test_a_page_image_never_holds_the_contact_block(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    res = client.get(f"/v1/resumes/{resume['id']}/tailored/{copy['id']}/pages/1?zoom=1.5")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    # The image is drawn from a file that never contained the address at all.
    result = tailor.render(copy["blocks"], copy["style"], reveal=None)
    with pymupdf.open(stream=result.pdf, filetype="pdf") as document:
        assert "priya.sharma" not in document[0].get_text()


def test_another_student_cannot_open_a_copy(client, session, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    stranger = TestClient(app, headers={"X-Role": "student", "X-Candidate-Id": str(uuid.uuid4())})
    assert stranger.get(f"/v1/resumes/{resume['id']}/tailored/{copy['id']}").status_code == 403
    assert stranger.get(f"/v1/resumes/{resume['id']}/tailored/{copy['id']}/pdf").status_code == 403


def test_the_file_name_is_safe_and_ends_in_exactly_one_pdf():
    assert safe_filename("Priya_Sharma_Acme.pdf") == "Priya_Sharma_Acme.pdf"
    assert safe_filename("Priya resume.PDF.pdf") == "Priya resume.pdf"
    assert safe_filename('a/b\\c:d*?"<>|') == "a_b_c_d.pdf"
    assert safe_filename("   ", fallback="priya_resume") == "priya_resume.pdf"


def test_deleting_the_resume_deletes_its_copies(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    assert client.delete(f"/v1/resumes/{resume['id']}").status_code == 204
    assert client.get(f"/v1/resumes/{resume['id']}/tailored/{copy['id']}").status_code == 404


# ---------------------------------------------------------------------------
#  A line worded for one requirement
# ---------------------------------------------------------------------------


class _Fake:
    def __init__(self, data: dict):
        self.data = data

    @property
    def available(self) -> bool:
        return True

    def structured(self, *, job, system, user, schema):
        return llm.LLMResult(ok=True, data=self.data)


LINE = "Built a Redis cache for the product catalogue, cutting p95 latency from 420 ms to 95 ms."


def test_no_model_means_no_draft_and_says_so():
    llm.set_llm(llm.NullLLM())
    result = reword_for_requirement(LINE, requirement="Caching")
    assert result.suggestion is None and "No language model" in (result.refused or "")


def test_a_draft_that_adds_a_number_or_a_tool_is_discarded():
    llm.set_llm(_Fake({"suggestion": LINE.replace("95 ms", "50 ms"), "supported": True, "why": ""}))
    assert reword_for_requirement(LINE, requirement="Caching").suggestion is None

    added_tool = {
        "suggestion": "Built a Redis and Memcached cache cutting p95 latency from 420 ms to 95 ms.",
        "supported": True,
        "why": "",
    }
    llm.set_llm(_Fake(added_tool))
    refused = reword_for_requirement(LINE, requirement="Caching")
    assert refused.suggestion is None and "Memcached" in (refused.refused or "")


def test_a_clean_draft_comes_back_and_a_confirmed_term_may_be_added():
    good = (
        "Cut p95 latency from 420 ms to 95 ms by building a Redis caching layer for the "
        "product catalogue."
    )
    llm.set_llm(_Fake({"suggestion": good, "supported": True, "why": "names the cache"}))
    result = reword_for_requirement(LINE, requirement="Caching")
    assert result.suggestion == good and result.by_model

    with_term = good.replace("Redis caching layer", "Redis caching layer on AWS")
    llm.set_llm(_Fake({"suggestion": with_term, "supported": True, "why": ""}))
    assert reword_for_requirement(LINE, requirement="AWS").suggestion is None
    confirmed = reword_for_requirement(LINE, requirement="AWS", allowed_terms=["AWS"])
    assert confirmed.suggestion == with_term and confirmed.adds == ["AWS"]


def test_new_terms_catches_lower_case_tools_from_the_alias_table():
    assert "docker" in new_terms("Built an API.", "Built an API and shipped it with docker.")
    assert new_terms("Built an API.", "Built and shipped an API.") == []


# ---------------------------------------------------------------------------
#  The photo (2026-11-17)
# ---------------------------------------------------------------------------


def _picture(width: int = 160, height: int = 160) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), 0)
    pixmap.set_rect(pixmap.irect, (90, 120, 160))
    return pixmap.tobytes("png")


def _pdf_with_image(rect: tuple[float, float, float, float], width: int, height: int) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((40, 60), "PRIYA SHARMA", fontsize=18)
    page.insert_image(pymupdf.Rect(*rect), stream=_picture(width, height))
    data = document.tobytes()
    document.close()
    return data


def test_the_photo_on_an_uploaded_resume_is_found_and_a_logo_is_not():
    photo = tailor.original_photo(_pdf_with_image((480, 36, 556, 112), 160, 160))
    assert photo is not None and photo[:3] == b"\xff\xd8\xff"
    # A wide banner is a logo, and an image low on the page is not a header photo.
    assert tailor.original_photo(_pdf_with_image((40, 30, 300, 80), 520, 100)) is None
    assert tailor.original_photo(_pdf_with_image((480, 600, 556, 676), 160, 160)) is None
    assert tailor.original_photo(None) is None


def test_the_photo_sits_beside_the_header_and_the_page_still_fits():
    blocks = tailor.build_blocks(
        redacted="PRIYA SHARMA\nSUMMARY\nBackend developer.\n",
        sections=[],
        claims=[],
    )
    with_photo = tailor.render(blocks, None, photo=_picture())
    assert "photo" in with_photo.boxes
    x0, y0, x1, _ = with_photo.boxes["photo"][0]["rect"]
    name_box = with_photo.boxes[blocks[0]["id"]][0]["rect"]
    assert name_box[2] < x0  # the name ends before the photo starts
    with pymupdf.open(stream=with_photo.pdf, filetype="pdf") as document:
        assert document[0].get_images()


def test_the_settings_picture_prints_and_can_be_left_off_one_copy(client, monkeypatch, m04_up):
    from backend_M01_Resume_Ingestion import tailored_api

    m04_up()
    monkeypatch.setattr(tailored_api, "_profile_photo", lambda _candidate: _picture())
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    base = f"/v1/resumes/{resume['id']}/tailored/{copy['id']}"
    assert copy["photo"]["available"] == "profile" and copy["photo"]["enabled"]
    with pymupdf.open(stream=client.get(f"{base}/pdf").content, filetype="pdf") as document:
        assert document[0].get_images()

    off = client.patch(f"{base}/style", json={"photo": False}).json()
    assert off["photo"]["enabled"] is False and off["revision"] == copy["revision"] + 1
    with pymupdf.open(stream=client.get(f"{base}/pdf").content, filetype="pdf") as document:
        assert not document[0].get_images()
    # Asking for what is already so changes nothing and makes no version.
    assert (
        client.patch(f"{base}/style", json={"photo": False}).json()["revision"] == off["revision"]
    )
    history = client.get(f"{base}/revisions").json()
    assert history[0]["action"] == "style" and history[0]["after"] == "photo off"


def test_no_picture_anywhere_means_no_photo_and_says_so(client, m04_up):
    m04_up()
    resume = _ingest(client)
    copy = _copy(client, resume["id"])
    assert copy["photo"] == {"available": None, "enabled": True, "digest": None}

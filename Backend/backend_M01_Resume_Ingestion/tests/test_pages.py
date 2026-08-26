"""The original page, rendered for §8.1's `PdfHighlightViewer`.

Two things are being protected, and only one of them is the feature.

The feature is §8.3: *"Click a claim → the original PDF scrolls and highlights
that exact bullet. This is a 4-hour feature that buys enormous trust: the
student sees we read THEIR document."*

The other thing is FR-1.17, and it is why this is a server-side render at all.
The obvious build is pdf.js over the uploaded bytes, which would send the
UNREDACTED document to a browser — the exact artifact the contact isolation
exists to keep in one place. So the page is rasterised here with the contact
painted out FIRST, and `test_the_contact_block_is_painted_out` checks the
pixels rather than trusting the call.
"""

from __future__ import annotations

import functools
import io
import uuid

import pytest

pymupdf = pytest.importorskip("pymupdf")

RESUME_TEXT = """ANSH BAJPAI
ansh.bajpai@example.com | +91 98765 43210

PROJECTS
Built a route planner in Python using dynamic programming on a 12k-node graph.
Developed a sentiment classifier on review data.
"""


@functools.cache
def _pdf() -> bytes:
    """One PDF, built once.

    Cached because PyMuPDF stamps each document it writes, so calling this
    twice produces two files with the same CONTENT and different BYTES — and
    the dedup test below is about byte-identical uploads being one object.
    That is also true of the real world: two exports of the same resume are
    two artifacts, and content-addressing dedups files, not documents.
    """
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 560, 700), RESUME_TEXT, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def _upload(client, candidate: str | None = None):
    candidate = candidate or str(uuid.uuid4())
    res = client.post(
        "/v1/resumes",
        data={"candidate_id": candidate},
        files={"file": ("cv.pdf", _pdf(), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
#  FR-1.2 — the FILE, not our reading of it
# ---------------------------------------------------------------------------


def test_the_uploaded_file_is_kept_not_just_the_text(client, m04_up):
    """FR-1.2: *"Store the raw file immutably… keyed by SHA-256 of contents."*

    `content_sha256` is the digest of the extracted TEXT, which is a
    derivative — so the requirement was being met against the wrong artifact
    and the upload itself was discarded at ingest. Nothing could render a page
    because there was no page.
    """
    m04_up()
    data = _upload(client)

    assert data["source_sha256"], "the uploaded file was not stored"
    assert data["source_sha256"] != data["content_sha256"], (
        "the file digest and the text digest must not be the same number"
    )


def test_a_pasted_resume_has_no_source_and_says_so(client, m04_up):
    """The paste path never had a file, and must not pretend to."""
    m04_up()
    res = client.post(
        "/v1/resumes/from-text",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": RESUME_TEXT},
    )

    assert res.json()["source_sha256"] == ""


# ---------------------------------------------------------------------------
#  The pages
# ---------------------------------------------------------------------------


def test_pages_carry_their_size_in_points(client, m04_up):
    """`SourceSpan.bbox` is in points, so a client drawing a highlight over the
    rendered image needs the page size to scale by — otherwise it hardcodes an
    assumption about the server's zoom and is wrong the day that changes."""
    m04_up()
    data = _upload(client)

    pages = client.get(f"/v1/resumes/{data['id']}/pages").json()

    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert pages[0]["width"] > 0 and pages[0]["height"] > 0


def test_a_pasted_resume_has_no_pages_rather_than_an_error(client, m04_up):
    """§8.2 asks for "Original not available (pasted text)" as a STATE.

    An empty list is how the viewer knows to fall back to the text highlight,
    which carries exactly the same offsets. A 500 here would turn a resume
    that parsed perfectly into a broken screen.
    """
    m04_up()
    res = client.post(
        "/v1/resumes/from-text",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": RESUME_TEXT},
    )

    assert client.get(f"/v1/resumes/{res.json()['id']}/pages").json() == []
    assert client.get(f"/v1/resumes/{res.json()['id']}/pages/1").status_code == 404


def test_a_page_renders_as_a_png(client, m04_up):
    m04_up()
    data = _upload(client)

    res = client.get(f"/v1/resumes/{data['id']}/pages/1")

    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_page_that_does_not_exist_is_a_404(client, m04_up):
    m04_up()
    data = _upload(client)

    assert client.get(f"/v1/resumes/{data['id']}/pages/9").status_code == 404
    assert client.get(f"/v1/resumes/{data['id']}/pages/0").status_code == 404


# ---------------------------------------------------------------------------
#  FR-1.17 — the reason this renders on the server
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_the_contact_block_is_painted_out_of_the_image(client, session, m04_up):
    """The pixels, not the intent.

    The rectangles are filled BEFORE the pixmap is taken, so the bytes that
    leave never contained the contact block at any point — not hidden under an
    overlay a client could strip, not in a layer, absent.

    Asserted by sampling inside every redaction rectangle the endpoint computes,
    because "the image differs from an unredacted one" only proves that
    SOMETHING was drawn. If this fails, a student's email address is in a PNG
    being served to a browser and the entire argument for rendering
    server-side has gone with it.
    """
    from backend_M01_Resume_Ingestion import documents, router, storage
    from backend_M01_Resume_Ingestion.models import Resume

    m04_up()
    data = _upload(client)

    row = session.get(Resume, uuid.UUID(data["id"]))
    assert "█" in row.redacted_text, "nothing was masked, so this proves nothing"

    source = storage.get_bytes(row.source_sha256, suffix="pdf")
    assert source is not None, "the uploaded file was not stored"
    geometry = documents.parse(source, row.filename)
    boxes = router._masked_boxes(row, geometry, 1)
    assert boxes, "the contact block produced no rectangles to paint"

    zoom = 2.0
    png = client.get(f"/v1/resumes/{data['id']}/pages/1").content
    image = pymupdf.Pixmap(io.BytesIO(png))

    for box in boxes:
        x0, y0, x1, y1 = (int(value * zoom) for value in box)
        # One pixel in from each edge: the rectangle's own border is
        # antialiased, and a test that samples it is testing the rasteriser.
        points = [(x, y) for x in range(x0 + 1, x1 - 1) for y in range(y0 + 1, y1 - 1)]
        assert points, f"rectangle {box} is too small to sample"
        black = sum(1 for x, y in points if image.pixel(x, y) == (0, 0, 0))
        assert black == len(points), (
            f"contact rectangle {box} is only {black / len(points):.0%} painted — "
            "part of the contact block is visible in the served image"
        )


@pytest.mark.gate
def test_deleting_a_resume_deletes_the_uploaded_file(client, session, m04_up):
    """§7: *"hard delete incl. object storage"*.

    There are two blobs per resume now — the extracted text and the document it
    came from — and a delete that removed one of them would leave the student's
    actual PDF on disk after they asked us to forget it. That is the deletion
    request not being honoured, in the module that stores the contact block.
    """
    from backend_M01_Resume_Ingestion import storage
    from backend_M01_Resume_Ingestion.models import Resume

    m04_up()
    data = _upload(client)
    row = session.get(Resume, uuid.UUID(data["id"]))
    digest = row.source_sha256

    assert storage.get_bytes(digest, suffix="pdf") is not None

    assert client.delete(f"/v1/resumes/{data['id']}").status_code == 204

    assert storage.get_bytes(digest, suffix="pdf") is None, (
        "the uploaded file survived a deletion request"
    )


def test_a_file_two_students_share_survives_one_of_them_deleting(client, session, m04_up):
    """Blobs are content-addressed, so identical uploads are ONE object.

    The second student's deletion must not take the first student's document
    with it — which is the failure mode content-addressing introduces and the
    reason the text blob already checks this before removing anything.
    """
    from backend_M01_Resume_Ingestion import storage
    from backend_M01_Resume_Ingestion.models import Resume

    m04_up()
    mine = _upload(client)
    theirs = _upload(client)

    digest = session.get(Resume, uuid.UUID(mine["id"])).source_sha256
    assert digest == session.get(Resume, uuid.UUID(theirs["id"])).source_sha256

    client.delete(f"/v1/resumes/{theirs['id']}")

    assert storage.get_bytes(digest, suffix="pdf") is not None, (
        "one student's deletion removed another student's file"
    )

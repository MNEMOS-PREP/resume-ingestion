"""The production-hardening pass: typography, tables, language, PII at rest.

Each of these closes a gap where the module was doing something reasonable and
saying nothing about it — a heading it could not see, a table it flattened, a
language it could not read, a phone number it stored in the clear. The pattern
they share is the one this module keeps designing against: **failing silently
is worse than failing.**
"""

import os
import uuid

import pytest
from backend_M01_Resume_Ingestion import crypto, documents, storage
from backend_M01_Resume_Ingestion.claims import segment

pymupdf = pytest.importorskip("pymupdf")


def _ingest(client, text):
    res = client.post(
        "/v1/resumes/from-text",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()


#: Padding so a fixture clears `config.MIN_TEXT_LAYER_CHARS`.
#:
#: Below 100 characters the pipeline treats the text layer as absent and routes
#: to OCR (FR-1.16) — correctly, and it made three of these tests fail against
#: perfectly good code. A fixture that is shorter than any real resume is
#: testing a path it did not mean to.
_PADDING = [
    ("SKILLS", 12, True),
    ("Python, SQL, Docker, Kubernetes, React, Java, Linux, Git", 10, False),
    ("Comfortable across the stack and happy to learn what is needed.", 10, False),
]


def _pdf(lines: list[tuple[str, int, bool]], *, pad: bool = True) -> bytes:
    """Build a PDF from (text, size, bold) lines."""
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for text, size, bold in [*lines, *(_PADDING if pad else [])]:
        if text:
            page.insert_text((50, y), text, fontsize=size, fontname="hebo" if bold else "helv")
        y += size * 1.9
    data = doc.tobytes()
    doc.close()
    return data


# ---------------------------------------------------------------------------
#  §6.3 — the typographic tier
# ---------------------------------------------------------------------------


def test_a_pdf_carries_how_each_line_is_set():
    """§6.3 scores a heading on font size and bold as well as on words.

    `words` output carries geometry and no typography, so this had to be read
    from the span tree separately — without it the lexicon is the only signal
    and a heading nobody anticipated is invisible.
    """
    parsed = documents.parse(
        _pdf([("PRIYA SHARMA", 16, True), ("EDUCATION", 12, True), ("Amrita, B.Tech", 10, False)]),
        "styled.pdf",
    )

    assert parsed.line_styles, "no typography was captured"
    styles = [parsed.line_styles[k] for k in sorted(parsed.line_styles)]
    assert styles[0].bold and styles[0].size_z > 1.0
    assert not styles[-1].bold


def test_a_heading_outside_the_lexicon_is_still_found():
    """The reason the typographic tier is worth having.

    "HACKATHON WINS" is in no lexicon and never will be — every template
    invents one. Set like a heading, followed by bullets, it is a heading, and
    its bullets become claims instead of being swallowed by the section above.
    """
    parsed = documents.parse(
        _pdf(
            [
                ("EDUCATION", 12, True),
                ("Amrita Vishwa Vidyapeetham, 2022 - 2026", 10, False),
                ("", 10, False),
                ("HACKATHON WINS", 12, True),
                ("- Won Smart India Hackathon 2024 with a team of 4.", 10, False),
            ]
        ),
        "unknown-heading.pdf",
    )
    kinds = [s.kind for s in segment(parsed.text, uuid.uuid4(), geometry=parsed)]

    assert "education" in kinds
    assert "unknown" in kinds, "the unlisted heading was not detected"


def test_typography_raises_confidence_on_a_heading_the_lexicon_knows():
    """Corroboration, not a second opinion — the kind does not change."""
    parsed = documents.parse(
        _pdf([("EDUCATION", 13, True), ("Amrita, B.Tech CSE, 2022 - 2026", 10, False)]),
        "styled.pdf",
    )
    education = next(
        s for s in segment(parsed.text, uuid.uuid4(), geometry=parsed) if s.kind == "education"
    )

    assert education.confidence > 0.9


def test_a_bolded_bullet_is_not_a_heading():
    """The false positive that would strand every claim after it.

    A bolded job title inside an experience block is bold, short, and not a
    heading. Four of §6.3's signals have to agree, not one.
    """
    parsed = documents.parse(
        _pdf(
            [
                ("EXPERIENCE", 12, True),
                ("- Software Engineer Intern at Zoho, 2025.", 10, True),
                ("- Built internal tooling for the platform team.", 10, False),
            ]
        ),
        "bold-bullet.pdf",
    )
    sections = segment(parsed.text, uuid.uuid4(), geometry=parsed)

    # Both bullets belong to EXPERIENCE. Neither may start a section of its
    # own — the second one partial-matched `tooling` and opened a SKILLS
    # section mid-block, which strands every bullet after it.
    experience = next(s for s in sections if s.kind == "experience")
    assert "Software Engineer Intern" in experience.span.text
    assert "internal tooling" in experience.span.text

    starts = [s.span.text.strip().splitlines()[0] for s in sections]
    assert not any(line.lstrip().startswith("-") for line in starts)


# ---------------------------------------------------------------------------
#  §6.2.4 — PDF tables
# ---------------------------------------------------------------------------


def test_a_ruled_pdf_table_becomes_key_value_lines():
    """EC-1.15. Half the Canva templates lay education out as a table.

    Read as flowed text those cells become one run nobody can parse a degree
    from, and the education section comes out as a single unreadable line.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "EDUCATION", fontsize=12, fontname="hebo")
    y = 70
    for label, value in [
        ("Institution", "Amrita Vishwa Vidyapeetham"),
        ("Degree", "B.Tech CSE"),
        ("CGPA", "8.1"),
    ]:
        page.draw_rect(pymupdf.Rect(50, y, 180, y + 22))
        page.draw_rect(pymupdf.Rect(180, y, 400, y + 22))
        page.insert_text((55, y + 15), label, fontsize=9)
        page.insert_text((185, y + 15), value, fontsize=9)
        y += 22
    data = doc.tobytes()
    doc.close()

    text = documents.parse(data, "table.pdf").text

    assert "Institution: Amrita Vishwa Vidyapeetham" in text
    assert "CGPA: 8.1" in text


def test_table_lines_are_appended_not_spliced():
    """Every offset in the text layer is committed by the time tables are read.

    Splicing them in would move every span already recorded, which is AC-1.1
    broken for a formatting improvement.
    """
    parsed = documents.parse(
        _pdf([("PROJECTS", 12, True), ("- Built a route planner in Python.", 10, False)]),
        "no-table.pdf",
    )

    for word in parsed.words:
        assert parsed.text[word.start : word.end].strip()


# ---------------------------------------------------------------------------
#  EC-1.6 — language
# ---------------------------------------------------------------------------


def test_an_english_resume_is_detected_as_english():
    text = (
        "PROJECTS\nBuilt a route planner in Python using dynamic programming "
        "for the campus network, cutting query time substantially."
    )
    language, _confidence = documents.detect_language(text)
    assert language == "en"


@pytest.mark.parametrize(
    "text",
    [
        "परियोजनाएं मैंने पायथन में एक मार्ग योजनाकार बनाया जो गतिशील प्रोग्रामिंग का उपयोग करता है और तेज है।",
        "திட்டங்கள் நான் பைத்தானில் ஒரு பாதை திட்டமிடுபவரை உருவாக்கினேன். இது வேகமாக இயங்குகிறது.",
    ],
)
def test_a_non_english_resume_is_flagged_not_silently_thin(text):
    """EC-1.6: "detect language; offer to proceed with reduced accuracy, flag
    clearly".

    Every lexicon in this module is English. Without the flag a Hindi resume
    parses to almost nothing and is indistinguishable from a resume with
    nothing on it — the exact silent failure this module keeps designing
    against.
    """
    language, confidence = documents.detect_language(text)

    assert language != "en"
    assert confidence > 0.5


def test_the_student_is_told_and_not_blocked(client, m04_up):
    """Flagged, never refused. The read still happens."""
    m04_up()
    data = _ingest(
        client,
        "परियोजनाएं मैंने पायथन में एक मार्ग योजनाकार बनाया जो गतिशील प्रोग्रामिंग का उपयोग करता है और तेज है।",
    )

    assert data["language"] != "en"
    assert data["parse_status"] == "needs_review"
    assert any("English" in note for note in data["parse_notes"])


def test_a_short_document_is_not_guessed_at():
    """Two words is not enough to call a language, and saying "en" anyway is a
    confident wrong answer where "unknown" is a true one."""
    assert documents.detect_language("Python")[0] == "unknown"


# ---------------------------------------------------------------------------
#  FR-1.17 — encryption at rest
# ---------------------------------------------------------------------------


@pytest.fixture(name="pii_key")
def pii_key_fixture(monkeypatch):
    monkeypatch.setenv("M01_PII_KEY", crypto.generate_key())
    yield


def test_a_contact_value_round_trips_through_encryption(pii_key):
    encrypted = crypto.encrypt("priya.sharma@example.com")

    assert encrypted.startswith(crypto.PREFIX)
    assert "priya.sharma" not in encrypted
    assert crypto.decrypt(encrypted) == "priya.sharma@example.com"


def test_the_stored_row_does_not_contain_the_phone_number(client, session, m04_up, pii_key):
    """The half FR-1.17 was missing.

    Separation and redaction already stopped PII reaching a screen or a model.
    This is what somebody holding a copy of the database file can read.
    """
    from backend_M01_Resume_Ingestion.models import ResumeContact

    m04_up()
    data = _ingest(client, "PRIYA SHARMA\npriya.sharma@example.com | +91 98765 43210\n")

    row = session.get(ResumeContact, uuid.UUID(data["id"]))
    assert row is not None
    stored = str(row.emails) + str(row.phones)
    assert "priya.sharma@example.com" not in stored
    assert "98765" not in stored

    # And it is still readable through the route that deliberately releases it.
    released = client.get(f"/v1/resumes/{data['id']}/contact").json()
    assert released["emails"] == ["priya.sharma@example.com"]


def test_without_a_key_values_are_stored_readable_and_that_is_reported(client, m04_up):
    """Deliberately not a hard failure.

    Refusing to start would mean a student cannot upload a resume because an
    operator has not read the deployment notes. The state is reported instead,
    so "we forgot" is discoverable rather than silent.
    """
    os.environ.pop("M01_PII_KEY", None)
    m04_up()
    _ingest(client, "PRIYA SHARMA\npriya.sharma@example.com\n")

    assert crypto.key_configured() is False
    assert client.get("/v1/quality").json()["pii_encrypted_at_rest"] is False


def test_a_value_written_before_the_key_existed_still_reads(pii_key):
    """A mixed table has to work, or turning encryption on loses history."""
    assert crypto.decrypt("priya.sharma@example.com") == "priya.sharma@example.com"


def test_an_undecryptable_value_does_not_raise(monkeypatch):
    """A rotated key must not turn a placement officer's lookup into a 500."""
    monkeypatch.setenv("M01_PII_KEY", crypto.generate_key())
    encrypted = crypto.encrypt("priya@example.com")
    monkeypatch.setenv("M01_PII_KEY", crypto.generate_key())

    assert "key does not match" in crypto.decrypt(encrypted)


# ---------------------------------------------------------------------------
#  FR-1.2 — the object key §6.1 specifies
# ---------------------------------------------------------------------------


def test_the_object_key_is_candidate_scoped():
    """§6.1: `resumes/{candidate_id}/{sha256}`.

    One prefix per student, so a deletion request is one operation rather than
    a scan, and a bucket listing is auditable without a database join.
    """
    key = storage.object_key("cand-1", "abc123", "pdf")
    assert key == "resumes/cand-1/abc123.pdf"


def test_a_shared_blob_records_every_owner(tmp_path):
    """Two students who submit the same file are one object.

    The path cannot belong to either of them, so ownership lives in a sidecar —
    which is also what a retention job needs in order to know what it governs.
    """
    digest, _uri = storage.put("same bytes", root=tmp_path, candidate_id="cand-1")
    storage.put("same bytes", root=tmp_path, candidate_id="cand-2")

    sidecar = next(tmp_path.rglob("*.owners"))
    body = sidecar.read_text(encoding="utf-8")

    assert f"retention_class={storage.RETENTION_CLASS}" in body
    assert f"resumes/cand-1/{digest}" in body
    assert f"resumes/cand-2/{digest}" in body


def test_recording_an_owner_twice_does_not_duplicate_it(tmp_path):
    storage.put("bytes", root=tmp_path, candidate_id="cand-1")
    storage.put("bytes", root=tmp_path, candidate_id="cand-1")

    sidecar = next(tmp_path.rglob("*.owners"))
    assert sidecar.read_text(encoding="utf-8").count("cand-1") == 1

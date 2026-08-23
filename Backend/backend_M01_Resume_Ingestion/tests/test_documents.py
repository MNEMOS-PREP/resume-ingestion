"""Intake, layout and reading order (FR-1.1, FR-1.3, FR-1.4, FR-1.16, §9).

Spec §12 asks for "column detection on 20 synthetic layouts (1-col, 2-col,
2-col-with-header, table)". The layouts here are built with PyMuPDF rather than
checked in as fixture PDFs, so the geometry that is being asserted about is
visible in the test rather than hidden in a binary — and a failure says which
layout broke instead of which file did.
"""

import pytest

pymupdf = pytest.importorskip("pymupdf")

from backend_M01_Resume_Ingestion import config, documents  # noqa: E402
from backend_M01_Resume_Ingestion.documents import IntakeError  # noqa: E402

LEFT = """EDUCATION
Amrita Vishwa Vidyapeetham
B.Tech CSE 2022 - 2026
CGPA 8.1

PROJECTS
Route planner in Python
Hash map from scratch
Sentiment classifier
Campus placement portal
Weather dashboard
Chess engine
Recipe finder
Budget tracker
Note taking app
"""

RIGHT = """SKILLS
Python
Java
Docker
Kubernetes
React
SQL
Git
Linux
TensorFlow
PyTorch
Postgres
MongoDB
Redis
AWS
"""


def build_pdf(*, columns=1, header=None, pages=1) -> bytes:
    """A synthetic resume with a known layout."""
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        top = 40
        if header:
            page.insert_textbox(pymupdf.Rect(40, 30, 560, 95), header, fontsize=13)
            top = 105
        if columns == 2:
            page.insert_textbox(pymupdf.Rect(40, top, 240, 780), LEFT, fontsize=10)
            page.insert_textbox(pymupdf.Rect(330, top, 560, 780), RIGHT, fontsize=10)
        else:
            page.insert_textbox(
                pymupdf.Rect(40, top, 540, 780),
                LEFT + "\n" + RIGHT.replace("\n", ", "),
                fontsize=10,
            )
    data = doc.tobytes()
    doc.close()
    return data


def build_docx(rows=None) -> bytes:
    import io

    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("PRIYA SHARMA")
    document.add_paragraph("PROJECTS")
    document.add_paragraph("- Built a route planner in Python using dynamic programming.")
    if rows:
        table = document.add_table(rows=0, cols=2)
        for key, value in rows:
            cells = table.add_row().cells
            cells[0].text, cells[1].text = key, value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
#  FR-1.1 — what we accept, and how we refuse the rest
# ---------------------------------------------------------------------------


def test_type_is_decided_by_content_not_by_extension():
    """A student who renamed report.docx to resume.pdf is a real person.

    The extension is the one part of a filename anybody edits, so the magic
    bytes decide. Getting this wrong means handing a zip to a PDF parser and
    reporting "damaged file" about a perfectly good resume.
    """
    assert documents.sniff(build_pdf(), "anything.txt") == "application/pdf"
    assert documents.sniff(build_docx(), "resume.pdf").endswith("wordprocessingml.document")
    assert documents.sniff(b"Just some text", "resume.pdf") == "text/plain"


def test_legacy_doc_is_refused_by_name():
    """§6.1 writes this error message out in full, so it is asserted in full."""
    with pytest.raises(IntakeError) as caught:
        documents.sniff(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "resume.doc")
    assert caught.value.code == "legacy_doc"
    assert "save as PDF or .docx" in caught.value.message


def test_a_zero_byte_file_fails_at_intake():
    """EC-1.16 — caught before the pipeline, not three stages later where it
    presents as "no sections found"."""
    with pytest.raises(IntakeError) as caught:
        documents.sniff(b"", "resume.pdf")
    assert caught.value.code == "empty_file"


def test_an_oversized_file_is_refused_with_the_limit_in_the_message():
    """§12 adversarial: "10 MB of repeated text"."""
    with pytest.raises(IntakeError) as caught:
        documents.sniff(b"A" * (config.MAX_UPLOAD_BYTES + 1), "resume.txt")
    assert caught.value.code == "too_large"
    assert caught.value.status == 413
    assert "10 MB" in caught.value.message


def test_every_intake_error_points_at_the_paste_path_or_a_fix():
    """§10: the text-paste path always works, and every named failure says so.

    A student who cannot get past this screen leaves and does not come back
    (§2.4), so an error that only says what went wrong is half an error.
    """
    cases = [
        (b"", "resume.pdf"),
        (b"{\\rtf1 hello}", "resume.rtf"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "resume.doc"),
    ]
    for data, name in cases:
        with pytest.raises(IntakeError) as caught:
            documents.sniff(data, name)
        message = caught.value.message.casefold()
        assert "paste" in message or "save as" in message or "re-upload" in message


def test_a_corrupt_pdf_is_a_named_error_not_a_stack_trace():
    with pytest.raises(IntakeError) as caught:
        documents.parse(b"%PDF-1.4\nthis is not really a pdf", "broken.pdf")
    assert caught.value.code in {"corrupt_file", "no_text_found", "no_text_layer"}
    assert caught.value.status == 422


def test_a_password_protected_pdf_says_so():
    """EC-1.3 — "clear error + remove the password and re-upload"."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret resume")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()

    with pytest.raises(IntakeError) as caught:
        documents.parse(data, "locked.pdf")
    assert caught.value.code == "password_protected"
    assert "password" in caught.value.message.casefold()


# ---------------------------------------------------------------------------
#  FR-1.4 — columns and reading order (Trap 2)
# ---------------------------------------------------------------------------


def test_a_single_column_resume_is_not_split():
    parsed = documents.parse(build_pdf(columns=1), "one.pdf")
    assert parsed.columns == 1
    assert parsed.column_confidence == 1.0


def test_a_two_column_resume_is_read_column_by_column():
    """Trap 2, the single most common real-world failure.

    Naive top-to-bottom extraction interleaves the columns into word salad:
    "EDUCATION SKILLS / Amrita Vishwa Vidyapeetham Python". The whole left
    column must come out before the right one starts.
    """
    parsed = documents.parse(build_pdf(columns=2), "two.pdf")
    assert parsed.columns == 2

    text = parsed.text
    assert "EDUCATION SKILLS" not in text, "columns were interleaved — Trap 2"
    # Every left-column line precedes every right-column line.
    assert text.index("CGPA 8.1") < text.index("SKILLS")
    assert text.index("Route planner") < text.index("Kubernetes")


def test_a_full_width_header_above_two_columns_still_reads_first():
    """The 2-col-with-header layout from §12.

    The header crosses the gutter, which costs a little column confidence and
    must not cost the detection — and the name has to come out at the top or
    entity extraction takes the wrong line as the student's name.
    """
    parsed = documents.parse(
        build_pdf(columns=2, header="PRIYA SHARMA\npriya@example.com"), "hdr.pdf"
    )
    assert parsed.columns == 2
    assert parsed.text.lstrip().startswith("PRIYA SHARMA")


def test_a_two_column_layout_warns_the_student_to_check_it():
    """EC-1.1 — reading order is the thing most likely to be silently wrong,
    so the confirmation screen is told to ask about it."""
    parsed = documents.parse(build_pdf(columns=2), "two.pdf")
    assert parsed.notes
    assert "column" in " ".join(parsed.notes).casefold()


def test_column_detection_ignores_a_gap_that_is_only_a_few_lines_tall():
    """A wide indent under one heading is not a gutter.

    Over-splitting shreds the document; under-splitting only loses reading
    order. §6.2.2 is explicit about which way to fail.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 540, 300), LEFT, fontsize=10)
    page.insert_textbox(pymupdf.Rect(330, 320, 560, 400), "Python\nJava", fontsize=10)
    data = doc.tobytes()
    doc.close()

    assert documents.parse(data, "indent.pdf").columns == 1


# ---------------------------------------------------------------------------
#  FR-1.3 — geometry
# ---------------------------------------------------------------------------


def test_every_word_carries_a_page_and_a_box():
    parsed = documents.parse(build_pdf(), "one.pdf")
    assert parsed.words
    for word in parsed.words[:20]:
        assert word.page >= 1
        x0, y0, x1, y1 = word.bbox
        assert x1 > x0 and y1 > y0
        assert parsed.text[word.start : word.end].strip()


def test_a_span_resolves_back_to_a_box_on_the_right_page():
    """§8.3 — click a claim, the original PDF highlights that exact bullet.

    A 4-hour feature that buys enormous trust: the student sees we read THEIR
    document. It needs offsets to survive back into geometry.
    """
    parsed = documents.parse(build_pdf(pages=2), "two-page.pdf")
    needle = "Route planner"
    start = parsed.text.rindex(needle)
    page, bbox = parsed.geometry_for(start, start + len(needle))

    assert page == 2, "the second occurrence is on page 2"
    assert bbox is not None and bbox[2] > bbox[0]


def test_pasted_text_has_no_geometry_and_says_so():
    """Inventing a box would put a highlight on a page that does not exist."""
    parsed = documents.from_text("Built a thing.")
    assert parsed.words == []
    assert parsed.geometry_for(0, 5) == (1, None)


def test_a_hanging_indent_survives_into_the_text_layer():
    """§6.5.1 — "Multi-line bullets merge on hanging indent".

    In a PDF the indent is an x coordinate and nothing else. Emitted flush
    left, a wrapped bullet becomes two claims, and the second half — the half
    with the measurement in it — is scored as a bullet with no verb and gets
    probes generated about a sentence fragment.

    So the geometric indent is written out as leading spaces, which is what the
    bullet segmenter reads.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(40, 40, 400, 400),
        "PROJECTS\n"
        "- Built a route planner in Python using\n"
        "    dynamic programming; cut query time from 380ms to 45ms.\n",
        fontsize=10,
    )
    data = doc.tobytes()
    doc.close()

    lines = documents.parse(data, "wrapped.pdf").text.splitlines()
    continuation = next(line for line in lines if "dynamic programming" in line)
    bullet = next(line for line in lines if "route planner" in line)

    indent = len(continuation) - len(continuation.lstrip(" "))
    assert indent > len(bullet) - len(bullet.lstrip(" ")), "the hanging indent was flattened"


def test_the_right_column_is_not_read_as_one_deep_indent():
    """Indents are measured per column, not from the page margin.

    The right column starts 300pt in. Measured against the page, every line in
    it is a deep continuation of nothing, and the whole column merges into one
    claim.
    """
    parsed = documents.parse(build_pdf(columns=2), "two.pdf")
    skills = [
        line for line in parsed.text.splitlines() if line.strip() in {"Python", "Java", "Docker"}
    ]

    assert skills, "the right column did not come through"
    assert all(line == line.strip() for line in skills), "right column read as indented"


# ---------------------------------------------------------------------------
#  §6.1 — page cap (EC-1.5)
# ---------------------------------------------------------------------------


def test_a_long_cv_is_truncated_and_the_student_is_told():
    """EC-1.5 — "8-page CV (research student): parse first 6 pages; notify"."""
    parsed = documents.parse(build_pdf(pages=8), "cv.pdf")

    assert parsed.page_count == config.MAX_PAGES
    assert parsed.pages_skipped == 2
    assert any("8 pages" in note for note in parsed.notes)


# ---------------------------------------------------------------------------
#  FR-1.16 — OCR
# ---------------------------------------------------------------------------


def test_a_scanned_pdf_without_an_ocr_engine_fails_by_name(monkeypatch):
    """EC-1.2, and the honest half of it.

    §6.2.6 specifies PaddleOCR — a several-hundred-megabyte dependency this
    deployment does not carry. The requirement that survives regardless is that
    a scan must never come back as a silent empty parse: it is a named error
    with the paste path in it.
    """
    monkeypatch.setattr(documents, "ocr_available", lambda: False)

    doc = pymupdf.open()
    doc.new_page()  # a page with no text layer at all
    data = doc.tobytes()
    doc.close()

    with pytest.raises(IntakeError) as caught:
        documents.parse(data, "scan.pdf")
    assert caught.value.code == "no_text_layer"
    assert "paste" in caught.value.message.casefold()


def test_ocr_output_lowers_every_confidence(monkeypatch):
    """§6.2.6 — "Mark ocr_used=true and lower all confidences by 0.15."

    Everything derived from a reading of a picture is exactly that much less
    certain, and saying so once on the document beats each downstream stage
    remembering to.
    """
    monkeypatch.setattr(documents, "ocr_available", lambda: True)
    monkeypatch.setattr(documents, "_ocr_engine", lambda: lambda png: "PROJECTS\nBuilt a thing.")

    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()

    parsed = documents.parse(data, "scan.pdf")
    assert parsed.ocr_used is True
    assert parsed.confidence_penalty == config.OCR_CONFIDENCE_PENALTY
    assert any("from an image" in note for note in parsed.notes)


# ---------------------------------------------------------------------------
#  DOCX (§6.2.4)
# ---------------------------------------------------------------------------


def test_docx_paragraphs_are_read_in_order():
    parsed = documents.parse(build_docx(), "resume.docx")
    assert parsed.text.startswith("PRIYA SHARMA")
    assert "route planner" in parsed.text.casefold()


def test_a_docx_table_becomes_key_value_lines():
    """§6.2.4, and EC-1.15.

    A two-column table is how half the Canva templates lay out education.
    Flattened to bare cells it loses which side is the label, and the section
    segmenter then sees "Institution Amrita B.Tech 2022" as one unreadable run.
    """
    parsed = documents.parse(
        build_docx(rows=[("Institution", "Amrita Vishwa Vidyapeetham"), ("CGPA", "8.1")]),
        "table.docx",
    )
    assert "Institution: Amrita Vishwa Vidyapeetham" in parsed.text
    assert "CGPA: 8.1" in parsed.text


# ---------------------------------------------------------------------------
#  Control characters
# ---------------------------------------------------------------------------


def test_control_characters_are_replaced_without_moving_an_offset():
    """A NUL in a text layer breaks JSON encoding and SQLite alike.

    Replaced one-for-one rather than stripped, because stripping moves every
    offset after it and this module's one gate is that offsets hold.
    """
    raw = "Built\x00a\x07thing"
    parsed = documents.parse(raw.encode("utf-8"), "weird.txt")
    assert len(parsed.text) == len(raw)
    assert "\x00" not in parsed.text

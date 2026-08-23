"""Bytes in, a text layer with geometry out (FR-1.1, FR-1.3, FR-1.4, FR-1.16).

── The trap this file exists to avoid ─────────────────────────────────────────

Spec §3.1, Trap 2: *"Two-column resumes. The single most common real-world
failure. Naive top-to-bottom text extraction interleaves the two columns into
word salad."*  Every downstream stage then fails in a way that looks like a
model problem and is a layout problem, so column detection happens HERE, before
a single character is concatenated.

Trap 1 is the other half: no model reads the document. A PDF is a bag of
positioned glyphs and turning it into a reading order is geometry, not
language. The model's job starts after this file has produced text we know the
offsets of.

── What "the text layer" means ────────────────────────────────────────────────

One string, and a `WordBox` for every word in it carrying the page and the
rectangle that word occupies. Every offset anywhere in this module — a section,
a claim, a quantifier, a redaction — indexes THAT string, and `geometry_for()`
turns any offset range back into a page and a box. That is what makes §8.3's
click-a-claim-highlight-the-PDF possible, and it is why the extraction cannot
be "get_text() and hope".

── Failing honestly ───────────────────────────────────────────────────────────

Every rejection here is an `IntakeError` carrying a sentence written for a
student (§10: "never a raw stack trace"). The paste path has no dependency on
any of this and always works, which is the fallback every named error points
at.
"""

from __future__ import annotations

import functools
import io
import logging
import os
import re
import statistics
import zipfile
from dataclasses import dataclass, field

from backend_M01_Resume_Ingestion import config

log = logging.getLogger("uvicorn.error")


class IntakeError(Exception):
    """A file we will not parse, and the sentence the student should read.

    `code` is for the client to branch on, `message` is for a human, and both
    are required: a 400 with a stack trace in the body is the failure §10 is
    written to prevent.
    """

    def __init__(self, code: str, message: str, *, status: int = 415) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class WordBox:
    """One word, where it sits in the text layer and where it sits on the page."""

    page: int
    start: int
    end: int
    #: (x0, y0, x1, y1) in PDF points, origin top-left.
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class LineStyle:
    """How a line is SET, which is half of what makes it a heading (§6.3).

    The spec scores a candidate heading on "font size z-score > 1.0 vs body ·
    bold · ALL CAPS · ends without punctuation · < 5 words · followed by a
    blank line · matches a heading lexicon" — seven signals, of which the
    lexicon is one. Reading only the lexicon means a heading in a vocabulary
    nobody anticipated is invisible however obviously it is set, and every
    resume template invents one.

    Carried per line-start-offset so the segmenter can ask about a line without
    knowing anything about PDFs.
    """

    size: float
    bold: bool
    #: How many standard deviations above the document's body text this is.
    size_z: float = 0.0

    @property
    def looks_like_a_heading(self) -> bool:
        """Typographic evidence alone, before any word is read."""
        return self.bold or self.size_z > 1.0


@dataclass
class Document:
    """A parsed document, and everything we noticed while parsing it."""

    text: str
    mime: str
    page_count: int = 1
    words: list[WordBox] = field(default_factory=list)
    #: Offset of a line's first character -> how that line is set. Empty for
    #: everything except PDFs, which are the only source that carries type.
    line_styles: dict[int, LineStyle] = field(default_factory=dict)
    #: 1 = single column. Two-column resumes are the case this is here for.
    columns: int = 1
    column_confidence: float = 1.0
    ocr_used: bool = False
    #: Pages beyond `config.MAX_PAGES` that were not read (§6.1, EC-1.5).
    pages_skipped: int = 0
    #: Student-facing sentences: what we noticed, in words they can act on.
    notes: list[str] = field(default_factory=list)
    #: EC-1.6. Every lexicon in this module is English; a resume that is not
    #: parses to almost nothing, and it must not do so silently.
    language: str = "en"
    language_confidence: float = 0.0

    @property
    def confidence_penalty(self) -> float:
        """How much to discount every confidence in this document.

        OCR output is a reading of a picture of a document. Everything derived
        from it is exactly that much less certain, and saying so once here
        beats each downstream stage remembering to.
        """
        return config.OCR_CONFIDENCE_PENALTY if self.ocr_used else 0.0

    def geometry_for(
        self, start: int, end: int
    ) -> tuple[int, tuple[float, float, float, float] | None]:
        """(page, bounding box) for an offset range, or (1, None) with no geometry.

        The box is the union of every word the range touches, which is what
        makes a highlight cover a wrapped bullet rather than only its first
        line. Pasted text has no geometry at all and says so with `None` rather
        than with a plausible-looking zero rectangle.
        """
        touched = [w for w in self.words if w.start < end and w.end > start]
        if not touched:
            return 1, None
        page = touched[0].page
        same_page = [w for w in touched if w.page == page]
        return page, (
            min(w.bbox[0] for w in same_page),
            min(w.bbox[1] for w in same_page),
            max(w.bbox[2] for w in same_page),
            max(w.bbox[3] for w in same_page),
        )


# ---------------------------------------------------------------------------
#  Intake: what IS this (§6.1)
# ---------------------------------------------------------------------------

#: Magic bytes, not the extension. A student who renamed `report.docx` to
#: `resume.pdf` because a portal demanded a PDF is a real person, and the
#: extension is the one part of a filename anyone edits.
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_RTF_MAGIC = b"{\\rtf"


def sniff(data: bytes, filename: str | None = None) -> str:
    """The MIME type of `data`, by content. Raises `IntakeError` for the rest."""
    if not data:
        # EC-1.16, and caught here rather than three stages later where it
        # presents as "no sections found".
        raise IntakeError(
            "empty_file",
            "That file is empty. Try exporting it again, or paste the text instead.",
            status=422,
        )
    if len(data) > config.MAX_UPLOAD_BYTES:
        megabytes = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise IntakeError(
            "too_large",
            f"That file is over {megabytes} MB. A resume should be well under that — "
            "if it has embedded images, export it again without them.",
            status=413,
        )

    head = data[:2048]

    if head.startswith(_PDF_MAGIC):
        return "application/pdf"

    if head.startswith(_ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise IntakeError(
                "corrupt_file",
                "I could not open that file — it looks damaged. "
                "Try re-saving it, or paste the text instead.",
                status=422,
            ) from exc
        if "word/document.xml" in names:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        raise IntakeError(
            "unsupported_type",
            "That is a zip archive, not a resume. Upload the PDF or .docx inside it.",
        )

    if head.startswith(_OLE_MAGIC):
        # Spec §6.1, named verbatim.
        raise IntakeError(
            "legacy_doc",
            "Please save as PDF or .docx — the old .doc format can't be read reliably.",
        )

    if head.startswith(_RTF_MAGIC):
        raise IntakeError(
            "unsupported_type",
            "RTF is not supported. Save as PDF or .docx, or paste the text instead.",
        )

    # Anything that decodes cleanly is text. Tried last so a PDF with a stray
    # ASCII header never reaches it.
    for encoding in ("utf-8", "utf-16", "cp1252"):
        try:
            data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        return "text/plain"

    name = f" ({filename})" if filename else ""
    raise IntakeError(
        "unsupported_type",
        f"I cannot read that file type{name}. Upload a PDF or .docx, "
        "or paste the text and I will take it from there.",
    )


# ---------------------------------------------------------------------------
#  Column detection (§6.2.2, FR-1.4)
# ---------------------------------------------------------------------------


def _line_tolerance(boxes: list[tuple]) -> float:
    """Half a median line height (§6.2.3).

    A PDF idea of a line is a per-glyph run, so a superscript or a bolded word
    arrives with a slightly different baseline. Merging within this tolerance
    is what stops one visual line becoming three.
    """
    heights = [b[3] - b[1] for b in boxes if b[3] > b[1]]
    return (statistics.median(heights) if heights else 10.0) * config.LINE_MERGE_TOLERANCE


def _group_lines(items: list[tuple], tolerance: float) -> list[list[tuple]]:
    """Boxes grouped into visual lines, top to bottom, each sorted left to right.

    Done BEFORE any column reasoning, because whether a line is a full-width
    banner or two columns sharing a y is the question column detection needs
    answered first.
    """
    ordered = sorted(items, key=lambda b: ((b[1] + b[3]) / 2, b[0]))
    lines: list[list[tuple]] = []
    current: list[tuple] = []
    centre: float | None = None

    for box in ordered:
        box_centre = (box[1] + box[3]) / 2
        if centre is None or abs(box_centre - centre) <= tolerance:
            current.append(box)
            centre = box_centre if centre is None else (centre + box_centre) / 2
        else:
            lines.append(sorted(current, key=lambda b: b[0]))
            current = [box]
            centre = box_centre
    if current:
        lines.append(sorted(current, key=lambda b: b[0]))
    return lines


def _is_full_width(line: list[tuple], page_width: float) -> bool:
    """Is this line a banner running the whole page, rather than a column line?

    Two conditions, and the second is what makes it discriminating:

      · it spans most of the page, AND
      · it has no internal gap wide enough to BE a gutter.

    A name-and-contact header satisfies both. Two column lines that happen to
    share a y coordinate satisfy the first and fail the second, because the
    gutter between them is exactly the gap being looked for.
    """
    if len(line) < 2:
        return False
    extent = line[-1][2] - line[0][0]
    if extent < page_width * 0.55:
        return False
    biggest_gap = max(
        (right[0] - left[2] for left, right in zip(line, line[1:], strict=False)),
        default=0.0,
    )
    return biggest_gap < page_width * config.COLUMN_MIN_GAP_FRACTION


def _full_width_boxes(
    boxes: list[tuple[float, float, float, float]], page_width: float
) -> list[tuple[float, float, float, float]]:
    """Every box belonging to a full-width line."""
    tolerance = _line_tolerance(boxes)
    out: list[tuple[float, float, float, float]] = []
    for line in _group_lines(list(boxes), tolerance):
        if _is_full_width(line, page_width):
            out.extend(line)  # type: ignore[arg-type]
    return out


def detect_columns(
    boxes: list[tuple[float, float, float, float]],
    page_width: float,
    page_height: float,
) -> tuple[list[float], float]:
    """Column boundaries as x coordinates, and how sure we are.

    Projects word x-midpoints onto the x axis, bins them, and looks for a
    vertical corridor of near-zero density: a gutter. A gutter has to be wide
    (≥ 8% of the page) AND tall, because a wide gap over three lines is an
    indented heading and shredding a table into columns is worse than reading
    it in one pass.

    ── One deliberate departure from §6.2.2 ────────────────────────────────

    The spec measures the gutter against "≥ 60% of page height". Taken
    literally that is measured against the PAGE, and a one-page resume whose
    text stops two thirds down — which is most of them — can never clear the
    bar however cleanly it is split into columns. Measured the other way it is
    worse: on a document with text in only the top fifth, the corridor is
    trivially empty across the blank remainder and every indented heading
    becomes a column boundary.

    So the denominator here is the TEXT BAND — the vertical extent of the
    words actually on the page — and the corridor has to be clear across 60%
    of that, with real text on both sides of it. That is the property §6.2.2
    is reaching for ("near-zero density spanning the height"), stated in terms
    that survive a short resume and still reject a heading indent. A full-width
    header line above two columns crosses the corridor for a slice or two and
    costs a little coverage, which is correct: it is evidence against, just not
    enough of it.

    Returns `([], confidence)` for a single column. Two or more boundaries is
    rare enough on a resume to be suspicious, so §6.2.2 says treat it as one
    column with lowered confidence — under-splitting loses reading order,
    over-splitting loses the text.

    ── Full-width lines are excluded from the histogram ────────────────────

    This is the second thing a real resume broke. Almost every one of them
    opens with a name-and-contact line running the whole width of the page:

        PRIYA SHARMA · priya@example.com · +91 98765 43210 · github.com/priyash

    Its words land in the gutter bins. The near-zero corridor is then not
    near-zero, the density gap disappears, and a perfectly clean two-column
    resume is read as one column — which is Trap 2 happening for a reason that
    has nothing to do with the columns.

    So the histogram is built from BODY lines only. A line is full-width when
    it spans most of the page with no internal gap wide enough to be a gutter,
    which is a description of a banner and not of two column lines that happen
    to share a y coordinate. Those lines are still read, and read first — see
    `_reading_order`, which treats each one as a band boundary.
    """
    if len(boxes) < 12 or page_width <= 0 or page_height <= 0:
        return [], 1.0

    banners = set(_full_width_boxes(boxes, page_width))
    body = [box for box in boxes if box not in banners]
    if len(body) < 12:
        return [], 1.0

    bins = config.COLUMN_BINS
    width = page_width / bins
    density = [0] * bins
    for x0, _y0, x1, _y1 in body:
        index = min(bins - 1, max(0, int(((x0 + x1) / 2) / width)))
        density[index] += 1

    # Runs of empty bins that are not the page margins.
    gaps: list[tuple[int, int]] = []
    start: int | None = None
    for index, count in enumerate(density):
        if count == 0:
            start = index if start is None else start
        elif start is not None:
            gaps.append((start, index))
            start = None
    if start is not None:
        gaps.append((start, bins))

    min_bins = max(1, round(bins * config.COLUMN_MIN_GAP_FRACTION))
    boundaries: list[float] = []
    best_coverage = 0.0

    # Measured over the BODY. A banner sits above the columns and its slices
    # would otherwise be counted as evidence that they are not there.
    top = min(b[1] for b in body)
    bottom = max(b[3] for b in body)
    band = bottom - top
    if band <= 0:
        return [], 1.0

    slices = 20
    slice_height = band / slices

    for first, last in gaps:
        if first == 0 or last == bins:
            continue  # a margin, not a gutter
        if last - first < min_bins:
            continue
        x = ((first + last) / 2) * width

        left = [b for b in body if (b[0] + b[2]) / 2 < x]
        right = [b for b in body if (b[0] + b[2]) / 2 >= x]
        if len(left) < 6 or len(right) < 6:
            continue

        # The REAL corridor, from the words rather than from the bin edges.
        #
        # The empty-bin run is wider than the gutter whenever a column does not
        # fill its box — which is always, because a heading is shorter than a
        # bullet. Using the bin edges as the corridor made an ordinary
        # left-column word ("Vidyapeetham", ending well inside the run) count
        # as spanning the gutter, and enough of those dragged coverage under
        # the bar on exactly the layout this is for.
        gutter_from = max(b[2] for b in left)
        gutter_to = min(b[0] for b in right)
        if gutter_to - gutter_from < page_width * config.COLUMN_MIN_GAP_FRACTION:
            continue

        # A slice counts when both columns have text in it and nothing spans
        # the corridor. A full-width header line fails its own slice and no
        # more. Slices with no text at all are not evidence either way, so they
        # leave the denominator rather than counting against — otherwise a
        # blank band between a header and the columns quietly vetoes the split.
        clear = 0
        occupied = 0
        for index in range(slices):
            y0 = top + index * slice_height
            y1 = y0 + slice_height
            here = [b for b in body if b[1] < y1 and b[3] > y0]
            if not here:
                continue
            occupied += 1
            crosses = any(b[0] < gutter_to and b[2] > gutter_from for b in here)
            both = any((b[0] + b[2]) / 2 < x for b in here) and any(
                (b[0] + b[2]) / 2 >= x for b in here
            )
            if both and not crosses:
                clear += 1

        coverage = clear / occupied if occupied else 0.0
        if coverage < config.COLUMN_MIN_VERTICAL_COVERAGE:
            continue
        boundaries.append(x)
        best_coverage = max(best_coverage, coverage)

    if not boundaries:
        return [], 1.0
    if len(boundaries) > 1:
        # §6.2.2: "≥2 → rare; treat as single column and lower confidence
        # (safer to under-split than to shred a table)."
        return [], 0.35
    return boundaries, round(min(1.0, 0.55 + 0.45 * best_coverage), 3)


def _reading_order(
    words: list[tuple[float, float, float, float, str]],
    boundaries: list[float],
    page_width: float,
) -> list[list[tuple[float, float, float, float, str]]]:
    """Lines in the order a person reads them (§6.2.3).

    ── Bands, not columns ──────────────────────────────────────────────────

    Sorting every word into one of two column buckets is the obvious
    implementation and it is wrong for the layout every resume actually has:

        ┌─────────────────────────────────────┐
        │  PRIYA SHARMA · priya@example.com   │  ← banner, spans both
        ├──────────────────┬──────────────────┤
        │  EDUCATION       │  SKILLS          │
        │  PROJECTS        │  Python, Java    │  ← two columns
        └──────────────────┴──────────────────┘

    Bucketed by x-midpoint, "priya@example.com" is far enough right to land in
    the RIGHT column — so the student's name and their email end up in
    different places, and whichever column is read second gets an email address
    inserted into the middle of its skills list.

    So a full-width line is a BAND BOUNDARY. The page becomes a sequence of
    bands: banner, then a two-column region, then any later banner, and each
    band is read in its own order. That is what a person does, and it is what
    makes the name come out on line one where entity extraction looks for it.
    """
    tolerance = _line_tolerance(words)
    lines = _group_lines(list(words), tolerance)

    if not boundaries:
        return [sorted(line, key=lambda w: w[0]) for line in lines]  # type: ignore[arg-type]

    ordered: list[list] = []
    column_band: list[list] = []

    def flush() -> None:
        """Emit the pending two-column region, column by column.

        Each visual line is SPLIT at the boundary first. Two columns whose
        first entries sit at the same height — "EDUCATION" beside "SKILLS",
        which is what every two-column resume looks like at the top — are one
        line geometrically and two lines to a reader. Bucketing the line whole,
        by its midpoint, keeps them glued together and produces exactly the
        word salad this function exists to prevent, with the columns correctly
        detected.
        """
        if not column_band:
            return
        buckets: list[list[list]] = [[] for _ in range(len(boundaries) + 1)]
        for line in column_band:
            segments: list[list] = [[] for _ in range(len(boundaries) + 1)]
            for word in line:
                middle = (word[0] + word[2]) / 2
                segments[sum(1 for edge in boundaries if middle >= edge)].append(word)
            for index, segment in enumerate(segments):
                if segment:
                    buckets[index].append(segment)
        for bucket in buckets:
            ordered.extend(bucket)
        column_band.clear()

    for line in lines:
        if _is_full_width(line, page_width):
            flush()
            ordered.append(sorted(line, key=lambda w: w[0]))
        else:
            column_band.append(sorted(line, key=lambda w: w[0]))
    flush()

    return ordered  # type: ignore[return-value]


def _type_by_position(page) -> dict[tuple[int, int], tuple[float, bool]]:
    """(rounded x, rounded y) -> (font size, bold) for every span on the page.

    PyMuPDF's `words` output carries geometry and no typography; `dict` output
    carries both but is a nested structure that is awkward to read positionally.
    So the spans are read once into a lookup keyed on rounded coordinates, and
    a word finds its own type by asking where it is.

    Rounded to whole points because a span's bounding box and a word's are
    computed slightly differently and an exact match never hits.
    """
    styles: dict[tuple[int, int], tuple[float, bool]] = {}
    try:
        data = page.get_text("dict")
    except Exception:  # pragma: no cover - a page that will not render as dict
        return styles

    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span.get("bbox")
                if not bbox:
                    continue
                size = float(span.get("size", 0.0))
                # PyMuPDF sets bit 4 of `flags` for a bold face, and many PDFs
                # only say so in the font name.
                bold = (
                    bool(int(span.get("flags", 0)) & 2**4)
                    or "bold" in str(span.get("font", "")).casefold()
                )
                styles[(round(bbox[0]), round(bbox[1]))] = (size, bold)
    return styles


def _line_style(
    line: list[tuple], styles: dict[tuple[int, int], tuple[float, bool]], body_size: float
) -> LineStyle | None:
    """How this line is set, relative to the document's body text."""
    found = [styles.get((round(word[0]), round(word[1]))) for word in line]
    present = [f for f in found if f is not None]
    if not present:
        return None
    size = max(f[0] for f in present)
    bold = any(f[1] for f in present)
    z = ((size - body_size) / body_size * 4.0) if body_size else 0.0
    return LineStyle(size=size, bold=bold, size_z=round(z, 2))


def _body_size(styles: dict[tuple[int, int], tuple[float, bool]]) -> float:
    """The size most of the document is set in.

    The MODE, not the mean: a resume with a 24pt name and 130 lines of 10pt
    body has a mean pulled upward by the one thing that is not body text, and
    the z-score of every heading then collapses toward zero.
    """
    if not styles:
        return 0.0
    counts: dict[float, int] = {}
    for size, _bold in styles.values():
        rounded = round(size, 1)
        counts[rounded] = counts.get(rounded, 0) + 1
    return max(counts.items(), key=lambda pair: pair[1])[0]


def _column_margins(lines: list[list[tuple]], boundaries: list[float]) -> list[float]:
    """The left edge of each column, so an indent can be measured against it.

    The leftmost line in a column, not the leftmost word on the page: in a
    two-column layout the right column starts 300pt in, and measuring its
    indents from the page margin would make every one of its lines look like a
    deep continuation of nothing.
    """
    margins = [float("inf")] * (len(boundaries) + 1)
    for line in lines:
        index = sum(1 for edge in boundaries if (line[0][0] + line[0][2]) / 2 >= edge)
        margins[index] = min(margins[index], line[0][0])
    return [0.0 if margin == float("inf") else margin for margin in margins]


# ---------------------------------------------------------------------------
#  PDF (§6.2)
# ---------------------------------------------------------------------------


def parse_pdf(data: bytes) -> Document:
    """A PDF text layer, in reading order, with a box for every word."""
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise IntakeError(
            "pdf_unavailable",
            "PDF reading is not available on this server right now. "
            "Paste the text instead — that path always works.",
            status=503,
        ) from exc

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise IntakeError(
            "corrupt_file",
            "I could not open that PDF — it looks damaged. "
            "Try exporting it again, or paste the text instead.",
            status=422,
        ) from exc

    if document.needs_pass:
        document.close()
        raise IntakeError(
            "password_protected",
            "That PDF is password-protected. Remove the password and re-upload it.",
            status=422,
        )

    total_pages = document.page_count
    read_pages = min(total_pages, config.MAX_PAGES)
    notes: list[str] = []
    if total_pages > read_pages:
        notes.append(
            f"This is {total_pages} pages. I read the first {read_pages} — "
            "if the part you want me to see is further in, move it up or paste it."
        )

    chunks: list[str] = []
    words: list[WordBox] = []
    line_styles: dict[int, LineStyle] = {}
    columns_seen = 1
    confidences: list[float] = []
    offset = 0

    for number in range(read_pages):
        page = document[number]
        rect = page.rect
        # (x0, y0, x1, y1, word, block_no, line_no, word_no)
        raw = page.get_text("words")
        boxes = [(w[0], w[1], w[2], w[3]) for w in raw]
        type_at = _type_by_position(page)
        boundaries, confidence = detect_columns(boxes, rect.width, rect.height)
        confidences.append(confidence)
        columns_seen = max(columns_seen, len(boundaries) + 1)

        lines = _reading_order(
            [(w[0], w[1], w[2], w[3], w[4]) for w in raw], boundaries, rect.width
        )
        # Indentation is geometric in a PDF and textual everywhere else.
        #
        # `- Built a route planner in Python using` and its continuation
        # `dynamic programming; cut query time from 380ms to 45ms` are one
        # bullet on the page, held together by a hanging indent that exists
        # only as an x coordinate. Emitted flush left, they become two claims,
        # and the second half — the half with the measurement in it — is
        # scored as a bullet with no verb. §6.5.1 asks for the merge, and the
        # merge is a text rule, so the indent has to survive as text.
        # One space, in points. `_line_tolerance` is half a median glyph
        # height, and a space advance is about a quarter of a glyph height —
        # so half the tolerance. Deriving it from the line height instead
        # made the unit roughly 2.4× too wide, and a real three-space hanging
        # indent came out as one space: under the two the continuation rule
        # needs, so no wrapped bullet ever merged on the PDF path.
        indent_unit = max(1.5, _line_tolerance(list(raw)) * 0.5)
        margins = _column_margins(lines, boundaries)
        body_size = _body_size(type_at)

        for line in lines:
            margin = margins[sum(1 for edge in boundaries if (line[0][0] + line[0][2]) / 2 >= edge)]
            spaces = min(12, round((line[0][0] - margin) / indent_unit))
            if spaces > 0:
                chunks.append(" " * spaces)
                offset += spaces

            # Recorded at the offset of the line's FIRST character, which is
            # what the segmenter has when it is looking at a candidate heading.
            style = _line_style(line, type_at, body_size)
            if style is not None:
                line_styles[offset] = style

            for index, word in enumerate(line):
                if index:
                    chunks.append(" ")
                    offset += 1
                text = word[4]
                words.append(
                    WordBox(
                        page=number + 1,
                        start=offset,
                        end=offset + len(text),
                        bbox=(word[0], word[1], word[2], word[3]),
                    )
                )
                chunks.append(text)
                offset += len(text)
            chunks.append("\n")
            offset += 1
        chunks.append("\n")
        offset += 1

    document.close()

    # §6.2.4. Appended rather than spliced: every offset above is committed,
    # and inserting mid-layer would move every span already recorded.
    tables = extract_tables(data, read_pages)
    if tables:
        chunks.append("\n".join(tables))
        chunks.append("\n")

    text = "".join(chunks)
    column_confidence = min(confidences) if confidences else 1.0
    if columns_seen > 1:
        notes.append(
            "This looks like a two-column layout. Check on the next screen that "
            "I read the columns in the right order."
            if column_confidence >= config.COLUMN_CONFIDENCE_WARN_BELOW
            else "I struggled with the column layout on this one — please check what I read."
        )

    return Document(
        text=text,
        mime="application/pdf",
        page_count=read_pages,
        words=words,
        line_styles=line_styles,
        columns=columns_seen,
        column_confidence=column_confidence,
        pages_skipped=total_pages - read_pages,
        notes=notes,
    )


# ---------------------------------------------------------------------------
#  DOCX (§6.2.4 — tables become key: value lines)
# ---------------------------------------------------------------------------


def parse_docx(data: bytes) -> Document:
    """A .docx paragraphs and tables, in document order.

    A table cell-pair becomes `key: value` rather than two bare cells on one
    line, because a two-column "Institution | Amrita" table is how half the
    Canva templates lay out education, and flattening it loses which is which.
    """
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise IntakeError(
            "docx_unavailable",
            "DOCX reading is not available on this server right now. "
            "Paste the text instead — that path always works.",
            status=503,
        ) from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise IntakeError(
            "corrupt_file",
            "I could not open that .docx — it looks damaged. "
            "Try re-saving it, or paste the text instead.",
            status=422,
        ) from exc

    lines: list[str] = [paragraph.text.rstrip() for paragraph in document.paragraphs]

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            # Word repeats a merged cell across every column it spans.
            unique: list[str] = []
            for cell in cells:
                if not unique or unique[-1] != cell:
                    unique.append(cell)
            unique = [c for c in unique if c]
            if len(unique) == 2:
                lines.append(f"{unique[0]}: {unique[1]}")
            elif unique:
                lines.append(" | ".join(unique))

    text = "\n".join(lines)
    return Document(
        text=text,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        page_count=max(1, text.count("\f") + 1),
    )


# ---------------------------------------------------------------------------
#  OCR (§6.2.6, FR-1.16, EC-1.2)
# ---------------------------------------------------------------------------


def extract_tables(data: bytes, read_pages: int) -> list[str]:
    """Tables as `key: value` lines (§6.2.4, EC-1.15).

    *"If a region is a table, extract cell-wise and emit as `key: value` lines
    rather than raw text."*

    Half the Canva and Word templates lay education out as a two-column table:
    `Institution | Amrita`, `CGPA | 8.1`. Read as flowed text those become one
    unreadable run, and the education section comes out as a single line nobody
    can parse a degree from. `pdfplumber` finds the ruled regions; PyMuPDF does
    the rest of the page.

    Returns lines to APPEND rather than splicing them into the text layer, and
    that is deliberate: every offset in the layer is already committed by the
    time this runs, and moving one to insert a table would break every span
    recorded so far. A table's cells therefore have no bbox — they are read for
    their content, not pointed at.
    """
    try:
        import pdfplumber
    except ImportError:
        log.info("M01 pdfplumber not installed; PDF tables are read as flowed text")
        return []

    lines: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:read_pages]:
                for table in page.extract_tables() or []:
                    for row in table:
                        cells = [str(c).strip() for c in row if c and str(c).strip()]
                        if len(cells) == 2:
                            lines.append(f"{cells[0]}: {cells[1]}")
                        elif len(cells) > 2:
                            lines.append(" | ".join(cells))
    except Exception as error:
        # A table we cannot read is not a parse failure. The page's flowed text
        # is already in the layer and is what the student mostly sees anyway.
        log.info("M01 table extraction skipped: %s", error)
        return []
    return lines


#: EC-1.6. Below this share of Latin characters the document is probably not
#: English, and everything downstream — the heading lexicon, the verb lexicon,
#: the alias table — is English-only.
_LATIN_SHARE_MIN = 0.60


def detect_language(text: str) -> tuple[str, float]:
    """(language code, confidence). EC-1.6.

    *"Detect language; if not English, offer to proceed with reduced accuracy,
    flag clearly."*

    Every lexicon in this module is English. A Hindi or Tamil resume parses to
    almost nothing, and without this it does so SILENTLY — indistinguishable
    from a resume with nothing on it, which is the failure mode this module
    keeps having to design against.

    A cheap script check runs first and is the one that matters: `langdetect`
    is probabilistic and occasionally calls an English resume Afrikaans on the
    strength of a few proper nouns, whereas "almost none of these characters
    are Latin" is not a judgement call.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 40:
        return "unknown", 0.0

    latin = sum(1 for ch in letters if ch.isascii())
    share = latin / len(letters)
    if share < _LATIN_SHARE_MIN:
        return "non-latin", round(1.0 - share, 2)

    try:
        from langdetect import DetectorFactory, detect_langs

        # Without this the library is non-deterministic run to run, and a parse
        # that flags a resume as Croatian only on Tuesdays is worse than one
        # that never flags anything.
        DetectorFactory.seed = 0
        best = detect_langs(text[:4000])[0]
        return best.lang, round(best.prob, 2)
    except Exception:
        return "en", 0.5


def _language_notes(language: str) -> list[str]:
    """EC-1.6: "offer to proceed with reduced accuracy, flag clearly".

    The flag IS the offer — nothing is blocked. The student is told why the
    read is thin instead of concluding the parser is broken.
    """
    if language in {"en", "unknown"}:
        return []
    return [
        "This does not look like it is written in English. I read it anyway, but every "
        "list of words I match against is English, so expect to add a lot by hand."
    ]


def ocr_available() -> bool:
    """Whether an OCR engine is installed on this deployment.

    Reported rather than assumed. §6.2.6 specifies PaddleOCR, which is a
    several-hundred-megabyte dependency that most developers of this module do
    not have and every CI run would pay for. So the seam is here, the pipeline
    routes into it, and its ABSENCE is a named, student-facing failure with the
    paste path as the way out — never a silent empty parse, which is the exact
    thing EC-1.2 exists to prevent.
    """
    return _paddle_available() or _tesseract_available()


def _paddle_available() -> bool:
    """PaddleOCR AND the engine underneath it.

    `pip install paddleocr` succeeds without `paddlepaddle` — the wrapper
    installs, the engine does not, and importing the wrapper alone is enough to
    make a naive check say yes. It then fails at the first page, which is the
    "control that looks live and does nothing" failure §2.4 lists as a quit
    trigger, moved from the UI into the backend.
    """
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in ("paddleocr", "paddle"))


def _tesseract_available() -> bool:
    """pytesseract AND a Tesseract binary on PATH.

    Same trap in the other direction: `pytesseract` is a thin wrapper over a
    command-line program that pip cannot install. Present without the binary,
    it raises `TesseractNotFoundError` on the first call.
    """
    import importlib.util
    import shutil

    if importlib.util.find_spec("pytesseract") is None:
        return False
    return shutil.which("tesseract") is not None


def ocr_pdf(data: bytes) -> Document:
    """Render each page and read it as an image (FR-1.16).

    Every confidence downstream is reduced by `OCR_CONFIDENCE_PENALTY`, and the
    student is told the reading came from a picture (EC-1.2) — because a
    mis-read they cannot see the cause of is the failure that makes them leave.
    """
    if not ocr_available():
        raise IntakeError(
            "no_text_layer",
            "This PDF is a scan — there is no text in it to read, and OCR is not "
            "available on this server. Paste the text instead and I will take it from there.",
            status=422,
        )

    import pymupdf

    # An OCR engine that is INSTALLED and does not RUN is the worst of the
    # three states, because every check short of trying it says yes.
    # PaddlePaddle raises `ConvertPirAttribute2RuntimeAttribute not support` on
    # some CPU/version combinations; a missing model download raises something
    # else again. None of it is a reason to hand a student a stack trace, and
    # all of it means the same thing to them — so it collapses to the same
    # named error the missing-engine case already produces.
    try:
        engine = _ocr_engine()
    except Exception as error:
        log.error("M01 OCR engine failed to start: %s", error)
        raise IntakeError(
            "ocr_unavailable",
            "This PDF is a scan, and the text reader on this server would not start. "
            "Paste the text instead and I will take it from there.",
            status=422,
        ) from error

    document = pymupdf.open(stream=data, filetype="pdf")
    read_pages = min(document.page_count, config.MAX_PAGES)
    chunks: list[str] = []

    for number in range(read_pages):
        # 300 DPI (§6.2.6). PDF user space is 72 dpi, hence the 300/72 zoom.
        pixmap = document[number].get_pixmap(matrix=pymupdf.Matrix(300 / 72, 300 / 72))
        try:
            chunks.append(engine(pixmap.tobytes("png")))
        except Exception as error:
            document.close()
            log.error("M01 OCR failed on page %d: %s", number + 1, error)
            raise IntakeError(
                "ocr_failed",
                "I could not read this scan. Paste the text instead — that path always works.",
                status=422,
            ) from error
        chunks.append("\n\n")

    pages = read_pages
    skipped = document.page_count - read_pages
    document.close()

    return Document(
        text="".join(chunks),
        mime="application/pdf",
        page_count=pages,
        ocr_used=True,
        pages_skipped=skipped,
        notes=[
            "I read this from an image rather than from text, so double-check "
            "what I got — especially numbers and technology names."
        ],
    )


@functools.lru_cache(maxsize=1)
def _ocr_engine():
    """Whichever engine is installed, behind one `bytes -> str` call.

    Cached, because building a PaddleOCR reader loads several models and takes
    seconds. Uncached, a two-page scan paid that twice and FR-1.18's budget
    went with it.

    ── Two APIs, one adapter ───────────────────────────────────────────────

    PaddleOCR 3.x dropped `use_angle_cls` / `show_log` from the constructor and
    changed what `ocr()` returns — 2.x gives nested `[[box, (text, score)]]`,
    3.x gives a list of dicts with `rec_texts`. The spec was written against
    2.x. Both are handled rather than pinning to one, because a deployment that
    already has Paddle installed for another module should not need a
    downgrade to run this one.
    """
    if _paddle_available():
        from paddleocr import PaddleOCR

        # oneDNN off, deliberately.
        #
        # PaddlePaddle's oneDNN path raises `ConvertPirAttribute2RuntimeAttribute
        # not support` on some CPU/version combinations — including the machine
        # this was built on. It is a Paddle bug, it is not detectable before
        # inference, and the fallback kernels produce the same text a little
        # slower. A resume is one page: slower is free, and crashing is not.
        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        try:  # 3.x
            reader = PaddleOCR(lang="en", enable_mkldnn=False)
        except (TypeError, ValueError):  # 2.x
            reader = PaddleOCR(use_angle_cls=True, lang="en", show_log=False, enable_mkldnn=False)

        def run(png: bytes) -> str:
            import numpy as np
            from PIL import Image

            image = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
            try:
                result = reader.predict(image)  # 3.x
            except AttributeError:
                result = reader.ocr(image)  # 2.x
            return _paddle_text(result or [])

        return run

    import pytesseract
    from PIL import Image

    return lambda png: pytesseract.image_to_string(Image.open(io.BytesIO(png)))


def _paddle_text(result) -> str:
    """Lines out of whichever shape this Paddle version returned."""
    lines: list[str] = []
    for page in result:
        # 3.x: a dict-like with `rec_texts`.
        texts = page.get("rec_texts") if hasattr(page, "get") else None
        if texts:
            lines.extend(str(t) for t in texts)
            continue
        # 2.x: [[box, (text, score)], ...]
        if isinstance(page, list):
            for entry in page:
                try:
                    lines.append(str(entry[1][0]))
                except (IndexError, TypeError):
                    continue
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  The entry point
# ---------------------------------------------------------------------------

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def parse(data: bytes, filename: str | None = None) -> Document:
    """Any supported upload to a text layer. Raises `IntakeError` otherwise.

    §10 ladder in one place: the text layer is tried first, OCR is the fallback
    when there is nothing in it (FR-1.16), and a named error with the paste path
    is what happens when both are impossible. There is no branch that returns an
    empty document quietly.
    """
    mime = sniff(data, filename)

    if mime == "application/pdf":
        document = parse_pdf(data)
        if len(document.text.strip()) < config.MIN_TEXT_LAYER_CHARS:
            log.info("M01 text layer was %d chars; trying OCR", len(document.text.strip()))
            document = ocr_pdf(data)
    elif mime.endswith("wordprocessingml.document"):
        document = parse_docx(data)
    else:
        document = parse_text(data)

    document.text = _CONTROL.sub(" ", document.text)
    document.language, document.language_confidence = detect_language(document.text)
    document.notes.extend(_language_notes(document.language))
    if not document.text.strip():
        raise IntakeError(
            "no_text_found",
            "I could not find any text in that file. Paste the text instead — "
            "that path always works.",
            status=422,
        )
    return document


def parse_text(data: bytes) -> Document:
    for encoding in ("utf-8", "utf-16", "cp1252"):
        try:
            return Document(text=data.decode(encoding), mime="text/plain")
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise IntakeError(
        "unsupported_type",
        "I could not decode that file as text. Paste the text instead.",
        status=422,
    )


def from_text(text: str) -> Document:
    """The always-works path (§7, §10). No file, no geometry, no dependency."""
    cleaned = _CONTROL.sub(" ", text)
    language, confidence = detect_language(cleaned)
    return Document(
        text=cleaned,
        mime="text/plain",
        language=language,
        language_confidence=confidence,
        # The note belongs here as well as in `parse`. Detection without it is
        # a field nobody reads: the student is told nothing, and the thin parse
        # still looks like a broken parser rather than a wrong lexicon.
        notes=list(_language_notes(language)),
    )

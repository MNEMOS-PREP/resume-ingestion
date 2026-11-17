"""Tailored copies over HTTP: make one, edit it, see it, download it.

Every route is under `/v1/resumes/{resume_id}/tailored/…` for two reasons.
`resumes` is M01's noun in the platform shell's proxy table, so nothing new has
to be routed; and the resume id in the path is what `enforce_access` already
resolves to its owner, so a copy is exactly as private as the resume it came
from — a guard on a new noun would be a guard somebody had to remember.

M02 (the job description module) is the main caller: it makes one copy per
job description, and its tailoring screen edits it through these routes. M01
never needs to know what a job description is — `target_ref` is opaque here.
"""

from __future__ import annotations

import hashlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any

from ai_core.identity import principal_from_headers
from ai_core.models import USER_AGENT
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend_M01_Resume_Ingestion import documents, tailor
from backend_M01_Resume_Ingestion.models import Resume
from backend_M01_Resume_Ingestion.rewrite import TargetedRewrite, reword_for_requirement
from backend_M01_Resume_Ingestion.router import _m04_url, _require, enforce_access, get_db
from backend_M01_Resume_Ingestion.storage import get_bytes as source_bytes
from backend_M01_Resume_Ingestion.tailor import (
    BlockInsert,
    BlockMove,
    BlockPatch,
    ChangeRefused,
    TailoredResume,
    TailoredRevision,
)

router = APIRouter(
    prefix="/v1",
    tags=["M01 Tailored resumes"],
    dependencies=[Depends(enforce_access)],
)


# ---------------------------------------------------------------------------
#  Shapes
# ---------------------------------------------------------------------------


class TailoredIn(BaseModel):
    label: str = ""
    target_kind: str = "jd"
    target_ref: str = ""


class PhotoState(BaseModel):
    """Which picture a copy prints, and whether the student wants it there."""

    #: `profile` (set in Settings), `original` (printed on the uploaded
    #: resume), or None — there is no picture to print.
    available: str | None
    #: The student's choice for THIS copy. A picture can be left off any one.
    enabled: bool
    #: Changes when the picture does; screens key their page images on it.
    digest: str | None


class StyleIn(BaseModel):
    photo: bool
    source: str = "manual"


class TailoredOut(BaseModel):
    id: uuid.UUID
    resume_id: uuid.UUID
    candidate_id: uuid.UUID
    label: str
    target_kind: str
    target_ref: str
    revision: int
    style: dict
    blocks: list[dict]
    #: How many blocks differ from the resume they were made from.
    edited: int
    #: The name on the page, for a default file name. None when masked.
    name: str | None
    #: The source resume's file name, for "made from …".
    filename: str | None
    #: The picture this copy prints, if any (2026-11-17).
    photo: PhotoState
    created_at: datetime
    updated_at: datetime


class RevisionOut(BaseModel):
    n: int
    action: str
    block_id: str | None
    before: str | None
    after: str | None
    source: str
    note: str | None
    created_at: datetime


class PageBox(BaseModel):
    page: int
    rect: list[float]
    start: int
    end: int


class LayoutOut(BaseModel):
    """Where every block landed on the PDF this revision produces."""

    revision: int
    pages: list[dict[str, float]]
    boxes: dict[str, list[PageBox]]


class EditIn(BlockPatch):
    #: The revision the editor was looking at. A mismatch is a 409, so two tabs
    #: on one copy cannot silently overwrite each other's lines.
    expect_revision: int | None = None


class RestoreIn(BaseModel):
    n: int
    source: str = "manual"


class RewriteIn(BaseModel):
    requirement: str
    jd_line: str | None = None
    #: Terms the student has said are true of this line (the requirement's
    #: name, when they confirmed they used it here). Nothing else may be added.
    allowed_terms: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _get(session: Session, resume_id: uuid.UUID, tailored_id: uuid.UUID) -> TailoredResume:
    row = session.get(TailoredResume, tailored_id)
    if row is None or row.resume_id != resume_id:
        raise HTTPException(status_code=404, detail="No such tailored resume for this resume.")
    return row


def _out(row: TailoredResume, resume: Resume | None) -> TailoredOut:
    blocks = [{**b, "edited": _edited(b), "locked": not tailor.editable(b)} for b in row.blocks]
    _, available, digest = _photo(row, resume)
    return TailoredOut(
        id=row.id,
        resume_id=row.resume_id,
        candidate_id=row.candidate_id,
        label=row.label,
        target_kind=row.target_kind,
        target_ref=row.target_ref,
        revision=row.revision,
        style=row.style,
        blocks=blocks,
        edited=tailor.edited_count(row.blocks),
        name=tailor.header_name(row.blocks),
        filename=resume.filename if resume else None,
        photo=PhotoState(
            available=available,
            enabled=bool(row.style.get("photo", True)),
            digest=digest if row.style.get("photo", True) else None,
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _edited(block: dict) -> bool:
    return bool(block.get("added")) or (block.get("text") or "") != (block.get("original") or "")


def _record(
    session: Session,
    row: TailoredResume,
    blocks: list[dict],
    *,
    action: str,
    block_id: str | None = None,
    before: str | None = None,
    after: str | None = None,
    source: str = "manual",
    note: str | None = None,
) -> None:
    row.revision += 1
    row.blocks = blocks
    row.updated_at = _now()
    session.add(row)
    session.add(
        TailoredRevision(
            tailored_id=row.id,
            n=row.revision,
            action=action,
            block_id=block_id,
            before=before,
            after=after,
            source=(source or "manual")[:200],
            note=(note or None) and note[:1000],
            blocks=blocks,
        )
    )
    session.commit()
    session.refresh(row)


def _source_pdf(resume: Resume) -> bytes | None:
    if not resume.source_sha256 or resume.mime != "application/pdf":
        return None
    return source_bytes(resume.source_sha256, suffix="pdf")


def _reveal(resume: Resume, blocks: list[dict]) -> dict[str, str]:
    """Real text for every masked block, from `raw_text` at the same offsets.

    Server-side only: it is what lines are measured against, and printed only
    in the student's own download.
    """
    out: dict[str, str] = {}
    for block in blocks:
        span = block.get("span")
        if block.get("masked") and span:
            out[block["id"]] = tailor.revealed_from(
                resume.redacted_text, resume.raw_text, (int(span[0]), int(span[1]))
            )
    return out


# ---------------------------------------------------------------------------
#  The picture (2026-11-17)
# ---------------------------------------------------------------------------

#: candidate -> (checked at, bytes or None, ETag). M04 is asked again after a
#: few seconds — with the ETag, so an unchanged picture costs a 304 — because a
#: page of a PDF is drawn several times a second while the student scrolls, and
#: a picture changed in Settings should reach the next draw, not one later.
_PROFILE_PHOTOS: dict[str, tuple[float, bytes | None, str | None]] = {}
_PROFILE_TTL = 3.0
#: source file digest -> the photo printed on it, or None. A file never changes.
_ORIGINAL_PHOTOS: dict[str, bytes | None] = {}


def _profile_photo(candidate_id: str) -> bytes | None:
    """The picture the student set in Settings, from M04 — or None.

    Identity is forwarded, as M02 forwards it here: M04 decides whether this
    student's picture may be read, and M01 never holds a key that could read
    anyone else's.
    """
    cached = _PROFILE_PHOTOS.get(candidate_id)
    if cached is not None and time.monotonic() - cached[0] < _PROFILE_TTL:
        return cached[1]
    url = _m04_url(f"/v1/candidates/{candidate_id}/photo")
    if url is None:
        _PROFILE_PHOTOS[candidate_id] = (time.monotonic(), None, None)
        return None
    headers = {"X-Role": "student", "X-Candidate-Id": candidate_id, "User-Agent": USER_AGENT}
    if cached is not None and cached[2]:
        headers["If-None-Match"] = cached[2]
    data: bytes | None = None
    etag: str | None = None
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=2.0) as response:
            body = response.read()
            if body[:3] == b"\xff\xd8\xff" or body[:8] == b"\x89PNG\r\n\x1a\n":
                data, etag = body, response.headers.get("ETag")
    except urllib.error.HTTPError as error:
        # 304: unchanged since last asked. 404: there is no picture.
        if error.code == 304 and cached is not None:
            data, etag = cached[1], cached[2]
    except Exception:  # noqa: BLE001 - no picture is a normal state, not an error
        data = None
    _PROFILE_PHOTOS[candidate_id] = (time.monotonic(), data, etag)
    return data


def _photo(
    row: TailoredResume, resume: Resume | None
) -> tuple[bytes | None, str | None, str | None]:
    """(bytes to print, where they came from, digest) for one copy.

    The picture set in Settings first; the photo on the uploaded resume when
    there is none. The bytes are None when the student turned it off for this
    copy — `available` still says what could be printed.
    """
    data = _profile_photo(str(row.candidate_id))
    available = "profile" if data else None
    if data is None and resume is not None and resume.source_sha256:
        if resume.source_sha256 not in _ORIGINAL_PHOTOS:
            _ORIGINAL_PHOTOS[resume.source_sha256] = tailor.original_photo(_source_pdf(resume))
        data = _ORIGINAL_PHOTOS[resume.source_sha256]
        available = "original" if data else None
    digest = hashlib.sha256(data).hexdigest()[:16] if data else None
    if not row.style.get("photo", True):
        return None, available, digest
    return data, available, digest


#: (tailored id, revision, printed contact, photo digest) -> Rendered. A
#: revision is never rewritten — every change makes a new one — so a hit is
#: always current; the photo digest covers a picture changed in Settings.
_RENDERS: dict[tuple[str, int, bool, str], tailor.Rendered] = {}
_RENDER_LIMIT = 24


def _rendered(session: Session, row: TailoredResume, *, print_contact: bool) -> tailor.Rendered:
    resume = session.get(Resume, row.resume_id)
    photo, _, digest = _photo(row, resume)
    key = (str(row.id), row.revision, print_contact, digest if photo else "")
    hit = _RENDERS.get(key)
    if hit is not None:
        return hit
    reveal = _reveal(resume, row.blocks) if resume else {}
    name = tailor.header_name(row.blocks)
    try:
        result = tailor.render(
            row.blocks,
            row.style,
            reveal=reveal,
            print_contact=print_contact,
            title=f"{name} — Resume" if name else "Resume",
            photo=photo,
        )
    except ImportError as error:
        raise HTTPException(
            status_code=503, detail="This deployment cannot make PDFs (PyMuPDF is missing)."
        ) from error
    if len(_RENDERS) >= _RENDER_LIMIT:
        _RENDERS.pop(next(iter(_RENDERS)))
    _RENDERS[key] = result
    return result


def _is_owner(request: Request, row: TailoredResume) -> bool:
    principal = principal_from_headers(dict(request.headers))
    return principal is not None and principal.is_self(str(row.candidate_id))


_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_filename(name: str | None, fallback: str = "resume") -> str:
    """A file name a browser and every OS will accept, ending in exactly `.pdf`."""
    base = (name or "").strip()
    while re.search(r"\.pdf\s*$", base, re.IGNORECASE):
        base = re.sub(r"\.pdf\s*$", "", base, flags=re.IGNORECASE).strip()
    base = _UNSAFE.sub("_", base).strip(" ._")
    base = re.sub(r"\s+", " ", base)[:120].strip(" ._")
    return f"{base or fallback}.pdf"


def _disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    quoted = urllib.parse.quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"


# ---------------------------------------------------------------------------
#  Make, list, read, delete
# ---------------------------------------------------------------------------


@router.post(
    "/resumes/{resume_id}/tailored",
    response_model=TailoredOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tailored(
    resume_id: uuid.UUID, payload: TailoredIn, session: Session = Depends(get_db)
) -> TailoredOut:
    """A copy of this resume for one target. Asking twice returns the same copy.

    Idempotent on `(resume, target)`: a caller that retries, or a second tab
    opening the same job, must find the student's edits rather than a fresh
    copy that quietly replaced them.
    """
    resume = _require(session, resume_id)
    if resume.parse_status not in {"ready", "needs_review"}:
        raise HTTPException(
            status_code=409,
            detail="This resume has not been read yet, so there is nothing to copy.",
        )
    if payload.target_ref:
        existing = session.exec(
            select(TailoredResume).where(
                TailoredResume.resume_id == resume_id,
                TailoredResume.target_kind == payload.target_kind,
                TailoredResume.target_ref == payload.target_ref,
            )
        ).first()
        if existing is not None:
            return _out(existing, resume)

    blocks = tailor.build_blocks(
        redacted=resume.redacted_text, sections=resume.sections, claims=resume.claims
    )
    if not blocks:
        raise HTTPException(status_code=422, detail="This resume has no text to tailor.")
    row = TailoredResume(
        resume_id=resume.id,
        candidate_id=resume.candidate_id,
        label=(payload.label or resume.filename or "Tailored resume")[:200],
        target_kind=payload.target_kind[:40],
        target_ref=payload.target_ref[:200],
        blocks=blocks,
        style=tailor.detect_style(_source_pdf(resume)),
    )
    session.add(row)
    session.add(
        TailoredRevision(tailored_id=row.id, n=0, action="created", source="manual", blocks=blocks)
    )
    session.commit()
    session.refresh(row)
    return _out(row, resume)


@router.get("/resumes/{resume_id}/tailored", response_model=list[TailoredOut])
def list_tailored(resume_id: uuid.UUID, session: Session = Depends(get_db)) -> list[TailoredOut]:
    """Every tailored copy of this resume, newest change first."""
    resume = _require(session, resume_id)
    rows = session.exec(
        select(TailoredResume)
        .where(TailoredResume.resume_id == resume_id)
        .order_by(TailoredResume.updated_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_out(row, resume) for row in rows]


@router.get("/resumes/{resume_id}/tailored/{tailored_id}", response_model=TailoredOut)
def get_tailored(
    resume_id: uuid.UUID, tailored_id: uuid.UUID, session: Session = Depends(get_db)
) -> TailoredOut:
    row = _get(session, resume_id, tailored_id)
    return _out(row, session.get(Resume, resume_id))


@router.delete(
    "/resumes/{resume_id}/tailored/{tailored_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_tailored(
    resume_id: uuid.UUID, tailored_id: uuid.UUID, session: Session = Depends(get_db)
) -> Response:
    """The copy and its history. The resume it was made from is untouched."""
    row = _get(session, resume_id, tailored_id)
    delete_copies(session, [row])
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def delete_copies(session: Session, rows: list[TailoredResume]) -> None:
    """Delete copies and their revisions. The caller commits."""
    for row in rows:
        for revision in session.exec(
            select(TailoredRevision).where(TailoredRevision.tailored_id == row.id)
        ).all():
            session.delete(revision)
        session.delete(row)


# ---------------------------------------------------------------------------
#  Changes — every one a revision
# ---------------------------------------------------------------------------


@router.patch(
    "/resumes/{resume_id}/tailored/{tailored_id}/blocks/{block_id}", response_model=TailoredOut
)
def edit_block(
    resume_id: uuid.UUID,
    tailored_id: uuid.UUID,
    block_id: str,
    payload: EditIn,
    session: Session = Depends(get_db),
) -> TailoredOut:
    """Retype, hide or show one block. Refused with a reason, never silently."""
    row = _get(session, resume_id, tailored_id)
    if payload.expect_revision is not None and payload.expect_revision != row.revision:
        raise HTTPException(
            status_code=409,
            detail="This copy changed since you opened it (another tab?). Reload to see the latest.",
        )
    try:
        blocks, action, before, after = tailor.apply_patch(row.blocks, block_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such line in this copy.") from None
    except ChangeRefused as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from None
    _record(
        session,
        row,
        blocks,
        action=action,
        block_id=block_id,
        before=before,
        after=after,
        source=payload.source,
        note=payload.note,
    )
    return _out(row, session.get(Resume, resume_id))


@router.post("/resumes/{resume_id}/tailored/{tailored_id}/blocks", response_model=TailoredOut)
def add_block(
    resume_id: uuid.UUID,
    tailored_id: uuid.UUID,
    payload: BlockInsert,
    session: Session = Depends(get_db),
) -> TailoredOut:
    """A line the STUDENT wrote. Nothing in this module writes one for them."""
    row = _get(session, resume_id, tailored_id)
    try:
        blocks, block = tailor.insert_block(row.blocks, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such line to add after.") from None
    except ChangeRefused as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from None
    _record(
        session,
        row,
        blocks,
        action="insert",
        block_id=block["id"],
        after=block["text"],
        source=payload.source,
        note=payload.note,
    )
    return _out(row, session.get(Resume, resume_id))


@router.post("/resumes/{resume_id}/tailored/{tailored_id}/move", response_model=TailoredOut)
def move(
    resume_id: uuid.UUID,
    tailored_id: uuid.UUID,
    payload: BlockMove,
    session: Session = Depends(get_db),
) -> TailoredOut:
    """Move a line, or a whole entry, within its section."""
    row = _get(session, resume_id, tailored_id)
    try:
        blocks = tailor.move_block(row.blocks, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such line in this copy.") from None
    except ChangeRefused as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from None
    moved = next((b for b in row.blocks if b["id"] == payload.block_id), {})
    _record(
        session,
        row,
        blocks,
        action="move",
        block_id=payload.block_id,
        before=moved.get("text"),
        source=payload.source,
        note=payload.note,
    )
    return _out(row, session.get(Resume, resume_id))


@router.patch("/resumes/{resume_id}/tailored/{tailored_id}/style", response_model=TailoredOut)
def set_style(
    resume_id: uuid.UUID,
    tailored_id: uuid.UUID,
    payload: StyleIn,
    session: Session = Depends(get_db),
) -> TailoredOut:
    """Print the photo on this copy, or leave it off. A version like any other."""
    row = _get(session, resume_id, tailored_id)
    if bool(row.style.get("photo", True)) == payload.photo:
        return _out(row, session.get(Resume, resume_id))
    row.style = {**row.style, "photo": payload.photo}
    _record(
        session,
        row,
        [dict(b) for b in row.blocks],
        action="style",
        after="photo on" if payload.photo else "photo off",
        source=payload.source,
    )
    return _out(row, session.get(Resume, resume_id))


@router.get(
    "/resumes/{resume_id}/tailored/{tailored_id}/revisions", response_model=list[RevisionOut]
)
def list_revisions(
    resume_id: uuid.UUID, tailored_id: uuid.UUID, session: Session = Depends(get_db)
) -> list[RevisionOut]:
    """The copy's history, newest first — what changed, why, and from where."""
    _get(session, resume_id, tailored_id)
    rows = session.exec(
        select(TailoredRevision)
        .where(TailoredRevision.tailored_id == tailored_id)
        .order_by(TailoredRevision.n.desc())  # type: ignore[attr-defined]
    ).all()
    return [
        RevisionOut(
            n=r.n,
            action=r.action,
            block_id=r.block_id,
            before=r.before,
            after=r.after,
            source=r.source,
            note=r.note,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/resumes/{resume_id}/tailored/{tailored_id}/restore", response_model=TailoredOut)
def restore(
    resume_id: uuid.UUID,
    tailored_id: uuid.UUID,
    payload: RestoreIn,
    session: Session = Depends(get_db),
) -> TailoredOut:
    """Back to revision `n` — as a NEW revision, so nothing after it is lost."""
    row = _get(session, resume_id, tailored_id)
    target = session.exec(
        select(TailoredRevision).where(
            TailoredRevision.tailored_id == tailored_id, TailoredRevision.n == payload.n
        )
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="No such version of this copy.")
    _record(
        session,
        row,
        [dict(b) for b in target.blocks],
        action="restore",
        after=f"version {payload.n}",
        source=payload.source,
    )
    return _out(row, session.get(Resume, resume_id))


# ---------------------------------------------------------------------------
#  The PDF: layout, page images, the file
# ---------------------------------------------------------------------------


@router.get("/resumes/{resume_id}/tailored/{tailored_id}/layout", response_model=LayoutOut)
def layout(
    resume_id: uuid.UUID, tailored_id: uuid.UUID, session: Session = Depends(get_db)
) -> LayoutOut:
    """Pages, and the rectangles every block occupies on them, in PDF points."""
    row = _get(session, resume_id, tailored_id)
    result = _rendered(session, row, print_contact=False)
    return LayoutOut(
        revision=row.revision,
        pages=[{"page": i + 1, "width": w, "height": h} for i, (w, h) in enumerate(result.pages)],
        boxes={k: [PageBox(**box) for box in v] for k, v in result.boxes.items()},
    )


@router.get("/resumes/{resume_id}/tailored/{tailored_id}/pages/{page}")
def page_image(
    resume_id: uuid.UUID,
    tailored_id: uuid.UUID,
    page: int,
    zoom: float = Query(2.0, ge=1.0, le=4.0),
    rev: int | None = Query(None, description="Cache key only; the current revision is drawn."),
    photo: str | None = Query(None, description="Cache key only: the photo digest the page shows."),
    session: Session = Depends(get_db),
) -> Response:
    """One page of the PDF as a PNG, contact details painted out (FR-1.17).

    Rasterised from the very file the download is, with its contact bars in
    place — so what the editor shows is the document, not a picture of one.
    """
    row = _get(session, resume_id, tailored_id)
    result = _rendered(session, row, print_contact=False)
    if page < 1 or page > len(result.pages):
        raise HTTPException(status_code=404, detail="No such page.")
    png = documents.render_page(result.pdf, page - 1, zoom=zoom)
    # Immutable only when the URL names exactly what was drawn: this revision
    # and this photo. Anything else is a page someone must not keep.
    _, _, digest = _photo(row, session.get(Resume, resume_id))
    drawn = digest if row.style.get("photo", True) else None
    fresh = rev == row.revision and (photo or None) == drawn
    cache = "private, max-age=86400, immutable" if fresh else "no-store"
    return Response(content=png, media_type="image/png", headers={"Cache-Control": cache})


@router.get("/resumes/{resume_id}/tailored/{tailored_id}/pdf")
def download_pdf(
    resume_id: uuid.UUID,
    tailored_id: uuid.UUID,
    request: Request,
    filename: str | None = None,
    session: Session = Depends(get_db),
) -> Response:
    """The file, generated from the latest revision — never a renamed old one.

    The student's own download prints their contact details; anyone else the
    guard lets through (staff) gets the bars, like every screen.
    """
    row = _get(session, resume_id, tailored_id)
    owner = _is_owner(request, row)
    result = _rendered(session, row, print_contact=owner)
    name = tailor.header_name(row.blocks) or "resume"
    fallback = re.sub(r"\s+", "_", name.strip().lower()) + "_resume"
    chosen = safe_filename(filename, fallback=fallback)
    return Response(
        content=result.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": _disposition(chosen),
            "Cache-Control": "no-store",
            "X-Revision": str(row.revision),
            "X-Contact": "printed" if owner else "masked",
        },
    )


# ---------------------------------------------------------------------------
#  A line worded for one requirement
# ---------------------------------------------------------------------------


@router.post(
    "/resumes/{resume_id}/tailored/{tailored_id}/blocks/{block_id}/rewrite",
    response_model=TargetedRewrite,
)
def rewrite_block(
    resume_id: uuid.UUID,
    tailored_id: uuid.UUID,
    block_id: str,
    payload: RewriteIn,
    session: Session = Depends(get_db),
) -> TargetedRewrite:
    """A draft of this line that foregrounds one requirement — on request, and
    checked: a new number, a dropped number or a new tool discards the draft."""
    row = _get(session, resume_id, tailored_id)
    block: dict[str, Any] | None = next((b for b in row.blocks if b["id"] == block_id), None)
    if block is None:
        raise HTTPException(status_code=404, detail="No such line in this copy.")
    if not tailor.editable(block):
        raise HTTPException(status_code=422, detail="This line can't be reworded here.")
    return reword_for_requirement(
        block.get("text") or "",
        requirement=payload.requirement[:300],
        jd_line=(payload.jd_line or "")[:600] or None,
        allowed_terms=[t[:60] for t in payload.allowed_terms[:5]],
    )

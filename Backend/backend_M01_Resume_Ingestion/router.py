"""M01 — Resume Ingestion & Claim Extraction.

The rule this module lives under is Rule 2: a missing input narrows the SCOPE
of what we show, never the quality, and never silently. Applied here that
means one thing above all — **a skill id we guessed offline must never be
indistinguishable from one M04 resolved.** Downstream, an id is a licence to
test the student on it; handing over an unconfirmed one and saying nothing is
how a fabricated concept ends up in a real interview.

── The pipeline, and where each stage lives ───────────────────────────────────

    upload → intake → layout → segment → entities → claims
           → scoring → probes → red flags → confirmation → commit

    intake, layout      documents.py    (PDF, DOCX, columns, OCR, reading order)
    injection filter    safety.py       (§6.7, before anything reads the text)
    segment             claims.segment
    entities            entities.py
    skills              extract.py + skills.py
    claims → flags      claims.py
    corrections, diff   revisions.py
    events              events.py

This file is the HTTP surface and the order of those calls, and as little else
as it can manage.

── One ordering decision worth stating ────────────────────────────────────────

Contact extraction and injection scanning both run on the ORIGINAL text, and
everything after them runs on the redacted copy. Redaction masks in place and
preserves length, so every offset is identical either way — but `SourceSpan`
carries a verbatim slice, and a slice taken from the original would put the
student's email address inside the contact section's span. FR-1.17 is about
what leaves this module, and a span is a thing that leaves this module.
"""

import json
import math
import re
import time
import urllib.request
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai_core.concepts import normalise_alias
from ai_core.dependencies import DependencyRegistry, DependencyStatus
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from backend_M01_Resume_Ingestion import (
    config,
    crypto,
    documents,
    llm,
    normalise,
    objectstore,
    retention,
    safety,
)
from backend_M01_Resume_Ingestion import probes as probe_gen
from backend_M01_Resume_Ingestion import skills as skills_mod
from backend_M01_Resume_Ingestion.models import (
    Resume,
    ResumeContact,
    ResumeCorrection,
    ResumeOut,
)

from .claims import (
    ResumeClaim,
    extract_claims,
    extract_contact,
    find_red_flags,
    redact,
    segment,
    verify_spans,
)
from .documents import IntakeError
from .entities import extract_entities
from .events import ResumeEvent, emit
from .extract import drop_redundant, extract_surface_forms, scan_prose
from .retention import Disclosure, ShareGrant
from .revisions import ALLOWED as ALLOWED_CORRECTIONS
from .revisions import apply_correction, diff_claims
from .rewrite import RewriteSuggestion, suggest_grounded
from .storage import put as store_artifact

router = APIRouter(prefix="/v1", tags=["M01 Resume Ingestion"])

_MANIFEST = Path(__file__).resolve().parents[2] / "module.json"


def get_db():
    from backend_M01_Resume_Ingestion.app import engine

    with Session(engine) as session:
        yield session


@lru_cache(maxsize=1)
def dependency_registry() -> DependencyRegistry:
    """Built once, not per call.

    The registry caches probe results for ~30s. Rebuilding it inside every
    helper threw that cache away and re-probed M04 twice per ingest, so the
    cache existed but never hit.
    """
    if not _MANIFEST.exists():
        return DependencyRegistry()
    return DependencyRegistry.from_manifest(_MANIFEST)


def _m04_url(path: str) -> str | None:
    """M04's URL for `path`, or None when M04 is not usable right now.

    Probes first: `is_available` is cached, the call is not, and asking a dead
    port twice per ingest costs a socket timeout each time.
    """
    deps = dependency_registry()
    dep = deps.get("M04")
    if dep is None or not dep.base_url or not deps.is_available("M04"):
        return None
    return f"{dep.base_url.rstrip('/')}{path}"


def get_m04_concepts() -> list[dict[str, Any]]:
    url = _m04_url("/v1/concepts")
    if url is None:
        return []
    try:
        with urllib.request.urlopen(url, timeout=2.0) as response:
            return json.loads(response.read()).get("concepts", [])
    except Exception:
        return []


def resolve_labels(labels: list[str]) -> dict[str, str | None]:
    """label -> concept_id as M04 resolves it. `None` means M04 could not."""
    if not labels:
        return {}
    url = _m04_url("/v1/concepts/resolve")
    if url is None:
        return {label: None for label in labels}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"labels": labels}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as response:
            return json.loads(response.read()).get("resolved", {})
    except Exception:
        return {label: None for label in labels}


class ResumeIngestIn(BaseModel):
    candidate_id: uuid.UUID
    raw_text: str


#: Enough ontology to be useful with M04 down, and small enough that nobody
#: mistakes it for the ontology. Every response records which one was used.
FALLBACK_CONCEPTS: list[dict[str, Any]] = [
    {"name": "Dynamic Programming", "aliases": ["DP", "dynamic programming"]},
    {"name": "Recursion", "aliases": ["recursion"]},
    {"name": "Hashing", "aliases": ["hashing", "hash map", "hashmap"]},
    {"name": "SQL", "aliases": ["sql", "sql_basics"]},
    {"name": "Transactions", "aliases": ["transactions", "transactions_acid"]},
]

FALLBACK_RESOLUTIONS = {
    "dynamic programming": "concept:dynamic_programming",
    "recursion": "concept:recursion",
    "hashing": "concept:hashing",
    "sql": "concept:sql_basics",
    "transactions": "concept:transactions_acid",
}


@router.get("/deps", response_model=list[DependencyStatus], tags=["meta"])
def dependency_health() -> list[DependencyStatus]:
    """Which upstream modules are up, and what breaks when they are not.

    Answers "why did my resume come back with no concepts?" in one request
    instead of a console dig.
    """
    return dependency_registry().statuses(force=True)


@router.get("/capabilities", tags=["meta"])
def capabilities() -> dict[str, Any]:
    """What this deployment can actually read (FR-1.1, FR-1.16).

    The upload screen asks before it renders a control. A dropzone that accepts
    a PDF on a server with no PDF library is a control that looks live and does
    nothing, which reads as a broken product rather than an unfinished one —
    and §2.4 lists exactly that as a quit trigger.
    """
    have_pdf = _module_available("pymupdf")
    return {
        "accepts": {
            "text/plain": True,
            "application/pdf": have_pdf,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
                _module_available("docx")
            ),
        },
        "ocr": documents.ocr_available(),
        # §6.7's model tier. Reported for the same reason `accepts` is: a
        # student whose questions read as generic should be able to find out
        # that generation is off, rather than concluding the product is thin.
        "generation": llm.status(),
        "max_bytes": config.MAX_UPLOAD_BYTES,
        "max_pages": config.MAX_PAGES,
        "parser_version": config.PARSER_VERSION,
        # The paste path has no dependency on any of the above and is why every
        # named intake error points at it (§10).
        "always_available": ["text/plain"],
    }


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


# ---------------------------------------------------------------------------
#  Ingest
# ---------------------------------------------------------------------------


def _ingest(
    session: Session,
    candidate_id: uuid.UUID,
    document: documents.Document,
    *,
    filename: str | None = None,
) -> Resume:
    """The pipeline, once, for a document that has already been read.

    Both entry points — multipart upload and pasted text — land here, so the
    paste path exercises the same extraction as the upload path rather than a
    simplified one. What you fix in isolation is what students get.
    """
    started = time.perf_counter()
    original = document.text

    # ------------------------------------------------------------------
    #  EC-1.8 — the same bytes for the same candidate is not a new resume.
    #  "Students re-upload the same file constantly" (§6.1). Returning the
    #  existing parse also returns their corrections, which is the behaviour
    #  they expect and the cheapest possible parse.
    # ------------------------------------------------------------------
    digest = _digest(original)
    existing = session.exec(
        select(Resume)
        .where(Resume.candidate_id == candidate_id)
        .where(Resume.content_sha256 == digest)
    ).first()
    if existing is not None:
        emit(
            session,
            "reused",
            resume_id=existing.id,
            candidate_id=candidate_id,
            reused_blob=1,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        session.commit()
        session.refresh(existing)
        return existing

    concepts = get_m04_concepts()
    scanned_against = "m04" if concepts else "offline_lexicon"
    if not concepts:
        concepts = FALLBACK_CONCEPTS

    # ------------------------------------------------------------------
    #  §6.7 — the document is untrusted, and it is neutralised BEFORE any
    #  stage reads it. Homoglyph folding first, because a Cyrillic о inside
    #  "ignore previous instructions" is the cheapest way past a regex.
    #  Both transformations preserve length, so no offset moves.
    # ------------------------------------------------------------------
    folded = safety.normalise_homoglyphs(original)
    findings = safety.scan(folded)
    scrubbed = safety.neutralise(folded, findings)

    # ------------------------------------------------------------------
    #  Read the document, THEN resolve. The order is the whole fix. The
    #  previous version walked the ontology and matched it against the text,
    #  so a skill the ontology had never heard of could not be seen at all:
    #  a fourteen-technology SKILLS line returned exactly what an empty
    #  string returned, and `unresolved_skills` could never hold anything a
    #  student had actually written. See extract.py.
    # ------------------------------------------------------------------
    surface_forms = extract_surface_forms(scrubbed)

    # Concepts named in running prose rather than listed — "using dynamic
    # programming" in a project bullet is real evidence. Ambiguous one-word
    # aliases are excluded there, which is what stops "a solid communicator"
    # from becoming a SOLID Principles claim.
    prose_hits = scan_prose(scrubbed, concepts)

    labels: list[str] = []
    seen: set[str] = set()
    for label in [*surface_forms, *sorted(prose_hits)]:
        # Punctuation-preserving, so "C", "C++" and "C#" stay three labels.
        dedup = normalise.key(label)
        if dedup and dedup not in seen:
            seen.add(dedup)
            labels.append(label)

    resolved = resolve_labels(labels)

    concepts_by_label: dict[str, str] = {}
    concept_source: dict[str, str] = {}
    unresolved: list[str] = []
    #: surface form -> the canonical spelling the alias table recognised. Kept
    #: even when nothing resolved: "we know what you meant, we just do not know
    #: which concept it is" is a more useful thing to show than silence, and it
    #: collapses five spellings of Kubernetes into one review-queue entry.
    canonical_of: dict[str, str] = {}
    for label in labels:
        concept_id = resolved.get(label)
        if concept_id:
            concepts_by_label[label] = str(concept_id)
            concept_source[label] = "m04"
            continue
        # M04 could not resolve it. Before giving up, run §6.4's own ladder
        # over the curated alias table: exact, then the short-token guard, then
        # fuzzy. That is what turns "reactjs", "k8s", "postgres" and "Kubernets"
        # into names rather than into permanent unmapped-queue entries.
        match = normalise.resolve(label)
        canonical = match.canonical

        # A canonical NAME is not a concept id. Ask M04 about the canonical form
        # too — a student's "k8s" may be unresolvable while "Kubernetes" is not.
        if canonical and canonical != label:
            confirmed = resolved.get(canonical) or resolve_labels([canonical]).get(canonical)
            if confirmed:
                concepts_by_label[label] = str(confirmed)
                concept_source[label] = "m04"
                canonical_of[label] = canonical
                continue

        guess = FALLBACK_RESOLUTIONS.get(normalise_alias(canonical or label))
        if guess:
            # Usable, and marked. M04 has not confirmed this id exists.
            concepts_by_label[label] = guess
            concept_source[label] = "offline_fallback"
            if canonical:
                canonical_of[label] = canonical
        else:
            unresolved.append(label)
            if canonical:
                # Unmapped, but not unrecognised: we know what the student
                # meant, only not which concept it is. The read-back can show
                # the canonical spelling and the ontology review queue gets one
                # entry for "Kubernetes" rather than five for its spellings.
                canonical_of[label] = canonical

    unresolved = drop_redundant(unresolved, list(concepts_by_label))
    # What the student wrote, mapped or not, in the order they wrote it. The
    # read-back screen splits these on `resolved_concepts` membership and
    # renders the remainder in its own hatched group.
    parsed = [label for label in labels if label in concepts_by_label or label in unresolved]

    # ------------------------------------------------------------------
    #  The artifact, and the copy anything is allowed to look at (FR-1.17)
    # ------------------------------------------------------------------
    contact = extract_contact(scrubbed)
    redacted = redact(scrubbed, contact)
    # Immutable and content-addressed (FR-1.2). Same bytes, same object. The
    # ORIGINAL is what is stored: a span has to stay re-verifiable against the
    # artifact it was extracted from, and neutralisation is a display concern.
    digest, storage_uri = store_artifact(original, candidate_id=str(candidate_id))

    resume = Resume(
        candidate_id=candidate_id,
        raw_text=original,
        redacted_text=redacted,
        content_sha256=digest,
        storage_uri=storage_uri,
        parsed_skills=parsed,
        resolved_concepts=concepts_by_label,
        concept_source=concept_source,
        unresolved_skills=unresolved,
        canonical_skills=canonical_of,
        scanned_against=scanned_against,
        filename=filename,
        mime=document.mime,
        page_count=document.page_count,
        parser_version=config.PARSER_VERSION,
        ocr_used=document.ocr_used,
        language=document.language,
        language_confidence=document.language_confidence,
        columns=document.columns,
        column_confidence=document.column_confidence,
        injections_removed=len(findings),
        parse_notes=list(document.notes),
    )

    # ------------------------------------------------------------------
    #  Sections, claims, probes, flags (FR-1.5, FR-1.8, FR-1.9, FR-1.10,
    #  FR-1.13). Everything runs on the redacted copy; see the module
    #  docstring for why that is not the same as running on the original.
    # ------------------------------------------------------------------
    sections = segment(
        redacted,
        resume.id,
        geometry=document,
        confidence_penalty=document.confidence_penalty,
    )

    def concepts_for(bullet: str) -> tuple[list[str], list[str]]:
        """Which already-resolved skills this bullet actually mentions.

        Reuses the resolution done above rather than asking M04 again per
        bullet: the labels are the same strings, and a resume with twenty
        bullets should not be twenty round trips.
        """
        # Word boundaries, not substrings: "sql" is inside "PostgreSQL", and
        # a probe that asks "how did you implement SQL?" about a bullet that
        # said Postgres reads as though the system was not listening.
        hit_labels = [
            lab
            for lab in concepts_by_label
            if re.search(rf"\b{re.escape(lab)}\b", bullet, re.IGNORECASE)
        ]
        return hit_labels, [concepts_by_label[lab] for lab in hit_labels]

    claim_models = extract_claims(
        redacted, resume.id, sections, concepts_for=concepts_for, geometry=document
    )
    # §6.5.4: never store a claim whose span does not resolve. AC-1.1 is the
    # gate; this is the code that makes it true rather than hoped for.
    claim_models = verify_spans(redacted, claim_models)

    # §6.7's model tier, over the top of the ladder that already ran.
    #
    # After `verify_spans` on purpose: a claim whose span did not resolve was
    # already dropped, so no model time is spent writing questions about a
    # bullet that will not be stored. With no key this is a no-op and every
    # claim keeps the deterministic probes it already has.
    probes_generated = probe_gen.enrich(claim_models, concepts_by_label=concepts_by_label)

    flags = find_red_flags(
        redacted,
        claim_models,
        resume.id,
        today=datetime.now(UTC).date(),
        listed_concepts=[concepts_by_label[lab] for lab in concepts_by_label],
    )

    mentions = skills_mod.find_mentions(
        redacted,
        parsed,
        resume.id,
        sections,
        resolved=concepts_by_label,
        sources=concept_source,
    )

    resume.sections = [s.model_dump(mode="json") for s in sections]
    resume.claims = [c.model_dump(mode="json") for c in claim_models]
    resume.red_flags = [f.model_dump(mode="json") for f in flags]
    resume.skill_mentions = [m.model_dump(mode="json") for m in mentions]
    resume.entities = extract_entities(redacted, sections).model_dump(mode="json")

    # A parse we are not confident in is not `ready` — it is a proposal the
    # student has to look at (§2.3 Screen 3). Saying so in `parse_status` is
    # what lets the confirmation screen ask rather than skim, and EC-1.1 and
    # EC-1.2 both land here.
    if (
        document.ocr_used
        or document.language not in {"en", "unknown"}
        or resume.column_confidence < config.COLUMN_CONFIDENCE_WARN_BELOW
        or (sections and max(s.confidence for s in sections) < 0.5)
    ):
        resume.parse_status = "needs_review"

    # ------------------------------------------------------------------
    #  Corrections are ground truth (FR-1.12). Re-applied here, before the
    #  row is written, so a student who fixed a mis-read heading once does
    #  not fix it again on every upload of the same file.
    # ------------------------------------------------------------------
    prior = session.exec(
        select(ResumeCorrection)
        .where(ResumeCorrection.candidate_id == candidate_id)
        .where(ResumeCorrection.content_sha256 == digest)
    ).all()
    reapplied = 0
    for correction in prior:
        applied, _ = apply_correction(
            resume.sections,
            resume.claims,
            resume.parsed_skills,
            resume.unresolved_skills,
            resume.resolved_concepts,
            target=correction.target,
            target_id=correction.target_id,
            field=correction.field,
            value=correction.new_value,
        )
        reapplied += int(applied)

    # ------------------------------------------------------------------
    #  EC-1.9 — a new version does not replace the old one. The previous
    #  row stays, with its claims, so progress tracking survives a rewrite
    #  and the diff has something to diff against.
    # ------------------------------------------------------------------
    for previous in session.exec(
        select(Resume).where(Resume.candidate_id == candidate_id).where(Resume.is_active)
    ).all():
        previous.is_active = False
        session.add(previous)

    resume.parse_ms = int((time.perf_counter() - started) * 1000)

    session.add(resume)
    session.add(
        ResumeContact(
            resume_id=resume.id,
            candidate_id=candidate_id,
            # FR-1.17's "encrypted column". Separation stops PII reaching a
            # screen or a model; this is what somebody holding a copy of the
            # database file can read.
            emails=crypto.encrypt_all(contact.emails),
            phones=crypto.encrypt_all(contact.phones),
            links=crypto.encrypt_all(contact.links),
        )
    )
    safety.record(session, findings, resume_id=resume.id, candidate_id=candidate_id)

    bands = [c["risk_band"] for c in resume.claims]
    emit(
        session,
        "ingested",
        resume_id=resume.id,
        candidate_id=candidate_id,
        chars=len(original),
        lines=original.count(chr(10)) + 1,
        sections=len(resume.sections),
        claims=len(resume.claims),
        probes=sum(len(c["probes"]) for c in resume.claims),
        # How many claims a model wrote questions for. Zero is the
        # normal answer with no key, and telling those two apart is
        # what makes "why are my questions generic?" answerable.
        probes_generated=probes_generated,
        red_flags=len(resume.red_flags),
        skills_found=len(resume.parsed_skills),
        skills_mapped=len(resume.resolved_concepts),
        skills_unmapped=len(resume.unresolved_skills),
        scanned_against=scanned_against,
        risk_strong=bands.count("strong"),
        risk_vague=bands.count("vague"),
        risk_risky=bands.count("risky"),
        corrections=reapplied,
        stored=1,
        duration_ms=resume.parse_ms,
    )

    session.commit()
    session.refresh(resume)
    return resume


def _digest(text: str) -> str:
    from .storage import digest_of

    return digest_of(text)


@router.post("/resumes", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    candidate_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
):
    """A PDF or DOCX upload (§7, FR-1.1).

    Synchronous rather than the spec's `202 {resume_id, status}` + worker. The
    whole pipeline is deterministic and runs in single-digit milliseconds on
    pasted text and well inside FR-1.18's budget on a real PDF; a queue would
    add a moving part, a failure mode and a polling loop to buy nothing. The
    SSE endpoint below still exists, because §2.3 Screen 2 is about what the
    student is told while waiting, and that is true at 300 ms as much as at
    25 s — it just has less to narrate.
    """
    data = await file.read()
    try:
        document = documents.parse(data, file.filename)
    except IntakeError as error:
        # A named error with the always-works path in it (§2.4, §10) — AND a
        # persisted row saying what happened.
        #
        # §10's last line is "Everything fails → `parse_status=failed`". Raising
        # only, as this did, left `parse_status` and `parse_error` declared on
        # the table and written by nothing: a student whose upload failed three
        # times in a row left no trace at all, so "which file types are actually
        # failing for real students" was a question the data could not answer.
        _record_failure(session, candidate_id, error, filename=file.filename)
        raise HTTPException(
            status_code=error.status,
            detail={"code": error.code, "message": error.message, "fallback": "text"},
        ) from error
    return ResumeOut.of(_ingest(session, candidate_id, document, filename=file.filename))


def _record_failure(
    session: Session,
    candidate_id: uuid.UUID,
    error: IntakeError,
    *,
    filename: str | None,
) -> None:
    """A parse that never started, on the record (§10).

    Deliberately not `is_active`: a failed upload must not supersede the resume
    the student already has working. It carries no text, because there was none
    we could read — only what was tried and why it stopped.
    """
    resume = Resume(
        candidate_id=candidate_id,
        raw_text="",
        redacted_text="",
        content_sha256=_digest(f"failed:{filename}:{error.code}"),
        filename=filename,
        parse_status="failed",
        parse_error=f"{error.code}: {error.message}",
        parser_version=config.PARSER_VERSION,
        is_active=False,
    )
    session.add(resume)
    emit(
        session,
        "failed",
        resume_id=resume.id,
        candidate_id=candidate_id,
        chars=0,
    )
    session.commit()


@router.post("/resumes/from-text", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
def ingest_from_text(payload: ResumeIngestIn, session: Session = Depends(get_db)):
    """The always-works fallback (§7, §10).

    No file, no PDF library, no OCR. Every named intake error above points a
    student here, so this path must never be the one that is broken.
    """
    return ResumeOut.of(
        _ingest(session, payload.candidate_id, documents.from_text(payload.raw_text))
    )


@router.post("/resumes/ingest", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
def ingest_resume(payload: ResumeIngestIn, session: Session = Depends(get_db)):
    """This module's original name for `/resumes/from-text`.

    Kept because M02 and the frontend already call it. §7 names the other one,
    so both exist and neither is a redirect — a 307 through a POST loses the
    body in enough HTTP clients to be worth two lines instead.
    """
    return ingest_from_text(payload, session)


# ---------------------------------------------------------------------------
#  Reading
# ---------------------------------------------------------------------------


@router.get("/resumes/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    resume = session.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return ResumeOut.of(resume)


@router.get("/resumes/candidate/{candidate_id}", response_model=list[ResumeOut])
def get_resumes_by_candidate(candidate_id: uuid.UUID, session: Session = Depends(get_db)):
    rows = session.exec(
        select(Resume).where(Resume.candidate_id == candidate_id).order_by(Resume.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [ResumeOut.of(r) for r in rows]


@router.get("/resumes/{resume_id}/claims")
def list_claims(
    resume_id: uuid.UUID,
    band: str | None = Query(None, pattern="^(strong|vague|risky)$"),
    session: Session = Depends(get_db),
):
    """The Claim Map (§7, §2.3 Screen 4).

    Ordered by `prominence × risk_score`, which is §6.6's whole argument for
    prominence: *"A vague bullet buried at the bottom of page 2 is not a risk.
    A vague bullet that is the first line of the first project is a serious
    risk, because it is what the interviewer reads first."*  The first element
    of this list is the "one thing to fix first" card, and it is returned
    separately so a client cannot disagree about which one that is.
    """
    resume = _require(session, resume_id)
    claims = [c for c in resume.claims if band is None or c["risk_band"] == band]
    claims.sort(key=lambda c: c.get("prominence", 0) * c.get("risk_score", 0), reverse=True)

    counts = {name: 0 for name in ("strong", "vague", "risky")}
    for claim in resume.claims:
        counts[claim["risk_band"]] = counts.get(claim["risk_band"], 0) + 1

    risky = [c for c in resume.claims if c["risk_band"] == "risky"]
    risky.sort(key=lambda c: c.get("prominence", 0) * c.get("risk_score", 0), reverse=True)

    return {
        "resume_id": str(resume.id),
        "claims": claims,
        "counts": counts,
        "total": len(resume.claims),
        # §2.3: "Bullet 3 in Crop Disease Detection. It's your most prominent
        # claim and your least defensible one."
        "fix_first": risky[0] if risky else None,
    }


@router.get("/resumes/{resume_id}/red-flags")
def list_red_flags(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    """§6.8 — deterministic rules only, and none of them accuse."""
    resume = _require(session, resume_id)
    flags = resume.red_flags
    order = {"serious": 0, "notable": 1, "info": 2}
    return {
        "resume_id": str(resume.id),
        "red_flags": sorted(flags, key=lambda f: order.get(f.get("severity", "info"), 3)),
        "counts": {
            severity: sum(1 for f in flags if f.get("severity") == severity)
            for severity in ("serious", "notable", "info")
        },
    }


@router.get("/resumes/{resume_id}/skills")
def list_skill_mentions(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    """Skill mentions with their context (§5, §6.4, FR-1.7).

    `unmapped` is returned as its own list rather than filtered out. §6.4:
    *"The unmapped queue is a feature, not debt — it is how the ontology learns
    what students actually write."*
    """
    resume = _require(session, resume_id)
    mentions = [skills_mod.SkillMention(**m) for m in resume.skill_mentions]
    summary = skills_mod.SkillSummary.of(mentions)
    return {
        "resume_id": str(resume.id),
        "scanned_against": resume.scanned_against,
        "mentions": [m.model_dump(mode="json") for m in mentions],
        "mapped": summary.mapped,
        "unmapped": summary.unmapped,
        "claimed_use": summary.claimed_use,
        "unmapped_queue": skills_mod.unmapped_report(mentions),
    }


@router.get("/resumes/{resume_id}/contact", response_model=ResumeContact, tags=["pii"])
def get_resume_contact(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    """The contact block, released deliberately (FR-1.17).

    Its own route, its own tag, and not a field on the resume — so "who saw
    the student's phone number" is answerable from an access log rather than
    from reading every caller of the resume endpoint.
    """
    contact = session.get(ResumeContact, resume_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Decrypted here and only here — the single route that deliberately
    # releases the contact block. Returned as a copy so the decrypted values
    # cannot be flushed back to the row by a later commit in this session.
    return ResumeContact(
        resume_id=contact.resume_id,
        candidate_id=contact.candidate_id,
        emails=crypto.decrypt_all(contact.emails),
        phones=crypto.decrypt_all(contact.phones),
        links=crypto.decrypt_all(contact.links),
        created_at=contact.created_at,
    )


@router.get("/resumes/{resume_id}/stream", tags=["meta"])
def stream_progress(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    """Stage-by-stage progress for §2.3 Screen 2.

    *"Parsing takes 8-25 seconds. A spinner for 25 seconds feels broken. So we
    narrate, and each line appears as its stage actually completes."*

    The parse here is synchronous and already finished by the time anyone can
    subscribe, so this REPLAYS the stages from what the row actually records —
    section count, claim count, whether OCR ran — rather than inventing a
    timeline. That distinction matters: a progress bar that animates over work
    that is not happening is the theatre §2.3 is warning about. When the
    pipeline grows a worker, this endpoint changes and its consumers do not.
    """
    resume = _require(session, resume_id)

    stages = [
        ("intake", f"Read {resume.page_count} page(s)" if resume.page_count else "Read your text"),
        (
            "layout",
            "Read this from an image" if resume.ocr_used else f"Found {resume.columns} column(s)",
        ),
        ("segment", f"Found {len(resume.sections)} section(s)"),
        ("entities", _entities_detail(resume)),
        ("claims", f"Extracted {len(resume.claims)} claim(s)"),
        ("scoring", _band_detail(resume)),
        (
            "probes",
            f"Prepared {sum(len(c.get('probes', [])) for c in resume.claims)} question(s)",
        ),
        ("flags", f"Checked for {len(resume.red_flags)} thing(s) worth knowing"),
    ]

    def events():
        total = len(stages)
        for index, (stage, detail) in enumerate(stages, start=1):
            payload = {
                "stage": stage,
                "status": "done",
                "detail": detail,
                "progress": round(index / total, 2),
            }
            yield f"data: {json.dumps(payload)}\n\n"
        yield (
            "data: "
            + json.dumps(
                {
                    "stage": "complete",
                    "status": "done",
                    "detail": f"Done in {resume.parse_ms} ms",
                    "progress": 1.0,
                    "parse_status": resume.parse_status,
                }
            )
            + "\n\n"
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _entities_detail(resume: Resume) -> str:
    entities = resume.entities or {}
    return (
        f"Recognised {len(entities.get('education', []))} qualification(s) "
        f"and {len(entities.get('roles', []))} role(s)"
    )


def _band_detail(resume: Resume) -> str:
    risky = sum(1 for c in resume.claims if c.get("risk_band") == "risky")
    return f"{len(resume.claims)} claim(s) scored, {risky} look risky"


def _require(session: Session, resume_id: uuid.UUID) -> Resume:
    resume = session.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


# ---------------------------------------------------------------------------
#  Corrections (FR-1.11, FR-1.12)
# ---------------------------------------------------------------------------


class CorrectionIn(BaseModel):
    """One field, on one target, set to one value.

    Deliberately not a patch document. A student correcting a section kind and
    a claim's text in one request would land as one audit row covering two
    disagreements, and AC-1.7 counts disagreements.
    """

    target: str  # "section" | "claim" | "skill"
    target_id: str
    field: str
    value: str | None = None


def _apply(
    session: Session,
    resume: Resume,
    target: str,
    target_id: str,
    field: str,
    value: str | None,
) -> Resume:
    # DEEP copies, and the depth matters. A shallow `list(resume.sections)`
    # holds the same dict objects, so editing one mutates the loaded value in
    # place — and the rebind that follows then assigns a list EQUAL to what is
    # already there. SQLAlchemy emits no UPDATE for an unchanged attribute, so
    # the correction applied, returned 201, and silently did not persist.
    sections = deepcopy(resume.sections)
    claims = deepcopy(resume.claims)
    parsed = list(resume.parsed_skills)
    unresolved = list(resume.unresolved_skills)
    resolved = dict(resume.resolved_concepts)
    entities = deepcopy(resume.entities)

    applied, old_value = apply_correction(
        sections,
        claims,
        parsed,
        unresolved,
        resolved,
        target=target,
        target_id=target_id,
        field=field,
        value=value,
        entities=entities,
    )
    if not applied:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot set {target}.{field}. Correctable: {ALLOWED_CORRECTIONS}",
        )

    resume.sections = sections
    resume.claims = claims
    resume.parsed_skills = parsed
    resume.unresolved_skills = unresolved
    resume.resolved_concepts = resolved
    resume.entities = entities

    # A corrected bullet is a different claim, so it is re-scored rather than
    # left carrying the score of the text it replaced (§8.3: "Editing a bullet
    # re-scores only that claim"). `user_edited` stays true either way.
    if target == "claim" and field == "text":
        _rescore(resume, target_id)

    session.add(resume)
    session.add(
        ResumeCorrection(
            resume_id=resume.id,
            candidate_id=resume.candidate_id,
            content_sha256=resume.content_sha256,
            target=target,
            target_id=target_id,
            field=field,
            old_value=old_value,
            new_value=value,
        )
    )
    emit(
        session,
        "corrected",
        resume_id=resume.id,
        candidate_id=resume.candidate_id,
        corrections=1,
    )
    session.commit()
    session.refresh(resume)
    return resume


def _rescore(resume: Resume, claim_id: str) -> None:
    """Re-run the four axes for one edited claim, in place.

    Only that claim: §8.3 asks for a re-score in under 500 ms, and re-parsing
    the document to change one bullet would also discard every other correction
    the student has made in this session.
    """
    from .claims import band, extract_quantifiers, score_claim

    claims = deepcopy(resume.claims)
    for claim in claims:
        if str(claim.get("id")) != claim_id:
            continue
        text = claim.get("text") or ""
        quantifiers = extract_quantifiers(text, claim["span"]["start"], resume.id)
        concept_ids = [
            cid
            for label, cid in resume.resolved_concepts.items()
            if re.search(rf"\b{re.escape(label)}\b", text, re.IGNORECASE)
        ]
        scores = score_claim(
            text,
            quantifiers=quantifiers,
            concepts=concept_ids,
            has_link="http" in text or "github.com" in text,
            prominence=claim.get("prominence", 0.5),
            today=datetime.now(UTC).date(),
        )
        claim.update(scores)
        claim["risk_band"] = band(scores["risk_score"])
        claim["subject_concepts"] = concept_ids
        claim["quantifiers"] = [q.model_dump(mode="json") for q in quantifiers]
        break
    resume.claims = claims


@router.post(
    "/resumes/{resume_id}/corrections",
    response_model=ResumeOut,
    status_code=status.HTTP_201_CREATED,
)
def correct_resume(
    resume_id: uuid.UUID,
    payload: CorrectionIn,
    session: Session = Depends(get_db),
):
    """The student overrules the parser (FR-1.12).

    Applied immediately and logged permanently. The log is what makes AC-1.7
    answerable — "edit rate > 40% means the parser needs work" needs every
    correction still on disk, not a field that quietly became right.
    """
    resume = _require(session, resume_id)
    return ResumeOut.of(
        _apply(session, resume, payload.target, payload.target_id, payload.field, payload.value)
    )


class FieldPatch(BaseModel):
    field: str
    value: str | None = None


@router.patch("/resumes/{resume_id}/sections/{section_id}", response_model=ResumeOut)
def patch_section(
    resume_id: uuid.UUID,
    section_id: str,
    payload: FieldPatch,
    session: Session = Depends(get_db),
):
    """§7 — a section the parser labelled wrong (FR-1.11)."""
    resume = _require(session, resume_id)
    return ResumeOut.of(
        _apply(session, resume, "section", section_id, payload.field, payload.value)
    )


@router.patch("/resumes/{resume_id}/claims/{claim_id}", response_model=ResumeOut)
def patch_claim(
    resume_id: uuid.UUID,
    claim_id: str,
    payload: FieldPatch,
    session: Session = Depends(get_db),
):
    """§7 — a bullet the student rewrote (FR-1.11). Re-scored on the way through."""
    resume = _require(session, resume_id)
    return ResumeOut.of(_apply(session, resume, "claim", claim_id, payload.field, payload.value))


class DatePatch(BaseModel):
    """A date range the student is correcting, written the way they write it."""

    value: str | None = None


@router.patch("/resumes/{resume_id}/dates/{index}", response_model=ResumeOut)
def patch_date(
    resume_id: uuid.UUID,
    index: int,
    payload: DatePatch,
    session: Session = Depends(get_db),
):
    """§2.3 Screen 3's fourth editable target (FR-1.11).

    "Sections, bullets, skills, and dates" — dates were the one thing a student
    could not fix, and a mis-read date drives both the timeline-gap flag and
    `recency`. An empty value strikes a range the parser invented.

    The typed value goes through the same parser that read the document, so a
    422 here means "I could not read that as a date range", not "rejected".
    """
    resume = _require(session, resume_id)
    return ResumeOut.of(_apply(session, resume, "entity", str(index), "dates", payload.value))


class SkillPatch(BaseModel):
    label: str
    present: bool = True


@router.post("/resumes/{resume_id}/skills", response_model=ResumeOut)
def patch_skill(
    resume_id: uuid.UUID,
    payload: SkillPatch,
    session: Session = Depends(get_db),
):
    """§7 — add or remove a skill (FR-1.11).

    An added skill lands in `unresolved_skills`, never in `resolved_concepts`.
    M01 does not get to mint a concept_id: a student typing "Kubernetes" is a
    claim about their resume, not a statement that the ontology has a concept
    for it, and inventing one here is how a fabricated id reaches M05.
    """
    resume = _require(session, resume_id)
    return ResumeOut.of(
        _apply(
            session,
            resume,
            "skill",
            payload.label,
            "present",
            "true" if payload.present else "false",
        )
    )


@router.delete("/resumes/{resume_id}/claims/{claim_id}", response_model=ResumeOut)
def delete_claim(
    resume_id: uuid.UUID,
    claim_id: str,
    session: Session = Depends(get_db),
):
    """Remove a claim the student says is not theirs (EC-1.17).

    *"User deletes every claim in the editor — allowed; product continues
    resume-free."*  Routed through the correction log like every other
    disagreement rather than as a bare delete, because a student striking a
    claim we invented is the most informative correction there is and AC-1.7
    should count it.
    """
    resume = _require(session, resume_id)
    return ResumeOut.of(_apply(session, resume, "claim", claim_id, "present", "false"))


@router.post("/resumes/{resume_id}/confirm", response_model=ResumeOut)
def confirm_resume(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    """The student has been through the confirmation pass (§2.3 Screen 3, §7).

    *"We do not silently trust the parse."*  Until this is called the parse is
    a proposal; after it, it is a reading the student has signed off, and
    downstream modules can tell those apart. Idempotent — confirming twice is
    a double-click, not an error.
    """
    resume = _require(session, resume_id)
    if not resume.confirmed:
        resume.confirmed = True
        resume.confirmed_at = datetime.now(UTC)
        if resume.parse_status in {"ready", "needs_review"}:
            resume.parse_status = "ready"
        session.add(resume)
        corrections = session.exec(
            select(ResumeCorrection).where(ResumeCorrection.resume_id == resume_id)
        ).all()
        emit(
            session,
            "confirmed",
            resume_id=resume.id,
            candidate_id=resume.candidate_id,
            claims=len(resume.claims),
            # AC-1.7 watches this: "> 40% means the parser needs work". It is
            # only answerable if the count is recorded at the moment the
            # student said they were done looking.
            corrections=len(corrections),
        )
        session.commit()
        session.refresh(resume)
    return ResumeOut.of(resume)


@router.get("/resumes/{resume_id}/corrections", response_model=list[ResumeCorrection])
def list_corrections(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    """Every time the parser was overruled on this resume."""
    return session.exec(
        select(ResumeCorrection).where(ResumeCorrection.resume_id == resume_id)
    ).all()


# ---------------------------------------------------------------------------
#  Rewrite (FR-1.19)
# ---------------------------------------------------------------------------


@router.post("/resumes/{resume_id}/claims/{claim_id}/rewrite", response_model=RewriteSuggestion)
def rewrite_claim(
    resume_id: uuid.UUID,
    claim_id: str,
    session: Session = Depends(get_db),
):
    """A STAR shape for a weak bullet (FR-1.19, §15 decision 2).

    On request only, and it changes nothing. *"A resume the student didn't
    write is a resume they can't defend, which is the exact failure this module
    exists to prevent."*  The response is a skeleton with the student's own
    facts left as blanks, plus what is missing and what to fix first.
    """
    resume = _require(session, resume_id)
    raw = next((c for c in resume.claims if str(c.get("id")) == claim_id), None)
    if raw is None:
        raise HTTPException(status_code=404, detail="Claim not found on this resume")

    claim = ResumeClaim(**raw)
    labels = [
        label
        for label in resume.resolved_concepts
        if re.search(rf"\b{re.escape(label)}\b", claim.text, re.IGNORECASE)
    ]
    return suggest_grounded(claim, concept_labels=labels)


# ---------------------------------------------------------------------------
#  Versions (FR-1.15)
# ---------------------------------------------------------------------------


@router.get("/resumes/{resume_id}/diff")
def diff_against(
    resume_id: uuid.UUID,
    against: uuid.UUID = Query(..., description="The older resume to compare with"),
    session: Session = Depends(get_db),
):
    """What changed between two uploads (§7, FR-1.15)."""
    return _diff(session, resume_id, against)


@router.get("/resumes/{resume_id}/diff/{other_id}")
def diff_resumes(
    resume_id: uuid.UUID,
    other_id: uuid.UUID,
    session: Session = Depends(get_db),
):
    """The path form of the above. Both exist for the reason `/ingest` does."""
    return _diff(session, resume_id, other_id)


def _diff(session: Session, newer_id: uuid.UUID, older_id: uuid.UUID) -> dict:
    """`newer_id` is the newer one.

    Compared on claim TEXT rather than id, because every id changes on re-parse
    and an id-keyed diff would report a completely rewritten resume every time
    somebody fixed a typo.
    """
    newer = session.get(Resume, newer_id)
    older = session.get(Resume, older_id)
    if not newer or not older:
        raise HTTPException(status_code=404, detail="Resume not found")
    if newer.candidate_id != older.candidate_id:
        raise HTTPException(
            status_code=422,
            detail="Those resumes belong to different candidates.",
        )

    result = diff_claims(older.claims, newer.claims)
    result["before"] = str(older.id)
    result["after"] = str(newer.id)
    result["identical_content"] = older.content_sha256 == newer.content_sha256
    return result


@router.delete("/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    """Hard delete, including object storage (§7).

    The contact row goes with it — that is the whole point of a deletion
    request. The correction log does NOT: it is keyed to the content digest
    rather than the row, it holds no document text, and it is the evidence
    behind AC-1.7. A student deleting a resume is asking us to forget the
    resume, not to forget that the parser was wrong nine times.

    The blob is removed only when no other row still cites that digest. Two
    candidates who uploaded the same file share one object, and one of them
    leaving must not break the other's spans.
    """
    resume = _require(session, resume_id)
    digest = resume.content_sha256

    contact = session.get(ResumeContact, resume_id)
    if contact:
        session.delete(contact)
    for event in session.exec(select(ResumeEvent).where(ResumeEvent.resume_id == resume_id)).all():
        session.delete(event)
    session.delete(resume)
    session.commit()

    others = session.exec(select(Resume).where(Resume.content_sha256 == digest)).first()
    if others is None:
        from .storage import remove

        remove(digest)
    return None


class ShareIn(BaseModel):
    """A student granting somebody sight of their claims (§15 decision 4)."""

    grantee: str
    days: int | None = 90


@router.post("/resumes/{resume_id}/share", status_code=status.HTTP_201_CREATED)
def share_resume(resume_id: uuid.UUID, payload: ShareIn, session: Session = Depends(get_db)):
    """The student decides who sees this (§15 decision 4).

    The decision itself is not made here — the placement cell has not been
    asked yet. What is decided is the SHAPE: a grant is to somebody named, it
    expires, and revoking leaves a trace. Whichever way the policy lands, it
    lands as configuration on top of this rather than as a rewrite.
    """
    resume = _require(session, resume_id)
    grant = ShareGrant(
        resume_id=resume.id,
        candidate_id=resume.candidate_id,
        grantee=payload.grantee,
        expires_at=(datetime.now(UTC) + timedelta(days=payload.days) if payload.days else None),
    )
    session.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


@router.delete("/resumes/{resume_id}/share/{grantee}", status_code=status.HTTP_200_OK)
def revoke_share(resume_id: uuid.UUID, grantee: str, session: Session = Depends(get_db)):
    """Withdraw a grant. Recorded, not deleted.

    A student who shared and then withdrew has a right to know it was
    withdrawn, and a row removed from the table cannot tell them that.
    """
    grants = session.exec(
        select(ShareGrant)
        .where(ShareGrant.resume_id == resume_id)
        .where(ShareGrant.grantee == grantee)
    ).all()
    revoked = 0
    for grant in grants:
        if grant.revoked_at is None:
            grant.revoked_at = datetime.now(UTC)
            session.add(grant)
            revoked += 1
    session.commit()
    return {"revoked": revoked, "grantee": grantee}


@router.get("/resumes/{resume_id}/disclosure", tags=["meta"])
def disclosure(
    resume_id: uuid.UUID,
    viewer: str = Query(..., description="Who is asking"),
    session: Session = Depends(get_db),
):
    """What this viewer may see, and until when (§15 decisions 3 and 4).

    Fails closed: a viewer with no grant gets `aggregate_only`, which is §15's
    proposed default and the only sensible one to hold while the decision is
    open. There is no auth in this platform yet, so this ANSWERS the question
    rather than enforcing it — the answer is the part that has to exist before
    anything can enforce anything.
    """
    resume = _require(session, resume_id)
    grants = session.exec(select(ShareGrant).where(ShareGrant.resume_id == resume_id)).all()
    level = retention.disclosure_for(list(grants), viewer=viewer, candidate_id=resume.candidate_id)
    created = resume.created_at.date()
    return {
        "resume_id": str(resume.id),
        "viewer": viewer,
        "disclosure": level.value,
        "may_see_individual_claims": level is not Disclosure.aggregate_only,
        "retention": {
            **retention.retention_policy(),
            "created_on": created.isoformat(),
            "expires_on": retention.expires_on(created).isoformat(),
            "expired": retention.is_expired(created),
        },
    }


@router.get("/quality", tags=["meta"])
def quality_report(session: Session = Depends(get_db)):
    """AC-1.7, answerable (§13).

    *"Confirmation screen edit rate; tracked; > 40% means the parser needs
    work."*  Every correction was already on disk and nothing added them up, so
    the criterion was a column rather than a number anybody could look at.

    Rates are over CONFIRMED resumes only. A student who has not reached the
    confirmation screen has not declined to correct anything, and counting them
    as agreement is how an edit rate flatters itself.
    """
    resumes = session.exec(select(Resume).where(Resume.parse_status != "failed")).all()
    confirmed = [r for r in resumes if r.confirmed]
    corrections = session.exec(select(ResumeCorrection)).all()

    corrected_ids = {c.resume_id for c in corrections}
    edited = [r for r in confirmed if r.id in corrected_ids]
    rate = len(edited) / len(confirmed) if confirmed else 0.0

    by_target: dict[str, int] = {}
    for correction in corrections:
        key = f"{correction.target}.{correction.field}"
        by_target[key] = by_target.get(key, 0) + 1

    failed = session.exec(select(Resume).where(Resume.parse_status == "failed")).all()
    failures: dict[str, int] = {}
    for row in failed:
        code = (row.parse_error or "unknown").split(":", 1)[0]
        failures[code] = failures.get(code, 0) + 1

    return {
        "resumes": len(resumes),
        "confirmed": len(confirmed),
        "edit_rate": round(rate, 3),
        # §13's own threshold, evaluated rather than left to the reader.
        "edit_rate_target": 0.40,
        "parser_needs_work": rate > 0.40,
        "corrections": len(corrections),
        "corrections_by_target": dict(sorted(by_target.items())),
        "needs_review": sum(1 for r in resumes if r.parse_status == "needs_review"),
        "ocr_used": sum(1 for r in resumes if r.ocr_used),
        "two_column": sum(1 for r in resumes if r.columns > 1),
        # Which uploads are failing, and how — the question the dead
        # `parse_error` column could not answer.
        # FR-1.17: an operator who has not set the key should be able to
        # find that out without reading the logs.
        "pii_encrypted_at_rest": crypto.key_configured(),
        # §6.1 asks for a virus scan before parsing. There is not one, and
        # a stubbed "scanned: true" would be worse than the honest gap.
        "virus_scan": not objectstore.scan_required(),
        "object_store": "s3" if objectstore.configured() else "local",
        "retention": retention.retention_policy(),
        "failed": len(failed),
        "failures_by_code": dict(sorted(failures.items())),
        # AC-1.6, evaluated rather than left in a column. `parse_ms` has been
        # written since the first commit and nothing ever added it up, so the
        # criterion was a number on every row and an answer on none — the same
        # shape AC-1.7 was in. §11 budgets p95 at 22 s and §13 gates it at 25.
        "timing": _timing(resumes),
    }


#: AC-1.6's target, in milliseconds. §13: "p95 end-to-end parse (2 pages, no
#: OCR) ≤ 25 s". The OCR exclusion is the whole reason this is measured
#: separately below: §11 budgets OCR alone at 15 s p95, so a corpus with
#: scanned resumes in it would breach a target that was never about them.
PARSE_P95_TARGET_MS = 25_000


def _percentile(values: list[int], fraction: float) -> int:
    """Nearest-rank percentile.

    Not interpolated. On the handful of resumes a dev machine holds, an
    interpolated p95 reports a duration no parse actually took — and the
    question here is "did a real parse breach the budget", which wants a real
    measurement.
    """
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _timing(resumes: list[Resume]) -> dict[str, Any]:
    """How long parsing actually takes, against §13's line.

    Measured over the resumes AC-1.6 is about: parsed, and not read from an
    image. Both exclusions are the criterion's own words, not a flattering
    filter — and both counts are reported so nobody has to guess how much of
    the corpus was set aside.
    """
    eligible = [r for r in resumes if r.parse_ms > 0 and not r.ocr_used]
    durations = [r.parse_ms for r in eligible]
    ocr = [r.parse_ms for r in resumes if r.parse_ms > 0 and r.ocr_used]

    p95 = _percentile(durations, 0.95)
    return {
        "measured": len(durations),
        "excluded_ocr": len(ocr),
        "p50_ms": _percentile(durations, 0.50),
        "p95_ms": p95,
        "max_ms": max(durations) if durations else 0,
        "target_ms": PARSE_P95_TARGET_MS,
        # False on an empty corpus: nothing has breached a budget it has not
        # been asked to meet, and reporting "over" for zero parses would make
        # a fresh clone look broken.
        "over_budget": bool(durations) and p95 > PARSE_P95_TARGET_MS,
        # Reported alongside rather than folded in — §11 budgets OCR at 15 s of
        # its own, so a slow scanned resume is expected rather than a breach.
        "ocr_p95_ms": _percentile(ocr, 0.95),
    }


@router.get("/resumes/{resume_id}/events", response_model=list[ResumeEvent], tags=["meta"])
def list_events(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    """The `resume.*` stage boundaries recorded for this resume (FR-1.20).

    Readable over HTTP because an event stream nobody can look at is one that
    quietly stops being emitted.
    """
    return session.exec(select(ResumeEvent).where(ResumeEvent.resume_id == resume_id)).all()

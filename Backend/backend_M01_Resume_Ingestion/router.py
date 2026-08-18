"""M01 — Resume Ingestion & Claim Extraction.

The rule this module lives under is Rule 2: a missing input narrows the SCOPE
of what we show, never the quality, and never silently. Applied here that
means one thing above all — **a skill id we guessed offline must never be
indistinguishable from one M04 resolved.** Downstream, an id is a licence to
test the student on it; handing over an unconfirmed one and saying nothing is
how a fabricated concept ends up in a real interview.
"""

import json
import re
import urllib.request
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai_core.dependencies import DependencyRegistry, DependencyStatus
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from backend_M01_Resume_Ingestion.models import Resume

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


@router.post("/resumes/ingest", response_model=Resume, status_code=status.HTTP_201_CREATED)
def ingest_resume(payload: ResumeIngestIn, session: Session = Depends(get_db)):
    concepts = get_m04_concepts()
    scanned_against = "m04" if concepts else "offline_lexicon"
    if not concepts:
        concepts = FALLBACK_CONCEPTS

    found_skills = set()
    text_lower = payload.raw_text.lower()
    for c in concepts:
        names_to_check = [c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]
        for name in names_to_check:
            if re.search(rf"\b{re.escape(name)}\b", text_lower):
                found_skills.add(c["name"])
                break

    resolved = resolve_labels(sorted(found_skills))

    concepts_by_label: dict[str, str] = {}
    concept_source: dict[str, str] = {}
    unresolved: list[str] = []
    for label in sorted(found_skills):
        concept_id = resolved.get(label)
        if concept_id:
            concepts_by_label[label] = str(concept_id)
            concept_source[label] = "m04"
            continue
        guess = FALLBACK_RESOLUTIONS.get(label.lower())
        if guess:
            # Usable, and marked. M04 has not confirmed this id exists.
            concepts_by_label[label] = guess
            concept_source[label] = "offline_fallback"
        else:
            unresolved.append(label)

    resume = Resume(
        candidate_id=payload.candidate_id,
        raw_text=payload.raw_text,
        parsed_skills=sorted(found_skills),
        resolved_concepts=concepts_by_label,
        concept_source=concept_source,
        unresolved_skills=unresolved,
        scanned_against=scanned_against,
    )
    session.add(resume)
    session.commit()
    session.refresh(resume)
    return resume


@router.get("/resumes/{resume_id}", response_model=Resume)
def get_resume(resume_id: uuid.UUID, session: Session = Depends(get_db)):
    resume = session.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


@router.get("/resumes/candidate/{candidate_id}", response_model=list[Resume])
def get_resumes_by_candidate(candidate_id: uuid.UUID, session: Session = Depends(get_db)):
    return session.exec(select(Resume).where(Resume.candidate_id == candidate_id)).all()

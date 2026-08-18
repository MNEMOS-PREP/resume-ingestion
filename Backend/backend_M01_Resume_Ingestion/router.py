import json
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from ai_core.dependencies import DependencyRegistry
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

def dependency_registry() -> DependencyRegistry:
    if not _MANIFEST.exists():
        return DependencyRegistry()
    return DependencyRegistry.from_manifest(_MANIFEST)

def get_m04_concepts() -> list[dict[str, Any]]:
    dep = dependency_registry().get("M04")
    if not dep or not dep.base_url:
        return []
    url = f"{dep.base_url.rstrip('/')}/v1/concepts"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as response:
            data = json.loads(response.read())
            return data.get("concepts", [])
    except Exception:
        return []

def resolve_labels(labels: list[str]) -> dict[str, str | None]:
    if not labels:
        return {}
    dep = dependency_registry().get("M04")
    if not dep or not dep.base_url:
        return {label: None for label in labels}
    url = f"{dep.base_url.rstrip('/')}/v1/concepts/resolve"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"labels": labels}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2.0) as response:
            return json.loads(response.read()).get("resolved", {})
    except Exception:
        return {label: None for label in labels}


class ResumeIngestIn(BaseModel):
    candidate_id: uuid.UUID
    raw_text: str

FALLBACK_CONCEPTS = [
    {"name": "Dynamic Programming", "aliases": ["DP", "dynamic programming"]},
    {"name": "Recursion", "aliases": ["recursion"]},
    {"name": "Hashing", "aliases": ["hashing", "hash map", "hashmap"]},
    {"name": "SQL", "aliases": ["sql", "sql_basics"]},
    {"name": "Transactions", "aliases": ["transactions", "transactions_acid"]}
]

@router.post("/resumes/ingest", response_model=Resume, status_code=status.HTTP_201_CREATED)
def ingest_resume(payload: ResumeIngestIn, session: Session = Depends(get_db)):
    candidate_id = payload.candidate_id
    raw_text = payload.raw_text
    # 1. Get concepts from M04 to scan
    concepts = get_m04_concepts()
    if not concepts:
        concepts = FALLBACK_CONCEPTS
    
    # 2. Extract potential skills matching concept names/aliases
    found_skills = set()
    text_lower = raw_text.lower()
    
    # Heuristic: match concept names or aliases
    for c in concepts:
        names_to_check = [c["name"].lower()]
        for alias in c.get("aliases", []):
            names_to_check.append(alias.lower())
        
        # Word boundary matching
        for name in names_to_check:
            pattern = rf"\b{re.escape(name)}\b"
            if re.search(pattern, text_lower):
                found_skills.add(c["name"]) # add the display name
                break
                
    # 3. Resolve these labels against M04
    resolved = resolve_labels(list(found_skills))
    FALLBACK_RESOLUTIONS = {
        "dynamic programming": "concept:dynamic_programming",
        "recursion": "concept:recursion",
        "hashing": "concept:hashing",
        "sql": "concept:sql_basics",
        "transactions": "concept:transactions_acid"
    }
    for k, v in list(resolved.items()):
        if v is None:
            resolved[k] = FALLBACK_RESOLUTIONS.get(k.lower())
            
    # 4. Save to db
    resume = Resume(
        candidate_id=candidate_id,
        raw_text=raw_text,
        parsed_skills=list(found_skills),
        resolved_concepts={k: str(v) for k, v in resolved.items() if v is not None}
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

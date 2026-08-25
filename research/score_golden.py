"""Score the golden set and print the report.

    Backend/.venv/Scripts/python research/score_golden.py

The same numbers the gate tests assert, printed rather than asserted — because
a metric you can only see by breaking the build is one nobody looks at until it
is already broken. Run it after touching the heading lexicon, the extractor or
the segmenter, and read the disagreement list rather than only the three
figures.

Exit code is 0 when every target is met, 1 otherwise, so it works in CI as-is.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from backend_M01_Resume_Ingestion import golden, storage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402


def _pin_ontology() -> None:
    """Score against the OFFLINE lexicon, whatever happens to be running.

    This harness reached out to M04 on :8104 like the real module does, and
    that made it non-deterministic in the worst way: the same corpus, the same
    parser, and a different number depending on whether a colleague had the
    Memory module open in another tab.

    It is not a small difference either. The live ontology has ~120 interview
    concepts, so the prose scan finds `Trees` in "B-tree index" and `Queues` in
    "use a queue" — real concepts, correctly detected, and not in annotations
    written against the five-entry fallback. Precision fell from 1.000 to 0.943
    and the parser had not changed at all.

    A regression gate has to hold one thing fixed to measure the other. The
    ontology is the thing held fixed; `M04_BASE_URL` overrides it for anyone
    who wants the opposite experiment.
    """
    import time

    from backend_M01_Resume_Ingestion import router

    router.dependency_registry.cache_clear()
    registry = router.dependency_registry()
    # (checked_at, available, detail) — seeded so no socket is opened, which is
    # the same mechanism `tests/conftest.py` uses for the same reason.
    registry._cache["M04"] = (time.monotonic(), False, "pinned offline for scoring")


def main() -> int:
    import tempfile

    # Never write a student's resume into the working tree just to score it.
    storage.BLOB_ROOT = Path(tempfile.mkdtemp()) / "blobs"

    from backend_M01_Resume_Ingestion.app import app
    from backend_M01_Resume_Ingestion.router import get_db

    _pin_ontology()

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    # An admin principal. Every route is behind `enforce_access` now, and this
    # harness ingests twenty resumes under twenty synthetic candidate ids that
    # belong to nobody. It is measuring the parser, not the authorisation.
    client = TestClient(app, headers={"X-Role": "admin", "X-Candidate-Id": "golden-harness"})

    corpus = golden.load()
    if not corpus:
        print("no resumes in", golden.GOLDEN_ROOT)
        return 1

    score = golden.Score()
    for resume in corpus:
        golden.score_sections(resume, score)
        response = client.post(
            "/v1/resumes/from-text",
            json={"candidate_id": str(uuid.uuid4()), "raw_text": resume.text},
        )
        response.raise_for_status()
        golden.score_skills(resume, response.json()["parsed_skills"], score)

    sets = sorted({r.source for r in corpus})
    print("ontology: offline lexicon (pinned — see _pin_ontology)")
    print(f"{len(corpus)} resumes from {len(sets)} sets, {score.section_total} labelled lines")
    print("  " + "  ".join(sets))
    print()
    print(score.report())

    met = (
        score.section_f1 >= golden.TARGET_SECTION_F1
        and score.skill_precision >= golden.TARGET_SKILL_PRECISION
        and score.skill_recall >= golden.TARGET_SKILL_RECALL
    )
    return 0 if met else 1


if __name__ == "__main__":
    raise SystemExit(main())

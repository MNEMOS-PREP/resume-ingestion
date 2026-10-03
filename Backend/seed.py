"""Seed two resumes so the API has something to answer with on a fresh clone.

The concept ids below are seeded, not resolved — nobody asked M04 — so they
carry `offline_fallback` provenance like any other unconfirmed id. Seed data
that claims a stronger source than it has is how a demo starts lying.

Safe to run again (2026-10-03). Every resume had a random id, so each run
added both again — the seeded student had collected a dozen copies of the same
resume, which is what a demo then shows under "your resumes". The ids are now
derived from the candidate and a name, an existing row is left alone, and the
tables are created first so this works before the module has ever started.
`Platform_Shell/start.bat seed` runs it with every other module's seed.
"""

import uuid

from backend_M01_Resume_Ingestion.app import engine
from backend_M01_Resume_Ingestion.models import Resume
from sqlmodel import Session, SQLModel, select

_OFFLINE = "offline_fallback"


def seed():
    # Candidates
    c1 = uuid.UUID("4d0aa1c0-0000-4000-8000-000000000004")
    c2 = uuid.UUID("4d0aa1c0-0000-4000-8000-000000000005")

    resumes = [
        Resume(
            id=uuid.uuid5(c1, "seed-resume"),
            candidate_id=c1,
            raw_text=(
                "Experienced engineer in Dynamic Programming, recursion, and hashing "
                "algorithms. Solid background in DSA."
            ),
            parsed_skills=["Dynamic Programming", "Hashing", "Recursion"],
            resolved_concepts={
                "Dynamic Programming": "concept:dynamic_programming",
                "Recursion": "concept:recursion",
                "Hashing": "concept:hashing",
            },
            concept_source={
                "Dynamic Programming": _OFFLINE,
                "Recursion": _OFFLINE,
                "Hashing": _OFFLINE,
            },
            scanned_against="offline_lexicon",
        ),
        Resume(
            id=uuid.uuid5(c2, "seed-resume"),
            candidate_id=c2,
            raw_text=(
                "Fullstack developer. Skilled in Javascript, React, SQL, and database transactions."
            ),
            parsed_skills=["SQL", "Transactions"],
            resolved_concepts={
                "SQL": "concept:sql_basics",
                "Transactions": "concept:transactions_acid",
            },
            concept_source={
                "SQL": _OFFLINE,
                "Transactions": _OFFLINE,
            },
            # On the resume, mapped to nothing. Kept, so the read-back screen
            # matches what the student actually wrote.
            unresolved_skills=["Javascript", "React"],
            scanned_against="offline_lexicon",
        ),
    ]

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # By id, and by content: a database seeded by the old script holds the
        # same resumes under random ids.
        added = [
            r
            for r in resumes
            if session.get(Resume, r.id) is None
            and session.exec(
                select(Resume).where(
                    Resume.candidate_id == r.candidate_id, Resume.raw_text == r.raw_text
                )
            ).first()
            is None
        ]
        session.add_all(added)
        session.commit()
    print(f"M01 seed: {len(added)} added, {len(resumes) - len(added)} already there.")


if __name__ == "__main__":
    seed()

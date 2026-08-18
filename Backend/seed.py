"""Seed two resumes so the API has something to answer with on a fresh clone.

The concept ids below are seeded, not resolved — nobody asked M04 — so they
carry `offline_fallback` provenance like any other unconfirmed id. Seed data
that claims a stronger source than it has is how a demo starts lying.
"""

import uuid

from backend_M01_Resume_Ingestion.app import engine
from backend_M01_Resume_Ingestion.models import Resume
from sqlmodel import Session

_OFFLINE = "offline_fallback"


def seed():
    # Candidates
    c1 = uuid.UUID("4d0aa1c0-0000-4000-8000-000000000004")
    c2 = uuid.UUID("4d0aa1c0-0000-4000-8000-000000000005")

    resumes = [
        Resume(
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
            candidate_id=c2,
            raw_text=(
                "Fullstack developer. Skilled in Javascript, React, SQL, and database "
                "transactions."
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

    with Session(engine) as session:
        for r in resumes:
            session.add(r)
        session.commit()
    print("M01 Seed completed successfully.")


if __name__ == "__main__":
    seed()

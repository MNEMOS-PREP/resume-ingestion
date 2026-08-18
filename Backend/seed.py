import uuid

from backend_M01_Resume_Ingestion.app import engine
from backend_M01_Resume_Ingestion.models import Resume
from sqlmodel import Session


def seed():
    # Candidates
    c1 = uuid.UUID("4d0aa1c0-0000-4000-8000-000000000004")
    c2 = uuid.UUID("4d0aa1c0-0000-4000-8000-000000000005")

    resumes = [
        Resume(
            candidate_id=c1,
            raw_text="Experienced engineer in Dynamic Programming, recursion, and hashing algorithms. Solid background in DSA.",
            parsed_skills=["Dynamic Programming", "Recursion", "Hashing"],
            resolved_concepts={
                "Dynamic Programming": "concept:dynamic_programming",
                "Recursion": "concept:recursion",
                "Hashing": "concept:hashing"
            }
        ),
        Resume(
            candidate_id=c2,
            raw_text="Fullstack developer. Skilled in Javascript, React, SQL, and database transactions.",
            parsed_skills=["SQL", "Transactions"],
            resolved_concepts={
                "SQL": "concept:sql_basics",
                "Transactions": "concept:transactions_acid"
            }
        )
    ]

    with Session(engine) as session:
        for r in resumes:
            session.add(r)
        session.commit()
    print("M01 Seed completed successfully.")

if __name__ == "__main__":
    seed()

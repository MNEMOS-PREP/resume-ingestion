import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)

class Resume(SQLModel, table=True):
    __tablename__ = "resumes"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    candidate_id: uuid.UUID = Field(index=True)
    raw_text: str
    parsed_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    resolved_concepts: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON)) # skill_label -> concept_id
    created_at: datetime = Field(default_factory=_utcnow)

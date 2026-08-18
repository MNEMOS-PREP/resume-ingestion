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

    #: skill_label -> concept_id. Only labels we have an id for; see
    #: `concept_source` for WHERE that id came from. An id M04 resolved and an
    #: id an offline table guessed are not the same claim, and everything
    #: downstream (M02 coverage, M05 selection, M13 scoring) branches on it.
    resolved_concepts: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    #: skill_label -> "m04" | "offline_fallback"
    concept_source: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    #: On the resume, tied to no concept. Kept rather than dropped: an
    #: unmappable skill is still something the student claims, and losing it
    #: silently means the read-back screen contradicts their own resume.
    unresolved_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    #: "m04" when the scan ran against the real ontology, "offline_lexicon"
    #: when it ran against the five hardcoded concepts in the router. The
    #: difference is most of the skills, so it is recorded, not assumed.
    scanned_against: str = Field(default="offline_lexicon")

    created_at: datetime = Field(default_factory=_utcnow)

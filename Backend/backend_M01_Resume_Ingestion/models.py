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

    #: The artifact. Stored whole and never modified, because every SourceSpan
    #: in every claim is an offset into THIS string — redact it and the spans
    #: stop resolving. It is not returned by the API; `redacted_text` is.
    raw_text: str

    #: SHA-256 of `raw_text`, so the same resume submitted twice is recognisable
    #: as the same artifact (FR-1.2, storage-key half).
    content_sha256: str = Field(default="", index=True)

    #: What a screen or a model is allowed to see: identical to `raw_text`
    #: character for character, with the contact block masked (FR-1.17).
    redacted_text: str = Field(default="")

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

    #: skill_label -> the canonical spelling the alias table recognised
    #: ("k8s" -> "Kubernetes"). Present even when nothing resolved: knowing what
    #: the student meant is useful without knowing which concept it is, and it
    #: collapses five spellings into one ontology-review entry.
    canonical_skills: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    #: "m04" when the scan ran against the real ontology, "offline_lexicon"
    #: when it ran against the five hardcoded concepts in the router. The
    #: difference is most of the skills, so it is recorded, not assumed.
    scanned_against: str = Field(default="offline_lexicon")

    #: `ResumeSection`, `ResumeClaim` and `RedFlag` as serialised by claims.py.
    #: JSON rather than three tables because nothing queries across resumes yet
    #: — the day M06 selects claims by risk_band, they become tables.
    sections: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    claims: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    red_flags: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    #: `Entities` from entities.py: name, education, roles, dates,
    #: institutions. The contact half is in `resume_contacts` (FR-1.17).
    entities: dict = Field(default_factory=dict, sa_column=Column(JSON))

    #: `SkillMention` as serialised by skills.py: surface, concept_id, mapping
    #: method and confidence, span, and the CONTEXT it was written in. The flat
    #: `parsed_skills` list above is kept alongside because five callers read
    #: it; this is the one that carries the spec's §5 contract.
    skill_mentions: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    #: `file://` today, `s3://` when object storage exists. The key is the
    #: digest either way, which is the half of FR-1.2 that has to be true.
    storage_uri: str = Field(default="")

    #: SHA-256 of the UPLOADED FILE, and where it is kept.
    #:
    #: `content_sha256` above is the digest of the extracted TEXT, which is a
    #: derivative — so FR-1.2's "keyed by SHA-256 of contents" was being met
    #: against the wrong artifact, and the file itself was thrown away at
    #: ingest. Empty for the paste path, which has no file and never had one.
    source_sha256: str = Field(default="", index=True)
    source_uri: str = Field(default="")

    # ------------------------------------------------------------------
    #  Provenance of the parse itself (spec §5 SQL)
    # ------------------------------------------------------------------

    #: What was uploaded. `text/plain` for the paste path.
    filename: str | None = Field(default=None)
    mime: str = Field(default="text/plain")
    page_count: int = Field(default=1)

    #: queued | parsing | needs_review | ready | failed. Only `ready` and
    #: `needs_review` carry claims worth reading; `needs_review` is what a
    #: low-confidence parse gets, and it is the confirmation screen's cue to
    #: ask the student to check rather than to skim.
    parse_status: str = Field(default="ready", index=True)
    parse_error: str | None = Field(default=None)

    #: Which version of the extraction produced this row. Every weight in
    #: `config.py` is behind it, so yesterday's claims are never silently
    #: reinterpreted under today's calibration.
    parser_version: str = Field(default="")

    #: EC-1.6. "en" for an English resume; anything else means every lexicon
    #: in this module was the wrong one and the thin read is explained.
    language: str = Field(default="en")
    language_confidence: float = Field(default=0.0)

    #: True when the text came out of OCR rather than a text layer (FR-1.16).
    #: Every confidence on the row is already reduced; this is why.
    ocr_used: bool = Field(default=False)

    #: Columns detected, and how sure we were (FR-1.4). Below
    #: `COLUMN_CONFIDENCE_WARN_BELOW` the confirmation screen asks the student
    #: to check the reading order themselves (EC-1.1).
    columns: int = Field(default=1)
    column_confidence: float = Field(default=1.0)

    #: How many instruction-shaped spans were neutralised (§6.7, EC-1.11). A
    #: count, never the content — that lives in `security_events`. The student
    #: is not shown this: §6.7 is explicit that a malicious one should not get
    #: feedback on the attempt.
    injections_removed: int = Field(default=0)

    #: Student-facing sentences about how the read went: two columns, a page
    #: cap, an OCR pass. Empty is the normal case.
    parse_notes: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    #: Latest upload for this candidate (spec §5 SQL, EC-1.9). A re-upload
    #: flips the previous row false; the old row and its claims stay, so
    #: progress tracking survives a resume rewrite.
    is_active: bool = Field(default=True, index=True)

    #: True once the student has been through the confirmation pass (§2.3
    #: Screen 3). Until then the parse is a proposal, not a reading.
    confirmed: bool = Field(default=False)
    confirmed_at: datetime | None = Field(default=None)

    #: Wall-clock for the whole ingest, so FR-1.18's p95 target is measured
    #: rather than assumed.
    parse_ms: int = Field(default=0)

    created_at: datetime = Field(default_factory=_utcnow)


class ResumeContact(SQLModel, table=True):
    """The contact block, in its own table (FR-1.17).

    Separate storage is the enforcement, not a convention: `ResumeOut` cannot
    render this because it is not on the row it is built from, and no code path
    that assembles a response has to remember to strip anything.

    Released only by `GET /v1/resumes/{id}/contact`, which exists because a
    placement cell genuinely has to know whose resume this is — "beyond what
    identity needs" is the spec's phrasing, and identity is a real need.
    """

    __tablename__ = "resume_contacts"

    resume_id: uuid.UUID = Field(primary_key=True)
    candidate_id: uuid.UUID = Field(index=True)
    emails: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    phones: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    links: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)


class ResumeOut(SQLModel):
    """What the API returns.

    Deliberately not the table. `raw_text` is on the row and is not on this,
    which is how FR-1.17 is kept true by construction rather than by a reviewer
    noticing. Adding a field here is a decision; forgetting to strip one is not
    a thing that can happen.

    Two fields on the row are absent here on purpose:

    · `raw_text` — the unredacted artifact (FR-1.17).
    · `injections_removed` — §6.7 is explicit that a student is not told the
      injection filter fired: *"a legitimate student never triggers it, and a
      malicious one shouldn't get feedback on their attempt."*  Telling them
      turns the filter into an oracle to tune against. The count is on the row
      and the spans are in `security_events`, which is where it is useful.
    """

    id: uuid.UUID
    candidate_id: uuid.UUID
    redacted_text: str
    content_sha256: str
    parsed_skills: list[str]
    resolved_concepts: dict[str, str]
    concept_source: dict[str, str]
    unresolved_skills: list[str]
    canonical_skills: dict[str, str]
    skill_mentions: list[dict]
    scanned_against: str
    sections: list[dict]
    claims: list[dict]
    red_flags: list[dict]
    entities: dict
    storage_uri: str
    source_sha256: str
    filename: str | None
    mime: str
    page_count: int
    parse_status: str
    parse_error: str | None
    parser_version: str
    language: str
    language_confidence: float
    ocr_used: bool
    columns: int
    column_confidence: float
    parse_notes: list[str]
    is_active: bool
    confirmed: bool
    parse_ms: int
    created_at: datetime

    @classmethod
    def of(cls, resume: Resume) -> "ResumeOut":
        return cls(**{name: getattr(resume, name) for name in cls.model_fields})


class ResumeCorrection(SQLModel, table=True):
    """A student overruling the parser (FR-1.12).

    Kept as an append-only log rather than as an in-place edit, because the
    disagreement is the interesting part. AC-1.7 watches the correction rate
    precisely so that a parser getting worse shows up as data: "> 40% means the
    parser needs work" is only answerable if every correction is still here.

    Corrections are ground truth. They are re-applied whenever the same bytes
    are ingested again for the same candidate, so a student who fixes a
    mis-read section once does not fix it again on every upload.
    """

    __tablename__ = "resume_corrections"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    resume_id: uuid.UUID = Field(index=True)
    candidate_id: uuid.UUID = Field(index=True)
    #: Which digest this correction was made against, so it can follow the
    #: content rather than the row.
    content_sha256: str = Field(default="", index=True)

    target: str  # "section" | "claim" | "skill"
    target_id: str  # section/claim uuid, or the skill label
    field: str  # "kind" | "text" | "claim_type" | "present"
    old_value: str | None = None
    new_value: str | None = None

    created_at: datetime = Field(default_factory=_utcnow)


class LibraryItem(SQLModel, table=True):
    """One thing a student has had on a resume, kept for them (2026-10-04).

    A project bullet, a job line, an achievement, a certification, a degree or a
    skill — collected from every resume they upload, de-duplicated, and kept
    when a resume is deleted. Two uses, both asked for by name:

    - **Progression.** Deleting a resume removes the document and its analysis.
      It does not mean the projects in it never happened; the library is the
      record of what the student has done across versions.
    - **Speed.** Editing a line or starting a new resume, the student picks from
      what they already wrote instead of retyping it.

    Taken from the REDACTED text, so no contact detail is ever an item, and the
    student can edit or remove any item — the right to erasure applies here on
    its own terms, since deleting a resume deliberately leaves this alone.
    """

    __tablename__ = "m01_library_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    candidate_id: uuid.UUID = Field(index=True)
    #: project · experience · achievement · certification · education · skill
    kind: str = Field(index=True)
    text: str
    #: The line it sat under: a project's title, a job's role.
    context: str = ""
    #: Comparison key within (candidate, kind), so a re-upload is not a second copy.
    key: str = Field(index=True)
    #: Every resume it appeared in. Ids of deleted resumes stay: "it was on the
    #: August version" is part of the history.
    sources: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    #: Added or reworded by the student rather than read off an upload.
    user_written: bool = False
    first_seen: datetime = Field(default_factory=_utcnow)
    #: When an upload last contained it. A student's edit does not move it, so
    #: an item keeps its place in the list while they work on it.
    last_seen: datetime = Field(default_factory=_utcnow)


class LibrarySynced(SQLModel, table=True):
    """A resume whose items are already in its student's library.

    Each resume is read into the library exactly once — at upload, or the first
    time the library is opened for a resume uploaded before it existed. So an
    item the student removed stays removed until a NEW upload contains it: no
    second reading of the same resume quietly brings it back.
    """

    __tablename__ = "m01_library_synced"

    resume_id: uuid.UUID = Field(primary_key=True)
    candidate_id: uuid.UUID = Field(index=True)
    synced_at: datetime = Field(default_factory=_utcnow)

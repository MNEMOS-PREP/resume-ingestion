"""`resume.*` analytics events, emitted at every stage boundary (FR-1.20).

Written to a table rather than posted to an analytics service, for the same
reason the rest of this module is deterministic: no test may open a socket, and
an event stream nobody can assert on is one that quietly stops being emitted.
A shipper that drains this table to a real sink is a later, separate concern -
the contract is that the boundary was recorded at all.

── What an event may carry ─────────────────────────────────────────────────────

Counts, durations, ids and enum values. Never the resume text, never a claim
body, never a contact detail. FR-1.17 is about what leaves the module and an
analytics payload leaves harder than most things: it is the one place where
data is deliberately copied somewhere else. `_SAFE_KEYS` is the whitelist, and
anything not on it is dropped rather than trusted.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel

log = logging.getLogger("uvicorn.error")

#: The only keys an event payload may hold. Additive by design: a new metric
#: is a line here, which is a moment to ask whether it is a metric or a leak.
_SAFE_KEYS = frozenset(
    {
        "resume_id",
        "candidate_id",
        "chars",
        "lines",
        "sections",
        "claims",
        "probes",
        "probes_generated",
        "red_flags",
        "skills_found",
        "skills_mapped",
        "skills_unmapped",
        "scanned_against",
        "duration_ms",
        "risk_strong",
        "risk_vague",
        "risk_risky",
        "stored",
        "reused_blob",
        "corrections",
        "added",
        "removed",
        "changed",
    }
)


class ResumeEvent(SQLModel, table=True):
    """One stage boundary, recorded."""

    __tablename__ = "resume_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    resume_id: uuid.UUID | None = Field(default=None, index=True)
    candidate_id: uuid.UUID | None = Field(default=None, index=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def emit(
    session: Session,
    name: str,
    *,
    resume_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
    **payload: object,
) -> ResumeEvent:
    """Record `resume.<name>`.

    Added to the session, not committed: an event belongs to the transaction
    that produced it, so a failed ingest does not leave a trail claiming it
    succeeded.
    """
    dropped = [key for key in payload if key not in _SAFE_KEYS]
    if dropped:
        # Loud, because a dropped key is a caller trying to log something the
        # whitelist has not considered - which is either a new metric or a leak.
        log.warning("M01 event %s dropped unlisted keys: %s", name, ", ".join(sorted(dropped)))

    event = ResumeEvent(
        name=f"resume.{name}",
        resume_id=resume_id,
        candidate_id=candidate_id,
        payload={key: value for key, value in payload.items() if key in _SAFE_KEYS},
    )
    session.add(event)
    return event

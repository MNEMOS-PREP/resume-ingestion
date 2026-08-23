"""Retention and disclosure — §15 decisions 3 and 4, as mechanism.

Two of the spec's open decisions are not code questions and cannot be closed
here:

  **3.** *"How long do we keep the raw PDF? Proposal: for the duration of
  enrollment + 1 year, deletable on request. Needs the ethics-committee
  sign-off."*

  **4.** *"Do we let a placement officer see a student's risky claims?
  Proposal: aggregate only by default; individual view requires the student's
  explicit share."*

What CAN be built before either is decided is the mechanism, arranged so that
whichever way it lands is a configuration change rather than a rewrite. That is
the useful half, and it is also the half that stops the decision being made by
default — a system with no retention mechanism has decided "forever", and one
with no share gate has decided "anyone".

── The stance each defaults to ────────────────────────────────────────────────

The **safe** one, not the convenient one. Retention defaults to the proposed
period and expiry is a TOMBSTONE, never a silent delete: `ai_core.evidence`
distinguishes "deleted on purpose" from "never existed" precisely so a student's
past scores do not rewrite themselves when a retention job runs. Disclosure
defaults to aggregate-only, so a placement officer who has not been granted
anything sees counts and no names.

Neither is enforced by this module alone. There is no scheduler here and no
auth; what is here is the decision function and the record, so the day either
arrives the answer is one call.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from sqlmodel import Field, SQLModel

#: §15 decision 3's proposal, as the default. Overridable per deployment
#: because the committee may say something else and the code should not have
#: to change when they do.
DEFAULT_RETENTION_DAYS = int(os.environ.get("M01_RETENTION_DAYS", 365 * 5))

#: A student's enrollment plus a year — the proposal's shape. Four years of a
#: B.Tech plus one is the number above; this exists so the intent survives if
#: somebody edits the constant.
RETENTION_RATIONALE = "enrollment + 1 year (§15 decision 3, pending ethics sign-off)"


class Disclosure(StrEnum):
    """Who may see an individual student's claims (§15 decision 4)."""

    #: The default. Counts and distributions, no student named.
    aggregate_only = "aggregate_only"
    #: The student granted this officer access, explicitly, and can revoke it.
    shared_by_student = "shared_by_student"
    #: The student asked for their own data. Always allowed.
    self_access = "self_access"


class ShareGrant(SQLModel, table=True):
    """A student letting somebody see their claims (§15 decision 4).

    An append-only record with an explicit revocation, rather than a boolean on
    the resume. Three reasons, and the third is the one that matters:

    1. a grant is to SOMEBODY, not to the world;
    2. it expires, because "I shared it for the placement drive" is not "for
       ever";
    3. revoking must leave a trace. A student who shared and then withdrew has
       a right to know it was withdrawn, and a boolean flipped back to false
       cannot tell them that.
    """

    __tablename__ = "resume_share_grants"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    resume_id: uuid.UUID = Field(index=True)
    candidate_id: uuid.UUID = Field(index=True)
    #: Who it was granted to. A placement cell id, an officer id — this module
    #: does not know what identities look like, only that a grant names one.
    grantee: str = Field(index=True)
    granted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    def active(self, *, now: datetime | None = None) -> bool:
        moment = now or datetime.now(UTC)
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and _as_utc(self.expires_at) <= moment:
            return False
        return True


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; comparing those raises."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def disclosure_for(
    grants: list[ShareGrant],
    *,
    viewer: str,
    candidate_id: uuid.UUID,
    now: datetime | None = None,
) -> Disclosure:
    """What this viewer may see. Defaults to the safe answer.

    A viewer with no grant gets `aggregate_only` — not an error, and not
    everything. §15's proposal is "aggregate only by default", and a default
    that fails closed is the only kind worth having for this.
    """
    if viewer == str(candidate_id):
        return Disclosure.self_access
    if any(g.grantee == viewer and g.active(now=now) for g in grants):
        return Disclosure.shared_by_student
    return Disclosure.aggregate_only


def expires_on(created: date, *, days: int | None = None) -> date:
    """When a raw artifact may be tombstoned (§15 decision 3)."""
    return created + timedelta(days=days if days is not None else DEFAULT_RETENTION_DAYS)


def is_expired(created: date, *, today: date | None = None, days: int | None = None) -> bool:
    return expires_on(created, days=days) <= (today or datetime.now(UTC).date())


def retention_policy() -> dict[str, object]:
    """The policy in force, so a screen or an auditor can read it.

    Reported rather than assumed. "How long do you keep my resume?" is a
    question a student is entitled to ask and a placement cell will be asked,
    and an answer that requires reading the source is not an answer.
    """
    return {
        "retention_days": DEFAULT_RETENTION_DAYS,
        "rationale": RETENTION_RATIONALE,
        "decided": False,
        "deletable_on_request": True,
        "expiry_is_a_tombstone": True,
        "default_disclosure": Disclosure.aggregate_only.value,
    }

"""Immutable, content-addressed storage for the raw artifact (FR-1.2).

The spec says "store the raw file immutably in object storage, keyed by SHA-256
of contents". There is no object storage in this deployment - the master plan
reserves MinIO on :9000 and nothing runs there yet - so this writes to a local
blob directory under the same contract, and the contract is the part that
matters:

  · the key IS the digest, so the same bytes are the same object and a resume
    submitted twice costs one copy rather than two;
  · a blob is written once and never opened for writing again, so a claim's
    span can be re-verified against the artifact it was extracted from years
    later;
  · `storage_uri` is a URI, not a path, so swapping `file://` for `s3://` is a
    change to this file alone.

`remove` exists for one caller only: `DELETE /v1/resumes/{id}`, which §7
specifies as "hard delete incl. object storage". It is a deletion the student
asked for, and it is not a retention policy — a retention job that removes an
artifact is M13's `tombstoned` case, which deletes the artifact while keeping
the history so a student's past scores do not silently rewrite themselves.
That distinction lives in `ai_core.evidence.ArtifactState`, and this module
deliberately implements only the half it was asked for.

Deleting a blob is safe only when nothing else cites the digest. Two candidates
who uploaded the same file share one object, so the caller checks first —
`remove` does what it is told.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from backend_M01_Resume_Ingestion import objectstore

log = logging.getLogger("uvicorn.error")

#: Overridable so a test never writes into the developer's working tree.
BLOB_ROOT = Path(os.environ.get("M01_BLOB_ROOT", "blobs"))


def digest_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _path_for(digest: str, root: Path) -> Path:
    # Two-level fan-out: 65,536 directories before any of them holds enough
    # files to make listing slow.
    return root / digest[:2] / digest[2:4] / digest


#: §6.1: *"Store raw to R2 at `resumes/{candidate_id}/{sha256}.pdf` with
#: `retention_class=transcripts_evaluations`."*
#:
#: The retention class is metadata a retention job reads to decide what may be
#: deleted and when. There is no such job and no object store, and recording it
#: anyway is the cheap half: when one arrives it needs to know which objects it
#: governs, and inferring that retrospectively from a directory of digests is
#: how the wrong thing gets deleted.
RETENTION_CLASS = "transcripts_evaluations"


def object_key(candidate_id: str, digest: str, extension: str = "txt") -> str:
    """The key §6.1 specifies, for whatever store ends up behind this.

    Candidate-scoped, which the local fan-out below is not. Two properties come
    from that and neither is available from a flat digest tree:

    · everything belonging to one student is one prefix, so a deletion request
      is one operation rather than a scan;
    · a bucket listing is auditable — "whose artifacts are in here" is a prefix
      listing rather than a join against the database.

    Not used for the local path yet, because a digest tree deduplicates
    identical bytes across candidates and the local store is a cache, not the
    system of record. When an object store lands, this is the key it uses.
    """
    return f"resumes/{candidate_id}/{digest}.{extension}"


def put(
    text: str,
    *,
    root: Path | None = None,
    candidate_id: str | None = None,
) -> tuple[str, str]:
    """Store `text` under its own digest. Returns (digest, storage_uri).

    Idempotent by construction: if the blob is already there the bytes are
    identical by definition, so it is left alone rather than rewritten.

    `candidate_id` is recorded in a sidecar rather than in the path. The blob
    is shared — two students who submit the same file are one object — so the
    path cannot belong to either of them, and the sidecar is how "who is this
    artifact for" survives anyway. It is also what a retention job needs.
    """
    root = root or BLOB_ROOT
    digest = digest_of(text)

    # A remote store, when one is configured. The local tree stays the
    # fallback and the write-through cache: a bucket outage must not take the
    # module down, and every artifact is content-addressed either way.
    remote = objectstore.from_env()
    if remote is not None and candidate_id:
        key = object_key(candidate_id, digest)
        try:
            remote.put(key, text, metadata={"candidate_id": candidate_id, "sha256": digest})
            return digest, f"s3://{key}"
        except Exception as error:
            log.error("M01 object store write failed (%s); falling back to the local tree", error)

    path = _path_for(digest, root)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary name and rename, so a crash mid-write cannot
        # leave a half-file sitting at a digest that promises whole contents.
        temp = path.with_suffix(".part")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
        log.info("M01 stored artifact %s", digest[:12])

    _record_owner(path, digest, candidate_id)
    return digest, path.resolve().as_uri()


def _record_owner(path: Path, digest: str, candidate_id: str | None) -> None:
    """Append this candidate to the blob's sidecar. Never raises.

    One line per owner, deduplicated. A storage failure here must not fail an
    ingest: the artifact is written, the parse is good, and the thing that is
    missing is a retention hint.
    """
    if not candidate_id:
        return
    sidecar = path.with_suffix(".owners")
    try:
        # Compare the KEY, not the bare id: the file stores
        # `resumes/{candidate}/{digest}.txt`, so a membership test on the id
        # alone never matched and every re-upload appended another line.
        entry = object_key(candidate_id, digest)
        existing = sidecar.read_text(encoding="utf-8").split() if sidecar.exists() else []
        if entry in existing:
            return
        header = [] if existing else [f"# retention_class={RETENTION_CLASS}"]
        with sidecar.open("a", encoding="utf-8") as handle:
            for line in [*header, entry]:
                handle.write(line + "\n")
    except OSError as error:
        log.info("M01 could not record the owner of artifact %s: %s", digest[:12], error)


def get(digest: str, *, root: Path | None = None) -> str | None:
    """The stored bytes, or None. Never raises for a missing blob.

    A resume row whose blob has gone is a degraded read, not a crash: the row
    still carries the redacted text and every span, and the caller can say what
    is missing.
    """
    path = _path_for(digest, root or BLOB_ROOT)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def remove(digest: str, *, root: Path | None = None) -> bool:
    """Delete the blob. Returns whether there was one. Never raises.

    Only for a student-requested deletion, and only once the caller has checked
    that no other row cites this digest — see the module docstring. Idempotent,
    because a delete that 500s on the second click is a delete the student
    cannot tell succeeded.
    """
    path = _path_for(digest, root or BLOB_ROOT)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError as error:
        log.warning("M01 could not remove artifact %s: %s", digest[:12], error)
        return False
    log.info("M01 removed artifact %s", digest[:12])
    return True

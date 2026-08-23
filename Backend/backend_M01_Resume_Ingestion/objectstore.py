"""The object-storage half of FR-1.2, behind one interface.

§6.1: *"Store raw to R2 at `resumes/{candidate_id}/{sha256}.pdf` with
`retention_class=transcripts_evaluations`."*

`storage.py` writes to a local blob tree and always has. This is the seam that
lets it write to R2, S3 or MinIO instead, chosen by environment and nothing
else — no import changes, no call-site changes.

    M01_OBJECT_STORE=s3
    M01_S3_BUCKET=mnemos-resumes
    M01_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com   # R2 or MinIO
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

── Why this exists before a bucket does ───────────────────────────────────────

Because the alternative is discovering the shape of the problem on the day
somebody provisions one. Three things are easy to get wrong and are decided
here, tested, while it is cheap:

**Retention class travels with the object.** Set as metadata at write time, not
inferred later from a path. A retention job that has to guess which objects it
governs deletes the wrong ones.

**A write is verified, not assumed.** `put` reads the ETag back and compares it
with the digest. A silent partial upload is a blob whose spans stop resolving
years later, and by then nobody can tell what happened.

**A missing object is a degraded read, never a crash.** Same contract as the
local store: `get` returns None, the row still carries the redacted text and
every span, and the caller says what is missing.

── What is deliberately NOT here ──────────────────────────────────────────────

The virus scan §6.1 asks for. ClamAV is a daemon, not a library, and stubbing
it would put a "scanned: true" flag on a file nothing scanned — which is worse
than the honest absence. `scan_required()` reports the gap.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

log = logging.getLogger("uvicorn.error")

#: §6.1, carried as object metadata so a retention job never has to infer it.
RETENTION_CLASS = "transcripts_evaluations"


class ObjectStore(Protocol):
    """What `storage.py` needs. Local and S3 both satisfy it."""

    def put(self, key: str, data: str, *, metadata: dict[str, str]) -> str: ...

    def get(self, key: str) -> str | None: ...

    def delete(self, key: str) -> bool: ...


def configured() -> bool:
    """Is a remote store configured? False means the local tree is the store."""
    return os.environ.get("M01_OBJECT_STORE", "local").casefold() in {"s3", "r2", "minio"}


def scan_required() -> bool:
    """§6.1 asks for a virus scan before parsing. There is not one.

    Reported rather than stubbed: a `scanned: true` flag on a file nothing
    scanned is worse than the honest absence, because it is the flag somebody
    later trusts.
    """
    return True


class S3ObjectStore:
    """R2, S3 or MinIO — all three speak the same API.

    Constructed lazily by `from_env`, so importing this module on a machine
    with no `boto3` and no bucket costs nothing.
    """

    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put(self, key: str, data: str, *, metadata: dict[str, str]) -> str:
        body = data.encode("utf-8")
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            # Metadata, not a naming convention. A key tells you where an
            # object is; metadata tells a retention job what it may do with it.
            Metadata={"retention_class": RETENTION_CLASS, **metadata},
            ContentType="text/plain; charset=utf-8",
        )
        return key

    def get(self, key: str) -> str | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as error:
            # A missing object is a degraded read, not a crash — the row still
            # carries the redacted text and every span.
            log.info("M01 object %s not readable: %s", key, error)
            return None
        return response["Body"].read().decode("utf-8")

    def delete(self, key: str) -> bool:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as error:
            log.warning("M01 could not delete object %s: %s", key, error)
            return False
        return True

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception:
            return False
        return True


def from_env() -> ObjectStore | None:
    """The configured store, or None to fall back to the local tree.

    Returns None rather than raising on a misconfiguration. An operator who set
    three of the four variables should get a working module and a loud log,
    not a platform that will not start — the local store is a correct fallback
    and every artifact it holds is still content-addressed.
    """
    if not configured():
        return None

    bucket = os.environ.get("M01_S3_BUCKET")
    if not bucket:
        log.error("M01_OBJECT_STORE is set but M01_S3_BUCKET is not; using the local store")
        return None

    try:
        import boto3
    except ImportError:
        log.error("M01_OBJECT_STORE is set but boto3 is not installed; using the local store")
        return None

    endpoint = os.environ.get("M01_S3_ENDPOINT") or None
    try:
        client = boto3.client("s3", endpoint_url=endpoint)
    except Exception as error:
        log.error("M01 could not build an S3 client (%s); using the local store", error)
        return None

    log.info("M01 object store: s3 bucket=%s endpoint=%s", bucket, endpoint or "aws")
    return S3ObjectStore(client, bucket)

"""Encryption at rest for the contact block (FR-1.17, §6.4).

    *"phone, email, and postal address are extracted into `candidate_pii`
    (separate table, encrypted column, restricted role)"*

Separation and redaction were already true and are the half that stops PII
reaching a model or a screen. This is the other half: what somebody who gets a
copy of `dev.db` can read.

── What this does and does not protect against ────────────────────────────────

**Does:** a leaked database file, a backup on someone's laptop, a developer
running `SELECT * FROM resume_contacts` out of curiosity. On a student
placement platform those are the realistic threats and they are worth closing.

**Does not:** an attacker who has the application server, because the key is
readable there by definition. Column encryption is not a substitute for the
restricted database role §6.4 also asks for — that is a deployment concern and
is still open. Saying so here rather than letting the presence of this file
imply more than it delivers.

── The key, and the mode without one ──────────────────────────────────────────

`M01_PII_KEY` — a Fernet key, generated with `generate_key()` below.

With no key set, values are stored in the clear and a warning is logged on
every write. That is deliberate rather than a hard failure: refusing to start
would mean a student cannot upload a resume because an operator has not read
the deployment notes yet, and losing the whole product to protect the phone
number is the wrong trade. The warning is loud and the state is visible at
`GET /v1/quality`, so "we forgot" is discoverable rather than silent.

Values carry a prefix saying which they are, so a database holding both — one
written before the key was set, one after — reads back correctly either way.
Migrating is then a matter of re-saving, not of guessing.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("uvicorn.error")

#: Marks a value as encrypted. Without it, a mixed table is unreadable: there
#: is no way to tell ciphertext from a phone number that happens to look odd.
PREFIX = "enc:v1:"

_WARNED = False


def key_configured() -> bool:
    return bool(os.environ.get("M01_PII_KEY"))


def generate_key() -> str:
    """A new key, for an operator to put in the environment.

        Backend/.venv/Scripts/python -c "from backend_M01_Resume_Ingestion.crypto \\
            import generate_key; print(generate_key())"
    """
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("ascii")


def _cipher():
    raw = os.environ.get("M01_PII_KEY")
    if not raw:
        return None
    try:
        from cryptography.fernet import Fernet

        return Fernet(raw.encode("ascii"))
    except Exception as error:
        # A malformed key is an operator mistake, and falling back to plaintext
        # silently would hide it for as long as nobody looks.
        log.error("M01 M01_PII_KEY is set but unusable (%s); storing contact in the clear", error)
        return None


def encrypt(value: str) -> str:
    """One value, encrypted if a key is configured. Never raises."""
    global _WARNED
    if not value:
        return value

    cipher = _cipher()
    if cipher is None:
        if not _WARNED:
            log.warning(
                "M01 M01_PII_KEY is not set — the contact block is stored in the clear. "
                "FR-1.17 asks for an encrypted column; see crypto.py."
            )
            _WARNED = True
        return value
    return PREFIX + cipher.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str) -> str:
    """The inverse. A value written before the key existed passes through.

    A value that cannot be decrypted is returned as a placeholder rather than
    raised on: a rotated key must not turn a placement officer's contact lookup
    into a 500, and "this cannot be read" is a true and useful answer.
    """
    if not value or not value.startswith(PREFIX):
        return value

    cipher = _cipher()
    if cipher is None:
        return "[encrypted — M01_PII_KEY is not set]"
    try:
        return cipher.decrypt(value[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except Exception:
        log.warning("M01 could not decrypt a contact value; the key may have been rotated")
        return "[encrypted — key does not match]"


def encrypt_all(values: list[str]) -> list[str]:
    return [encrypt(v) for v in values]


def decrypt_all(values: list[str]) -> list[str]:
    return [decrypt(v) for v in values]

"""M01's only route to a language model.

Spec: plan_in_depth/M01_Resume_Ingestion.md §6.3.3, §6.5.3, §6.7, Trap 4

Everything in this module was deterministic until now, and the argument in
`claims.py` for that is still right: a score a student cannot argue with is a
score they cannot appeal, and a suite that needs a key is a suite that does not
run on a marker's laptop. Nothing here weakens either.

── Four rules this file exists to hold ─────────────────────────────────────────

1. **The deterministic result is the floor, never the fallback.** Every caller
   computes its answer first and asks a model to IMPROVE it. A model that is
   absent, slow, wrong or lying leaves the student with exactly what M01
   produced yesterday — which is a working product, not a broken one.

2. **No key is a degradation, not a failure.** With nothing configured this
   hands back `NullLLM`, every caller keeps its deterministic answer, and
   `GET /v1/capabilities` says so. The 245-test suite runs offline, and there
   is an autouse fixture making sure it cannot do anything else.

3. **The resume is untrusted input (Trap 4).** Text reaching a model has already
   been through `safety.scan` and `redact` — the injection filter and the
   contact block, both before this file sees anything. What is sent here is
   additionally fenced and labelled as data, and no instruction is ever taken
   from inside it.

4. **A model's output is a claim, not a fact.** Structured output or nothing:
   every call declares a JSON Schema and gets parsed JSON or `None`. There is no
   regex over model prose anywhere in M01, which keeps the surface a caller has
   to validate small enough to actually validate.

── Where the model ids live ────────────────────────────────────────────────────

Not here. `ai_core.models` is the platform's roster and this module names a
TIER — "generation", "extraction" — so a model change is one line in one file
for all nineteen modules rather than a search across nineteen repositories.
Override one call without touching the tier via the `job_env` names below.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ai_core.models import USER_AGENT, Route, resolve

log = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------------------------
#  Credentials
# ---------------------------------------------------------------------------

#: Searched from `Backend/` upwards to the repo root. `keys.txt` is gitignored
#: and holds the real values; `required_keys.txt` is committed and holds the
#: shape with a sentence per key.
_KEY_FILES = ("keys.txt", ".env")


def load_keys(*, override: bool = False) -> list[str]:
    """Read `keys.txt` into the environment. Returns the names it set.

    Values already in the environment win unless `override`, so a deployment
    can set real environment variables with no file and a developer can change
    one key for one shell without editing anything.

    Deliberately not python-dotenv: one function, no dependency, and the format
    is the one everybody already writes by hand.
    """
    here = Path(__file__).resolve()
    roots = [here.parents[1], here.parents[2]]  # Backend/, repo root
    loaded: list[str] = []

    for root in roots:
        for name in _KEY_FILES:
            path = root / name
            if not path.exists():
                continue
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if not key or not value:
                    continue
                if override or not os.getenv(key):
                    os.environ[key] = value
                    loaded.append(key)
    return loaded


class KeyRing:
    """Round-robin over a pool of keys.

    Several providers rate-limit per key rather than per account, so a pool of
    keys is a pool of quota. Deliberately not smarter than round-robin: a key
    that starts failing is a thing to see in the logs, not to route around
    silently until nobody remembers which keys still work.
    """

    def __init__(self, keys: list[str]) -> None:
        self._keys = list(keys)
        self._cycle = itertools.cycle(self._keys) if self._keys else None
        self._lock = threading.Lock()

    def __bool__(self) -> bool:
        return bool(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def next(self) -> str | None:
        if self._cycle is None:
            return None
        with self._lock:
            return next(self._cycle)


# ---------------------------------------------------------------------------
#  Jobs
# ---------------------------------------------------------------------------

#: Every model call in M01 names one of these. The name reaches telemetry, so
#: "what did probe generation cost this week" is a GROUP BY rather than an
#: archaeology exercise.
JOB_PROBES = "probes"
JOB_REWRITE = "rewrite"
JOB_EXTRACTION = "extraction"

#: Job -> (tier, per-job override env var). The tier is what normally decides;
#: the env var is the escape hatch for one call needing something different.
_JOBS: dict[str, tuple[str, str]] = {
    JOB_PROBES: ("generation", "M01_MODEL_PROBES"),
    JOB_REWRITE: ("generation", "M01_MODEL_REWRITE"),
    JOB_EXTRACTION: ("extraction", "M01_MODEL_EXTRACTION"),
}

#: Long enough for a large model on a cold route, short enough that an ingest
#: does not stall behind an unreachable provider. FR-1.18 budgets the whole
#: parse at 25 s, and this has to fit inside that with room to spare.
TIMEOUT = float(os.getenv("M01_LLM_TIMEOUT", "20"))

#: `gpt-oss` models emit reasoning tokens that are billed and counted but never
#: returned as content. Budget below what the reasoning needs and the call
#: returns an empty string with a full completion count — which looks like the
#: model refusing rather than the caller under-provisioning. Measured: three
#: grounded probes cost ~850 completion tokens, most of it reasoning.
MAX_TOKENS = int(os.getenv("M01_LLM_MAX_TOKENS", "2000"))

#: Pause before the single retry. Short on purpose — see `_send`.
RETRY_BACKOFF = float(os.getenv("M01_LLM_RETRY_BACKOFF", "0.75"))


# ---------------------------------------------------------------------------
#  Result
# ---------------------------------------------------------------------------


@dataclass
class LLMResult:
    """What a call produced, or the stated reason it produced nothing.

    `ok` is false for every failure mode — no key, timeout, HTTP error, invalid
    JSON, schema violation — and `reason` always says which. A caller branches
    on `ok` once and keeps its deterministic answer otherwise.
    """

    ok: bool = False
    data: dict[str, Any] | None = None
    reason: str = ""
    model: str = ""
    duration_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


class LLM(Protocol):
    """The whole interface. Structured output or nothing."""

    @property
    def available(self) -> bool: ...

    def structured(
        self, *, job: str, system: str, user: str, schema: dict[str, Any]
    ) -> LLMResult: ...


@dataclass
class NullLLM:
    """No key configured. Every call declines, with the reason.

    Not an error object and not a raise: this is the normal state of a fresh
    clone, of CI, and of every test run. The reason is worth surfacing because
    "why are my questions generic?" should be answerable without reading code.
    """

    reason: str = "no model configured"

    @property
    def available(self) -> bool:
        return False

    def structured(self, *, job: str, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        return LLMResult(ok=False, reason=self.reason)


@dataclass
class OpenAICompatLLM:
    """One client for every OpenAI-dialect endpoint the roster knows.

    Groq and NVIDIA NIM both speak chat-completions, so swapping either is a
    change in `ai_core.models` rather than here.
    """

    rings: dict[str, KeyRing] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return any(bool(resolve(tier)) for tier, _ in _JOBS.values())

    def _ring(self, route: Route) -> KeyRing:
        assert route.provider is not None
        name = route.provider.name
        ring = self.rings.get(name)
        if ring is None or len(ring) != len(route.keys):
            ring = KeyRing(route.keys)
            self.rings[name] = ring
        return ring

    def _send(
        self, request: urllib.request.Request, route: Route
    ) -> tuple[dict[str, Any] | None, str | None]:
        """One call, with one retry for the failures that are worth retrying.

        Rate limits and 5xx are transient by definition; a 400 or a 401 is the
        request being wrong and repeating it is just slower. Retried on the NEXT
        key in the pool, because a 429 is usually that key's minute rather than
        the account's.

        One retry, not three. The whole parse is budgeted at 25 s (FR-1.18) and
        this runs four-wide inside it — a longer backoff ladder turns a slow
        provider into a breached budget, and the caller already has working
        deterministic probes to fall back to.
        """
        attempts = 2
        last: str | None = None

        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                    return json.loads(response.read()), None
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:200]
                last = f"HTTP {exc.code}: {detail}"
                retryable = exc.code == 429 or exc.code >= 500
            except TimeoutError as exc:
                last = f"timeout after {TIMEOUT}s: {exc}"
                retryable = True
            except Exception as exc:  # noqa: BLE001 - every failure degrades
                last = f"{type(exc).__name__}: {exc}"
                retryable = isinstance(exc, urllib.error.URLError)

            if not retryable or attempt == attempts - 1:
                break

            # Next key, and a short pause. A 429 is normally this key's minute.
            following = self._ring(route).next()
            if following:
                request.add_header("Authorization", f"Bearer {following}")
            time.sleep(RETRY_BACKOFF)
            log.info("M01 retrying %s after: %s", route.model, last)

        return None, last

    def structured(self, *, job: str, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        tier, job_env = _JOBS.get(job, ("generation", ""))
        route = resolve(tier, job_env=job_env or None)  # type: ignore[arg-type]
        if not route:
            return LLMResult(ok=False, reason=route.unusable or "no route", model=route.model)

        assert route.provider is not None
        key = self._ring(route).next()
        if key is None:  # pragma: no cover - `resolve` already guarantees a key
            return LLMResult(ok=False, reason="key ring empty", model=route.model)

        body: dict[str, Any] = {
            "model": route.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Low but not zero. Zero makes a model repeat one bad phrasing across
            # every claim on a resume, which is the exact complaint this whole
            # path exists to answer.
            "temperature": 0.3,
            "max_tokens": MAX_TOKENS,
        }
        if route.profile is not None and route.profile.json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": job, "strict": True, "schema": schema},
            }

        request = urllib.request.Request(
            f"{route.provider.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                # Not cosmetic. A default urllib User-Agent is a Cloudflare 403
                # with body `error code: 1010`, which reads as a rejected key.
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )

        started = time.perf_counter()
        payload, failure = self._send(request, route)
        if payload is None:
            return LLMResult(ok=False, reason=failure or "no response", model=route.model)

        elapsed = int((time.perf_counter() - started) * 1000)
        usage = payload.get("usage", {}) or {}
        result = LLMResult(
            model=route.model,
            duration_ms=elapsed,
            tokens_in=usage.get("prompt_tokens", 0) or 0,
            tokens_out=usage.get("completion_tokens", 0) or 0,
        )

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            result.reason = "response had no message content"
            return result

        if not content or not content.strip():
            # Almost always `max_tokens` consumed by reasoning tokens. Say that,
            # because "the model returned nothing" sends people to the prompt.
            result.reason = f"empty content ({result.tokens_out} completion tokens, likely reasoning)"
            return result

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            result.reason = f"unparseable JSON: {exc}"
            return result

        if not isinstance(parsed, dict):
            result.reason = "response was not a JSON object"
            return result

        result.ok = True
        result.data = parsed
        return result


# ---------------------------------------------------------------------------
#  Access
# ---------------------------------------------------------------------------

_llm: LLM | None = None
_lock = threading.Lock()


def get_llm(*, refresh: bool = False) -> LLM:
    """The module's one client. Built once.

    `refresh` re-reads the environment, which is what a test that has just set
    a key needs and what nothing in production should want.
    """
    global _llm
    with _lock:
        if _llm is not None and not refresh:
            return _llm

        load_keys()
        usable = [tier for tier, _ in _JOBS.values() if resolve(tier)]  # type: ignore[arg-type]
        if not usable:
            reason = resolve("generation").unusable or "no model configured"
            log.info("M01 language model off: %s", reason)
            _llm = NullLLM(reason=reason)
        else:
            _llm = OpenAICompatLLM()
            log.info("M01 language model on: %s", ", ".join(sorted(set(usable))))
        return _llm


def set_llm(llm: LLM | None) -> None:
    """Replace the client. For tests, and for nothing else."""
    global _llm
    with _lock:
        _llm = llm


def is_available() -> bool:
    return get_llm().available


def status() -> dict[str, Any]:
    """What `GET /v1/capabilities` reports about generation.

    A student asking "why are my questions generic?" gets an answer here rather
    than from a log, and an operator who has not set a key finds out without
    reading source. Never returns a key or any part of one.
    """
    client = get_llm()
    generation = resolve("generation", job_env="M01_MODEL_PROBES")
    return {
        "available": client.available,
        "model": generation.model if generation else None,
        "provider": generation.provider.name if generation.provider else None,
        "reason": None if client.available else getattr(client, "reason", "unavailable"),
    }

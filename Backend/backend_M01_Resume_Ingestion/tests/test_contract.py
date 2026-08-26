"""The backend surface and the frontend client, checked against each other.

`api.ts` states the rule this file enforces: *"One hook per backend endpoint,
and no hook without one. A hook for an endpoint that does not answer lets a
screen be built against it, and the caller finds out in the browser rather than
in a review."*

It was a comment, and a comment cannot notice. When this test was written ten
of the thirty-one routes had no client at all — the contact block, the date
correction, claim deletion, the correction log, the event stream, sharing,
revocation, disclosure, the quality report — and four hooks that did exist were
mounted by no screen. Every one of those was invisible from either side alone:
the backend's tests passed, the frontend built, and the feature did not exist.

── Why this lives in the Python suite ─────────────────────────────────────────

Because this suite is the one that runs. Both halves are in this repository and
the check needs to read both; putting it here means a route added without a
client fails the same command that already gates a release, rather than a
second one somebody has to remember.

It reads the frontend as TEXT rather than parsing TypeScript. A regex over
template literals is crude and it is enough: it answers "could any request in
this file produce that path", which is the question, and it cannot be satisfied
by a hook that names an endpoint in a comment.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from backend_M01_Resume_Ingestion.app import app

_REPO = pathlib.Path(__file__).resolve().parents[3]
_FRONTEND = _REPO / "Frontend" / "frontend_M01_Resume_Ingestion" / "src"

#: Routes the server itself declares as an alias of another, in `router.py`,
#: with the reason stated there: a 307 through a POST loses the body in enough
#: HTTP clients to be worth two lines instead. Both run the same function, so
#: one client covers both — and a second hook would let two screens drift onto
#: two spellings of one operation. Adding an entry here is a decision; it is
#: not a place to park an endpoint nobody got round to wiring.
ALIASES: dict[tuple[str, str], str] = {
    ("POST", "/v1/resumes/ingest"): "POST /v1/resumes/from-text",
    ("GET", "/v1/resumes/{resume_id}/diff/{other_id}"): "GET /v1/resumes/{id}/diff?against=",
}


def _routes() -> set[tuple[str, str]]:
    """Every path this app serves.

    From the OpenAPI schema rather than `app.routes`: FastAPI wraps an included
    router in a node whose children are not on the top-level list, and walking
    that list reported two endpoints out of thirty-one — a check that passes by
    seeing almost nothing.
    """
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() not in {"HEAD", "OPTIONS"}
    }


def _source(name: str) -> str:
    return (_FRONTEND / name).read_text(encoding="utf-8")


def _all_components() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in _FRONTEND.rglob("*.ts*")
        if path.name != "api.ts"
    )


def _client_exists_for(path: str, api: str) -> bool:
    """Could any template literal in `api.ts` produce this path?"""
    pattern = re.escape(path)
    # `{resume_id}` in the route -> `${anything}` in the template literal.
    pattern = re.sub(r"\\\{[a-z_]+\\\}", r"\\$\\{[^`]*?\\}", pattern)
    return re.search(pattern, api) is not None


@pytest.mark.gate
def test_every_endpoint_has_a_client():
    """A route with no caller is a feature that does not exist.

    It is worse than an unbuilt one: the tests pass, the docs list it, and the
    only person who finds out is the student who needed it.
    """
    api = _source("api.ts")

    orphans = sorted(
        f"{method} {path}"
        for method, path in _routes()
        if (method, path) not in ALIASES and not _client_exists_for(path, api)
    )

    assert not orphans, "backend routes with no client in api.ts:\n  " + "\n  ".join(orphans)


@pytest.mark.gate
def test_every_hook_is_mounted_by_a_screen():
    """The other direction, and the one that is easier to let slide.

    A hook nothing renders is an endpoint the student cannot reach — the same
    outcome as not writing it, reached by a route that looks finished in every
    file you would think to open. `useRedFlags` and `useSkills` sat unused
    while two screens re-derived the same values from the raw resume, so the
    server's ordering and its counts were computed twice and agreed by luck.
    """
    api = _source("api.ts")
    components = _all_components()

    hooks = re.findall(r"export function (use[A-Za-z]+|subscribeToProgress)", api)
    assert hooks, "no hooks found — the regex or the file layout changed"

    dead = sorted(hook for hook in hooks if not re.search(rf"\b{hook}\b", components))

    assert not dead, "hooks that no screen mounts:\n  " + "\n  ".join(dead)


def test_an_alias_is_only_ever_a_second_spelling():
    """The exemption list cannot become a parking space.

    Every entry has to point at a route that IS served and IS wired, or the
    exemption is hiding an endpoint rather than explaining one.
    """
    api = _source("api.ts")
    served = _routes()

    for alias, target in ALIASES.items():
        assert alias in served, f"{alias} is exempted but not served — stale entry"
        method, _, path = target.partition(" ")
        base = path.split("?")[0].replace("{id}", "{resume_id}")
        assert (method, base) in served, f"{alias} points at {target}, which is not served"
        assert _client_exists_for(base, api), f"{alias} points at {target}, which has no client"


@pytest.mark.gate
def test_every_raw_fetch_in_the_client_sends_identity():
    """A raw `fetch` bypasses `@ai/core`, and therefore bypasses the headers.

    `setIdentityHeaders` puts identity on core's wrapper. `api.ts` has two
    helpers that deliberately do NOT use that wrapper — PATCH, which core does
    not carry, and multipart upload, where setting `Content-Type` yourself is
    actively wrong. Both were invisible to the change that added identity, so
    the backend started answering 403 "Not signed in." to every upload and
    every correction while the paste path worked perfectly.

    That shape will recur: the next verb core does not carry gets written the
    same way. So the rule is checked rather than remembered — a `fetch(` in
    this file must mention `identityHeaders`.
    """
    source = _source("api.ts")

    # Body of each `fetch(...)` call, roughly: up to the line that closes it.
    calls = re.findall(r"fetch\((.*?)\n  \}\)", source, re.DOTALL)
    assert calls, "no raw fetch calls found — the regex or the file layout changed"

    naked = [call for call in calls if "identityHeaders" not in call]
    assert not naked, (
        "raw fetch without identity headers — the backend will answer 403:\n  "
        + "\n  ".join(call.strip()[:90] for call in naked)
    )

"""Test fixtures for M01.

The important one is `m04`. Every degradation test here has to be true
regardless of what is running on the developer's machine: if these tests
inferred "M04 is down" from a closed port, they would flip to green-but-
meaningless the moment somebody had Memory running in another tab. So the
registry's probe cache is seeded directly and M04's HTTP surface is served
from the fixture.
"""

import json
import time
import urllib.error
import urllib.request

import pytest
from backend_M01_Resume_Ingestion import router as router_module
from backend_M01_Resume_Ingestion.app import app
from backend_M01_Resume_Ingestion.router import get_db
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class _Response:
    """The slice of an http.client.HTTPResponse that the router actually uses."""

    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeM04:
    """M04's HTTP surface, or its absence, under the test's control."""

    def __init__(self, registry):
        self.registry = registry
        self.concepts: list[dict] = []
        self.resolved: dict[str, str | None] = {}
        self.down()

    def down(self):
        # (checked_at, available, detail) — seeded so no socket is opened.
        self.registry._cache["M04"] = (time.monotonic(), False, "unreachable (test)")

    def up(self, *, concepts=None, resolved=None):
        self.registry._cache["M04"] = (time.monotonic(), True, "healthy (200)")
        if concepts is not None:
            self.concepts = concepts
        if resolved is not None:
            self.resolved = resolved

    def urlopen(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/health"):
            # ai_core probes this, and `statuses(force=True)` re-probes rather
            # than trusting the seeded cache, so the fixture has to answer it.
            if not self.registry._cache["M04"][1]:
                raise urllib.error.URLError("connection refused (test)")
            return _Response({"status": "ok", "module": "M04"})
        if url.endswith("/v1/concepts"):
            body = {"concepts": self.concepts}
        elif url.endswith("/v1/concepts/resolve"):
            labels = json.loads(req.data.decode("utf-8"))["labels"]
            body = {"resolved": {label: self.resolved.get(label) for label in labels}}
        else:  # pragma: no cover - a call we did not expect is a test bug
            raise AssertionError(f"unexpected M04 call: {url}")
        return _Response(body)


#: The ids M01's offline table would guess, so a test can assert that a label
#: resolved by a live M04 is recorded as M04's and not as the table's.
_M04_IDS = {
    "Dynamic Programming": "concept:dynamic_programming",
    "Recursion": "concept:recursion",
    "Hashing": "concept:hashing",
    "SQL": "concept:sql_basics",
    "Transactions": "concept:transactions_acid",
}


@pytest.fixture(name="m04")
def m04_fixture(monkeypatch):
    router_module.dependency_registry.cache_clear()
    registry = router_module.dependency_registry()
    fake = _FakeM04(registry)
    monkeypatch.setattr(urllib.request, "urlopen", fake.urlopen)
    yield fake
    router_module.dependency_registry.cache_clear()


@pytest.fixture(name="m04_up")
def m04_up_fixture(m04):
    """Bring M04 up with the standard ontology."""

    def _bring_up(*, extra_concepts=None, extra_resolutions=None):
        concepts = list(router_module.FALLBACK_CONCEPTS) + list(extra_concepts or [])
        resolved = dict(_M04_IDS)
        resolved.update(extra_resolutions or {})
        m04.up(concepts=concepts, resolved=resolved)
        return m04

    return _bring_up


@pytest.fixture(name="client")
def client_fixture(session, m04):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

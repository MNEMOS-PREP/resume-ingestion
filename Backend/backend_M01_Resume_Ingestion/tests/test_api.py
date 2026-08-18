import uuid


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "module": "M01"}


def test_ingest_resume(client):
    candidate_id = str(uuid.uuid4())
    res = client.post(
        "/v1/resumes/ingest",
        json={
            "candidate_id": candidate_id,
            "raw_text": "Built a project using Dynamic Programming and SQL.",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["candidate_id"] == candidate_id
    assert "Dynamic Programming" in data["parsed_skills"]

    resume_id = data["id"]
    assert client.get(f"/v1/resumes/{resume_id}").json()["id"] == resume_id
    listed = client.get(f"/v1/resumes/candidate/{candidate_id}").json()
    assert [r["id"] for r in listed] == [resume_id]


def test_offline_ids_are_labelled_as_guesses(client):
    """Rule 2. With M04 down we still map skills — and we say who mapped them.

    A concept_id is a licence for M05 to build questions on and for M13 to
    score against. One this module guessed from a five-entry table must not
    arrive downstream looking like one the ontology confirmed.
    """
    res = client.post(
        "/v1/resumes/ingest",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": "Strong SQL and recursion."},
    )
    data = res.json()
    assert data["scanned_against"] == "offline_lexicon"
    assert data["concept_source"] == {
        "Recursion": "offline_fallback",
        "SQL": "offline_fallback",
    }


def test_live_m04_ids_are_labelled_as_resolved(client, m04_up):
    m04_up()
    res = client.post(
        "/v1/resumes/ingest",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": "Strong SQL and recursion."},
    )
    data = res.json()
    assert data["scanned_against"] == "m04"
    assert set(data["concept_source"].values()) == {"m04"}
    assert data["resolved_concepts"]["SQL"] == "concept:sql_basics"


def test_unmappable_skill_is_kept_not_dropped(client, m04_up):
    """A skill the ontology has no id for is still a claim on the resume.

    Dropping it silently is how the read-back screen ends up contradicting the
    student's own document — they see a skill they wrote go missing with no
    explanation, which reads as "the parser is broken".
    """
    m04_up(
        extra_concepts=[{"name": "Kubernetes", "aliases": ["k8s"]}],
        extra_resolutions={"Kubernetes": None},
    )
    res = client.post(
        "/v1/resumes/ingest",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": "Deployed k8s, wrote SQL."},
    )
    data = res.json()
    assert "Kubernetes" in data["parsed_skills"]
    assert data["unresolved_skills"] == ["Kubernetes"]
    assert "Kubernetes" not in data["resolved_concepts"]
    assert "Kubernetes" not in data["concept_source"]


def test_deps_names_the_missing_module(client):
    """The degradation is reportable, not merely absent."""
    deps = client.get("/v1/deps").json()
    assert [d["module_id"] for d in deps] == ["M04"]
    assert deps[0]["available"] is False
    assert deps[0]["base_url"] == "http://127.0.0.1:8104"
    assert deps[0]["required"] is False
    assert "M04" in deps[0]["on_missing"]


def test_deps_reports_a_live_upstream(client, m04_up):
    m04_up()
    deps = client.get("/v1/deps").json()
    assert deps[0]["available"] is True


def test_unknown_resume_is_404(client):
    assert client.get(f"/v1/resumes/{uuid.uuid4()}").status_code == 404

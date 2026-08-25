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
    """The degradation is reportable, not merely absent.

    Asserted as a PROPERTY of every declared upstream rather than as a literal
    list. The list was `== ["M04"]`, so adding M06 for the defend drill failed
    a test about M04's degradation message — which tells the next person that
    declaring a dependency is a thing that breaks tests, rather than telling
    them what a dependency has to carry.
    """
    deps = {d["module_id"]: d for d in client.get("/v1/deps").json()}

    assert "M04" in deps, "the ontology upstream must always be declared"

    for module_id, dep in deps.items():
        # None of them is running in a test, and that is the point: a student
        # gets a sentence naming the module, not a silently thinner page.
        assert dep["available"] is False
        assert dep["required"] is False, f"{module_id} must not be able to take M01 down"
        assert dep["base_url"], f"{module_id} has no base_url, so it is off even when it is up"
        assert module_id in dep["on_missing"], f"{module_id}'s message must name the module"

    assert deps["M04"]["base_url"] == "http://127.0.0.1:8104"


def test_deps_reports_a_live_upstream(client, m04_up):
    m04_up()
    deps = client.get("/v1/deps").json()
    assert deps[0]["available"] is True


def test_unknown_resume_is_404(client):
    assert client.get(f"/v1/resumes/{uuid.uuid4()}").status_code == 404


def test_status_reports_the_platform_registry(client):
    """Not this module's opinion of itself - the shared registry's."""
    res = client.get("/status")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "M01"
    assert body["implemented"] is True
    assert body["reserved_port"] == 8101


# ---------------------------------------------------------------------------
#  Extraction: what the document says, before the ontology has an opinion
#
#  `test_unmappable_skill_is_kept_not_dropped` above asserts the right thing
#  and used to pass for the wrong reason. It injects a concept INTO M04 and
#  then makes M04 fail to resolve it — an internal inconsistency, and the only
#  path by which the old extraction could ever populate `unresolved_skills`,
#  because labels reached the resolver only by having come from the resolver.
#  A student's own skill could not get there. These cover the real path.
# ---------------------------------------------------------------------------


def _ingest(client, text):
    return client.post(
        "/v1/resumes/ingest",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": text},
    ).json()


def test_technologies_outside_the_ontology_are_kept_not_invisible(client, m04_up):
    """The regression that mattered most.

    The ontology holds interview concepts, not technologies, so almost nothing
    on a real SKILLS line resolves to anything. That is fine and expected — but
    it must show up as "we could not map these", never as silence.
    """
    m04_up()
    data = _ingest(client, "SKILLS\nPython, Java, Docker, Kubernetes, TensorFlow")

    assert data["parsed_skills"] == ["Python", "Java", "Docker", "Kubernetes", "TensorFlow"]
    assert data["unresolved_skills"] == ["Python", "Java", "Docker", "Kubernetes", "TensorFlow"]
    assert data["resolved_concepts"] == {}


def test_a_real_skills_line_is_not_an_empty_resume(client, m04_up):
    """These two responses used to be identical. That was the whole bug."""
    m04_up()
    written = _ingest(client, "SKILLS\nPython, Docker, Kubernetes, AWS, React")
    blank = _ingest(client, "")

    assert blank["parsed_skills"] == []
    assert written["parsed_skills"] != blank["parsed_skills"]


def test_everyday_words_do_not_become_claims(client, m04_up):
    """ "a solid communicator" is not a claim about SOLID principles.

    Twenty-five of the ontology's aliases are ordinary English words. Matched
    in running prose they invent requirements out of adjectives, and downstream
    an invented requirement becomes an interview question.
    """
    m04_up(
        extra_concepts=[
            {"name": "SOLID Principles", "aliases": ["solid"]},
            {"name": "Stacks", "aliases": ["stack"]},
            {"name": "Classes and Objects", "aliases": ["class"]},
        ]
    )
    data = _ingest(
        client,
        "A solid communicator. Full stack developer, class of 2026.",
    )

    assert data["parsed_skills"] == []


def test_a_listed_ambiguous_word_is_still_a_claim(client, m04_up):
    """The same word, enumerated rather than used as an adjective, counts.

    This is the other half of the rule: "stack" in prose is an adjective,
    "stack" as an item under SKILLS is a claim. Blocking it everywhere would
    trade one silent failure for another.
    """
    m04_up(extra_concepts=[{"name": "Stacks", "aliases": ["stack"]}])
    data = _ingest(client, "SKILLS\nstack, queues")

    assert "stack" in data["parsed_skills"]


def test_multi_word_concepts_still_match_in_running_prose(client, m04_up):
    """A project bullet is evidence too, and phrases are unambiguous."""
    m04_up()
    data = _ingest(client, "Built a route planner using dynamic programming on a 12k-node graph.")

    assert "Dynamic Programming" in data["parsed_skills"]
    assert data["resolved_concepts"]["Dynamic Programming"] == "concept:dynamic_programming"


# ---------------------------------------------------------------------------
#  The defend drill (§2.3 Screen 5, AC-1.8)
# ---------------------------------------------------------------------------

DRILLABLE = """PROJECTS
- Built a route planner in Python using dynamic programming.
"""


def test_the_drill_answers_even_though_m06_does_not_exist(client, m04_up):
    """AC-1.8 is the module's stated KPI and it had no numerator at all.

    §13: "Parsing accuracy is a means; a student running a drill because they
    saw a risky claim is the outcome." The SESSION needs M06. The affordance
    does not, and a button that vanishes when an upstream is down teaches a
    student the product is thin rather than unfinished.
    """
    m04_up()
    data = _ingest(client, DRILLABLE)
    claim_id = data["claims"][0]["id"]

    res = client.post(f"/v1/resumes/{data['id']}/claims/{claim_id}/drill")

    assert res.status_code == 200, "a missing upstream must degrade, never 502"
    body = res.json()
    assert body["available"] is False
    assert body["needs_module"] == "M06"
    assert "M06" in body["explanation"]
    # The half that needs nobody: the questions are already on the card.
    assert body["questions"], "a student who cannot start a drill can still answer out loud"
    assert body["questions"] == [p["question"] for p in data["claims"][0]["probes"]]


def test_a_drill_on_a_claim_that_is_not_there_is_a_404(client, m04_up):
    """The one case that IS an error. A missing upstream degrades; a claim id
    that does not exist is the caller being wrong."""
    m04_up()
    data = _ingest(client, DRILLABLE)

    res = client.post(f"/v1/resumes/{data['id']}/claims/{uuid.uuid4()}/drill")

    assert res.status_code == 404

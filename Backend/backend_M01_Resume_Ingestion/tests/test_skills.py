"""Skill normalisation: the ambiguity suite and the context split (§6.4, FR-1.7).

§12 asks for "the ambiguity suite — `R`, `C`, `Go`, `Rust`, `Swift`, `Spring`,
`Django`, `Express`, `Next`, and 50 real surface forms". The interesting half
is not that `Django` resolves; it is that `R` does not resolve to `React`, and
that a skill nobody can map is still reported.
"""

import uuid

from backend_M01_Resume_Ingestion import skills as skills_mod

RESUME = """PRIYA SHARMA

EXPERIENCE
- Software Engineer Intern at Zoho. Built ingestion services in Python and shipped them.

PROJECTS
- Built a route planner in Python using dynamic programming on a 12k-node graph.

SKILLS
Python, Java, R, C, Go, Docker, Kubernetes, React, Spring, Express, Next
"""


def _ingest(client, text=RESUME, candidate=None):
    res = client.post(
        "/v1/resumes/from-text",
        json={"candidate_id": str(candidate or uuid.uuid4()), "raw_text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
#  §6.4 step 2 — the short-token guard
# ---------------------------------------------------------------------------


def test_a_one_or_two_character_token_may_only_match_exactly():
    """The rule that gets dropped by whoever reimplements this.

    Without it, "R" fuzzy-matches "React" and a student who listed a statistics
    language is asked about a frontend framework.
    """
    for short in ("R", "C", "Go", "C#", "JS"):
        assert not skills_mod.guard_short_token(short), f"{short} should be exact-match only"
    for long in ("Rust", "Swift", "React", "Django", "Python"):
        assert skills_mod.guard_short_token(long)


def test_short_ambiguous_tokens_are_kept_but_never_guessed_at(client, m04_up):
    """They are on the resume, so they are reported — as unmapped.

    Both halves matter. Dropping them contradicts the student's own document;
    guessing at them hands M05 a concept the student never claimed.
    """
    m04_up()
    data = _ingest(client)

    for short in ("R", "C", "Go"):
        assert short in data["parsed_skills"], f"{short} was dropped"
        assert short in data["unresolved_skills"], f"{short} was guessed at"
        assert short not in data["resolved_concepts"]


def test_a_framework_name_never_absorbs_a_shorter_one(client, m04_up):
    """ "Next" must not become "Next.js" plus "React", and "Express" must not
    become "Expression". Every one of these stays exactly what was written."""
    m04_up()
    data = _ingest(client)

    for label in ("React", "Spring", "Express", "Next"):
        assert label in data["parsed_skills"]
        assert label not in data["resolved_concepts"], f"{label} was mapped without an ontology"


# ---------------------------------------------------------------------------
#  §6.4 — context weighting
# ---------------------------------------------------------------------------


def test_the_same_skill_in_two_places_is_two_mentions(client, m04_up):
    """§6.4, and the entire point of `context`.

    *"a skill appearing only in a skills list is a claim of familiarity; the
    same skill inside a project description is a claim of use. M5 asks much
    harder questions about the latter."*
    """
    m04_up()
    data = _ingest(client)

    python = [m for m in data["skill_mentions"] if m["surface"].casefold() == "python"]
    contexts = {m["context"] for m in python}

    assert "skills_list" in contexts, "the SKILLS line entry"
    assert contexts & {"project_tech", "experience_body"}, "the one used in a bullet"


def test_a_claim_of_use_outranks_a_claim_of_familiarity(client, m04_up):
    m04_up()
    data = _ingest(client)

    mentions = [skills_mod.SkillMention(**m) for m in data["skill_mentions"]]
    by_context = {m.context: m for m in mentions}

    assert (
        skills_mod.CONTEXT_STRENGTH["experience_body"]
        > skills_mod.CONTEXT_STRENGTH["project_tech"]
        > skills_mod.CONTEXT_STRENGTH["education"]
        > skills_mod.CONTEXT_STRENGTH["skills_list"]
    )
    assert by_context, "no mentions were produced at all"


def test_a_skill_listed_fourteen_times_is_one_mention_with_a_count(client, m04_up):
    """EC-1.12 — "Dedup to one SkillMention per (concept, context) with an
    occurrence count"."""
    m04_up()
    data = _ingest(client, "SKILLS\n" + ", ".join(["Docker"] * 14) + "\n")

    docker = [m for m in data["skill_mentions"] if m["surface"].casefold() == "docker"]
    assert len(docker) == 1
    assert docker[0]["occurrences"] == 14


# ---------------------------------------------------------------------------
#  Provenance of an id
# ---------------------------------------------------------------------------


def test_an_offline_guess_is_not_labelled_as_a_model_or_as_the_ontology(client):
    """The module's whole reason for existing, at the mention level.

    An id from M01's five-entry fallback table is not `alias_exact` — nothing
    confirmed the concept exists — and it is emphatically not `llm`, because no
    model ran. Labelling a hardcoded lookup as a model output is precisely the
    confusion that puts a fabricated concept into a real interview.
    """
    data = _ingest(client, "SKILLS\nSQL, recursion\n")  # M04 down by default

    assert data["scanned_against"] == "offline_lexicon"
    mapped = [m for m in data["skill_mentions"] if m["concept_id"]]
    assert mapped
    for mention in mapped:
        assert mention["mapping_method"] == "offline_alias"
        assert mention["mapping_confidence"] < 1.0


def test_an_ontology_resolved_id_says_so(client, m04_up):
    m04_up()
    data = _ingest(client, "SKILLS\nSQL, recursion\n")

    mapped = [m for m in data["skill_mentions"] if m["concept_id"]]
    assert mapped
    for mention in mapped:
        assert mention["mapping_method"] == "alias_exact"
        assert mention["mapping_confidence"] == 1.0


def test_an_unmapped_mention_says_no_method_ran(client, m04_up):
    m04_up()
    data = _ingest(client, "SKILLS\nKubernetes, Terraform\n")

    for mention in data["skill_mentions"]:
        assert mention["concept_id"] is None
        assert mention["mapping_method"] == "unmapped"
        assert mention["mapping_confidence"] == 0.0


# ---------------------------------------------------------------------------
#  §6.4 — the unmapped queue is a feature
# ---------------------------------------------------------------------------


def test_the_unmapped_queue_is_ordered_by_how_often_students_write_it(client, m04_up):
    """*"It is how the ontology learns what students actually write."*

    Ordered by frequency, because that is the order in which adding a concept
    is worth somebody fifteen minutes.
    """
    m04_up()
    data = _ingest(client, "SKILLS\nDocker, Docker, Docker, Terraform, Terraform, Nomad\n")
    queue = client.get(f"/v1/resumes/{data['id']}/skills").json()["unmapped_queue"]

    surfaces = [entry["surface"] for entry in queue]
    counts = [entry["occurrences"] for entry in queue]

    assert counts == sorted(counts, reverse=True)
    assert surfaces[0].casefold() == "docker"


def test_every_mention_carries_a_span_that_resolves(client, m04_up):
    """A mention nobody can point at in the document is not evidence of
    anything — same rule as a claim, one level down."""
    m04_up()
    data = _ingest(client)
    source = data["redacted_text"]

    assert data["skill_mentions"]
    for mention in data["skill_mentions"]:
        span = mention["span"]
        assert source[span["start"] : span["end"]] == span["text"]


def test_a_student_added_skill_never_invents_a_concept_id(client, m04_up):
    """M01 does not get to mint an id.

    A student typing "Kubernetes" is a claim about their resume, not a
    statement that the ontology has a concept for it.
    """
    m04_up()
    data = _ingest(client)

    after = client.post(
        f"/v1/resumes/{data['id']}/skills",
        json={"label": "Terraform", "present": True},
    ).json()

    assert "Terraform" in after["parsed_skills"]
    assert "Terraform" in after["unresolved_skills"]
    assert "Terraform" not in after["resolved_concepts"]


# ---------------------------------------------------------------------------
#  A word the page layout broke in half
# ---------------------------------------------------------------------------

WRAPPED = """PRIYA SHARMA

PROJECTS
- Built a sentiment classifier on review data.

SKILLS
Python, NLP, Multi-
modal Learning, PyTorch
"""


def test_a_skill_wrapped_at_its_hyphen_is_one_skill_not_two(client, m04_up):
    """A PDF wrapping "Multi-modal Learning" must not report three skills.

    The layout breaks the line at a hyphen the author already typed. Split on
    the break it becomes "Multi-" and "modal Learning", and both are then read
    back to the student as things they claimed — the read-back contradicting
    their own document, which is the failure this module cares most about.
    """
    m04_up()
    data = _ingest(client, WRAPPED)

    assert "Multi-modal Learning" in data["parsed_skills"]
    assert "Multi-" not in data["parsed_skills"]
    assert "modal Learning" not in data["parsed_skills"]


def test_a_rejoined_skill_still_points_at_the_words_it_came_from(client, m04_up):
    """The repair must not cost the skill its span.

    `extract.py` rejoins the halves, so the label is "Multi-modal Learning"
    while the document still reads "Multi-\nmodal Learning". A literal search
    finds nothing, and the skill would land in the read-back with no span and
    no context — the one promise this module makes about every fact, quietly
    untrue for exactly the skills that needed repairing.
    """
    m04_up()
    data = _ingest(client, WRAPPED)
    source = data["redacted_text"]

    mention = next(
        (m for m in data["skill_mentions"] if m["surface"] == "Multi-modal Learning"),
        None,
    )
    assert mention is not None, "the rejoined skill was never located in the document"

    span = mention["span"]
    # The span is a verbatim slice and keeps the break; the surface closes it.
    assert source[span["start"] : span["end"]] == span["text"]
    assert "\n" in span["text"]
    assert "\n" not in mention["surface"]


def test_a_list_item_that_ends_in_a_hyphen_is_not_glued_to_the_next(client, m04_up):
    """The other side of the line.

    Only a lower-case continuation is a broken word. A capital after the break
    is the next list item, and joining those would invent a skill rather than
    repair one.
    """
    m04_up()
    data = _ingest(
        client,
        "PRIYA SHARMA\n\nSKILLS\nC++, Java -\nPython, Docker\n",
    )

    assert "Python" in data["parsed_skills"]
    assert not any("Java -Python" in skill for skill in data["parsed_skills"])

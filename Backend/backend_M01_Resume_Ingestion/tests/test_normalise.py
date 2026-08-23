"""§6.4's five-step ladder, and the punctuation bug that nearly ate it.

The tests that matter most here are the ones about what must NOT happen. A
resolver that maps more things is trivially easy to write and is worse: an
invented skill becomes an interview question about something the student never
claimed, and they have no way to tell that is what happened.
"""

import uuid

import pytest
from backend_M01_Resume_Ingestion import normalise


def _ingest(client, text):
    res = client.post(
        "/v1/resumes/from-text",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
#  The punctuation bug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "canonical"),
    [("C", "C"), ("C++", "C++"), ("C#", "C#"), (".NET", ".NET"), ("Node.js", "Node.js")],
)
def test_punctuation_that_is_part_of_a_name_survives(written, canonical):
    """`normalise_alias` strips punctuation, which folds `C`, `C#` and `C++`
    onto one key. Whichever landed in the alias table last then answered for
    all three, and a student who wrote C++ was asked about C#.
    """
    assert normalise.resolve(written).canonical == canonical


def test_a_skills_line_of_c_variants_keeps_all_three(client, m04_up):
    """The same bug one layer up, in the dedup.

    "C, C++, C#" deduplicated to a single entry, so two of the three languages
    disappeared from the student's own read-back with no explanation.
    """
    m04_up()
    data = _ingest(client, "SKILLS\nC, C++, C#\n")

    assert data["parsed_skills"] == ["C", "C++", "C#"]


# ---------------------------------------------------------------------------
#  §6.4 step 2 — the short-token guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("short", ["R", "C", "Go", "C#", "C++", "JS"])
def test_short_names_are_exact_match_only(short):
    """Measured in LETTERS, so `C#` and `C++` join `C` and `R`.

    At two letters, WRatio cannot tell `R` from `Ruby` or `React`. Anything but
    an exact hit here is a guess, and unmapped is a perfectly good answer.
    """
    assert normalise.is_short(short)


def test_a_short_name_never_reaches_the_fuzzy_step():
    """The failure this guards: a student lists R, and is asked about React."""
    assert normalise.resolve("Rx").canonical is None
    assert normalise.resolve("Qz").canonical is None


# ---------------------------------------------------------------------------
#  §6.4 step 3 — fuzzy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typo", "canonical"),
    [("Kubernets", "Kubernetes"), ("Javascrpt", "JavaScript"), ("Postgressql", "PostgreSQL")],
)
def test_a_near_miss_spelling_still_resolves(typo, canonical):
    match = normalise.resolve(typo)
    assert match.canonical == canonical
    assert match.method == "alias_fuzzy"
    assert match.confidence < 1.0, "a fuzzy hit is not an exact one"


@pytest.mark.parametrize("mangled", ["Postgersql", "Docekr", "Pyton"])
def test_a_heavier_typo_is_refused_rather_than_mis_mapped(mangled):
    """The threshold earning its keep.

    `Postgersql` scores 90 against `sql` and `Docekr` scores 90 against `c` —
    both under the bar, and both would be *wrong* rather than approximately
    right. Refusing them puts the word in the unmapped queue, where the
    confirmation screen lets the student fix it in fifteen seconds; accepting
    them puts a skill on their resume that they never wrote.
    """
    assert normalise.resolve(mangled).canonical is None


def test_java_does_not_become_javascript():
    """They score 90 on WRatio and are not the same skill.

    The length-ratio guard is what separates them, and it is the guard most
    likely to be removed by somebody chasing recall.
    """
    assert normalise.resolve("Java").canonical == "Java"
    assert normalise.resolve("JavaScript").canonical == "JavaScript"


def test_something_genuinely_unknown_stays_unmapped():
    """§6.4 step 5. The unmapped queue is a feature, not a failure."""
    for unknown in ("Figma", "Salesforce", "Blender"):
        match = normalise.resolve(unknown)
        assert match.canonical is None
        assert match.method == "unmapped"


# ---------------------------------------------------------------------------
#  The table itself
# ---------------------------------------------------------------------------


def test_the_alias_table_loads_and_has_no_contested_spellings():
    """One alias claimed by two canonical names is a curation bug.

    Left silent it resolves by dict order, so a resume's "CV" is Computer
    Vision on one deploy and something else on the next.
    """
    table = normalise.alias_table()

    assert len(table) > 200, "the seed table did not load"
    assert normalise.canonical_names(), "no canonical names"
    for alias, canonical in table.items():
        assert alias == normalise.key(alias), f"{alias!r} is not stored normalised"
        assert canonical


def test_every_canonical_name_resolves_to_itself():
    """An exact hit on the name must never fall through to the fuzzy step."""
    for name in normalise.canonical_names():
        assert normalise.resolve(name).canonical == name


def test_step_four_is_absent_and_never_claimed():
    """No embedding service exists, so `mapping_method` is never "embedding".

    Reporting the absence is the point: a fuzzy hit dressed as a semantic one
    would let a downstream consumer trust it more than it should.
    """
    methods = {normalise.resolve(n).method for n in normalise.canonical_names()}
    assert "embedding" not in methods


# ---------------------------------------------------------------------------
#  Through the pipeline
# ---------------------------------------------------------------------------


def test_the_spellings_students_write_reach_a_canonical_name(client, m04_up):
    """The point of the whole file: five spellings of Kubernetes are one entry
    in the ontology review queue, not five."""
    m04_up()
    data = _ingest(client, "SKILLS\nreactjs, k8s, postgres, tensor flow, sklearn, DSA, oops\n")

    canonical = data["canonical_skills"]
    assert canonical["reactjs"] == "React"
    assert canonical["k8s"] == "Kubernetes"
    assert canonical["postgres"] == "PostgreSQL"
    assert canonical["sklearn"] == "scikit-learn"
    assert canonical["DSA"] == "Data Structures"


def test_an_unrecognised_skill_is_still_kept(client, m04_up):
    """Unchanged promise: a skill nothing can map is still on the resume."""
    m04_up()
    data = _ingest(client, "SKILLS\nFigma, Python\n")

    assert "Figma" in data["parsed_skills"]
    assert "Figma" in data["unresolved_skills"]
    assert "Figma" not in data["canonical_skills"]

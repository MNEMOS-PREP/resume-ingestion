"""The golden set, run against the real pipeline (§12, AC-1.3/1.4/1.5).

`golden.py` carries the argument for what these numbers mean; the short version
is that the corpus is synthetic, so this is a **regression floor** rather than
the acceptance measurement. The gate marker is on it anyway: a change that makes
segmentation or skill extraction worse should fail the build today, and the day
real resumes replace the corpus this file does not change at all.

Skills go through the API rather than through `extract_surface_forms` directly,
because the thing worth protecting is what a student ends up seeing — which
includes the resolution pass, the conjunction splitting and `drop_redundant`.
"""

import uuid

import pytest
from backend_M01_Resume_Ingestion import golden


@pytest.fixture(name="corpus", scope="module")
def corpus_fixture():
    loaded = golden.load()
    assert loaded, "the golden corpus is empty — check research/data/golden/resumes/"
    return loaded


def _ingest(client, text):
    response = client.post(
        "/v1/resumes/from-text",
        json={"candidate_id": str(uuid.uuid4()), "raw_text": text},
    )
    assert response.status_code == 201, response.text
    return response.json()


#: The corpus is scored in one pass and three tests read different numbers off
#: it. `client` is function-scoped — it owns a fresh in-memory database per test
#: — so a module-scoped fixture cannot ask for it. Caching the result here keeps
#: "score once" without widening the database's lifetime, which is the thing
#: that scope actually protects.
_CACHE: dict[str, golden.Score] = {}


@pytest.fixture(name="scored")
def scored_fixture(corpus, client, m04_up):
    if "score" not in _CACHE:
        m04_up()
        score = golden.Score()
        for resume in corpus:
            golden.score_sections(resume, score)
            data = _ingest(client, resume.text)
            golden.score_skills(resume, data["parsed_skills"], score)
        _CACHE["score"] = score
    return _CACHE["score"]


@pytest.mark.gate
def test_section_segmentation_does_not_regress(scored):
    """AC-1.3 as a floor. §14 day 4 wants F1 ≥ 0.80 from the heuristic tier
    alone; §13 wants 0.90 for the module."""
    assert scored.section_f1 >= golden.TARGET_SECTION_F1, "\n" + scored.report()


@pytest.mark.gate
def test_skill_precision_does_not_regress(scored):
    """AC-1.4 as a floor, and the more important of the two.

    An invented skill becomes an interview question about something the student
    never claimed. A missed one is a gap the confirmation screen lets them fill
    in fifteen seconds.
    """
    assert scored.skill_precision >= golden.TARGET_SKILL_PRECISION, "\n" + scored.report()


@pytest.mark.gate
def test_skill_recall_does_not_regress(scored):
    """AC-1.5 as a floor."""
    assert scored.skill_recall >= golden.TARGET_SKILL_RECALL, "\n" + scored.report()


def test_the_corpus_covers_the_shapes_the_spec_names(corpus):
    """A golden set that only holds easy documents measures nothing.

    §3.2 and §9 name the hard cases specifically, so the corpus is checked for
    them rather than trusted to have them — it is the kind of coverage that
    quietly erodes as fixtures get added for other reasons.
    """
    notes = " ".join(f"{r.id} {r.note}".casefold() for r in corpus)

    assert len(corpus) >= 12, "too small to say anything"
    assert "position of responsibility" in notes or any("por" in r.id for r in corpus), (
        "the Indian-resume heading vocabulary §6.3 names"
    )
    assert any("paragraph" in r.id for r in corpus), "EC-1.10, no bullets"
    assert any("no-headings" in r.id for r in corpus), "a document with no structure"
    assert any("two-column" in r.id for r in corpus), "linearised two-column output"
    assert any("ambiguous" in r.id for r in corpus), "the R / C / Go suite"


def test_a_document_with_no_headings_is_not_confidently_mislabelled(corpus):
    """The honest answer to "we could not tell what any of this is".

    Guessing `education` at 0.9 on an unstructured document is worse than
    saying `unknown` at 0.2: the first sends a project bullet somewhere nothing
    will probe it, and nobody can see that it happened.
    """
    unstructured = next(r for r in corpus if "no-headings" in r.id)
    score = golden.Score()
    golden.score_sections(unstructured, score)

    assert score.section_hits == score.section_total, "\n" + score.report()


def test_the_heading_lexicon_is_the_size_the_spec_asks_for():
    """§6.3: *"a heading lexicon (~120 variants ... the Indian-resume
    vocabulary specifically)"*.

    It was 49 when the golden set first ran, and both headings the spec names by
    example — "Areas of Interest", "Position of Responsibility" — were missing.
    """
    from backend_M01_Resume_Ingestion import headings

    assert headings.variant_count() >= 120

    for named in ("Areas of Interest", "Position of Responsibility"):
        assert headings.lookup(named) is not None, f"{named} is named in §6.3"


def test_a_skills_heading_always_introduces_a_list():
    """The invariant whose violation cost section F1 and skill recall together.

    Two lexicons drifted: `claims.py` decided what a section IS, `extract.py`
    decided whether a list followed, and a heading in one but not the other
    failed in a way that is genuinely hard to read from the outside — the
    section labelled correctly and every skill under it invisible.

    They are one table now. This asserts the part of the relationship that must
    hold: if a heading means "skills", a list follows it.
    """
    from backend_M01_Resume_Ingestion import headings

    for variant in headings.SECTION_HEADINGS["skills"]:
        assert headings.is_enumerating(variant), (
            f"{variant!r} is a skills heading, so the extractor must know a list follows it"
        )


def test_a_spoken_language_block_is_not_a_skills_list():
    """The one heading deliberately left out of the lexicon.

    "Languages Known" on an Indian resume is followed by Tamil, Hindi and
    English. Treated as a skills list it puts three spoken languages into the
    ontology review queue for ever.
    """
    from backend_M01_Resume_Ingestion import headings

    assert not headings.is_enumerating("Languages Known")
    assert headings.is_enumerating("Programming Languages")


def test_every_annotation_names_a_heading_that_exists(corpus):
    """`load()` raises on a stale annotation rather than sliding the labels.

    Getting here at all means every fixture's headings resolved; this asserts
    the corpus is actually annotated rather than silently empty.
    """
    for resume in corpus:
        assert resume.line_kinds, f"{resume.id} has no labelled lines"
        assert set(resume.line_kinds) <= set(range(len(resume.lines)))

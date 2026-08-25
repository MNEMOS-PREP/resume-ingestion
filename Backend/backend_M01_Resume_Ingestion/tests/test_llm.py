"""The model tier, tested without a model.

Every test here installs a fake through `set_llm`. None opens a socket, which is
the platform rule and also the only way these can assert anything: a real model
gives a different answer every run, so "did the pipeline handle THIS answer
correctly" is a question only a fake can be asked.

What is being protected is the promise in `llm.py`'s docstring — **the
deterministic result is the floor, never the fallback**. A student whose model
call fails, times out, returns nonsense, or was never configured must end up
with exactly the probes M01 produced before any of this existed.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from backend_M01_Resume_Ingestion import llm, probes
from backend_M01_Resume_Ingestion.claims import (
    PROBE_VERSION,
    ResumeClaim,
    SourceSpan,
    band,
    classify,
    extract_quantifiers,
    probes_for,
    score_claim,
)

BULLET = "Built a route planner in Python using dynamic programming on a 12k-node graph."


def _claim(text: str = BULLET) -> ResumeClaim:
    rid = uuid.uuid4()
    quantifiers = extract_quantifiers(text, 0, rid)
    scores = score_claim(
        text,
        quantifiers=quantifiers,
        concepts=[],
        has_link=False,
        prominence=0.8,
        today=date.today(),
    )
    claim = ResumeClaim(
        resume_id=rid,
        section_id=uuid.uuid4(),
        span=SourceSpan(artifact_id=rid, start=0, end=len(text), text=text),
        text=text,
        claim_type=classify(text),
        quantifiers=quantifiers,
        risk_band=band(scores["risk_score"]),
        **scores,
    )
    # The pipeline never produces a claim without probes — `extract_claims`
    # fills them from the ladder before anything else sees it. A helper that
    # skipped that step would let a test pass on a claim shape that cannot
    # occur, and the first thing it hid was `enrich` leaving a crashed claim
    # untouched: correct behaviour, but only visible against a real starting
    # state.
    claim.probes = probes_for(claim, concept_labels=[])
    return claim


class FakeLLM:
    """A model whose answer the test chooses."""

    def __init__(self, result: llm.LLMResult):
        self.result = result
        self.calls: list[dict] = []

    @property
    def available(self) -> bool:
        return True

    def structured(self, *, job, system, user, schema):
        self.calls.append({"job": job, "system": system, "user": user, "schema": schema})
        return self.result


def _good(probe_count: int = 3) -> llm.LLMResult:
    return llm.LLMResult(
        ok=True,
        model="test/model",
        data={
            "probes": [
                {
                    "depth": depth,
                    "question": f"A grounded question about the route planner, number {depth}?",
                    "expects": ["a concrete mechanism"],
                    "rationale": "Because a panel would.",
                }
                for depth in range(probe_count)
            ]
        },
    )


# ---------------------------------------------------------------------------
#  The floor holds
# ---------------------------------------------------------------------------


def test_with_no_model_the_probes_are_the_deterministic_ones():
    """The state of a fresh clone, of CI, and of every deployment with no key."""
    llm.set_llm(llm.NullLLM())
    claim = _claim()

    generated = probes.generate(claim, concept_labels=[])

    assert generated
    assert all(p.generated_by == PROBE_VERSION for p in generated)


@pytest.mark.parametrize(
    "failure",
    [
        llm.LLMResult(ok=False, reason="HTTP 429: rate limited"),
        llm.LLMResult(ok=False, reason="timeout after 20s"),
        llm.LLMResult(ok=False, reason="unparseable JSON"),
        llm.LLMResult(ok=True, data={"probes": []}),
        llm.LLMResult(ok=True, data={}),
    ],
)
def test_every_way_a_call_can_fail_leaves_the_template_probes(failure):
    """One assertion, five failure modes, because they must not diverge.

    A rate limit and a malformed body arrive by different paths and have to end
    in the same place: the student gets questions.
    """
    llm.set_llm(FakeLLM(failure))
    claim = _claim()

    generated = probes.generate(claim, concept_labels=[])

    assert generated
    assert all(p.generated_by == PROBE_VERSION for p in generated)


def test_a_crash_costs_one_claim_and_not_the_ingest():
    """`enrich` runs four-wide. An exception in one worker must not take an
    upload down — the student would lose a parse over a question."""

    class Exploding(FakeLLM):
        def structured(self, **kwargs):
            raise RuntimeError("provider did something unexpected")

    llm.set_llm(Exploding(_good()))
    claims = [_claim(), _claim("Led a team of four through the finals.")]

    improved = probes.enrich(claims, concepts_by_label={})

    assert improved == 0
    assert all(claim.probes for claim in claims)


# ---------------------------------------------------------------------------
#  A good answer is used, and labelled
# ---------------------------------------------------------------------------


def test_generated_probes_replace_the_templates_and_say_who_wrote_them():
    """`generated_by` is the provenance that matters.

    A probe a model wrote and one the ladder wrote must never be
    indistinguishable — downstream, "who said this" changes what may be done
    with it, exactly as `concept_source` does for a skill id.
    """
    llm.set_llm(FakeLLM(_good()))
    claim = _claim()

    generated = probes.generate(claim, concept_labels=[])

    assert len(generated) == 3
    assert all(p.generated_by == "test/model" for p in generated)
    assert [p.depth for p in generated] == [0, 1, 2]


def test_the_ladder_is_sorted_even_when_the_model_answers_out_of_order():
    result = _good()
    result.data["probes"].reverse()
    llm.set_llm(FakeLLM(result))

    generated = probes.generate(_claim(), concept_labels=[])

    assert [p.depth for p in generated] == sorted(p.depth for p in generated)


# ---------------------------------------------------------------------------
#  What is rejected
# ---------------------------------------------------------------------------


def test_a_probe_that_just_restates_the_bullet_is_dropped():
    """A model occasionally answers "ground it in the bullet" by quoting it.

    Being read your own sentence teaches a student nothing, so it falls back to
    the ladder — which at least asks something.
    """
    llm.set_llm(
        FakeLLM(
            llm.LLMResult(
                ok=True,
                model="test/model",
                data={
                    "probes": [
                        {
                            "depth": 0,
                            "question": BULLET + "?",
                            "expects": ["something"],
                            "rationale": "r",
                        }
                    ]
                },
            )
        )
    )

    generated = probes.generate(_claim(), concept_labels=[])

    assert all(p.generated_by == PROBE_VERSION for p in generated)


def test_a_probe_with_no_expects_is_dropped():
    """`expects` becomes M13's rubric key-points. A question with no expected
    answer cannot be scored, so it is not a probe."""
    llm.set_llm(
        FakeLLM(
            llm.LLMResult(
                ok=True,
                model="test/model",
                data={
                    "probes": [
                        {
                            "depth": 1,
                            "question": "What index type did you choose, and why that one?",
                            "expects": [],
                            "rationale": "r",
                        }
                    ]
                },
            )
        )
    )

    generated = probes.generate(_claim(), concept_labels=[])

    assert all(p.generated_by == PROBE_VERSION for p in generated)


def test_duplicate_depths_are_collapsed():
    """The ladder escalates. Two depth-1 questions is one question twice."""
    llm.set_llm(
        FakeLLM(
            llm.LLMResult(
                ok=True,
                model="test/model",
                data={
                    "probes": [
                        {
                            "depth": 1,
                            "question": "How did you build the priority queue for this?",
                            "expects": ["a mechanism"],
                            "rationale": "r",
                        },
                        {
                            "depth": 1,
                            "question": "How did you handle the graph updates arriving live?",
                            "expects": ["a mechanism"],
                            "rationale": "r",
                        },
                    ]
                },
            )
        )
    )

    generated = probes.generate(_claim(), concept_labels=[])

    assert len(generated) == 1


# ---------------------------------------------------------------------------
#  What reaches the model
# ---------------------------------------------------------------------------


def test_the_bullet_is_fenced_as_data_not_offered_as_instruction():
    """Trap 4. The injection filter already ran, and this is the second wall:
    the resume arrives inside a labelled fence with the system turn saying that
    nothing inside it is an instruction."""
    fake = FakeLLM(_good())
    llm.set_llm(fake)

    probes.generate(_claim(), concept_labels=[])

    sent = fake.calls[0]
    assert "RESUME_BULLET" in sent["user"]
    assert "quoted as data" in sent["system"]


def test_a_quoted_number_is_pointed_at_explicitly():
    """The number on a bullet is the thing a student is certain to be asked
    about, and the deterministic ladder already knows that."""
    fake = FakeLLM(_good())
    llm.set_llm(fake)

    probes.generate(
        _claim("Cut query time from 380ms to 45ms on a 12k-node graph."), concept_labels=[]
    )

    assert "380ms" in fake.calls[0]["user"]


def test_enrich_is_a_no_op_without_a_model():
    """No key, no work, no cost, and no time spent inside a 25 s parse budget."""
    llm.set_llm(llm.NullLLM())
    claims = [_claim()]
    before = [p.question for p in claims[0].probes]

    assert probes.enrich(claims, concepts_by_label={}) == 0
    assert [p.question for p in claims[0].probes] == before

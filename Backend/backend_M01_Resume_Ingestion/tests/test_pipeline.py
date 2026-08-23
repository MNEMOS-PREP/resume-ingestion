"""The rest of §12, and the gates §13 marks release-blocking.

The file is organised by what it is protecting rather than by which module the
code lives in: bullet shapes, date shapes, scoring properties, the §7 surface,
and the two gates that are about the PRODUCT rather than about a function.
"""

import uuid

import pytest

RESUME = """PRIYA SHARMA
priya.sharma@example.com | +91 98765 43210

EDUCATION
Amrita Vishwa Vidyapeetham, B.Tech CSE, 2022 - 2026, CGPA 8.1

EXPERIENCE
- Software Engineer Intern, Jun 2025 - Aug 2025. Led a team to ship internal tooling.

PROJECTS
- Built a route planner in Python using dynamic programming; cut average query time from 380ms to 45ms on a 12k-node graph.
- Worked on a world-class seamless blockchain platform.

SKILLS
Python, Java, SQL, Docker, Kubernetes, React
"""


def _ingest(client, text=RESUME, candidate=None):
    res = client.post(
        "/v1/resumes/from-text",
        json={"candidate_id": str(candidate or uuid.uuid4()), "raw_text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
#  §3.2.2 — "a bullet isn't a bullet"
# ---------------------------------------------------------------------------

BULLET_STYLES = {
    "hyphen": "- Built a route planner in Python on a 12k-node graph.",
    "bullet": "• Built a route planner in Python on a 12k-node graph.",
    "square": "▪ Built a route planner in Python on a 12k-node graph.",
    "triangle": "‣ Built a route planner in Python on a 12k-node graph.",
    "asterisk": "* Built a route planner in Python on a 12k-node graph.",
    "numbered": "1. Built a route planner in Python on a 12k-node graph.",
    "paren": "1) Built a route planner in Python on a 12k-node graph.",
    "word_o": "o Built a route planner in Python on a 12k-node graph.",
    "arrow": "→ Built a route planner in Python on a 12k-node graph.",
}


@pytest.mark.parametrize("style", sorted(BULLET_STYLES))
def test_every_bullet_glyph_a_real_resume_uses(client, m04_up, style):
    """§3.2.2: *"Real resumes use •, -, ▪, ‣, o, numbers, or nothing at all."*

    The `o` form is the one that catches people out — Word autoformats a
    lowercase o into a bullet and then exports it as the letter.
    """
    m04_up()
    data = _ingest(client, f"PROJECTS\n{BULLET_STYLES[style]}\n")

    assert len(data["claims"]) == 1, f"{style} was not read as a bullet"
    assert "route planner" in data["claims"][0]["text"]


def test_a_wrapped_bullet_is_one_claim_not_two(client, m04_up):
    """§6.5.1 — "Multi-line bullets merge on hanging indent".

    Split in two, the student gets a probe about half a sentence and the
    quantifier lands on a claim that no longer contains the thing it measures.
    """
    m04_up()
    data = _ingest(
        client,
        "PROJECTS\n"
        "- Built a route planner in Python using dynamic programming;\n"
        "  cut average query time from 380ms to 45ms on a 12k-node graph.\n",
    )

    assert len(data["claims"]) == 1
    claim = data["claims"][0]
    assert "380ms" in claim["text"] and "route planner" in claim["text"]
    assert [q["raw"] for q in claim["quantifiers"]]


def test_a_paragraph_resume_still_yields_claims(client, m04_up):
    """EC-1.10 — "Zero bullets (paragraph style): sentence-level claim
    extraction fallback".

    A resume written as prose is a real resume. Returning nothing for it is the
    same silent-empty-parse failure as a scanned PDF.
    """
    m04_up()
    data = _ingest(
        client,
        "PROJECTS\n"
        "I built a route planner in Python using dynamic programming. "
        "It cut average query time from 380ms to 45ms on a 12k-node graph. "
        "I also wrote a hash map from scratch to compare open addressing with chaining.\n",
    )

    assert len(data["claims"]) >= 2
    assert any("route planner" in c["text"] for c in data["claims"])


def test_a_short_fragment_is_not_a_claim(client, m04_up):
    """A heading that lost its newline is not something anyone can defend, and
    generating a probe for it is how the Claim Map stops being trusted."""
    m04_up()
    data = _ingest(client, "PROJECTS\nMisc. Other. Etc.\n")

    assert data["claims"] == []


# ---------------------------------------------------------------------------
#  §3.2.3 — Indian resume date formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "start", "end"),
    [
        ("Jan 2024 - Apr 2024", 2024, 2024),
        ("January 2024 to April 2024", 2024, 2024),
        ("2024 - 2025", 2024, 2025),
        ("Jun 2025 – Aug 2025", 2025, 2025),
        ("Mar 2023 until Sep 2023", 2023, 2023),
        ("Aug 2022 through Dec 2022", 2022, 2022),
        # The two-digit forms. Both are everywhere on Indian campus resumes and
        # both used to fall through to "no date at all" — which scores as
        # `recency = 0.5` rather than as wrong, so it was invisible.
        ("Jan'24 - Apr'24", 2024, 2024),
        ("2022-26", 2022, 2026),
        ("2022 - 26", 2022, 2026),
    ],
)
def test_date_ranges_students_actually_write(client, m04_up, written, start, end):
    """§3.2.3: *"Dates in Indian resumes are chaotic."*

    Every one of these has to produce a range with the right years, or the
    timeline-gap flag and the recency score both go quietly wrong.
    """
    m04_up()
    data = _ingest(client, f"EXPERIENCE\n- Intern at Zoho, {written}, built tooling.\n")

    ranges = data["entities"]["dates"]
    assert ranges, f"no date range parsed from {written!r}"
    assert (ranges[0]["start_year"], ranges[0]["end_year"]) == (start, end)


def test_a_heading_with_its_list_on_the_same_line_is_still_a_heading(client, m04_up):
    """`Skills: Python, SQL, Pandas` — the one-page resume shape.

    Without it a one-line resume has no sections at all, so every skill on it
    gets the weakest context and nothing downstream knows it was a skills list.
    """
    m04_up()
    data = _ingest(client, "VIKRAM SINGH\nvikram.singh@example.com\nSkills: Python, SQL, Pandas\n")

    kinds = {s["kind"] for s in data["sections"]}
    assert "skills" in kinds
    assert {"Python", "SQL", "Pandas"} <= set(data["parsed_skills"])


def test_a_position_of_responsibility_produces_a_claim(client, m04_up):
    """It is a role, not a hobby.

    Filed under `extras` — which is not a claim-bearing section — a student who
    led a 200-person technical festival got no claim, no probe and no score for
    it. On an Indian campus resume that is one of the two or three things a
    panel reliably asks about.
    """
    m04_up()
    data = _ingest(
        client,
        "POSITION OF RESPONSIBILITY\n"
        "- Coordinator, Pragyan technical festival. Led a team of 12 volunteers.\n",
    )

    assert [s["kind"] for s in data["sections"]] == ["experience"]
    assert len(data["claims"]) == 1
    assert data["claims"][0]["probes"]


@pytest.mark.parametrize(
    ("bullet", "claim_type", "must_mention"),
    [
        (
            "POSITION OF RESPONSIBILITY\n- Coordinator, Pragyan fest. Led a team of 12.\n",
            "led",
            "team",
        ),
        (
            "ACHIEVEMENTS\n- Ranked 3rd in the Smart India Hackathon national finals.\n",
            "achieved",
            "judged",
        ),
        (
            "PUBLICATIONS\n- Investigated contact-map refinement and published it at BIBM.\n",
            "researched",
            "question",
        ),
    ],
)
def test_a_probe_fits_the_kind_of_claim_it_is_about(
    client, m04_up, bullet, claim_type, must_mention
):
    """FR-1.10 — grounded in the bullet's verb, not only its nouns.

    §6.7's ladder is right and its worked example is an engineering one.
    Applied to every bullet regardless, that example's phrasing asks a student
    who coordinated a technical festival "how did you implement this project?"
    — which reads as the system not having listened, and §2.3 says that is what
    loses the confident student.
    """
    m04_up()
    data = _ingest(client, bullet)

    claim = data["claims"][0]
    assert claim["claim_type"] == claim_type
    questions = " ".join(p["question"] for p in claim["probes"]).casefold()

    assert must_mention in questions
    assert "implement" not in questions, "the engineering phrasing leaked"


def test_a_quoted_number_outranks_the_family_question(client, m04_up):
    """Whatever the claim type, a number the student wrote is the thing they
    are certain to be asked about, and quoting it back is what makes the probe
    theirs rather than a bank's."""
    m04_up()
    data = _ingest(
        client, "POSITION OF RESPONSIBILITY\n- Led a team of 12 across 3 events for 200 people.\n"
    )

    questions = " ".join(p["question"] for p in data["claims"][0]["probes"])
    assert any(q["raw"] in questions for q in data["claims"][0]["quantifiers"])


def test_a_hobbies_block_does_not_produce_claims(client, m04_up):
    """The other side of that line.

    "Reading, cricket" is not something anyone can be asked to defend, and
    generating three probes about it is how the Claim Map stops being trusted.
    """
    m04_up()
    data = _ingest(client, "HOBBIES\n- Reading, cricket and long-distance running.\n")

    assert [s["kind"] for s in data["sections"]] == ["extras"]
    assert data["claims"] == []


def test_a_label_value_line_is_not_a_section_boundary(client, m04_up):
    """The other half, and the reason the inline form needs an exact hit.

    A PERSONAL DETAILS block is full of `Label: value` lines. Matched loosely,
    "Languages Known: Tamil, English" becomes a skills section on the strength
    of the word "languages", and three spoken languages enter the ontology
    review queue for ever.
    """
    m04_up()
    data = _ingest(
        client,
        "PERSONAL DETAILS\nDate of Birth: 14 March 2002\nLanguages Known: Tamil, English\n",
    )

    assert [s["kind"] for s in data["sections"] if s["kind"] == "skills"] == []
    assert "Tamil" not in data["parsed_skills"]
    assert "English" not in data["parsed_skills"]


def test_a_section_word_used_as_english_is_not_a_heading(client, m04_up):
    """ "I have experience with Docker" is a bullet, not an EXPERIENCE heading.

    The heading matcher requires a line that is mostly just the heading, and
    this is what that requirement is protecting: a resume whose every third
    bullet starts a new section is one where no claim lands anywhere useful.
    """
    m04_up()
    data = _ingest(
        client,
        "PROJECTS\n"
        "- I have experience with Docker and used it to containerise four services.\n"
        "- Built a deployment tool; the interests of the ops team drove the design.\n"
        "- My activities included on-call rotation and writing the runbook.\n",
    )

    kinds = [s["kind"] for s in data["sections"]]
    assert kinds.count("projects") == 1
    assert "experience" not in kinds and "extras" not in kinds
    assert len(data["claims"]) == 3


def test_a_name_with_a_slash_or_a_dot_is_not_split(client, m04_up):
    """CI/CD is one thing. Node.js is one thing. A wrong split is a fabricated
    skill, and a fabricated skill becomes an interview question."""
    m04_up()
    data = _ingest(client, "TECHNICAL SKILLS\nCI/CD, TCP/IP, Node.js, .NET, C++, Objective-C\n")

    assert {"CI/CD", "TCP/IP", "Node.js", ".NET", "C++", "Objective-C"} <= set(
        data["parsed_skills"]
    )


def test_eligibility_text_on_a_skills_line_is_not_a_skill(client, m04_up):
    """ "7.5 CGPA" is a requirement, not a skill.

    Filed under skills it becomes a permanent entry in the unmapped queue that
    no ontology will ever have a concept for.
    """
    m04_up()
    data = _ingest(
        client, "KEY SKILLS\nPython, Django, 7.5 CGPA, 2+ years experience, B.Tech degree\n"
    )

    assert set(data["parsed_skills"]) == {"Python", "Django"}


def test_an_institution_name_never_swallows_the_heading_above_it(client, m04_up):
    """`\\s` matches a newline, and that is how a heading gets into a name.

    The institution is what a placement cell displays and matches a student by,
    so "EDUCATION\\nAmrita Vishwa Vidyapeetham" is not a cosmetic problem.
    """
    m04_up()
    data = _ingest(
        client,
        "EDUCATION\nAmrita Vishwa Vidyapeetham\nB.Tech CSE 2022-26, CGPA 8.1\n",
    )

    for institution in data["entities"]["institutions"]:
        assert "\n" not in institution
        assert not institution.upper().startswith("EDUCATION")


def test_a_word_before_the_year_is_not_read_as_a_month(client, m04_up):
    """`B.Tech CSE 2022-26` — "CSE" is not a month.

    An unknown month falls back to January, so the parsed range was right and
    the `raw` string shown back to the student said "CSE 2022-26". The wrong
    half is the one they can see.
    """
    m04_up()
    data = _ingest(client, "EDUCATION\nB.Tech CSE 2022-26, CGPA 8.1\n")

    found = data["entities"]["dates"][0]
    assert found["raw"] == "2022-26"
    assert (found["start_year"], found["end_year"]) == (2022, 2026)


def test_a_two_digit_start_year_needs_its_apostrophe(client, m04_up):
    """`Jan'25` is a date. `Section 12 - 15` is not.

    Without the asymmetry — apostrophe required on a two-digit START, optional
    on a two-digit END because the start already established we are reading
    years — any small numeric range on the page becomes a career timeline.
    """
    m04_up()
    data = _ingest(client, "EXPERIENCE\n- Solved problems 12 - 15 from the textbook.\n")

    assert data["entities"]["dates"] == []


def test_an_open_ended_range_is_marked_ongoing_not_guessed_at(client, m04_up):
    m04_up()
    data = _ingest(client, "EXPERIENCE\n- Intern at Zoho, 2024 - Present, built tooling.\n")

    found = data["entities"]["dates"][0]
    assert found["ongoing"] is True
    assert found["end_year"] is None


def test_a_gap_over_six_months_is_flagged_without_accusing(client, m04_up):
    """§6.8 — *"Gaps are normal (JEE drop year, health, family)."*

    Severity `info`, and the copy has to give the student a way to answer it
    rather than a finding to feel bad about.
    """
    m04_up()
    data = _ingest(
        client,
        "EXPERIENCE\n- Intern, Jan 2022 - Mar 2022, built tooling.\n"
        "- Analyst, Jan 2024 - Jun 2024, built more tooling.\n",
    )

    gaps = [f for f in data["red_flags"] if f["kind"] == "timeline_gap"]
    assert gaps
    assert gaps[0]["severity"] == "info"
    assert gaps[0]["suggested_answer"]
    assert "normal" in gaps[0]["explanation"].casefold()


# ---------------------------------------------------------------------------
#  §12 — risk scoring properties
# ---------------------------------------------------------------------------


def test_adding_a_quantifier_never_increases_risk(client, m04_up):
    """§12: "Risk scoring: monotonicity properties".

    A property rather than an example, because the failure it guards against is
    a weight change that inverts the scale — and a student being told a bullet
    got riskier for gaining a measurement would be worse than no score at all.
    """
    m04_up()
    vague = _ingest(client, "PROJECTS\n- Built a route planner in Python for the campus.\n")
    precise = _ingest(
        client,
        "PROJECTS\n- Built a route planner in Python for the campus, "
        "cutting query time from 380ms to 45ms.\n",
    )

    assert precise["claims"][0]["risk_score"] <= vague["claims"][0]["risk_score"]
    assert precise["claims"][0]["specificity"] >= vague["claims"][0]["specificity"]


def test_an_undated_claim_is_not_scored_as_an_old_one(client, m04_up):
    """Rule 3, one level down: "we do not know when" is not "this is old"."""
    m04_up()
    undated = _ingest(client, "PROJECTS\n- Built a parser in Python using recursion.\n")

    assert undated["claims"][0]["recency"] == 0.5


def test_prominence_orders_the_map_without_changing_a_band(client, m04_up):
    """§6.6 — the argument for keeping prominence out of `risk_score`.

    A bullet does not stop being badly written by moving down the page. It
    stops being the FIRST thing to fix, which is an ordering, and that is what
    prominence drives.
    """
    m04_up()
    data = _ingest(client)
    listing = client.get(f"/v1/resumes/{data['id']}/claims").json()

    scores = [c["prominence"] * c["risk_score"] for c in listing["claims"]]
    assert scores == sorted(scores, reverse=True)

    for claim in listing["claims"]:
        assert 0.0 <= claim["prominence"] <= 1.0


def test_the_one_thing_to_fix_first_is_the_most_prominent_risky_claim(client, m04_up):
    """§2.3 Screen 4 — *"It's your most prominent claim and your least
    defensible one."*

    Returned by the server rather than computed by each client, so two screens
    cannot disagree about which bullet the student should fix.
    """
    m04_up()
    data = _ingest(client)
    listing = client.get(f"/v1/resumes/{data['id']}/claims").json()

    fix_first = listing["fix_first"]
    assert fix_first is not None
    assert fix_first["risk_band"] == "risky"

    risky = [c for c in listing["claims"] if c["risk_band"] == "risky"]
    best = max(c["prominence"] * c["risk_score"] for c in risky)
    assert fix_first["prominence"] * fix_first["risk_score"] == best


# ---------------------------------------------------------------------------
#  §6.8 — the two red flags that were missing
# ---------------------------------------------------------------------------


def test_the_same_project_listed_twice_is_reported_once(client, m04_up):
    """§6.8 duplicate_project, and it reports a GROUP rather than a pair.

    Pair output is quadratic in the size of a cluster: four near-identical
    bullets is six flags saying the same thing. One flag naming four bullets is
    the sentence a student can act on.
    """
    m04_up()
    data = _ingest(
        client,
        "EXPERIENCE\n- Built a crop disease detector with a CNN reaching 94% accuracy.\n"
        "PROJECTS\n- Built a crop disease detector using a CNN, reaching 94% accuracy.\n",
    )

    duplicates = [f for f in data["red_flags"] if f["kind"] == "duplicate_project"]
    assert len(duplicates) == 1
    assert len(duplicates[0]["spans"]) == 2


def test_four_different_cnn_projects_are_four_projects(client, m04_up):
    """The other half of the rule.

    Shared vocabulary is not shared work. Flagging every ML student's resume
    for having several ML projects would make the flag worthless.
    """
    m04_up()
    data = _ingest(
        client,
        "PROJECTS\n"
        "- Built a crop disease detector with a CNN on 12k leaf images.\n"
        "- Trained a speech emotion classifier using an LSTM over 40 hours of audio.\n"
        "- Wrote a chess engine with alpha-beta pruning to depth 8.\n",
    )

    assert not [f for f in data["red_flags"] if f["kind"] == "duplicate_project"]


def test_a_leadership_claim_with_nothing_under_it_is_flagged(client, m04_up):
    m04_up()
    data = _ingest(client, "EXPERIENCE\n- Led the backend team and owned the architecture.\n")

    flags = [f for f in data["red_flags"] if f["kind"] == "title_inflation"]
    assert flags
    assert "how many" in flags[0]["explanation"].casefold()


def test_a_leadership_claim_with_a_team_size_is_not_flagged(client, m04_up):
    """The claim is not the problem; the absence of anything under it is."""
    m04_up()
    data = _ingest(
        client, "EXPERIENCE\n- Led a team of 4 to ship a REST API serving 50k requests/day.\n"
    )

    assert not [f for f in data["red_flags"] if f["kind"] == "title_inflation"]


def test_a_duplicate_heavy_document_does_not_produce_unbounded_flags(client, m04_up):
    """The regression this cost an eighty-second test run to find.

    Two thousand near-identical bullets produced roughly two million pairwise
    flags and 1.4 GB of JSON, and the insert died with "string or blob too
    big". Flag output has to be linear in distinct pieces of work.
    """
    m04_up()
    data = _ingest(client, "PROJECTS\n" + "- Built a route planner in Python.\n" * 300)

    duplicates = [f for f in data["red_flags"] if f["kind"] == "duplicate_project"]
    assert len(duplicates) <= 5
    assert data["parse_ms"] < 25_000


# ---------------------------------------------------------------------------
#  §7 — the API surface
# ---------------------------------------------------------------------------


def test_claims_can_be_filtered_by_band(client, m04_up):
    m04_up()
    data = _ingest(client)

    risky = client.get(f"/v1/resumes/{data['id']}/claims?band=risky").json()
    assert risky["claims"]
    assert all(c["risk_band"] == "risky" for c in risky["claims"])
    assert risky["total"] == len(data["claims"])


def test_an_unknown_band_is_refused_rather_than_returning_everything(client, m04_up):
    m04_up()
    data = _ingest(client)

    assert client.get(f"/v1/resumes/{data['id']}/claims?band=terrible").status_code == 422


def test_red_flags_come_back_worst_first(client, m04_up):
    m04_up()
    data = _ingest(client)
    body = client.get(f"/v1/resumes/{data['id']}/red-flags").json()

    order = {"serious": 0, "notable": 1, "info": 2}
    ranks = [order[f["severity"]] for f in body["red_flags"]]
    assert ranks == sorted(ranks)


def test_the_progress_stream_narrates_real_stages(client, m04_up):
    """§2.3 Screen 2 — narrated, and narrated from what actually happened.

    A progress bar animating over work that is not running is the theatre the
    spec warns about, so every line is derived from the stored row.
    """
    m04_up()
    data = _ingest(client)

    with client.stream("GET", f"/v1/resumes/{data['id']}/stream") as response:
        assert response.status_code == 200
        lines = [line[6:] for line in response.iter_lines() if line.startswith("data:")]

    import json

    events = [json.loads(line) for line in lines]
    stages = [event["stage"] for event in events]

    assert stages[0] == "intake" and stages[-1] == "complete"
    assert [e["progress"] for e in events] == sorted(e["progress"] for e in events)
    assert any(str(len(data["claims"])) in e["detail"] for e in events)


def test_confirming_marks_the_parse_as_signed_off(client, m04_up):
    """§2.3 Screen 3 — until this is called the parse is a proposal.

    Downstream modules need to tell a reading the student checked from one
    nobody has looked at.
    """
    m04_up()
    data = _ingest(client)
    assert data["confirmed"] is False

    confirmed = client.post(f"/v1/resumes/{data['id']}/confirm").json()
    assert confirmed["confirmed"] is True
    assert confirmed["parse_status"] == "ready"

    # Idempotent: confirming twice is a double-click, not an error.
    assert client.post(f"/v1/resumes/{data['id']}/confirm").status_code == 200


def test_a_rewrite_suggests_and_never_replaces(client, m04_up):
    """FR-1.19 with §15 decision 2.

    *"A resume the student didn't write is a resume they can't defend, which is
    the exact failure this module exists to prevent."*
    """
    m04_up()
    data = _ingest(client)
    weak = next(c for c in data["claims"] if c["risk_band"] == "risky")

    suggestion = client.post(f"/v1/resumes/{data['id']}/claims/{weak['id']}/rewrite").json()

    assert suggestion["original"] == weak["text"]
    assert "[" in suggestion["suggestion"], "the student's own facts stay as blanks"
    assert suggestion["first_fix"]
    assert suggestion["caveat"]

    # And the claim itself is untouched.
    after = client.get(f"/v1/resumes/{data['id']}").json()
    assert next(c for c in after["claims"] if c["id"] == weak["id"])["text"] == weak["text"]


def test_a_rewrite_names_the_filler_words_it_wants_dropped(client, m04_up):
    m04_up()
    data = _ingest(client)
    blockchain = next(c for c in data["claims"] if "blockchain" in c["text"])

    suggestion = client.post(f"/v1/resumes/{data['id']}/claims/{blockchain['id']}/rewrite").json()

    assert {w.casefold() for w in suggestion["drop_words"]} >= {"world-class", "seamless"}


def test_editing_a_bullet_rescores_that_claim_and_no_other(client, m04_up):
    """§8.3 — "Editing a bullet re-scores only that claim"."""
    m04_up()
    data = _ingest(client)
    weak = next(c for c in data["claims"] if c["risk_band"] == "risky")
    others = {c["id"]: c["risk_score"] for c in data["claims"] if c["id"] != weak["id"]}

    after = client.patch(
        f"/v1/resumes/{data['id']}/claims/{weak['id']}",
        json={
            "field": "text",
            "value": (
                "Built a blockchain settlement layer in Go, "
                "cutting confirmation time from 900ms to 120ms across 4k transactions."
            ),
        },
    ).json()

    edited = next(c for c in after["claims"] if c["id"] == weak["id"])
    assert edited["user_edited"] is True
    assert edited["risk_score"] < weak["risk_score"]
    assert edited["quantifiers"]

    for claim in after["claims"]:
        if claim["id"] in others:
            assert claim["risk_score"] == others[claim["id"]]


def test_a_student_can_delete_a_claim(client, m04_up):
    """EC-1.17 — "User deletes every claim in the editor: allowed."

    A claim the student says is not theirs must not reach M05 or M06 at all.
    Routed through the correction log rather than as a bare delete, because
    striking a claim we invented is the most informative correction there is.
    """
    m04_up()
    data = _ingest(client)
    victim = data["claims"][0]["id"]

    after = client.delete(f"/v1/resumes/{data['id']}/claims/{victim}").json()

    assert victim not in [c["id"] for c in after["claims"]]
    assert len(after["claims"]) == len(data["claims"]) - 1
    logged = client.get(f"/v1/resumes/{data['id']}/corrections").json()
    assert any(c["target"] == "claim" and c["field"] == "present" for c in logged)


def test_deleting_every_claim_leaves_a_working_resume(client, m04_up):
    """The second half of EC-1.17: "product continues resume-free"."""
    m04_up()
    data = _ingest(client)
    for claim in data["claims"]:
        client.delete(f"/v1/resumes/{data['id']}/claims/{claim['id']}")

    listing = client.get(f"/v1/resumes/{data['id']}/claims").json()
    assert listing["claims"] == []
    assert listing["fix_first"] is None
    assert client.post(f"/v1/resumes/{data['id']}/confirm").status_code == 200


def test_a_student_can_correct_a_misread_date(client, m04_up):
    """FR-1.11 — §2.3 lists "sections, bullets, skills, and dates".

    Dates were the one editable target with no path, and a mis-read date drives
    both the timeline-gap flag and `recency`.
    """
    m04_up()
    data = _ingest(client, "EXPERIENCE\n- Intern at Zoho, 2024 - 2025, built tooling.\n")
    assert data["entities"]["dates"][0]["start_year"] == 2024

    after = client.patch(
        f"/v1/resumes/{data['id']}/dates/0", json={"value": "Jun 2023 - Aug 2023"}
    ).json()

    corrected = after["entities"]["dates"][0]
    assert (corrected["start_year"], corrected["end_year"]) == (2023, 2023)
    assert corrected["user_corrected"] is True


def test_a_date_that_will_not_parse_is_refused_not_stored(client, m04_up):
    """A date nothing can compare is worse than the mis-read it replaced — the
    mis-read at least still fires the gap check."""
    m04_up()
    data = _ingest(client, "EXPERIENCE\n- Intern at Zoho, 2024 - 2025, built tooling.\n")

    res = client.patch(f"/v1/resumes/{data['id']}/dates/0", json={"value": "sometime last year"})

    assert res.status_code == 422
    unchanged = client.get(f"/v1/resumes/{data['id']}").json()
    assert unchanged["entities"]["dates"][0]["start_year"] == 2024


def test_a_failed_upload_is_recorded_not_only_raised(client, m04_up):
    """§10: "Everything fails → parse_status=failed".

    `parse_status` and `parse_error` were declared on the table and written by
    nothing, so a student whose upload failed three times left no trace and
    "which file types actually fail for real students" was unanswerable.
    """
    m04_up()
    candidate = uuid.uuid4()
    res = client.post(
        "/v1/resumes",
        data={"candidate_id": str(candidate)},
        files={"file": ("cv.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "")},
    )
    assert res.status_code == 415

    rows = client.get(f"/v1/resumes/candidate/{candidate}").json()
    assert len(rows) == 1
    assert rows[0]["parse_status"] == "failed"
    assert "legacy_doc" in rows[0]["parse_error"]
    # A failed upload must not supersede a resume the student already has.
    assert rows[0]["is_active"] is False


def test_a_section_can_be_relabelled_through_its_own_route(client, m04_up):
    m04_up()
    data = _ingest(client)
    section = data["sections"][1]

    after = client.patch(
        f"/v1/resumes/{data['id']}/sections/{section['id']}",
        json={"field": "kind", "value": "experience"},
    ).json()

    changed = next(s for s in after["sections"] if s["id"] == section["id"])
    assert changed["kind"] == "experience"
    assert changed["user_corrected"] is True


def test_deleting_a_resume_takes_the_contact_row_with_it(client, m04_up):
    """§7 — hard delete. The point of a deletion request."""
    m04_up()
    data = _ingest(client)

    assert client.delete(f"/v1/resumes/{data['id']}").status_code == 204
    assert client.get(f"/v1/resumes/{data['id']}").status_code == 404
    assert client.get(f"/v1/resumes/{data['id']}/contact").status_code == 404


def test_deleting_one_candidates_copy_keeps_anothers_blob(client, m04_up):
    """Two students who uploaded the same file share one content-addressed
    object. One of them leaving must not break the other's spans."""
    m04_up()
    from backend_M01_Resume_Ingestion import storage

    mine = _ingest(client)
    theirs = _ingest(client)  # different candidate, identical bytes
    assert mine["content_sha256"] == theirs["content_sha256"]

    client.delete(f"/v1/resumes/{mine['id']}")

    assert storage.get(theirs["content_sha256"]) is not None
    assert client.get(f"/v1/resumes/{theirs['id']}").status_code == 200


def test_re_uploading_the_same_file_returns_the_existing_parse(client, m04_up):
    """EC-1.8 — *"Students re-upload the same file constantly."*

    Returning the stored parse also returns their corrections, which is the
    behaviour they expect and the cheapest possible parse.
    """
    m04_up()
    candidate = uuid.uuid4()
    first = _ingest(client, candidate=candidate)
    again = _ingest(client, candidate=candidate)

    assert again["id"] == first["id"]


def test_a_new_version_deactivates_the_old_one_without_deleting_it(client, m04_up):
    """EC-1.9 — *"New row; old marked inactive; claims keep their history so
    progress tracking survives."*"""
    m04_up()
    candidate = uuid.uuid4()
    first = _ingest(client, candidate=candidate)
    second = _ingest(client, RESUME.replace("blockchain platform", "payments platform"), candidate)

    assert second["id"] != first["id"]
    assert second["is_active"] is True
    assert client.get(f"/v1/resumes/{first['id']}").json()["is_active"] is False


def test_the_diff_query_form_matches_the_path_form(client, m04_up):
    """§7 spells it `?against=`; this module shipped the path form first."""
    m04_up()
    candidate = uuid.uuid4()
    first = _ingest(client, candidate=candidate)
    second = _ingest(client, RESUME.replace("blockchain platform", "payments platform"), candidate)

    by_query = client.get(f"/v1/resumes/{second['id']}/diff?against={first['id']}").json()
    by_path = client.get(f"/v1/resumes/{second['id']}/diff/{first['id']}").json()

    assert by_query == by_path
    assert by_query["summary"]


def test_capabilities_reports_what_this_deployment_can_read(client):
    """§2.4 — a control that looks live and does nothing reads as a broken
    product. The upload screen asks before it renders one."""
    body = client.get("/v1/capabilities").json()

    assert body["accepts"]["text/plain"] is True
    assert body["always_available"] == ["text/plain"]
    assert isinstance(body["ocr"], bool)
    assert body["max_pages"] >= 1


# ---------------------------------------------------------------------------
#  §13 — gates
# ---------------------------------------------------------------------------


@pytest.mark.gate
def test_the_product_works_end_to_end_with_no_resume(client, m04_up):
    """AC-1.2 [GATE] — *"Product usable end-to-end with no resume."*

    FR-1.14 is a P0, and it is the requirement most easily broken by accident:
    every later feature assumes a resume exists, and one 500 on an empty
    document turns "practise without one" into a dead end. So the empty case is
    walked all the way through the surface a Skip path would touch.
    """
    m04_up()
    data = _ingest(client, "")
    resume_id = data["id"]

    assert data["parsed_skills"] == []
    assert data["claims"] == []

    assert client.get(f"/v1/resumes/{resume_id}").status_code == 200
    assert client.get(f"/v1/resumes/{resume_id}/claims").json()["fix_first"] is None
    assert client.get(f"/v1/resumes/{resume_id}/red-flags").json()["red_flags"] == []
    assert client.get(f"/v1/resumes/{resume_id}/skills").json()["mentions"] == []
    assert client.post(f"/v1/resumes/{resume_id}/confirm").status_code == 200

    with client.stream("GET", f"/v1/resumes/{resume_id}/stream") as response:
        assert response.status_code == 200


@pytest.mark.gate
def test_every_span_resolves_on_a_file_upload_too(client, m04_up):
    """AC-1.1 [GATE], extended past the paste path.

    A PDF text layer is built by joining positioned words, so its offsets are
    computed rather than given. That is exactly where a span stops resolving,
    and it is the path the existing gate did not cover.
    """
    pymupdf = pytest.importorskip("pymupdf")
    m04_up()

    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(
        pymupdf.Rect(40, 40, 540, 700),
        "PRIYA SHARMA\n\nPROJECTS\n"
        "- Built a route planner in Python using dynamic programming;\n"
        "cut average query time from 380ms to 45ms on a 12k-node graph.\n"
        "- Led a team of 4 to ship a REST API serving 50k requests/day.\n\n"
        "SKILLS\nPython, SQL, Docker\n",
        fontsize=11,
    )
    data = document.tobytes()
    document.close()

    response = client.post(
        "/v1/resumes",
        data={"candidate_id": str(uuid.uuid4())},
        files={"file": ("resume.pdf", data, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    source = body["redacted_text"]

    assert body["mime"] == "application/pdf"
    assert body["claims"], "a PDF with two project bullets produced no claims"

    for claim in body["claims"]:
        span = claim["span"]
        assert " ".join(source[span["start"] : span["end"]].split()) == " ".join(
            span["text"].split()
        )
        # FR-1.3: a claim off a PDF knows where it is on the page.
        assert span["bbox"] is not None
        assert span["page"] >= 1


@pytest.mark.gate
def test_an_upload_of_the_wrong_type_names_the_problem_and_the_way_out(client, m04_up):
    """§10 — *"never a raw stack trace"*, and the paste path always works."""
    m04_up()
    response = client.post(
        "/v1/resumes",
        data={"candidate_id": str(uuid.uuid4())},
        files={"file": ("resume.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "")},
    )

    assert response.status_code == 415
    detail = response.json()["detail"]
    assert detail["code"] == "legacy_doc"
    assert detail["fallback"] == "text"
    assert "save as PDF or .docx" in detail["message"]

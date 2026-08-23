# research/

Measurement, not product. Nothing here is imported by the running module.

```bash
Backend/.venv/Scripts/python research/score_golden.py
```

---

## The golden set

`data/golden/resumes/` holds hand-annotated resumes. Each one carries the
document, the section kind of every line, and the skills a correct parse should
find. `score_golden.py` runs the real pipeline over all of them and reports
three numbers; the same numbers are gate tests in
`Backend/backend_M01_Resume_Ingestion/tests/test_golden.py`, so a regression
fails the build rather than waiting for somebody to run a script.

| | Target | Spec |
|---|---|---|
| Section F1 | ≥ 0.90 | AC-1.3 |
| Skill precision | ≥ 0.95 | AC-1.4 |
| Skill recall | ≥ 0.85 | AC-1.5 |

### What these numbers are, and what they are not

**Read this before quoting one.**

The spec asks for *"30 resumes with hand-annotated sections, claims, and skills,
collected with consent from seniors"*. This corpus is **not that**. It is
synthetic — written to cover the shapes the spec names, not sampled from what
students actually submit. The documents and the parser came from the same hand,
so the numbers are an optimistic estimate of real-world performance, and adding
more fixtures does not fix that.

So it does one of two jobs:

- **A regression gate — yes.** A change that makes segmentation or extraction
  worse fails the build. That holds regardless of where the documents came
  from, because the comparison is against a fixed annotation.
- **The acceptance measurement — no.** AC-1.3/1.4/1.5 are claims about real
  resumes and stay *unmeasured* until real ones land. `golden.MEASURES_REAL_WORLD`
  is `False` and the report prints a note saying so.

### Replacing it with real resumes

The structure is the reusable part. When consented resumes arrive:

1. Drop them into `data/golden/resumes/` in the same schema (below).
2. Delete or keep the synthetic sets — keeping them is fine, they are labelled
   by their `set` field.
3. Flip `MEASURES_REAL_WORLD` to `True` in `golden.py`.

Nothing else changes: the scorer, the gates and the report are identical.

### Schema

```json
{
  "set": "conventional",
  "note": "why this group exists",
  "resumes": [
    {
      "id": "conventional-01-latex",
      "note": "what this document is testing",
      "text": ["line", "by", "line"],
      "preamble": "contact",
      "sections": [["EDUCATION", "education"], ["SKILLS", "skills"]],
      "skills": ["Python", "SQL"]
    }
  ]
}
```

`sections` anchors on **heading text**, not line numbers. A line number in a
hand-written fixture goes stale the moment somebody inserts a line, and it goes
stale *silently* — the file still parses and the labels just slide by one.
Heading text either matches or raises. `preamble` is the kind for lines before
the first heading; every non-empty line gets exactly one kind.

### The sets

| File | What it is for |
|---|---|
| `01_conventional.json` | LaTeX, Word and Google Docs shapes. The easy cases; a drop here is structural |
| `02_indian_headings.json` | "Position of Responsibility", "Areas of Interest", "Industrial Training" — the vocabulary §6.3 names specifically |
| `03_hard_layouts.json` | Linearised two-column output, paragraph style, no headings at all, colon headings |
| `04_edge_cases.json` | §9: fresher with only coursework, research CV, the R/C/Go ambiguity suite, a skill repeated |
| `05_traps.json` | Documents written to make the parser *wrong* — section words used as English, `CI/CD`, inline headings, eligibility text on a skills line |

`05_traps.json` is the one that earns its keep. A corpus of well-formed
documents scores 1.000 and measures nothing; the traps are written so a
plausible wrong answer scores worse than the right one.

### What it has already caught

Every one of these was found by running the set, not by reading the code:

- **The heading lexicon was 49 variants where §6.3 asks for ~120**, and both
  headings the spec names by example — "Areas of Interest", "Position of
  Responsibility" — were missing. Section F1 was 0.906 and skill recall 0.806.
- **There were two heading lexicons and they had drifted.** `claims.py` decided
  what a section *is*; `extract.py` decided whether a list followed. A heading
  in one and not the other labels the section correctly and makes every skill
  under it invisible. They are one table in `headings.py` now, and a test
  asserts every skills heading is also an enumerating one.
- **`Skills: Python, SQL` on one line was not a heading at all**, so a one-page
  resume had no sections and every skill on it got the weakest context.
- **`.NET` lost its leading dot.** The metric missed it — `normalise_alias`
  folds the dot away, so the two forms compare equal — and the student would
  have seen "NET" on the read-back of their own document.

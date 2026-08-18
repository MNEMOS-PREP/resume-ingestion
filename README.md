# M01 — Resume Ingestion & Claim Extraction

> **What the student says they did, in a form the rest of the platform can
> test.** Every later module that asks "defend this bullet" is asking about
> something this module extracted.
>
> Spec: [plan_in_depth/M01_Resume_Ingestion.md](plan_in_depth/M01_Resume_Ingestion.md) · Ports: API `8101`, web `5201` ([PORTS.txt](PORTS.txt))

```bash
git clone https://github.com/MNEMOS-PREP/resume-ingestion
cd resume-ingestion
python -m venv Backend/.venv && Backend/.venv/Scripts/python -m pip install -e ".[dev]"
Backend/.venv/Scripts/python -m pytest       # 9 passed, no network, no API key
cd Frontend && npm install && cd ..
start_resume.bat                              # API :8101 · web :5201
```

No API key needed, and **no model is called anywhere in this milestone.** The
scan is a word-boundary match over an ontology. The spec's pipeline (§6) is
LLM-heavy; none of it has landed.

---

## What is built

A skill extractor, and one property held properly.

| Endpoint | What it does |
|---|---|
| `POST /v1/resumes/ingest` | Word-boundary scan of resume text against M04's ontology; resolves each hit to a `concept_id` |
| `GET /v1/resumes/{id}` | The stored resume |
| `GET /v1/resumes/candidate/{candidate_id}` | Every resume for one candidate |
| `GET /v1/deps` | Which upstreams are up and what breaks when they are not |
| `GET /health` | |

**The property worth the code: nothing leaves here claiming a stronger source
than it has.** Both halves are tested rather than asserted in a comment.

**1. A guessed `concept_id` is labelled as a guess.** [`router.py`](Backend/backend_M01_Resume_Ingestion/router.py) ·
A `concept_id` is a licence for M05 to build questions on and for M13 to score
against. With M04 unreachable this module falls back to a five-entry table —
useful, and now carrying `concept_source: "offline_fallback"` per label, plus
`scanned_against` for the lexicon itself. This mattered more than it sounds:
the manifest declared M04 with no `base_url`, `from_manifest` defaults that to
`""`, and every M04 call was therefore skipped *even with M04 healthy on
:8104*. The offline table was not the fallback path, it was the only path, and
nothing said so.

**2. An unmappable skill is kept, not dropped.** Skills M04 could not resolve
used to vanish from the response entirely. The student then meets a read-back
screen that contradicts their own resume, with no explanation — which reads as
"the parser is broken". They are now in `unresolved_skills`, stated as
unmapped rather than absent.

### What is deliberately not built

Nearly all of it, and it is **absent, not stubbed** — an endpoint that returns
a placeholder is worse than one that does not, because a caller writes against
it and finds out later.

Measured against [§4](plan_in_depth/M01_Resume_Ingestion.md), **1 of 20
functional requirements is met**: FR-1.7 (normalise every skill mention to a
`concept_id` or mark it unmapped). FR-1.1 is one third met — pasted text only,
no PDF, no DOCX.

The module is named *Claim Extraction* and **extracts no claims.** In spec
terms nothing below `SkillMention` exists: no `SourceSpan`, no
`ResumeSection`, no `ResumeClaim`, no `Quantifier`, no `ClaimProbe`.

| Missing | What it blocks |
|---|---|
| **`SourceSpan`** (§5, FR-1.3/1.8) | The spec calls it "the atom of traceability — everything downstream cites one of these". Without spans, M13 cannot verify an evidence quote, M19 has nothing to put in the ledger, and the PDF highlight in §8 has no coordinates. This is the first thing to build; use `ai_core.evidence.EvidenceSpan` rather than declaring a second type. |
| **`ResumeClaim` + scoring** (FR-1.8/1.9) | M05 has no claim-grounded probes, M06 has no claims to defend, M13 has no claim under test. Four of the five downstream modules consume claims, so today none of them can consume this module at all. |
| **Sections & entities** (FR-1.5/1.6) | No structure, so no confirmation UI and no red-flag detection. |
| **Probe generation** (FR-1.10) | The 1–3 escalating questions per claim are the module's product for M06. |
| **PII handling** (FR-1.17, P0) | The contact block is not classed, separated, or withheld from logs. Right now the whole resume text is stored in one column and returned verbatim by two endpoints. **This is the one gap that is a liability rather than a missing feature.** |
| **Correction persistence** (FR-1.11/1.12) | User edits as ground truth over the parser. |
| **Immutable raw storage by SHA-256** (FR-1.2) | No re-parse, no diff view, no audit. |
| **OCR fallback, multi-column reading order** (FR-1.4/1.16) | A scanned or two-column resume yields nothing, silently. |

### Contract note

The spec's §7 surface is 14 endpoints rooted at `POST /v1/resumes`; this code
serves `POST /v1/resumes/ingest`. Nothing consumes it yet, so the divergence
is free to resolve in whichever direction — but resolve it before M05 or M06
writes against it.

---

## The frontend

Two screens on `:5201`, and the reason they are only two is that the backend
fills only two. `src/api.ts` has one hook per endpoint and none without one —
so there is no `useClaims`, no `useRedFlags`, no `useConfirm`, because writing
them would let a screen be built on an endpoint that does not answer.

**There is no mastery bar on these screens, on purpose.** M01 reads claims; it
does not test them. A bar here — even an empty one — would imply a measurement
this module has no business making, and `@ai/core` owns that component precisely
so it appears only where a measurement exists.

What the screens do carry is the honesty the backend now enforces:

- **Every mapped skill says who mapped it.** `ontology` (green) means M04
  resolved the id; `guessed offline` (amber) means the five-entry table did and
  nothing has confirmed it exists. An id is a licence for M05 to build questions
  on and M13 to score against, so handing one over unlabelled is how a concept
  nobody reviewed reaches a real interview.
- **Unmapped skills get their own group**, hatched and colourless — outside the
  scale rather than at the bottom of it. Silently dropping them makes the
  read-back contradict the student's own document, and the fix they reach for is
  editing their resume to please the parser.
- **The scan source is stated above the list.** A three-skill result from the
  offline lexicon and a three-skill result from the full ontology look identical
  and mean completely different things.

What is absent rather than stubbed: no upload control (PDF/DOCX aren't parsed,
and a disabled button reads as a broken product), no SSE progress feed (§2.3's
stage-by-stage screen would be theatre over a 30 ms regex), and no editing
(FR-1.11/1.12 need a PATCH endpoint and a section model — an input that
discards what you type is worse than no input). The claims section names what
the module is called after and does not do, including the FR-1.17 PII gap.

---

## Layout

```
module.json                     manifest: ports, upstreams, feeds. Read at
                                request time to probe M04.
dependencies.txt                the same thing for humans, plus what breaks
PORTS.txt                       platform-wide port allocation
Backend/
  backend_M01_Resume_Ingestion/
    app.py                      FastAPI app, SQLite engine, /health
    router.py                   every endpoint, and the M04 client
    models.py                   Resume — the whole data model today
    tests/                      9 tests, no socket opened
  seed.py                       two resumes, provenance-marked as seeded
Frontend/
  frontend_M01_Resume_Ingestion/
    src/api.ts                  one hook per endpoint, and none without one
    src/types.ts                only fields the API actually sends
    src/components/             IngestPage, ResumePage, SkillSet, DepsPage
    src/ui/                     shell, primitives, design tokens
scripts/                        launcher engine (shared, identical across repos)
start_resume.bat                this module            (:8101 · :5201)
start_all.bat                   plus any sibling repo checked out next door
```

## Conventions worth knowing before you edit

- **`module.json` and `dependencies.txt` are one fact in two files.** Edit one,
  edit the other. The backend reads the first at startup.
- **Every declared upstream carries a `base_url`.** `from_manifest` defaults it
  to `""`, and an empty base_url disables the upstream *silently*. That was
  this repo's first bug, and it is invisible from the outside — the module
  looks like it is working.
- **The sibling folder name comes from the repo URL's last path segment.**
  On-disk folder and GitHub repo name must agree or `start_all.bat` skips a
  running module in silence.
- **Resume text is untrusted input** (spec §6.7) and, once claims land, an
  injection surface. Nothing here sanitises it yet because nothing here sends
  it to a model yet. That order must not reverse.
- `ruff check .` before committing; the config is in `pyproject.toml`.

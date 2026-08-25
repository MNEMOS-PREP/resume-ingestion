# M01 — TODO

Task list for taking **M01 Resume Ingestion & Claim Extraction** to 100% of
[M01_Resume_Ingestion.md](M01_Resume_Ingestion.md).

> **Read this first when starting a session on M01.** It is the running state of
> the module: what is done, what is next, and what is deliberately deferred.
> Update it as things land — a stale list is worse than no list, because the
> next session trusts it.

- **Repo:** `resume-ingestion` · **Ports:** API `8101`, web `5201`
- **Run the suite:** `Backend/.venv/Scripts/python -m pytest`
- **Run the gates only:** `Backend/.venv/Scripts/python -m pytest -m gate`
- **Lint:** `Backend/.venv/Scripts/python -m ruff check Backend/`

Legend: ✅ done · 🟡 partly done · ⬜ not started

---

## 0. Ideas and scouting

Things worth building that did not come from the spec — usually from reading
somebody else's implementation. **New ideas go at the top of this section.**

The rule we keep arriving at: borrow a **technique**, not a **component**. The
platform's contracts — character offsets, per-fact provenance, permanent
evidence — are more demanding than general-purpose tools assume, so integration
usually costs more than reimplementing the one idea we actually wanted.

### Scouting verdict: pdf-inspector — **do not adopt, take two ideas**

From reading [firecrawl/pdf-inspector](https://github.com/firecrawl/pdf-inspector)
(Rust, MIT). Its extraction engine is **not** worth adopting — M01 already does
columns, typography, tables and OCR routing, its headline output is Markdown
where our whole contract is character offsets, and a native binding is a demo
that does not start on a marker's laptop. Two of its ideas are worth taking.

### ⬜ Encoding-corruption detection — a real gap, confirmed

```
138 chars, clears the 100-char OCR threshold
language: unknown
notes: NONE — accepted silently
```

That is private-use-area mojibake, the classic broken-`ToUnicode` signature.
M01 accepts it, produces a confidently empty parse, and tells the student
nothing. The garbled-Latin variant is worse in a different way — it gets
flagged, but as **German**, which is a wrong explanation rather than no
explanation.

This is exactly the silent-wrong-answer class the module is written against,
and we do not catch it. A PDF whose font map is broken extracts something that
has the LENGTH of text and none of the meaning, so every check downstream —
the OCR threshold, the language guess, the section lexicon — is being asked
about characters that are not letters.

Detect on: private-use-area codepoints, no vowels, absent word structure, a
character distribution nothing like prose. Route it to OCR, which is the one
thing that can actually read such a page, and say so.

### ⬜ Per-page OCR routing

`parse_pdf` OCRs the WHOLE document when the text layer is thin. A resume with
one scanned page gets everything OCR'd — slower, and
`OCR_CONFIDENCE_PENALTY` lands on pages that did not need it, so a perfectly
readable page 1 is reported as less certain than it is.

Route per page instead: classify each page's text layer, OCR only the ones that
need it, and apply the penalty only to those. Roughly twenty lines in
`parse_pdf`.

---

## 1. Where the module stands

| | |
|---|---|
| Backend tests passing | **281** (offline, no API key, no socket) |
| Release gates (§13) | **12 gate tests pass** — AC-1.1 (paste + upload), AC-1.2, AC-1.6, AC-1.9, the two contract gates, and AC-1.3/1.4/1.5 as regression floors |
| FRs met | **19 fully · 1 partially · 0 missing** |
| §7 API surface | **32 routes · every one reachable from a screen**, enforced at `-m gate` |
| Completion | **~90%** of the written spec, and the last 10% is not evenly spread — see §11 |

*Audited 2026-08-25 against the spec section by section, verifying in code
rather than from this file. `pytest` 281 passed · `pytest -m gate` 12 passed ·
`ruff check` clean · `tsc --noEmit` clean · `npm run build` clean ·
`research/score_golden.py` 1.000 / 1.000 / 1.000.*

> **The completion figure moved down, not up.** The 2026-08-23 pass counted
> functional requirements and got ~98%, which was true and misleading: FRs are
> not the whole spec. §11 audits what the FR table does not cover — the KPI in
> §13, the semantic tier in §6, the screens in §2.3 and §8 — and those are where
> the remaining work is. Nothing regressed; the measurement got honest.

---

## 2. Functional requirements (§4)

| ID | Requirement | State | Where |
|---|---|---|---|
| FR-1.1 | Accept PDF, DOCX, pasted text; named error otherwise | ✅ | `documents.py` |
| FR-1.2 | Immutable raw storage keyed by SHA-256 | 🟡 | `objectstore.py` — S3/R2/MinIO backend behind the contract; no bucket to point it at, and no virus scan |
| FR-1.3 | Text layer with per-word bboxes and page numbers | ✅ | `documents.py` |
| FR-1.4 | Multi-column detection + correct reading order | ✅ | `documents.detect_columns` |
| FR-1.5 | Section segmentation with per-section confidence | ✅ | lexicon + typography (font size, bold) + caps + word count |
| FR-1.6 | Entities: name, education, dates, institutions, roles | ✅ | `entities.py` |
| FR-1.7 | Every skill mention → `concept_id` or `unmapped` | 🟡 | `normalise.py` — §6.4 steps 1, 2, **3**, 5; step 4 needs an embedding service |
| FR-1.8 | Each bullet a `ResumeClaim` with a verbatim span | ✅ | `claims.extract_claims` |
| FR-1.9 | Score specificity / verifiability / ownership / recency | 🟡 | `claims.score_claim` — all four axes; sub-terms simplified (no scope/method/genericness) |
| FR-1.10 | 1–3 escalating probe questions per claim | ✅ | `claims.probes_for` |
| FR-1.11 | Confirmation UI: edit sections, bullets, skills, dates | ✅ | all four editable; claims deletable (EC-1.17) |
| FR-1.12 | Corrections persisted and treated as ground truth | ✅ | `revisions.py` |
| FR-1.13 | Red flags, all six kinds | ✅ | `claims.find_red_flags` |
| FR-1.14 | Product fully usable with no resume at all | ✅ | Skip → `/skipped`, gate-tested |
| FR-1.15 | Re-upload with a diff view | ✅ | `DiffPage.tsx` at `/resumes/:id/diff` |
| FR-1.16 | OCR fallback when the text layer is empty | ✅ | PaddleOCR installed and verified reading a real scan |
| FR-1.17 | Contact block never rendered, logged, or modelled | ✅ | separation, redaction, and an encrypted column (`crypto.py`) |
| FR-1.18 | p95 ≤ 25 s for a 2-page resume | ✅ | `parse_ms` on every row, and `GET /v1/quality` now computes the p95 against the 25 s line. Recording it was never the same as meeting it |
| FR-1.19 | Auto-STAR rewrite for weak claims, on request only | ✅ | `rewrite.py` |
| FR-1.20 | `resume.*` analytics events at every stage boundary | ✅ | `events.py` |

---

## 3. Done — backend

- ✅ `config.py` — every threshold in one file, as §6.6 demands
- ✅ `documents.py` — magic-byte intake, PDF words + bboxes, column detection,
      reading order, DOCX tables as `key: value`, page cap, OCR seam
- ✅ `safety.py` — prompt-injection filter, homoglyph folding, `security_events`
- ✅ `skills.py` — `SkillMention` with context, mapping method, confidence,
      occurrence count, and the weekly unmapped queue
- ✅ `rewrite.py` — deterministic STAR skeleton, suggestion only
- ✅ `claims.py` — six red-flag kinds, paragraph fallback, spec prominence,
      bboxes on spans, `verify_spans` enforcing AC-1.1
- ✅ `dates.py` — one definition of a date range, shared by `claims.py` and
      `entities.py`; two-digit years, open-ended ranges
- ✅ `headings.py` — the §6.3 lexicon, 163 variants, shared by the segmenter
      and the extractor. It was 49 in two drifting copies
- ✅ `golden.py` + `research/` — the golden-set harness and corpus
- ✅ `models.py` — parse lifecycle: `mime`, `page_count`, `parse_status`,
      `parser_version`, `ocr_used`, `columns`, `is_active`, `confirmed`
- ✅ `router.py` — the whole §7 API surface, bar the items deferred in §8
- ✅ Eight test files: `test_api`, `test_claims`, `test_documents`,
      `test_golden`, `test_pipeline`, `test_revisions`, `test_safety`,
      `test_skills`

Landed after the golden set and the live runs started finding things (§4b):

- ✅ One heading lexicon instead of two, 49 variants → 163, with a test
      asserting every skills heading is also an enumerating one
- ✅ `Position of Responsibility` / `Leadership` reclassified as `experience`,
      so they produce claims; hobbies and activities stay in `extras`
- ✅ Probes branch on claim type — leadership, achievement, research,
      learning, engineering — with a quoted number still outranking the family
- ✅ Inline headings (`Skills: Python, SQL`), gated on an exact lexicon hit
- ✅ `.NET` keeps its leading dot

## 4. Done — frontend

Rebuilt against the current `ResumeOut`. Typecheck and production build both
clean; verified against a live API on :8101 through the Vite proxy.

- ✅ `types.ts` / `api.ts` — the whole surface, including SSE and multipart
- ✅ `ResumeDropzone` — file + paste + first-class Skip, capability-gated
- ✅ `ParseProgress` — narrated stages, ARIA live region, slow-parse copy
- ✅ `ConfirmationEditor` — sections, bullets and skills, all editable
- ✅ `ClaimMap` + `ClaimCard` — bands, probes, "the one thing to fix first"
- ✅ `RedFlagBanner` — severity-ordered, every flag carries its answer
- ✅ `SkillChipEditor` — add/remove, hatched unmapped group preserved
- ✅ `RewriteDiff` — blanks rendered as blanks, no apply button by design
- ✅ `SourceHighlight` — click a claim, highlight its span in the document
- ✅ a11y — `j`/`k`/`Enter`/`e`, focus rings, never colour alone

Two fixes worth remembering:

- `/status` was never in the Vite proxy, so the dev server answered with
  index.html and a 200. The Dependencies page failed on JSON parsing, which
  reads as "the registry is broken" rather than "this path is not proxied".
- `types.ts` declared `raw_text`, which stopped being sent when PII isolation
  landed. The read-back screen rendered `undefined` — a blank panel, no error,
  on the one screen whose job is showing the student we read their document.

## 4b. Found by running it, not by reading it

The golden set and the live end-to-end runs each surfaced defects that no
amount of unit testing had. Listed because the pattern is the useful part: all
five were invisible from inside the module.

- **Two heading lexicons had drifted**, and the failure mode is asymmetric — in
  the section table only, the section is labelled right and every skill under it
  is invisible. One table in `headings.py` now, 49 variants → 163.
- **`Position of Responsibility` was filed under `extras`**, which is not a
  claim-bearing section. A student who led a 200-person festival got no claim,
  no probe and no score for it.
- **Probes were grounded in the bullet's nouns but not its verb**, so a
  coordination role was asked "how did you implement this project?".
- **`Skills: Python, SQL` on one line was not a heading**, so one-page resumes
  had no sections at all.
- **`.NET` lost its leading dot.** The golden metric could not see it —
  `normalise_alias` folds the dot away — but the student would have.

## 4c. The frontend caught up with the backend (2026-08-25)

Ten of thirty-one routes had **no client at all**, and four hooks that existed
were mounted by no screen. Neither half could see it: the backend suite passed,
the frontend built, and the feature did not exist.

- ✅ **Every route has a client; every hook has a screen.**
      `tests/test_contract.py` reads both halves and fails `-m gate` on either.
      It carries an explicit two-entry allowlist for the server's own aliases
      (`/resumes/ingest`, `/diff/{other}`), and a third test stops that
      allowlist becoming a parking space.
- ✅ **Three new screens** — `…/audit` (correction log + event stream),
      `…/privacy` (contact release, share grants, disclosure, retention,
      deletion), `/quality` (AC-1.7 against §13's line).
- ✅ **Dates are editable** (FR-1.11). §2.3 asks for "sections, bullets, skills,
      and dates"; three of the four had been editable since the confirmation
      pass was built. A mis-read date drives the gap flag the student is then
      told to prepare an answer for.
- ✅ **A claim can be struck** (EC-1.17). The QA script had assumed this button
      for months. The endpoint was there; the button was not.
- ✅ **`claim_type` is correctable.** The last correctable field with no control,
      and the one that decides which probe family a bullet gets.
- ✅ **Red flags and skills read from their own endpoints.** Both screens were
      re-deriving from the raw resume, so the server's severity ordering was
      discarded and the most serious flag could render third.

### Three defects found by looking at the rendered page

The pattern from §4b again — none of these was visible from inside a test.

- **`Multi-modal Learning` came out as three skills.** The PDF wrapped it at its
  own hyphen and the line break split it into `NLP`, `Multi-` and
  `modal Learning`. `extract.py` now rejoins a hyphen-wrapped word, keeping the
  hyphen; `skills.py` searches break-tolerantly so the repaired label still
  resolves its span in the unrepaired document.
- **Every risky claim got identical probes.** The subject fell back to the
  constant `"this project"` whenever nothing resolved, so six risky bullets
  produced eighteen near-identical lines. `claims.subject_of` now reads it off
  the sentence. The ladder was never the problem; the noun was.
- **Two skill sections that read as one.** "Mapped to nothing" and "never used
  in a bullet" are genuinely different questions that overlap almost completely
  on a real resume. They are two independent properties of one skill, so they
  are now two tags on one row.

## 5. Tests (§12, §13)

- ✅ **AC-1.2 [GATE]** — the product is usable end to end with no resume
- ✅ AC-1.1 extended to the file-upload path
- ✅ Date parser across the real Indian formats — 9 cases including the
      two-digit forms `Jan'24` and `2022-26`, plus the guard that keeps
      `problems 12 - 15` from becoming a career timeline
- ✅ Bullet segmentation — 9 glyph styles, wrapped bullets, paragraph fallback
- ✅ Risk-scoring monotonicity: adding a quantifier never increases risk
- ✅ Golden set harness — 20 annotated resumes across five sets, scored in CI
      as a regression floor. Section F1 1.000, skill precision 1.000, skill
      recall 1.000
- ✅ Adversarial suite — injection in visible text, homoglyphs, 10 MB of
      repeated text, and the `05_traps.json` set written to make the parser
      wrong
- ✅ Intake edge cases — `.doc`, encrypted PDF, zero-byte, oversize, 8-page CV

The one open test item is a **data** task and is tracked in §7: replacing the
synthetic corpus with real consented resumes. Until then AC-1.3, AC-1.4 and
AC-1.5 are enforced as regression floors and are **not** measured.

## 6. Done — docs

- ✅ `README.md` — rewritten against what is actually built
- ✅ `dependencies.txt` — the new packages and what their absence removes
- ✅ `pyproject.toml` — pymupdf, python-docx, python-multipart; `[ocr]` extra

## 7. Next

One thing is left that is not waiting on another module, and it is a **data**
task rather than a code one:

- ⬜ **Real resumes for the golden set.** The harness, the corpus schema, the
      scorer and the CI gates are all built and green
      ([research/README.md](../research/README.md)). What is synthetic is the
      *documents*: they were written to cover the shapes the spec names, by the
      same hand that wrote the parser, so the numbers are an optimistic
      estimate. That makes them a real regression gate and **not** the AC-1.3 /
      AC-1.4 / AC-1.5 acceptance measurement, which stays unmeasured.

      To close it: collect ~30 resumes with consent from seniors, annotate them
      in the same schema, drop them in `research/data/golden/resumes/`, and flip
      `golden.MEASURES_REAL_WORLD` to `True`. No code changes.

Everything else is waiting on another module — see §8.

---

## 8. Deferred — inter-module

Not gaps in M01. Each needs a module that is not built or not wired yet, and
each is listed here so it is not mistaken for an oversight.

| Item | Waiting on |
|---|---|
| `POST /v1/resumes/{id}/claims/{cid}/drill` | M06 Mock Interview Engine |
| `linked_repo_id` on a claim; `verifiability = 1.0` for a verified repo | M03 GitHub Analyzer |
| Live concept ontology beyond the five-entry fallback | M04 reachable on :8104 |
| Probe `expects` handed over as rubric key-points | M13 Evaluation Engine |
| Claim provenance into the evidence ledger | M19 Reports & Dashboards |
| `mapping_method="embedding"` (§6.4 step 4) | a platform embedding service |
| `mapping_method="alias_fuzzy"` (§6.4 step 3) | `rapidfuzz` + the 2,000-entry alias table |
| Async parse worker + `202 Accepted` | only worth it when a stage gets slow |

### 8b. ⬜ M01 probes vs M05 grounded items — the two specs disagree

Raised 2026-08-25. **Not a bug today; a guaranteed duplication the day M05 lands.**

Both modules generate a question from an M01 claim, and neither spec says which
one is supposed to:

| | says |
|---|---|
| M05 §5 `GroundedSource` | `kind="resume_claim"`, `source_id` = **an M1 claim id**, `source_module="M01"` — M05 takes the CLAIM and generates its own item |
| M05 §6.8 step 3 | *"Generate a grounded item on the fly (repo/resume)"* — M05 generating |
| M05 §6.2 | grounding priority puts `resume claim (M1)` second; the prompt gets *"the source artifact"* |
| **M01 `module.json` feeds** | M05 takes *"claim-grounded **probes**, the resume-specific question source"* — M05 consuming what M01 already wrote |

The first three describe M05 regenerating from the claim. The fourth describes
M05 reusing M01's probes. Both cannot be the design.

**Why M01 generating them is still right.** FR-1.10 is P0 and §6.7 is M01's own
stage, and the probes have two consumers that are not M05:

- §2.3 Screen 4, the Claim Map — *"An interviewer will ask:"*. This is the
  payoff screen and the thing students screenshot. It cannot wait on a module
  that does not exist, and Rule 2 forbids it going blank when M05 is down.
- M13, via `expects` — §6.7: *"the key points a good answer covers, which
  becomes the rubric key-points when this question is used in a real round"*.

**What is actually different between the two artifacts:**

| | M01 probe | M05 grounded item |
|---|---|---|
| purpose | diagnosis, shown to the student | instrument, asked in a round |
| shape | question + `expects` + rationale | full package incl. reference answer |
| gates | none (nothing is scored on it) | G1/G4/G5 inline, all five for bank items |
| calibration | none | `theta_eligible=False`, consent_id, `grounded_for_candidate` |
| lifetime | stored with the resume | ephemeral, deleted with the candidate |

So the artifacts are genuinely different. **The generation CALL is not** — same
source, same model, near-identical output, and the day M05 ships there will be
two of them.

**Recommended resolution — M05 wraps rather than regenerates.** M01's probe
becomes M05's candidate stem; M05 adds the package, the gates, the consent
binding and `theta_eligible=False`. That is `module.json`'s version, it makes
one generation instead of two, and it means the student is asked in the round
exactly what the Claim Map warned them they would be asked — which is the whole
emotional arc §2.2 is built on.

Needs M05's owner to agree, and M05 §5's `GroundedSource` to change from
"an M1 claim id" to an M1 probe id, or to carry both.

## 9. Decisions (§15)

**Settled, and the code holds to them.** Both are the kind of decision that
gets quietly reversed by a well-meaning change, so each has a note here and a
comment at the site.

- ✅ **No ATS-style score, anywhere.** The Claim Map summary is a count —
      "12 claims found · 4 look risky" — never a mark. If the placement cell
      insists on one it goes behind a separate tab, out of the main flow.
- ✅ **A STAR rewrite is suggested, never applied.** `POST .../rewrite` returns
      a shape with the student's own facts left as blanks and changes nothing on
      the server. A resume they did not write is one they cannot defend.

**Still open — each needs someone outside this repo:**

- 🟡 Raw PDF retention period. **Mechanism built and now visible, decision open.**
      `retention.py` carries the period, the rationale, and `decided: false`;
      `GET /v1/resumes/{id}/disclosure` reports when an artifact expires and
      that expiry is a tombstone rather than a silent delete. Since 2026-08-25
      the `…/privacy` screen renders all of it, including the pending sign-off —
      a student asking "how long do you keep my resume?" gets an answer that is
      not "read the source". The ethics committee still has to choose the
      number (§48).
- 🟡 Whether a placement officer can see an individual student's risky claims.
      **Mechanism built and now operable, decision open.**
      `ShareGrant` — a grant is to somebody named, it expires, and revoking
      leaves a trace. It fails closed: a viewer with no grant gets
      `aggregate_only`. The `…/privacy` screen can now grant, revoke, and show
      what a named viewer would see; it says plainly that with no auth on the
      platform this answers the question rather than enforcing it. The cell
      still has to confirm that is the policy.
- ⬜ Who reviews the unmapped-skill queue, and how often. Proposal: E3,
      weekly, fifteen minutes. The queue is built and served at
      `GET /v1/resumes/{id}/skills`; only the process is undecided.

---

## 10. The real backlog — reachable now

Ordered by what a student would notice first. Nothing here is blocked on
another module; §8 is the list that is.

### Would be visible to a student

- ✅ **Diff screen (FR-1.15).** `DiffPage.tsx`, reachable from the claim map.
      Re-banded claims lead, because "you added a number and this moved out of
      risky" is the most useful thing a re-upload can say.
- ✅ **Editable dates (FR-1.11).** `PATCH /v1/resumes/{id}/dates/{index}`. The
      typed value goes through the same parser that read the document, and one
      that will not parse is refused rather than stored.
- ✅ **Delete a claim (EC-1.17).** `DELETE /v1/resumes/{id}/claims/{cid}`,
      routed through the correction log so AC-1.7 counts it.
- ✅ **Visible focus rings (§8.4).** One `:focus-visible` rule in `theme.css`,
      plus a skip link and a `prefers-reduced-motion` block. Declared once
      because the failure mode is one component being forgotten.
- ✅ **"One thing to fix first" sticky on mobile (§8.3).** Sticky at the
      bottom below `lg`, static in the flow above it.
- ✅ **§8.2 partial states.** "read 3 of 4 clearly",
      "4 of 12 mapped to a concept" — a bare count reads as completeness even
      when a third of the document was unreadable.

### Parse quality

- ✅ **Skill matching step 3 (§6.4).** `rapidfuzz` is installed and wired;
      `normalise.resolve` runs exact → short-token guard → fuzzy, with a
      length-ratio and first-character guard so "Java" never becomes
      "JavaScript". Verified: `Tensorflow 2.x`, `Pythonn`, `Kubernets` and
      `Dynamic Programing` all resolve; `R` and `C` stop at exact.
      **What is still short is the TABLE, not the ladder** — 271 aliases
      against the spec's ~2,000, and no versioned `aliases.yaml`. See §10
      "Parse quality, still open" below.
- ✅ **Typography tier for headings (§6.3).** `documents.py` records
      `line_styles` from font size and weight (`_line_style`, `_body_size`,
      `_type_by_position`), so a heading in a font the lexicon has never seen
      is still scored on how it is SET rather than only on what it says.
- ✅ **PDF table extraction (§6.2.4).** `pdfplumber` reads ruled regions and emits
      `key: value`; appended rather than spliced, so no committed offset moves.
- ✅ **`Spring 2025`, `2 months` (§3.2.3).** Seasons resolve to a month;
      durations are reported as a LENGTH and never as a range, because a
      duration with an invented start date manufactures a timeline gap that is
      not on the resume.
- ✅ **Language detection (EC-1.6).** Script check first, `langdetect` second.
      Flagged and never blocked — a Hindi resume parsed to almost nothing and
      was indistinguishable from an empty one.
- ✅ **An OCR engine.** PaddleOCR + paddlepaddle, in the venv,
      verified reading a scanned page end to end. oneDNN is disabled — Paddle
      raises `ConvertPirAttribute2RuntimeAttribute` on some CPUs and the
      fallback kernels give the same text. An engine that is installed and does
      not RUN now degrades to the same named error as a missing one.

### Operational honesty

- ✅ **`parse_status="failed"` and `parse_error` are now written.** A refused
      upload persists an inactive row saying what was tried and why it stopped,
      so §10's "Everything fails → `parse_status=failed`" is true and
      "which file types fail for real students" is answerable.
- ✅ **PII at rest (FR-1.17, §6.4).** `crypto.py` — a Fernet-encrypted contact
      column keyed on `M01_PII_KEY`, reported at `GET /v1/quality`. The
      restricted database role §6.4 also asks for is a deployment concern and
      is still open.
- 🟡 **Object storage (FR-1.2, §6.1).** `objectstore.py` speaks S3/R2/MinIO and
      `storage.put` uses it when `M01_OBJECT_STORE` is set, falling back to the
      local tree otherwise. What is left needs a bucket to point at, and the
      ClamAV pass — reported at `GET /v1/quality` as `virus_scan: false` rather
      than stubbed, because a `scanned: true` on a file nothing scanned is the
      flag somebody later trusts.
- ✅ **AC-1.7 is reported.** `GET /v1/quality` answers "is the edit rate over
      40%?" directly, and breaks corrections down by target. It also reports
      `failures_by_code`, which is the question the dead `parse_error` column
      could not answer.
- ✅ **Manual QA script (§12).** [QA.md](../QA.md) — nine steps plus a copy
      check, each one a thing a test cannot decide for you.
- ✅ **AC-1.6 is reported.** `GET /v1/quality` carries a `timing` block: p50,
      p95, slowest, and §13's 25 s line evaluated as `over_budget`. OCR reads
      are excluded per the criterion's own wording and counted separately, so
      the exclusion is visible rather than a filter nobody can check.

---

## 11. What is actually left — audited against the spec, 2026-08-25

Every line below was checked against the code, not against this file. Two
entries in §10 carried a ✅ and a body describing something unbuilt; both are
corrected in place. Ordered by what it would cost a student.

### 11.1 The KPI the module is measured on — affordance landed 2026-08-25

**AC-1.8 — *"% of users who run ≥1 defend drill from the Claim Map ≥ 35% (this
is the module's real KPI)"*.** §13 says it outright: *"The KPI to actually watch
is AC-1.8. Parsing accuracy is a means; a student running a drill because they
saw a risky claim is the outcome."*

There is no drill. Not the endpoint §7 lists
(`POST /v1/resumes/{id}/claims/{cid}/drill`), not the button §2.3 Screen 4 puts
on every risky card (`[ Practise defending this (2 min) ]`), not the `Enter`
binding §8.3 asks for. §2.4's quit-trigger table answers *"nothing to do next"*
with *"every risky claim has a 2-minute drill button"* — the counter to its last
quit trigger is the piece that is missing.

The SESSION is blocked on M06 and §8 files it there correctly. The AFFORDANCE
was not, and is now built — a button that says what would happen and which
module it is waiting on is exactly Rule 2. Before it, the Claim Map ended in a
cul-de-sac and the KPI had no numerator at all: not "below target",
unmeasurable.

- ✅ **A drill affordance on every risky claim.** `POST …/claims/{cid}/drill`
      exists and always answers: M06's session when M06 is up, and otherwise
      the questions plus the sentence naming the module. `DrillPanel` renders
      both, "Practise defending this" is the primary action on every card, and
      `Enter` opens it — which is what §8.3 asked for all along.
- ⬜ **The scored session itself.** Needs M06, declared in `module.json` as an
      optional upstream. AC-1.8 can now be COUNTED; whether it clears 35% is a
      question about M06.

### 11.2 The semantic tier — probes landed 2026-08-25, the rest is open

The spec's pipeline is deterministic-first with an LLM layer on top. **§6.7 now
exists**; §6.3.3, §6.5.3 and §6.4 step 4 still do not.

- ✅ **§6.7 probe generation.** `llm.py` + `probes.py`, on `ai_core.models`
      (Platform_Core v0.8.0 — one roster naming every model all nineteen
      modules call). `openai/gpt-oss-120b` via Groq, four claims concurrently,
      ~4.9 s for a five-bullet resume inside FR-1.18's 25 s. The deterministic
      ladder is the FLOOR: no key, a timeout, a 429, malformed JSON or a probe
      that just restates the bullet all leave the student with the template
      questions, and `generated_by` says which wrote each one. 15 tests, none
      opening a socket.

Still absent, and the rest of this section stands: This is a deliberate and well-argued position — `claims.py`
opens with three reasons and they are good ones — but it is not what §6
describes, and the difference is invisible from outside the code.

| Spec | State | What it costs |
|---|---|---|
| §6.3.3 LLM segmentation when heuristic confidence < 0.6 | ⬜ absent | A resume whose headings the lexicon misses gets no second opinion |
| §6.5.3 LLM claim extraction, one call per section | ⬜ absent | `subject_concepts` are regex hits, not read comprehension; no paraphrase. **This is what would fix the quantifier gap below** |
| §6.7 LLM probe ladder | ✅ **done** | — |
| §6.4 step 4 embedding NN (cosine ≥ 0.86) | ⬜ absent | Needs a platform embedding service |

- ⬜ **The quantifier regex misses most real ML numbers.** `macro-F1: 0.897`,
      `F1 of 0.897` and `72-hour` all extract as nothing, so a bullet whose
      headline IS a number is told "there is no number in it" and its depth-2
      probe falls back to the generic trade-off question. Bare decimals and
      hyphenated units. Deterministic fix, and the cheapest one left.
- ⬜ **§6.5.3 would subsume it.** A model reading the bullet finds the number a
      regex cannot enumerate. Worth deciding whether to widen the regex, do
      §6.5.3, or both — the regex is the floor either way.

### 11.3 Parse quality, still open

- ⬜ **The alias table is 271 entries; the spec seeds ~2,000** in a versioned
      `packages/knowledge/ontology/aliases.yaml`. The ladder that consumes it is
      finished and verified. This is the single biggest remaining lever on skill
      recall against real resumes, and it is data entry rather than engineering.
- ⬜ **`has_scope`, `has_method_detail`, `genericness` (§6.6).** Specificity is
      three terms against the spec's five. The missing one that matters is
      `genericness` — a cosine distance from a corpus of generic resume phrases,
      which is what would let "Worked on various modules" score differently from
      a real bullet of the same length.
- ⬜ **`verifiability` sub-terms (§6.6).** The spec distinguishes a verified repo
      (1.00), a URL (0.70), a publication (0.60) and a named organisation
      (0.40). The code has link / quantifier / concept. Publications and named
      orgs are detectable today; `linked_repo_verified` needs M03.
- ⬜ **Claim embeddings.** §5's SQL declares `embedding VECTOR(1024)` with an
      HNSW index, for dedup and M05 retrieval. Nothing writes one — so §3.2.4's
      *"keep both spans linked to one claim group"* is a red flag rather than a
      grouping, and M05 cannot retrieve claims by similarity.

### 11.4 Screens thinner than the spec draws them

- ⬜ **`PdfHighlightViewer` (§8.1, §8.3).** *"Click a claim → the original PDF
      scrolls and highlights that exact bullet… a 4-hour feature that buys
      enormous trust."*  `SourceHighlight` highlights the redacted TEXT, which
      carries the same guarantee and none of the recognition. The `bbox` is
      extracted, stored on every span, and rendered by nothing.
- ⬜ **Screen 3 is four flat lists, not the project tree §2.3 draws.** The spec
      shows each project as a card with its title, its dates, its tech chips
      (`Tech: TensorFlow, OpenCV, Flask [+ add tech]`) and its own bullets.
      Sections, bullets, skills and dates are each editable — but separately, so
      a student fixing one mis-read project edits it in three places and never
      sees it as one thing.
- ⬜ **The per-section "I couldn't read this one" affordance (§2.3, §8.2).**
      *"⚠ I couldn't read one section clearly (page 2, bottom). [Show me]
      [It's not important]"*, and §8.2's ConfirmationEditor error column asks for
      per-section retry. `parse_notes` says it once at the top of the page
      instead, so it cannot be dismissed or jumped to.
- ⬜ **Camera-scan path (§8.4).** *"Many students only have a printed resume.
      Scan → OCR → same pipeline. Worth building; it removes a real blocker."*
      OCR is installed and works end to end; the dropzone has no capture path.

### 11.5 Operational

- ⬜ **ClamAV (§6.1).** Reported honestly as `virus_scan: false` rather than
      stubbed. Still a gap, and it sits on the path a stranger's file takes.
- 🟡 **An object-storage bucket (FR-1.2).** The code speaks S3/R2/MinIO; there
      is nothing to point it at, and `retention_class=transcripts_evaluations`
      is set nowhere.
- ⬜ **The restricted database role for the contact table (§6.4).** The column is
      encrypted; the role that should be the second lock is a deployment concern
      nobody owns yet.
- ⬜ **AC-1.9 as a CI scan.** *"Zero PII in any model call — verified by a CI
      scan of trace payloads."*  There is a unit test asserting redaction and no
      scan of trace payloads, because there are no traces and no model calls. It
      becomes real the day §11.2 does.
- ⬜ **Async worker and `202 Accepted` (§7, §10).** §7 documents the upload as
      returning 202; it returns 201 with a finished parse. §10's *"worker crashes
      mid-parse → idempotency key resumes from the last completed stage"* has
      nothing to resume. Correctly deferred while parsing is fast — but §7
      currently describes an API that does not exist, and `/stream` replays a
      finished parse rather than narrating a live one. Both are honest in the
      code and wrong in the spec.

### 11.6 The one that is not code

- ⬜ **Real resumes for the golden set.** Unchanged, and still the largest single
      item. The corpus is synthetic, written by the same hand as the parser, so
      AC-1.3 / AC-1.4 / AC-1.5 read 1.000 as regression floors and are **not**
      the acceptance measurement they are labelled as. Everything else in §11 is
      judgement about a design; this is the only entry where a number on the
      release checklist is not measuring what it says it measures.

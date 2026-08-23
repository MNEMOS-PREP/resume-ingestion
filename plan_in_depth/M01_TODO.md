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

## 1. Where the module stands

| | |
|---|---|
| Backend tests passing | **233** (offline, no API key, no socket) |
| Release gates (§13) | **10 gate tests pass** — AC-1.1 (paste + upload), AC-1.2, AC-1.6, AC-1.9, and AC-1.3/1.4/1.5 as regression floors |
| FRs met | **19 fully · 1 partially · 0 missing** |
| Completion | **~98%** of the written spec. What remains needs another module (§8), real consented resumes (§7), an S3 bucket, or a human decision (§9) |

*Audited 2026-08-23 against the spec section by section, verifying in code
rather than from this file — which was over-marked on eight FRs before that
pass. `pytest` 170 passed · `pytest -m gate` 10 passed ·
`ruff check` clean · `tsc --noEmit` clean · `npm run build` clean ·
`research/score_golden.py` 1.000 / 1.000 / 1.000.*

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
| FR-1.18 | p95 ≤ 25 s for a 2-page resume | ✅ | `parse_ms` on every row |
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

- 🟡 Raw PDF retention period. **Mechanism built, decision open.**
      `retention.py` carries the period, the rationale, and `decided: false`;
      `GET /v1/resumes/{id}/disclosure` reports when an artifact expires and
      that expiry is a tombstone rather than a silent delete. The ethics
      committee still has to choose the number (§48).
- 🟡 Whether a placement officer can see an individual student's risky claims.
      **Mechanism built, decision open.**
      `ShareGrant` — a grant is to somebody named, it expires, and revoking
      leaves a trace. It fails closed: a viewer with no grant gets
      `aggregate_only`. The cell still has to confirm that is the policy.
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

- ✅ **Skill matching step 3 (§6.4).** Only exact-match and the
      short-token guard are built. `rapidfuzz` is not installed and there is no
      `aliases.yaml`; the spec wants ~2,000 seeded entries. This is the single
      biggest lever on skill recall against real resumes.
- ✅ **Typography tier for headings (§6.3).** The spec scores a line on font
      size z-score and bold as well as caps and lexicon. `documents.py` extracts
      words but not font attributes, so a heading in a font the lexicon has
      never seen is invisible.
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

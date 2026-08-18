/**
 * Paste a resume.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2 (the journey), FR-1.1
 *
 * The spec accepts PDF, DOCX and pasted text, and calls the paste path "the
 * always-works fallback". It is the only one with a backend, so it is the only
 * one here — and the missing two are named rather than rendered as a disabled
 * upload box, because a control that looks live and does nothing reads as a
 * broken product rather than an unfinished one.
 *
 * There is no progress stream either. §2.3's Screen 2 is a stage-by-stage SSE
 * feed — segment, extract, score — and this ingest is one synchronous call that
 * runs a regex. A fake progress bar over a 30ms request would be theatre.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCandidateResumes, useIngestResume } from "../api";
import { useCandidateId } from "./candidate-hook";
import { Btn, ErrorNote, Panel, Section, SkeletonRows, TextArea } from "../ui/primitives";

const SAMPLE = `PRIYA SHARMA · B.Tech CSE, 2026 · 8.1 CGPA

PROJECTS
· Built a route planner in Python using dynamic programming; cut average
  query time from 380ms to 45ms on a 12k-node graph.
· Implemented a hash map from scratch to compare open addressing against
  chaining for a data structures course project.

SKILLS
Python, SQL, recursion, Javascript, React, Docker`;

export function IngestPage() {
  const navigate = useNavigate();
  const candidateId = useCandidateId();
  const ingest = useIngestResume();
  const existing = useCandidateResumes(candidateId);

  const [text, setText] = useState("");
  const canSubmit = text.trim().length > 0 && !ingest.isPending;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    ingest.mutate(
      { candidate_id: candidateId, raw_text: text },
      { onSuccess: (resume) => navigate(`/resumes/${resume.id}`) },
    );
  }

  return (
    <>
      <header className="mb-8">
        <h1 className="text-display font-semibold text-ink">Your resume, read back</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          Paste the text and we map the skills you mention onto the platform&rsquo;s concept
          ontology &mdash; which is what lets everything downstream ask you about them. Every id
          says whether the ontology confirmed it.
        </p>
      </header>

      <Section label="Paste your resume">
        <Panel className="p-5">
          <form onSubmit={submit} className="space-y-4">
            <TextArea
              label="Resume text"
              hint="Plain text. Copy straight out of your PDF — layout does not matter yet."
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={14}
              placeholder={SAMPLE}
              required
            />

            {ingest.isError && (
              <ErrorNote>
                The ingest failed. Check that the API is up on :8101 &mdash;{" "}
                {ingest.error instanceof Error ? ingest.error.message : "unknown error"}
              </ErrorNote>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Btn type="submit" variant="primary" disabled={!canSubmit}>
                {ingest.isPending ? "Reading it…" : "Read my resume"}
              </Btn>
              <Btn type="button" variant="ghost" size="sm" onClick={() => setText(SAMPLE)}>
                Use a sample resume
              </Btn>
            </div>
          </form>
        </Panel>

        <p className="mt-2.5 text-xs text-ink-faint">
          PDF and DOCX upload (FR-1.1), OCR fallback (FR-1.16) and multi-column reading order
          (FR-1.4) are not built. A scanned or two-column resume would yield nothing here, and
          would do it silently &mdash; which is why the upload control is absent rather than
          disabled.
        </p>
      </Section>

      <Section label="Already ingested" meta={`candidate ${candidateId.slice(0, 8)}`}>
        {existing.isLoading && <SkeletonRows rows={2} />}
        {existing.data && existing.data.length === 0 && (
          <Panel tone="sunken" className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              Nothing yet for this candidate. Paste something above, or run{" "}
              <code className="provenance">Backend/.venv/Scripts/python seed.py</code> for two
              seeded resumes.
            </p>
          </Panel>
        )}
        {existing.data && existing.data.length > 0 && (
          <Panel className="px-4 py-1">
            <div className="divide-y divide-line">
              {existing.data.map((resume) => (
                <button
                  key={resume.id}
                  type="button"
                  onClick={() => navigate(`/resumes/${resume.id}`)}
                  className="flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5 text-left hover:text-brand"
                >
                  <span className="truncate text-sm text-ink">
                    {resume.parsed_skills.join(" · ") || "no skills matched"}
                  </span>
                  <span className="provenance shrink-0">{resume.id.slice(0, 8)}</span>
                </button>
              ))}
            </div>
          </Panel>
        )}
      </Section>
    </>
  );
}

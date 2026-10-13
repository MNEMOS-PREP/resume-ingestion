/**
 * Screens 1 and 2, and the route back to a resume already read.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2.3, FR-1.1, FR-1.14
 *
 * ── The arc this page is responsible for ────────────────────────────────────
 *
 *   upload / paste  →  narrated progress  →  the confirmation pass
 *
 * §2.3 is explicit that the middle step is where products lose people, and
 * equally explicit that the escape hatch stays open the whole way: *"The Skip
 * escape hatch stays available the whole time. A student who wants to start a
 * mock right now can, and we attach the resume when it lands."*
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Icon, PageHeader } from "@ai/core";

import { useCandidateResumes, useCapabilities, useIngestResume, useLibrary, useUploadResume } from "../api";
import type { Resume } from "../types";
import { BANDS } from "./bands";
import { useCandidateId } from "./candidate-hook";
import { DeleteResumeDialog } from "./DeleteResumeDialog";
import { ParseProgress } from "./ParseProgress";
import { ResumeDropzone } from "./ResumeDropzone";
import { Btn, Panel, Section, SkeletonRows } from "../ui/primitives";

export function IngestPage() {
  const navigate = useNavigate();
  const candidateId = useCandidateId();
  const capabilities = useCapabilities();
  const ingest = useIngestResume();
  const upload = useUploadResume();
  const existing = useCandidateResumes(candidateId);
  const library = useLibrary(candidateId);

  const [parsing, setParsing] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Resume | null>(null);
  const busy = ingest.isPending || upload.isPending;

  function go(resumeId: string) {
    setParsing(resumeId);
  }

  if (parsing) {
    return (
      <ParseProgress
        resumeId={parsing}
        onDone={() => navigate(`/resumes/${parsing}`)}
        onSkip={() => navigate("/skipped")}
      />
    );
  }

  /*
    A student who already has resumes came back for one of them, or to upload
    a new version. The page used to greet them as a first-timer — "Let's start
    with your resume", a dropzone first, a "Skip for now" under it — above the
    list they came for (2026-10-13). Now their list comes first, the upload is
    a new version, and there is nothing to skip.
  */
  const returning = (existing.data?.length ?? 0) > 0;
  const dropzone = (
    <Section label={returning ? "Upload a new version" : "Your resume"}>
      <ResumeDropzone
        capabilities={capabilities.data}
        busy={busy}
        error={upload.error ?? ingest.error}
        onFile={(file) =>
          upload.mutate({ candidateId, file }, { onSuccess: (resume) => go(resume.id) })
        }
        onText={(text) =>
          ingest.mutate(
            { candidate_id: candidateId, raw_text: text },
            { onSuccess: (resume) => go(resume.id) },
          )
        }
        onSkip={returning ? undefined : () => navigate("/skipped")}
      />
    </Section>
  );

  return (
    <>
      <div className="mb-8">
        <PageHeader
          title={returning ? "Your resumes" : "Let’s start with your resume"}
          subtitle={
            returning
              ? "Open one to see the lines an interviewer would push on, or upload a new version."
              : "We find every line an interviewer could ask you to defend — and which ones you can't explain yet."
          }
          how={
            <p>
              Each line is read for what it claims and how hard it would be to back up in an
              interview. You see the exact words each finding came from, and nothing is shared
              unless you choose to share it.
            </p>
          }
        />
      </div>

      {!returning && dropzone}

      <Section label="Your resumes">
        {existing.isLoading && <SkeletonRows rows={2} />}
        {existing.data && existing.data.length === 0 && (
          <Panel tone="sunken" className="px-4 py-3">
            <p className="text-sm text-ink-soft">Nothing yet — add your resume above.</p>
          </Panel>
        )}
        {existing.data && existing.data.length > 0 && (
          <Panel className="px-4 py-1">
            <div className="divide-y divide-line">
              {existing.data.map((resume) => {
                const risky = resume.claims.filter(
                  (claim) => claim.risk_band === "risky",
                ).length;
                return (
                  <div key={resume.id} className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        navigate(resume.confirmed ? `/resumes/${resume.id}/review` : `/resumes/${resume.id}`)
                      }
                      className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5 text-left hover:text-brand"
                    >
                      <span className="truncate text-sm text-ink">
                        {resume.filename ?? "Pasted text"}
                        <span className="ml-2 text-ink-soft" data-numeric>
                          {resume.claims.length} line
                          {resume.claims.length === 1 ? "" : "s"} to defend
                          {risky > 0 && (
                            <>
                              {" · "}
                              <span aria-hidden>{BANDS.risky.icon}</span> {risky} risky
                            </>
                          )}
                        </span>
                      </span>
                      <span className="shrink-0 text-xs text-ink-faint">
                        {!resume.is_active && "older version · "}
                        {resume.confirmed ? "checked by you" : "not checked yet"}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setRemoving(resume)}
                      aria-label={`Remove ${resume.filename ?? "this pasted resume"}`}
                      title="Remove this resume"
                      className="grid size-8 shrink-0 place-items-center rounded-md text-ink-faint hover:bg-surface-sunken hover:text-contested"
                    >
                      <Icon name="trash" size={16} />
                    </button>
                  </div>
                );
              })}
            </div>
          </Panel>
        )}
      </Section>

      {returning && dropzone}

      {/* The library outlives every resume above, so it is offered beside them
          rather than inside any one of them. */}
      {library.data && library.data.items.length > 0 && (
        <Section label="Your library">
          <Link to="/resume/library" className="block">
            <Panel className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 hover:border-line-strong">
              <span className="text-sm text-ink">
                Everything you've had on a resume, kept
                <span className="ml-2 text-ink-soft" data-numeric>
                  {librarySummary(library.data.items)}
                </span>
              </span>
              <span className="text-sm font-medium text-brand">Open · build a new resume →</span>
            </Panel>
          </Link>
        </Section>
      )}

      <DeleteResumeDialog resume={removing} onClose={() => setRemoving(null)} />
    </>
  );
}

function librarySummary(items: { kind: string }[]): string {
  const count = (...kinds: string[]) => items.filter((item) => kinds.includes(item.kind)).length;
  const parts = [
    [count("experience", "project"), "project and job line", "project and job lines"],
    [count("achievement", "certification"), "achievement or certification", "achievements & certifications"],
    [count("skill"), "skill", "skills"],
  ] as const;
  return parts
    .filter(([n]) => n > 0)
    .map(([n, one, many]) => `${n} ${n === 1 ? one : many}`)
    .join(" · ");
}

/**
 * FR-1.14 — where Skip lands.
 *
 * *"Allow the entire product to be used with no resume at all."*  A P0, and the
 * requirement most easily broken by accident, because every later feature
 * assumes a resume exists. This page is the proof that the path is real: it is
 * a destination with something on it, not a dead end with a back button.
 */
export function SkippedPage() {
  return (
    <>
      <header className="mb-8">
        <h1 className="text-display font-semibold text-ink">No resume, no problem</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          Everything except the resume-specific questions works without one. You can add a resume
          whenever you like and the questions get sharper &mdash; but nothing is blocked on it.
        </p>
      </header>

      <Section label="What still works">
        <Panel className="px-4 py-3.5">
          <ul className="space-y-2 text-sm text-ink-soft">
            <li>
              <span className="font-medium text-ink">Practice interviews</span> from a job
              description, or on general topics.
            </li>
            <li>
              <span className="font-medium text-ink">Coding and aptitude practice</span>, which
              never depended on a resume.
            </li>
            <li>
              <span className="font-medium text-ink">Writing your first project line</span> — describe
              one project out loud, and we write the bullet with you rather than for you.
            </li>
          </ul>
          <p className="mt-3 text-xs text-ink-faint">
            Those live in other modules and are not wired up from here yet. What this page
            guarantees today is that skipping is a real path rather than a dead end.
          </p>
        </Panel>
      </Section>

      <div className="flex gap-3">
        <Link to="/resume">
          <Btn type="button" variant="secondary">
            Add a resume after all
          </Btn>
        </Link>
      </div>
    </>
  );
}

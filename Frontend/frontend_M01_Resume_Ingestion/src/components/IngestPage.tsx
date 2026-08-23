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

import { useCandidateResumes, useCapabilities, useIngestResume, useUploadResume } from "../api";
import { BANDS } from "./bands";
import { useCandidateId } from "./candidate-hook";
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

  const [parsing, setParsing] = useState<string | null>(null);
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

  return (
    <>
      <header className="mb-8">
        <h1 className="text-display font-semibold text-ink">
          Let&rsquo;s start with your resume
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          We turn it into the claims you would have to defend in an interview &mdash; and show you
          which lines you cannot actually explain yet, before someone else finds out.
        </p>
      </header>

      <Section label="Your resume">
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
          onSkip={() => navigate("/skipped")}
        />
      </Section>

      <Section label="Already read" meta={`candidate ${candidateId.slice(0, 8)}`}>
        {existing.isLoading && <SkeletonRows rows={2} />}
        {existing.data && existing.data.length === 0 && (
          <Panel tone="sunken" className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              Nothing yet for this candidate. Add something above, or run{" "}
              <code className="provenance">Backend/.venv/Scripts/python seed.py</code> for two
              seeded resumes.
            </p>
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
                  <button
                    key={resume.id}
                    type="button"
                    onClick={() => navigate(`/resumes/${resume.id}`)}
                    className="flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5 text-left hover:text-brand"
                  >
                    <span className="truncate text-sm text-ink">
                      {resume.filename ?? "Pasted text"}
                      <span className="ml-2 text-ink-soft" data-numeric>
                        {resume.claims.length} claim
                        {resume.claims.length === 1 ? "" : "s"}
                        {risky > 0 && (
                          <>
                            {" · "}
                            <span aria-hidden>{BANDS.risky.icon}</span> {risky} risky
                          </>
                        )}
                      </span>
                    </span>
                    <span className="provenance shrink-0">
                      {!resume.is_active && "superseded · "}
                      {resume.confirmed ? "confirmed" : "unconfirmed"}
                    </span>
                  </button>
                );
              })}
            </div>
          </Panel>
        )}
      </Section>
    </>
  );
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
              <span className="font-medium text-ink">Building your first claim</span> — describe
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
        <Link to="/">
          <Btn type="button" variant="secondary">
            Add a resume after all
          </Btn>
        </Link>
      </div>
    </>
  );
}

/**
 * "Do you have a job in mind for this?" — the step after a resume is read.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2 (the flow), M02 FR-2.15
 *
 * A resume on its own answers "what have I claimed". A resume against a POSTING
 * answers "will this get me in", and that is the question a student came with.
 * Until now the two lived in separate apps with no path between them, so
 * finishing an ingest left you on a claim map with nowhere to go.
 *
 * ── Why this asks instead of assuming ───────────────────────────────────────
 *
 * FR-1.14 is a P0: *"allow the entire product to be used with no resume at
 * all"*, and the same principle runs the other way. A student who uploaded a
 * resume to fix their resume should not be pushed into a job-matching flow they
 * did not ask for. So this is a question with a real second answer, and the
 * second answer keeps everything they already have.
 *
 * ── What it cannot offer, and does not pretend to ───────────────────────────
 *
 * There is no "pick one of your saved job descriptions" list here, because
 * there is no such list to read. M02 caches a parse by CONTENT HASH and shares
 * it across every student who pastes the same posting (FR-2.12) — deliberately,
 * since a posting is the company's and not the student's. A consequence is that
 * M02 cannot say "your JDs", so neither can this. Offering a picker that quietly
 * listed everyone's postings would be worse than offering nothing.
 */

import { Link, useParams } from "react-router-dom";

import { useResume } from "../api";
import { useCandidateId } from "./candidate-hook";
import { m02Link } from "../links";
import { Empty, Panel, Section, SkeletonRows } from "../ui/primitives";

export function TargetJobPage() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const candidateId = useCandidateId();
  const resume = useResume(resumeId);

  if (resume.isLoading) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8 md:px-8">
        <SkeletonRows rows={5} />
      </div>
    );
  }

  if (resume.isError || !resume.data) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8 md:px-8">
        <Empty title="No such resume">
          The id in the URL does not match a stored resume.
          <div className="mt-3">
            <Link
              to="/resume"
              className="text-sm font-medium text-brand hover:text-brand-hover"
            >
              Upload one &rarr;
            </Link>
          </div>
        </Empty>
      </div>
    );
  }

  const data = resume.data;
  const skillCount = data.parsed_skills.length;
  const grade = (data.entities?.education ?? []).find(
    (entry: { grade?: string | null }) => entry.grade,
  )?.grade;

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8 md:px-8">
      <header className="mb-8">
        <p className="rule-label">Resume read</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">
          Is there a job you are aiming this at?
        </h1>
        <p className="mt-2 text-sm text-ink-soft">
          If you paste the posting, we can tell you whether you clear its
          eligibility bar, which of its requirements your resume actually
          mentions, and how a mock interview for it should spend its time. If
          not, everything below is still yours to work on.
        </p>
      </header>

      <Section label="What we would send across">
        <Panel className="px-4 py-3">
          <dl className="space-y-2.5 text-sm">
            <div className="flex flex-wrap justify-between gap-x-4">
              <dt className="text-ink-soft">Skills we read</dt>
              <dd className="text-ink">
                {skillCount} {skillCount === 1 ? "skill" : "skills"}
                {data.unresolved_skills.length > 0 && (
                  <span className="provenance ml-2">
                    {data.unresolved_skills.length} unmapped
                  </span>
                )}
              </dd>
            </div>
            <div className="flex flex-wrap justify-between gap-x-4">
              <dt className="text-ink-soft">Grade on your resume</dt>
              <dd className="text-ink">
                {grade ? (
                  <span>
                    {grade}
                    <span className="provenance ml-2">exactly as written</span>
                  </span>
                ) : (
                  <span className="text-ink-faint">none we could read</span>
                )}
              </dd>
            </div>
            <div className="flex flex-wrap justify-between gap-x-4">
              <dt className="text-ink-soft">Read-back</dt>
              <dd
                className={data.confirmed ? "text-confirmed" : "text-ink-faint"}
              >
                {data.confirmed ? "you have confirmed it" : "not confirmed yet"}
              </dd>
            </div>
          </dl>
          {!data.confirmed && (
            <p className="mt-3 border-t border-line pt-3 text-xs text-ink-soft">
              Worth confirming first. Anything a job match tells you is computed
              from what we extracted, not from what you verified &mdash; if we
              misread a skill or a grade, the match inherits it and you have no
              way to tell.{" "}
              <Link
                to={`/resumes/${resumeId}`}
                className="font-medium text-brand hover:text-brand-hover"
              >
                Check the read-back
              </Link>
              .
            </p>
          )}
          {!grade && (
            <p className="mt-3 border-t border-line pt-3 text-xs text-ink-soft">
              Without a grade we cannot check any CGPA cutoff &mdash; the match
              will say &ldquo;unknown&rdquo; rather than guessing, which is
              honest and not much use. If your resume states one and we missed
              it, that is worth fixing here first.
            </p>
          )}
        </Panel>
      </Section>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <a
          href={m02Link("/", candidateId)}
          className="rounded-md bg-brand px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-hover"
        >
          Yes &mdash; paste the job description
        </a>
        <Link
          to={`/resumes/${resumeId}`}
          className="text-sm text-ink-soft hover:text-ink"
        >
          No &mdash; carry on with my resume
        </Link>
      </div>

      <p className="mt-4 text-xs text-ink-faint">
        The job description opens in the JD parser, which is a different screen
        on a different port. Your candidate id travels with the link so the
        analysis is about you and not about whoever that browser last looked at
        &mdash; there is no shared sign-in yet, and this is what stands in for
        one.
      </p>
    </div>
  );
}

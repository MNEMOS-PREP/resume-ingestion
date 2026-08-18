/**
 * One resume, read back.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2.3, §8
 *
 * The spec's confirmation screen is editable - sections, bullets, skills and
 * dates, with user corrections treated as ground truth over the parser
 * (FR-1.11, FR-1.12). Nothing here is editable, because there is no PATCH
 * endpoint and no section model to edit. Rendering an input that discards what
 * you type would be worse than rendering none.
 */

import { Link, useParams } from "react-router-dom";

import { useResume } from "../api";
import { ClaimsNotBuilt, ScanSourceNote, SkillSet } from "./SkillSet";
import { Empty, Panel, Section, SkeletonRows } from "../ui/primitives";

export function ResumePage() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const resume = useResume(resumeId);

  if (resume.isLoading) return <SkeletonRows rows={6} />;

  if (resume.isError || !resume.data) {
    return (
      <Empty title="No such resume">
        The id in the URL does not match a stored resume.
        <div className="mt-3">
          <Link to="/" className="text-sm font-medium text-brand hover:text-brand-hover">
            Paste one &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  const data = resume.data;

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">candidate {data.candidate_id.slice(0, 8)}</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">What we read</h1>
        <div className="mt-2.5 max-w-2xl">
          <ScanSourceNote scannedAgainst={data.scanned_against} />
        </div>
      </header>

      <SkillSet resume={data} />

      <Section label="Your text">
        <Panel tone="sunken" className="px-4 py-3">
          <pre className="text-source whitespace-pre-wrap break-words font-mono text-ink-soft">
            {data.raw_text}
          </pre>
        </Panel>
        <p className="mt-2 text-xs text-ink-faint">
          Shown whole because there are no source spans yet: we cannot point at the words a skill
          came from, so the document stands in for the citation. This is the field FR-1.17 says
          must have its contact block separated and withheld - it does not.
        </p>
      </Section>

      <ClaimsNotBuilt />
    </>
  );
}

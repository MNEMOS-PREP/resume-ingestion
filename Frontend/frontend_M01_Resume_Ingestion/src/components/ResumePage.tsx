/**
 * One resume: the confirmation pass, then the Claim Map.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2.3 Screens 3 and 4, §8
 *
 * ── Why the two screens live on one route ───────────────────────────────────
 *
 * They are one motion. §2.3 puts the confirmation pass immediately before the
 * payoff *because* the payoff depends on it: a Claim Map built from a mis-read
 * document is a diagnosis of the wrong resume, and the student has no way to
 * tell. So `confirmed` decides which is showing, and the confirmation pass
 * stays reachable afterwards — a student who spots a mis-read heading on the
 * map must be able to go back and fix it, not start again.
 *
 * ── The document panel ──────────────────────────────────────────────────────
 *
 * Sticky beside the map on a wide screen. §8.3: *"Click a claim → the original
 * scrolls and highlights that exact bullet. This is a 4-hour feature that buys
 * enormous trust: the student sees we read **their** document."*
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useResume } from "../api";
import { ClaimMap } from "./ClaimMap";
import { ConfirmationEditor } from "./ConfirmationEditor";
import { RedFlagBanner } from "./RedFlagBanner";
import { ScanSourceNote, SkillSet } from "./SkillSet";
import { RedactionNote, SourceHighlight } from "./SourceHighlight";
import { Btn, Empty, Panel, Section, SkeletonRows } from "../ui/primitives";
import type { ResumeClaim, SourceSpan } from "../types";

export function ResumePage() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const resume = useResume(resumeId);
  const [span, setSpan] = useState<SourceSpan | null>(null);
  const [reviewing, setReviewing] = useState(false);

  if (resume.isLoading) return <SkeletonRows rows={6} />;

  if (resume.isError || !resume.data) {
    return (
      <Empty title="No such resume">
        The id in the URL does not match a stored resume.
        <div className="mt-3">
          <Link to="/" className="text-sm font-medium text-brand hover:text-brand-hover">
            Start again &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  const data = resume.data;
  const showConfirmation = reviewing || !data.confirmed;

  if (showConfirmation) {
    return (
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <ConfirmationEditor resume={data} onConfirmed={() => setReviewing(false)} />
        </div>
        <aside className="min-w-0">
          <p className="rule-label mb-2">What we read</p>
          <SourceHighlight text={data.redacted_text} span={null} />
          <RedactionNote />
        </aside>
      </div>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0">
        <header className="mb-7 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="rule-label">candidate {data.candidate_id.slice(0, 8)}</p>
            <div className="mt-1 max-w-2xl">
              <ScanSourceNote scannedAgainst={data.scanned_against} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to={`/resumes/${data.id}/diff`}>
              <Btn type="button" variant="ghost" size="sm">
                What changed since last time
              </Btn>
            </Link>
            <Btn type="button" variant="ghost" size="sm" onClick={() => setReviewing(true)}>
              Something&rsquo;s wrong — let me fix it
            </Btn>
          </div>
        </header>

        <ClaimMap
          resumeId={data.id}
          onSelectSpan={(claim: ResumeClaim) => setSpan(claim.span)}
          onEditClaim={() => setReviewing(true)}
        />

        <RedFlagBanner flags={data.red_flags} />
        <SkillSet resume={data} />

        <Section label="How this was read">
          <Panel tone="sunken" className="px-4 py-3">
            <dl className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
              <Fact label="Source">
                {data.filename ?? "pasted text"} · {data.mime}
              </Fact>
              <Fact label="Pages">{data.page_count}</Fact>
              <Fact label="Columns">
                {data.columns}
                {data.columns > 1 && ` · ${Math.round(data.column_confidence * 100)}% sure`}
              </Fact>
              <Fact label="Read from an image">{data.ocr_used ? "yes" : "no"}</Fact>
              <Fact label="Took">{data.parse_ms} ms</Fact>
              <Fact label="Parser">{data.parser_version}</Fact>
            </dl>
            <p className="mt-2.5 text-xs text-ink-faint">
              Here because a score you cannot trace is a score you cannot argue with. Every claim
              above points at a range of characters in the document beside it.
            </p>
          </Panel>
        </Section>
      </div>

      <aside className="min-w-0 lg:sticky lg:top-20 lg:self-start">
        <p className="rule-label mb-2">
          {span ? "The words this came from" : "What we read"}
        </p>
        <SourceHighlight text={data.redacted_text} span={span} />
        <RedactionNote />
      </aside>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1 last:border-0">
      <dt className="text-ink-soft">{label}</dt>
      <dd className="provenance text-right">{children}</dd>
    </div>
  );
}

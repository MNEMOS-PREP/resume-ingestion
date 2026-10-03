/**
 * Screen 4, as a workspace rather than a page.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2.3 Screen 4, §8.1, §8.3
 *
 *   ┌──────────┬────────────────────────────┬──────────────────┐
 *   │  rail    │  the claims                │  your document   │
 *   │          │                            │                  │
 *   │ counts   │  grouped by risk, or by    │  the words this  │
 *   │ filters  │  the section they were     │  claim came from │
 *   │ fix 1st  │  written in               │  lit up in place │
 *   └──────────┴────────────────────────────┴──────────────────┘
 *
 * ── Why three panes and not one column ──────────────────────────────────────
 *
 * §8.3 makes the document link the module's trust proposition: *"Click a claim
 * → the original scrolls and highlights that exact bullet … the student sees we
 * read THEIR document, not a generic template."*
 *
 * In a single column the document was a 22rem panel beside the map and, on
 * anything narrower than a desktop, below it. So the highlight fired somewhere
 * the student was not looking. The feature worked perfectly and was invisible,
 * which is the same failure the focus rings had.
 *
 * Three panes are what make it land: the claim, the questions it invites, and
 * the line it came from are visible at once, and clicking connects them in
 * front of you.
 *
 * ── What holds the selection ────────────────────────────────────────────────
 *
 * One `selected` claim id, here, because three panes need to agree on it: the
 * rail highlights nothing without it, the list draws the ring, and the document
 * scrolls. It is an id rather than an index — the list is filterable, and an
 * index means the cursor jumps to a different claim when a filter changes.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useClaims } from "../api";
import { ClaimList } from "./ClaimMap";
import { ClaimRail } from "./ClaimRail";
import type { Filter, GroupBy } from "./ClaimRail";
import { RedFlagPanel } from "./RedFlagBanner";
import { SECTION_LABEL, SECTION_STAKE } from "./sections";
import { ScanSourceNote, SkillPanel } from "./SkillSet";
import { PageRedactionNote, PdfHighlightViewer } from "./PdfHighlightViewer";
import { RedactionNote, SourceHighlight } from "./SourceHighlight";
import { Btn, Empty, Panel, Section, SkeletonRows } from "../ui/primitives";
import type { Resume, ResumeClaim, SectionKind, SourceSpan } from "../types";

export function ResumeWorkspace({
  resume,
  onReview,
}: {
  resume: Resume;
  onReview: () => void;
}) {
  const listing = useClaims(resume.id);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [spans, setSpans] = useState<SourceSpan[]>([]);
  const [groupBy, setGroupBy] = useState<GroupBy>("risk");
  const [filter, setFilter] = useState<Filter>(null);
  // The page view is the default when there IS a page; `usePages` answers
  // empty for a pasted resume and the viewer falls back on its own.
  const [view, setView] = useState<"page" | "text">("page");

  const claims = useMemo(() => listing.data?.claims ?? [], [listing.data]);

  const kindOf = useMemo(
    () => new Map(resume.sections.map((section) => [section.id, section.kind])),
    [resume.sections],
  );

  const visible = useMemo(() => {
    if (!filter) return claims;
    if (filter.by === "risk")
      return claims.filter((c) => c.risk_band === filter.band);
    return claims.filter(
      (c) => (kindOf.get(c.section_id) ?? "unknown") === filter.kind,
    );
  }, [claims, filter, kindOf]);

  function select(claim: ResumeClaim) {
    setSelectedId(claim.id);
    setSpans([claim.span]);
  }

  // Position within the VISIBLE list, not the whole one: the buttons have to
  // agree with what is on screen, or "next" skips past claims a filter is
  // hiding and the count reads wrong.
  const at = visible.findIndex((claim) => claim.id === selectedId);

  function step(delta: number) {
    if (visible.length === 0) return;
    // From nothing, "next" means the first and "previous" means the last.
    const next = at < 0 ? (delta > 0 ? 0 : visible.length - 1) : at + delta;
    const claim = visible[Math.max(0, Math.min(next, visible.length - 1))];
    if (claim) select(claim);
  }

  const document = (
    <>
      <div className="flex shrink-0 items-baseline justify-between gap-2 px-4 pt-4 pb-2">
        <p className="rule-label">
          {spans.length > 0 ? "The words this came from" : "What we read"}
        </p>
        <span className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setView(view === "page" ? "text" : "page")}
            className="provenance hover:text-ink-soft"
          >
            {view === "page" ? "as text" : "as the page"}
          </button>
          {spans.length > 0 && (
            <button
              type="button"
              onClick={() => {
                setSpans([]);
                setSelectedId(null);
              }}
              className="provenance hover:text-ink-soft"
            >
              clear
            </button>
          )}
        </span>
      </div>
      <div className="min-h-0 flex-1 px-4">
        {/* §8.3's four-hour feature. The text view is not a lesser fallback —
            it carries exactly the same offsets — but a student looking at
            their OWN page, with the box drawn on it, does not have to be
            persuaded that we read their document. */}
        {view === "page" ? (
          <PdfHighlightViewer
            resumeId={resume.id}
            spans={spans}
            fallback={
              <SourceHighlight
                fill
                text={resume.redacted_text}
                spans={spans}
                sections={resume.sections}
              />
            }
          />
        ) : (
          <SourceHighlight
            fill
            text={resume.redacted_text}
            spans={spans}
            sections={resume.sections}
          />
        )}
      </div>
      <div className="shrink-0 px-4 pt-2 pb-4">
        {view === "page" ? <PageRedactionNote /> : <RedactionNote />}
        {/* The three "how was this read / who can see it" screens. They were
            ghost buttons above the diagnosis, competing with it for the first
            thing a student looks at. They belong beside the document, because
            all three are questions about the document. */}
        <p className="provenance mt-2 flex flex-wrap gap-x-3 gap-y-1">
          <Link
            to={`/resumes/${resume.id}/audit`}
            className="hover:text-ink-soft"
          >
            how this was read
          </Link>
          <Link
            to={`/resumes/${resume.id}/diff`}
            className="hover:text-ink-soft"
          >
            what changed
          </Link>
          <Link
            to={`/resumes/${resume.id}/privacy`}
            className="hover:text-ink-soft"
          >
            who can see this
          </Link>
        </p>
      </div>
    </>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      {/* ── rail ─────────────────────────────────────────────────────────── */}
      <aside
        aria-label="Claims on this resume"
        className="shrink-0 border-b border-line bg-surface lg:h-full lg:w-64 lg:border-b-0 lg:border-r"
      >
        {listing.isLoading && (
          <div className="px-4 py-5">
            <SkeletonRows rows={5} />
          </div>
        )}
        {listing.data && (
          <ClaimRail
            resume={resume}
            listing={listing.data}
            groupBy={groupBy}
            onGroupBy={setGroupBy}
            filter={filter}
            onFilter={setFilter}
            onSelect={select}
            onReview={onReview}
          />
        )}
      </aside>

      {/* ── the claims ───────────────────────────────────────────────────── */}
      <div className="min-w-0 flex-1 overflow-y-auto px-5 py-6 md:px-8">
        <header className="mb-6">
          <h2 className="text-title font-semibold text-ink">
            Your resume, as an interviewer sees it
          </h2>
          <div className="mt-1 max-w-2xl">
            <ScanSourceNote scannedAgainst={resume.scanned_against} />
          </div>

          {/* The way out of this module.
              A resume alone answers "what have I claimed". A resume against a
              POSTING answers "will this get me in", which is the question the
              student arrived with — and it lives in M02, which until now had
              nothing pointing at it. Finishing an ingest left you on a claim
              map with nowhere to go. */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-brand-line bg-brand-soft px-4 py-3">
            <p className="text-sm text-ink">
              <span className="font-medium">
                Aiming this at a specific job?
              </span>{" "}
              Paste the posting and we will check the eligibility bar, what your
              resume evidences, and how a mock for it should spend its time.
            </p>
            <span className="flex shrink-0 flex-wrap items-center gap-4">
              <Link
                to={`/resumes/${resume.id}/target`}
                className="text-sm font-medium text-brand hover:text-brand-hover"
              >
                Check against a job &rarr;
              </Link>
              {/* 2026-10-04: the other way out. M06 plans a segment on the
                  lines here that are hardest to defend, so the interview is
                  the practice this screen is diagnosing. */}
              <Link
                to="/mock"
                className="text-sm font-medium text-brand hover:text-brand-hover"
              >
                Practise defending it &rarr;
              </Link>
            </span>
          </div>

          {/* The same movement `j` and `k` do, for the people who will never
              find out that `j` and `k` do it. §8.3 asks for the keys and is
              explicit that "power users exist even among students" — which is
              an argument for the keys, not against the buttons. */}
          {visible.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Btn
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => step(-1)}
              >
                &larr; Previous
              </Btn>
              <Btn
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => step(1)}
              >
                Next &rarr;
              </Btn>
              <span className="provenance" data-numeric>
                {at < 0
                  ? `${visible.length} claims`
                  : `${at + 1} of ${visible.length}`}
              </span>
            </div>
          )}
        </header>

        {filter?.by === "section" && (
          <SectionBrief kind={filter.kind} claims={visible} />
        )}

        {listing.isLoading && <SkeletonRows rows={6} />}

        {listing.data && claims.length === 0 && (
          <Empty title="No claims yet">
            Nothing here asserts something an interviewer could push on. Add a
            project bullet that says what you built and what changed, and it
            will show up here.
          </Empty>
        )}

        {listing.data && claims.length > 0 && (
          <ClaimList
            resumeId={resume.id}
            claims={visible}
            selectedId={selectedId}
            onSelect={select}
            onEditClaim={onReview}
          />
        )}

        {/* Both read from their own endpoint rather than off the row: the
            server owns the severity ordering and the claimed-use view, and a
            screen that re-derives them is how two of them start disagreeing. */}
        <RedFlagPanel resumeId={resume.id} />
        <SkillPanel resume={resume} />

        <Section label="How this was read">
          <Panel tone="sunken" className="px-4 py-3">
            <dl className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
              <Fact label="Source">
                {resume.filename ?? "pasted text"} · {resume.mime}
              </Fact>
              <Fact label="Pages">{resume.page_count}</Fact>
              <Fact label="Columns">
                {resume.columns}
                {resume.columns > 1 &&
                  ` · ${Math.round(resume.column_confidence * 100)}% sure`}
              </Fact>
              <Fact label="Read from an image">
                {resume.ocr_used ? "yes" : "no"}
              </Fact>
              <Fact label="Took">{resume.parse_ms} ms</Fact>
              <Fact label="Parser">{resume.parser_version}</Fact>
            </dl>
            <p className="mt-2.5 text-xs text-ink-faint">
              Here because a score you cannot trace is a score you cannot argue
              with. Every claim above points at a range of characters in the
              document beside it.
            </p>
          </Panel>
        </Section>
      </div>

      {/* ── the document ─────────────────────────────────────────────────── */}
      <aside
        aria-label="Your resume"
        className="flex max-h-[60vh] shrink-0 flex-col border-t border-line bg-surface lg:h-full lg:max-h-none lg:w-[26rem] lg:border-t-0 lg:border-l"
      >
        {document}
      </aside>
    </div>
  );
}

/**
 * What this section is, and what an interviewer does with it.
 *
 * Shown only when the claims are grouped by section, because that is the view
 * where a student is asking about their Projects block rather than about their
 * riskiest line. The count of probes is the direct answer to *"what would they
 * ask me about this section"* - it is not a new computation, it is the ladders
 * M01 already generated for each claim, added up.
 */
function SectionBrief({
  kind,
  claims,
}: {
  kind: SectionKind;
  claims: ResumeClaim[];
}) {
  const risky = claims.filter((claim) => claim.risk_band === "risky").length;
  const probes = claims.reduce((sum, claim) => sum + claim.probes.length, 0);
  const stake = SECTION_STAKE[kind];

  return (
    <Panel tone="sunken" className="mb-7 px-4 py-3.5">
      <p className="text-sm font-semibold text-ink">{SECTION_LABEL[kind]}</p>
      {stake && <p className="mt-1 max-w-2xl text-sm text-ink-soft">{stake}</p>}
      <p className="mt-2 text-xs text-ink-soft" data-numeric>
        {claims.length} claim{claims.length === 1 ? "" : "s"} here
        {risky > 0 && ` · ${risky} hard to defend`}
        {probes > 0 &&
          ` · ${probes} question${probes === 1 ? "" : "s"} an interviewer could open with`}
      </p>
    </Panel>
  );
}

function Fact({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1 last:border-0">
      <dt className="text-ink-soft">{label}</dt>
      <dd className="provenance text-right">{children}</dd>
    </div>
  );
}

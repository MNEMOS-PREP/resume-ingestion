/**
 * Where every number on this resume came from (FR-1.12, FR-1.20, AC-1.7).
 *
 * Two append-only logs the backend has always kept and nothing has ever shown:
 *
 *   · the CORRECTION log — every time the student overruled the parser. It is
 *     what makes AC-1.7 answerable at all: "edit rate > 40% means the parser
 *     needs work" is only a criterion if every correction is still on disk.
 *
 *   · the EVENT stream — the `resume.*` stage boundaries. The endpoint exists
 *     because an event stream nobody can look at is one that quietly stops
 *     being emitted, and until this screen the only way to look was the database.
 *
 * ── Why the student sees this and not only an operator ──────────────────────
 *
 * The correction log is a record of the student's own disagreements with us.
 * Hiding it would mean the one party who knows whether we read their document
 * correctly cannot check what we recorded about that. The event payloads carry
 * counts, durations and ids and never the resume text — the server whitelists
 * the keys — so there is nothing here to withhold.
 */

import { Link, useParams } from "react-router-dom";

import { useCorrections, useResume, useResumeEvents } from "../api";
import { Empty, Panel, Section, SkeletonRows } from "../ui/primitives";
import type { Correction, ResumeEventRow } from "../types";

const TARGET_LABEL: Record<string, string> = {
  section: "section heading",
  claim: "bullet",
  skill: "skill",
  entity: "date",
};

const FIELD_LABEL: Record<string, string> = {
  kind: "relabelled",
  text: "rewrote",
  claim_type: "reclassified",
  present: "added or removed",
  dates: "corrected",
};

const EVENT_LABEL: Record<string, string> = {
  "resume.ingested": "read the document",
  "resume.parsed": "found the sections and bullets",
  "resume.scored": "scored every claim",
  "resume.corrected": "you corrected something",
  "resume.confirmed": "you signed off on the read",
  "resume.failed": "the read failed",
  "resume.deleted": "deleted on request",
};

export function AuditPage() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const resume = useResume(resumeId);
  const corrections = useCorrections(resumeId);
  const events = useResumeEvents(resumeId);

  if (resume.isLoading) return <SkeletonRows rows={5} />;

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

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">resume {resume.data.id.slice(0, 8)}</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">How this read was made</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          Everything below is a record, not a setting. It is here because a score you cannot trace
          is a score you cannot argue with &mdash; and because a log nobody can read is one that
          quietly stops being written.
        </p>
      </header>

      <Section
        label="What you corrected"
        meta={corrections.data ? `${corrections.data.length}` : undefined}
      >
        {corrections.isLoading && <SkeletonRows rows={3} />}

        {corrections.data && corrections.data.length === 0 && (
          <Panel tone="sunken" className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              Nothing yet. You have not overruled the parser on this resume &mdash; which either
              means it read your document correctly, or that you have not been through the
              confirmation pass. Those are very different, and this page cannot tell them apart.
            </p>
          </Panel>
        )}

        {corrections.data && corrections.data.length > 0 && (
          <Panel className="px-4 py-1">
            <div className="divide-y divide-line">
              {corrections.data.map((correction) => (
                <CorrectionRow key={correction.id} correction={correction} />
              ))}
            </div>
          </Panel>
        )}

        <p className="mt-2 text-xs text-ink-faint">
          These follow the document rather than this row, so re-uploading the same file re-applies
          every fix you already made. They also survive deleting the resume &mdash; they hold no
          document text, and they are the evidence behind whether the parser is getting better.
        </p>
      </Section>

      <Section
        label="What happened, in order"
        meta={events.data ? `${events.data.length}` : undefined}
      >
        {events.isLoading && <SkeletonRows rows={4} />}

        {events.data && events.data.length === 0 && (
          <Panel tone="sunken" className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              No stage boundaries recorded. For a resume that parsed, this is a bug rather than an
              empty state &mdash; it means the events stopped being emitted.
            </p>
          </Panel>
        )}

        {events.data && events.data.length > 0 && (
          <Panel className="px-4 py-1">
            <div className="divide-y divide-line">
              {events.data.map((event) => (
                <EventRow key={event.id} event={event} />
              ))}
            </div>
          </Panel>
        )}

        <p className="mt-2 text-xs text-ink-faint">
          Counts, durations and ids only. The resume text, your bullets and your contact details
          are never written to this stream &mdash; the server keeps a whitelist of what an event
          may carry and drops anything else.
        </p>
      </Section>

      <div className="flex flex-wrap gap-4 border-t border-line pt-5">
        <Link
          to={`/resumes/${resumeId}`}
          className="text-sm font-medium text-brand hover:text-brand-hover"
        >
          &larr; Back to the claim map
        </Link>
        <Link
          to={`/resumes/${resumeId}/privacy`}
          className="text-sm font-medium text-brand hover:text-brand-hover"
        >
          Who can see this &rarr;
        </Link>
      </div>
    </>
  );
}

function CorrectionRow({ correction }: { correction: Correction }) {
  const target = TARGET_LABEL[correction.target] ?? correction.target;
  const what = FIELD_LABEL[correction.field] ?? correction.field;

  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
      <div className="min-w-0">
        <p className="text-sm text-ink">
          You {what} a {target}
        </p>
        <p className="provenance mt-0.5 break-words">
          {correction.old_value ?? "—"} <span aria-hidden>&rarr;</span>{" "}
          {correction.new_value ?? "(removed)"}
        </p>
      </div>
      <span className="provenance shrink-0">{shortTime(correction.created_at)}</span>
    </div>
  );
}

function EventRow({ event }: { event: ResumeEventRow }) {
  const label = EVENT_LABEL[event.name] ?? event.name;
  const facts = Object.entries(event.payload).filter(
    ([key]) => key !== "resume_id" && key !== "candidate_id",
  );

  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
      <div className="min-w-0">
        <p className="text-sm text-ink">{label}</p>
        {facts.length > 0 && (
          <p className="provenance mt-0.5 break-words">
            {facts.map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`).join(" · ")}
          </p>
        )}
      </div>
      <span className="provenance shrink-0">{shortTime(event.at)}</span>
    </div>
  );
}

/**
 * Local time, to the second.
 *
 * The second matters: an ingest and its parse events land inside the same
 * minute, and a minute-resolution stamp renders the whole pipeline as one
 * instant — which hides the ordering that is the only reason to read a stream
 * rather than a summary.
 *
 * The `Z` is added when the server did not send one. SQLite hands back naive
 * datetimes, FastAPI serialises them without an offset, and a browser then
 * reads a UTC timestamp as local — which on IST puts every event five and a
 * half hours in the future and makes the log look like it is describing
 * something that has not happened yet.
 */
function shortTime(iso: string): string {
  const normalised = /[Z+]|-\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const at = new Date(normalised);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

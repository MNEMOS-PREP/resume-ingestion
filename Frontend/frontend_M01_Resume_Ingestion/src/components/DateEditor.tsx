/**
 * Dates — §2.3 Screen 3's fourth editable target (FR-1.11).
 *
 * *"Sections, bullets, skills, and dates."*  Three of those four have been
 * editable since the confirmation pass was built. Dates were not, and they are
 * the one that feeds something the student is then asked to defend: a mis-read
 * range drives both the timeline-gap red flag and `recency`, so a student could
 * be told to prepare an answer for a gap between two dates the parser
 * invented, with no way to say so.
 *
 * ── Two operations, and the second is the one that matters ──────────────────
 *
 * Correcting a range, and STRIKING one. A parser that reads "12k-node" as a
 * year produces a range that is not on the resume at all, and there is no
 * correct value to type into it. An empty value removes it, which the server
 * records as a correction like any other — AC-1.7 should count a student
 * telling us we invented something.
 *
 * ── Why a free-text box and not two year pickers ────────────────────────────
 *
 * The typed value goes through the same parser that read the document, so a
 * corrected date and a read one are the same shape downstream and the
 * timeline rules never have to handle two. It also means the student writes
 * the range the way their resume writes it. A 422 here says "I could not read
 * that as a date range", which is a different sentence from "rejected", and
 * the screen says the difference.
 */

import { useState } from "react";

import { useEditDate } from "../api";
import { Btn, ErrorNote, Panel, Section } from "../ui/primitives";
import type { DateRange, Resume } from "../types";

export function DateEditor({ resume }: { resume: Resume }) {
  const ranges = resume.entities?.dates ?? [];
  if (ranges.length === 0) return null;

  return (
    <Section label="Dates" meta={`${ranges.length} read off the page`}>
      <div className="space-y-2">
        {ranges.map((range, index) => (
          <DateRow
            // Index is the server's own address for this range, so it is the
            // identity here too — a `raw` key collides the moment a resume
            // lists two roles in the same year, which is most of them.
            key={`${index}-${range.raw}`}
            resumeId={resume.id}
            index={index}
            range={range}
          />
        ))}
      </div>
      <p className="mt-2 text-xs text-ink-faint">
        These drive the gap check. If one of them is not a date at all, strike it &mdash; a gap
        measured from a number we misread is a question you would be preparing for no reason.
      </p>
    </Section>
  );
}

function DateRow({
  resumeId,
  index,
  range,
}: {
  resumeId: string;
  index: number;
  range: DateRange;
}) {
  const [draft, setDraft] = useState(range.raw);
  const [editing, setEditing] = useState(false);
  const edit = useEditDate(resumeId);

  const unreadable = edit.isError;

  if (!editing) {
    return (
      <Panel className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 px-4 py-2.5">
        <span className="text-sm text-ink">
          {range.raw}
          <span className="provenance ml-2">
            {range.start_year}
            {range.ongoing ? " → now" : range.end_year ? ` → ${range.end_year}` : ""}
          </span>
        </span>
        <span className="flex gap-2">
          <Btn
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setDraft(range.raw);
              setEditing(true);
            }}
          >
            edit
          </Btn>
          <Btn
            type="button"
            variant="ghost"
            size="sm"
            disabled={edit.isPending}
            onClick={() => edit.mutate({ index, value: null })}
          >
            not a date
          </Btn>
        </span>
      </Panel>
    );
  }

  return (
    <Panel className="px-4 py-3">
      <label className="block">
        <span className="rule-label">Date range</span>
        <span className="mt-0.5 block text-xs text-ink-soft">
          Write it the way your resume writes it &mdash; &ldquo;Jun 2025 - Aug 2025&rdquo;,
          &ldquo;2022 - present&rdquo;.
        </span>
        <input
          value={draft}
          autoFocus
          onChange={(event) => setDraft(event.target.value)}
          className="mt-1.5 w-full rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-brand-line"
        />
      </label>

      {unreadable && (
        <div className="mt-2">
          <ErrorNote>
            I could not read that as a date range, so I have left the old one alone rather than
            store something the gap check cannot compare. Try a form with a year in it.
          </ErrorNote>
        </div>
      )}

      <div className="mt-2 flex gap-2">
        <Btn
          type="button"
          variant="primary"
          size="sm"
          disabled={edit.isPending || !draft.trim() || draft === range.raw}
          onClick={() =>
            edit.mutate({ index, value: draft }, { onSuccess: () => setEditing(false) })
          }
        >
          {edit.isPending ? "Saving…" : "Save"}
        </Btn>
        <Btn
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            edit.reset();
            setEditing(false);
          }}
        >
          Cancel
        </Btn>
      </div>
    </Panel>
  );
}

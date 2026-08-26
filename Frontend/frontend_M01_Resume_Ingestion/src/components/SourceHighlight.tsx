/**
 * Click a claim, and the document highlights that exact bullet.
 *
 * Spec §8.3: *"This is a 4-hour feature that buys enormous trust: the student
 * sees we read **their** document, not a generic template."*
 *
 * ── Why this highlights text and not a PDF page ─────────────────────────────
 *
 * §8.1 names a `PdfHighlightViewer` that draws the `bbox` over a rendered page.
 * That needs a PDF renderer in the browser (pdf.js, ~350 KB) and the original
 * bytes served back to the client — and the original is the unredacted
 * artifact, which FR-1.17 says does not leave the module. Rendering it in a
 * student's browser would be handing back the exact document the contact
 * isolation exists to keep in one place.
 *
 * So the highlight is drawn over `redacted_text`, which is the same document,
 * the same length, character for character. The offsets that would drive a bbox
 * overlay drive a text range instead, and the trust-buying property — *we can
 * point at the words in your document* — is fully intact. The bbox is still
 * carried on every span (FR-1.3) and is what a later viewer would use.
 *
 * ── Why it takes a LIST of spans ────────────────────────────────────────────
 *
 * A claim has one span. A red flag has several — `RedFlag.spans` is a list
 * because a chronology conflict is a statement about two dates and pointing at
 * one of them explains nothing. A skill has one per occurrence, which is what
 * makes "you wrote this three times" checkable rather than asserted.
 *
 * Highlighting them one at a time turns a finding about a PATTERN into a
 * sequence of unrelated jumps. Showing all of them at once is the finding.
 *
 * ── Redaction is visible, not silent ────────────────────────────────────────
 *
 * The masked contact block renders as blocks. That is deliberate: a student
 * seeing their email replaced by ████ understands what happened to it, where a
 * blank gap looks like a parsing failure.
 */

import { useEffect, useMemo, useRef } from "react";

import { Panel } from "../ui/primitives";
import type { SourceSpan } from "../types";

/** A run of the document, and whether it is part of the current finding. */
interface Segment {
  text: string;
  hit: boolean;
}

/**
 * Cut the document into segments at the span boundaries.
 *
 * Spans are clamped to the text and sorted, and overlapping ones are merged —
 * two highlights that share a character would otherwise render nested `<mark>`s
 * and double the background, which reads as a third, darker band that means
 * nothing.
 */
function segment(text: string, spans: SourceSpan[]): Segment[] | null {
  const ranges = spans
    .map((s) => {
      const start = Math.max(0, Math.min(s.start, text.length));
      return { start, end: Math.max(start, Math.min(s.end, text.length)) };
    })
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start);

  if (ranges.length === 0) return null;

  const merged: typeof ranges = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range.start <= last.end) last.end = Math.max(last.end, range.end);
    else merged.push({ ...range });
  }

  const out: Segment[] = [];
  let cursor = 0;
  for (const range of merged) {
    if (range.start > cursor) out.push({ text: text.slice(cursor, range.start), hit: false });
    out.push({ text: text.slice(range.start, range.end), hit: true });
    cursor = range.end;
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor), hit: false });
  return out;
}

export function SourceHighlight({
  text,
  span,
  spans,
  emptyNote,
  fill = false,
}: {
  text: string;
  /** One span — the common case, a claim. */
  span?: SourceSpan | null;
  /** Several — a red flag, or every occurrence of a skill. Wins over `span`. */
  spans?: SourceSpan[] | null;
  emptyNote?: string;
  /**
   * Fill the parent instead of capping at 28rem.
   *
   * In the workspace this panel IS a column of the page and owns its own
   * scrollbar, so a max-height would leave dead space under it and put a second
   * scrollbar inside the first. Everywhere else it sits in a reading column
   * beside other content and has to stay a panel rather than take the page.
   */
  fill?: boolean;
}) {
  const first = useRef<HTMLElement>(null);

  const active = useMemo<SourceSpan[]>(
    () => (spans && spans.length > 0 ? spans : span ? [span] : []),
    [spans, span],
  );

  // The identity of the selection, so the scroll fires when the student picks a
  // different finding and not on every unrelated re-render.
  const key = active.map((s) => `${s.start}-${s.end}`).join(",");

  useEffect(() => {
    // `block: "center"` rather than the default, so the highlighted bullet
    // lands in the middle of the panel instead of flush against its top edge
    // where it reads as "the document starts here".
    first.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [key]);

  const segments = useMemo(() => segment(text, active), [text, active]);

  if (!text.trim()) {
    return (
      <Panel tone="sunken" className={`px-4 py-6 ${fill ? "h-full" : ""}`}>
        <p className="text-sm text-ink-soft">
          {emptyNote ?? "Nothing to show — no resume text was stored."}
        </p>
      </Panel>
    );
  }

  let seenHit = false;

  return (
    <Panel
      tone="sunken"
      className={`overflow-y-auto px-4 py-3 ${fill ? "h-full" : "max-h-[28rem]"}`}
    >
      <pre className="text-source whitespace-pre-wrap break-words font-mono text-ink-soft">
        {segments
          ? segments.map((part, index) => {
              if (!part.hit) return <span key={index}>{part.text}</span>;
              const isFirst = !seenHit;
              seenHit = true;
              return (
                <mark
                  key={index}
                  ref={isFirst ? first : undefined}
                  className="rounded-sm bg-brand-soft px-0.5 text-ink ring-1 ring-brand-line"
                >
                  {part.text}
                </mark>
              );
            })
          : text}
      </pre>
    </Panel>
  );
}

/**
 * The note that explains the blocks, shown once beneath the document.
 *
 * Without it the first reaction to ████ is "the parser corrupted my resume".
 */
export function RedactionNote() {
  return (
    <p className="mt-2 text-xs text-ink-faint">
      Your email, phone number and links are masked here (█). They are stored separately and are
      never sent to a model or shown on this screen &mdash; the characters are kept in place so
      every highlight still lines up with your document.
    </p>
  );
}

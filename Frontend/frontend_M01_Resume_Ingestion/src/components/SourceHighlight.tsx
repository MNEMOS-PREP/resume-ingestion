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
 * ── Redaction is visible, not silent ────────────────────────────────────────
 *
 * The masked contact block renders as blocks. That is deliberate: a student
 * seeing their email replaced by ████ understands what happened to it, where a
 * blank gap looks like a parsing failure.
 */

import { useEffect, useMemo, useRef } from "react";

import { Panel } from "../ui/primitives";
import type { SourceSpan } from "../types";

export function SourceHighlight({
  text,
  span,
  emptyNote,
}: {
  text: string;
  span: SourceSpan | null;
  emptyNote?: string;
}) {
  const mark = useRef<HTMLElement>(null);

  useEffect(() => {
    // `block: "center"` rather than the default, so the highlighted bullet
    // lands in the middle of the panel instead of flush against its top edge
    // where it reads as "the document starts here".
    mark.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [span?.start, span?.end]);

  const parts = useMemo(() => {
    if (!span) return null;
    const start = Math.max(0, Math.min(span.start, text.length));
    const end = Math.max(start, Math.min(span.end, text.length));
    return { before: text.slice(0, start), hit: text.slice(start, end), after: text.slice(end) };
  }, [text, span]);

  if (!text.trim()) {
    return (
      <Panel tone="sunken" className="px-4 py-6">
        <p className="text-sm text-ink-soft">
          {emptyNote ?? "Nothing to show — no resume text was stored."}
        </p>
      </Panel>
    );
  }

  return (
    <Panel tone="sunken" className="max-h-[28rem] overflow-y-auto px-4 py-3">
      <pre className="text-source whitespace-pre-wrap break-words font-mono text-ink-soft">
        {parts ? (
          <>
            {parts.before}
            <mark
              ref={mark}
              className="rounded-sm bg-brand-soft px-0.5 text-ink ring-1 ring-brand-line"
            >
              {parts.hit}
            </mark>
            {parts.after}
          </>
        ) : (
          text
        )}
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

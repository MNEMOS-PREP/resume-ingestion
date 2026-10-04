/**
 * Click a claim, and the box lights up on the page you actually uploaded.
 *
 * Spec: §8.1 (`PdfHighlightViewer`), §8.3, §8.2's states table
 *
 * §8.3: *"Click a claim → the original PDF scrolls and highlights that exact
 * bullet. This is a 4-hour feature that buys enormous trust: the student sees
 * we read **their** document."*
 *
 * Every `SourceSpan` has carried a `bbox` since FR-1.3 landed. Nothing rendered
 * it. The text view beside this carries the same guarantee — the offsets are
 * exact — and none of the recognition: a student reading their own resume in a
 * monospace column has to take our word that it is theirs.
 *
 * ── Why the page is an image from the server ────────────────────────────────
 *
 * The obvious build is pdf.js over the original bytes, and it cannot happen:
 * the original is the UNREDACTED document, and sending it to a browser hands
 * back the exact artifact the contact isolation exists to keep in one place. A
 * student's phone number would leave the module in order to draw a box on it.
 *
 * So the backend rasterises the page with the contact block painted out FIRST —
 * verified pixel-by-pixel, not asserted — and what arrives here is an image
 * that never contained it. The highlight is a positioned div over that image.
 *
 * ── Scaling ─────────────────────────────────────────────────────────────────
 *
 * `bbox` is in PDF points. The image is rendered at a zoom the client does not
 * choose and should not assume, so `/pages` returns each page's size in points
 * and the overlay scales by `renderedWidth / pointsWidth` — measured from the
 * `img` after it loads, which also makes it correct at every window size
 * without a resize listener doing arithmetic.
 */

import { useEffect, useRef, useState } from "react";

import { usePageImage, usePages } from "../api";
import { Panel, SkeletonRows } from "../ui/primitives";
import type { SourceSpan } from "../types";

export function PdfHighlightViewer({
  resumeId,
  spans,
  fallback,
  autoScroll = true,
}: {
  resumeId: string;
  spans: SourceSpan[];
  /** Scroll the highlighted page into view. Off where it would move the
   *  whole window rather than this viewer (a phone, in the review). */
  autoScroll?: boolean;
  /** Shown when there is no page — a pasted resume, or a deleted file. */
  fallback: React.ReactNode;
}) {
  const pages = usePages(resumeId);

  if (pages.isLoading) {
    return (
      <Panel tone="sunken" className="h-full px-4 py-3">
        <SkeletonRows rows={6} />
      </Panel>
    );
  }

  // §8.2: "Original not available (pasted text)" is a STATE, not an error.
  if (!pages.data || pages.data.length === 0) return <>{fallback}</>;

  // The page the current selection is on. With nothing selected, the first —
  // a student opening this should see their resume, not a blank frame.
  const target = spans.length > 0 ? spans[0].page : 1;

  return (
    <div className="h-full overflow-y-auto">
      {pages.data.map((page) => (
        <PageImage
          key={page.page}
          resumeId={resumeId}
          page={page.page}
          widthPoints={page.width}
          spans={spans.filter((span) => span.page === page.page && span.bbox)}
          scrollTo={autoScroll && page.page === target && spans.length > 0}
        />
      ))}
    </div>
  );
}

function PageImage({
  resumeId,
  page,
  widthPoints,
  spans,
  scrollTo,
}: {
  resumeId: string;
  page: number;
  widthPoints: number;
  spans: SourceSpan[];
  scrollTo: boolean;
}) {
  const src = usePageImage(resumeId, page);
  const image = useRef<HTMLImageElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  // Points -> rendered pixels. Measured rather than assumed: the server picks
  // the zoom, and the browser then fits the image to the column.
  const [scale, setScale] = useState(0);

  const measure = () => {
    const width = image.current?.clientWidth ?? 0;
    if (width > 0 && widthPoints > 0) setScale(width / widthPoints);
  };

  useEffect(() => {
    if (!image.current) return;
    const observer = new ResizeObserver(measure);
    observer.observe(image.current);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widthPoints, src.data]);

  const key = spans.map((s) => `${s.start}-${s.end}`).join(",");
  useEffect(() => {
    if (scrollTo && spans.length > 0) {
      frame.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, scrollTo]);

  return (
    <div ref={frame} className="relative mb-4 last:mb-0">
      {src.isError ? (
        <p className="rounded-panel border border-line px-3 py-6 text-center text-sm text-ink-soft">
          {(src.error as Error).message}
        </p>
      ) : !src.data ? (
        <div className="aspect-[1/1.414] w-full animate-pulse rounded-panel border border-line bg-surface-sunken" />
      ) : (
        <img
          ref={image}
          src={src.data}
          alt={`Page ${page} of your resume`}
          onLoad={measure}
          className="w-full rounded-panel border border-line"
        />
      )}

      {scale > 0 &&
        spans.map((span) => {
          const [x0, y0, x1, y1] = span.bbox as [number, number, number, number];
          return (
            <div
              key={`${span.start}-${span.end}`}
              aria-hidden
              className="pointer-events-none absolute rounded-sm bg-brand-soft/50 ring-2 ring-brand-line"
              style={{
                left: x0 * scale,
                top: y0 * scale,
                width: Math.max(2, (x1 - x0) * scale),
                height: Math.max(2, (y1 - y0) * scale),
              }}
            />
          );
        })}
    </div>
  );
}

/**
 * The note under the page view.
 *
 * The black bars need explaining for the same reason the block characters do in
 * the text view: without a sentence, the first reading of a blacked-out line is
 * "something went wrong", not "they hid this on purpose".
 */
export function PageRedactionNote() {
  return (
    <p className="mt-2 text-xs text-ink-faint">
      This is your own file, re-rendered here with your email, phone number and links painted out
      before the image was made &mdash; they are not hidden under the black, they were never in
      it. The original never leaves the server.
    </p>
  );
}

/**
 * A change shown as what it was and what it becomes — the review page's diff,
 * shared (2026-11-17).
 *
 * The review page's cards, the tailored copy's history and M02's job-match
 * suggestions all show the same thing: one line before and after. One
 * component, so a blank is marked the same way on every screen and the red /
 * green reads the same everywhere.
 */

/** A blank only the student can fill. Kept in step with `review.BLANK`. */
export const BLANK = /\[[^[\]]+\]/g;

/** Text with every [blank] marked. */
export function Blanks({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (const match of text.matchAll(BLANK)) {
    if (match.index > at) parts.push(text.slice(at, match.index));
    parts.push(
      <mark key={match.index} className="rounded bg-reported-soft px-0.5 font-medium text-ink">
        {match[0]}
      </mark>,
    );
    at = match.index + match[0].length;
  }
  if (at < text.length) parts.push(text.slice(at));
  return <>{parts}</>;
}

export function FixDiff({
  original,
  suggestion,
  compact = false,
}: {
  original: string;
  suggestion: string;
  /** Smaller type, for a history row or a narrow rail. */
  compact?: boolean;
}) {
  const size = compact ? "px-2.5 py-1.5 text-xs" : "px-3 py-2 text-sm";
  return (
    <div className="space-y-1.5 overflow-hidden rounded-lg border border-line">
      {original && (
        <p
          className={`bg-contested-soft leading-relaxed text-ink-soft line-through decoration-contested/60 ${size}`}
        >
          <span className="sr-only">Before: </span>
          {original}
        </p>
      )}
      <p className={`bg-confirmed-soft leading-relaxed text-ink ${size}`}>
        <span className="sr-only">After: </span>
        <Blanks text={suggestion} />
      </p>
    </div>
  );
}

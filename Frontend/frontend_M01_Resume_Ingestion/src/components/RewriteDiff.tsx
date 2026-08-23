/**
 * A STAR rewrite suggestion (FR-1.19, §8.1 `RewriteDiff`).
 *
 * ── The thing this screen must not become ───────────────────────────────────
 *
 * §15 open decision 2: *"Auto-apply STAR rewrites? Recommendation: **no** —
 * suggest only. A resume the student didn't write is a resume they can't
 * defend, which is the exact failure this module exists to prevent."*
 *
 * There is therefore no "apply" button here, and there is no finished sentence
 * to copy. The suggestion arrives as a shape with the student's own facts left
 * as bracketed blanks, and the blanks are rendered as blanks — visibly, so the
 * temptation to paste it wholesale never arises. What they get instead is a
 * list of the four things a defensible bullet has, ticked or not, and the one
 * change with the most effect.
 */

import { Btn, Panel } from "../ui/primitives";
import type { RewriteSuggestion } from "../types";

const SLOT_LABEL: Record<string, string> = {
  action: "What you did",
  task: "Why it was needed",
  result: "What measurably changed",
  situation: "How big it was",
};

export function RewriteDiff({
  suggestion,
  onClose,
}: {
  suggestion: RewriteSuggestion;
  onClose: () => void;
}) {
  return (
    <Panel className="px-4 py-4">
      <div className="flex items-start justify-between gap-4">
        <h3 className="text-section font-semibold text-ink">A stronger shape for this bullet</h3>
        <Btn type="button" variant="ghost" size="sm" onClick={onClose}>
          close
        </Btn>
      </div>

      <p className="mt-3 text-xs font-medium text-ink-soft">The one thing to change</p>
      <p className="mt-1 text-sm text-ink">{suggestion.first_fix}</p>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div>
          <p className="rule-label">What you wrote</p>
          <p className="mt-1.5 rounded-md bg-surface-sunken px-3 py-2 text-sm text-ink-soft">
            {suggestion.original}
          </p>
        </div>
        <div>
          <p className="rule-label">The shape to fill in</p>
          <p className="mt-1.5 rounded-md border border-brand-line bg-brand-soft px-3 py-2 text-sm text-ink">
            <Blanks text={suggestion.suggestion} />
          </p>
        </div>
      </div>

      <ul className="mt-4 space-y-1.5">
        {suggestion.slots.map((slot) => (
          <li key={slot.slot} className="flex items-start gap-2 text-sm">
            <span aria-hidden className={slot.present ? "text-confirmed" : "text-ink-faint"}>
              {slot.present ? "✓" : "○"}
            </span>
            <span>
              <span className={slot.present ? "text-ink-soft" : "font-medium text-ink"}>
                {SLOT_LABEL[slot.slot] ?? slot.slot}
              </span>
              {slot.present ? (
                <span className="provenance ml-2">
                  {slot.evidence ? `“${slot.evidence}”` : "present"}
                </span>
              ) : (
                <span className="ml-2 text-ink-soft">{slot.prompt}</span>
              )}
            </span>
          </li>
        ))}
      </ul>

      {suggestion.drop_words.length > 0 && (
        <p className="mt-3 text-sm text-ink-soft">
          <span className="font-medium text-ink">Words doing no work: </span>
          {suggestion.drop_words.map((word) => (
            <span key={word} className="mr-1.5 line-through decoration-contested">
              {word}
            </span>
          ))}
          &mdash; each one is a place a measurement should be.
        </p>
      )}

      <p className="mt-4 border-t border-line pt-3 text-xs text-ink-faint">{suggestion.caveat}</p>
    </Panel>
  );
}

/**
 * Renders `[like this]` as a visible blank.
 *
 * The point of the whole screen is that the student fills these in. Set as
 * ordinary prose they read as a finished sentence with odd punctuation, and
 * somebody pastes it into their resume.
 */
function Blanks({ text }: { text: string }) {
  const parts = text.split(/(\[[^\]]+\])/g);
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith("[") && part.endsWith("]") ? (
          <span
            key={index}
            className="mx-0.5 rounded border-b-2 border-dotted border-brand-line bg-surface px-1 font-medium text-brand"
          >
            {part.slice(1, -1)}
          </span>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}

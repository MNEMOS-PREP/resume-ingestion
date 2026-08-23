/**
 * Screen 2 — the narrated parse (§2.3).
 *
 * *"Parsing takes 8-25 seconds. A spinner for 25 seconds feels broken. So we
 * narrate, and each line appears as its stage actually completes."*
 *
 * Every line here comes off the SSE stream, which the server derives from what
 * the parse actually recorded — section count, claim count, whether OCR ran. A
 * bar that animates over work that is not happening is the theatre §2.3 warns
 * about, so nothing on this screen is invented client-side.
 *
 * ── Accessibility ───────────────────────────────────────────────────────────
 *
 * §8.4 asks for an ARIA live region announcing parse stage changes. The stage
 * list is `aria-live="polite"`, so a screen-reader user hears "Found 4
 * sections" as it lands rather than discovering a finished screen.
 */

import { useEffect, useRef, useState } from "react";

import { subscribeToProgress } from "../api";
import type { ProgressEvent } from "../types";

const STAGE_TITLE: Record<string, string> = {
  intake: "Reading your resume",
  layout: "Working out the layout",
  segment: "Finding the sections",
  entities: "Reading your education and roles",
  claims: "Working out what each bullet is claiming",
  scoring: "Judging how defensible each one is",
  probes: "Preparing questions",
  flags: "Checking the timeline",
  complete: "Done",
};

/** Announced when a parse crosses this, per §2.3. */
const SLOW_MS = 30_000;

export function ParseProgress({
  resumeId,
  onDone,
  onSkip,
}: {
  resumeId: string;
  onDone: () => void;
  onSkip?: () => void;
}) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [slow, setSlow] = useState(false);
  const done = useRef(false);

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (!done.current && Date.now() - started > SLOW_MS) setSlow(true);
    }, 1000);

    const unsubscribe = subscribeToProgress(
      resumeId,
      (event) => setEvents((previous) => [...previous, event]),
      () => {
        done.current = true;
        window.clearInterval(timer);
        onDone();
      },
    );

    return () => {
      window.clearInterval(timer);
      unsubscribe();
    };
  }, [resumeId, onDone]);

  const progress = events.length ? events[events.length - 1].progress : 0;
  const stages = Object.keys(STAGE_TITLE).filter((stage) => stage !== "complete");
  const seen = new Set(events.map((event) => event.stage));

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-title font-semibold text-ink">Reading your resume…</h1>

      <ol className="mt-5 space-y-2" aria-live="polite" aria-busy={!done.current}>
        {stages.map((stage) => {
          const event = events.find((candidate) => candidate.stage === stage);
          const state = event ? "done" : seen.size && !event ? "waiting" : "waiting";
          return (
            <li key={stage} className="flex items-start gap-2.5 text-sm">
              <span
                aria-hidden
                className={
                  state === "done" ? "text-confirmed" : "text-ink-faint"
                }
              >
                {state === "done" ? "✓" : "○"}
              </span>
              <span className={state === "done" ? "text-ink" : "text-ink-faint"}>
                {event ? event.detail : STAGE_TITLE[stage]}
              </span>
            </li>
          );
        })}
      </ol>

      <div
        className="mt-5 h-1.5 overflow-hidden rounded-full bg-surface-sunken"
        role="progressbar"
        aria-valuenow={Math.round(progress * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Parse progress"
      >
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-300"
          style={{ width: `${Math.max(4, progress * 100)}%` }}
        />
      </div>

      {slow && (
        // §2.3, verbatim. Never a silent timeout.
        <p className="mt-3 text-sm text-ink-soft">
          This one&rsquo;s taking a while &mdash; it&rsquo;s a dense resume. Hang on.
        </p>
      )}

      {onSkip && (
        // §2.3: "The Skip escape hatch stays available the whole time."
        <button
          type="button"
          onClick={onSkip}
          className="mt-5 text-sm font-medium text-brand hover:text-brand-hover"
        >
          Start without waiting &mdash; I&rsquo;ll come back to this
        </button>
      )}
    </div>
  );
}

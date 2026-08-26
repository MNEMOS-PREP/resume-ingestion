/**
 * The 2-minute defend drill (§2.3 Screen 5) — the module's own KPI.
 *
 * §13 is blunt about it: *"The KPI to actually watch is AC-1.8. Parsing
 * accuracy is a means; a student running a drill because they saw a risky
 * claim is the outcome."*  And §2.4's quit-trigger table answers *"nothing to
 * do next"* with *"every risky claim has a 2-minute drill button"*.
 *
 * There was no button. The only actions on a risky card were "rewrite it" and
 * "edit the bullet" — both of which are about the SENTENCE — so the Claim Map
 * ended in a cul-de-sac and AC-1.8 had no numerator. Not below target:
 * unmeasurable.
 *
 * ── What this renders when M06 does not exist ───────────────────────────────
 *
 * The questions, and a sentence naming the module. That is Rule 2 — a missing
 * upstream removes a FEATURE, never the page, and never silently — and it is
 * also most of the value: a student reading three questions they cannot answer
 * has had the experience this module exists to produce. The scored session is
 * what M06 adds, not the discomfort.
 *
 * What it must NOT do is disappear. A button that vanishes when an upstream is
 * down teaches a student the product is thin; a button that says what it would
 * do teaches them it is unfinished, which is true and recoverable.
 */

import { useEffect } from "react";

import { useStartDrill } from "../api";
import { Btn, Panel, SkeletonRows } from "../ui/primitives";
import type { DrillHandoff } from "../types";

export function DrillPanel({
  resumeId,
  claimId,
  onClose,
}: {
  resumeId: string;
  claimId: string;
  onClose: () => void;
}) {
  const drill = useStartDrill(resumeId);

  // Started on mount, from an effect.
  //
  // This was `if (drill.isIdle) drill.mutate(claimId)` in the render body — a
  // side effect during render, which React is allowed to discard. Under
  // StrictMode's double render the first call was thrown away with the
  // discarded render and the second saw `isIdle` already false, so nothing was
  // ever sent: the panel showed its skeleton and sat there. It looked like a
  // slow network and was a mutation that never left.
  //
  // The student already pressed the button that mounted this, so it starts by
  // itself; asking them to press a second one is a step with no decision in it.
  const { mutate } = drill;
  useEffect(() => {
    mutate(claimId);
  }, [mutate, claimId]);

  if (drill.isPending || drill.isIdle) return <SkeletonRows rows={3} />;

  if (drill.isError || !drill.data) {
    return (
      <Panel tone="sunken" className="px-4 py-3">
        <p className="text-sm text-ink-soft">
          Could not start a drill on this claim. The questions on the card above are the ones it
          would ask &mdash; they are worth answering out loud either way.
        </p>
        <div className="mt-2">
          <Btn type="button" variant="ghost" size="sm" onClick={onClose}>
            Close
          </Btn>
        </div>
      </Panel>
    );
  }

  return <Handoff handoff={drill.data} onClose={onClose} />;
}

function Handoff({ handoff, onClose }: { handoff: DrillHandoff; onClose: () => void }) {
  if (handoff.available && handoff.session_url) {
    return (
      <Panel className="border-brand-line bg-brand-soft px-4 py-3.5">
        <p className="text-sm font-medium text-ink">Your drill is ready.</p>
        <div className="mt-2.5 flex flex-wrap gap-2">
          <a href={handoff.session_url}>
            <Btn type="button" variant="primary" size="sm">
              Start it &rarr;
            </Btn>
          </a>
          <Btn type="button" variant="ghost" size="sm" onClick={onClose}>
            Not now
          </Btn>
        </div>
      </Panel>
    );
  }

  return (
    <Panel tone="sunken" className="px-4 py-3.5">
      <p className="text-sm font-medium text-ink">
        Answer these out loud, right now, before you read on.
      </p>
      <ol className="mt-2 space-y-1.5">
        {handoff.questions.map((question, index) => (
          <li key={question} className="text-sm text-ink-soft">
            <span className="mr-1.5 text-ink-faint" aria-hidden>
              {index + 1}.
            </span>
            {question}
          </li>
        ))}
      </ol>

      <p className="mt-3 text-xs text-ink-soft">
        If you stalled on any of them, that is the whole point of this screen &mdash; you found
        out here instead of in the room.
      </p>

      {handoff.explanation && (
        <p className="mt-2 text-xs text-ink-faint">
          {handoff.explanation} A scored two-minute session with follow-ups is what that module
          adds; the questions are already yours.
        </p>
      )}

      <div className="mt-3">
        <Btn type="button" variant="ghost" size="sm" onClick={onClose}>
          Close
        </Btn>
      </div>
    </Panel>
  );
}

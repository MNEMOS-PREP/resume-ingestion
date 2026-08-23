/**
 * One claim, as an interviewer sees it (§2.3 Screen 4, §8.1 `ClaimCard`).
 *
 * ── The microcopy rule this card exists to obey ─────────────────────────────
 *
 * §2.3 has a table of what not to write, and the principle under it is: show
 * the CONSEQUENCE, not a label.
 *
 *   Don't write            Write instead
 *   "Weak bullet detected" "An interviewer will ask: 94% on what split?"
 *   "ATS score: 62"        "12 claims found · 4 look risky"
 *   "Poorly written"       "This claim is hard to defend as written"
 *   "Add more keywords"    "Add the dataset size and your baseline"
 *
 * So the headline of a risky card is the QUESTIONS, not the score. The four
 * axes are available behind a toggle because a student who wants to argue with
 * the band should be able to see what produced it — but they are not the first
 * thing on the card, because a number is not actionable and a question is.
 */

import { useState } from "react";

import { AXES, AxisBar, BANDS } from "./bands";
import { Btn, Panel } from "../ui/primitives";
import type { ClaimProbe, ResumeClaim } from "../types";

const DEPTH_LABEL: Record<number, string> = {
  0: "opener",
  1: "how",
  2: "why",
  3: "what if",
};

export function ClaimCard({
  claim,
  selected,
  onSelect,
  onRewrite,
  onEdit,
}: {
  claim: ResumeClaim;
  selected: boolean;
  onSelect: () => void;
  onRewrite: () => void;
  onEdit: () => void;
}) {
  const [showScores, setShowScores] = useState(false);
  const band = BANDS[claim.risk_band];

  return (
    <Panel
      className={[
        "border-l-4 px-4 py-3.5 transition-shadow",
        band.edge,
        selected ? "shadow-raised ring-1 ring-brand-line" : "",
      ].join(" ")}
    >
      {/* Clicking anywhere on the claim text highlights it in the document
          (§8.3). A button rather than a div so it is keyboard-reachable. */}
      <button
        type="button"
        onClick={onSelect}
        className="w-full text-left"
        aria-pressed={selected}
      >
        <span className="sr-only">{band.screenReader}: </span>
        <span className="text-sm font-medium text-ink">{claim.text}</span>
      </button>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-2xs font-medium ${band.chip}`}
        >
          <span aria-hidden>{band.icon}</span>
          {band.label}
        </span>
        {claim.user_edited && (
          <span className="provenance text-confirmed">you edited this</span>
        )}
        {claim.quantifiers.map((quantifier) => (
          <span key={quantifier.span.start} className="provenance">
            {quantifier.raw}
            {quantifier.metric_hint ? ` · ${quantifier.metric_hint}` : ""}
          </span>
        ))}
      </div>

      {claim.probes.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-ink-soft">An interviewer will ask:</p>
          <ul className="mt-1.5 space-y-1.5">
            {claim.probes.map((probe) => (
              <ProbeRow key={probe.id} probe={probe} />
            ))}
          </ul>
        </div>
      )}

      {claim.risk_band !== "strong" && (
        <p className="mt-3 text-xs text-ink-soft">
          <span className="font-medium text-ink">Why it&rsquo;s {band.label.toLowerCase()}: </span>
          {whyThisBand(claim)}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {claim.risk_band !== "strong" && (
          <Btn type="button" variant="secondary" size="sm" onClick={onRewrite}>
            Rewrite it
          </Btn>
        )}
        <Btn type="button" variant="ghost" size="sm" onClick={onEdit}>
          Edit the bullet
        </Btn>
        <button
          type="button"
          onClick={() => setShowScores((previous) => !previous)}
          className="provenance hover:text-ink-soft"
          aria-expanded={showScores}
        >
          {showScores ? "hide the scoring" : "why this band?"}
        </button>
      </div>

      {showScores && (
        <div className="mt-3 space-y-1.5 border-t border-line pt-3">
          {AXES.map((axis) => (
            <AxisBar
              key={axis.key}
              label={axis.label}
              hint={axis.hint}
              value={(claim as unknown as Record<string, number>)[axis.key] ?? 0}
            />
          ))}
          <p className="pt-1 text-xs text-ink-faint">
            Each one is a property of the sentence, not of you &mdash; and each can be pointed at
            in the words above, which is what makes it something you can argue with.
          </p>
        </div>
      )}
    </Panel>
  );
}

function ProbeRow({ probe }: { probe: ClaimProbe }) {
  return (
    <li className="text-sm text-ink-soft">
      <span className="mr-1.5 text-ink-faint" aria-hidden>
        →
      </span>
      <span className="text-ink">{probe.question}</span>
      <span className="provenance ml-1.5" title={probe.rationale}>
        {DEPTH_LABEL[probe.depth]}
      </span>
      {probe.expects.length > 0 && (
        <span className="mt-0.5 block pl-5 text-xs text-ink-faint">
          A good answer covers: {probe.expects.join("; ")}.
        </span>
      )}
    </li>
  );
}

/**
 * The consequence, in one sentence, derived from which axis is weakest.
 *
 * Generic copy ("this claim is vague") tells the student nothing they cannot
 * see. Naming the missing thing is what §2.3's table asks for: "Add the dataset
 * size and your baseline", not "add more keywords".
 */
function whyThisBand(claim: ResumeClaim): string {
  if (claim.quantifiers.length === 0 && claim.specificity < 0.6) {
    return "there is no number in it and nothing named that an interviewer can hold on to, so the first question will be one you have to improvise an answer to.";
  }
  if (claim.verifiability <= 0.35) {
    return "there is nothing behind it anyone could go and check — no link, no measurement, no named organisation — so it rests entirely on you sounding convincing.";
  }
  if (claim.ownership_clarity <= 0.5) {
    return "it does not say which part was yours, and the follow-up to that is always the same: what did you personally do here?";
  }
  if (claim.quantifiers.length > 0) {
    return "a number with no baseline and no detail about how it was measured is the first thing a panel attacks.";
  }
  return "it is short on the detail that would let an interviewer ask a second question, which usually means they ask a harder first one.";
}

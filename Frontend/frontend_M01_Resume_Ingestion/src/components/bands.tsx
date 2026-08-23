/**
 * How a risk band looks, in one place.
 *
 * Spec §8.3: *"Risk bands use colour **and** an icon **and** a word — never
 * colour alone (8% of male users are colour-blind)."*
 *
 * Every band that appears anywhere on this frontend comes from here, because a
 * second definition is how one screen quietly loses the icon and the rule stops
 * being true on the screen nobody re-checked.
 *
 * ── The words, and why they are these words ─────────────────────────────────
 *
 * §2.3's microcopy table is explicit: attack the claim, never the person.
 * "risky" is a property of a sentence — it means an interviewer will push here
 * and the sentence has nothing to push back with. It does not mean the student
 * is a liar, and none of this copy is allowed to imply it.
 */

import type { ReactNode } from "react";

import type { RiskBand } from "../types";

export interface BandStyle {
  /** The word. Shown next to the icon, never replaced by it. */
  label: string;
  /** A glyph, for the fast scan and for a monochrome screen. */
  icon: string;
  /** What the band means, in the student's terms (§2.3 Screen 4). */
  meaning: string;
  /** Tailwind classes for the card edge and the chip. */
  chip: string;
  edge: string;
  /** Read out instead of the colour. */
  screenReader: string;
}

export const BANDS: Record<RiskBand, BandStyle> = {
  risky: {
    label: "Risky",
    icon: "▲",
    meaning: "You will likely be asked, and it is hard to defend as written.",
    chip: "border-contested-line bg-contested-soft text-contested",
    edge: "border-l-contested",
    screenReader: "Risky claim",
  },
  vague: {
    label: "Vague",
    icon: "●",
    meaning: "It will not hurt you. It will not help you either.",
    chip: "border-reported-line bg-reported-soft text-reported",
    edge: "border-l-reported",
    screenReader: "Vague claim",
  },
  strong: {
    label: "Strong",
    icon: "✓",
    meaning: "Specific, checkable, and clearly yours.",
    chip: "border-confirmed-line bg-confirmed-soft text-confirmed",
    edge: "border-l-confirmed",
    screenReader: "Strong claim",
  },
};

/** Worst first, which is the order the Claim Map groups them in. */
export const BAND_ORDER: RiskBand[] = ["risky", "vague", "strong"];

export function BandChip({ band, children }: { band: RiskBand; children?: ReactNode }) {
  const style = BANDS[band];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-2xs font-medium ${style.chip}`}
    >
      <span aria-hidden>{style.icon}</span>
      <span>{style.label}</span>
      {children}
    </span>
  );
}

/**
 * The four defensibility axes, as a label a student can argue with.
 *
 * Each is a property of the sentence that can be pointed at in the text, which
 * is what makes a band appealable rather than a verdict.
 */
export const AXES: { key: string; label: string; hint: string }[] = [
  {
    key: "specificity",
    label: "Specific",
    hint: "Names a technology, a number, and enough scope to mean something.",
  },
  {
    key: "verifiability",
    label: "Checkable",
    hint: "There is something behind it a person could go and look at.",
  },
  {
    key: "ownership_clarity",
    label: "Clearly yours",
    hint: "Says who did the work: I, we, or nobody at all.",
  },
  {
    key: "recency",
    label: "Recent",
    hint: "How long ago. No date at all counts as half, not as zero.",
  },
];

/** A 0–1 axis as a short bar. Labelled, because a bare bar is not a claim. */
export function AxisBar({ value, label, hint }: { value: number; label: string; hint: string }) {
  const percent = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2" title={hint}>
      <span className="w-24 shrink-0 text-2xs text-ink-soft">{label}</span>
      <span
        className="h-1 flex-1 overflow-hidden rounded-full bg-surface-sunken"
        role="img"
        aria-label={`${label}: ${percent} out of 100`}
      >
        <span
          className="block h-full rounded-full bg-ink-faint"
          style={{ width: `${Math.max(2, percent)}%` }}
        />
      </span>
      <span className="provenance w-7 shrink-0 text-right" data-numeric>
        {percent}
      </span>
    </div>
  );
}

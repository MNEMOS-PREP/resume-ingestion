/**
 * Red flags (§6.8, FR-1.13, §8.1 `RedFlagBanner`).
 *
 * ── The tone rule ───────────────────────────────────────────────────────────
 *
 * §6.8: *"Deterministic rules only (no LLM — false positives here are expensive
 * and hurtful)."*  And on a timeline gap specifically:
 *
 *   *"Gaps are normal (JEE drop year, health, family). The copy is: 'There's a
 *   gap from Jun 2023 to Feb 2024. That's completely fine — but they will ask.
 *   Here's a way to answer it.'"*
 *
 * So nothing here is a finding about the student. Each one is a thing that will
 * come up, with a way to answer it — which is why `suggested_answer` is
 * rendered as prominently as the flag itself rather than tucked behind a
 * disclosure. A flag with no answer attached is just an accusation.
 */

import { useState } from "react";

import { Panel, Section } from "../ui/primitives";
import type { RedFlag, RedFlagKind } from "../types";

const KIND_LABEL: Record<RedFlagKind, string> = {
  timeline_gap: "A gap they will ask about",
  chronology_conflict: "Dates that do not line up",
  claim_skill_mismatch: "A skill with no story attached",
  unverifiable_superlative: "An adjective doing a number's job",
  title_inflation: "A title with nothing under it",
  duplicate_project: "The same work, listed twice",
};

const SEVERITY_STYLE: Record<RedFlag["severity"], string> = {
  serious: "border-contested-line bg-contested-soft",
  notable: "border-reported-line bg-reported-soft",
  info: "border-line bg-surface-sunken",
};

const SEVERITY_ICON: Record<RedFlag["severity"], string> = {
  serious: "▲",
  notable: "●",
  info: "ⓘ",
};

export function RedFlagBanner({ flags }: { flags: RedFlag[] }) {
  const [open, setOpen] = useState(true);
  if (flags.length === 0) return null;

  const serious = flags.filter((flag) => flag.severity !== "info").length;

  return (
    <Section
      label="Worth having an answer ready for"
      meta={`${flags.length} thing${flags.length === 1 ? "" : "s"}`}
      action={
        <button
          type="button"
          onClick={() => setOpen((previous) => !previous)}
          className="provenance hover:text-ink-soft"
          aria-expanded={open}
        >
          {open ? "hide" : "show"}
        </button>
      }
    >
      {!open ? (
        <Panel tone="sunken" className="px-4 py-2.5">
          <p className="text-sm text-ink-soft">
            {flags.length} noted{serious > 0 ? `, ${serious} worth reading` : ""}.
          </p>
        </Panel>
      ) : (
        <div className="space-y-2">
          {flags.map((flag, index) => (
            <div
              key={`${flag.kind}-${index}`}
              className={`rounded-panel border px-4 py-3 ${SEVERITY_STYLE[flag.severity]}`}
            >
              <p className="flex items-center gap-2 text-sm font-medium text-ink">
                <span aria-hidden>{SEVERITY_ICON[flag.severity]}</span>
                {KIND_LABEL[flag.kind]}
              </p>
              <p className="mt-1 text-sm text-ink-soft">{flag.explanation}</p>
              {flag.suggested_answer && (
                <p className="mt-2 text-sm text-ink">
                  <span className="font-medium">How to handle it: </span>
                  {flag.suggested_answer}
                </p>
              )}
              {flag.spans.length > 0 && (
                <p className="provenance mt-1.5">
                  {flag.spans.map((span) => `“${span.text.trim().slice(0, 60)}”`).join(" · ")}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

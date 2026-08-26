/**
 * The workspace rail — what is on this resume, and what to open next.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2.3 Screen 4, §8.3
 *
 * ── What the rail is for, and what it must not become ───────────────────────
 *
 * It is a navigator, not a second copy of the claim list. Listing every claim
 * here and again in the centre is how the two drift, and it wastes the one
 * thing the rail actually has: permanence. It does not scroll with the claims,
 * so whatever sits here is visible the entire time a student is working —
 * which is exactly what §2.3's *"one thing to fix first"* card needs and never
 * got while it lived in a scrolling column.
 *
 * ── Counts, never a score ───────────────────────────────────────────────────
 *
 * §2.3's microcopy table forbids `ATS score: 62` outright, and §15 decision 1
 * recommends there is never a total on this screen at all. The rail is the most
 * tempting place in the module to put a ring with a number in it, because every
 * competitor has one there. What it shows instead is `12 claims · 4 risky`:
 * the same glanceability, and it decomposes into things a student can open.
 *
 * ── Two ways to cut the same claims ─────────────────────────────────────────
 *
 * **By risk** answers *"what do I fix first"* and is the default, because it is
 * the question a student three days from a drive is actually asking.
 *
 * **By section** answers *"how does my Projects section hold up"*, which is the
 * student's own mental model of their document — they wrote it in sections and
 * they will edit it in sections. It costs nothing: claims already carry
 * `section_id`.
 *
 * Neither is a filter over the other. They are the same claims, grouped twice.
 */

import { BANDS, BAND_ORDER } from "./bands";
import { FixFirstCard } from "./ClaimMap";
import { SECTION_LABEL } from "./sections";
import { Btn } from "../ui/primitives";
import type { ClaimListing, Resume, ResumeClaim, RiskBand, SectionKind } from "../types";

export type GroupBy = "risk" | "section";

/** `null` is the "Everything" row at the top of each list. */
export type Filter = { by: "risk"; band: RiskBand } | { by: "section"; kind: SectionKind } | null;

export function ClaimRail({
  resume,
  listing,
  groupBy,
  onGroupBy,
  filter,
  onFilter,
  onSelect,
  onReview,
}: {
  resume: Resume;
  listing: ClaimListing;
  groupBy: GroupBy;
  onGroupBy: (next: GroupBy) => void;
  filter: Filter;
  onFilter: (next: Filter) => void;
  onSelect: (claim: ResumeClaim) => void;
  onReview: () => void;
}) {
  const { claims, counts, total, fix_first: fixFirst } = listing;
  const risky = counts.risky ?? 0;

  /* Section kind per claim, resolved through the resume's own sections. A claim
     whose section_id resolves to nothing is `unknown` rather than dropped - the
     module's standing rule is that nothing the student wrote disappears because
     we could not classify it. */
  const kindOf = new Map(resume.sections.map((section) => [section.id, section.kind]));
  const sectionOf = (claim: ResumeClaim): SectionKind => kindOf.get(claim.section_id) ?? "unknown";

  /* Ordered by the document rather than by count, so the rail reads like a walk
     down their own resume. */
  const orderedKinds = [
    ...new Set(
      resume.sections
        .filter((section) => claims.some((claim) => claim.section_id === section.id))
        .map((section) => section.kind),
    ),
  ];
  if (claims.some((claim) => !kindOf.has(claim.section_id))) orderedKinds.push("unknown");

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
        <header>
          <p className="rule-label">This resume</p>
          {/* §2.3: "12 claims found · 4 look risky" - a count, never a score. */}
          <p className="mt-1 text-sm text-ink" data-numeric>
            <span className="font-semibold">{total}</span> claim{total === 1 ? "" : "s"}
            {risky > 0 && (
              <>
                {" · "}
                <span className="font-semibold text-contested">{risky}</span> risky
              </>
            )}
          </p>
          <p className="provenance mt-1 truncate" title={resume.filename ?? "pasted text"}>
            {resume.filename ?? "pasted text"}
          </p>
        </header>

        {fixFirst && (
          <div className="mt-4">
            <FixFirstCard compact claim={fixFirst} onSelect={() => onSelect(fixFirst)} />
          </div>
        )}

        <div className="mt-6">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="rule-label">Group by</p>
            <div
              role="group"
              aria-label="Group claims by"
              className="flex rounded-md border border-line p-0.5"
            >
              {(["risk", "section"] as GroupBy[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={groupBy === option}
                  onClick={() => {
                    onGroupBy(option);
                    onFilter(null); // A filter from the other axis means nothing here.
                  }}
                  className={[
                    "rounded px-2 py-0.5 text-2xs font-medium capitalize transition-colors",
                    groupBy === option
                      ? "bg-surface-sunken text-ink"
                      : "text-ink-faint hover:text-ink-soft",
                  ].join(" ")}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>

          <ul className="space-y-0.5">
            <RailRow
              label="Everything"
              count={total}
              active={filter === null}
              onClick={() => onFilter(null)}
            />

            {groupBy === "risk"
              ? BAND_ORDER.map((band) => {
                  const count = counts[band] ?? 0;
                  if (count === 0) return null;
                  return (
                    <RailRow
                      key={band}
                      icon={BANDS[band].icon}
                      label={BANDS[band].label}
                      count={count}
                      tone={band}
                      active={filter?.by === "risk" && filter.band === band}
                      onClick={() => onFilter({ by: "risk", band })}
                    />
                  );
                })
              : orderedKinds.map((kind) => {
                  const inSection = claims.filter((claim) => sectionOf(claim) === kind);
                  if (inSection.length === 0) return null;
                  const riskyHere = inSection.filter((c) => c.risk_band === "risky").length;
                  return (
                    <RailRow
                      key={kind}
                      label={SECTION_LABEL[kind]}
                      count={inSection.length}
                      note={riskyHere > 0 ? `${riskyHere} risky` : undefined}
                      active={filter?.by === "section" && filter.kind === kind}
                      onClick={() => onFilter({ by: "section", kind })}
                    />
                  );
                })}
          </ul>
        </div>
      </div>

      {/* Pinned. This was one of four ghost buttons competing with the
          diagnosis for the top of the centre column, and none of them is what a
          student came to this screen to do. */}
      <div className="shrink-0 border-t border-line px-4 py-3">
        <Btn type="button" variant="secondary" size="sm" onClick={onReview} className="w-full">
          Something&rsquo;s wrong &mdash; let me fix it
        </Btn>
        <p className="provenance mt-2 leading-relaxed">
          j / k move · Enter practise · r rewrite · e edit
        </p>
      </div>
    </div>
  );
}

function RailRow({
  icon,
  label,
  count,
  note,
  tone,
  active,
  onClick,
}: {
  icon?: string;
  label: string;
  count: number;
  note?: string;
  tone?: RiskBand;
  active: boolean;
  onClick: () => void;
}) {
  const iconTone =
    tone === "risky" ? "text-contested" : tone === "vague" ? "text-reported" : "text-confirmed";

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        className={[
          "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
          active
            ? "bg-surface-sunken font-medium text-ink"
            : "text-ink-soft hover:bg-surface-sunken hover:text-ink",
        ].join(" ")}
      >
        {/* Colour is never the only signal (§8.3) - the icon and the word both
            travel with it, and this row carries all three. */}
        {icon && (
          <span aria-hidden className={iconTone}>
            {icon}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {note && <span className="provenance shrink-0">{note}</span>}
        <span className="shrink-0 text-xs text-ink-faint" data-numeric>
          {count}
        </span>
      </button>
    </li>
  );
}

/**
 * Screen 4 — "Your resume, as an interviewer sees it" (§2.3, §8.1 `ClaimMap`).
 *
 * *"This is the screen students screenshot and send to friends. It must feel
 * like a diagnosis, not a report card."*
 *
 * ── What makes it a diagnosis ───────────────────────────────────────────────
 *
 * The summary line is `12 claims found · 4 look risky` — a count of things to
 * look at, not a mark out of a hundred. §2.3's microcopy table forbids the
 * alternative outright: *"'ATS score: 62' → we are not an ATS checker and must
 * never be mistaken for one."*  There is no total score on this screen and §15
 * decision 1 recommends there never is.
 *
 * ── Two forms, for the reason the module's other pairs have two ─────────────
 *
 * `ClaimList` takes claims; `ClaimMap` fetches them. M06 mounts the fetching
 * form with a resume id it already holds. M01's own workspace fetches once at
 * the top — the rail needs the counts and `fix_first`, the centre needs the
 * claims, and two components each calling `useClaims` is two chances for the
 * rail to say "4 risky" while the list beside it shows three.
 *
 * ── The one thing to fix first ──────────────────────────────────────────────
 *
 * Chosen by the server (`fix_first`), not here, so two screens cannot disagree
 * about which bullet a student should start with. It is the most PROMINENT
 * risky claim rather than the worst-scoring one, which is §6.6's whole argument
 * for prominence: a vague bullet at the bottom of page 2 is not the problem, a
 * vague bullet at the top of the first project is.
 *
 * ── Keyboard ────────────────────────────────────────────────────────────────
 *
 * §8.3: *"j/k to move between claims, Enter to open the drill, e to edit. Power
 * users exist even among students."*  The cursor walks the list AS RENDERED, so
 * with a band filter applied j/k stay inside it — a cursor that jumps to a
 * claim the student cannot see is worse than no cursor.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { useClaims, useRewriteClaim } from "../api";
import { BANDS, BAND_ORDER } from "./bands";
import { ClaimCard } from "./ClaimCard";
import { DrillPanel } from "./DrillPanel";
import { RewriteDiff } from "./RewriteDiff";
import { Empty, Panel, Section, SkeletonRows } from "../ui/primitives";
import type { ResumeClaim, RiskBand } from "../types";

/* ------------------------------------------------------------------ */
/*  The list                                                           */
/* ------------------------------------------------------------------ */

export function ClaimList({
  resumeId,
  claims,
  selectedId,
  onSelect,
  onEditClaim,
  keyboard = true,
}: {
  resumeId: string;
  claims: ResumeClaim[];
  /** The claim whose words are lit up in the document panel. */
  selectedId: string | null;
  onSelect: (claim: ResumeClaim) => void;
  onEditClaim: (claim: ResumeClaim) => void;
  /** Off for a second mounted copy, so two lists cannot both answer `j`. */
  keyboard?: boolean;
}) {
  const rewrite = useRewriteClaim(resumeId);
  const [openRewrite, setOpenRewrite] = useState<string | null>(null);
  const [openDrill, setOpenDrill] = useState<string | null>(null);

  const cursor = useMemo(
    () => claims.findIndex((claim) => claim.id === selectedId),
    [claims, selectedId],
  );

  const askForRewrite = useCallback(
    (claim: ResumeClaim) => {
      setOpenDrill(null);
      setOpenRewrite(claim.id);
      rewrite.mutate(claim.id);
    },
    [rewrite],
  );

  const startDrill = useCallback((claim: ResumeClaim) => {
    setOpenRewrite(null);
    setOpenDrill(claim.id);
  }, []);

  useEffect(() => {
    if (!keyboard) return;

    function onKey(event: KeyboardEvent) {
      // Never steal a key from someone typing into the confirmation editor.
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (!claims.length) return;

      // Nothing selected yet: j starts at the top, k at the bottom. Otherwise
      // the first keypress on a fresh page appears to do nothing.
      const at = cursor < 0 ? (event.key === "k" ? claims.length : -1) : cursor;
      const current = claims[cursor < 0 ? 0 : cursor];

      if (event.key === "j") {
        event.preventDefault();
        onSelect(claims[Math.min(at + 1, claims.length - 1)]);
      } else if (event.key === "k") {
        event.preventDefault();
        onSelect(claims[Math.max(at - 1, 0)]);
      } else if (event.key === "Enter") {
        event.preventDefault();
        startDrill(current);
      } else if (event.key === "r") {
        event.preventDefault();
        askForRewrite(current);
      } else if (event.key === "e") {
        event.preventDefault();
        onEditClaim(current);
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keyboard, claims, cursor, onSelect, askForRewrite, startDrill, onEditClaim]);

  if (claims.length === 0) {
    return (
      <Empty title="Nothing in this group">
        Every claim we read sits under one of the other bands. Clear the filter to see them.
      </Empty>
    );
  }

  return (
    <div>
      {BAND_ORDER.map((band) => {
        const inBand = claims.filter((claim) => claim.risk_band === band);
        if (inBand.length === 0) return null;
        return (
          <Section
            key={band}
            label={`${BANDS[band].icon} ${BANDS[band].label.toUpperCase()} — ${BANDS[band].meaning}`}
            meta={`${inBand.length}`}
          >
            <div className="space-y-2.5">
              {inBand.map((claim) => (
                <div key={claim.id} id={`claim-${claim.id}`} className="scroll-mt-4">
                  <ClaimCard
                    claim={claim}
                    selected={claim.id === selectedId}
                    onSelect={() => onSelect(claim)}
                    onRewrite={() => askForRewrite(claim)}
                    onEdit={() => onEditClaim(claim)}
                    onDrill={() => startDrill(claim)}
                  />
                  {openDrill === claim.id && (
                    <div className="mt-2">
                      <DrillPanel
                        resumeId={resumeId}
                        claimId={claim.id}
                        onClose={() => setOpenDrill(null)}
                      />
                    </div>
                  )}
                  {openRewrite === claim.id && (
                    <div className="mt-2">
                      {rewrite.isPending && <SkeletonRows rows={3} />}
                      {rewrite.data && rewrite.data.claim_id === claim.id && (
                        <RewriteDiff
                          suggestion={rewrite.data}
                          onClose={() => setOpenRewrite(null)}
                        />
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Section>
        );
      })}

      <p className="provenance mt-8">
        j / k to move · Enter to practise · r to rewrite · e to edit
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  The fetching form, for modules that hold only an id                */
/* ------------------------------------------------------------------ */

export function ClaimMap({
  resumeId,
  onSelectSpan,
  onEditClaim,
}: {
  resumeId: string;
  onSelectSpan: (claim: ResumeClaim) => void;
  onEditClaim: (claim: ResumeClaim) => void;
}) {
  const listing = useClaims(resumeId);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const claims = useMemo(() => listing.data?.claims ?? [], [listing.data]);

  const select = useCallback(
    (claim: ResumeClaim) => {
      setSelectedId(claim.id);
      onSelectSpan(claim);
    },
    [onSelectSpan],
  );

  if (listing.isLoading) return <SkeletonRows rows={6} />;

  if (!listing.data || claims.length === 0) {
    return (
      <Empty title="No claims yet">
        Nothing here asserts something an interviewer could push on. Add a project bullet that says
        what you built and what changed, and it will show up here.
      </Empty>
    );
  }

  const { counts, total, fix_first: fixFirst } = listing.data;
  const risky = counts.risky ?? 0;

  return (
    <div>
      <header className="mb-6">
        <h2 className="text-title font-semibold text-ink">
          Your resume, as an interviewer sees it
        </h2>
        {/* §2.3: "12 claims found · 4 look risky" — a count, never a score. */}
        <p className="mt-1 text-sm text-ink-soft" data-numeric>
          {total} claim{total === 1 ? "" : "s"} found
          {risky > 0 ? ` · ${risky} look${risky === 1 ? "s" : ""} risky` : " · none look risky"}
        </p>
      </header>

      {fixFirst && <FixFirstCard claim={fixFirst} onSelect={() => select(fixFirst)} />}

      <ClaimList
        resumeId={resumeId}
        claims={claims}
        selectedId={selectedId}
        onSelect={select}
        onEditClaim={onEditClaim}
      />
    </div>
  );
}

/**
 * §2.3's card: *"Bullet 3 in 'Crop Disease Detection'. It's your most prominent
 * claim and your least defensible one."*
 *
 * In the workspace this is pinned in the rail, where it is permanently in view
 * rather than scrolling away exactly when the student starts reading the thing
 * it points at. `compact` is that placement: same words, no sticky behaviour,
 * because the rail does not scroll with the claims.
 */
export function FixFirstCard({
  claim,
  onSelect,
  compact = false,
}: {
  claim: ResumeClaim;
  onSelect: () => void;
  compact?: boolean;
}) {
  return (
    <Panel
      className={[
        "border-brand-line bg-brand-soft px-4 py-3.5",
        compact
          ? ""
          : // Sticky at the BOTTOM on a narrow screen, static in the flow on a
            // wide one (§8.3) — on a phone the card scrolls away exactly when
            // the student starts reading what it points at.
            "sticky bottom-2 z-20 mb-8 shadow-raised lg:static lg:z-auto lg:shadow-none",
      ].join(" ")}
    >
      <p className="flex items-center gap-2 text-sm font-semibold text-ink">
        <span aria-hidden>🎯</span> The one thing to fix first
      </p>
      <button type="button" onClick={onSelect} className="mt-1 text-left">
        <p className="text-sm text-ink">&ldquo;{claim.text}&rdquo;</p>
      </button>
      <p className="mt-1.5 text-xs text-ink-soft">
        It is the most visible claim on the page that is also the hardest to defend &mdash; which
        makes it the one an interviewer reaches first.
      </p>
    </Panel>
  );
}

/** Counts by band, for a header or a summary bar. */
export function BandSummary({ counts }: { counts: Record<RiskBand, number> }) {
  return (
    <div className="flex flex-wrap gap-3">
      {BAND_ORDER.map((band) => (
        <span key={band} className="inline-flex items-center gap-1.5 text-sm text-ink-soft">
          <span aria-hidden className="text-ink-faint">
            {BANDS[band].icon}
          </span>
          <span data-numeric>{counts[band] ?? 0}</span>
          <span>{BANDS[band].label.toLowerCase()}</span>
        </span>
      ))}
    </div>
  );
}
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
 * users exist even among students."*  `Enter` opens the rewrite rather than a
 * drill, because the drill is M06 and M06 is not built — a key that silently
 * does nothing is worse than one that does the nearest real thing.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useClaims, useRewriteClaim } from "../api";
import { BANDS, BAND_ORDER } from "./bands";
import { ClaimCard } from "./ClaimCard";
import { DrillPanel } from "./DrillPanel";
import { RewriteDiff } from "./RewriteDiff";
import { Empty, Panel, Section, SkeletonRows } from "../ui/primitives";
import type { ResumeClaim, RiskBand } from "../types";

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
  const rewrite = useRewriteClaim(resumeId);
  const [cursor, setCursor] = useState(0);
  const [openRewrite, setOpenRewrite] = useState<string | null>(null);
  const [openDrill, setOpenDrill] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);

  const claims = useMemo(() => listing.data?.claims ?? [], [listing.data]);

  const select = useCallback(
    (index: number) => {
      const claim = claims[index];
      if (!claim) return;
      setCursor(index);
      onSelectSpan(claim);
    },
    [claims, onSelectSpan],
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
    function onKey(event: KeyboardEvent) {
      // Never steal a key from someone typing into the confirmation editor.
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (!claims.length) return;

      if (event.key === "j") {
        event.preventDefault();
        select(Math.min(cursor + 1, claims.length - 1));
      } else if (event.key === "k") {
        event.preventDefault();
        select(Math.max(cursor - 1, 0));
      } else if (event.key === "Enter") {
        event.preventDefault();
        // §8.3: "Enter to open the drill". It used to open the rewrite, with a
        // comment explaining that the drill was M06 and M06 was not built. The
        // drill affordance exists now and degrades honestly on its own, so the
        // binding does what the spec says.
        startDrill(claims[cursor]);
      } else if (event.key === "r") {
        event.preventDefault();
        askForRewrite(claims[cursor]);
      } else if (event.key === "e") {
        event.preventDefault();
        onEditClaim(claims[cursor]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [claims, cursor, select, askForRewrite, startDrill, onEditClaim]);

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
    <div ref={container}>
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

      {fixFirst && <FixFirstCard claim={fixFirst} onSelect={() => onSelectSpan(fixFirst)} />}

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
              {inBand.map((claim) => {
                const index = claims.indexOf(claim);
                return (
                  <div key={claim.id}>
                    <ClaimCard
                      claim={claim}
                      selected={index === cursor}
                      onSelect={() => select(index)}
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
                );
              })}
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

/**
 * §2.3's sticky card: *"Bullet 3 in 'Crop Disease Detection'. It's your most
 * prominent claim and your least defensible one."*
 *
 * Sticky at the bottom on mobile per §8.3, static in the flow above the map on
 * a wide screen where it does not have to compete for the same space.
 */
function FixFirstCard({ claim, onSelect }: { claim: ResumeClaim; onSelect: () => void }) {
  return (
    // Sticky at the BOTTOM on a narrow screen, static in the flow above the map
    // on a wide one. §8.3 asks for the first because on a phone the card
    // scrolls away exactly when the student starts reading the thing it is
    // pointing at, and the whole job of the card is to still be there then.
    <Panel className="sticky bottom-2 z-20 mb-8 border-brand-line bg-brand-soft px-4 py-3.5 shadow-raised lg:static lg:z-auto lg:shadow-none">
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

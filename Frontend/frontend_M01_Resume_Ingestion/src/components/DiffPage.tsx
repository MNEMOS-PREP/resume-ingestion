/**
 * What changed between two uploads (FR-1.15, §7).
 *
 * *"Support re-upload with a diff view ('3 new claims, 1 removed')."*
 *
 * The endpoint and the `useDiff` hook both existed for a while with nothing
 * rendering them, which is the mirror image of the rule `api.ts` states — one
 * hook per endpoint, none without one. A student who rewrote their resume and
 * uploaded it again was told nothing at all about whether it had worked.
 *
 * ── The line that matters ───────────────────────────────────────────────────
 *
 * `changed` — a bullet whose text survived but whose band moved. §6 calls it
 * out: *"a bullet the student rewrote to add a number is the single most
 * useful thing a re-upload can report"*, and a text-only comparison would call
 * it unchanged. It is first on this screen for that reason.
 */

import { Link, useParams, useSearchParams } from "react-router-dom";

import { useCandidateResumes, useDiff, useResume } from "../api";
import { BANDS } from "./bands";
import { useCandidateId } from "./candidate-hook";
import { Btn, Empty, Panel, Section, SkeletonRows } from "../ui/primitives";
import type { RiskBand } from "../types";

export function DiffPage() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const [params] = useSearchParams();
  const candidateId = useCandidateId();

  const newer = useResume(resumeId);
  const history = useCandidateResumes(candidateId);

  // Compare against whatever was asked for, or the next-most-recent upload —
  // which is what "what changed?" means when nobody said otherwise.
  const explicit = params.get("against");
  const previous = history.data?.find((r) => r.id !== resumeId);
  const against = explicit ?? previous?.id;

  const diff = useDiff(resumeId, against);

  if (newer.isLoading || history.isLoading) return <SkeletonRows rows={5} />;

  if (!against) {
    return (
      <Empty title="Nothing to compare against">
        This is the only resume stored for this candidate, so there is no earlier
        version to diff. Upload a revised copy and this screen will show what moved.
        <div className="mt-3">
          <Link to="/resume" className="text-sm font-medium text-brand hover:text-brand-hover">
            Upload another &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  if (diff.isLoading) return <SkeletonRows rows={5} />;
  if (diff.isError || !diff.data) {
    return (
      <Empty title="Could not compare these two">
        They may belong to different candidates, or one of them may have been deleted.
      </Empty>
    );
  }

  const data = diff.data;
  const nothingMoved =
    data.added.length === 0 && data.removed.length === 0 && data.changed.length === 0;

  return (
    <>
      <header className="mb-7">
        <p className="rule-label">since your last upload</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">{data.summary}</h1>
        {data.identical_content && (
          <p className="mt-2 text-sm text-ink-soft">
            These two are byte-for-byte the same file, so nothing could have changed. If you
            meant to upload a revision, check you exported it before picking the file.
          </p>
        )}
      </header>

      {nothingMoved && !data.identical_content && (
        <Panel tone="sunken" className="mb-8 px-4 py-3">
          <p className="text-sm text-ink-soft">
            The file changed but no claim did &mdash; the edits were outside the bullets we read,
            or they did not change what any of them assert.
          </p>
        </Panel>
      )}

      {/* First, because it is the most useful thing a re-upload can report. */}
      {data.changed.length > 0 && (
        <Section label="Rewritten" meta={`${data.changed.length}`}>
          <div className="space-y-2">
            {data.changed.map((entry) => (
              <Panel key={entry.text} className="px-4 py-3">
                <p className="text-sm text-ink">{entry.text}</p>
                <p className="mt-1.5 flex items-center gap-2 text-xs">
                  <BandWord band={entry.risk_band_before} />
                  <span aria-hidden className="text-ink-faint">
                    &rarr;
                  </span>
                  <BandWord band={entry.risk_band_after} />
                  <span className="text-ink-soft">{verdict(entry)}</span>
                </p>
              </Panel>
            ))}
          </div>
        </Section>
      )}

      {data.added.length > 0 && (
        <Section label="New" meta={`${data.added.length}`}>
          <ClaimList entries={data.added} />
        </Section>
      )}

      {data.removed.length > 0 && (
        <Section label="Gone" meta={`${data.removed.length}`}>
          <ClaimList entries={data.removed} muted />
          <p className="mt-2 text-xs text-ink-faint">
            Removed claims keep their history &mdash; anything you already practised against them
            is still on your record.
          </p>
        </Section>
      )}

      <div className="flex flex-wrap gap-3 border-t border-line pt-5">
        <Link to={`/resumes/${resumeId}`}>
          <Btn type="button" variant="primary">
            Back to the claim map
          </Btn>
        </Link>
        <span className="provenance self-center">
          {data.before.slice(0, 8)} &rarr; {data.after.slice(0, 8)}
        </span>
      </div>
    </>
  );
}

function ClaimList({
  entries,
  muted = false,
}: {
  entries: { text: string; risk_band: RiskBand }[];
  muted?: boolean;
}) {
  return (
    <div className="space-y-2">
      {entries.map((entry) => (
        <Panel key={entry.text} className="px-4 py-2.5">
          <p className={`text-sm ${muted ? "text-ink-soft line-through" : "text-ink"}`}>
            {entry.text}
          </p>
          <p className="mt-1">
            <BandWord band={entry.risk_band} />
          </p>
        </Panel>
      ))}
    </div>
  );
}

/** Colour, icon and word — the same three signals as everywhere else (§8.3). */
function BandWord({ band }: { band: RiskBand }) {
  const style = BANDS[band];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-2xs font-medium ${style.chip}`}
    >
      <span aria-hidden>{style.icon}</span>
      {style.label}
    </span>
  );
}

const ORDER: RiskBand[] = ["risky", "vague", "strong"];

/**
 * Whether the rewrite helped, said plainly.
 *
 * A student who added a measurement and watched a bullet move out of "risky"
 * should be told that is what happened — it is the moment the whole module is
 * trying to produce.
 */
function verdict(entry: { risk_band_before: RiskBand; risk_band_after: RiskBand }): string {
  const before = ORDER.indexOf(entry.risk_band_before);
  const after = ORDER.indexOf(entry.risk_band_after);
  if (after > before) return "— that rewrite helped.";
  if (after < before) return "— this one got harder to defend, not easier.";
  return "";
}

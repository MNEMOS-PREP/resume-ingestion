/**
 * Is the parser getting better or worse? (AC-1.7, §13)
 *
 * *"Confirmation screen edit rate; tracked; > 40% means the parser needs
 * work."*  The endpoint that answers this has existed for a while and the
 * release checklist tells you to curl it, which means the number is looked at
 * by whoever remembers to. A criterion nobody can see is one that stops being
 * a criterion.
 *
 * ── This is an operator screen, and it does not pretend otherwise ───────────
 *
 * Nothing here is about one student. It is the parser's own report card, and
 * the verdict on the top line is the SERVER'S — `parser_needs_work` is
 * computed there against §13's threshold, so this page and the release
 * checklist cannot disagree about whether the bar was met.
 *
 * ── The three gaps that are rendered rather than hidden ─────────────────────
 *
 * PII encryption, virus scanning and the object store are reported honestly,
 * including when the answer is "no". §6.1 asks for a virus scan and there is
 * not one; a stubbed "scanned ✓" would be worse than the honest gap, and an
 * operator who has not set the PII key should be able to find that out without
 * reading logs.
 */

import { useQuality } from "../api";
import { Empty, Field, Panel, Pill, Rows, Section, SkeletonRows } from "../ui/primitives";

export function QualityPage() {
  const quality = useQuality();

  if (quality.isLoading) return <SkeletonRows rows={6} />;

  if (quality.isError || !quality.data) {
    return (
      <Empty title="The quality report is unreachable">
        <code className="provenance">GET /v1/quality</code> did not answer. The backend is either
        down or running a build from before this endpoint existed.
      </Empty>
    );
  }

  const data = quality.data;
  const pct = Math.round(data.edit_rate * 100);
  const target = Math.round(data.edit_rate_target * 100);

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">AC-1.7 · parser quality</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">
          {data.confirmed === 0
            ? "Nobody has finished the confirmation pass yet"
            : `${pct}% of students corrected something`}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          {data.confirmed === 0 ? (
            <>
              The edit rate is measured over confirmed resumes only. A student who never reached
              the confirmation screen has not declined to correct anything, and counting them as
              agreement is how an edit rate flatters itself.
            </>
          ) : (
            <>
              Over {data.confirmed} confirmed resume{data.confirmed === 1 ? "" : "s"}. §13 puts the
              line at {target}%: above it, the parser is being overruled often enough that the
              cheapest fix is in the parser rather than in the screen.
            </>
          )}
        </p>
      </header>

      {data.confirmed > 0 && (
        <Section label="The number">
          <Panel
            className={`px-4 py-3.5 ${data.parser_needs_work ? "border-contested-line bg-contested-soft" : "border-confirmed-line bg-confirmed-soft"}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={data.parser_needs_work ? "contested" : "confirmed"}>
                {data.parser_needs_work ? "over the line" : "within the line"}
              </Pill>
              <span className="provenance">
                {pct}% edited · target under {target}%
              </span>
            </div>
            <EditRateBar rate={data.edit_rate} target={data.edit_rate_target} />
            <p className="mt-2.5 text-sm text-ink-soft">
              {data.parser_needs_work
                ? "Students are correcting us more often than the spec allows for. Look at what they are correcting below — the field with the most rows is the one to fix first."
                : "Students are mostly agreeing with the read. The confirmation pass is doing what it is for rather than covering for the parser."}
            </p>
          </Panel>
        </Section>
      )}

      <Section label="What gets corrected" meta={`${data.corrections} in total`}>
        {Object.keys(data.corrections_by_target).length === 0 ? (
          <Panel tone="sunken" className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              No corrections recorded. Genuinely good on a large corpus and meaningless on a small
              one &mdash; there are {data.resumes} resume
              {data.resumes === 1 ? "" : "s"} here.
            </p>
          </Panel>
        ) : (
          <Panel className="px-4 py-3">
            <Rows>
              {Object.entries(data.corrections_by_target)
                .sort((a, b) => b[1] - a[1])
                .map(([key, count]) => (
                  <Field key={key} label={key.replace(/[._]/g, " ")}>
                    {count}
                  </Field>
                ))}
            </Rows>
            <p className="mt-2.5 text-xs text-ink-faint">
              Ordered by how often each field was overruled, which is the order in which fixing one
              is worth somebody an afternoon.
            </p>
          </Panel>
        )}
      </Section>

      <Section label="The corpus">
        <Panel tone="sunken" className="px-4 py-3">
          <dl className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
            <Fact label="Resumes read">{data.resumes}</Fact>
            <Fact label="Confirmed by a student">{data.confirmed}</Fact>
            <Fact label="Flagged needs-review">{data.needs_review}</Fact>
            <Fact label="Read from an image (OCR)">{data.ocr_used}</Fact>
            <Fact label="Two-column layouts">{data.two_column}</Fact>
            <Fact label="Failed to parse">{data.failed}</Fact>
          </dl>
        </Panel>
      </Section>

      {Object.keys(data.failures_by_code).length > 0 && (
        <Section label="What is failing, and how" meta={`${data.failed} upload${data.failed === 1 ? "" : "s"}`}>
          <Panel className="px-4 py-3">
            <Rows>
              {Object.entries(data.failures_by_code)
                .sort((a, b) => b[1] - a[1])
                .map(([code, count]) => (
                  <Field key={code} label={code}>
                    {count}
                  </Field>
                ))}
            </Rows>
            <p className="mt-2.5 text-xs text-ink-faint">
              Every one of these ends at the paste box, so nobody was stranded &mdash; but a code
              climbing this list is a file type that is failing in the wild.
            </p>
          </Panel>
        </Section>
      )}

      <Section label="How this deployment is set up">
        <Panel tone="sunken" className="px-4 py-3">
          <Rows>
            <Field label="contact block encrypted at rest">
              <Honest ok={data.pii_encrypted_at_rest}>
                {data.pii_encrypted_at_rest ? "yes" : "no — M01_PII_KEY is unset"}
              </Honest>
            </Field>
            <Field label="uploads virus-scanned">
              <Honest ok={data.virus_scan}>
                {data.virus_scan ? "yes" : "no — §6.1 asks for one and there is not one"}
              </Honest>
            </Field>
            <Field label="object store">{data.object_store}</Field>
            <Field label="retention">
              {data.retention.retention_days} days · {data.retention.rationale}
            </Field>
            <Field label="default disclosure">{data.retention.default_disclosure}</Field>
          </Rows>
          <p className="mt-2.5 text-xs text-ink-faint">
            Reported rather than assumed, including when the answer is no. A stubbed
            &ldquo;scanned&rdquo; would be worse than the gap it hides, because the gap is at least
            actionable.
          </p>
        </Panel>
      </Section>
    </>
  );
}

/**
 * The rate against §13's line, drawn.
 *
 * A bar rather than a number alone because the question is never "what is the
 * rate", it is "are we over the line" — and a marked threshold answers that
 * without arithmetic. Every value is also written out in words above, so the
 * bar carries nothing that colour alone has to convey (§8.3).
 */
function EditRateBar({ rate, target }: { rate: number; target: number }) {
  const width = Math.min(100, Math.round(rate * 100));
  const mark = Math.min(100, Math.round(target * 100));
  const over = rate > target;

  return (
    <div className="relative mt-3 h-2 w-full rounded-full bg-surface-sunken" aria-hidden>
      <div
        className={`h-2 rounded-full ${over ? "bg-contested" : "bg-confirmed"}`}
        style={{ width: `${width}%` }}
      />
      <div
        className="absolute top-[-3px] h-3.5 w-px bg-ink-faint"
        style={{ left: `${mark}%` }}
        title={`§13 threshold: ${mark}%`}
      />
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1 last:border-0">
      <dt className="text-ink-soft">{label}</dt>
      <dd className="provenance text-right">{children}</dd>
    </div>
  );
}

/** A "no" that reads as a known gap rather than as a rendering failure. */
function Honest({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return <span className={ok ? "text-confirmed" : "text-reported"}>{children}</span>;
}

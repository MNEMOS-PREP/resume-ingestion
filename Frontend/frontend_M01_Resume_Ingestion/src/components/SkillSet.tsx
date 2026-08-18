/**
 * The read-back: what we found on the resume, and where each id came from.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §5, §8, FR-1.7
 *
 * ── The one thing this file exists to get right ──────────────────────────────
 *
 * **A skill the ontology could not map is still on the resume.** The student
 * wrote it. Dropping it silently means this screen contradicts their own
 * document with no explanation, which reads as a broken parser — and the fix
 * they will reach for is editing their resume to please the machine.
 *
 * So unmapped skills get their own group, visibly hatched and colourless:
 * outside the scale rather than at the bottom of it. And every mapped skill
 * carries whether M04 confirmed its id or M02's offline table guessed it,
 * because an id is a licence for M05 to build questions on and M13 to score
 * against.
 *
 * ── Why there is no bar on this screen ───────────────────────────────────────
 *
 * M01 does not measure anything. It reads claims; it does not test them. A
 * mastery bar here — even an empty one — would imply a measurement this module
 * has no business making, and the platform has a component for that
 * (`MasteryBar`) precisely so it appears only where a measurement exists.
 */

import type { ConceptSource, Resume, ScannedAgainst } from "../types";
import { Panel, Pill, Section } from "../ui/primitives";

const SOURCE_COPY: Record<
  ConceptSource,
  { label: string; tone: "confirmed" | "reported"; hint: string }
> = {
  m04: {
    label: "ontology",
    tone: "confirmed",
    hint: "M04 resolved this label to a concept in the skill graph. Anything downstream can test it.",
  },
  offline_fallback: {
    label: "guessed offline",
    tone: "reported",
    hint:
      "M04 was unreachable, so this id comes from a five-entry table in M01. " +
      "It has not been confirmed to exist in the ontology.",
  },
};

export function ScanSourceNote({ scannedAgainst }: { scannedAgainst: ScannedAgainst }) {
  if (scannedAgainst === "m04") {
    return (
      <p className="text-xs text-ink-soft">
        Scanned against M04&rsquo;s full concept ontology.
      </p>
    );
  }
  return (
    <p className="text-xs text-ink-soft">
      Scanned against M01&rsquo;s five-concept offline lexicon, because M04 was unreachable.{" "}
      <strong className="font-medium text-ink">
        Skills outside those five were not looked for at all
      </strong>{" "}
      &mdash; a short list here means an outage, not a thin resume.
    </p>
  );
}

export function SkillSet({ resume }: { resume: Resume }) {
  const mapped = resume.parsed_skills.filter((s) => s in resume.resolved_concepts);
  const confirmedCount = mapped.filter((s) => resume.concept_source[s] === "m04").length;

  return (
    <>
      <Section
        label="Skills we found"
        meta={
          mapped.length > 0
            ? `${confirmedCount}/${mapped.length} confirmed by the ontology`
            : undefined
        }
      >
        {mapped.length === 0 ? (
          <div className="rounded-panel border border-dashed border-line-strong px-4 py-5">
            <p className="text-sm font-medium text-ink">Nothing mapped to a concept</p>
            <p className="mt-1 max-w-xl text-sm text-ink-soft">
              Either the resume text does not mention anything in the lexicon, or the scan ran
              against the five-concept fallback. Check the note above &mdash; those look identical
              from here and are very different problems.
            </p>
          </div>
        ) : (
          <Panel className="px-4 py-3">
            <div className="flex flex-wrap gap-1.5">
              {mapped.map((skill) => {
                const copy = SOURCE_COPY[resume.concept_source[skill]];
                return (
                  <span key={skill} className="inline-flex items-center gap-1.5">
                    <span className="text-sm text-ink">{skill}</span>
                    <Pill
                      tone={copy.tone}
                      title={`${resume.resolved_concepts[skill]} · ${copy.hint}`}
                    >
                      {copy.label}
                    </Pill>
                  </span>
                );
              })}
            </div>
          </Panel>
        )}
      </Section>

      {resume.unresolved_skills.length > 0 && (
        <Section label="On the resume, mapped to nothing">
          <Panel tone="sunken" className="px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              {resume.unresolved_skills.map((skill) => (
                <span
                  key={skill}
                  className="untestable-mark inline-flex items-center px-2 py-0.5 text-sm text-ink-soft"
                >
                  {skill}
                </span>
              ))}
            </div>
            <p className="mt-2.5 text-xs text-ink-soft">
              These are on the resume and the ontology has no concept for them, so nothing
              downstream can build a question from them yet. They are listed rather than dropped
              &mdash; a skill we cannot test is still a skill you claimed, and a read-back that
              quietly loses it reads as a broken parser.
            </p>
          </Panel>
        </Section>
      )}
    </>
  );
}

/**
 * What the module is named after, and does not do.
 *
 * Kept on the screen rather than in a backlog file. Anyone who opens this
 * module expecting the spec's product — scored, probe-generating, span-cited
 * claims — should learn in one glance that it is not here, rather than
 * concluding the extraction is broken.
 */
export function ClaimsNotBuilt() {
  return (
    <Section label="Not built yet">
      <Panel tone="sunken" className="px-4 py-3.5">
        <p className="text-sm text-ink-soft">
          This module is named <em>Claim Extraction</em> and extracts no claims. Nothing below{" "}
          <code className="provenance">SkillMention</code> in the spec&rsquo;s §5 exists.
        </p>
        <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
          <li>
            <strong className="font-medium text-ink">SourceSpan</strong> &mdash; &ldquo;the atom of
            traceability; everything downstream cites one of these&rdquo;. Without it there is no
            PDF highlight, no verifiable quote for M13, and nothing for M19&rsquo;s ledger. First
            thing to build, and it should use{" "}
            <code className="provenance">ai_core.evidence.EvidenceSpan</code> rather than a second
            type.
          </li>
          <li>
            <strong className="font-medium text-ink">ResumeClaim + defensibility scores</strong>{" "}
            &mdash; specificity, verifiability, ownership clarity, recency, and the red/yellow/green
            band. Four of five downstream modules read claims, so none of them can consume M01
            today.
          </li>
          <li>
            <strong className="font-medium text-ink">Probe generation</strong> &mdash; the 1&ndash;3
            escalating questions per claim that are this module&rsquo;s product for M06.
          </li>
          <li>
            <strong className="font-medium text-ink">Sections, entities, PDF and DOCX</strong>{" "}
            &mdash; pasted text is the only input, and it is one of three the spec requires.
          </li>
        </ul>
        <p className="mt-2.5 text-xs text-ink-faint">
          One gap is a liability rather than a missing feature: FR-1.17 (P0) requires the contact
          block to be PII-classed and withheld from logs and models. The whole resume currently
          sits in one column and is returned verbatim by two endpoints.
        </p>
      </Panel>
    </Section>
  );
}

/**
 * The read-back: what we found on the resume, and where each id came from.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §5, §6.4, §8, FR-1.7
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
 * carries whether the ontology confirmed its id or an offline table produced
 * it, because an id is a licence for M05 to build questions on and M13 to score
 * against.
 *
 * ── What `context` adds ─────────────────────────────────────────────────────
 *
 * §6.4 splits a claim of *familiarity* from a claim of *use*: "Python" on a
 * skills line is the first, "built a route planner in Python" is the second,
 * and M05 asks much harder questions about the second. That distinction is
 * shown here because it is the most useful thing on the screen for a student
 * deciding what to revise — a skill listed and never used is the easiest thing
 * on a resume to get caught on.
 *
 * ── Why there is no bar on this screen ───────────────────────────────────────
 *
 * M01 does not measure anything. It reads claims; it does not test them. A
 * mastery bar here — even an empty one — would imply a measurement this module
 * has no business making, and the platform has a component for that
 * (`MasteryBar`) precisely so it appears only where a measurement exists.
 */

import type { ConceptSource, Resume, ScannedAgainst, SkillContext } from "../types";
import { Panel, Pill, Section } from "../ui/primitives";

const SOURCE_COPY: Record<
  ConceptSource,
  { label: string; tone: "confirmed" | "reported"; hint: string }
> = {
  m04: {
    label: "ontology",
    tone: "confirmed",
    hint: "The skill graph resolved this label to a concept. Anything downstream can test it.",
  },
  offline_fallback: {
    label: "guessed offline",
    tone: "reported",
    hint:
      "The skill graph was unreachable, so this id comes from a five-entry table in M01. " +
      "It has not been confirmed to exist in the ontology.",
  },
};

const CONTEXT_COPY: Record<SkillContext, { label: string; hint: string }> = {
  experience_body: {
    label: "used at work",
    hint: "You described using this in a role. Expect the hardest questions here.",
  },
  project_tech: {
    label: "used in a project",
    hint: "You described building something with this, so expect to be asked how.",
  },
  education: {
    label: "coursework",
    hint: "This came from your education section, so expect conceptual questions.",
  },
  skills_list: {
    label: "listed only",
    hint: "This appears only in your skills list, with no story attached to it.",
  },
};

export function ScanSourceNote({ scannedAgainst }: { scannedAgainst: ScannedAgainst }) {
  if (scannedAgainst === "m04") {
    return (
      <p className="text-xs text-ink-soft">Scanned against the full concept ontology.</p>
    );
  }
  return (
    <p className="text-xs text-ink-soft">
      Scanned against M01&rsquo;s five-concept offline lexicon, because the skill graph was
      unreachable.{" "}
      <strong className="font-medium text-ink">
        Skills outside those five were not looked for at all
      </strong>{" "}
      &mdash; a short list here means an outage, not a thin resume.
    </p>
  );
}

export function SkillSet({ resume }: { resume: Resume }) {
  const mapped = resume.parsed_skills.filter((skill) => skill in resume.resolved_concepts);
  const confirmedCount = mapped.filter(
    (skill) => resume.concept_source[skill] === "m04",
  ).length;

  /** surface (lowercased) -> the strongest context it was written in. */
  const contexts = new Map<string, SkillContext>();
  const rank: SkillContext[] = ["skills_list", "education", "project_tech", "experience_body"];
  for (const mention of resume.skill_mentions) {
    const key = mention.surface.toLowerCase();
    const current = contexts.get(key);
    if (!current || rank.indexOf(mention.context) > rank.indexOf(current)) {
      contexts.set(key, mention.context);
    }
  }

  const listedOnly = resume.parsed_skills.filter(
    (skill) => (contexts.get(skill.toLowerCase()) ?? "skills_list") === "skills_list",
  );

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
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {mapped.map((skill) => {
                const copy = SOURCE_COPY[resume.concept_source[skill]];
                const context = contexts.get(skill.toLowerCase()) ?? "skills_list";
                return (
                  <span key={skill} className="inline-flex items-center gap-1.5">
                    <span className="text-sm text-ink">{skill}</span>
                    <Pill
                      tone={copy.tone}
                      title={`${resume.resolved_concepts[skill]} · ${copy.hint}`}
                    >
                      {copy.label}
                    </Pill>
                    <span className="provenance" title={CONTEXT_COPY[context].hint}>
                      {CONTEXT_COPY[context].label}
                    </span>
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

      {listedOnly.length > 0 && (
        <Section label="Listed, but never used in a bullet">
          <Panel tone="sunken" className="px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              {listedOnly.map((skill) => (
                <span key={skill} className="text-sm text-ink-soft">
                  {skill}
                </span>
              ))}
            </div>
            <p className="mt-2.5 text-xs text-ink-soft">
              You list these but no project or role bullet mentions them. A skill with no story
              attached is the easiest thing on a resume to get caught on &mdash; either attach it
              to something you built, or take it off the list.
            </p>
          </Panel>
        </Section>
      )}
    </>
  );
}

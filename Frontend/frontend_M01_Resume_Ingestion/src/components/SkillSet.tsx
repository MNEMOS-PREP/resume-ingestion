/**
 * The read-back: what we found on the resume, and what we know about each one.
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
 * ── One list, two tags ──────────────────────────────────────────────────────
 *
 * This screen used to be three lists: what mapped, what "mapped to nothing",
 * and what was "listed but never used in a bullet". The last two are genuinely
 * different questions —
 *
 *     mapping   does the ontology have a concept for this?  (can it be tested)
 *     evidence  does any bullet mention it?                 (can it be defended)
 *
 * — and on a real resume they overlap almost completely, because the skills
 * nobody wrote a bullet about are mostly the ones the ontology has never heard
 * of. Rendered as two lists it was the same twenty words twice under two
 * different explanations, which reads as a bug even though both sentences were
 * true.
 *
 * They are two INDEPENDENT properties of one skill, so they are two tags on one
 * row. The list is ordered by evidence, strongest first, so it reads as "what
 * you can actually defend" from the top down rather than as an inventory.
 *
 * ── Why there is no bar on this screen ───────────────────────────────────────
 *
 * M01 does not measure anything. It reads claims; it does not test them. A
 * mastery bar here — even an empty one — would imply a measurement this module
 * has no business making, and the platform has a component for that
 * (`MasteryBar`) precisely so it appears only where a measurement exists.
 */

import { useSkills } from "../api";
import { Panel, Pill, Section } from "../ui/primitives";
import type {
  ConceptSource,
  Resume,
  ScannedAgainst,
  SkillContext,
  SkillListing,
} from "../types";

/* ------------------------------------------------------------------ */
/*  Tag one: can anything test it?                                    */
/* ------------------------------------------------------------------ */

type Mapping = ConceptSource | "unmapped";

const MAPPING_COPY: Record<
  Mapping,
  { label: string; tone: "confirmed" | "reported" | "neutral"; hint: string }
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
  unmapped: {
    label: "no concept yet",
    tone: "neutral",
    hint:
      "It is on your resume and the ontology has no concept for it, so nothing can build a " +
      "question from it yet. It is kept rather than dropped — a skill we cannot test is still " +
      "a skill you claimed.",
  },
};

/* ------------------------------------------------------------------ */
/*  Tag two: can the student defend it?                               */
/* ------------------------------------------------------------------ */

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

/** Strongest evidence last, so an index comparison means "more defensible". */
const CONTEXT_RANK: SkillContext[] = [
  "skills_list",
  "education",
  "project_tech",
  "experience_body",
];

export function ScanSourceNote({ scannedAgainst }: { scannedAgainst: ScannedAgainst }) {
  if (scannedAgainst === "m04") {
    return <p className="text-xs text-ink-soft">Scanned against the full concept ontology.</p>;
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

interface Row {
  skill: string;
  mapping: Mapping;
  context: SkillContext;
  /** How many times it is written on the page. Only shown when it is > 1. */
  occurrences: number;
}

/**
 * `listing` is optional on purpose.
 *
 * M02 and M06 render this component with a `Resume` they already hold and no
 * separate fetch, and the contexts can be derived from `skill_mentions` on the
 * row. When the listing IS supplied — as it is on M01's own resume screen — the
 * server's `claimed_use` and its occurrence counts are used instead, because
 * those are the values the rest of the platform reads and a screen deriving its
 * own is how two of them start disagreeing.
 */
export function SkillSet({ resume, listing }: { resume: Resume; listing?: SkillListing }) {
  const rows = buildRows(resume, listing);

  const mapped = rows.filter((row) => row.mapping !== "unmapped");
  const confirmed = rows.filter((row) => row.mapping === "m04");
  const listedOnly = rows.filter((row) => row.context === "skills_list");

  if (rows.length === 0) {
    return (
      <Section label="Skills we found">
        <div className="rounded-panel border border-dashed border-line-strong px-4 py-5">
          <p className="text-sm font-medium text-ink">Nothing found</p>
          <p className="mt-1 max-w-xl text-sm text-ink-soft">
            Either the resume has no skills section the parser recognised, or the scan ran against
            the five-concept fallback. Check the note above &mdash; those look identical from here
            and are very different problems.
          </p>
        </div>
      </Section>
    );
  }

  return (
    <Section
      label="Skills we found"
      meta={`${rows.length} · ${confirmed.length} the ontology confirmed`}
    >
      <Panel className="px-4 py-1">
        <div className="divide-y divide-line">
          {rows.map((row) => (
            <SkillRow key={row.skill} row={row} conceptId={resume.resolved_concepts[row.skill]} />
          ))}
        </div>
      </Panel>

      <div className="mt-2.5 space-y-1.5 text-xs text-ink-faint">
        <p>
          Two separate things, and a skill can fail either. The first tag is whether the ontology
          has a concept for it &mdash; that decides whether anything can build a question from it.
          The second is where on your resume you wrote it, which decides how hard that question
          will be.
        </p>
        {listedOnly.length > 0 && (
          <p>
            <strong className="font-medium text-ink">
              {listedOnly.length} of these appear only in your skills list
            </strong>{" "}
            with no project or role bullet mentioning them. A skill with no story attached is the
            easiest thing on a resume to get caught on &mdash; either attach it to something you
            built, or take it off the list.
          </p>
        )}
        {mapped.length < rows.length && (
          <p>
            {rows.length - mapped.length} are on your resume and mapped to nothing. They are listed
            rather than dropped: a read-back that quietly loses what you wrote reads as a broken
            parser, and we would rather show you the gap.
          </p>
        )}
      </div>
    </Section>
  );
}

function SkillRow({ row, conceptId }: { row: Row; conceptId?: string }) {
  const mapping = MAPPING_COPY[row.mapping];
  const context = CONTEXT_COPY[row.context];
  const untestable = row.mapping === "unmapped";

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2">
      <span
        className={
          untestable
            ? "untestable-mark inline-flex items-center px-1.5 text-sm text-ink-soft"
            : "text-sm text-ink"
        }
      >
        {row.skill}
        {row.occurrences > 1 && (
          <span className="provenance ml-2">&times;{row.occurrences}</span>
        )}
      </span>
      <span className="flex shrink-0 items-center gap-2">
        <Pill tone={mapping.tone} title={conceptId ? `${conceptId} · ${mapping.hint}` : mapping.hint}>
          {mapping.label}
        </Pill>
        <span className="provenance" title={context.hint}>
          {context.label}
        </span>
      </span>
    </div>
  );
}

/**
 * One row per skill, ordered by how defensible it is.
 *
 * Strongest evidence first: a student reading down the page sees what they can
 * actually talk about before they see what they cannot. Ties break
 * alphabetically so the order is stable across renders — an unstable list on a
 * screen the student is comparing against their own resume is its own bug.
 */
function buildRows(resume: Resume, listing?: SkillListing): Row[] {
  const mentions = listing?.mentions ?? resume.skill_mentions;

  const strongest = new Map<string, SkillContext>();
  for (const mention of mentions) {
    const key = mention.surface.toLowerCase();
    const current = strongest.get(key);
    if (!current || CONTEXT_RANK.indexOf(mention.context) > CONTEXT_RANK.indexOf(current)) {
      strongest.set(key, mention.context);
    }
  }

  const counts = new Map<string, number>();
  for (const entry of listing?.unmapped_queue ?? []) {
    counts.set(entry.surface.toLowerCase(), entry.occurrences);
  }
  for (const mention of mentions) {
    const key = mention.surface.toLowerCase();
    counts.set(key, Math.max(counts.get(key) ?? 0, mention.occurrences));
  }

  const rows: Row[] = resume.parsed_skills.map((skill) => {
    const key = skill.toLowerCase();
    const source = resume.concept_source[skill];
    return {
      skill,
      mapping: skill in resume.resolved_concepts && source ? source : "unmapped",
      context: strongest.get(key) ?? "skills_list",
      occurrences: counts.get(key) ?? 1,
    };
  });

  return rows.sort((a, b) => {
    const byEvidence = CONTEXT_RANK.indexOf(b.context) - CONTEXT_RANK.indexOf(a.context);
    return byEvidence !== 0 ? byEvidence : a.skill.localeCompare(b.skill);
  });
}

/**
 * The same list, fetching the server's own view of it.
 *
 * `GET /v1/resumes/{id}/skills` is where `claimed_use`, the mapped/unmapped
 * counts and the occurrence figures are computed. M01's own screen reads them
 * from there rather than recomputing; the plain `SkillSet` above stays
 * prop-only for the modules that mount it with a resume they already have.
 */
export function SkillPanel({ resume }: { resume: Resume }) {
  const listing = useSkills(resume.id);
  return <SkillSet resume={resume} listing={listing.data} />;
}

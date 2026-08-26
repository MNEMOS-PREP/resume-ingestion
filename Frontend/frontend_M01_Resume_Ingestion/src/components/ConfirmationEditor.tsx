/**
 * Screen 3 — "Here's what I read. Fix anything I got wrong." (§2.3, FR-1.11)
 *
 * §2.3 calls this *"the single most important UX decision in this module"*, and
 * the reason is an engineering one:
 *
 *   *"Parsing accuracy on real Indian campus resumes with two-column templates,
 *   tables, and Canva exports will never hit 100%. Rather than chase the last
 *   8% with engineering, we spend one screen and get 100% with the user's help.
 *   This is the cheapest correctness win in the entire product."*
 *
 * So the parse is a PROPOSAL until the student says otherwise. Everything here
 * is editable, every edit is written immediately, and every edit is logged as a
 * disagreement — AC-1.7 watches the correction rate precisely because a parser
 * getting worse should show up as data.
 *
 * ── What is shown before anything is edited ─────────────────────────────────
 *
 * `parse_notes` and `parse_status`. A two-column resume, an OCR pass, a
 * six-page cap — the student is told what happened and asked to check the part
 * most likely to be wrong (EC-1.1, EC-1.2). A confirmation screen that says
 * nothing about a low-confidence read is asking the student to rubber-stamp it.
 */

import { useState } from "react";

import {
  useConfirmResume,
  useCorrection,
  useCorrectSection,
  useDeleteClaim,
  useEditClaim,
  useEditSkill,
} from "../api";
import { DateEditor } from "./DateEditor";
import { Btn, Panel, Section, TextField } from "../ui/primitives";
import { SECTION_KINDS, SECTION_LABEL } from "./sections";
import type { ClaimType, Resume, ResumeClaim, ResumeSection } from "../types";



export function ConfirmationEditor({
  resume,
  onConfirmed,
}: {
  resume: Resume;
  onConfirmed: () => void;
}) {
  const confirm = useConfirmResume(resume.id);

  return (
    <>
      <header className="mb-7">
        <h1 className="text-display font-semibold text-ink">
          Here&rsquo;s what I read. Fix anything I got wrong.
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          This takes about fifteen seconds and it is the difference between questions about your
          work and questions about a mis-read heading. Nothing here is a judgement of your resume.
        </p>
      </header>

      <ParseNotes resume={resume} />

      <Section label="Sections" meta={sectionProgress(resume)}>
        <div className="space-y-2">
          {resume.sections.map((section) => (
            <SectionRow key={section.id} resume={resume} section={section} />
          ))}
        </div>
        {resume.sections.length === 0 && (
          <Panel tone="sunken" className="px-4 py-3">
            <p className="text-sm text-ink-soft">
              No sections found. If you pasted plain text without headings, that is expected
              &mdash; everything is treated as one block and the claims below still work.
            </p>
          </Panel>
        )}
      </Section>

      <BulletEditor resume={resume} />
      <SkillChipEditor resume={resume} />
      {/* §2.3's fourth editable target. It was the one thing a student could
          not fix, and it drives the gap flag they are then asked to prepare
          an answer for. */}
      <DateEditor resume={resume} />

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-5">
        <Btn
          type="button"
          variant="primary"
          disabled={confirm.isPending}
          onClick={() => confirm.mutate(undefined, { onSuccess: onConfirmed })}
        >
          {confirm.isPending ? "Saving…" : "Looks right — continue →"}
        </Btn>
        <span className="text-xs text-ink-faint">
          You can come back and change any of this later.
        </span>
      </div>
    </>
  );
}

/**
 * §8.2's PARTIAL column, which the states table asks for and this screen had
 * only the loading / empty / success thirds of.
 *
 * "Read 3 of 4 sections" is a different sentence from "found 4", and it is the
 * one that tells a student where to look. A count alone reads as completeness
 * even when a third of the document was unreadable.
 */
function sectionProgress(resume: Resume): string {
  const total = resume.sections.length;
  if (total === 0) return "none found";
  const sure = resume.sections.filter((section) => section.confidence >= 0.5).length;
  return sure === total ? `${total} found` : `read ${sure} of ${total} clearly`;
}

function claimProgress(resume: Resume): string {
  const total = resume.claims.length;
  if (total === 0) return "none found";
  const scored = resume.claims.filter((claim) => claim.risk_band).length;
  return scored === total ? `${total} found` : `${scored} of ${total} scored`;
}

function skillProgress(resume: Resume): string {
  const total = resume.parsed_skills.length;
  if (total === 0) return "none found";
  const mapped = Object.keys(resume.resolved_concepts).length;
  return mapped === total ? `${total} found` : `${mapped} of ${total} mapped to a concept`;
}

/**
 * What we noticed while reading, in words the student can act on.
 *
 * EC-1.1 asks for "Check I read the columns in the right order" on a
 * low-confidence two-column parse; EC-1.2 for an explicit banner on an OCR
 * read. Both arrive here as `parse_notes` from the server, so the sentence a
 * student sees is written once, next to the code that decided to say it.
 */
function ParseNotes({ resume }: { resume: Resume }) {
  const needsReview = resume.parse_status === "needs_review";
  if (!needsReview && resume.parse_notes.length === 0) return null;

  return (
    <div
      className="mb-7 rounded-md border border-reported-line bg-reported-soft px-4 py-3"
      role="note"
    >
      <p className="text-sm font-medium text-reported">
        {needsReview ? "Worth a closer look at this one" : "One thing to know"}
      </p>
      <ul className="mt-1.5 space-y-1 text-sm text-ink-soft">
        {resume.parse_notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
        {resume.language !== "en" && resume.language !== "unknown" && (
          <li>
            Detected language: <strong className="font-medium text-ink">{resume.language}</strong>.
            Nothing is blocked &mdash; but the skills and headings I look for are English, so
            expect to add more by hand than usual.
          </li>
        )}
        {needsReview && resume.parse_notes.length === 0 && (
          <li>
            I am less sure than usual about this read. Check the sections below before continuing.
          </li>
        )}
      </ul>
    </div>
  );
}

/** One section, relabelable in place (FR-1.11). */
function SectionRow({ resume, section }: { resume: Resume; section: ResumeSection }) {
  const correct = useCorrectSection(resume.id);
  // Six lines, not two. The student is being asked "is this the right label
  // for this block?", and two lines of a SKILLS section is one line of
  // libraries — not enough of the block to judge it, on the screen §2.3
  // calls the most important in the module.
  const preview = section.span.text.trim().split("\n").slice(0, 6).join(" · ");
  const lowConfidence = section.confidence < 0.5;

  return (
    <Panel className="px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <label className="flex items-center gap-2">
          <span className="sr-only">Section type</span>
          <select
            value={section.kind}
            disabled={correct.isPending}
            onChange={(event) =>
              correct.mutate({ sectionId: section.id, kind: event.target.value })
            }
            className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink outline-none focus:border-brand-line"
          >
            {SECTION_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {SECTION_LABEL[kind]}
              </option>
            ))}
          </select>
        </label>

        <span className="provenance">
          {section.user_corrected ? (
            <span className="text-confirmed">you corrected this</span>
          ) : (
            <>
              {lowConfidence ? "unsure · " : ""}
              {Math.round(section.confidence * 100)}% confident
            </>
          )}
        </span>
      </div>

      <p className="mt-2 line-clamp-3 text-sm text-ink-soft">{preview || "(empty)"}</p>
    </Panel>
  );
}

/**
 * Editing a bullet, and re-scoring it (§8.3).
 *
 * *"Editing a bullet re-scores only that claim, optimistically, in < 500 ms."*
 * The server re-scores just the edited claim and returns the whole resume, so
 * the band on this row can change under the student's hands — which is the
 * point. They watch a rewrite move a bullet out of "risky".
 */
function BulletEditor({ resume }: { resume: Resume }) {
  if (resume.claims.length === 0) {
    return (
      <Section label="Bullets" meta="none left">
        <Panel tone="sunken" className="px-4 py-3">
          <p className="text-sm text-ink-soft">
            No bullets. If you removed them all, that is allowed and nothing downstream is broken
            by it &mdash; the rest of the product works without a resume at all.
          </p>
        </Panel>
      </Section>
    );
  }

  return (
    <Section label="Bullets" meta={claimProgress(resume)}>
      <div className="space-y-2">
        {resume.claims.map((claim) => (
          <BulletRow key={claim.id} resumeId={resume.id} claim={claim} />
        ))}
      </div>
    </Section>
  );
}

/**
 * What kind of assertion a bullet is (FR-1.12).
 *
 * The classifier reads this off the bullet's verb, and the verb is often not
 * the one that matters: "Worked on the placement portal" classifies as `used`
 * for a student who built it, and the probe family follows the type — so a
 * mis-read verb asks someone who shipped a system what it let them do that
 * they could not do before. It is a one-word correction with a visible
 * consequence, and it was the one correctable field with no control.
 */
const CLAIM_TYPES: ClaimType[] = [
  "built",
  "improved",
  "led",
  "researched",
  "achieved",
  "used",
  "learned",
];

const CLAIM_TYPE_LABEL: Record<ClaimType, string> = {
  built: "I built it",
  improved: "I improved it",
  led: "I led it",
  researched: "I researched it",
  achieved: "I achieved it",
  used: "I used it",
  learned: "I learned it",
};

function BulletRow({ resumeId, claim }: { resumeId: string; claim: ResumeClaim }) {
  const [draft, setDraft] = useState(claim.text);
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const edit = useEditClaim(resumeId);
  const remove = useDeleteClaim(resumeId);
  // The generic correction endpoint, for the one field with no dedicated
  // route. It speaks the audit shape directly, which is what this needs.
  const reclassify = useCorrection(resumeId);

  if (!editing) {
    return (
      <Panel className="px-4 py-2.5">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm text-ink">{claim.text}</p>
          <div className="flex shrink-0 gap-1">
            <Btn
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(claim.text);
                setEditing(true);
              }}
            >
              edit
            </Btn>
            {!confirmingDelete ? (
              <Btn
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirmingDelete(true)}
              >
                not mine
              </Btn>
            ) : (
              <>
                <Btn
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(claim.id)}
                >
                  {remove.isPending ? "Removing…" : "remove it"}
                </Btn>
                <Btn
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmingDelete(false)}
                >
                  keep
                </Btn>
              </>
            )}
          </div>
        </div>

        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5">
            <span className="sr-only">What kind of claim this is</span>
            <select
              value={claim.claim_type}
              disabled={reclassify.isPending}
              onChange={(event) =>
                reclassify.mutate({
                  target: "claim",
                  target_id: claim.id,
                  field: "claim_type",
                  value: event.target.value,
                })
              }
              className="rounded-md border border-line bg-surface px-1.5 py-0.5 text-xs text-ink outline-none focus:border-brand-line"
            >
              {CLAIM_TYPES.map((kind) => (
                <option key={kind} value={kind}>
                  {CLAIM_TYPE_LABEL[kind]}
                </option>
              ))}
            </select>
          </label>
          {claim.user_edited && <span className="provenance text-confirmed">you edited this</span>}
        </div>

        {confirmingDelete && (
          <p className="mt-1.5 text-xs text-ink-soft">
            Removing a bullet takes it out of everything downstream &mdash; no interview will ask
            you to defend it. It is recorded as a correction, because a claim we invented is the
            most useful thing you can tell us about the parser.
          </p>
        )}
      </Panel>
    );
  }

  return (
    <Panel className="px-4 py-3">
      <TextField
        label="Bullet"
        value={draft}
        autoFocus
        onChange={(event) => setDraft(event.target.value)}
      />
      <div className="mt-2 flex gap-2">
        <Btn
          type="button"
          variant="primary"
          size="sm"
          disabled={edit.isPending || !draft.trim() || draft === claim.text}
          onClick={() =>
            edit.mutate(
              { claimId: claim.id, field: "text", value: draft },
              { onSuccess: () => setEditing(false) },
            )
          }
        >
          {edit.isPending ? "Saving…" : "Save and re-score"}
        </Btn>
        <Btn type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
          Cancel
        </Btn>
      </div>
    </Panel>
  );
}

/**
 * Add a skill we missed, or strike one we invented (FR-1.11, §8.1).
 *
 * A student-added skill lands in `unresolved_skills` and never in
 * `resolved_concepts`: M01 does not get to mint a concept id, and typing
 * "Kubernetes" is a claim about a resume, not a statement that the ontology has
 * a concept for it.
 */
export function SkillChipEditor({ resume }: { resume: Resume }) {
  const [draft, setDraft] = useState("");
  const edit = useEditSkill(resume.id);

  return (
    <Section label="Skills" meta={skillProgress(resume)}>
      <Panel className="px-4 py-3">
        <div className="flex flex-wrap gap-1.5">
          {resume.parsed_skills.map((skill) => {
            const mapped = skill in resume.resolved_concepts;
            return (
              <span
                key={skill}
                className={[
                  "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-sm",
                  mapped
                    ? "border-line bg-surface-sunken text-ink"
                    : "untestable-mark border-transparent text-ink-soft",
                ].join(" ")}
              >
                {skill}
                <button
                  type="button"
                  aria-label={`Remove ${skill}`}
                  disabled={edit.isPending}
                  onClick={() => edit.mutate({ label: skill, present: false })}
                  className="text-ink-faint hover:text-contested"
                >
                  ✕
                </button>
              </span>
            );
          })}
          {resume.parsed_skills.length === 0 && (
            <span className="text-sm text-ink-soft">
              Nothing found yet &mdash; add anything I missed.
            </span>
          )}
        </div>

        <form
          className="mt-3 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const label = draft.trim();
            if (!label) return;
            edit.mutate({ label, present: true }, { onSuccess: () => setDraft("") });
          }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Add a skill I missed"
            aria-label="Add a skill"
            className="w-56 rounded-md border border-line bg-surface px-2.5 py-1 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-brand-line"
          />
          <Btn type="submit" variant="secondary" size="sm" disabled={!draft.trim()}>
            Add
          </Btn>
        </form>
      </Panel>

      <p className="mt-2 text-xs text-ink-faint">
        A skill you add is kept as written and mapped to nothing until the skill graph confirms it
        &mdash; we don&rsquo;t invent an id for it, because everything downstream treats an id as
        permission to test you on it.
      </p>
    </Section>
  );
}

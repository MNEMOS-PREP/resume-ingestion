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

import { useConfirmResume, useCorrectSection, useEditClaim, useEditSkill } from "../api";
import { Btn, Panel, Section, TextField } from "../ui/primitives";
import type { Resume, ResumeSection, SectionKind } from "../types";

const SECTION_KINDS: SectionKind[] = [
  "contact",
  "summary",
  "education",
  "experience",
  "projects",
  "skills",
  "achievements",
  "certifications",
  "publications",
  "extras",
  "unknown",
];

const KIND_LABEL: Record<SectionKind, string> = {
  contact: "Contact",
  summary: "Summary",
  education: "Education",
  experience: "Experience",
  projects: "Projects",
  skills: "Skills",
  achievements: "Achievements",
  certifications: "Certifications",
  publications: "Publications",
  extras: "Extra-curricular",
  unknown: "Not sure",
};

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
  const preview = section.span.text.trim().split("\n").slice(0, 2).join(" · ");
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
                {KIND_LABEL[kind]}
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

      <p className="mt-2 line-clamp-2 text-sm text-ink-soft">{preview || "(empty)"}</p>
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
  if (resume.claims.length === 0) return null;

  return (
    <Section label="Bullets" meta={claimProgress(resume)}>
      <div className="space-y-2">
        {resume.claims.map((claim) => (
          <BulletRow key={claim.id} resumeId={resume.id} claimId={claim.id} text={claim.text} />
        ))}
      </div>
    </Section>
  );
}

function BulletRow({
  resumeId,
  claimId,
  text,
}: {
  resumeId: string;
  claimId: string;
  text: string;
}) {
  const [draft, setDraft] = useState(text);
  const [editing, setEditing] = useState(false);
  const edit = useEditClaim(resumeId);

  if (!editing) {
    return (
      <Panel className="flex items-start justify-between gap-3 px-4 py-2.5">
        <p className="text-sm text-ink">{text}</p>
        <Btn
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setDraft(text);
            setEditing(true);
          }}
        >
          edit
        </Btn>
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
          disabled={edit.isPending || !draft.trim() || draft === text}
          onClick={() =>
            edit.mutate(
              { claimId, field: "text", value: draft },
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

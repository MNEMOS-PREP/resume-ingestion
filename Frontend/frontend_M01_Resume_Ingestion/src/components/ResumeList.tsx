/**
 * A student's resumes, one row each — the list on "Your resumes", shared
 * (2026-11-17).
 *
 * The resume page lists them to open one; the job description module lists
 * them to choose which one to tailor. Same rows, same counts, same words, so
 * a student picking a resume for a job sees exactly the list they upload to.
 */
import { Icon } from "@ai/core";

import type { Resume } from "../types";
import { BANDS } from "./bands";
import { Panel } from "../ui/primitives";

export function ResumeList({
  resumes,
  onOpen,
  onRemove,
  selectedId,
  actionLabel,
}: {
  resumes: Resume[];
  onOpen: (resume: Resume) => void;
  /** Offer the remove button. Left out where removing is not the job. */
  onRemove?: (resume: Resume) => void;
  /** The chosen row, when the list is a picker. */
  selectedId?: string | null;
  /** A word on the right of each row ("Use this"), when the list is a picker. */
  actionLabel?: string;
}) {
  return (
    <Panel className="px-4 py-1">
      <ul className="divide-y divide-line">
        {resumes.map((resume) => {
          const risky = resume.claims.filter((claim) => claim.risk_band === "risky").length;
          const selected = selectedId === resume.id;
          return (
            <li key={resume.id} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onOpen(resume)}
                aria-pressed={selectedId !== undefined ? selected : undefined}
                className={`flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5 text-left ${
                  selected ? "text-brand" : "hover:text-brand"
                }`}
              >
                <span className="flex min-w-0 items-center gap-2 text-sm text-ink">
                  {selectedId !== undefined && (
                    <span
                      aria-hidden
                      className={`grid size-4 shrink-0 place-items-center rounded-full border ${
                        selected ? "border-brand bg-brand text-white" : "border-line-strong"
                      }`}
                    >
                      {selected && <Icon name="check" size={11} />}
                    </span>
                  )}
                  <span className="truncate">
                    {resume.filename ?? "Pasted text"}
                    <span className="ml-2 text-ink-soft" data-numeric>
                      {resume.claims.length} line{resume.claims.length === 1 ? "" : "s"} to defend
                      {risky > 0 && (
                        <>
                          {" · "}
                          <span aria-hidden>{BANDS.risky.icon}</span> {risky} risky
                        </>
                      )}
                    </span>
                  </span>
                </span>
                <span className="shrink-0 text-xs text-ink-faint">
                  {!resume.is_active && "older version · "}
                  {resume.confirmed ? "checked by you" : "not checked yet"}
                  {actionLabel && !selected && (
                    <span className="ml-3 font-medium text-brand">{actionLabel}</span>
                  )}
                </span>
              </button>
              {onRemove && (
                <button
                  type="button"
                  onClick={() => onRemove(resume)}
                  aria-label={`Remove ${resume.filename ?? "this pasted resume"}`}
                  title="Remove this resume"
                  className="grid size-8 shrink-0 place-items-center rounded-md text-ink-faint hover:bg-surface-sunken hover:text-contested"
                >
                  <Icon name="trash" size={16} />
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

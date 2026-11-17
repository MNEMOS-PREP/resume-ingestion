/**
 * The versions of one resume — each a copy worded for one job, or one the
 * student made to try something — with the uploaded resume untouched above
 * them all (2026-11-17).
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { apiProblem, useCreateTailored, useDeleteTailored, useTailoredCopies } from "../api";
import { m02Href } from "../links";
import type { TailoredResume } from "../types";

/** A server time, read as UTC: SQLite drops the zone, so a bare ISO string is UTC. */
function utc(iso: string): number {
  return new Date(/[zZ]$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
}

function when(iso: string): string {
  const days = Math.floor((Date.now() - utc(iso)) / 86_400_000);
  if (days < 1) return "today";
  if (days === 1) return "yesterday";
  return `${days} days ago`;
}

/** Where a copy opens: its job's tailoring screen, or this module's editor. */
export function tailoredHref(copy: TailoredResume): { href: string; external: boolean } {
  if (copy.target_kind === "jd" && copy.target_ref) {
    return m02Href(`/jds/${copy.target_ref}/tailor`, copy.candidate_id);
  }
  return { href: `/resumes/${copy.resume_id}/versions/${copy.id}`, external: false };
}

export function TailoredCopies({ resumeId }: { resumeId: string }) {
  const copies = useTailoredCopies(resumeId);
  const create = useCreateTailored();
  const remove = useDeleteTailored(resumeId);
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState<string | null>(null);

  const list = copies.data ?? [];
  return (
    <div>
      <div className="flex items-center justify-between px-2.5">
        <p className="text-xs font-medium text-ink-faint">Versions</p>
        <button
          type="button"
          disabled={create.isPending}
          onClick={() =>
            create.mutate(
              {
                resumeId,
                targetRef: `version-${Date.now().toString(36)}`,
                label: `Version ${list.filter((c) => c.target_kind === "version").length + 1}`,
                targetKind: "version",
              },
              { onSuccess: (copy) => navigate(`/resumes/${resumeId}/versions/${copy.id}`) },
            )
          }
          className="text-xs font-medium text-brand hover:underline disabled:opacity-50"
        >
          + New version
        </button>
      </div>
      <p className="px-2.5 pt-0.5 text-[0.6875rem] text-ink-faint">
        Copies you can reword and download. This resume stays as you uploaded it.
      </p>
      {list.length === 0 && !copies.isLoading && (
        <p className="px-2.5 pt-1.5 text-xs text-ink-soft">None yet — tailor it to a job to make one.</p>
      )}
      <ul className="mt-1 space-y-0.5">
        {list.map((copy) => {
          const target = tailoredHref(copy);
          const label = (
            <>
              <span className="block truncate text-ink">{copy.label}</span>
              <span className="block text-[0.6875rem] text-ink-faint" data-numeric>
                {copy.target_kind === "jd" ? "for a job · " : ""}
                {copy.edited} change{copy.edited === 1 ? "" : "s"} · {when(copy.updated_at)}
              </span>
            </>
          );
          return (
            <li key={copy.id} className="group flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm hover:bg-surface-sunken">
              {target.external ? (
                <a href={target.href} className="min-w-0 flex-1">
                  {label}
                </a>
              ) : (
                <Link to={target.href} className="min-w-0 flex-1">
                  {label}
                </Link>
              )}
              {confirming === copy.id ? (
                <span className="flex shrink-0 items-center gap-1 text-xs">
                  <button
                    type="button"
                    onClick={() => remove.mutate(copy.id, { onSettled: () => setConfirming(null) })}
                    className="font-medium text-contested"
                  >
                    Delete
                  </button>
                  <button type="button" onClick={() => setConfirming(null)} className="text-ink-soft">
                    Keep
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  aria-label={`Delete ${copy.label}`}
                  onClick={() => setConfirming(copy.id)}
                  className="shrink-0 text-xs text-ink-faint opacity-0 group-hover:opacity-100 hover:text-contested focus:opacity-100"
                >
                  Delete
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {(create.error || remove.error) && (
        <p className="px-2.5 text-xs text-contested">{apiProblem(create.error ?? remove.error)}</p>
      )}
    </div>
  );
}

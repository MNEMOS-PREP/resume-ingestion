/**
 * "This resume is going to be removed" — and what is NOT (2026-10-04).
 *
 * Asked for in those words, with the second half spelled out: removing a resume
 * "doesn't mean you remove the projects talked about or even skills in that",
 * because those are how progress is tracked. So the dialog says both, with the
 * numbers: what goes (the file, what we read, its review and questions), and
 * what stays in the library and why.
 */
import { Link } from "react-router-dom";

import { useCandidateResumes, useDeleteResume, useLibrary } from "../api";
import type { Resume } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";
import { keptFrom } from "./library";

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function DeleteResumeDialog({
  resume,
  onClose,
  onDeleted,
}: {
  /** The resume to remove; null keeps the dialog closed. */
  resume: Resume | null;
  onClose: () => void;
  onDeleted?: () => void;
}) {
  const candidateId = resume?.candidate_id;
  const library = useLibrary(candidateId);
  const resumes = useCandidateResumes(candidateId);
  const remove = useDeleteResume();

  const kept = resume && library.data ? keptFrom(library.data.items, resume.id) : null;
  const others = (resumes.data ?? []).filter((r) => r.id !== resume?.id);
  const name = resume?.filename ?? "This pasted resume";

  const keptLines = kept
    ? [
        kept.lines > 0 && plural(kept.lines, "line from your projects and jobs", "lines from your projects and jobs"),
        kept.honours > 0 && plural(kept.honours, "achievement or certification", "achievements and certifications"),
        kept.education > 0 && plural(kept.education, "education entry", "education entries"),
        kept.skills > 0 && plural(kept.skills, "skill", "skills"),
      ].filter((line): line is string => Boolean(line))
    : [];

  return (
    <ConfirmDialog
      open={resume !== null}
      title="Remove this resume?"
      confirmLabel="Remove resume"
      busyLabel="Removing…"
      busy={remove.isPending}
      error={remove.error ? "That didn't go through. Nothing was removed — try again." : null}
      onClose={() => {
        remove.reset();
        onClose();
      }}
      onConfirm={() =>
        resume &&
        remove.mutate(resume.id, {
          onSuccess: () => {
            onClose();
            onDeleted?.();
          },
        })
      }
    >
      <p>
        <span className="font-medium text-ink">{name}</span> and everything we read from it — its
        review, the questions it raised and its page view — will be removed. This can't be undone.
      </p>

      <div className="rounded-lg border border-confirmed-line bg-confirmed-soft px-3.5 py-3 text-ink">
        <p className="font-medium">Kept in your library</p>
        {library.isLoading ? (
          <p className="mt-1 text-ink-soft">Counting what it held…</p>
        ) : keptLines.length > 0 ? (
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-soft" data-numeric>
            {keptLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-ink-soft">Everything it held is already there.</p>
        )}
        <p className="mt-2 text-ink-soft">
          So your progress stays on record, and you can pick these for your next resume. Remove them
          separately in{" "}
          <Link to="/resume/library" className="font-medium text-ink underline underline-offset-2" onClick={onClose}>
            your library
          </Link>
          .
        </p>
      </div>

      {resume?.is_active && (
        <p>
          {others.length > 0
            ? "Your newest other resume becomes the current one."
            : "You'll have no resume on file. Practice still works without one."}
        </p>
      )}
    </ConfirmDialog>
  );
}

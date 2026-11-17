/**
 * The photo on a tailored resume: on or off for this copy (2026-11-17).
 *
 * The picture comes from Settings, or — when the student has not set one —
 * from the photo printed on the resume they uploaded. Some recruiters prefer
 * resumes without one, so it is a choice per copy, saved as a version like
 * any other change.
 */
import { Link } from "react-router-dom";

import { apiProblem, useTailoredPhoto } from "../api";
import { standalone } from "../links";
import type { TailoredResume } from "../types";

export function PhotoToggle({ copy }: { copy: TailoredResume }) {
  const set = useTailoredPhoto(copy.resume_id, copy.id);
  const photo = copy.photo;
  const settings = standalone() ? null : "/settings#photo";

  if (!photo?.available) {
    return (
      <p className="text-xs text-ink-faint">
        No photo on this resume.{" "}
        {settings && (
          <Link to={settings} className="font-medium text-brand hover:underline">
            Add your picture in Settings
          </Link>
        )}
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <button
        type="button"
        role="switch"
        aria-checked={photo.enabled}
        disabled={set.isPending}
        onClick={() => set.mutate(!photo.enabled)}
        className="inline-flex items-center gap-2 font-medium text-ink disabled:opacity-60"
      >
        <span
          aria-hidden
          className={`relative h-4 w-7 rounded-full transition-colors ${photo.enabled ? "bg-brand" : "bg-line-strong"}`}
        >
          <span
            className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${photo.enabled ? "left-3.5" : "left-0.5"}`}
          />
        </span>
        Photo on this resume
      </button>
      <span className="text-ink-faint">
        {photo.available === "profile" ? "your picture from Settings" : "the photo on your uploaded resume"}
        {settings && (
          <>
            {" · "}
            <Link to={settings} className="font-medium text-brand hover:underline">
              {photo.available === "profile" ? "change" : "use a different one"}
            </Link>
          </>
        )}
      </span>
      {set.error && <span className="text-contested">{apiProblem(set.error)}</span>}
    </div>
  );
}

/**
 * One version of a resume, edited beside its PDF (2026-11-17).
 *
 * The same editor and preview the job-description screen uses, without a job:
 * a copy the student made to try a different wording, or one made for a job
 * and opened from here. The uploaded resume is not touched by anything on it.
 */
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useTailored } from "../api";
import { DownloadPdf, suggestFilename } from "./DownloadPdf";
import { PhotoToggle } from "./PhotoToggle";
import { TailoredEditor } from "./TailoredEditor";
import { tailoredHref } from "./TailoredCopies";
import { TailoredPreview, type PreviewFocus } from "./TailoredPreview";
import { Empty, SkeletonRows } from "../ui/primitives";

export function TailoredVersionPage() {
  const { resumeId = "", tailoredId = "" } = useParams<{ resumeId: string; tailoredId: string }>();
  const copy = useTailored(resumeId, tailoredId);
  const [focus, setFocus] = useState<PreviewFocus | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [filename, setFilename] = useState("");

  if (copy.isLoading) {
    return (
      <div className="mx-auto w-full max-w-6xl px-5 py-8">
        <SkeletonRows rows={8} />
      </div>
    );
  }
  if (copy.isError || !copy.data) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8">
        <Empty title="This version couldn't be found">
          It may have been deleted, along with the resume it was made from.
          <div className="mt-3">
            <Link to={`/resumes/${resumeId}/review`} className="text-sm font-medium text-brand">
              Back to the resume →
            </Link>
          </div>
        </Empty>
      </div>
    );
  }

  const data = copy.data;
  const job = data.target_kind === "jd" ? tailoredHref(data) : null;
  const suggested = suggestFilename(data.name);

  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-4 px-4 py-5 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/resumes/${resumeId}/review`} className="text-xs font-medium text-ink-soft hover:text-ink">
            ← {data.filename ?? "Your resume"}
          </Link>
          <h1 className="mt-1 truncate text-title font-semibold tracking-tight text-ink">{data.label}</h1>
          <p className="mt-0.5 text-sm text-ink-soft">
            A copy you can reword and download — your uploaded resume stays as it is.
            {job &&
              (job.external ? (
                <a href={job.href} className="ml-2 font-medium text-brand">
                  Open with its job description →
                </a>
              ) : (
                <Link to={job.href} className="ml-2 font-medium text-brand">
                  Open with its job description →
                </Link>
              ))}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <DownloadPdf copy={data} filename={filename} onFilename={setFilename} suggested={suggested} />
          <PhotoToggle copy={data} />
        </div>
      </header>
      <div className="grid gap-4 lg:h-[calc(100dvh-11rem)] lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <TailoredEditor
          copy={data}
          focusId={focusId}
          onFocus={(blockId) => {
            setFocusId(blockId);
            setFocus({ blockId, nonce: Date.now() });
          }}
        />
        <TailoredPreview copy={data} focus={focus} onPick={(blockId) => setFocusId(blockId)} />
      </div>
    </div>
  );
}

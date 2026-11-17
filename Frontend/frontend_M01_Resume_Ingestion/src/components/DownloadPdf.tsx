/**
 * The file name, editable, and the download (2026-11-17).
 *
 * The PDF is generated on request from the copy's latest revision — never an
 * old file renamed — and saved under the name typed here. The `.pdf` is shown
 * beside the field rather than in it, so it cannot be typed twice or lost.
 */
import { useState } from "react";

import { apiProblem, downloadTailoredPdf } from "../api";
import type { TailoredResume } from "../types";
import { Btn } from "../ui/primitives";

/** "ANSH BAJPAI" + "Acme Corp" -> "Ansh_Bajpai_Acme_Corp_resume". No extension. */
export function suggestFilename(name: string | null | undefined, company?: string | null): string {
  const words = (value: string | null | undefined) =>
    (value ?? "")
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((w) => (w === w.toUpperCase() && w.length > 3 ? w[0] + w.slice(1).toLowerCase() : w));
  const person = words(name).slice(0, 3);
  const firm = words(company).slice(0, 3);
  return [...(person.length ? person : ["my"]), ...firm, "resume"].join("_");
}

/** What the user typed, without any `.pdf` they added, and never empty. */
export function stem(value: string): string {
  return value.replace(/(\.pdf\s*)+$/i, "").trim();
}

export function DownloadPdf({
  copy,
  filename,
  onFilename,
  suggested,
  compact = false,
}: {
  copy: TailoredResume;
  /** Controlled: the host keeps it (M02 saves it with the job). */
  filename: string;
  onFilename: (value: string) => void;
  suggested: string;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const name = stem(filename) || suggested;

  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await downloadTailoredPdf(copy.resume_id, copy.id, `${name}.pdf`);
      setDone(`Saved ${result.filename} · version ${result.revision ?? copy.revision}`);
    } catch (err) {
      setError(apiProblem(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? "" : "py-1"}`}>
      <label className="flex min-w-0 items-center overflow-hidden rounded-md border border-line bg-surface focus-within:border-brand">
        <span className="sr-only">File name</span>
        <input
          value={filename}
          placeholder={suggested}
          onChange={(event) => {
            onFilename(event.target.value);
            setDone(null);
          }}
          onBlur={() => {
            if (stem(filename) !== filename) onFilename(stem(filename));
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") void download();
          }}
          spellCheck={false}
          className="w-56 min-w-0 bg-transparent px-2.5 py-1.5 text-sm text-ink outline-none placeholder:text-ink-faint"
        />
        <span className="border-l border-line bg-surface-sunken px-2 py-1.5 text-sm text-ink-faint">.pdf</span>
      </label>
      <Btn variant="primary" size={compact ? "sm" : "md"} onClick={() => void download()} disabled={busy}>
        {busy ? "Making the PDF…" : "Download PDF"}
      </Btn>
      {done && <span className="text-xs text-confirmed">{done}</span>}
      {error && <span className="text-xs text-contested">{error}</span>}
    </div>
  );
}

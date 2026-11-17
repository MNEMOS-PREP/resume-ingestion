/**
 * "Draft this line for that requirement" — asked for, checked, then applied or
 * not (2026-11-17).
 *
 * The model proposes wording; this module decides whether the proposal may be
 * shown. A draft that adds a number, drops one, or names a tool the line never
 * named is discarded on the server, and the student reads WHY rather than a
 * weaker line. An accepted draft is an ordinary edit of the tailored copy —
 * with where it came from and why, so the history can say.
 */
import { useState } from "react";

import { apiProblem, useEditTailoredBlock, useRewriteTailoredBlock } from "../api";
import type { TailoredResume } from "../types";
import { BLANK, FixDiff } from "./FixDiff";
import { Btn } from "../ui/primitives";

export function TailoredRewrite({
  copy,
  blockId,
  requirement,
  jdLine,
  allowedTerms,
  source = "manual",
  note,
  onApplied,
}: {
  copy: TailoredResume;
  blockId: string;
  requirement: string;
  jdLine?: string | null;
  /** Terms the student confirmed are true of this line. Nothing else is added. */
  allowedTerms?: string[];
  /** Recorded on the revision: `jd:<suggestion key>`. */
  source?: string;
  /** Recorded on the revision: why the change was made. */
  note?: string;
  onApplied?: () => void;
}) {
  const rewrite = useRewriteTailoredBlock(copy.resume_id, copy.id);
  const edit = useEditTailoredBlock(copy.resume_id, copy.id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const block = copy.blocks.find((b) => b.id === blockId);
  if (!block) return null;

  const result = rewrite.data;
  const apply = (text: string) =>
    edit.mutate(
      { blockId, patch: { text, source, note, expect_revision: copy.revision } },
      { onSuccess: () => onApplied?.() },
    );
  const blanks = draft.match(BLANK)?.length ?? 0;

  if (!result && !rewrite.isPending) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Btn
          size="sm"
          onClick={() => rewrite.mutate({ blockId, requirement, jdLine, allowedTerms })}
        >
          Draft wording for this
        </Btn>
        <span className="text-xs text-ink-faint">
          Reworded from your line only — a draft that adds a number or a tool is thrown away.
        </span>
        {rewrite.error && <span className="text-xs text-contested">{apiProblem(rewrite.error)}</span>}
      </div>
    );
  }

  if (rewrite.isPending) return <p className="text-xs text-ink-faint">Drafting from your own words…</p>;

  if (!result?.suggestion) {
    return (
      <div className="rounded-md border border-line bg-surface-sunken px-3 py-2 text-xs text-ink-soft">
        <p>{result?.refused ?? "No draft came back."}</p>
        <button
          type="button"
          onClick={() => rewrite.reset()}
          className="mt-1 font-medium text-brand hover:underline"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {editing ? (
        <div>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={3}
            aria-label="Your version of the line"
            className="w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm leading-relaxed text-ink outline-none focus:border-brand"
          />
          {blanks > 0 && <p className="text-xs text-reported">Fill every [blank] first.</p>}
        </div>
      ) : (
        <FixDiff original={block.text} suggestion={result.suggestion} compact />
      )}
      {result.why && <p className="text-xs text-ink-soft">{result.why}</p>}
      {result.adds.length > 0 && (
        <p className="text-xs text-ink-soft">
          Adds {result.adds.join(", ")} — only because you said you used it here.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Btn
          variant="primary"
          size="sm"
          disabled={edit.isPending || (editing && (!draft.trim() || blanks > 0))}
          onClick={() => apply(editing ? draft.trim() : result.suggestion!)}
        >
          {edit.isPending ? "Applying…" : editing ? "Apply my version" : "Accept"}
        </Btn>
        {!editing && (
          <Btn
            size="sm"
            onClick={() => {
              setDraft(result.suggestion!);
              setEditing(true);
            }}
          >
            Edit first
          </Btn>
        )}
        <Btn size="sm" variant="ghost" onClick={() => rewrite.reset()}>
          Discard
        </Btn>
      </div>
      {edit.error && <p className="text-xs text-contested">{apiProblem(edit.error)}</p>}
    </div>
  );
}

/**
 * A tailored copy, line by line, editable in place (2026-11-17).
 *
 * The centre of the tailoring workspace. It edits a COPY: every save is a new
 * revision of that copy, the resume it was made from is never written, and
 * any revision can be brought back. M02's job-description screen mounts it
 * with the job's evidence as tags on each line; M01's own versions page
 * mounts it bare.
 *
 * ── What a student can do to a line ────────────────────────────────────────
 *   edit     retype it (a line with a [blank] is not saved — the review
 *            page's rule, enforced again by the server)
 *   hide     keep it out of the PDF without losing it
 *   move     an entry with everything under it, or a bullet within its entry
 *   add      a line in their OWN words, after an entry or a bullet
 *   compare  what it said when the copy was made, against what it says now
 *
 * The contact line is masked on screen (FR-1.17) and so is locked: it prints
 * in the student's own download, and can be hidden or moved, never retyped.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@ai/core";

import {
  apiProblem,
  useAddTailoredBlock,
  useEditTailoredBlock,
  useMoveTailoredBlock,
  useRestoreTailored,
  useTailoredRevisions,
} from "../api";
import type { TailoredBlock, TailoredResume, TailoredRevision } from "../types";
import { BLANK, FixDiff } from "./FixDiff";
import { Btn } from "../ui/primitives";

/** A tag on a line — what M02 says this line evidences, or why it is flagged. */
export interface BlockAnnotation {
  key: string;
  label: string;
  /** direct · partial: evidence. unsupported: not in the original resume. */
  tone: "direct" | "partial" | "unsupported" | "added" | "info";
  title?: string;
}

/** Characters of a line to mark — a requirement's words where they appear. */
export interface BlockMark {
  start: number;
  end: number;
  tone?: "direct" | "partial" | "focus";
}

const TONE: Record<BlockAnnotation["tone"], string> = {
  direct: "border-confirmed-line bg-confirmed-soft text-ink",
  partial: "border-reported-line bg-reported-soft text-ink",
  unsupported: "border-contested-line bg-contested-soft text-ink",
  added: "border-brand-line bg-brand-soft text-ink",
  info: "border-line bg-surface-sunken text-ink-soft",
};

const MARK: Record<NonNullable<BlockMark["tone"]>, string> = {
  direct: "bg-confirmed-soft",
  partial: "bg-reported-soft",
  focus: "bg-brand-soft ring-1 ring-brand-line",
};

const ACTION_LABEL: Record<TailoredRevision["action"], string> = {
  created: "Copy made",
  edit: "Edited",
  hide: "Hidden",
  show: "Shown again",
  insert: "Line added",
  move: "Moved",
  restore: "Restored",
  style: "Photo",
};

/** A run of masked contact characters, shown as what it is. */
function masked(text: string, key: string | number): React.ReactNode {
  if (!text.includes("\u2588")) return text;
  return text.split(/(\u2588+)/).map((part, index) =>
    part.startsWith("\u2588") ? (
      <span
        key={`${key}-${index}`}
        title="Masked on screen, printed in your download"
        className="mx-0.5 inline-block rounded bg-surface-sunken px-1.5 align-baseline text-[0.6875rem] font-medium text-ink-faint"
      >
        hidden
      </span>
    ) : (
      part
    ),
  );
}

function marked(text: string, marks: BlockMark[] | undefined): React.ReactNode {
  if (!marks?.length) return masked(text, "t");
  const sorted = [...marks]
    .filter((m) => m.end > m.start && m.start >= 0 && m.end <= text.length)
    .sort((a, b) => a.start - b.start);
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (const mark of sorted) {
    if (mark.start < at) continue;
    if (mark.start > at) parts.push(masked(text.slice(at, mark.start), at));
    parts.push(
      <mark key={mark.start} className={`rounded-sm px-0.5 text-ink ${MARK[mark.tone ?? "direct"]}`}>
        {text.slice(mark.start, mark.end)}
      </mark>,
    );
    at = mark.end;
  }
  if (at < text.length) parts.push(masked(text.slice(at), at));
  return parts;
}

/** A server time, read as UTC: SQLite drops the zone, so a bare ISO string is UTC. */
function utc(iso: string): number {
  return new Date(/[zZ]$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
}

function ago(iso: string): string {
  const seconds = Math.max(0, (Date.now() - utc(iso)) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return new Date(utc(iso)).toLocaleDateString();
}

/** Bring a line into view inside the editor's own scroller, never the page. */
function intoPane(el: HTMLElement | null) {
  const pane = el?.closest<HTMLElement>("[data-editor-scroll]");
  if (!el || !pane || pane.scrollHeight <= pane.clientHeight) return;
  const top = el.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
  if (top < pane.scrollTop + 40 || top > pane.scrollTop + pane.clientHeight - 80) {
    pane.scrollTo({ top: top - pane.clientHeight / 3, behavior: "smooth" });
  }
}

/* ── one line ─────────────────────────────────────────────────────────────── */

function Line({
  copy,
  block,
  focused,
  annotations,
  marks,
  canUp,
  canDown,
  onUp,
  onDown,
  onFocus,
  onAnnotation,
}: {
  copy: TailoredResume;
  block: TailoredBlock;
  focused: boolean;
  annotations?: BlockAnnotation[];
  marks?: BlockMark[];
  canUp: boolean;
  canDown: boolean;
  onUp: () => void;
  onDown: () => void;
  onFocus?: (blockId: string) => void;
  onAnnotation?: (blockId: string, annotation: BlockAnnotation) => void;
}) {
  const edit = useEditTailoredBlock(copy.resume_id, copy.id);
  const add = useAddTailoredBlock(copy.resume_id, copy.id);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [draft, setDraft] = useState("");
  const [newLine, setNewLine] = useState("");
  const row = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (focused) intoPane(row.current);
  }, [focused]);

  useEffect(() => {
    if (editing) box.current?.focus();
  }, [editing]);

  const blanks = draft.match(BLANK)?.length ?? 0;
  const save = () => {
    const text = draft.trim();
    if (!text || blanks > 0 || text === block.text) return;
    edit.mutate(
      { blockId: block.id, patch: { text, expect_revision: copy.revision } },
      { onSuccess: () => setEditing(false) },
    );
  };
  const addLine = () => {
    const text = newLine.trim();
    if (!text || (text.match(BLANK)?.length ?? 0) > 0) return;
    add.mutate(
      { after: block.id, text, kind: block.section === "skills" ? "text" : "bullet" },
      {
        onSuccess: () => {
          setAdding(false);
          setNewLine("");
        },
      },
    );
  };

  const isHeading = block.kind === "heading";
  const textClass =
    block.kind === "name"
      ? "text-base font-semibold tracking-tight"
      : block.kind === "entry"
        ? "font-semibold"
        : block.kind === "subtitle"
          ? "italic text-ink-soft"
          : block.kind === "contact"
            ? "text-ink-soft"
            : "";
  const canAdd = block.kind === "entry" || block.kind === "bullet" || (block.section === "skills" && block.kind === "text");
  const error = edit.error ?? add.error;

  if (isHeading) {
    return (
      <div
        ref={row}
        className={`mt-5 flex items-center gap-2 border-b border-line pb-1 first:mt-0 ${block.hidden ? "opacity-50" : ""}`}
      >
        <h3 className="text-xs font-semibold tracking-wider text-ink-soft uppercase">{block.text}</h3>
      </div>
    );
  }

  return (
    <div
      ref={row}
      data-block={block.id}
      onClick={() => onFocus?.(block.id)}
      className={`group relative rounded-lg border px-2.5 py-1.5 transition-colors ${
        focused ? "border-brand-line bg-brand-soft/60" : "border-transparent hover:border-line hover:bg-surface-sunken/60"
      } ${block.kind === "bullet" ? "ml-3" : ""} ${block.hidden ? "opacity-55" : ""}`}
    >
      {block.edited && !block.hidden && (
        <span aria-hidden className="absolute top-2 bottom-2 -left-1 w-0.5 rounded-full bg-confirmed" />
      )}

      {editing ? (
        <div onClick={(event) => event.stopPropagation()}>
          <textarea
            ref={box}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setEditing(false);
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) save();
            }}
            rows={Math.min(6, Math.max(2, Math.ceil(draft.length / 80)))}
            aria-label="Edit this line"
            className="w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm leading-relaxed text-ink outline-none focus:border-brand"
          />
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <Btn variant="primary" size="sm" onClick={save} disabled={edit.isPending || !draft.trim() || blanks > 0 || draft.trim() === block.text}>
              {edit.isPending ? "Saving…" : "Save"}
            </Btn>
            <Btn variant="ghost" size="sm" onClick={() => setEditing(false)}>
              Cancel
            </Btn>
            <span className={`text-xs ${blanks ? "text-reported" : "text-ink-faint"}`}>
              {blanks
                ? `Fill ${blanks === 1 ? "the blank" : `all ${blanks} blanks`} with your own facts — a line with one isn't saved.`
                : "Only what you can explain out loud. Ctrl + Enter saves, Esc cancels."}
            </span>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-2">
          {block.kind === "bullet" && <span aria-hidden className="mt-px text-ink-faint">•</span>}
          <p className={`min-w-0 flex-1 text-[0.8125rem] leading-[1.6] text-ink ${textClass} ${block.hidden ? "line-through decoration-ink-faint" : ""}`}>
            {marked(block.text, marks)}
            {block.aside && (
              <span className="ml-2 text-xs font-normal whitespace-nowrap text-ink-faint">{block.aside}</span>
            )}
            {annotations?.map((annotation) => (
              <button
                key={annotation.key}
                type="button"
                title={annotation.title}
                onClick={(event) => {
                  event.stopPropagation();
                  onAnnotation?.(block.id, annotation);
                }}
                className={`ml-1.5 inline-flex translate-y-[-1px] items-center rounded-full border px-1.5 py-px align-middle text-[0.6875rem] leading-4 font-medium hover:brightness-95 ${TONE[annotation.tone]}`}
              >
                {annotation.label}
              </button>
            ))}
          </p>
          <div
            className={`absolute -top-3 right-1.5 z-10 flex items-center gap-0.5 rounded-md border border-line bg-surface px-0.5 shadow-sm ${
              focused ? "opacity-100" : "pointer-events-none opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 focus-within:pointer-events-auto focus-within:opacity-100"
            }`}
            onClick={(event) => event.stopPropagation()}
          >
            {!block.locked && !block.hidden && (
              <button
                type="button"
                onClick={() => {
                  setDraft(block.text);
                  setEditing(true);
                }}
                className="rounded-md px-1.5 py-0.5 text-xs font-medium text-ink-soft hover:bg-surface hover:text-ink"
              >
                Edit
              </button>
            )}
            {(block.edited || block.added) && !block.hidden && block.original && (
              <button
                type="button"
                aria-pressed={comparing}
                onClick={() => setComparing((on) => !on)}
                className="rounded-md px-1.5 py-0.5 text-xs font-medium text-ink-soft hover:bg-surface hover:text-ink"
              >
                Compare
              </button>
            )}
            {block.kind !== "name" && (
              <button
                type="button"
                onClick={() => edit.mutate({ blockId: block.id, patch: { hidden: !block.hidden } })}
                className="rounded-md px-1.5 py-0.5 text-xs font-medium text-ink-soft hover:bg-surface hover:text-ink"
              >
                {block.hidden ? "Show" : "Hide"}
              </button>
            )}
            {canUp && (
              <button type="button" aria-label="Move up" title="Move up" onClick={onUp} className="grid size-6 place-items-center rounded-md text-ink-soft hover:bg-surface hover:text-ink">
                <Icon name="chevronUp" size={14} />
              </button>
            )}
            {canDown && (
              <button type="button" aria-label="Move down" title="Move down" onClick={onDown} className="grid size-6 place-items-center rounded-md text-ink-soft hover:bg-surface hover:text-ink">
                <Icon name="chevronDown" size={14} />
              </button>
            )}
            {canAdd && !block.hidden && (
              <button type="button" aria-label="Add a line after this" title="Add a line after this" onClick={() => setAdding(true)} className="grid size-6 place-items-center rounded-md text-ink-soft hover:bg-surface hover:text-ink">
                <Icon name="plus" size={14} />
              </button>
            )}
          </div>
        </div>
      )}

      {((block.locked && block.kind !== "name") || block.added || block.hidden) && !editing && (
        <p className="mt-0.5 pl-4 text-[0.6875rem] text-ink-faint">
          {block.hidden
            ? "Hidden — not in the PDF"
            : block.locked
              ? "Contact details or a link — masked on screen, printed in your download"
              : "Added by you"}
        </p>
      )}

      {comparing && !editing && (
        <div className="mt-2" onClick={(event) => event.stopPropagation()}>
          <FixDiff original={block.original} suggestion={block.text} compact />
        </div>
      )}

      {adding && (
        <div className="mt-2 rounded-md border border-dashed border-line p-2" onClick={(event) => event.stopPropagation()}>
          <label className="text-xs font-medium text-ink-faint" htmlFor={`add-${block.id}`}>
            A new line, in your own words
          </label>
          <textarea
            id={`add-${block.id}`}
            autoFocus
            value={newLine}
            onChange={(event) => setNewLine(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setAdding(false);
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) addLine();
            }}
            rows={2}
            className="mt-1 w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-brand"
          />
          <div className="mt-1 flex items-center gap-2">
            <Btn variant="primary" size="sm" onClick={addLine} disabled={add.isPending || !newLine.trim()}>
              {add.isPending ? "Adding…" : "Add line"}
            </Btn>
            <Btn variant="ghost" size="sm" onClick={() => setAdding(false)}>
              Cancel
            </Btn>
            <span className="text-xs text-ink-faint">Nothing is written for you here — only what you did.</span>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-1 pl-4 text-xs text-contested">
          {apiProblem(error)}
        </p>
      )}
    </div>
  );
}

/* ── history ──────────────────────────────────────────────────────────────── */

function History({ copy, onClose }: { copy: TailoredResume; onClose: () => void }) {
  const revisions = useTailoredRevisions(copy.resume_id, copy.id);
  const restore = useRestoreTailored(copy.resume_id, copy.id);
  return (
    <div className="border-b border-line bg-surface-sunken px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-ink">Version history</p>
        <button type="button" onClick={onClose} className="text-xs font-medium text-ink-soft hover:text-ink">
          Close
        </button>
      </div>
      <p className="mt-0.5 text-xs text-ink-faint">
        Restoring a version adds it as a new one — nothing after it is lost.
      </p>
      {revisions.isLoading && <p className="mt-2 text-xs text-ink-faint">Loading…</p>}
      <ol className="mt-2 max-h-72 space-y-2 overflow-y-auto pr-1">
        {revisions.data?.map((revision) => (
          <li key={revision.n} className="rounded-lg border border-line bg-surface px-3 py-2">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
              <span className="font-semibold text-ink" data-numeric>
                v{revision.n}
              </span>
              <span className="text-ink-soft">{ACTION_LABEL[revision.action] ?? revision.action}</span>
              {revision.source.startsWith("jd:") && (
                <span className="rounded-full bg-brand-soft px-1.5 text-[0.6875rem] font-medium text-brand">
                  from a suggestion
                </span>
              )}
              <span className="text-ink-faint">{ago(revision.created_at)}</span>
              {revision.n !== copy.revision && (
                <button
                  type="button"
                  disabled={restore.isPending}
                  onClick={() => restore.mutate(revision.n)}
                  className="ml-auto text-xs font-medium text-brand hover:underline disabled:opacity-50"
                >
                  Restore
                </button>
              )}
              {revision.n === copy.revision && <span className="ml-auto text-[0.6875rem] text-ink-faint">current</span>}
            </div>
            {revision.action === "edit" && revision.after && (
              <div className="mt-1.5">
                <FixDiff original={revision.before ?? ""} suggestion={revision.after} compact />
              </div>
            )}
            {revision.action !== "edit" && (revision.before || revision.after) && (
              <p className="mt-1 line-clamp-2 text-xs text-ink-soft">{revision.after ?? revision.before}</p>
            )}
            {revision.note && <p className="mt-1 text-xs text-ink-faint">Why: {revision.note}</p>}
          </li>
        ))}
      </ol>
      {restore.error && <p className="mt-2 text-xs text-contested">{apiProblem(restore.error)}</p>}
    </div>
  );
}

/* ── the editor ───────────────────────────────────────────────────────────── */

export function TailoredEditor({
  copy,
  focusId,
  onFocus,
  annotations,
  onAnnotation,
  marks,
  header,
}: {
  copy: TailoredResume;
  focusId?: string | null;
  onFocus?: (blockId: string) => void;
  annotations?: Record<string, BlockAnnotation[]>;
  onAnnotation?: (blockId: string, annotation: BlockAnnotation) => void;
  marks?: Record<string, BlockMark[]>;
  /** Anything the host wants above the lines (a filter, a note). */
  header?: React.ReactNode;
}) {
  const move = useMoveTailoredBlock(copy.resume_id, copy.id);
  const restore = useRestoreTailored(copy.resume_id, copy.id);
  const revisions = useTailoredRevisions(copy.resume_id, copy.id);
  const [history, setHistory] = useState(false);

  // Undo goes to the state before the last real change. A restore is itself a
  // new version, so "current minus one" would undo an undo (a redo): follow
  // each restore back to the version it copied first.
  const undoTo = useMemo(() => {
    const byN = new Map((revisions.data ?? []).map((r) => [r.n, r]));
    let n = copy.revision;
    for (let guard = 0; guard < 500; guard += 1) {
      const revision = byN.get(n);
      const copied = revision?.action === "restore" ? Number(/(\d+)/.exec(revision.after ?? "")?.[1]) : NaN;
      if (!Number.isFinite(copied)) break;
      n = copied;
    }
    return revisions.data && n > 0 ? n - 1 : null;
  }, [copy.revision, revisions.data]);

  // Neighbours for moving: entries among entries of their section, bullets
  // among bullets of their entry.
  const siblings = useMemo(() => {
    const out: Record<string, { prev?: string; next?: string }> = {};
    const groups = new Map<string, string[]>();
    for (const block of copy.blocks) {
      let key: string | null = null;
      if (block.kind === "entry") key = `entries:${block.section_id}`;
      else if (block.kind === "bullet") key = `bullets:${block.group ?? block.section_id}`;
      if (!key) continue;
      groups.set(key, [...(groups.get(key) ?? []), block.id]);
    }
    for (const ids of groups.values()) {
      ids.forEach((id, index) => {
        out[id] = { prev: ids[index - 1], next: ids[index + 1] };
      });
    }
    return out;
  }, [copy.blocks]);

  return (
    <section aria-label="Resume editor" className="panel flex min-h-0 flex-col overflow-hidden bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <p className="text-sm font-semibold text-ink">Resume</p>
        <span className="text-xs text-ink-faint" data-numeric>
          v{copy.revision} · {copy.edited} change{copy.edited === 1 ? "" : "s"}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <Btn
            size="sm"
            variant="ghost"
            disabled={undoTo === null || restore.isPending}
            onClick={() => undoTo !== null && restore.mutate(undoTo)}
            title="Back to the version before the last change"
          >
            Undo
          </Btn>
          <Btn size="sm" variant={history ? "secondary" : "ghost"} aria-pressed={history} onClick={() => setHistory((on) => !on)}>
            <Icon name="clock" size={13} /> History
          </Btn>
        </div>
      </div>
      {history && <History copy={copy} onClose={() => setHistory(false)} />}
      {header}
      {move.error && (
        <p role="alert" className="border-b border-line px-4 py-2 text-xs text-contested">
          {apiProblem(move.error)}
        </p>
      )}
      <div data-editor-scroll className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {copy.blocks.map((block) => {
          const near = siblings[block.id] ?? {};
          return (
            <Line
              key={block.id}
              copy={copy}
              block={block}
              focused={focusId === block.id}
              annotations={annotations?.[block.id]}
              marks={marks?.[block.id]}
              canUp={Boolean(near.prev) && !move.isPending}
              canDown={Boolean(near.next) && !move.isPending}
              onUp={() => near.prev && move.mutate({ block_id: block.id, before: near.prev })}
              onDown={() => near.next && move.mutate({ block_id: near.next, before: block.id })}
              onFocus={onFocus}
              onAnnotation={onAnnotation}
            />
          );
        })}
      </div>
    </section>
  );
}

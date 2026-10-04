/**
 * Your library — everything you have had on a resume, kept (2026-10-04).
 *
 * Two requests, one page:
 *
 * - **Progression.** Removing a resume does not remove the projects, skills,
 *   achievements and certifications it held. They are here, with where each
 *   came from, deleted versions included.
 * - **Speed.** Starting a resume or fixing a line means picking from what you
 *   already wrote. "Build a new resume" turns a selection into resume text —
 *   copied, downloaded, or checked straight away as a new resume.
 *
 * Achievements and certifications are shown together: resumes head them as one
 * section as often as two, so which of the two a line is was a guess, and a
 * guess the student can change from the item's edit form.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Icon, PageHeader } from "@ai/core";

import {
  useAddLibraryItem,
  useCandidateResumes,
  useClearLibrary,
  useDeleteLibraryItem,
  useEditLibraryItem,
  useIngestResume,
  useLibrary,
} from "../api";
import type { LibraryItem, LibraryKind } from "../types";
import { useCandidateId } from "./candidate-hook";
import { ConfirmDialog } from "./ConfirmDialog";
import {
  KIND_LABEL,
  LIBRARY_GROUPS,
  TITLED,
  byContext,
  compose,
  downloadAs,
  inGroup,
  sourceNote,
  type LibraryGroupKey,
} from "./library";
import { Btn, Empty, Panel, SkeletonRows } from "../ui/primitives";

const INPUT =
  "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm leading-relaxed text-ink outline-none placeholder:text-ink-faint focus:border-brand";

const ADDABLE: LibraryKind[] = ["achievement", "certification", "project", "experience", "education", "skill"];

/* ── one item: read, edit, remove ──────────────────────────────────────── */

function IconButton({ label, icon, onClick }: { label: string; icon: "copy" | "trash" | "check"; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="grid size-8 place-items-center rounded-md text-ink-faint hover:bg-surface-sunken hover:text-ink"
    >
      <Icon name={icon} size={16} />
    </button>
  );
}

function ItemEditor({
  candidateId,
  item,
  onDone,
}: {
  candidateId: string;
  item: LibraryItem;
  onDone: () => void;
}) {
  const edit = useEditLibraryItem(candidateId);
  const [text, setText] = useState(item.text);
  const [context, setContext] = useState(item.context);
  const [kind, setKind] = useState<LibraryKind>(item.kind);
  const honour = item.kind === "achievement" || item.kind === "certification";

  const save = () =>
    edit.mutate(
      {
        itemId: item.id,
        ...(text.trim() !== item.text ? { text: text.trim() } : {}),
        ...(context.trim() !== item.context ? { context: context.trim() } : {}),
        ...(kind !== item.kind ? { kind } : {}),
      },
      { onSuccess: onDone },
    );

  return (
    <div className="space-y-2">
      <label className="block">
        <span className="text-xs font-medium text-ink-faint">The line</span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") onDone();
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && text.trim()) save();
          }}
          rows={item.kind === "skill" ? 1 : 3}
          autoFocus
          className={`mt-1 ${INPUT}`}
        />
      </label>
      {TITLED.has(item.kind) && (
        <label className="block">
          <span className="text-xs font-medium text-ink-faint">Under the title</span>
          <input value={context} onChange={(event) => setContext(event.target.value)} className={`mt-1 ${INPUT}`} />
        </label>
      )}
      {honour && (
        <label className="block">
          <span className="text-xs font-medium text-ink-faint">It's an</span>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as LibraryKind)}
            className={`mt-1 ${INPUT} sm:w-auto`}
          >
            <option value="achievement">Achievement</option>
            <option value="certification">Certification</option>
          </select>
        </label>
      )}
      {edit.error && (
        <p role="alert" className="text-sm text-contested">
          That didn't save — try again.
        </p>
      )}
      <div className="flex gap-2">
        <Btn variant="primary" size="sm" onClick={save} disabled={edit.isPending || !text.trim()}>
          {edit.isPending ? "Saving…" : "Save"}
        </Btn>
        <Btn variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Btn>
      </div>
    </div>
  );
}

function ItemRow({
  candidateId,
  item,
  note,
  selecting,
  selected,
  onToggle,
}: {
  candidateId: string;
  item: LibraryItem;
  note: string;
  selecting: boolean;
  selected: boolean;
  onToggle: () => void;
}) {
  const remove = useDeleteLibraryItem(candidateId);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [copied, setCopied] = useState(false);
  const honour = item.kind === "achievement" || item.kind === "certification";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(item.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard refused — the text is on screen to select by hand */
    }
  };

  return (
    // Actions beside the text from `sm` up; under it on a phone, where three
    // controls beside the line squeezed it into a third of the width.
    <li className={`flex gap-3 py-3 ${selecting ? "items-start" : "flex-col gap-y-1 sm:flex-row sm:items-start"}`}>
      {selecting && (
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={`Include on the new resume: ${item.text.slice(0, 80)}`}
          className="mt-1 size-4 shrink-0 accent-[var(--color-brand)]"
        />
      )}
      <div className="min-w-0 flex-1">
        {editing ? (
          <ItemEditor candidateId={candidateId} item={item} onDone={() => setEditing(false)} />
        ) : (
          <>
            <p className="text-sm leading-relaxed text-ink">{item.text}</p>
            <p className="mt-0.5 text-xs text-ink-faint">
              {honour && <span className="font-medium text-ink-soft">{KIND_LABEL[item.kind]} · </span>}
              {note}
            </p>
          </>
        )}
        {confirming && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-ink-soft">Remove it from your library?</span>
            <Btn size="sm" onClick={() => remove.mutate(item.id)} disabled={remove.isPending}>
              {remove.isPending ? "Removing…" : "Remove"}
            </Btn>
            <Btn variant="ghost" size="sm" onClick={() => setConfirming(false)}>
              Keep
            </Btn>
          </div>
        )}
      </div>
      {!selecting && !editing && !confirming && (
        <div className="-ml-2 flex shrink-0 items-center sm:ml-0">
          <IconButton label={copied ? "Copied" : "Copy"} icon={copied ? "check" : "copy"} onClick={copy} />
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded-md px-2 py-1.5 text-xs font-medium text-ink-soft hover:bg-surface-sunken hover:text-ink"
          >
            Edit
          </button>
          <IconButton label="Remove from library" icon="trash" onClick={() => setConfirming(true)} />
        </div>
      )}
    </li>
  );
}

/* ── skills: chips ─────────────────────────────────────────────────────── */

function SkillChips({
  candidateId,
  items,
  selecting,
  selected,
  onToggle,
}: {
  candidateId: string;
  items: LibraryItem[];
  selecting: boolean;
  selected: Set<string>;
  onToggle: (id: string) => void;
}) {
  const remove = useDeleteLibraryItem(candidateId);
  return (
    <ul className="flex flex-wrap gap-1.5 py-3" aria-label="Skills">
      {items.map((item) =>
        selecting ? (
          <li key={item.id}>
            <button
              type="button"
              aria-pressed={selected.has(item.id)}
              onClick={() => onToggle(item.id)}
              className={`rounded-full border px-3 py-1 text-sm ${
                selected.has(item.id) ? "border-brand-line bg-brand-soft text-ink" : "border-line text-ink-soft"
              }`}
            >
              {item.text}
            </button>
          </li>
        ) : (
          <li key={item.id} className="flex items-center rounded-full border border-line py-0.5 pl-3 pr-1 text-sm text-ink">
            {item.text}
            <button
              type="button"
              aria-label={`Remove ${item.text} from your library`}
              onClick={() => remove.mutate(item.id)}
              className="ml-1 grid size-6 place-items-center rounded-full text-ink-faint hover:bg-surface-sunken hover:text-ink"
            >
              <Icon name="close" size={12} />
            </button>
          </li>
        ),
      )}
    </ul>
  );
}

/* ── adding what no resume says yet ────────────────────────────────────── */

function AddForm({ candidateId, onDone }: { candidateId: string; onDone: (kind: LibraryKind) => void }) {
  const add = useAddLibraryItem(candidateId);
  const [kind, setKind] = useState<LibraryKind>("achievement");
  const [text, setText] = useState("");
  const [context, setContext] = useState("");

  return (
    <Panel className="mb-6 px-4 py-4">
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!text.trim()) return;
          add.mutate(
            { kind, text: text.trim(), context: TITLED.has(kind) ? context.trim() : "" },
            { onSuccess: () => onDone(kind) },
          );
        }}
      >
        <p className="text-sm font-medium text-ink">Add to your library</p>
        <div className="grid gap-3 sm:grid-cols-[12rem_minmax(0,1fr)]">
          <label className="block">
            <span className="text-xs font-medium text-ink-faint">What it is</span>
            <select value={kind} onChange={(event) => setKind(event.target.value as LibraryKind)} className={`mt-1 ${INPUT}`}>
              {ADDABLE.map((value) => (
                <option key={value} value={value}>
                  {KIND_LABEL[value]}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-faint">
              {kind === "skill" ? "The skill" : kind === "education" ? "Degree, institution, years" : "The line, as it would read on a resume"}
            </span>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={kind === "skill" ? 1 : 2}
              autoFocus
              placeholder={
                kind === "certification"
                  ? "e.g. AWS Certified Cloud Practitioner (2026)"
                  : kind === "achievement"
                    ? "e.g. Ranked 12th of 900 teams at Smart India Hackathon 2026"
                    : ""
              }
              className={`mt-1 ${INPUT}`}
            />
          </label>
        </div>
        {TITLED.has(kind) && (
          <label className="block">
            <span className="text-xs font-medium text-ink-faint">Under the title (optional)</span>
            <input
              value={context}
              onChange={(event) => setContext(event.target.value)}
              placeholder={kind === "project" ? "The project's name" : "Your role, the organisation"}
              className={`mt-1 ${INPUT}`}
            />
          </label>
        )}
        {add.error && (
          <p role="alert" className="text-sm text-contested">
            That didn't save — try again.
          </p>
        )}
        <div className="flex gap-2">
          <Btn type="submit" variant="primary" disabled={add.isPending || !text.trim()}>
            {add.isPending ? "Adding…" : "Add"}
          </Btn>
          <Btn type="button" variant="ghost" onClick={() => onDone(kind)}>
            Cancel
          </Btn>
        </div>
      </form>
    </Panel>
  );
}

/* ── building a new resume from a selection ────────────────────────────── */

/** Mounted only while open, so the text is composed once and a refetch of the
 *  library underneath cannot throw away what the student typed into it. */
function ComposerDialog({
  candidateId,
  items,
  onClose,
}: {
  candidateId: string;
  items: LibraryItem[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const navigate = useNavigate();
  const ingest = useIngestResume();
  const [text, setText] = useState(() => compose(items));
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby="composer-title"
      onClose={onClose}
      className="m-auto w-[min(48rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 text-ink shadow-raised backdrop:bg-black/40"
    >
      <div className="px-5 pt-5">
        <h2 id="composer-title" className="text-lg font-semibold tracking-tight">
          Your new resume
        </h2>
        <p className="mt-1 text-sm text-ink-soft">
          Built from {items.length} {items.length === 1 ? "item" : "items"}. Edit it here, then copy it into your
          resume file — your name and contact details aren't kept in the library, so add them at the top.
        </p>
        <label className="mt-3 block">
          <span className="sr-only">Resume text</span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={16}
            className={`${INPUT} font-[inherit]`}
          />
        </label>
        {ingest.error && (
          <p role="alert" className="mt-2 text-sm text-contested">
            That couldn't be checked — try again.
          </p>
        )}
        {ingest.isPending && (
          <p role="status" className="mt-2 text-sm text-ink-soft">
            Reading it the way an upload is read, questions included — this takes a few seconds.
          </p>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">
        <Btn
          variant="primary"
          disabled={ingest.isPending || !text.trim()}
          onClick={() =>
            ingest.mutate(
              { candidate_id: candidateId, raw_text: text },
              { onSuccess: (resume) => navigate(`/resumes/${resume.id}/review`) },
            )
          }
        >
          {ingest.isPending ? "Checking…" : "Check it as a new resume"}
        </Btn>
        <Btn
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            } catch {
              /* select it by hand */
            }
          }}
        >
          {copied ? "Copied" : "Copy"}
        </Btn>
        <Btn onClick={() => downloadAs("resume-from-library.txt", text)}>Download .txt</Btn>
        <Btn variant="ghost" className="ml-auto" onClick={onClose}>
          Close
        </Btn>
        <p className="w-full text-xs text-ink-faint">
          Checking it makes it your current resume and opens its review. Your other resumes stay.
        </p>
      </div>
    </dialog>
  );
}

/* ── the page ──────────────────────────────────────────────────────────── */

export function LibraryPage() {
  const candidateId = useCandidateId();
  const library = useLibrary(candidateId);
  const resumes = useCandidateResumes(candidateId);
  const clear = useClearLibrary(candidateId);

  const [filter, setFilter] = useState<LibraryGroupKey | "all">("all");
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [composing, setComposing] = useState(false);
  const [clearing, setClearing] = useState(false);

  const items = library.data?.items ?? [];
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = items.filter(
    (item) =>
      (filter === "all" || inGroup(item, filter)) &&
      words.every((word) => `${item.text} ${item.context}`.toLowerCase().includes(word)),
  );
  const chosen = useMemo(() => items.filter((item) => selected.has(item.id)), [items, selected]);

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const actions = (
    <div className="flex flex-wrap gap-2">
      <Btn onClick={() => setAdding(true)}>
        <Icon name="plus" size={14} /> Add
      </Btn>
      <Btn variant="primary" onClick={() => setSelecting(true)}>
        Build a new resume
      </Btn>
    </div>
  );

  if (library.isLoading) {
    return <SkeletonRows rows={8} />;
  }
  if (library.isError) {
    return (
      <Empty title="Your library couldn't be loaded">
        {(library.error as Error | null)?.message ?? "Try again in a moment."}
      </Empty>
    );
  }

  return (
    <>
      <div className="mb-6">
        <p className="mb-2 text-sm">
          <Link to="/resume" className="text-ink-soft hover:text-ink">
            ← Your resumes
          </Link>
        </p>
        <PageHeader
          title="Your library"
          subtitle="Everything you've had on a resume — kept even when you remove one, and ready to pick from for the next."
          actions={
            // Beside the title from `sm` up; on a phone a row of its own below,
            // or the title is squeezed into a column a word wide.
            items.length > 0 && !selecting ? <div className="hidden sm:block">{actions}</div> : undefined
          }
          how={
            <p>
              Each upload adds its project and job lines, achievements, certifications, education and skills here.
              The same line on two versions is one item. A line you improve on the review page is improved here too.
              Removing a resume leaves all of it; remove items here when you want them gone.
            </p>
          }
        />
      </div>

      {items.length > 0 && !selecting && <div className="mb-6 sm:hidden">{actions}</div>}

      {adding && (
        <AddForm
          candidateId={candidateId}
          onDone={(kind) => {
            setAdding(false);
            const group = LIBRARY_GROUPS.find((g) => (g.kinds as readonly LibraryKind[]).includes(kind));
            if (group && filter !== "all") setFilter(group.key);
          }}
        />
      )}

      {items.length === 0 ? (
        <Empty title="Nothing here yet">
          Your library fills as you upload resumes.{" "}
          <Link to="/resume" className="font-medium text-ink underline underline-offset-2">
            Add a resume
          </Link>{" "}
          or{" "}
          <button type="button" onClick={() => setAdding(true)} className="font-medium text-ink underline underline-offset-2">
            add something by hand
          </button>
          .
        </Empty>
      ) : (
        <>
          {selecting && (
            <div className="sticky top-16 z-10 mb-5 flex flex-wrap items-center gap-2 rounded-lg border border-brand-line bg-brand-soft px-4 py-2.5">
              <p className="mr-auto text-sm text-ink" data-numeric>
                <span className="font-medium">{selected.size} selected</span>
                <span className="text-ink-soft"> — tick what goes on the new resume</span>
              </p>
              <Btn
                size="sm"
                onClick={() => setSelected((current) => new Set([...current, ...shown.map((item) => item.id)]))}
              >
                Select all shown
              </Btn>
              <Btn variant="primary" size="sm" disabled={selected.size === 0} onClick={() => setComposing(true)}>
                Preview
              </Btn>
              <Btn
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSelecting(false);
                  setSelected(new Set());
                }}
              >
                Cancel
              </Btn>
            </div>
          )}

          <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
            <div
              className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none]"
              role="group"
              aria-label="Show"
            >
              {[{ key: "all" as const, label: "All" }, ...LIBRARY_GROUPS].map((group) => {
                const count =
                  group.key === "all" ? items.length : items.filter((item) => inGroup(item, group.key)).length;
                if (count === 0) return null;
                return (
                  <button
                    key={group.key}
                    type="button"
                    aria-pressed={filter === group.key}
                    onClick={() => setFilter(group.key)}
                    className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium ${
                      filter === group.key ? "border-brand-line bg-brand-soft text-ink" : "border-line text-ink-soft hover:text-ink"
                    }`}
                  >
                    {group.label} <span data-numeric>{count}</span>
                  </button>
                );
              })}
            </div>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search"
              aria-label="Search your library"
              className={`${INPUT} sm:ml-auto sm:w-56`}
            />
          </div>

          {LIBRARY_GROUPS.map((group) => {
            const inThis = shown.filter((item) => inGroup(item, group.key));
            if (inThis.length === 0) return null;
            return (
              <section key={group.key} className="mb-9" aria-labelledby={`lib-${group.key}`}>
                <h2 id={`lib-${group.key}`} className="mb-1 text-sm font-semibold text-ink">
                  {group.label} <span className="font-normal text-ink-faint" data-numeric>{inThis.length}</span>
                </h2>
                {group.key === "skills" ? (
                  <SkillChips
                    candidateId={candidateId}
                    items={inThis}
                    selecting={selecting}
                    selected={selected}
                    onToggle={toggle}
                  />
                ) : group.key === "experience" || group.key === "projects" ? (
                  byContext(inThis).map((titled) => (
                    <div key={titled.context || "untitled"} className="border-t border-line pt-3 first:border-t-0">
                      <p className="text-sm font-medium text-ink-soft">{titled.context || "Lines without a title"}</p>
                      <ul className="divide-y divide-line">
                        {titled.items.map((item) => (
                          <ItemRow
                            key={item.id}
                            candidateId={candidateId}
                            item={item}
                            note={sourceNote(item, resumes.data)}
                            selecting={selecting}
                            selected={selected.has(item.id)}
                            onToggle={() => toggle(item.id)}
                          />
                        ))}
                      </ul>
                    </div>
                  ))
                ) : (
                  <ul className="divide-y divide-line">
                    {inThis.map((item) => (
                      <ItemRow
                        key={item.id}
                        candidateId={candidateId}
                        item={item}
                        note={sourceNote(item, resumes.data)}
                        selecting={selecting}
                        selected={selected.has(item.id)}
                        onToggle={() => toggle(item.id)}
                      />
                    ))}
                  </ul>
                )}
              </section>
            );
          })}

          {shown.length === 0 && (
            <p className="text-sm text-ink-soft">Nothing in your library matches that.</p>
          )}

          {!selecting && (
            <p className="mt-10 border-t border-line pt-4 text-xs text-ink-faint">
              Want it all gone?{" "}
              <button type="button" onClick={() => setClearing(true)} className="font-medium text-contested hover:underline">
                Clear your library
              </button>
            </p>
          )}
        </>
      )}

      {composing && (
        <ComposerDialog candidateId={candidateId} items={chosen} onClose={() => setComposing(false)} />
      )}

      <ConfirmDialog
        open={clearing}
        title="Clear your whole library?"
        confirmLabel="Clear library"
        busyLabel="Clearing…"
        busy={clear.isPending}
        error={clear.error ? "That didn't go through. Nothing was removed." : null}
        onClose={() => setClearing(false)}
        onConfirm={() => clear.mutate(undefined, { onSuccess: () => setClearing(false) })}
      >
        <p>
          All {items.length} items go — the record of what you've done across resumes. Your resumes themselves
          stay, and the next one you upload starts the library again. This can't be undone.
        </p>
      </ConfirmDialog>
    </>
  );
}

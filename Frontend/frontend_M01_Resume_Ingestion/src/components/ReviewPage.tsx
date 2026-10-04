/**
 * Review & fix — the resume check by check, each failing line a card you can
 * act on, and the document updating beside it as you do (2026-10-04).
 *
 * ── What it borrows, and from where ─────────────────────────────────────────
 * Asked for as "what Resume Worded charges for, here, free". Its layout is the
 * right one and §11.7 already took it for the Claim Map: checks on the left,
 * the work in the middle, the document on the right. The middle borrows from a
 * requirements-review tool the student built themselves: each problem as a
 * card — the original, why it matters, a fix shown as a diff — with Apply,
 * Edit and Ignore, and the document reflecting every applied fix at once.
 *
 * ── What it refuses, on purpose (M01 §15 decisions 1 and 2) ─────────────────
 * - **No overall score.** The rail counts checks passed and lines to fix,
 *   each of which opens to a list. A single number is the most memorable
 *   thing on a page and the least defensible.
 * - **No locks.** A student's own diagnostic is never gated.
 * - **A fix never adds a fact.** Suggestions either remove words or leave a
 *   [blank] for a fact only the student has, and a line that still has one is
 *   not saved. "Suggest wording" asks the model to restructure, never to add.
 *
 * An applied fix is a real edit (`PATCH …/claims/{id}`), re-scored on the way
 * through, so the check it fails re-runs and the card goes away if it passes.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useEditClaim, useResume, useReview, useRewriteClaim } from "../api";
import { DrillPanel } from "./DrillPanel";
import { PdfHighlightViewer } from "./PdfHighlightViewer";
import { ResumeTabs } from "./ResumeTabs";
import { SECTION_LABEL } from "./sections";
import { Btn, Empty, Panel, SkeletonRows } from "../ui/primitives";
import type { DocumentSegment, ResumeReview, ReviewCheck, ReviewGroup, ReviewIssue } from "../types";

/** A blank only the student can fill. Kept in step with `review.BLANK`. */
const BLANK = /\[[^[\]]+\]/g;

const GROUP_LABEL: Record<ReviewGroup, string> = {
  defend: "Defend",
  impact: "Impact",
  clarity: "Clarity",
  complete: "Complete",
};

/** Checks whose suggestion the model can restructure (never add to). */
const WORDING = new Set(["risky", "numbers", "verbs", "length", "ownership"]);

function typing(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
  );
}

/* ── ignored issues: this student's, kept in this browser ──────────────── */

function useIgnored(resumeId: string) {
  const key = `m01.review.ignored.${resumeId}`;
  const [ignored, setIgnored] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(key) ?? "[]") as string[]);
    } catch {
      return new Set();
    }
  });
  const toggle = useCallback(
    (id: string) =>
      setIgnored((current) => {
        const next = new Set(current);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        try {
          localStorage.setItem(key, JSON.stringify([...next]));
        } catch {
          /* still ignored for this visit */
        }
        return next;
      }),
    [key],
  );
  return { ignored, toggle };
}

/* ── a diff that shows exactly what a fix changes ──────────────────────── */

function Blanks({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (const match of text.matchAll(BLANK)) {
    if (match.index > at) parts.push(text.slice(at, match.index));
    parts.push(
      <mark key={match.index} className="rounded bg-reported-soft px-0.5 font-medium text-ink">
        {match[0]}
      </mark>,
    );
    at = match.index + match[0].length;
  }
  if (at < text.length) parts.push(text.slice(at));
  return <>{parts}</>;
}

function FixDiff({ original, suggestion }: { original: string; suggestion: string }) {
  return (
    <div className="space-y-1.5 overflow-hidden rounded-lg border border-line">
      <p className="bg-contested-soft px-3 py-2 text-sm leading-relaxed text-ink-soft line-through decoration-contested/60">
        {original}
      </p>
      <p className="bg-confirmed-soft px-3 py-2 text-sm leading-relaxed text-ink">
        <Blanks text={suggestion} />
      </p>
    </div>
  );
}

/* ── one card per failing line ─────────────────────────────────────────── */

function IssueCard({
  resumeId,
  issue,
  position,
  of,
  focused,
  follow,
  ignored,
  onFocus,
  onIgnore,
}: {
  resumeId: string;
  issue: ReviewIssue;
  position: number;
  of: number;
  focused: boolean;
  /** The student is moving through cards by keyboard: keep the focused one in view. */
  follow: boolean;
  ignored: boolean;
  onFocus: () => void;
  onIgnore: () => void;
}) {
  const edit = useEditClaim(resumeId);
  const wording = useRewriteClaim(resumeId);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [drill, setDrill] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const card = useRef<HTMLElement>(null);

  // The model's restructure, once asked for, replaces the template's.
  const suggestion = wording.data?.suggestion ?? issue.suggestion;
  const blanks = suggestion ? (suggestion.match(BLANK)?.length ?? 0) : 0;
  const draftBlanks = draft.match(BLANK)?.length ?? 0;
  const canEdit = Boolean(issue.claim_id);

  const open = useCallback((text: string) => {
    setDraft(text);
    setEditing(true);
  }, []);

  // On opening the editor, select the first blank so typing replaces it.
  useEffect(() => {
    if (!editing || !box.current) return;
    const el = box.current;
    el.focus();
    const first = BLANK.exec(el.value);
    BLANK.lastIndex = 0;
    if (first) el.setSelectionRange(first.index, first.index + first[0].length);
  }, [editing]);

  // Into view only when the student moved to it with J / K. On load it would
  // scroll a phone past the summary (and a mount-time guard is not enough:
  // React runs mount effects twice in development).
  useEffect(() => {
    if (focused && follow) card.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focused, follow]);

  const save = useCallback(
    (text: string) => {
      if (!issue.claim_id) return;
      edit.mutate(
        { claimId: issue.claim_id, field: "text", value: text.trim() },
        { onSuccess: () => setEditing(false) },
      );
    },
    [edit, issue.claim_id],
  );

  const apply = useCallback(() => {
    if (!suggestion || !canEdit) return;
    if (blanks === 0) save(suggestion);
    else open(suggestion);
  }, [blanks, canEdit, open, save, suggestion]);

  // A / E / I on the focused card, as in the review tool this borrows from.
  useEffect(() => {
    if (!focused || editing) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === "a" && suggestion && canEdit) {
        event.preventDefault();
        apply();
      } else if (key === "e" && canEdit) {
        event.preventDefault();
        open(issue.original);
      } else if (key === "i") {
        event.preventDefault();
        onIgnore();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [apply, canEdit, editing, focused, issue.original, onIgnore, open, suggestion]);

  return (
    <article
      ref={card}
      onClick={onFocus}
      className={`panel overflow-hidden transition-colors ${focused ? "border-brand-line ring-1 ring-brand-line" : ""} ${
        ignored ? "opacity-60" : ""
      }`}
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3 text-xs text-ink-faint">
        {issue.section && (
          <span className="rounded-full border border-line px-2 py-0.5 font-medium text-ink-soft">
            {SECTION_LABEL[issue.section] ?? issue.section}
          </span>
        )}
        <span data-numeric>
          {position} of {of}
        </span>
        {ignored && <span className="font-medium">ignored</span>}
      </header>

      <div className="space-y-4 px-5 py-4">
        {issue.original && !suggestion && (
          <blockquote className="rounded-lg bg-surface-sunken px-3 py-2 text-sm leading-relaxed text-ink">
            {issue.original}
          </blockquote>
        )}

        <p className="text-sm leading-relaxed text-ink-soft">{issue.problem}</p>

        {issue.answer && (
          <div className="rounded-lg border border-line px-3 py-2">
            <p className="text-xs font-medium text-ink-faint">If they ask</p>
            <p className="mt-1 text-sm leading-relaxed text-ink">{issue.answer}</p>
          </div>
        )}

        {suggestion && !editing && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-faint">
              {blanks > 0
                ? `Suggested shape — fill ${blanks === 1 ? "the blank" : `the ${blanks} blanks`} with your own facts`
                : "Suggested fix"}
              {wording.data && " · restructured, nothing added"}
            </p>
            <FixDiff original={issue.original} suggestion={suggestion} />
          </div>
        )}

        {editing && (
          <div>
            <label className="text-xs font-medium text-ink-faint" htmlFor={`edit-${issue.id}`}>
              Your line
            </label>
            <textarea
              id={`edit-${issue.id}`}
              ref={box}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setEditing(false);
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && draftBlanks === 0)
                  save(draft);
              }}
              rows={3}
              className="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm leading-relaxed text-ink outline-none focus:border-brand"
            />
            <p className={`mt-1 text-xs ${draftBlanks ? "text-reported" : "text-ink-faint"}`}>
              {draftBlanks
                ? `Fill ${draftBlanks === 1 ? "the blank" : `all ${draftBlanks} blanks`} with your own facts — a line with one isn't saved.`
                : "Only what you can explain out loud. Ctrl + Enter saves."}
            </p>
          </div>
        )}

        {(edit.error || wording.error) && (
          <p role="alert" className="text-sm text-contested">
            {((edit.error ?? wording.error) as Error).message}
          </p>
        )}

        {drill && issue.claim_id && (
          <DrillPanel resumeId={resumeId} claimId={issue.claim_id} onClose={() => setDrill(false)} />
        )}
      </div>

      <footer className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">
        {editing ? (
          <>
            <Btn
              variant="primary"
              onClick={() => save(draft)}
              disabled={edit.isPending || !draft.trim() || draftBlanks > 0 || draft.trim() === issue.original}
            >
              {edit.isPending ? "Saving…" : "Save line"}
            </Btn>
            <Btn variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Btn>
          </>
        ) : (
          <>
            {suggestion && canEdit && (
              <Btn variant="primary" onClick={apply} disabled={edit.isPending}>
                {edit.isPending ? "Applying…" : blanks > 0 ? "Fill the blanks" : "Apply fix"}
                <span className="kbd ml-1 hidden sm:inline-grid">A</span>
              </Btn>
            )}
            {canEdit && (
              <Btn onClick={() => open(issue.original)}>
                Edit line <span className="kbd ml-1 hidden sm:inline-grid">E</span>
              </Btn>
            )}
            {issue.check === "risky" && issue.claim_id && (
              <Btn variant="ghost" onClick={() => setDrill((on) => !on)}>
                {drill ? "Hide the drill" : "Practise defending it"}
              </Btn>
            )}
            {issue.claim_id && WORDING.has(issue.check) && !wording.data && (
              <Btn variant="ghost" onClick={() => wording.mutate(issue.claim_id!)} disabled={wording.isPending}>
                {wording.isPending ? "Thinking…" : "Suggest wording"}
              </Btn>
            )}
            <Btn variant="ghost" className="ml-auto" onClick={onIgnore}>
              {ignored ? "Restore" : "Ignore"} <span className="kbd ml-1 hidden sm:inline-grid">I</span>
            </Btn>
          </>
        )}
      </footer>
    </article>
  );
}

/* ── the rail: checks, counted ─────────────────────────────────────────── */

function Rail({
  resumeId,
  review,
  ignored,
  selected,
  onSelect,
}: {
  resumeId: string;
  review: ResumeReview;
  ignored: Set<string>;
  selected: string;
  onSelect: (check: string) => void;
}) {
  const open = (check: ReviewCheck) => check.issues.filter((i) => !ignored.has(i.id)).length;
  const toFix = review.checks.filter((c) => open(c) > 0);
  const passed = review.checks.filter((c) => open(c) === 0);

  const row = (check: ReviewCheck, count: number) => (
    <li key={check.id}>
      <button
        type="button"
        onClick={() => onSelect(check.id)}
        aria-current={selected === check.id ? "true" : undefined}
        className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm ${
          selected === check.id ? "bg-brand-soft text-ink" : "text-ink-soft hover:bg-surface-sunken hover:text-ink"
        }`}
      >
        <span className="min-w-0 flex-1 truncate">{check.title}</span>
        {count > 0 ? (
          <span className="rounded-full bg-reported-soft px-2 py-0.5 text-xs font-semibold text-ink" data-numeric>
            {count}
          </span>
        ) : (
          <span aria-label="passed" className="text-confirmed">
            ✓
          </span>
        )}
      </button>
    </li>
  );

  return (
    <aside className="min-w-0 space-y-4 lg:sticky lg:top-20 lg:space-y-6 lg:self-start">
      <div>
        <p className="text-xs font-medium text-ink-faint">Resume review</p>
        <p className="mt-1 truncate text-sm font-medium text-ink">{review.filename ?? "Pasted text"}</p>
        {/* Counts, not a score: each segment is one check, and it opens. */}
        <p className="mt-4 text-2xl font-semibold tracking-tight text-ink" data-numeric>
          {passed.length}
          <span className="text-base font-normal text-ink-faint"> of {review.total} checks passed</span>
        </p>
        <div className="mt-2 flex gap-0.5" aria-hidden>
          {review.checks.map((check) => (
            <span
              key={check.id}
              className={`h-1.5 flex-1 rounded-full ${open(check) === 0 ? "bg-confirmed" : "bg-reported"}`}
            />
          ))}
        </div>
      </div>

      {/* On a phone the checks become one row of chips, so the first card is
          on the first screen rather than under eleven rows of rail. */}
      {toFix.length > 0 && (
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none] lg:hidden">
          {toFix.map((check) => (
            <button
              key={check.id}
              type="button"
              onClick={() => onSelect(check.id)}
              aria-current={selected === check.id ? "true" : undefined}
              className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium ${
                selected === check.id ? "border-brand-line bg-brand-soft text-ink" : "border-line text-ink-soft"
              }`}
            >
              {check.title}
              <span className="rounded-full bg-reported-soft px-1.5 text-ink" data-numeric>
                {open(check)}
              </span>
            </button>
          ))}
        </div>
      )}
      {toFix.length > 0 && (
        <div className="hidden lg:block">
          <p className="px-2.5 text-xs font-medium text-ink-faint">To fix</p>
          <ul className="mt-1 space-y-0.5">{toFix.map((c) => row(c, open(c)))}</ul>
        </div>
      )}
      {passed.length > 0 && (
        <div className="hidden lg:block">
          <p className="px-2.5 text-xs font-medium text-ink-faint">Passed</p>
          <ul className="mt-1 space-y-0.5">{passed.map((c) => row(c, 0))}</ul>
        </div>
      )}

      <div className="hidden border-t border-line pt-4 lg:block">
        <p className="px-2.5 text-xs font-medium text-ink-faint">Tools</p>
        <ul className="mt-1 space-y-0.5 text-sm">
          <li>
            <Link to={`/resumes/${resumeId}`} className="block rounded-lg px-2.5 py-2 text-ink-soft hover:bg-surface-sunken hover:text-ink">
              What an interviewer will ask
            </Link>
          </li>
          <li>
            <Link to={`/resumes/${resumeId}/target`} className="block rounded-lg px-2.5 py-2 text-ink-soft hover:bg-surface-sunken hover:text-ink">
              Check it against a job
            </Link>
          </li>
          <li>
            <Link to="/mock" className="block rounded-lg px-2.5 py-2 text-ink-soft hover:bg-surface-sunken hover:text-ink">
              Practise an interview on it
            </Link>
          </li>
        </ul>
      </div>
    </aside>
  );
}

/* ── the document, with every applied fix in it ────────────────────────── */

function downloadText(review: ResumeReview) {
  const text = review.document.map((s) => s.text).join("");
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${(review.filename ?? "resume").replace(/\.[^.]+$/, "")}-edited.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Bring a line into view INSIDE the document pane, never by moving the page.
 *
 * `scrollIntoView` scrolls every ancestor, so on a phone — where the pane is
 * not its own scroller — opening the review jumped straight past the cards to
 * the document. Only a pane that actually scrolls is moved.
 */
function scrollWithinPane(el: HTMLElement | null) {
  const pane = el?.closest<HTMLElement>("[data-doc-scroll]");
  if (!el || !pane || pane.scrollHeight <= pane.clientHeight) return;
  const top = el.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
  pane.scrollTo({ top: top - pane.clientHeight / 2, behavior: "smooth" });
}

function Segments({ segments, focusClaim }: { segments: DocumentSegment[]; focusClaim: string | null }) {
  const lit = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    scrollWithinPane(lit.current);
  }, [focusClaim]);
  return (
    <div className="whitespace-pre-wrap text-[0.8125rem] leading-6 text-ink">
      {segments.map((segment, index) => {
        const focused = segment.claim_id !== null && segment.claim_id === focusClaim;
        if (!segment.claim_id) return <span key={index}>{segment.text}</span>;
        return (
          <span
            key={index}
            ref={focused ? lit : undefined}
            title={segment.edited ? "You edited this line" : undefined}
            className={`rounded-sm ${focused ? "bg-brand-soft ring-1 ring-brand-line" : ""} ${
              segment.edited ? "bg-confirmed-soft underline decoration-confirmed decoration-2 underline-offset-4" : ""
            }`}
          >
            {segment.text}
          </span>
        );
      })}
    </div>
  );
}

/** Whether the three panes sit side by side (each with its own scrollbar). */
function useWide(): boolean {
  const query = "(min-width: 1024px)";
  const [wide, setWide] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setWide(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, []);
  return wide;
}

function DocumentPane({ review, focus }: { review: ResumeReview; focus: ReviewIssue | null }) {
  const wide = useWide();
  const [view, setView] = useState<"edits" | "page">(() =>
    review.has_original && review.edited === 0 ? "page" : "edits",
  );
  // The first applied fix switches to the edited view: the page image is the
  // file as uploaded and no longer shows what the student just changed.
  const edited = review.edited;
  const seen = useRef(edited);
  useEffect(() => {
    if (edited > seen.current) setView("edits");
    seen.current = edited;
  }, [edited]);

  return (
    <aside className="panel flex flex-col overflow-hidden lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:self-start">
      <div className="flex items-center gap-1 border-b border-line px-3 py-2">
        <button
          type="button"
          aria-pressed={view === "edits"}
          onClick={() => setView("edits")}
          className={`rounded-md px-2.5 py-1 text-xs font-medium ${view === "edits" ? "bg-surface-sunken text-ink" : "text-ink-soft hover:text-ink"}`}
        >
          With your edits{review.edited > 0 && ` · ${review.edited}`}
        </button>
        {review.has_original && (
          <button
            type="button"
            aria-pressed={view === "page"}
            onClick={() => setView("page")}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${view === "page" ? "bg-surface-sunken text-ink" : "text-ink-soft hover:text-ink"}`}
          >
            Original page
          </button>
        )}
      </div>
      <div data-doc-scroll className="min-h-[24rem] flex-1 overflow-y-auto p-4">
        {view === "page" ? (
          <PdfHighlightViewer
            resumeId={review.resume_id}
            spans={focus?.spans ?? []}
            autoScroll={wide}
            fallback={<Segments segments={review.document} focusClaim={focus?.claim_id ?? null} />}
          />
        ) : (
          <Segments segments={review.document} focusClaim={focus?.claim_id ?? null} />
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
        <Btn size="sm" onClick={() => downloadText(review)}>
          Download edited text
        </Btn>
        <p className="min-w-0 flex-1 text-xs text-ink-faint">
          Your file isn't changed — copy the fixed lines into it. Contact details stay masked here.
        </p>
      </div>
    </aside>
  );
}

/* ── the page ──────────────────────────────────────────────────────────── */

export function ReviewPage() {
  const { resumeId = "" } = useParams<{ resumeId: string }>();
  const resume = useResume(resumeId);
  const review = useReview(resumeId);
  const { ignored, toggle } = useIgnored(resumeId);
  const [chosen, setChosen] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [showIgnored, setShowIgnored] = useState(false);
  const [byKeyboard, setByKeyboard] = useState(false);

  const data = review.data;
  // The first check with something to fix, in the order a panel hits them.
  const firstOpen = useMemo(
    () => data?.checks.find((c) => c.issues.some((i) => !ignored.has(i.id)))?.id ?? data?.checks[0]?.id ?? "",
    [data, ignored],
  );
  const selectedId = chosen ?? firstOpen;
  const check = data?.checks.find((c) => c.id === selectedId) ?? null;
  const visible = useMemo(
    () => (check?.issues ?? []).filter((i) => showIgnored || !ignored.has(i.id)),
    [check, ignored, showIgnored],
  );
  const hiddenCount = (check?.issues ?? []).filter((i) => ignored.has(i.id)).length;
  const focus = visible.find((i) => i.id === focusId) ?? visible[0] ?? null;

  // J / K between cards — the focused one takes A, E and I.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target)) return;
      const key = event.key.toLowerCase();
      if (key !== "j" && key !== "k") return;
      event.preventDefault();
      const at = Math.max(0, visible.findIndex((i) => i.id === focus?.id));
      const next = visible[Math.min(visible.length - 1, Math.max(0, at + (key === "j" ? 1 : -1)))];
      if (next) {
        setByKeyboard(true);
        setFocusId(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus?.id, visible]);

  if (review.isLoading || resume.isLoading) {
    return (
      <div className="mx-auto w-full max-w-6xl px-5 py-8">
        <SkeletonRows rows={8} />
      </div>
    );
  }
  if (review.isError || !data) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8">
        <Empty title="This review couldn't be loaded">
          {(review.error as Error | null)?.message ?? "Try again in a moment."}
        </Empty>
      </div>
    );
  }

  const openCount = data.checks.reduce((n, c) => n + c.issues.filter((i) => !ignored.has(i.id)).length, 0);

  return (
    <div className="mx-auto grid w-full max-w-[96rem] gap-6 px-4 py-6 md:px-6 lg:grid-cols-[14rem_minmax(0,1fr)_minmax(0,26rem)] 2xl:grid-cols-[15rem_minmax(0,1fr)_minmax(0,32rem)]">
      {/* The three views of this resume come first, on every width. */}
      <div className="lg:col-span-3">
        <ResumeTabs resumeId={resumeId} active="review" />
      </div>
      <Rail resumeId={resumeId} review={data} ignored={ignored} selected={selectedId} onSelect={(id) => {
        setChosen(id);
        setFocusId(null);
      }} />

      <main className="min-w-0">
        <header>
          <h1 className="text-title font-semibold tracking-tight text-ink">
            {openCount === 0 ? "Nothing left to fix" : `${openCount} thing${openCount === 1 ? "" : "s"} to fix`}
          </h1>
          <p className="mt-1.5 text-sm text-ink-soft">
            {data.edited > 0 && `${data.edited} line${data.edited === 1 ? "" : "s"} edited so far · `}
            Every check is about the words on the page, never about you.
          </p>
          {resume.data && !resume.data.confirmed && (
            <p className="mt-3 rounded-lg border border-reported-line bg-reported-soft px-3 py-2 text-sm text-ink">
              We haven't confirmed what we read yet.{" "}
              <Link to={`/resumes/${resumeId}`} className="font-medium underline underline-offset-2">
                Check the read-back first
              </Link>{" "}
              — a mis-read heading changes what these checks see.
            </p>
          )}
        </header>

        {check && (
          <section className="mt-7" aria-labelledby="check-title">
            <p className="text-xs font-medium text-ink-faint">{GROUP_LABEL[check.group]}</p>
            <h2 id="check-title" className="mt-0.5 text-lg font-semibold text-ink">
              {check.title}
            </h2>
            <p className="mt-1 text-sm text-ink-soft">{check.looks_for}</p>

            <div className="mt-5 space-y-4">
              {visible.length === 0 ? (
                <Panel className="px-5 py-6">
                  <p className="flex items-center gap-2 text-sm font-medium text-ink">
                    <span className="text-confirmed">✓</span> Nothing to fix here.
                  </p>
                  <p className="mt-1 text-sm text-ink-soft">
                    Checked {check.looked_at} {check.looked_at === 1 ? "item" : "items"}.
                  </p>
                </Panel>
              ) : (
                visible.map((issue, index) => (
                  <IssueCard
                    key={issue.id}
                    resumeId={resumeId}
                    issue={issue}
                    position={index + 1}
                    of={visible.length}
                    focused={focus?.id === issue.id}
                    follow={byKeyboard}
                    ignored={ignored.has(issue.id)}
                    onFocus={() => setFocusId(issue.id)}
                    onIgnore={() => toggle(issue.id)}
                  />
                ))
              )}
            </div>

            {hiddenCount > 0 && (
              <button
                type="button"
                onClick={() => setShowIgnored((on) => !on)}
                className="mt-4 text-sm font-medium text-ink-soft hover:text-ink"
              >
                {showIgnored ? "Hide ignored" : `Show ${hiddenCount} ignored`}
              </button>
            )}
            <p className="mt-6 hidden text-xs text-ink-faint lg:block">
              <span className="kbd">J</span> <span className="kbd">K</span> move between cards ·{" "}
              <span className="kbd">A</span> apply · <span className="kbd">E</span> edit ·{" "}
              <span className="kbd">I</span> ignore
            </p>
          </section>
        )}
      </main>

      <DocumentPane review={data} focus={focus} />
    </div>
  );
}

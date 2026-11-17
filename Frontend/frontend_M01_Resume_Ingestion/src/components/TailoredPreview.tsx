/**
 * The PDF of a tailored copy, live (2026-11-17).
 *
 * Not a picture of the document: each page is rasterised on the server from
 * the very file the download is, at the copy's current revision, so an
 * accepted change appears here the moment it is saved and the download can
 * never disagree with it. The contact block is painted out of every image
 * (FR-1.17) and printed only in the student's own download.
 *
 * The server also says where every block landed (`/layout`): a rectangle per
 * printed line. That is what lets a claim be traced onto the page — the line
 * is boxed, the page scrolls to it, a note sits beside it — and what lets a
 * click on the page find the line in the editor.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@ai/core";

import { useTailoredLayout, useTailoredPage } from "../api";
import type { PageBox, TailoredLayout, TailoredResume } from "../types";

/** What to show on the page: one block, optionally one range of its text. */
export interface PreviewFocus {
  blockId: string;
  start?: number;
  end?: number;
  /** Changes on every request, so asking for the same line twice still scrolls. */
  nonce: number;
}

const ZOOMS = [0.6, 0.75, 0.9, 1, 1.15, 1.3, 1.5, 1.75, 2];

/** The PNG resolution to ask for: enough for the screen, from a few sizes. */
function resolution(scale: number): number {
  const wanted = scale * (typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1);
  return [1, 1.5, 2, 3, 4].find((z) => z >= wanted) ?? 4;
}

function Page({
  copy,
  page,
  width,
  height,
  scale,
  pngZoom,
  boxes,
  focus,
  hoverId,
  popup,
  onPick,
}: {
  copy: TailoredResume;
  page: number;
  width: number;
  height: number;
  scale: number;
  pngZoom: number;
  boxes: Record<string, PageBox[]>;
  focus: PreviewFocus | null;
  hoverId?: string | null;
  popup?: React.ReactNode;
  onPick?: (blockId: string) => void;
}) {
  const image = useTailoredPage(copy.resume_id, copy.id, page, copy.revision, pngZoom, copy.photo?.digest);
  const pct = (box: PageBox) => ({
    left: `${(box.rect[0] / width) * 100}%`,
    top: `${(box.rect[1] / height) * 100}%`,
    width: `${((box.rect[2] - box.rect[0]) / width) * 100}%`,
    height: `${((box.rect[3] - box.rect[1]) / height) * 100}%`,
  });

  const focusBoxes = focus ? (boxes[focus.blockId] ?? []).filter((b) => b.page === page) : [];
  const hoverBoxes = hoverId && hoverId !== focus?.blockId ? (boxes[hoverId] ?? []).filter((b) => b.page === page) : [];
  const hitsRange = (box: PageBox) =>
    focus?.start === undefined || focus.end === undefined || (box.start < focus.end && box.end > focus.start);
  const anchor = focusBoxes.filter(hitsRange).at(-1) ?? focusBoxes.at(-1);

  return (
    <div
      data-page={page}
      className="relative mx-auto bg-white shadow-[0_1px_3px_oklch(0_0_0/0.12),0_8px_24px_-12px_oklch(0_0_0/0.25)]"
      style={{ width: width * scale, height: height * scale }}
    >
      {image.data ? (
        <img src={image.data} alt={`Page ${page} of your tailored resume`} className="absolute inset-0 size-full select-none" draggable={false} />
      ) : (
        <div className="skeleton absolute inset-0" aria-hidden />
      )}
      {image.isError && (
        <p className="absolute inset-x-4 top-4 rounded-md bg-contested-soft px-3 py-2 text-xs text-ink">
          {(image.error as Error).message}
        </p>
      )}

      {/* Every printed line is a target: a click finds it in the editor. */}
      {onPick &&
        Object.entries(boxes).flatMap(([blockId, list]) =>
          list
            .filter((box) => box.page === page)
            .map((box, index) => (
              <button
                key={`${blockId}-${index}`}
                type="button"
                tabIndex={-1}
                aria-hidden
                onClick={() => onPick(blockId)}
                className="absolute cursor-pointer rounded-[2px] hover:bg-brand/8"
                style={pct(box)}
              />
            )),
        )}

      {hoverBoxes.map((box, index) => (
        <span key={`h${index}`} aria-hidden className="pointer-events-none absolute rounded-[2px] bg-brand/10" style={pct(box)} />
      ))}
      {focusBoxes.map((box, index) => (
        <span
          key={`f${index}-${focus?.nonce}`}
          aria-hidden
          className={`pointer-events-none absolute rounded-[3px] ${
            hitsRange(box)
              ? "bg-reported/25 ring-2 ring-reported motion-safe:animate-[pulse_1.2s_ease-out_1]"
              : "bg-reported/10"
          }`}
          style={pct(box)}
        />
      ))}
      {popup && anchor && (
        <div
          role="dialog"
          aria-label="What this line answers"
          className="absolute z-10 w-[min(26rem,92%)] -translate-x-1/2"
          style={{
            left: `${Math.min(Math.max(((anchor.rect[0] + anchor.rect[2]) / 2 / width) * 100, 30), 70)}%`,
            top: `calc(${(anchor.rect[3] / height) * 100}% + 8px)`,
          }}
        >
          {popup}
        </div>
      )}
    </div>
  );
}

export function TailoredPreview({
  copy,
  focus = null,
  popup,
  hoverId,
  onPick,
  onBack,
  toolbar,
}: {
  copy: TailoredResume;
  focus?: PreviewFocus | null;
  /** Shown beside the focused line — what it answers, where, and why. */
  popup?: React.ReactNode;
  /** Lightly boxed: the line the editor's pointer is over. */
  hoverId?: string | null;
  onPick?: (blockId: string) => void;
  /** Called when "Back" returns the page to where it was before a trace. */
  onBack?: () => void;
  /** Anything the host wants in the header (a download button). */
  toolbar?: React.ReactNode;
}) {
  const layout = useTailoredLayout(copy.resume_id, copy.id, copy.revision);
  const scroller = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [current, setCurrent] = useState(1);
  const [back, setBack] = useState<number[]>([]);

  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    setWidth(el.clientWidth);
    return () => observer.disconnect();
  }, []);

  const data: TailoredLayout | undefined = layout.data;
  const pages = data?.pages ?? [];
  const first = pages[0];
  const fit = first && width ? Math.max(0.2, (width - 32) / first.width) : 1;
  const scale = fit * zoom;
  const pngZoom = resolution(scale);

  const scrollToPage = useCallback((page: number) => {
    const el = scroller.current?.querySelector<HTMLElement>(`[data-page="${page}"]`);
    if (el && scroller.current) scroller.current.scrollTo({ top: el.offsetTop - 12, behavior: "smooth" });
  }, []);

  // A trace: remember where we were, then bring the line to a third of the way
  // down the pane, so the note under it has room.
  const lastNonce = useRef<number | null>(null);
  useEffect(() => {
    if (!focus || !data || !scroller.current || focus.nonce === lastNonce.current) return;
    const boxes = data.boxes[focus.blockId];
    if (!boxes?.length) return;
    lastNonce.current = focus.nonce;
    const box =
      boxes.find((b) => focus.start === undefined || (b.start < (focus.end ?? b.end) && b.end > focus.start)) ?? boxes[0];
    const pageEl = scroller.current.querySelector<HTMLElement>(`[data-page="${box.page}"]`);
    if (!pageEl) return;
    const pane = scroller.current;
    setBack((stack) => [...stack.slice(-9), pane.scrollTop]);
    const target = pageEl.offsetTop + box.rect[1] * scale - pane.clientHeight / 3;
    pane.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
  }, [focus, data, scale]);

  const onScroll = () => {
    const pane = scroller.current;
    if (!pane) return;
    const middle = pane.scrollTop + pane.clientHeight / 2;
    let seen = 1;
    pane.querySelectorAll<HTMLElement>("[data-page]").forEach((el) => {
      if (el.offsetTop <= middle) seen = Number(el.dataset.page);
    });
    setCurrent(seen);
  };

  const goBack = () => {
    const pane = scroller.current;
    const top = back.at(-1);
    if (!pane || top === undefined) return;
    setBack((stack) => stack.slice(0, -1));
    pane.scrollTo({ top, behavior: "smooth" });
    onBack?.();
  };

  const zoomIndex = useMemo(() => ZOOMS.indexOf(zoom), [zoom]);
  const updating = layout.isFetching || layout.isPlaceholderData;

  return (
    <section aria-label="PDF preview" className="panel flex min-h-0 flex-col overflow-hidden bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <p className="text-sm font-semibold text-ink">PDF</p>
        {updating && <span className="text-xs text-ink-faint">updating…</span>}
        {back.length > 0 && (
          <button
            type="button"
            onClick={goBack}
            className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-0.5 text-xs font-medium text-ink hover:border-line-strong"
          >
            <Icon name="arrowLeft" size={12} /> Back to where you were
          </button>
        )}
        <div className="ml-auto flex items-center gap-1 text-xs">
          <button
            type="button"
            aria-label="Previous page"
            disabled={current <= 1}
            onClick={() => scrollToPage(current - 1)}
            className="grid size-6 place-items-center rounded-md text-ink-soft hover:bg-surface-sunken disabled:opacity-40"
          >
            <Icon name="chevronUp" size={14} />
          </button>
          <span className="min-w-[4.5rem] text-center text-ink-soft" data-numeric>
            {pages.length ? `Page ${current} of ${pages.length}` : "—"}
          </span>
          <button
            type="button"
            aria-label="Next page"
            disabled={current >= pages.length}
            onClick={() => scrollToPage(current + 1)}
            className="grid size-6 place-items-center rounded-md text-ink-soft hover:bg-surface-sunken disabled:opacity-40"
          >
            <Icon name="chevronDown" size={14} />
          </button>
          <span className="mx-1 h-4 w-px bg-line" aria-hidden />
          <button
            type="button"
            aria-label="Zoom out"
            disabled={zoomIndex <= 0}
            onClick={() => setZoom(ZOOMS[Math.max(0, zoomIndex - 1)])}
            className="grid size-6 place-items-center rounded-md text-ink-soft hover:bg-surface-sunken disabled:opacity-40"
          >
            <Icon name="minus" size={14} />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            title="Fit to width"
            className="min-w-[3rem] rounded-md px-1 py-0.5 text-ink-soft hover:bg-surface-sunken"
            data-numeric
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            type="button"
            aria-label="Zoom in"
            disabled={zoomIndex >= ZOOMS.length - 1}
            onClick={() => setZoom(ZOOMS[Math.min(ZOOMS.length - 1, zoomIndex + 1)])}
            className="grid size-6 place-items-center rounded-md text-ink-soft hover:bg-surface-sunken disabled:opacity-40"
          >
            <Icon name="plus" size={14} />
          </button>
          {toolbar}
        </div>
      </div>

      <div
        ref={scroller}
        onScroll={onScroll}
        data-preview-scroll
        className="relative min-h-[24rem] flex-1 overflow-auto bg-surface-sunken px-4 py-4"
      >
        {layout.isLoading && (
          <div className="skeleton mx-auto aspect-[1/1.414] w-full max-w-[40rem] rounded" aria-label="Drawing your PDF" />
        )}
        {layout.isError && (
          <p className="rounded-md bg-contested-soft px-3 py-2 text-sm text-ink">
            The PDF could not be drawn: {(layout.error as Error).message}
          </p>
        )}
        {data && (
          <div className="space-y-4">
            {pages.map((page) => (
              <Page
                key={page.page}
                copy={copy}
                page={page.page}
                width={page.width}
                height={page.height}
                scale={scale}
                pngZoom={pngZoom}
                boxes={data.boxes}
                focus={focus}
                hoverId={hoverId}
                popup={focus && data.boxes[focus.blockId]?.some((b) => b.page === page.page) ? popup : undefined}
                onPick={onPick}
              />
            ))}
          </div>
        )}
      </div>
      <p className="border-t border-line px-3 py-1.5 text-[0.6875rem] text-ink-faint">
        The real file at this version. Contact details are masked on screen and printed in your download.
        {copy.style.source === "original" && " Page size, margins and type size follow your original."}
      </p>
    </section>
  );
}

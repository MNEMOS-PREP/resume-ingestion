/**
 * A question that has to be answered before something is removed (2026-10-04).
 *
 * The native `<dialog>`, opened with `showModal()`: it traps focus, closes on
 * Escape, puts everything behind it out of reach of a screen reader, and sits
 * above the shell without a z-index war. Cancel takes focus first, so Enter on
 * an accidental open keeps things rather than removing them.
 */
import { useEffect, useId, useRef, type ReactNode } from "react";

import { Btn } from "../ui/primitives";

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  busyLabel,
  busy = false,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busyLabel: string;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(event) => {
        // Escape while it is working would leave the request running unseen.
        if (busy) event.preventDefault();
      }}
      onClick={(event) => {
        // A click on the backdrop (the dialog element itself, outside the box).
        if (event.target === ref.current && !busy) onClose();
      }}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 text-ink shadow-raised backdrop:bg-black/40"
    >
      <div className="px-5 pt-5">
        <h2 id={titleId} className="text-lg font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <div className="mt-2 space-y-3 text-sm leading-relaxed text-ink-soft">{children}</div>
        {error && (
          <p role="alert" className="mt-3 text-sm text-contested">
            {error}
          </p>
        )}
      </div>
      <div className="mt-5 flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">
        <Btn variant="ghost" onClick={onClose} disabled={busy} autoFocus>
          Cancel
        </Btn>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className="inline-flex items-center justify-center rounded-md bg-contested px-3.5 py-1.5 text-sm font-medium text-surface transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? busyLabel : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

/**
 * "Pick from your library" inside the line editor (2026-10-04).
 *
 * Editing a line usually means writing something the student has already
 * written — on last term's resume, or a better wording they settled on. This
 * puts every line they have had one search away: picking one puts it in the
 * editor, where it is still theirs to change before it is saved.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useLibrary } from "../api";
import type { LibraryKind } from "../types";
import { KIND_LABEL } from "./library";

/** Kinds a resume line can be replaced with. Skills and degrees are not lines. */
const LINE_KINDS: LibraryKind[] = ["experience", "project", "achievement", "certification"];

export function LibraryPicker({
  candidateId,
  prefer,
  exclude,
  onPick,
  onClose,
}: {
  candidateId: string;
  /** Shown first: the kind of the line being edited. */
  prefer?: LibraryKind;
  /** The line as it stands — picking it again would change nothing. */
  exclude?: string;
  onPick: (text: string) => void;
  onClose: () => void;
}) {
  const library = useLibrary(candidateId);
  const [query, setQuery] = useState("");

  const items = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const rank = (kind: LibraryKind) => (kind === prefer ? 0 : 1 + LINE_KINDS.indexOf(kind));
    return (library.data?.items ?? [])
      .filter((item) => LINE_KINDS.includes(item.kind) && item.text !== exclude)
      .filter((item) => {
        const hay = `${item.text} ${item.context}`.toLowerCase();
        return words.every((word) => hay.includes(word));
      })
      .sort((a, b) => rank(a.kind) - rank(b.kind));
  }, [exclude, library.data, prefer, query]);

  return (
    <div className="mt-3 rounded-lg border border-line bg-surface-sunken p-3">
      <div className="flex items-center gap-2">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.stopPropagation();
              onClose();
            }
          }}
          placeholder="Search your library"
          aria-label="Search your library"
          autoFocus
          className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-brand"
        />
        <button type="button" onClick={onClose} className="text-xs font-medium text-ink-soft hover:text-ink">
          Close
        </button>
      </div>

      {library.isLoading ? (
        <p className="mt-3 text-sm text-ink-soft">Opening your library…</p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-sm text-ink-soft">
          {query
            ? "Nothing in your library matches that."
            : "Nothing here yet — your library fills as you upload resumes."}
        </p>
      ) : (
        <ul className="mt-2 max-h-72 space-y-1 overflow-y-auto" aria-label="Lines in your library">
          {items.slice(0, 60).map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => onPick(item.text)}
                className="w-full rounded-md px-2.5 py-2 text-left hover:bg-surface"
              >
                <span className="block text-sm leading-relaxed text-ink">{item.text}</span>
                <span className="mt-0.5 block truncate text-xs text-ink-faint">
                  {KIND_LABEL[item.kind]}
                  {item.context && ` · ${item.context}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-ink-faint">
        Picking one puts it in the editor — change it before you save.{" "}
        <Link to="/resume/library" className="font-medium text-ink-soft underline underline-offset-2">
          Open your library
        </Link>
      </p>
    </div>
  );
}

/**
 * The app shell: a thin top bar and a reading-width content area.
 *
 * The candidate control lives here because it changes what every screen shows.
 * There is no auth yet, and both the ingest and the "already ingested" list are
 * scoped to a candidate — putting that in one screen's header is how it ends up
 * set differently depending on which page you landed on.
 */

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { DependencyAlert } from "@ai/core";

import { useDeps, useHealth } from "../api";
import { setCandidateId } from "../components/candidate";
import { useCandidateId } from "../components/candidate-hook";
import { Pill } from "./primitives";

const NAV = [
  { to: "/", label: "Paste a resume" },
  { to: "/deps", label: "Dependencies" },
];

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("m01.theme") as "light" | "dark") || "light",
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("m01.theme", theme);
  }, [theme]);

  return (
    <button
      type="button"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="rounded-md px-2 py-1 text-ink-soft transition-colors hover:bg-surface-sunken hover:text-ink"
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
    >
      <span aria-hidden className="text-sm">
        {theme === "dark" ? "☀" : "☾"}
      </span>
    </button>
  );
}

/**
 * Whose resume this is.
 *
 * Visible rather than hidden in a constant: an empty "already ingested" list is
 * the correct answer for a candidate nothing has been stored against, and a
 * developer staring at that needs to know whether they are looking at an empty
 * database or the wrong candidate. Those are different bugs.
 */
function CandidateControl() {
  const candidateId = useCandidateId();
  const [draft, setDraft] = useState(candidateId);
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Whose resume this is. No auth yet."
        className="provenance rounded border border-line px-1.5 py-0.5 hover:border-line-strong hover:text-ink-soft"
      >
        candidate {candidateId.slice(0, 8)}
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setCandidateId(draft);
        setOpen(false);
      }}
      className="flex items-center gap-1"
    >
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        aria-label="Candidate id"
        className="w-64 rounded border border-line bg-surface px-2 py-0.5 font-mono text-xs text-ink outline-none focus:border-brand-line"
      />
      <button type="submit" className="text-xs font-medium text-brand hover:text-brand-hover">
        set
      </button>
    </form>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const health = useHealth();
  const deps = useDeps();

  const m04Down = deps.data?.some((d) => d.module_id === "M04" && !d.available);

  /* The banner needs DegradedFeature[], and /v1/deps returns statuses - so it
     is derived here from the upstreams that have a named consequence. */
  const degraded = m04Down
    ? deps.data
        ?.filter((d) => !d.available)
        .map((d) => ({
          feature: "Mapping your skills onto the ontology",
          needs_module: d.module_id,
          needs_module_name: d.name,
          explanation: d.on_missing,
        }))
    : [];

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-5 py-2.5">
          <Link to="/" className="flex shrink-0 items-center gap-2.5">
            <span
              aria-hidden
              className="grid h-6.5 w-6.5 place-items-center rounded-md bg-brand text-xs font-bold text-white"
            >
              ai
            </span>
            <span className="text-sm font-semibold text-ink">Resume Ingestion</span>
          </Link>

          <nav aria-label="Main" className="flex flex-wrap items-center gap-0.5">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  [
                    "rounded-md px-2.5 py-1 text-sm transition-colors",
                    isActive
                      ? "bg-surface-sunken font-medium text-ink"
                      : "text-ink-soft hover:bg-surface-sunken hover:text-ink",
                  ].join(" ")
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {m04Down && (
              <Pill
                tone="reported"
                title="M04 is unreachable. The scan runs on a five-concept offline lexicon and every id it produces is marked as a guess."
              >
                offline lexicon
              </Pill>
            )}
            {health.data && <span className="provenance hidden lg:inline">M01 · :8101</span>}
            <CandidateControl />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-5 py-8 md:px-8 md:py-10">
        <div className="mb-8 empty:mb-0">
          <DependencyAlert degraded={degraded} />
        </div>
        {children}
      </main>

      <footer className="border-t border-line px-5 py-5 md:px-8">
        <p className="provenance mx-auto max-w-5xl">
          M01 · Resume Ingestion &amp; Claim Extraction — every concept id here says whether the
          ontology confirmed it, and nothing you wrote is dropped for being unmappable.
        </p>
      </footer>
    </div>
  );
}

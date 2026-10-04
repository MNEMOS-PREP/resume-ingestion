/**
 * The app shell — two layouts, chosen by route.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2.3, §8.3, §8.4
 *
 * ── Why there are two ───────────────────────────────────────────────────────
 *
 * §2.3 draws M01 as five screens, and four of them genuinely are screens:
 * upload, the narrated parse, the confirmation pass, and the no-resume path
 * each ask the student for exactly one thing and then get out of the way. They
 * want a reading column and nothing else on the page competing with it.
 *
 * The Claim Map is not a screen. It is a place a student *works*, moving
 * between a claim, the questions it invites, and the line in their own document
 * it was read from. §8.3 makes that last link the module's trust proposition:
 * *"Click a claim → the original scrolls and highlights that exact bullet …
 * the student sees we read THEIR document, not a generic template."*  A
 * document panel that is 22rem wide and below the fold cannot carry that — the
 * highlight lands somewhere the student is not looking, and the one feature
 * that proves we read their resume is the one they never see fire.
 *
 * So that route gets the whole viewport, three panes, each scrolling on its
 * own.
 *
 * ── Why the route decides, and not a prop ───────────────────────────────────
 *
 * The shell wraps `<Routes>`, so the page inside cannot tell it anything
 * without a context and an effect — and an effect renders the reading layout
 * for one frame before swapping. That is a visible jump, on the module's most
 * important screen, every time it loads. Matching the path is deterministic and
 * happens on the first render.
 *
 * ── The candidate control ───────────────────────────────────────────────────
 *
 * Lives here because it changes what every screen shows. There is no auth yet
 * (PLATFORM_TODO item 1), and both the ingest and the "already read" list are
 * scoped to a candidate — putting that in one screen's header is how it ends up
 * set differently depending on which page you landed on.
 */

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { DependencyAlert } from "@ai/core";

import { useDeps, useHealth } from "../api";
import { setCandidateId } from "../components/candidate";
import { useCandidateId } from "../components/candidate-hook";
import { Pill } from "./primitives";

const NAV = [
  { to: "/", label: "Paste a resume" },
  // AC-1.7 is a release gate, and a gate you have to curl for is one that gets
  // checked by whoever remembers to.
  { to: "/quality", label: "Parser quality" },
  { to: "/deps", label: "Dependencies" },
];

/**
 * The one route that owns the viewport.
 *
 * Deliberately exact: `/resumes/:id/audit`, `/diff` and `/privacy` are reading
 * screens and keep the reading column. Only the Claim Map itself is a
 * workspace.
 */
const WORKSPACE_ROUTE = /^\/resumes\/[^/]+(\/review)?\/?$/;

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
 * Visible rather than hidden in a constant: an empty "already read" list is the
 * correct answer for a candidate nothing has been stored against, and a
 * developer staring at that needs to know whether they are looking at an empty
 * database or the wrong candidate. Those are different bugs.
 *
 * This is the dev shape of identity and it is refused outside
 * `AI_AUTH_MODE=dev`. The real session is `Platform_Shell`'s and is the open
 * half of PLATFORM_TODO item 1; when it lands this control is replaced by one
 * call in `candidate.ts` and this component is deleted.
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
        title="Whose resume this is. No auth yet — PLATFORM_TODO item 1."
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
  const { pathname } = useLocation();

  const workspace = WORKSPACE_ROUTE.test(pathname);
  const m04Down = deps.data?.some((d) => d.module_id === "M04" && !d.available);

  /* The banner needs DegradedFeature[], and /v1/deps returns statuses - so it
     is derived here from the upstreams that have a named consequence. */
  const degraded = m04Down
    ? (deps.data
        ?.filter((d) => !d.available)
        .map((d) => ({
          feature: "Mapping your skills onto the ontology",
          needs_module: d.module_id,
          needs_module_name: d.name,
          explanation: d.on_missing,
        })) ?? [])
    : [];

  return (
    <div
      className={[
        "flex flex-col bg-canvas",
        /* The workspace pins itself to the viewport so its three panes can each
           own a scrollbar. Only from `lg` up: on a phone there is no room for
           three columns, the panes stack, and pinning the height would trap the
           whole screen inside a pane-sized scroller (§8.4 - "the Claim Map
           becomes a vertical stack"). Every other route grows with its
           content. */
        workspace ? "min-h-screen lg:h-screen lg:overflow-hidden" : "min-h-screen",
      ].join(" ")}
    >
      {/* §8.4. Without it a keyboard user tabs the whole nav on every screen
          before reaching the thing they came for. */}
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="z-30 shrink-0 border-b border-line bg-canvas/90 backdrop-blur">
        <div
          className={[
            "flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-2.5",
            workspace ? "w-full" : "mx-auto max-w-5xl",
          ].join(" ")}
        >
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

      {workspace ? (
        <>
          {degraded.length > 0 && (
            <div className="shrink-0 border-b border-line px-5 py-3">
              <DependencyAlert degraded={degraded} />
            </div>
          )}
          {/* min-h-0 is load-bearing: without it a flex child refuses to shrink
              below its content height and the panes scroll the PAGE instead of
              themselves, which is the whole point of this layout. */}
          <main id="main" className="flex min-h-0 flex-1 flex-col">
            {children}
          </main>
        </>
      ) : (
        <>
          <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-5 py-8 md:px-8 md:py-10">
            <div className="mb-8 empty:mb-0">
              <DependencyAlert degraded={degraded} />
            </div>
            {children}
          </main>

          <footer className="border-t border-line px-5 py-5 md:px-8">
            <p className="provenance mx-auto max-w-5xl">
              M01 · Resume Ingestion &amp; Claim Extraction — every concept id here says whether
              the ontology confirmed it, and nothing you wrote is dropped for being unmappable.
            </p>
          </footer>
        </>
      )}
    </div>
  );
}
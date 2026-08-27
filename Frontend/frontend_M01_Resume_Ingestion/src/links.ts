/**
 * Where the other modules' screens live.
 *
 * Every module in this platform is a separate app on a separate port, which is
 * a deployment fact a student should never have to know. When M01 sends
 * somebody to M02 — "you have a resume, now hold it against a job" — it needs a
 * URL, and hard-coding `http://localhost:5202` into a component means the link
 * works on one machine and 404s everywhere else.
 *
 * So it comes from the environment with the dev port as the fallback. The
 * fallback is the DEV one on purpose: in production the variable is set, and a
 * missing variable there produces a visibly wrong link rather than a silently
 * plausible one that leads nowhere.
 */

/** M02 — JD Parser & Coverage Planner. Port 5202 per its own `module.json`. */
const M02_URL: string = import.meta.env.VITE_M02_URL ?? "http://localhost:5202";

/**
 * A link into M02 that carries who the student is.
 *
 * There is no shared session yet — each module reads a candidate id from its
 * own store, and M02's reads `?candidate=` from the URL before falling back to
 * its own `localStorage`. Passing it here is what makes the handoff continuous:
 * without it a student lands in M02 as whoever that browser last looked at,
 * which for a first visit is the seed candidate, and the analysis they came for
 * would be about somebody else entirely.
 *
 * Replaced wholesale when auth lands — one call site, deliberately.
 */
export function m02Link(path: string, candidateId: string): string {
  const url = new URL(path, M02_URL);
  url.searchParams.set("candidate", candidateId);
  return url.toString();
}

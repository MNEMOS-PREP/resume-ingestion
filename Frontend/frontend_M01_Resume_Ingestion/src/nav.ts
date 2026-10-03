/**
 * One entry in a module's own top bar.
 *
 * Declared here rather than imported. `@ai/core` exported a `NavItem` up to
 * v0.6.0 and dropped it in 0.7.0 — on the stated grounds that it "was imported
 * by nothing", which was not true: this file imported it, and M01 is pinned at
 * v0.6.0, so the break was real but invisible. It would have surfaced as a
 * type error the day somebody bumped the pin for an unrelated reason.
 *
 * Two words and a URL is not a platform contract in any case. The things
 * `@ai/core` owns are the ones nineteen repos must agree on — what a sourced
 * fact looks like, what "not yet tested" looks like. Nav is chrome, and 0.7.0's
 * own reasoning says so: *"a module owns its own chrome; this package owns the
 * vocabulary."*  Keeping it local means M01 can take a core upgrade without
 * this line being the thing that stops it.
 */
export interface NavItem {
  to: string;
  label: string;
}

/**
 * Nav for M01 running standalone. The platform shell supplies its own.
 *
 * `Parser quality` is here rather than behind a URL somebody has to know,
 * because AC-1.7 is a release gate and a gate nobody can see is one that stops
 * being checked. The per-resume audit and privacy screens are NOT here: they
 * belong to a resume, so they hang off one rather than off the top bar.
 */
export const M01_NAV: NavItem[] = [
  { to: "/resume", label: "Your resume" },
  { to: "/quality", label: "Parser quality" },
  { to: "/deps", label: "Dependencies" },
];

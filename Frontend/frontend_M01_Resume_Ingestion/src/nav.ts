import type { NavItem } from "@ai/core";

/**
 * Nav for M01 running standalone. The platform shell supplies its own.
 *
 * `Parser quality` is here rather than behind a URL somebody has to know,
 * because AC-1.7 is a release gate and a gate nobody can see is one that stops
 * being checked. The per-resume audit and privacy screens are NOT here: they
 * belong to a resume, so they hang off one rather than off the top bar.
 */
export const M01_NAV: NavItem[] = [
  { to: "/", label: "Your resume" },
  { to: "/quality", label: "Parser quality" },
  { to: "/deps", label: "Dependencies" },
];

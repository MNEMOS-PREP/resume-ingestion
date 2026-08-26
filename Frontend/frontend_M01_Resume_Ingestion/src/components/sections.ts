/**
 * What a section of a resume is called, in one place.
 *
 * Three screens name these now — the confirmation editor's `kind` picker, the
 * workspace rail's section filter, and the section headers in the claim list —
 * and the module's own rule about the risk bands applies here for the same
 * reason: a second copy is how one screen quietly says "Extras" while the one
 * beside it says "Extra-curricular", and the student concludes they are two
 * different things.
 *
 * The order is the order a resume is read in, not alphabetical. It is what the
 * rail lists and what the claim list groups by, so a student scanning it moves
 * down their own document rather than through a lookup table.
 */

import type { SectionKind } from "../types";

export const SECTION_KINDS: SectionKind[] = [
  "contact",
  "summary",
  "education",
  "experience",
  "projects",
  "skills",
  "achievements",
  "certifications",
  "publications",
  "extras",
  "unknown",
];

export const SECTION_LABEL: Record<SectionKind, string> = {
  contact: "Contact",
  summary: "Summary",
  education: "Education",
  experience: "Experience",
  projects: "Projects",
  skills: "Skills",
  achievements: "Achievements",
  certifications: "Certifications",
  publications: "Publications",
  extras: "Extra-curricular",
  unknown: "Not sure",
};

/**
 * What an interviewer does with this section, in one line.
 *
 * Shown as the section's subtitle when the claims are grouped by section, and
 * it is the difference between a heading and an explanation. A student looking
 * at "Projects · 6 claims · 3 risky" learns what to fix; a student who also
 * reads *"this is where most technical interviews actually start"* learns why
 * that is the section to fix first.
 *
 * Deliberately about the INTERVIEW rather than about resume formatting. M01 is
 * not an ATS checker (§2.3) and copy about what recruiters skim would make it
 * one by accident.
 */
export const SECTION_STAKE: Partial<Record<SectionKind, string>> = {
  summary:
    "Read first and quoted back at you. Anything you claim here you will be asked to justify twice.",
  experience:
    "The part they probe hardest, because someone else can be asked to confirm it.",
  projects:
    "Where most technical interviews actually start — you chose these, so you are expected to own every decision in them.",
  skills:
    "Treated as a menu of things you are volunteering to be tested on. A skill listed and never used in a project is the classic trap.",
  education: "Usually a formality, unless a grade or a gap invites a question.",
  achievements: "Fine as they are, until one has a number in it that nothing behind it explains.",
  certifications: "Rarely probed. When they are, it is 'what did you actually do with it?'",
  publications: "Expect the viva treatment: contribution, method, and what would falsify it.",
};

/**
 * The library's shapes, shared by its page, the delete dialog and the picker in
 * the review editor (2026-10-04).
 */
import type { LibraryItem, LibraryKind, Resume } from "../types";

/** How the library is shown: achievements and certifications together, because
 *  a resume as often heads them as one section as two, and which of the two a
 *  line is was a guess the student can change. */
export const LIBRARY_GROUPS = [
  { key: "experience", label: "Experience", kinds: ["experience"] },
  { key: "projects", label: "Projects", kinds: ["project"] },
  { key: "honours", label: "Achievements & certifications", kinds: ["achievement", "certification"] },
  { key: "education", label: "Education", kinds: ["education"] },
  { key: "skills", label: "Skills", kinds: ["skill"] },
] as const satisfies readonly { key: string; label: string; kinds: readonly LibraryKind[] }[];

export type LibraryGroupKey = (typeof LIBRARY_GROUPS)[number]["key"];

export const KIND_LABEL: Record<LibraryKind, string> = {
  experience: "Experience",
  project: "Project",
  achievement: "Achievement",
  certification: "Certification",
  education: "Education",
  skill: "Skill",
};

/** Kinds whose lines sit under a title (a project's name, a job's role). */
export const TITLED: ReadonlySet<LibraryKind> = new Set(["experience", "project"]);

export function inGroup(item: LibraryItem, key: LibraryGroupKey): boolean {
  const group = LIBRARY_GROUPS.find((g) => g.key === key);
  return Boolean(group && (group.kinds as readonly LibraryKind[]).includes(item.kind));
}

/** Lines under the same title, in the order they first appear; lines with no
 *  title last, since they are the ones a reader cannot place. */
export function byContext(items: LibraryItem[]): { context: string; items: LibraryItem[] }[] {
  const groups = new Map<string, LibraryItem[]>();
  for (const item of items) {
    const key = item.context.trim();
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return [...groups.entries()]
    .map(([context, grouped]) => ({ context, items: grouped }))
    .sort((a, b) => Number(!a.context) - Number(!b.context));
}

/** Where an item came from, in words: "On 2 resumes", "From a deleted resume". */
export function sourceNote(item: LibraryItem, resumes: Resume[] | undefined): string {
  const live = new Set((resumes ?? []).map((r) => r.id));
  const on = item.sources.filter((id) => live.has(id)).length;
  const gone = item.sources.length - on;
  const parts: string[] = [];
  if (item.sources.length === 0) parts.push("Added by you");
  if (on > 0) parts.push(`On ${on === 1 ? "1 resume" : `${on} resumes`}`);
  if (gone > 0)
    parts.push(`${on > 0 ? "and" : "From"} ${gone === 1 ? "a deleted resume" : `${gone} deleted resumes`}`);
  const note = parts.join(" ");
  return item.user_written && item.sources.length > 0 ? `${note} · reworded by you` : note;
}

/** What one resume put in the library, counted the way the delete dialog says it. */
export function keptFrom(items: LibraryItem[], resumeId: string) {
  const mine = items.filter((item) => item.sources.includes(resumeId));
  const count = (kinds: LibraryKind[]) => mine.filter((item) => kinds.includes(item.kind)).length;
  return {
    total: mine.length,
    lines: count(["experience", "project"]),
    honours: count(["achievement", "certification"]),
    education: count(["education"]),
    skills: count(["skill"]),
  };
}

/** A resume's sections in a fresher's order: education leads. */
const COMPOSE_ORDER: { kind: LibraryKind; heading: string }[] = [
  { kind: "education", heading: "EDUCATION" },
  { kind: "experience", heading: "EXPERIENCE" },
  { kind: "project", heading: "PROJECTS" },
  { kind: "achievement", heading: "ACHIEVEMENTS" },
  { kind: "certification", heading: "CERTIFICATIONS" },
  { kind: "skill", heading: "SKILLS" },
];

/**
 * Chosen items as resume text: headings M01's own parser knows, titles above
 * their bullets, skills as one list. No name or contact — the library never
 * holds them — so the student adds those at the top.
 */
export function compose(items: LibraryItem[]): string {
  const out: string[] = [];
  for (const { kind, heading } of COMPOSE_ORDER) {
    const chosen = items.filter((item) => item.kind === kind);
    if (chosen.length === 0) continue;
    out.push(heading);
    if (kind === "skill") {
      out.push(chosen.map((item) => item.text).join(", "));
    } else if (kind === "education") {
      for (const item of chosen) out.push(item.text);
    } else {
      for (const group of byContext(chosen)) {
        if (group.context) out.push(group.context);
        for (const item of group.items) out.push(`- ${item.text}`);
      }
    }
    out.push("");
  }
  return `${out.join("\n").trim()}\n`;
}

export function downloadAs(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

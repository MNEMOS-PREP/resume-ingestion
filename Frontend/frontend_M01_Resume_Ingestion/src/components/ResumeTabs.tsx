/**
 * The three ways to look at one resume, one click apart (2026-10-04).
 *
 * Review & fix is the line-by-line edit; What they'll ask is the Claim Map, the
 * questions each line invites; Check against a job is the posting match. They
 * were reachable only from links inside each other, so a student who opened
 * one did not know the other two existed.
 */
import { Link } from "react-router-dom";

const TABS = [
  { key: "review", label: "Review & fix", path: "/review" },
  { key: "ask", label: "What they'll ask", path: "" },
  { key: "job", label: "Job match", path: "/target" },
] as const;

export type ResumeTab = (typeof TABS)[number]["key"];

export function ResumeTabs({ resumeId, active }: { resumeId: string; active: ResumeTab }) {
  return (
    <nav aria-label="Ways to look at this resume" className="flex gap-1 overflow-x-auto border-b border-line [scrollbar-width:none]">
      {TABS.map((tab) => {
        const on = tab.key === active;
        return (
          <Link
            key={tab.key}
            to={`/resumes/${resumeId}${tab.path}`}
            aria-current={on ? "page" : undefined}
            className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium ${
              on ? "border-brand text-ink" : "border-transparent text-ink-soft hover:text-ink"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

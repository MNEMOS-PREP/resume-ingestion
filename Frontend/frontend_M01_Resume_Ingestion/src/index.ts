/**
 * M01 - Resume Ingestion & Claim Extraction · public surface.
 *
 * Anything not exported here is private to this module. `SkillSet` is exported
 * because M02 shows the same skills when weighting a JD requirement and M06
 * shows them when configuring an interview - and two copies of the component
 * that decides whether an unmapped skill is displayed at all is how "we never
 * silently drop what the student claimed" stops being true in one of them.
 */

export { m01Routes } from "./routes";
export { M01_NAV } from "./nav";
export { AppShell } from "./ui/AppShell";
export { SkillSet, ScanSourceNote } from "./components/SkillSet";
export { useCandidateResumes, useDeps, useIngestResume, useResume } from "./api";
export type { ConceptSource, Resume } from "./types";

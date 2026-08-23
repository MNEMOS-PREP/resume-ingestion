/**
 * M01 - Resume Ingestion & Claim Extraction · public surface.
 *
 * Anything not exported here is private to this module. `SkillSet` is exported
 * because M02 shows the same skills when weighting a JD requirement and M06
 * shows them when configuring an interview - and two copies of the component
 * that decides whether an unmapped skill is displayed at all is how "we never
 * silently drop what the student claimed" stops being true in one of them.
 *
 * `ClaimMap` and `ClaimCard` are exported for the same reason: M06 needs to
 * show which claim a round is about, and a second card is how the band stops
 * carrying its icon and its word on one of the two screens (§8.3).
 */

export { m01Routes } from "./routes";
export { M01_NAV } from "./nav";
export { AppShell } from "./ui/AppShell";
export { SkillSet, ScanSourceNote } from "./components/SkillSet";
export { ClaimMap, BandSummary } from "./components/ClaimMap";
export { ClaimCard } from "./components/ClaimCard";
export { BANDS, BAND_ORDER, BandChip } from "./components/bands";
export { RedFlagBanner } from "./components/RedFlagBanner";
export { SourceHighlight, RedactionNote } from "./components/SourceHighlight";
// Mounted by name in the platform shell, which owns "/" and cannot take a
// second index route. Standalone still routes to them through m01Routes.
export { IngestPage, SkippedPage } from "./components/IngestPage";
export { ResumePage } from "./components/ResumePage";
export { DiffPage } from "./components/DiffPage";
export {
  subscribeToProgress,
  useCandidateResumes,
  useCapabilities,
  useClaims,
  useConfirmResume,
  useDeps,
  useIngestResume,
  useRedFlags,
  useResume,
  useRewriteClaim,
  useDiff,
  useSkills,
  useUploadResume,
} from "./api";
export type {
  ClaimListing,
  ClaimProbe,
  ConceptSource,
  Resume,
  ResumeClaim,
  RedFlag,
  RiskBand,
  SkillMention,
  SourceSpan,
} from "./types";

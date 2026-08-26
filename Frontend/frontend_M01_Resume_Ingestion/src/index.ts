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
 *
 * ── The `*Panel` pairs ──────────────────────────────────────────────────────
 *
 * `SkillSet` / `SkillPanel` and `RedFlagBanner` / `RedFlagPanel` are the same
 * component twice: once taking props, once fetching. Other modules mount the
 * prop form with a resume they already hold; M01's own screens mount the
 * fetching form, so the server's ordering and its derived counts are what gets
 * rendered rather than a second opinion computed in the browser.
 */

export { m01Routes } from "./routes";
export { M01_NAV } from "./nav";
export type { NavItem } from "./nav";
export { AppShell } from "./ui/AppShell";
export { SkillSet, SkillPanel, ScanSourceNote } from "./components/SkillSet";
export { ClaimMap, ClaimList, BandSummary, FixFirstCard } from "./components/ClaimMap";
export { ClaimRail } from "./components/ClaimRail";
export type { GroupBy, Filter } from "./components/ClaimRail";
export { ResumeWorkspace } from "./components/ResumeWorkspace";
export { SECTION_KINDS, SECTION_LABEL, SECTION_STAKE } from "./components/sections";
export { ClaimCard } from "./components/ClaimCard";
export { BANDS, BAND_ORDER, BandChip } from "./components/bands";
export { RedFlagBanner, RedFlagPanel } from "./components/RedFlagBanner";
export { SourceHighlight, RedactionNote } from "./components/SourceHighlight";
export { ContactPanel } from "./components/ContactPanel";
export { DrillPanel } from "./components/DrillPanel";
export { DateEditor } from "./components/DateEditor";
// Mounted by name in the platform shell, which owns "/" and cannot take a
// second index route. Standalone still routes to them through m01Routes.
export { IngestPage, SkippedPage } from "./components/IngestPage";
export { ResumePage } from "./components/ResumePage";
export { DiffPage } from "./components/DiffPage";
export { AuditPage } from "./components/AuditPage";
export { PrivacyPage } from "./components/PrivacyPage";
export { QualityPage } from "./components/QualityPage";
export {
  subscribeToProgress,
  useCandidateResumes,
  useCapabilities,
  useClaims,
  useConfirmResume,
  useCorrection,
  useCorrections,
  useDeleteClaim,
  useDeleteResume,
  useStartDrill,
  useDeps,
  useDisclosure,
  useEditClaim,
  useEditDate,
  useEditSkill,
  useIngestResume,
  useQuality,
  useRedFlags,
  useResume,
  useResumeContact,
  useResumeEvents,
  useRevokeShare,
  useRewriteClaim,
  useShareResume,
  useCorrectSection,
  useDiff,
  useSkills,
  useUploadResume,
} from "./api";
export type {
  Capabilities,
  ClaimListing,
  ClaimProbe,
  ConceptSource,
  Correction,
  DisclosureLevel,
  DisclosureReport,
  DrillHandoff,
  QualityReport,
  Resume,
  ResumeClaim,
  ResumeContact,
  ResumeEventRow,
  RedFlag,
  RedFlagListing,
  RetentionPolicy,
  RiskBand,
  ShareGrant,
  SkillListing,
  SkillMention,
  SourceSpan,
} from "./types";

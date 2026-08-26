/**
 * M01 — Resume Ingestion & Claim Extraction · the shapes the backend sends.
 *
 * Hand-written against `router.py` rather than generated, and deliberately
 * narrow: there is no type here for a field the API does not return.
 *
 * ── The field that is NOT here ──────────────────────────────────────────────
 *
 * `raw_text`. It is on the table and it is not on `ResumeOut`, because the
 * contact block lives in its own row and the unredacted document never leaves
 * the module (FR-1.17). `redacted_text` is the copy a screen may show — same
 * length, character for character, so every `SourceSpan` offset points at the
 * same words in it. That equal-length property is what makes the highlight in
 * `SourceHighlight` possible at all.
 *
 * This file previously declared `raw_text`, which is what the read-back screen
 * rendered. When PII isolation landed the field stopped being sent and the
 * screen rendered `undefined` — a blank panel with no error, on the one screen
 * whose whole job is showing the student we read their document.
 */

import type { DependencyStatus } from "@ai/core";

/* ------------------------------------------------------------------ */
/*  Provenance                                                        */
/* ------------------------------------------------------------------ */

/** Where a concept_id came from. The whole reason the field exists. */
export type ConceptSource = "m04" | "offline_fallback";

/** Which ontology the resume was scanned against. */
export type ScannedAgainst = "m04" | "offline_lexicon";

/**
 * How a label became a concept_id (spec §6.4).
 *
 * `offline_alias` is M01's own five-entry fallback table with M04 down. It is
 * not `alias_exact` — nothing confirmed the concept exists — and it is not
 * `llm`, because no model ran.
 */
export type MappingMethod =
  | "alias_exact"
  | "alias_fuzzy"
  | "embedding"
  | "llm"
  | "user"
  | "offline_alias"
  | "unmapped";

/**
 * Where on the resume a skill was written.
 *
 * §6.4: a skill in the skills list is a claim of *familiarity*; the same skill
 * inside a project is a claim of *use*, and M05 asks much harder questions
 * about the latter.
 */
export type SkillContext = "skills_list" | "project_tech" | "experience_body" | "education";

/* ------------------------------------------------------------------ */
/*  The atom of traceability                                          */
/* ------------------------------------------------------------------ */

/** "Everything downstream cites one of these" (spec §5). */
export interface SourceSpan {
  artifact_id: string;
  page: number;
  start: number;
  end: number;
  /** Only for documents that had geometry. `null` for pasted text. */
  bbox: [number, number, number, number] | null;
  text: string;
}

export type SectionKind =
  | "contact"
  | "summary"
  | "education"
  | "experience"
  | "projects"
  | "skills"
  | "achievements"
  | "certifications"
  | "publications"
  | "extras"
  | "unknown";

export interface ResumeSection {
  id: string;
  kind: SectionKind;
  span: SourceSpan;
  confidence: number;
  user_corrected: boolean;
}

export type ClaimType =
  | "built"
  | "improved"
  | "led"
  | "researched"
  | "achieved"
  | "used"
  | "learned";

/** Red, amber, green — but never rendered as colour alone (§8.3). */
export type RiskBand = "strong" | "vague" | "risky";

export interface Quantifier {
  raw: string;
  value: number;
  unit: string | null;
  metric_hint: string | null;
  span: SourceSpan;
}

export interface ClaimProbe {
  id: string;
  claim_id: string;
  /** 0 what · 1 how · 2 why · 3 what-if. */
  depth: 0 | 1 | 2 | 3;
  question: string;
  /** The key points a good answer covers. */
  expects: string[];
  /** Shown to the student: why they would ask this. */
  rationale: string;
  generated_by: string;
}

export interface ResumeClaim {
  id: string;
  resume_id: string;
  section_id: string;
  span: SourceSpan;
  text: string;
  claim_type: ClaimType;
  subject_concepts: string[];
  quantifiers: Quantifier[];
  specificity: number;
  verifiability: number;
  ownership_clarity: number;
  recency: number;
  risk_score: number;
  risk_band: RiskBand;
  linked_repo_id: string | null;
  /** How visible this bullet is. Orders the map; never changes the band. */
  prominence: number;
  user_edited: boolean;
  probes: ClaimProbe[];
}

export type RedFlagKind =
  | "timeline_gap"
  | "chronology_conflict"
  | "claim_skill_mismatch"
  | "unverifiable_superlative"
  | "title_inflation"
  | "duplicate_project";

export interface RedFlag {
  kind: RedFlagKind;
  severity: "info" | "notable" | "serious";
  explanation: string;
  spans: SourceSpan[];
  suggested_answer: string | null;
}

export interface SkillMention {
  surface: string;
  concept_id: string | null;
  mapping_method: MappingMethod;
  mapping_confidence: number;
  span: SourceSpan;
  context: SkillContext;
  occurrences: number;
  user_added: boolean;
}

/* ------------------------------------------------------------------ */
/*  Entities                                                          */
/* ------------------------------------------------------------------ */

export interface DateRange {
  raw: string;
  start_year: number;
  end_year: number | null;
  ongoing: boolean;
  start: number;
  end: number;
}

export interface EducationEntry {
  institution: string | null;
  degree: string | null;
  grade: string | null;
  dates: DateRange | null;
  line: string;
  start: number;
  end: number;
}

export interface RoleEntry {
  title: string | null;
  organisation: string | null;
  dates: DateRange | null;
  line: string;
  start: number;
  end: number;
}

export interface Entities {
  name: string | null;
  education: EducationEntry[];
  roles: RoleEntry[];
  dates: DateRange[];
  institutions: string[];
}

/* ------------------------------------------------------------------ */
/*  The resume                                                        */
/* ------------------------------------------------------------------ */

/**
 * queued | parsing | needs_review | ready | failed.
 *
 * `needs_review` is the one that changes a screen: it means the parse is a
 * proposal we are not confident in, and the confirmation pass should ask the
 * student to check rather than to skim.
 */
export type ParseStatus = "queued" | "parsing" | "needs_review" | "ready" | "failed";

export interface Resume {
  id: string;
  candidate_id: string;
  /** Contact masked in place, same length as the original. */
  redacted_text: string;
  content_sha256: string;
  parsed_skills: string[];
  /** skill label -> concept_id. Only labels that resolved to something. */
  resolved_concepts: Record<string, string>;
  concept_source: Record<string, ConceptSource>;
  /** On the resume, mapped to no concept. Kept, never dropped. */
  unresolved_skills: string[];
  /** surface form -> the canonical spelling we recognised ("k8s" -> "Kubernetes"). */
  canonical_skills: Record<string, string>;
  skill_mentions: SkillMention[];
  scanned_against: ScannedAgainst;
  sections: ResumeSection[];
  claims: ResumeClaim[];
  red_flags: RedFlag[];
  entities: Entities;
  storage_uri: string;
  /** SHA-256 of the uploaded FILE. Empty for the paste path. */
  source_sha256: string;
  filename: string | null;
  mime: string;
  page_count: number;
  parse_status: ParseStatus;
  parse_error: string | null;
  parser_version: string;
  ocr_used: boolean;
  /** EC-1.6. Anything but "en" means every lexicon we matched against was the
   *  wrong one, which is why the read is thin. */
  language: string;
  language_confidence: number;
  columns: number;
  column_confidence: number;
  /** Student-facing sentences about how the read went. Usually empty. */
  parse_notes: string[];
  is_active: boolean;
  confirmed: boolean;
  parse_ms: number;
  created_at: string;
}

/* ------------------------------------------------------------------ */
/*  Derived views the server owns                                     */
/* ------------------------------------------------------------------ */

/**
 * `GET /v1/resumes/{id}/claims`.
 *
 * `fix_first` is computed by the server rather than by each client, so two
 * screens cannot disagree about which bullet the student should fix first.
 */
export interface ClaimListing {
  resume_id: string;
  claims: ResumeClaim[];
  counts: Record<RiskBand, number>;
  total: number;
  fix_first: ResumeClaim | null;
}

export interface RedFlagListing {
  resume_id: string;
  red_flags: RedFlag[];
  counts: Record<"serious" | "notable" | "info", number>;
}

export interface UnmappedEntry {
  surface: string;
  occurrences: number;
  contexts: SkillContext[];
}

export interface SkillListing {
  resume_id: string;
  scanned_against: ScannedAgainst;
  mentions: SkillMention[];
  mapped: number;
  unmapped: number;
  /** concept_id -> the strongest context it was claimed in. */
  claimed_use: Record<string, SkillContext>;
  unmapped_queue: UnmappedEntry[];
}

/* ------------------------------------------------------------------ */
/*  Rewrite (FR-1.19)                                                 */
/* ------------------------------------------------------------------ */

export interface RewriteSlot {
  slot: string;
  present: boolean;
  prompt: string;
  evidence: string | null;
}

export interface RewriteSuggestion {
  claim_id: string;
  original: string;
  /** A shape with the student's own facts left as bracketed blanks. */
  suggestion: string;
  slots: RewriteSlot[];
  first_fix: string;
  drop_words: string[];
  caveat: string;
}

/* ------------------------------------------------------------------ */
/*  Diff (FR-1.15)                                                    */
/* ------------------------------------------------------------------ */

export interface ClaimDiffEntry {
  text: string;
  risk_band: RiskBand;
}

export interface RebandedEntry {
  text: string;
  risk_band_before: RiskBand;
  risk_band_after: RiskBand;
}

export interface ResumeDiff {
  added: ClaimDiffEntry[];
  removed: ClaimDiffEntry[];
  changed: RebandedEntry[];
  summary: string;
  before: string;
  after: string;
  identical_content: boolean;
}

/* ------------------------------------------------------------------ */
/*  Meta                                                              */
/* ------------------------------------------------------------------ */

/**
 * `GET /v1/capabilities` — what this deployment can actually read.
 *
 * Asked before an upload control is rendered. A dropzone that accepts a PDF on
 * a server with no PDF library is a control that looks live and does nothing,
 * which §2.4 lists as a quit trigger.
 */
export interface Capabilities {
  accepts: Record<string, boolean>;
  ocr: boolean;
  max_bytes: number;
  max_pages: number;
  parser_version: string;
  always_available: string[];
}

/** One line of §2.3 Screen 2's narrated progress. */
export interface ProgressEvent {
  stage: string;
  status: string;
  detail: string;
  progress: number;
  parse_status?: ParseStatus;
}

/** The body of a 4xx from the upload endpoint. Always names a way forward. */
export interface IntakeErrorDetail {
  code: string;
  message: string;
  fallback: "text";
}

export interface Health {
  status: string;
  module: string;
}

/** `ai_core.modules_meta.ModuleStatus`, as served by GET /status. */
export interface ModuleStatus {
  id: string;
  name: string;
  slug: string;
  phase: string;
  owner: string;
  implemented: boolean;
  spec: string;
  reserved_port: number;
  detail: string;
}

export type Deps = DependencyStatus[];

export interface ResumeIngestIn {
  candidate_id: string;
  raw_text: string;
}

export interface CorrectionIn {
  target: "section" | "claim" | "skill";
  target_id: string;
  field: string;
  value: string | null;
}

/* ------------------------------------------------------------------ */
/*  Contact (FR-1.17)                                                 */
/* ------------------------------------------------------------------ */

/**
 * `GET /v1/resumes/{id}/contact` — the block that is redacted everywhere else.
 *
 * Its own route, its own tag on the server, and its own type here rather than
 * fields on `Resume`: "who saw the student's phone number" has to be
 * answerable from an access log, and that is only true while this is the one
 * request that releases it. A screen that wants a name must ask for it on
 * purpose.
 */
export interface ResumeContact {
  resume_id: string;
  candidate_id: string;
  emails: string[];
  phones: string[];
  links: string[];
  created_at: string;
}

/* ------------------------------------------------------------------ */
/*  The correction log (FR-1.12, AC-1.7)                              */
/* ------------------------------------------------------------------ */

/** One time the parser was overruled. Append-only — the disagreement is the
 *  interesting part, and AC-1.7 counts them. */
export interface Correction {
  id: string;
  resume_id: string;
  candidate_id: string;
  content_sha256: string;
  target: "section" | "claim" | "skill" | "entity";
  target_id: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

/* ------------------------------------------------------------------ */
/*  Events (FR-1.20)                                                  */
/* ------------------------------------------------------------------ */

/**
 * One `resume.*` stage boundary.
 *
 * `payload` is a whitelist on the server — counts, durations, ids and enum
 * values, never resume text and never a contact detail. Typed as a record of
 * numbers and strings for that reason: anything richer arriving here means the
 * whitelist grew something it should not have.
 */
export interface ResumeEventRow {
  id: string;
  name: string;
  resume_id: string | null;
  candidate_id: string | null;
  payload: Record<string, string | number | boolean>;
  at: string;
}

/* ------------------------------------------------------------------ */
/*  Retention and disclosure (§15 decisions 3 and 4)                  */
/* ------------------------------------------------------------------ */

/** The policy in force, reported rather than assumed — "how long do you keep
 *  my resume?" is a question a student is entitled to ask. */
export interface RetentionPolicy {
  retention_days: number;
  rationale: string;
  /** False while the ethics committee has not signed off. Shown, not hidden. */
  decided: boolean;
  deletable_on_request: boolean;
  expiry_is_a_tombstone: boolean;
  default_disclosure: DisclosureLevel;
}

export type DisclosureLevel = "aggregate_only" | "shared_by_student" | "self_access";

/** `GET /v1/resumes/{id}/disclosure?viewer=` — fails closed. */
export interface DisclosureReport {
  resume_id: string;
  viewer: string;
  disclosure: DisclosureLevel;
  may_see_individual_claims: boolean;
  retention: RetentionPolicy & {
    created_on: string;
    expires_on: string;
    expired: boolean;
  };
}

/** A grant is to somebody named, it expires, and revoking leaves a trace. */
export interface ShareGrant {
  id: string;
  resume_id: string;
  candidate_id: string;
  grantee: string;
  granted_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface ShareIn {
  grantee: string;
  /** Null keeps it open-ended. 90 days is the server's default. */
  days: number | null;
}

export interface RevokeResult {
  revoked: number;
  grantee: string;
}

/* ------------------------------------------------------------------ */
/*  Parser quality (AC-1.7, §13)                                      */
/* ------------------------------------------------------------------ */

/**
 * `GET /v1/quality`.
 *
 * §13's own threshold, evaluated rather than left to the reader:
 * `parser_needs_work` is the server's verdict on `edit_rate > 0.40`, so a
 * screen cannot disagree with the release checklist about whether the bar was
 * met.
 */
/**
 * AC-1.6, evaluated. §13: *"p95 end-to-end parse (2 pages, no OCR) ≤ 25 s"*.
 *
 * `excluded_ocr` is reported rather than hidden. The criterion's own words
 * exclude OCR reads, and §11 budgets OCR at 15 s of its own — but a p95 over a
 * corpus with an unstated number of resumes set aside is not a measurement
 * anybody can check.
 */
export interface ParseTiming {
  measured: number;
  excluded_ocr: number;
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
  target_ms: number;
  over_budget: boolean;
  ocr_p95_ms: number;
}

export interface QualityReport {
  resumes: number;
  confirmed: number;
  edit_rate: number;
  edit_rate_target: number;
  parser_needs_work: boolean;
  corrections: number;
  corrections_by_target: Record<string, number>;
  needs_review: number;
  ocr_used: number;
  two_column: number;
  /** FR-1.17 — false means the key is not set and contact rows are in clear. */
  pii_encrypted_at_rest: boolean;
  /** §6.1 asks for one. There is not one, and the honest gap is reported. */
  virus_scan: boolean;
  object_store: "s3" | "local";
  retention: RetentionPolicy;
  failed: number;
  failures_by_code: Record<string, number>;
  timing: ParseTiming;
}

/* ------------------------------------------------------------------ */
/*  The defend drill (§2.3 Screen 5, AC-1.8)                          */
/* ------------------------------------------------------------------ */

/**
 * `POST /v1/resumes/{id}/claims/{cid}/drill`.
 *
 * Always answers. M06 owns the session and M06 is not built, so this carries
 * either the session it created or a stated reason there is none — never a
 * 502. `questions` is present either way: a student who cannot start a drill
 * can still read what they would be asked and answer it out loud, which is
 * most of the value and none of the infrastructure.
 */
export interface DrillHandoff {
  claim_id: string;
  questions: string[];
  available: boolean;
  session_id: string | null;
  session_url: string | null;
  needs_module: string | null;
  explanation: string | null;
}

/**
 * `GET /v1/resumes/{id}/pages` — one page of the original, in POINTS.
 *
 * `SourceSpan.bbox` is measured against these numbers, so a client drawing a
 * highlight over the rendered image scales by `renderedWidth / width` rather
 * than assuming the server's zoom.
 */
export interface ResumePageInfo {
  page: number;
  width: number;
  height: number;
}

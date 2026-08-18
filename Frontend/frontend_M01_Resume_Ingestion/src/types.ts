/**
 * M01 — Resume Ingestion & Claim Extraction · the shapes the backend sends.
 *
 * Hand-written against `router.py` rather than generated, and deliberately
 * narrow: there is no type here for a field the API does not return. The spec
 * (§5) defines `SourceSpan`, `ResumeSection`, `SkillMention`, `Quantifier`,
 * `ResumeClaim` and `ClaimProbe` — none of which exist yet — and declaring
 * them now would let a screen be written against a shape nothing serves.
 *
 * The absence of `SourceSpan` in particular is why this file is so short. The
 * spec calls it "the atom of traceability — everything downstream cites one of
 * these", and until it lands there is nothing to cite.
 */

import type { DependencyStatus } from "@ai/core";

/** Where a concept_id came from. The whole reason the field exists. */
export type ConceptSource = "m04" | "offline_fallback";

/** Which ontology the resume was scanned against. */
export type ScannedAgainst = "m04" | "offline_lexicon";

export interface Resume {
  id: string;
  candidate_id: string;
  raw_text: string;
  parsed_skills: string[];
  /** skill label -> concept_id. Only labels that resolved to something. */
  resolved_concepts: Record<string, string>;
  concept_source: Record<string, ConceptSource>;
  /** On the resume, mapped to no concept. Kept, never dropped. */
  unresolved_skills: string[];
  scanned_against: ScannedAgainst;
  created_at: string;
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

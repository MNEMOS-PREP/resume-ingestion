/**
 * M01 — Resume Ingestion & Claim Extraction · API client.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §7 (API surface)
 *
 * One hook per backend endpoint, and no hook without one. The spec's surface is
 * fourteen endpoints; four exist. There is no `useClaims`, no `useRedFlags` and
 * no `useConfirm` here, because writing them would let a screen be built on an
 * endpoint that does not answer — and the caller finds that out in the browser
 * rather than in a review.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@ai/core";
import type { Deps, Health, ModuleStatus, Resume, ResumeIngestIn } from "./types";

export const m01Keys = {
  health: ["m01", "health"] as const,
  status: ["m01", "status"] as const,
  deps: ["m01", "deps"] as const,
  resume: (resumeId: string) => ["m01", "resume", resumeId] as const,
  byCandidate: (candidateId: string) => ["m01", "resumes", candidateId] as const,
};

/* ------------------------------------------------------------------ */
/*  Meta                                                              */
/* ------------------------------------------------------------------ */

export function useHealth() {
  return useQuery({
    queryKey: m01Keys.health,
    queryFn: () => api.get<Health>("/health"),
    retry: false,
  });
}

/** What the platform registry says this module is — not what it says itself. */
export function useModuleStatus() {
  return useQuery({
    queryKey: m01Keys.status,
    queryFn: () => api.get<ModuleStatus>("/status"),
    retry: false,
  });
}

export function useDeps() {
  return useQuery({
    queryKey: m01Keys.deps,
    queryFn: () => api.get<Deps>("/v1/deps"),
    retry: false,
  });
}

/* ------------------------------------------------------------------ */
/*  Resumes                                                           */
/* ------------------------------------------------------------------ */

export function useIngestResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ResumeIngestIn) => api.post<Resume>("/v1/resumes/ingest", body),
    onSuccess: (resume) => {
      qc.setQueryData(m01Keys.resume(resume.id), resume);
      qc.invalidateQueries({ queryKey: m01Keys.byCandidate(resume.candidate_id) });
      // An ingest reads the ontology, so whether M04 answered is now known
      // more precisely than the last cached probe said.
      qc.invalidateQueries({ queryKey: m01Keys.deps });
    },
  });
}

export function useResume(resumeId: string | undefined) {
  return useQuery({
    queryKey: m01Keys.resume(resumeId ?? ""),
    enabled: Boolean(resumeId),
    retry: false,
    queryFn: () => api.get<Resume>(`/v1/resumes/${resumeId}`),
  });
}

export function useCandidateResumes(candidateId: string | undefined) {
  return useQuery({
    queryKey: m01Keys.byCandidate(candidateId ?? ""),
    enabled: Boolean(candidateId),
    queryFn: () => api.get<Resume[]>(`/v1/resumes/candidate/${candidateId}`),
  });
}

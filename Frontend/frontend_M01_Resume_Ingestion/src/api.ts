/**
 * M01 — Resume Ingestion & Claim Extraction · API client.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §7 (API surface)
 *
 * One hook per backend endpoint, and no hook without one. A hook for an
 * endpoint that does not answer lets a screen be built against it, and the
 * caller finds out in the browser rather than in a review.
 *
 * ── Two verbs `@ai/core` does not carry ─────────────────────────────────────
 *
 * `api` in core has get/post/del and a JSON content type. The confirmation
 * pass needs PATCH, and the upload path needs multipart — where setting
 * `Content-Type` yourself is actively wrong, because the browser has to add the
 * boundary. Both live here rather than in core: core is a versioned dependency
 * shared by nineteen repos, and "M01 needed PATCH" is not a reason to move all
 * of them. If a second module needs them, that is the moment they graduate.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@ai/core";
import type {
  Capabilities,
  ClaimListing,
  CorrectionIn,
  Deps,
  Health,
  IntakeErrorDetail,
  ModuleStatus,
  ProgressEvent,
  RedFlagListing,
  Resume,
  ResumeDiff,
  ResumeIngestIn,
  RewriteSuggestion,
  SkillListing,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

/**
 * An intake refusal, with the sentence the student should read.
 *
 * The backend answers a bad upload with `{code, message, fallback}` rather than
 * a bare string, precisely so a screen can show the message and offer the way
 * out instead of rendering a status code (§10: "never a raw stack trace").
 */
export class IntakeError extends Error {
  constructor(
    readonly status: number,
    readonly detail: IntakeErrorDetail,
  ) {
    super(detail.message);
    this.name = "IntakeError";
  }
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${response.status}: ${response.statusText}`);
  return (await response.json()) as T;
}

async function upload(candidateId: string, file: File): Promise<Resume> {
  const form = new FormData();
  form.append("candidate_id", candidateId);
  form.append("file", file);

  // No Content-Type header on purpose — the browser sets it, with the
  // multipart boundary that the server needs to split the parts.
  const response = await fetch(`${BASE}/v1/resumes`, { method: "POST", body: form });

  if (!response.ok) {
    let detail: IntakeErrorDetail = {
      code: "unknown",
      message: "That upload did not work. Paste the text instead — that always works.",
      fallback: "text",
    };
    try {
      const body = await response.json();
      if (body?.detail && typeof body.detail === "object") detail = body.detail;
      else if (typeof body?.detail === "string") detail = { ...detail, message: body.detail };
    } catch {
      /* non-JSON error body — the default sentence above is the right one */
    }
    throw new IntakeError(response.status, detail);
  }
  return (await response.json()) as Resume;
}

export const m01Keys = {
  health: ["m01", "health"] as const,
  status: ["m01", "status"] as const,
  deps: ["m01", "deps"] as const,
  capabilities: ["m01", "capabilities"] as const,
  resume: (id: string) => ["m01", "resume", id] as const,
  claims: (id: string, band?: string) => ["m01", "claims", id, band ?? "all"] as const,
  redFlags: (id: string) => ["m01", "red-flags", id] as const,
  skills: (id: string) => ["m01", "skills", id] as const,
  byCandidate: (candidateId: string) => ["m01", "resumes", candidateId] as const,
  diff: (a: string, b: string) => ["m01", "diff", a, b] as const,
};

/** Everything derived from one resume, invalidated together after a write. */
function invalidateResume(qc: ReturnType<typeof useQueryClient>, resume: Resume) {
  qc.setQueryData(m01Keys.resume(resume.id), resume);
  qc.invalidateQueries({ queryKey: ["m01", "claims", resume.id] });
  qc.invalidateQueries({ queryKey: m01Keys.redFlags(resume.id) });
  qc.invalidateQueries({ queryKey: m01Keys.skills(resume.id) });
  qc.invalidateQueries({ queryKey: m01Keys.byCandidate(resume.candidate_id) });
}

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

/**
 * What this deployment can read (FR-1.1, FR-1.16).
 *
 * Asked before the dropzone renders. Cached for the session because a server
 * does not grow a PDF library while you are looking at it.
 */
export function useCapabilities() {
  return useQuery({
    queryKey: m01Keys.capabilities,
    queryFn: () => api.get<Capabilities>("/v1/capabilities"),
    staleTime: Infinity,
    retry: false,
  });
}

/* ------------------------------------------------------------------ */
/*  Ingest                                                            */
/* ------------------------------------------------------------------ */

/** The always-works path (§7, §10). No file, no PDF library, no OCR. */
export function useIngestResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ResumeIngestIn) => api.post<Resume>("/v1/resumes/from-text", body),
    onSuccess: (resume) => {
      invalidateResume(qc, resume);
      // An ingest reads the ontology, so whether M04 answered is now known
      // more precisely than the last cached probe said.
      qc.invalidateQueries({ queryKey: m01Keys.deps });
    },
  });
}

/** PDF or DOCX (FR-1.1). Rejects with an `IntakeError` a screen can render. */
export function useUploadResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ candidateId, file }: { candidateId: string; file: File }) =>
      upload(candidateId, file),
    onSuccess: (resume) => {
      invalidateResume(qc, resume);
      qc.invalidateQueries({ queryKey: m01Keys.deps });
    },
  });
}

/* ------------------------------------------------------------------ */
/*  Reading                                                           */
/* ------------------------------------------------------------------ */

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

/** The Claim Map (§2.3 Screen 4), already ordered and with `fix_first` picked. */
export function useClaims(resumeId: string | undefined, band?: string) {
  return useQuery({
    queryKey: m01Keys.claims(resumeId ?? "", band),
    enabled: Boolean(resumeId),
    queryFn: () =>
      api.get<ClaimListing>(
        `/v1/resumes/${resumeId}/claims${band ? `?band=${encodeURIComponent(band)}` : ""}`,
      ),
  });
}

export function useRedFlags(resumeId: string | undefined) {
  return useQuery({
    queryKey: m01Keys.redFlags(resumeId ?? ""),
    enabled: Boolean(resumeId),
    queryFn: () => api.get<RedFlagListing>(`/v1/resumes/${resumeId}/red-flags`),
  });
}

export function useSkills(resumeId: string | undefined) {
  return useQuery({
    queryKey: m01Keys.skills(resumeId ?? ""),
    enabled: Boolean(resumeId),
    queryFn: () => api.get<SkillListing>(`/v1/resumes/${resumeId}/skills`),
  });
}

export function useDiff(newer: string | undefined, older: string | undefined) {
  return useQuery({
    queryKey: m01Keys.diff(newer ?? "", older ?? ""),
    enabled: Boolean(newer && older),
    queryFn: () => api.get<ResumeDiff>(`/v1/resumes/${newer}/diff?against=${older}`),
  });
}

/* ------------------------------------------------------------------ */
/*  The confirmation pass (FR-1.11, FR-1.12)                          */
/* ------------------------------------------------------------------ */

export function useCorrectSection(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sectionId, kind }: { sectionId: string; kind: string }) =>
      patch<Resume>(`/v1/resumes/${resumeId}/sections/${sectionId}`, {
        field: "kind",
        value: kind,
      }),
    onSuccess: (resume) => invalidateResume(qc, resume),
  });
}

export function useEditClaim(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, field, value }: { claimId: string; field: string; value: string }) =>
      patch<Resume>(`/v1/resumes/${resumeId}/claims/${claimId}`, { field, value }),
    onSuccess: (resume) => invalidateResume(qc, resume),
  });
}

export function useEditSkill(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ label, present }: { label: string; present: boolean }) =>
      api.post<Resume>(`/v1/resumes/${resumeId}/skills`, { label, present }),
    onSuccess: (resume) => invalidateResume(qc, resume),
  });
}

/** Any correction, for callers that already speak the audit shape. */
export function useCorrection(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CorrectionIn) =>
      api.post<Resume>(`/v1/resumes/${resumeId}/corrections`, body),
    onSuccess: (resume) => invalidateResume(qc, resume),
  });
}

/** "Looks right — continue" (§2.3 Screen 3). Idempotent. */
export function useConfirmResume(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Resume>(`/v1/resumes/${resumeId}/confirm`),
    onSuccess: (resume) => invalidateResume(qc, resume),
  });
}

/* ------------------------------------------------------------------ */
/*  Rewrite (FR-1.19)                                                 */
/* ------------------------------------------------------------------ */

/**
 * On request only, and it changes nothing on the server (§15 decision 2).
 *
 * A mutation rather than a query for exactly that reason: it is something the
 * student chooses to ask for, not something a screen fetches because it
 * rendered.
 */
export function useRewriteClaim(resumeId: string) {
  return useMutation({
    mutationFn: (claimId: string) =>
      api.post<RewriteSuggestion>(`/v1/resumes/${resumeId}/claims/${claimId}/rewrite`),
  });
}

export function useDeleteResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (resumeId: string) => api.del<void>(`/v1/resumes/${resumeId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["m01"] }),
  });
}

/* ------------------------------------------------------------------ */
/*  Progress (§2.3 Screen 2)                                          */
/* ------------------------------------------------------------------ */

/**
 * Subscribe to the parse narration.
 *
 * Not a react-query hook: it is a stream, and modelling a stream as a query
 * means either buffering it into one value (losing the narration, which is the
 * entire point) or re-running it on every cache event.
 *
 * Returns an unsubscribe function. `EventSource` reconnects on its own after a
 * drop, which for a finished parse would replay the whole narration, so the
 * source is closed as soon as the `complete` stage arrives.
 */
export function subscribeToProgress(
  resumeId: string,
  onEvent: (event: ProgressEvent) => void,
  onDone?: () => void,
): () => void {
  const source = new EventSource(`${BASE}/v1/resumes/${resumeId}/stream`);

  const finish = () => {
    source.close();
    onDone?.();
  };

  source.onmessage = (message) => {
    try {
      const parsed = JSON.parse(message.data) as ProgressEvent;
      onEvent(parsed);
      if (parsed.stage === "complete") finish();
    } catch {
      /* a malformed frame is not worth tearing the stream down for */
    }
  };
  // An error after the last frame is the server closing a finished stream,
  // which is not a failure. The screen has the stages either way.
  source.onerror = finish;

  return () => source.close();
}

/**
 * M01 — Resume Ingestion & Claim Extraction · API client.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §7 (API surface)
 *
 * One hook per backend endpoint, and no hook without one. A hook for an
 * endpoint that does not answer lets a screen be built against it, and the
 * caller finds out in the browser rather than in a review.
 *
 * ── The two endpoints deliberately without their own hook ───────────────────
 *
 * `POST /v1/resumes/ingest` and `GET /v1/resumes/{id}/diff/{other}` are the
 * server's own aliases for `/resumes/from-text` and `/diff?against=`. Both
 * exist because a caller already used the older spelling; both run the same
 * function on the same line. A second hook would let two screens drift onto
 * two spellings of one operation and disagree about which is current, so the
 * rule above is read as one hook per OPERATION — and the alias is named here
 * rather than left for the next person to rediscover in `router.py`.
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

import { identityHeaders } from "./components/candidate";
import type {
  Capabilities,
  ClaimListing,
  DrillHandoff,
  Correction,
  CorrectionIn,
  Deps,
  DisclosureReport,
  Health,
  IntakeErrorDetail,
  ModuleStatus,
  ProgressEvent,
  QualityReport,
  RedFlagListing,
  Resume,
  ResumeContact,
  ResumeDiff,
  ResumeEventRow,
  ResumeIngestIn,
  ResumePageInfo,
  ResumeReview,
  RevokeResult,
  RewriteSuggestion,
  ShareGrant,
  ShareIn,
  SkillListing,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

/**
 * M01's own prefix in the platform shell.
 *
 * The shell has no gateway; it proxies `/v1/<noun>` to whichever module owns
 * that noun, from a table it keeps. `resumes` is M01's, so the resume endpoints
 * route correctly — but a per-module META endpoint has no noun anybody owns.
 * `capabilities` was in no table, so `GET /v1/capabilities` never reached M01,
 * `useCapabilities` failed, and the upload control silently disappeared inside
 * the shell while working perfectly standalone.
 *
 * The shell already provides `/sys/<module>/...` for exactly this. So a meta
 * request tries the plain path first — which is what standalone serves — and
 * falls back to the module-scoped one. Both apps work, and neither needs a
 * table entry that every other module would also want to claim.
 */
const SYS = "/sys/m01";

async function meta<T>(path: string): Promise<T> {
  try {
    return await api.get<T>(path);
  } catch {
    return await api.get<T>(`${SYS}${path}`);
  }
}

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
    // `identityHeaders()` explicitly, because this is a RAW fetch.
    //
    // `setIdentityHeaders` puts them on `@ai/core`'s wrapper, and the two
    // helpers in this file exist precisely because they do not go through it.
    // So they did not get the header, and the backend — which now refuses
    // candidate-scoped data without one — answered 403 "Not signed in." on
    // every upload while the paste path, which does use `api.post`, worked
    // perfectly. The screen offered "paste the text instead" and was right.
    headers: { "Content-Type": "application/json", ...identityHeaders() },
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
  // multipart boundary that the server needs to split the parts. Identity is
  // not optional though; see the note in `patch`.
  const response = await fetch(`${BASE}/v1/resumes`, {
    method: "POST",
    headers: identityHeaders(),
    body: form,
  });

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
  quality: ["m01", "quality"] as const,
  resume: (id: string) => ["m01", "resume", id] as const,
  claims: (id: string, band?: string) => ["m01", "claims", id, band ?? "all"] as const,
  redFlags: (id: string) => ["m01", "red-flags", id] as const,
  skills: (id: string) => ["m01", "skills", id] as const,
  byCandidate: (candidateId: string) => ["m01", "resumes", candidateId] as const,
  diff: (a: string, b: string) => ["m01", "diff", a, b] as const,
  contact: (id: string) => ["m01", "contact", id] as const,
  corrections: (id: string) => ["m01", "corrections", id] as const,
  events: (id: string) => ["m01", "events", id] as const,
  pages: (id: string) => ["m01", "pages", id] as const,
  review: (id: string) => ["m01", "review", id] as const,
  disclosure: (id: string, viewer: string) => ["m01", "disclosure", id, viewer] as const,
};

/** Everything derived from one resume, invalidated together after a write. */
function invalidateResume(qc: ReturnType<typeof useQueryClient>, resume: Resume) {
  qc.setQueryData(m01Keys.resume(resume.id), resume);
  qc.invalidateQueries({ queryKey: ["m01", "claims", resume.id] });
  qc.invalidateQueries({ queryKey: m01Keys.redFlags(resume.id) });
  qc.invalidateQueries({ queryKey: m01Keys.skills(resume.id) });
  // The review is computed from the claims, so an edit re-checks it.
  qc.invalidateQueries({ queryKey: m01Keys.review(resume.id) });
  qc.invalidateQueries({ queryKey: m01Keys.byCandidate(resume.candidate_id) });
  // Every write above goes through the correction log and emits an event, so
  // the two audit views are stale the moment any of them lands. They were left
  // out of this list once and the log looked like it had stopped recording.
  qc.invalidateQueries({ queryKey: m01Keys.corrections(resume.id) });
  qc.invalidateQueries({ queryKey: m01Keys.events(resume.id) });
  // AC-1.7's edit rate is computed from those corrections.
  qc.invalidateQueries({ queryKey: m01Keys.quality });
}

/* ------------------------------------------------------------------ */
/*  Meta                                                              */
/* ------------------------------------------------------------------ */

export function useHealth() {
  return useQuery({
    queryKey: m01Keys.health,
    queryFn: () => meta<Health>("/health"),
    retry: false,
  });
}

/** What the platform registry says this module is — not what it says itself. */
export function useModuleStatus() {
  return useQuery({
    queryKey: m01Keys.status,
    queryFn: () => meta<ModuleStatus>("/status"),
    retry: false,
  });
}

export function useDeps() {
  return useQuery({
    queryKey: m01Keys.deps,
    queryFn: () => meta<Deps>("/v1/deps"),
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
    queryFn: () => meta<Capabilities>("/v1/capabilities"),
    staleTime: Infinity,
    retry: false,
  });
}

/**
 * AC-1.7, answerable (§13, `GET /v1/quality`).
 *
 * *"Confirmation screen edit rate; tracked; > 40% means the parser needs
 * work."*  It was tracked and nothing added it up, so the criterion was a
 * column rather than a number anybody could look at. `meta` rather than `api`
 * because `quality` is not a noun any module owns, so the shell has no route
 * for it and only the `/sys/m01` fallback reaches here.
 */
export function useQuality() {
  return useQuery({
    queryKey: m01Keys.quality,
    queryFn: () => meta<QualityReport>("/v1/quality"),
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

/**
 * The review (2026-10-04): every check, each line that fails one, and the
 * document as edited so far. Counts, never a total — §15 decision 1.
 */
export function useReview(resumeId: string | undefined) {
  return useQuery({
    queryKey: m01Keys.review(resumeId ?? ""),
    enabled: Boolean(resumeId),
    queryFn: () => api.get<ResumeReview>(`/v1/resumes/${resumeId}/review`),
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

/**
 * The contact block (FR-1.17). Never fetched because a screen rendered.
 *
 * `enabled` is the point of this signature. Every other field on a resume
 * arrives whether anyone looked at it or not; this one is the single request
 * that deliberately releases the student's email and phone number, and the
 * server gives it its own route and its own audit tag precisely so "who saw
 * it" is answerable. A hook that fired on mount would make that log say
 * "everyone who opened the page", which is the same as saying nothing.
 *
 * So the caller passes `reveal` and it starts false. See `ContactPanel`.
 */
export function useResumeContact(resumeId: string | undefined, reveal: boolean) {
  return useQuery({
    queryKey: m01Keys.contact(resumeId ?? ""),
    enabled: Boolean(resumeId) && reveal,
    retry: false,
    // Not cached across the session: the next reveal should be a new access,
    // recorded as one, rather than served silently from memory.
    staleTime: 0,
    gcTime: 0,
    queryFn: () => api.get<ResumeContact>(`/v1/resumes/${resumeId}/contact`),
  });
}

/** Every time the parser was overruled on this resume (FR-1.12). */
export function useCorrections(resumeId: string | undefined) {
  return useQuery({
    queryKey: m01Keys.corrections(resumeId ?? ""),
    enabled: Boolean(resumeId),
    queryFn: () => api.get<Correction[]>(`/v1/resumes/${resumeId}/corrections`),
  });
}

/**
 * The `resume.*` stage boundaries recorded for this resume (FR-1.20).
 *
 * Readable over HTTP for the reason the endpoint exists: an event stream
 * nobody can look at is one that quietly stops being emitted.
 */
export function useResumeEvents(resumeId: string | undefined) {
  return useQuery({
    queryKey: m01Keys.events(resumeId ?? ""),
    enabled: Boolean(resumeId),
    queryFn: () => api.get<ResumeEventRow[]>(`/v1/resumes/${resumeId}/events`),
  });
}

/**
 * What a given viewer may see, and until when (§15 decisions 3 and 4).
 *
 * Fails closed on the server: a viewer with no grant gets `aggregate_only`.
 * There is no auth in this platform yet, so this ANSWERS the question rather
 * than enforcing it — which is why the screen that renders it says so.
 */
export function useDisclosure(resumeId: string | undefined, viewer: string) {
  return useQuery({
    queryKey: m01Keys.disclosure(resumeId ?? "", viewer),
    enabled: Boolean(resumeId && viewer),
    queryFn: () =>
      api.get<DisclosureReport>(
        `/v1/resumes/${resumeId}/disclosure?viewer=${encodeURIComponent(viewer)}`,
      ),
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

/**
 * §2.3 Screen 3's fourth editable target: *"sections, bullets, skills, and
 * dates"* (FR-1.11).
 *
 * Dates were the one thing a student could not fix, and a mis-read date drives
 * both the timeline-gap flag and `recency` — so the flag they are being told to
 * prepare an answer for could be about a range the parser invented. An empty
 * value strikes such a range; the server refuses a value it cannot read as a
 * date rather than storing a string nothing can compare.
 */
export function useEditDate(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ index, value }: { index: number; value: string | null }) =>
      patch<Resume>(`/v1/resumes/${resumeId}/dates/${index}`, { value }),
    onSuccess: (resume) => invalidateResume(qc, resume),
  });
}

/**
 * Remove a claim the student says is not theirs (EC-1.17).
 *
 * *"User deletes every claim in the editor — allowed; product continues
 * resume-free."*  The server routes this through the correction log rather
 * than as a bare delete, because a student striking a claim we invented is the
 * most informative correction there is and AC-1.7 should count it.
 */
export function useDeleteClaim(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: string) =>
      api.del<Resume>(`/v1/resumes/${resumeId}/claims/${claimId}`),
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
/*  Sharing (§15 decision 4)                                          */
/* ------------------------------------------------------------------ */

/**
 * The student decides who sees this.
 *
 * The policy is not decided — the placement cell has not been asked. What is
 * decided is the shape: a grant is to somebody named, it expires, and revoking
 * leaves a trace. Whichever way the decision lands it lands as configuration
 * on top of this, so the screen can exist before the answer does.
 */
export function useShareResume(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ShareIn) => api.post<ShareGrant>(`/v1/resumes/${resumeId}/share`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["m01", "disclosure", resumeId] }),
  });
}

/** Withdraw a grant. Recorded, not deleted — a student who shared and then
 *  withdrew has a right to know it was withdrawn. */
export function useRevokeShare(resumeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (grantee: string) =>
      api.del<RevokeResult>(`/v1/resumes/${resumeId}/share/${encodeURIComponent(grantee)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["m01", "disclosure", resumeId] }),
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

/* ------------------------------------------------------------------ */
/*  The defend drill (§2.3 Screen 5, AC-1.8)                          */
/* ------------------------------------------------------------------ */

/**
 * Start the 2-minute drill on one claim.
 *
 * §13: *"The KPI to actually watch is AC-1.8. Parsing accuracy is a means; a
 * student running a drill because they saw a risky claim is the outcome."*
 * Until this existed the Claim Map ended in a cul-de-sac and that KPI had no
 * numerator at all.
 *
 * A mutation rather than a query because it is something the student chooses
 * to start — and because when M06 is up it creates a session, which is not a
 * thing a screen should do by rendering.
 */
export function useStartDrill(resumeId: string) {
  return useMutation({
    mutationFn: (claimId: string) =>
      api.post<DrillHandoff>(`/v1/resumes/${resumeId}/claims/${claimId}/drill`),
  });
}

/* ------------------------------------------------------------------ */
/*  The original page (§8.1 PdfHighlightViewer, §8.3)                 */
/* ------------------------------------------------------------------ */

/**
 * The pages of the uploaded document, with their size in points.
 *
 * An empty list is the answer for a pasted resume, and §8.2 asks for that as a
 * STATE — "Original not available (pasted text)" — rather than an error. The
 * viewer branches on it and falls back to the text highlight.
 */
export function usePages(resumeId: string | undefined) {
  return useQuery({
    queryKey: m01Keys.pages(resumeId ?? ""),
    enabled: Boolean(resumeId),
    retry: false,
    // A stored file does not change; only a re-upload does, and that is a
    // different resume id.
    staleTime: Infinity,
    queryFn: () => api.get<ResumePageInfo[]>(`/v1/resumes/${resumeId}/pages`),
  });
}

/** The URL of one rendered page. */
export function pageImageUrl(resumeId: string, page: number): string {
  return `${BASE}/v1/resumes/${resumeId}/pages/${page}`;
}

/**
 * One rendered page, fetched WITH the session's identity, as a local blob URL.
 *
 * This was a plain `img src`, on the reasoning that the contact block is
 * already painted out. But an `<img>` cannot send headers, and the router
 * refuses anyone who does not say who they are — so every page came back 403
 * and the viewer showed a broken image. Nobody saw it because the uploads
 * before the original was kept had no page to draw (2026-10-04).
 *
 * The URL is never revoked: the query cache hands the same one to every
 * remount, and a revoked URL would break the next one. A page is a few
 * hundred kilobytes and lives as long as the tab.
 */
export function usePageImage(resumeId: string, page: number) {
  return useQuery({
    queryKey: [...m01Keys.pages(resumeId), "image", page],
    staleTime: Infinity,
    retry: false,
    queryFn: async () => {
      const response = await fetch(pageImageUrl(resumeId, page), { headers: identityHeaders() });
      if (!response.ok) throw new Error(`Page ${page} could not be drawn (${response.status}).`);
      return URL.createObjectURL(await response.blob());
    },
  });
}

/**
 * Who the browser is — `@ai/core`'s session (v0.12.0), in this module's words:
 * which resumes are listed and which one is ingested for.
 *
 * This file used to keep its own id under its own localStorage key and set the
 * page's identity headers itself. The reasons it gave still hold — a hardcoded
 * uuid hides scoping bugs, a fresh one per load leaves every list empty — and
 * they are now the session's: one persisted student per browser, the seeded
 * one by default, set from the shell's sign-in screen or this module's own
 * control. Mounted in Platform_Shell beside M02, M06 and M15, the student is
 * the same one everywhere instead of whoever's module loaded last. The old key
 * is migrated by the session, so nobody loses the student they were.
 */

import {
  SEEDED_CANDIDATE_ID,
  candidateIdOf,
  getSession,
  sessionHeaders,
  signIn,
  subscribeSession,
} from "@ai/core";

/** M01's first seeded candidate. Deliberately shared across the module seeds. */
export const DEFAULT_CANDIDATE_ID = SEEDED_CANDIDATE_ID;

/**
 * The student these screens are about: the signed-in student, or — for staff,
 * who are nobody's candidate — the seeded one, which the backend then decides
 * whether they may see.
 */
export function getCandidateId(): string {
  return candidateIdOf(getSession()) ?? DEFAULT_CANDIDATE_ID;
}

/** The dev control's "be this student". */
export function setCandidateId(next: string): void {
  signIn({ role: "student", subject: next.trim() || DEFAULT_CANDIDATE_ID });
}

/** The headers a raw `fetch` has to send for itself. See `api.ts`. */
export function identityHeaders(): Record<string, string> {
  return sessionHeaders();
}

/** Kept for callers; the session publishes the headers itself now. */
export function publishIdentity(): void {}

export function subscribeCandidateId(listener: () => void): () => void {
  return subscribeSession(listener);
}

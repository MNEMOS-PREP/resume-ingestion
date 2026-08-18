import { useSyncExternalStore } from "react";

import { DEFAULT_CANDIDATE_ID, getCandidateId, subscribeCandidateId } from "./candidate";

/**
 * Separate from candidate.ts so the store stays a plain module with no React
 * import. The shell and three screens read it, and a provider wrapping all of
 * them would re-render the whole tree on every change of anything.
 */
export function useCandidateId(): string {
  return useSyncExternalStore(subscribeCandidateId, getCandidateId, () => DEFAULT_CANDIDATE_ID);
}

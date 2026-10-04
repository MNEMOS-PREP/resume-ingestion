/**
 * M01 - Resume Ingestion & Claim Extraction · routes.
 *
 * Nine screens. Two are there because a fact with no surface is a fact nobody
 * can check, and one is there because two modules that never linked to each
 * other are two products:
 *
 *   /resumes/:id/target       a resume alone answers "what have I claimed". A
 *                             resume against a POSTING answers "will this get
 *                             me in", which is the question the student came
 *                             with — and it lives in M02, which until now had
 *                             no path leading to it. Asked as a question with
 *                             a real second answer, because FR-1.14's principle
 *                             runs both ways: somebody who uploaded a resume to
 *                             fix their resume should not be pushed into a
 *                             job-matching flow they did not ask for.
 *
 *   /skipped                  FR-1.14 is a P0 - "allow the entire product to be
 *                             used with no resume at all" - and a Skip button
 *                             that navigates nowhere is the requirement quietly
 *                             not met. A real route is what makes it testable.
 *
 *   /resumes/:id/audit        the correction log and the event stream. Both
 *                             were written from the first commit and neither
 *                             was readable outside the database.
 *
 *   /resumes/:id/privacy      §15 decisions 3 and 4. The retention policy and
 *                             the share gate were both built and had no
 *                             surface, which is the worst state to be in: the
 *                             right thing decided, and no way to show it.
 *
 *   /quality                  AC-1.7. "Edit rate > 40% means the parser needs
 *                             work" was a number you had to curl for, so it
 *                             was looked at by whoever remembered to.
 */

import { Route } from "react-router-dom";

import { AuditPage } from "./components/AuditPage";
import { DiffPage } from "./components/DiffPage";
import { IngestPage, SkippedPage } from "./components/IngestPage";
import { PrivacyPage } from "./components/PrivacyPage";
import { QualityPage } from "./components/QualityPage";
import { ResumePage } from "./components/ResumePage";
import { ReviewPage } from "./components/ReviewPage";
import { TargetJobPage } from "./components/TargetJobPage";

/** Where this module's front door is, standalone and in the shell alike. */
export const M01_HOME = "/resume";

/*
  No index route and no /deps (2026-10-04). The index belongs to whoever hosts
  this tree — the shell's Today, or the standalone app's redirect to
  M01_HOME — and the shell mounts one /deps for every module. That is what
  lets Platform_Shell mount this tree whole instead of two screens by name.
*/
export const m01Routes = (
  <Route key="m01">
    <Route path="/resume" element={<IngestPage />} />
    <Route path="/resumes/:resumeId" element={<ResumePage />} />
    <Route path="/resumes/:resumeId/review" element={<ReviewPage />} />
    <Route path="/resumes/:resumeId/target" element={<TargetJobPage />} />
    <Route path="/resumes/:resumeId/diff" element={<DiffPage />} />
    <Route path="/resumes/:resumeId/audit" element={<AuditPage />} />
    <Route path="/resumes/:resumeId/privacy" element={<PrivacyPage />} />
    <Route path="/skipped" element={<SkippedPage />} />
    <Route path="/quality" element={<QualityPage />} />
  </Route>
);

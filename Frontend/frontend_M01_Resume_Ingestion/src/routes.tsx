/**
 * M01 - Resume Ingestion & Claim Extraction · routes.
 *
 * Eight screens, and two of them are there because a fact with no surface is a
 * fact nobody can check:
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
import { DepsPage } from "./components/DepsPage";
import { DiffPage } from "./components/DiffPage";
import { IngestPage, SkippedPage } from "./components/IngestPage";
import { PrivacyPage } from "./components/PrivacyPage";
import { QualityPage } from "./components/QualityPage";
import { ResumePage } from "./components/ResumePage";

export const m01Routes = (
  <Route key="m01">
    <Route index element={<IngestPage />} />
    <Route path="/resumes/:resumeId" element={<ResumePage />} />
    <Route path="/resumes/:resumeId/diff" element={<DiffPage />} />
    <Route path="/resumes/:resumeId/audit" element={<AuditPage />} />
    <Route path="/resumes/:resumeId/privacy" element={<PrivacyPage />} />
    <Route path="/skipped" element={<SkippedPage />} />
    <Route path="/quality" element={<QualityPage />} />
    <Route path="/deps" element={<DepsPage />} />
  </Route>
);

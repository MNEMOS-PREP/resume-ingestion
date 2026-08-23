/**
 * M01 - Resume Ingestion & Claim Extraction · routes.
 *
 * Five screens, and `/skipped` is one of them on purpose. FR-1.14 is a P0 -
 * "allow the entire product to be used with no resume at all" - and a Skip
 * button that navigates nowhere is the requirement quietly not met. Giving it a
 * real route is what makes the path testable.
 */

import { Route } from "react-router-dom";

import { DepsPage } from "./components/DepsPage";
import { DiffPage } from "./components/DiffPage";
import { IngestPage, SkippedPage } from "./components/IngestPage";
import { ResumePage } from "./components/ResumePage";

export const m01Routes = (
  <Route key="m01">
    <Route index element={<IngestPage />} />
    <Route path="/resumes/:resumeId" element={<ResumePage />} />
    <Route path="/resumes/:resumeId/diff" element={<DiffPage />} />
    <Route path="/skipped" element={<SkippedPage />} />
    <Route path="/deps" element={<DepsPage />} />
  </Route>
);

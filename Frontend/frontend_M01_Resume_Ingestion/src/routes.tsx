/**
 * M01 - Resume Ingestion & Claim Extraction · routes.
 *
 * Two screens, because there are two the backend can fill. The spec's §7
 * surface has fourteen endpoints; a route for /claims or /red-flags would be a
 * link to a page that cannot load.
 */

import { Route } from "react-router-dom";

import { DepsPage } from "./components/DepsPage";
import { IngestPage } from "./components/IngestPage";
import { ResumePage } from "./components/ResumePage";

export const m01Routes = (
  <Route key="m01">
    <Route index element={<IngestPage />} />
    <Route path="/resumes/:resumeId" element={<ResumePage />} />
    <Route path="/deps" element={<DepsPage />} />
  </Route>
);

/**
 * One resume: the confirmation pass, then the workspace.
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §2.3 Screens 3 and 4, §8
 *
 * ── Why they are one route and two shapes ───────────────────────────────────
 *
 * They are one motion. §2.3 puts the confirmation pass immediately before the
 * payoff *because* the payoff depends on it: a Claim Map built from a mis-read
 * document is a diagnosis of the wrong resume, and the student has no way to
 * tell. So `confirmed` decides which is showing, and the confirmation pass
 * stays reachable afterwards — a student who spots a mis-read heading on the
 * map must be able to go back and fix it, not start again.
 *
 * They do not get the same layout, though.
 *
 * **The confirmation pass is a screen.** It asks for one thing — *"here's what
 * I read, fix anything I got wrong"* — and §2.3 calls it *"the single most
 * important UX decision in this module"*. It gets a reading column, the
 * document beside it, and nothing else on the page. Rendering it as a pane
 * inside the workspace would surround the one question we need answered with
 * three columns of things to do instead.
 *
 * **The Claim Map is a workspace.** See `ResumeWorkspace`.
 *
 * The shell already gave this route the whole viewport (`AppShell`), so the
 * confirmation branch supplies its own scroll and its own reading width rather
 * than getting them from a max-width container it no longer sits in.
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useResume } from "../api";
import { ConfirmationEditor } from "./ConfirmationEditor";
import { ResumeWorkspace } from "./ResumeWorkspace";
import { RedactionNote, SourceHighlight } from "./SourceHighlight";
import { Empty, SkeletonRows } from "../ui/primitives";

export function ResumePage() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const resume = useResume(resumeId);
  const [reviewing, setReviewing] = useState(false);

  if (resume.isLoading) {
    return (
      <div className="mx-auto w-full max-w-5xl px-5 py-8 md:px-8">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  if (resume.isError || !resume.data) {
    return (
      <div className="mx-auto w-full max-w-5xl px-5 py-8 md:px-8">
        <Empty title="No such resume">
          The id in the URL does not match a stored resume.
          <div className="mt-3">
            <Link to="/resume" className="text-sm font-medium text-brand hover:text-brand-hover">
              Start again &rarr;
            </Link>
          </div>
        </Empty>
      </div>
    );
  }

  const data = resume.data;
  const showConfirmation = reviewing || !data.confirmed;

  if (showConfirmation) {
    // The same two-column shape as the workspace, for the same reason.
    //
    // This screen used to be a `max-w-5xl` reading column with the document in
    // a 22rem aside capped at 28rem tall. On a real monitor that put a
    // sixty-line resume in a box showing fifteen of them, with the rest of the
    // window empty on both sides — the student is asked to check what we read
    // while most of what we read is behind a scrollbar in the smallest element
    // on the page.
    //
    // §2.3 calls this "the single most important UX decision in this module"
    // and budgets it at fifteen seconds. Fifteen seconds is not enough time to
    // scroll a panel, so the panel stops being one: it fills the height, and
    // the editor scrolls beside it.
    return (
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-5 py-8 md:px-8 md:py-10">
            <ConfirmationEditor resume={data} onConfirmed={() => setReviewing(false)} />
          </div>
        </div>

        <aside className="flex max-h-[60vh] shrink-0 flex-col border-t border-line bg-surface lg:h-full lg:max-h-none lg:w-[30rem] lg:border-l lg:border-t-0">
          <p className="rule-label shrink-0 px-4 pt-4">What we read</p>
          <div className="min-h-0 flex-1 px-4 py-2">
            <SourceHighlight text={data.redacted_text} span={null} fill />
          </div>
          <div className="shrink-0 px-4 pb-4">
            <RedactionNote />
          </div>
        </aside>
      </div>
    );
  }

  return <ResumeWorkspace resume={data} onReview={() => setReviewing(true)} />;
}

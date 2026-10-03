/**
 * Who can see this, for how long, and how to make it stop (§15 decisions 3, 4).
 *
 * ── This screen exists because the DECISIONS do not ─────────────────────────
 *
 * Two of the spec's open questions are not code questions:
 *
 *   3. how long do we keep the raw PDF? *Proposal: enrollment + 1 year,
 *      deletable on request. Needs the ethics-committee sign-off.*
 *   4. may a placement officer see a student's risky claims? *Proposal:
 *      aggregate only by default; individual view requires an explicit share.*
 *
 * The mechanism for both was built and had no surface, which is the worst of
 * the three possible states: a system with no retention mechanism has decided
 * "forever" and one with no share gate has decided "anyone", but a system with
 * a mechanism nobody can see has decided the right thing and cannot show it.
 * A student asking "how long do you keep my resume?" is entitled to an answer
 * that is not "read the source".
 *
 * ── What this page is honest about ──────────────────────────────────────────
 *
 * There is no auth in this platform yet. So the disclosure check ANSWERS the
 * question rather than enforcing it, and the page says so rather than
 * implying a gate that is not there. `decided: false` on the retention policy
 * is rendered, not hidden — a policy in force while its sign-off is pending is
 * a fact about the system, and this is the trust screen.
 */

import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  useDeleteResume,
  useDisclosure,
  useResume,
  useRevokeShare,
  useShareResume,
} from "../api";
import { ContactPanel } from "./ContactPanel";
import { useCandidateId } from "./candidate-hook";
import { Btn, Empty, ErrorNote, Field, Panel, Pill, Rows, Section, SkeletonRows, TextField } from "../ui/primitives";
import type { DisclosureLevel } from "../types";

const DISCLOSURE_COPY: Record<
  DisclosureLevel,
  { label: string; tone: "confirmed" | "reported" | "neutral"; meaning: string }
> = {
  self_access: {
    label: "everything",
    tone: "confirmed",
    meaning:
      "This is your own resume, so you see all of it. That is never something you have to be granted.",
  },
  shared_by_student: {
    label: "your individual claims",
    tone: "reported",
    meaning:
      "You granted this person sight of your claims. They see the same map you do, until the grant expires or you withdraw it.",
  },
  aggregate_only: {
    label: "counts only, no names",
    tone: "neutral",
    meaning:
      "The default, and what everybody gets until you say otherwise. They can see how a cohort is doing; they cannot see which bullet is yours.",
  },
};

export function PrivacyPage() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const navigate = useNavigate();
  const candidateId = useCandidateId();
  const resume = useResume(resumeId);

  if (resume.isLoading) return <SkeletonRows rows={6} />;

  if (resume.isError || !resume.data) {
    return (
      <Empty title="No such resume">
        The id in the URL does not match a stored resume.
        <div className="mt-3">
          <Link to="/resume" className="text-sm font-medium text-brand hover:text-brand-hover">
            Start again &rarr;
          </Link>
        </div>
      </Empty>
    );
  }

  const data = resume.data;

  return (
    <>
      <header className="mb-8">
        <p className="rule-label">resume {data.id.slice(0, 8)}</p>
        <h1 className="mt-0.5 text-display font-semibold text-ink">Who can see this</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          Nobody, by default, beyond counts with no name attached. Everything below is something
          you turn on deliberately, and everything you turn on can be turned off again with a
          record that it was.
        </p>
      </header>

      <ContactPanel resume={data} />

      <ShareControls resumeId={data.id} candidateId={candidateId} />

      <DangerZone
        resumeId={data.id}
        filename={data.filename}
        onDeleted={() => navigate("/resume", { replace: true })}
      />

      <div className="flex flex-wrap gap-4 border-t border-line pt-5">
        <Link
          to={`/resumes/${data.id}`}
          className="text-sm font-medium text-brand hover:text-brand-hover"
        >
          &larr; Back to the claim map
        </Link>
        <Link
          to={`/resumes/${data.id}/audit`}
          className="text-sm font-medium text-brand hover:text-brand-hover"
        >
          How this read was made &rarr;
        </Link>
      </div>
    </>
  );
}

/**
 * A grant, and what a named viewer would actually see.
 *
 * The two are on one panel because they answer each other. "I shared this with
 * the placement cell" and "what does the placement cell see?" are the same
 * question asked twice, and separating them is how a student ends up sure they
 * revoked something they did not.
 */
function ShareControls({ resumeId, candidateId }: { resumeId: string; candidateId: string }) {
  const [grantee, setGrantee] = useState("");
  const [days, setDays] = useState("90");
  const [viewer, setViewer] = useState("");

  const share = useShareResume(resumeId);
  const revoke = useRevokeShare(resumeId);
  // Falls back to the student themselves, which demonstrates `self_access`
  // rather than showing an empty panel on a page nobody has typed into yet.
  const disclosure = useDisclosure(resumeId, viewer.trim() || candidateId);

  return (
    <Section label="Sharing">
      <Panel className="px-4 py-3.5">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const name = grantee.trim();
            if (!name) return;
            const parsed = Number.parseInt(days, 10);
            share.mutate(
              { grantee: name, days: Number.isFinite(parsed) ? parsed : null },
              { onSuccess: () => setGrantee("") },
            );
          }}
        >
          <div className="w-56">
            <TextField
              label="Let someone see your claims"
              placeholder="placement-cell"
              value={grantee}
              onChange={(event) => setGrantee(event.target.value)}
            />
          </div>
          <div className="w-28">
            <TextField
              label="For how long"
              type="number"
              min={1}
              value={days}
              onChange={(event) => setDays(event.target.value)}
            />
          </div>
          <Btn type="submit" variant="secondary" disabled={share.isPending || !grantee.trim()}>
            {share.isPending ? "Granting…" : "Grant"}
          </Btn>
        </form>

        {share.data && (
          <p className="mt-2.5 text-sm text-confirmed">
            {share.data.grantee} can see your claims
            {share.data.expires_at
              ? ` until ${new Date(share.data.expires_at).toLocaleDateString()}`
              : " with no expiry"}
            .
          </p>
        )}
        {share.isError && (
          <div className="mt-2.5">
            <ErrorNote>That grant did not save. Nothing has been shared.</ErrorNote>
          </div>
        )}

        <p className="mt-2.5 text-xs text-ink-faint">
          A grant is to somebody named, it expires, and withdrawing it leaves a record rather than
          removing the row &mdash; if you shared something and changed your mind, you are entitled
          to see that you changed your mind.
        </p>
      </Panel>

      <Panel tone="sunken" className="mt-3 px-4 py-3.5">
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-56">
            <TextField
              label="What would someone see?"
              placeholder={`${candidateId.slice(0, 8)} (you)`}
              value={viewer}
              onChange={(event) => setViewer(event.target.value)}
            />
          </div>
          <Btn
            type="button"
            variant="ghost"
            disabled={revoke.isPending || !viewer.trim()}
            onClick={() => revoke.mutate(viewer.trim())}
          >
            {revoke.isPending ? "Withdrawing…" : "Withdraw their access"}
          </Btn>
        </div>

        {revoke.data && (
          <p className="mt-2.5 text-sm text-ink-soft">
            {revoke.data.revoked > 0
              ? `Withdrawn. ${revoke.data.grantee} can no longer see your claims, and the withdrawal is on the record.`
              : `${revoke.data.grantee} had nothing to withdraw — they were never granted access.`}
          </p>
        )}

        {disclosure.isLoading && (
          <div className="mt-3">
            <SkeletonRows rows={3} />
          </div>
        )}

        {disclosure.data && (
          <div className="mt-3">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={DISCLOSURE_COPY[disclosure.data.disclosure].tone}>
                {DISCLOSURE_COPY[disclosure.data.disclosure].label}
              </Pill>
              <span className="provenance">
                as {disclosure.data.viewer.slice(0, 12)}
                {disclosure.data.viewer.length > 12 ? "…" : ""}
              </span>
            </div>
            <p className="mt-1.5 text-sm text-ink-soft">
              {DISCLOSURE_COPY[disclosure.data.disclosure].meaning}
            </p>

            <Rows>
              <Field label="stored since">
                {new Date(disclosure.data.retention.created_on).toLocaleDateString()}
              </Field>
              <Field label="kept until">
                {new Date(disclosure.data.retention.expires_on).toLocaleDateString()}
                {disclosure.data.retention.expired && " · past due"}
              </Field>
              <Field label="policy">{disclosure.data.retention.rationale}</Field>
              <Field label="on expiry">
                {disclosure.data.retention.expiry_is_a_tombstone
                  ? "marked deleted, never silently vanished"
                  : "removed"}
              </Field>
            </Rows>

            {!disclosure.data.retention.decided && (
              <p className="mt-2 text-xs text-reported">
                This retention period is a proposal awaiting an ethics-committee sign-off, not a
                settled policy. It is the one in force in the meantime, and it is shown rather than
                assumed so that the sign-off changes a number here rather than a surprise later.
              </p>
            )}

            <p className="mt-2 text-xs text-ink-faint">
              There is no login on this platform yet, so this answers the question rather than
              enforcing it &mdash; it is what an authenticated viewer <em>would</em> be allowed.
              Saying that plainly is better than a padlock that is not attached to anything.
            </p>
          </div>
        )}
      </Panel>
    </Section>
  );
}

/**
 * Deletion, and what survives it.
 *
 * The correction log is kept, and this says so before the button rather than
 * after. It holds no document text, it is keyed to the content digest rather
 * than the row, and it is the evidence behind whether the parser is improving
 * — but "we deleted it except for the part we kept" is only acceptable if
 * nobody has to find that out afterwards.
 */
function DangerZone({
  resumeId,
  filename,
  onDeleted,
}: {
  resumeId: string;
  filename: string | null;
  onDeleted: () => void;
}) {
  const [armed, setArmed] = useState(false);
  const remove = useDeleteResume();

  return (
    <Section label="Deleting this resume">
      <Panel className="border-contested-line px-4 py-3.5">
        <p className="text-sm text-ink">
          Deletes {filename ?? "this pasted text"}, its claims, the stored file and your contact
          block. It cannot be undone and it takes effect immediately.
        </p>
        <p className="mt-1.5 text-sm text-ink-soft">
          Your correction log stays. It records that you disagreed with the parser and how, holds
          none of your document, and is what tells us the parser is getting better rather than
          worse. Nothing in it identifies the resume you just removed.
        </p>

        {remove.isError && (
          <div className="mt-2.5">
            <ErrorNote>That did not delete. The resume is still stored.</ErrorNote>
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {!armed ? (
            <Btn type="button" variant="secondary" onClick={() => setArmed(true)}>
              Delete this resume
            </Btn>
          ) : (
            <>
              <Btn
                type="button"
                variant="primary"
                disabled={remove.isPending}
                onClick={() => remove.mutate(resumeId, { onSuccess: onDeleted })}
              >
                {remove.isPending ? "Deleting…" : "Yes — delete it"}
              </Btn>
              <Btn type="button" variant="ghost" onClick={() => setArmed(false)}>
                Keep it
              </Btn>
            </>
          )}
        </div>
      </Panel>
    </Section>
  );
}

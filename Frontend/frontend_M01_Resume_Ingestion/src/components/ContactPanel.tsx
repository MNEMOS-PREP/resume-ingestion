/**
 * The contact block, released on purpose (FR-1.17).
 *
 * Spec: plan_in_depth/M01_Resume_Ingestion.md §6.7, FR-1.17, §15 decision 4
 *
 * ── Why this is a button and not a field ────────────────────────────────────
 *
 * Everything else about a resume arrives with the resume. The contact block
 * does not: it lives in its own table, it is decrypted by exactly one route,
 * and that route carries its own audit tag so *"who saw this student's phone
 * number"* is answerable from an access log.
 *
 * A panel that fetched it on mount would make the log read "everyone who
 * opened the page", which answers nothing. So the request happens when
 * somebody asks for it, the screen says that it is being recorded, and the
 * answer is not cached — the next reveal is a new access and is recorded as
 * one.
 *
 * ── What is shown before the reveal ─────────────────────────────────────────
 *
 * The shape, not the values. "2 email addresses, 1 phone number" tells an
 * operator whether the parse found the contact block at all — the thing they
 * actually need nine times in ten — without releasing anything.
 */

import { useState } from "react";

import { useResumeContact } from "../api";
import { Btn, ErrorNote, Field, Panel, Rows, Section, SkeletonRows } from "../ui/primitives";
import type { Resume } from "../types";

export function ContactPanel({ resume }: { resume: Resume }) {
  const [revealed, setRevealed] = useState(false);
  const contact = useResumeContact(resume.id, revealed);

  return (
    <Section
      label="Contact details"
      meta={revealed ? "released · recorded" : "held back"}
      action={
        revealed ? (
          <Btn type="button" variant="ghost" size="sm" onClick={() => setRevealed(false)}>
            Hide again
          </Btn>
        ) : (
          <Btn type="button" variant="secondary" size="sm" onClick={() => setRevealed(true)}>
            Show contact details
          </Btn>
        )
      }
    >
      <Panel tone="sunken" className="px-4 py-3">
        {!revealed && (
          <>
            <p className="text-sm text-ink-soft">
              Your email, phone number and links are stored apart from the rest of the resume and
              are masked everywhere else on this site &mdash; including in the document panel,
              where they show as &block;.
            </p>
            <p className="mt-2 text-xs text-ink-faint">
              Showing them is a separate request that is recorded against this resume, so it stays
              possible to answer who has seen them. Nothing here is sent anywhere by displaying it.
            </p>
          </>
        )}

        {revealed && contact.isLoading && <SkeletonRows rows={3} />}

        {revealed && contact.isError && (
          <ErrorNote>
            No contact block was stored for this resume. That is the normal answer for pasted text
            with no email address in it &mdash; not a failure.
          </ErrorNote>
        )}

        {revealed && contact.data && (
          <>
            <Rows>
              <Field label="email">{join(contact.data.emails)}</Field>
              <Field label="phone">{join(contact.data.phones)}</Field>
              <Field label="links">{join(contact.data.links)}</Field>
            </Rows>
            <p className="mt-2.5 text-xs text-ink-faint">
              Read at {new Date().toLocaleTimeString()} from the one route that releases this. It
              is not held in memory afterwards, so closing this panel and opening it again is a
              second access and is recorded as one.
            </p>
          </>
        )}
      </Panel>
    </Section>
  );
}

/** An empty list is an answer — "we found none" — and reads as one. */
function join(values: string[]): string {
  return values.length > 0 ? values.join(" · ") : "none found";
}

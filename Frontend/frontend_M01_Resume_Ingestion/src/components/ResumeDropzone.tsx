/**
 * Screen 1 — "Let's start with your resume" (§2.3, FR-1.1, FR-1.14).
 *
 * ── Three decisions this file is built around ───────────────────────────────
 *
 * **1. "We don't score your formatting" is on the screen.**  §2.3: it kills the
 * ATS-anxiety association in one line. Divya — tier-2 college, resume from a
 * YouTube template — relaxes. There is no ATS score anywhere in this module and
 * §15 decision 1 recommends there never is one.
 *
 * **2. Skip is a first-class button, not a grey link.**  FR-1.14 is a P0: a
 * student without a resume must not be blocked from ever trying the product.
 * A greyed-out link is a blocked path with extra steps.
 *
 * **3. No mention of AI.**  §2.3, verbatim: *"It's a file upload; saying
 * 'AI-powered resume parsing' adds nothing and raises expectations."*
 *
 * ── Why the upload control asks first ───────────────────────────────────────
 *
 * `GET /v1/capabilities` says what this deployment can actually read. A
 * dropzone that accepts a PDF on a server with no PDF library is a control that
 * looks live and does nothing, and §2.4 lists exactly that as a quit trigger.
 * When PDF is unavailable the control is absent and named, never disabled.
 */

import { useRef, useState } from "react";

import { IntakeError } from "../api";
import { Btn, Panel, TextArea } from "../ui/primitives";
import type { Capabilities } from "../types";

const SAMPLE = `PRIYA SHARMA
priya.sharma@example.com | +91 98765 43210 | github.com/priyash

EDUCATION
Amrita Vishwa Vidyapeetham, B.Tech CSE, 2022 - 2026, CGPA 8.1

EXPERIENCE
- Software Engineer Intern, Jun 2025 - Aug 2025. Led a team to ship internal tooling.

PROJECTS
- Built a route planner in Python using dynamic programming; cut average
  query time from 380ms to 45ms on a 12k-node graph.
- Worked on a world-class seamless blockchain platform.

SKILLS
Python, Java, SQL, Docker, Kubernetes, React`;

const ACCEPTED_LABEL: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
};

export function ResumeDropzone({
  capabilities,
  busy,
  error,
  onFile,
  onText,
  onSkip,
}: {
  capabilities: Capabilities | undefined;
  busy: boolean;
  error: unknown;
  onFile: (file: File) => void;
  onText: (text: string) => void;
  onSkip: () => void;
}) {
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [pasting, setPasting] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const uploadable = Object.entries(capabilities?.accepts ?? {})
    .filter(([mime, ok]) => ok && mime !== "text/plain")
    .map(([mime]) => mime);
  const canUpload = uploadable.length > 0;
  const megabytes = Math.round((capabilities?.max_bytes ?? 10 * 1024 * 1024) / (1024 * 1024));

  function choose(files: FileList | null) {
    const file = files?.[0];
    if (file && !busy) onFile(file);
  }

  return (
    <div className="space-y-4">
      {canUpload && !pasting && (
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            choose(event.dataTransfer.files);
          }}
          className={[
            "rounded-panel border-2 border-dashed px-6 py-10 text-center transition-colors",
            dragging ? "border-brand bg-brand-soft" : "border-line-strong bg-surface",
          ].join(" ")}
        >
          <input
            ref={input}
            type="file"
            className="sr-only"
            accept={uploadable.join(",")}
            onChange={(event) => choose(event.target.files)}
          />
          <p className="text-sm font-medium text-ink">
            {busy ? "Reading it…" : "Drop your resume here"}
          </p>
          <p className="mt-1 text-sm text-ink-soft">
            or{" "}
            <button
              type="button"
              onClick={() => input.current?.click()}
              disabled={busy}
              className="font-medium text-brand underline underline-offset-2 hover:text-brand-hover disabled:opacity-50"
            >
              click to browse
            </button>
          </p>
          <p className="mt-3 text-xs text-ink-faint">
            {uploadable.map((mime) => ACCEPTED_LABEL[mime] ?? mime).join(" or ")} &middot; up to{" "}
            {megabytes} MB &middot; first {capabilities?.max_pages ?? 6} pages
          </p>
        </div>
      )}

      {!canUpload && capabilities && (
        <Panel tone="sunken" className="px-4 py-3">
          <p className="text-sm text-ink">File upload is not available on this server.</p>
          <p className="mt-1 text-sm text-ink-soft">
            Paste your resume text below instead &mdash; that path works everywhere and reads
            exactly the same way.
          </p>
        </Panel>
      )}

      {/* §10: the always-works fallback, and it is never hidden behind a
          failure. A student who would rather paste can always paste. */}
      {(pasting || !canUpload) && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (text.trim() && !busy) onText(text);
          }}
          className="space-y-3"
        >
          <TextArea
            label="Resume text"
            hint="Copy straight out of your PDF. Layout does not matter here."
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={14}
            placeholder={SAMPLE}
          />
          <div className="flex flex-wrap items-center gap-3">
            <Btn type="submit" variant="primary" disabled={!text.trim() || busy}>
              {busy ? "Reading it…" : "Read my resume"}
            </Btn>
            <Btn type="button" variant="ghost" size="sm" onClick={() => setText(SAMPLE)}>
              Use a sample resume
            </Btn>
            {canUpload && (
              <Btn type="button" variant="ghost" size="sm" onClick={() => setPasting(false)}>
                Upload a file instead
              </Btn>
            )}
          </div>
        </form>
      )}

      {canUpload && !pasting && (
        <p className="text-center text-sm text-ink-soft">
          <button
            type="button"
            onClick={() => setPasting(true)}
            className="font-medium text-brand hover:text-brand-hover"
          >
            Paste the text instead
          </button>
        </p>
      )}

      {error != null && <IntakeFailure error={error} onPaste={() => setPasting(true)} />}

      <p className="text-sm text-ink-soft">
        We read it to ask you questions about your own work. We don&rsquo;t score your formatting.
      </p>

      {/* FR-1.14, and it is a button because the requirement is a P0. A
          student with no resume must not be blocked from trying the product. */}
      <div className="border-t border-line pt-4">
        <Btn type="button" variant="secondary" onClick={onSkip}>
          Skip for now &mdash; I&rsquo;ll practise without it
        </Btn>
        <p className="mt-1.5 text-xs text-ink-faint">
          Everything except the resume-specific questions works without one, and you can add it
          later.
        </p>
      </div>
    </div>
  );
}

/**
 * A refused upload, said in words with a way forward (§2.4, §10).
 *
 * *"Upload fails, no explanation"* is the first quit trigger in the table. The
 * backend answers with a named code and a student-facing sentence precisely so
 * this component never has to render a status number.
 */
function IntakeFailure({ error, onPaste }: { error: unknown; onPaste: () => void }) {
  const message =
    error instanceof IntakeError
      ? error.detail.message
      : error instanceof Error
        ? error.message
        : "Something went wrong reading that.";

  return (
    <div
      role="alert"
      className="rounded-md border border-contested-line bg-contested-soft px-3 py-2.5"
    >
      <p className="text-sm text-contested">{message}</p>
      <button
        type="button"
        onClick={onPaste}
        className="mt-1.5 text-sm font-medium text-brand hover:text-brand-hover"
      >
        Paste the text instead &rarr;
      </button>
    </div>
  );
}

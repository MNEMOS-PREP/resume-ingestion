"""Scoring the golden set (§12 "Golden set", AC-1.3, AC-1.4, AC-1.5).

    Section F1 and skill precision run in CI; a regression fails the build.

── What this measures, and what it does not ───────────────────────────────────

**Read this before quoting a number from it.**

The spec asks for *"30 resumes with hand-annotated sections, claims, and skills,
collected with consent from seniors"*. The set in `research/data/golden/resumes/`
is not that. It is hand-annotated, and it is **synthetic** — written to cover the
shapes the spec names, not sampled from the population students actually submit.
That difference matters in one direction specifically: the documents and the
parser were written by the same hand, so an F1 measured here is an optimistic
estimate of an F1 on real resumes, and no amount of adding fixtures fixes that.

So there are two jobs, and only one of them is being done today:

  **A regression gate — done.**  A change that makes segmentation worse fails
  the build. This works regardless of where the documents came from, because it
  compares the parser against a fixed annotation rather than against reality.

  **The acceptance measurement — not done.**  AC-1.3 ≥ 0.90, AC-1.4 ≥ 0.95 and
  AC-1.5 ≥ 0.85 are claims about real resumes. They stay *unmeasured* until real
  ones land. `MEASURES_REAL_WORLD` below is the flag that says so, and it is
  False; flipping it is a deliberate act that goes with replacing the corpus.

Stating that here rather than in a commit message is the point. A synthetic
golden set quietly relabelled as the acceptance evidence is exactly how a
project ends up believing it met a bar it never tested.

── The two metrics ────────────────────────────────────────────────────────────

**Section F1** is computed per LINE, micro-averaged over every labelled line in
the corpus. Each non-empty line has one true section kind and gets one predicted
kind, so precision and recall coincide and F1 is the agreement rate — which is
the honest thing to report for a single-label assignment. Span-overlap F1 would
score a parser that merged two adjacent sections higher than one that mislabelled
a single line, and merging is the more damaging error: it puts a project bullet
in the education section, where nothing will ever probe it.

**Skill precision and recall** are set-valued over surface forms, normalised
through `ai_core.concepts.normalise_alias` so `Node.js` and `node js` are one
thing. Precision is the one that matters more: an invented skill becomes an
interview question about something the student never claimed, while a missed one
is a gap the confirmation screen lets them fill in fifteen seconds.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ai_core.concepts import normalise_alias

from backend_M01_Resume_Ingestion import documents
from backend_M01_Resume_Ingestion.claims import segment

#: Flip this only when the corpus is real resumes collected with consent. See
#: the module docstring: it is the difference between a regression gate and an
#: acceptance measurement, and the two must not be confused.
MEASURES_REAL_WORLD = False

GOLDEN_ROOT = Path(__file__).resolve().parents[2] / "research" / "data" / "golden" / "resumes"

#: The spec's targets. Enforced as a REGRESSION floor today (see above), which
#: is why the gate test names them as such rather than as AC-1.3/1.4/1.5 met.
TARGET_SECTION_F1 = 0.90
TARGET_SKILL_PRECISION = 0.95
TARGET_SKILL_RECALL = 0.85


@dataclass
class GoldenResume:
    """One annotated document."""

    id: str
    note: str
    text: str
    #: Section kind for every non-empty line, by line index.
    line_kinds: dict[int, str]
    skills: list[str]
    source: str

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


def load(root: Path | None = None) -> list[GoldenResume]:
    """Every annotated resume in the corpus.

    Annotations name their sections by HEADING TEXT rather than by line number:

        "sections": [["EDUCATION", "education"], ["SKILLS", "skills"]]

    Line numbers in a hand-written fixture go stale the moment somebody adds a
    line, and they go stale silently — the file still parses, the labels just
    slide by one and the F1 drops for a reason nobody can find. Heading text
    either matches or raises.
    """
    root = root or GOLDEN_ROOT
    out: list[GoldenResume] = []

    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload["resumes"]:
            lines = entry["text"]
            out.append(
                GoldenResume(
                    id=entry["id"],
                    note=entry.get("note", ""),
                    text="\n".join(lines),
                    line_kinds=_expand(entry, lines, path.name),
                    skills=list(entry.get("skills", [])),
                    source=path.name,
                )
            )
    return out


def _expand(entry: dict, lines: list[str], filename: str) -> dict[int, str]:
    """Heading-anchored annotations to a kind for every non-empty line."""
    starts: list[tuple[int, str]] = []
    cursor = 0
    for heading, kind in entry.get("sections", []):
        try:
            index = next(
                i for i in range(cursor, len(lines)) if lines[i].strip() == heading.strip()
            )
        except StopIteration:
            raise AssertionError(
                f"{filename}:{entry['id']} annotates a section headed {heading!r}, "
                "which is not a line in the document."
            ) from None
        starts.append((index, kind))
        cursor = index + 1

    kinds: dict[int, str] = {}
    preamble = entry.get("preamble", "contact")
    first = starts[0][0] if starts else len(lines)
    for index in range(first):
        if lines[index].strip():
            kinds[index] = preamble

    for position, (index, kind) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        for line in range(index, end):
            if lines[line].strip():
                kinds[line] = kind

    return kinds


# ---------------------------------------------------------------------------
#  Scoring
# ---------------------------------------------------------------------------


@dataclass
class Score:
    """One corpus-wide result, plus every disagreement behind it.

    The disagreements are kept because a bare F1 tells you a build failed and
    nothing about why. `report()` prints them, which is the difference between
    a red CI run and a fifteen-minute fix.
    """

    section_hits: int = 0
    section_total: int = 0
    skill_true_positives: int = 0
    skill_predicted: int = 0
    skill_expected: int = 0
    section_misses: list[tuple[str, str, str, str]] = field(default_factory=list)
    skill_invented: list[tuple[str, str]] = field(default_factory=list)
    skill_missed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def section_f1(self) -> float:
        """Per-line agreement. Precision and recall coincide — see the docstring."""
        return self.section_hits / self.section_total if self.section_total else 0.0

    @property
    def skill_precision(self) -> float:
        return self.skill_true_positives / self.skill_predicted if self.skill_predicted else 1.0

    @property
    def skill_recall(self) -> float:
        return self.skill_true_positives / self.skill_expected if self.skill_expected else 1.0

    def report(self) -> str:
        lines = [
            f"section F1        {self.section_f1:.3f}  "
            f"({self.section_hits}/{self.section_total} lines)  target {TARGET_SECTION_F1}",
            f"skill precision   {self.skill_precision:.3f}  "
            f"({self.skill_true_positives}/{self.skill_predicted})  "
            f"target {TARGET_SKILL_PRECISION}",
            f"skill recall      {self.skill_recall:.3f}  "
            f"({self.skill_true_positives}/{self.skill_expected})  "
            f"target {TARGET_SKILL_RECALL}",
        ]
        if self.section_misses:
            lines.append("")
            lines.append("mislabelled lines:")
            for resume_id, line, expected, got in self.section_misses[:25]:
                lines.append(f"  {resume_id:26s} {expected:>14s} -> {got:<14s} {line[:44]!r}")
        if self.skill_invented:
            lines.append("")
            lines.append("skills found that are not on the resume (precision):")
            for resume_id, skill in self.skill_invented[:25]:
                lines.append(f"  {resume_id:26s} {skill}")
        if self.skill_missed:
            lines.append("")
            lines.append("skills on the resume that were not found (recall):")
            for resume_id, skill in self.skill_missed[:25]:
                lines.append(f"  {resume_id:26s} {skill}")
        if not MEASURES_REAL_WORLD:
            lines.append("")
            lines.append(
                "NOTE: this corpus is synthetic. These numbers are a regression floor, "
                "not the AC-1.3/1.4/1.5 acceptance measurement — see golden.py."
            )
        return "\n".join(lines)


def score_sections(resume: GoldenResume, score: Score) -> None:
    """Predicted kind for every annotated line, against the annotation."""
    artifact = uuid.uuid4()
    predicted = segment(resume.text, artifact, geometry=documents.from_text(resume.text))

    lines = resume.lines
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1

    for index, expected in sorted(resume.line_kinds.items()):
        offset = offsets[index]
        got = next(
            (s.kind for s in predicted if s.span.start <= offset < s.span.end),
            "unknown",
        )
        score.section_total += 1
        if got == expected:
            score.section_hits += 1
        else:
            score.section_misses.append((resume.id, lines[index], expected, got))


def score_skills(resume: GoldenResume, found: list[str], score: Score) -> None:
    """Surface forms found against surface forms annotated."""
    expected = {normalise_alias(s): s for s in resume.skills}
    predicted = {normalise_alias(s): s for s in found}

    score.skill_expected += len(expected)
    score.skill_predicted += len(predicted)
    score.skill_true_positives += len(expected.keys() & predicted.keys())

    for key in predicted.keys() - expected.keys():
        score.skill_invented.append((resume.id, predicted[key]))
    for key in expected.keys() - predicted.keys():
        score.skill_missed.append((resume.id, expected[key]))

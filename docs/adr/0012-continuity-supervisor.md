# ADR 0012: A continuity supervisor driven by rubrics as code

- **Status:** Accepted
- **Date:** 2026-10-29
- **Deciders:** Isaac Tumuti

## Context

Reference sheets keep characters consistent ([ADR 0004](0004-cast-approval.md)), but not every time. Two real failures from the lighthouse story:
- Pip's reference sheet came back wearing a green sweater that belonged to Ada.
- Pip was drawn in a blue vest that is not on his sheet.

A creator spots these only by checking every panel against every sheet. That is the manual work Frameteller is meant to remove.

## Decision

- **Rubrics are files.** `agents/` holds one versioned markdown rubric per pipeline step:
  - `cast.md` checks a reference sheet against its description.
  - `panel-continuity.md` checks a panel against the reference sheets.
  - `shot.md` checks a panel against its shot.
  - `edit.md` checks an edit against its request.

  Each rule has a stable id (`CONT-04`), a severity (blocker, major or minor) and a one-line test. The files are read at runtime (`FileRubricLibrary`). The first 12 hex characters of each file's SHA-256 are recorded with every verdict, so a decision can be traced to the exact text that produced it. Editing a rubric is a reviewed commit, not a code change.
- **One port.** `ReviewerPort.review(ReviewRequest) -> Verdict`. A `Verdict` has these fields:
  - `decision`: pass, fix or ask.
  - `confidence`.
  - `issues`: each issue has a rule id, a severity and a description.
  - The fix: an instruction, a target and its parts.
  - `model` and `latency_ms`.
  - The rubric hashes.

  The model names the rule it saw broken; the rubric decides how serious that is. Output uses a strict JSON schema whose `rule_id` is an enum of the rubric's own ids.
- **Policy** (`SupervisePanel`, after every draft and final render, as a background job):
  - No blocker or major issue: the panel is **Checked**.
  - A fixable issue on a draft, with confidence ≥ 0.6, triggers one `EditPanelAppearance` with the reviewer's instruction, then a re-review against the rubrics plus `edit.md`. There are at most **2** fixes per render, each charged to the project budget. When the issue clears, the panel is **Fixed**.
  - Anything else is **Needs your eye**: a final render, low confidence, an issue an edit cannot repair, the fixes ran out, or the budget ran out. The user picks "Apply suggested fix", "Accept anyway" or "Redraw".
  - **Finals are never changed automatically.** A high-reasoning render is what the user asked for, so the supervisor only reports on it.
- **Sheets are reviewed, never auto-fixed** (`ReviewSheet`). Issues show on the sheet in the cast tray before approval. "Apply fix" redraws the sheet with the reviewer's correction appended to the prompt.
- **It never blocks drawing.**
  - Reviews are their own jobs, keyed on the panel revision or the sheet.
  - A review of a render that was replaced meanwhile is dropped.
  - No budget for a review means no review, not a failed render.
  - "Continuity checks" is a project setting, on by default.
- **It explains itself.** Every decision goes into `project.supervisor_log` (the last 100) and is sent as `supervisor.reviewed`, `supervisor.fixed` or `supervisor.needs_user` ([api-events](../api-events.md)), e.g. "Shot 4: remove the blue vest (CONT-04, Pip wears a blue vest that is not on his reference sheet). Fixed in 1 try."

## Consequences

- Each review costs a model call. The budget reserves USD 0.006 per review, at Spark's price, whichever model serves it. A storyboard of 6 panels with a few fixes stays well under USD 0.10 of reviews.
- A reviewer can be wrong both ways, so the policy limits the damage:
  - A false fix costs one draft edit, and the re-review catches a fix that made things worse.
  - A missed issue is still visible to the user.

  [supervisor-eval.md](../supervisor-eval.md) measures both rates.
- The rubric text is the interface between the product and the model. Changing it changes behaviour without a deploy of code, but the backend image must ship `agents/` (`RUBRICS_DIR`).

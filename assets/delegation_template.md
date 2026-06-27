# Standard Delegation Template for AI Agents

> Use this template every time you delegate to a new agent — it lets the agent know **what to read, what not to touch, where to output, where to log issues** on cold start.
> Far more effective than ad-hoc phrasing, battle-verified.

---

## Standard Format (copy & fill, replace [] with your project info)

```text
Start by reading AGENTS.md (including STATUS.md for current state and blockers).
This task only handles [phase X / task TY].
Don't modify: [raw data paths / existing core code paths / ...]
Output to: [specified output path].
If you find issues or new questions, log them in [specified doc, e.g., docs/known_issues.md], don't fix silently.
Known pitfalls for this task: [list known risk points]
Pre-delivery self-check: [conservation/bounds/count/magnitude/units…, check off one by one]
```

### Field Guide

| Field | Purpose | Don't write | Do write |
|---|---|---|---|
| **Known pitfalls** | Tell the agent about risks you (the orchestrator) already know, so it can avoid them | Leave blank | `Dataset X has 1691 rows with conservation偏差 >1; g/kg and Mg/ha units mixed, need conversion` |
| **Pre-delivery self-check** | Checks the agent must run before reporting completion | Leave blank | `① Raster rows/cols match expected; ② Output sum ≈ input sum (偏差 <0.5%); ③ All units in Mg/ha; ④ No out-of-bounds or uncleaned edge pixels` |

> **Why these two fields matter**: We've verified in practice — the same agent with a "self-check" prompt has **dramatically lower defect rates** than without. Agents aren't irresponsible; they just don't know which error types you care about. Spell out the checks explicitly and agents will self-intercept before reporting done.

## Real Example (with pitfalls + self-check)

```text
# Delegation: Phase 3 — Python faithful migration
Start by reading AGENTS.md (including STATUS.md for current state and blockers).
This task only handles Phase 3: Python faithful migration.
Don't modify: data/ (raw input) and references/ (original reference materials).
Output to: outputs/python_legacy/ and reports/.
If you find algorithmic concerns, log them in docs/known_issues.md, don't fix existing logic silently.
If blocked, update STATUS.md and append "[BLOCKED]" at the end.
Known pitfalls: (1) Algorithm diverges near boundaries — add divergence protection; (2) Input data has NA in some fields — migrated version must handle NA compatibly.
Pre-delivery self-check: (1) Migrated output vs original R output 偏差 < 0.1%; (2) No divergence on boundary 100 rows; (3) NA compatibility logic passes; (4) scripts/README.md has been updated.
```

## Why This Template Beats Ad-Hoc Phrasing

| Ad-hoc phrasing | This template |
|---|---|
| "Help me write a script to process the data" | Agent knows the full pipeline context — won't touch read-only data, won't overwrite others' outputs, won't dump in wrong dir, won't fix issues silently |
| User has to correct the agent after it steps in it | One-shot — agent knows boundaries, output location, and issue reporting channel from the start |

## Advanced: Delegating Multiple Agents

Append a mutual-exclusion statement:

```text
Start by reading AGENTS.md (including STATUS.md for current state).
This task only handles [your task]. No conflict with [another agent's task].
If you find crossover that needs coordination, log it in STATUS.md with "[CROSS-AGENT COORDINATION]" tag.
```

## Advanced: Tasks Requiring Independent Review

For critical tasks whose output affects paper conclusions or downstream pipelines, append:

```text
Schedule independent review after delivery: the orchestrator or another agent will spot-check key numbers (conservation/bounds/count/magnitude/consistency).
Before independent review passes, this output is considered "PENDING REVIEW" — no downstream agent may use it.
```

## Shutdown Steps (Mandatory — skip breaks the handoff chain)

When done, regardless of outcome, execute the following shutdown actions (append to your delegation template):

```text
When done, you MUST:
1. Update AGENTS.md §3 (cumulative snapshot with date) + §4 task board status
2. Write STATUS.md (incremental: what this round did / files touched / pitfalls hit)
3. If new scripts were added, update scripts/README.md
4. Shutdown self-check: python scripts/check_handoff.py (all pass = handoff qualified)
5. If new data was added, update the dataset's source.txt
```

---

> 💡 Copy this to your project's `docs/` directory. Every time you delegate, just copy-paste and fill — no need to rephrase each time.

> 💡 Copy this to your project's `docs/` directory. Every time you delegate, just copy-paste and fill — no need to rephrase each time.
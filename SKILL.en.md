---
name: multi-agent-project
description: Initialize or reconstruct a "cross-agent, cross-tool resumable" project documentation skeleton. Trigger when a user starts a new project/topic, wants to establish a multi-agent collaboration workflow, mentions AGENTS.md / CLAUDE.md / GEMINI.md / .cursorrules / copilot-instructions / project memory / agent handoff / switching tools / context loss, or has an existing project where every agent asks the same questions repeatedly, overwrites each other, or can't pick up where the previous one left off. Also triggered by vague requests like "help me set up project docs", "how to make multiple AI tools collaborate", "prepare a new research topic".
---

# Multi-Agent Project Skeleton (Cross-Tool Resumable)

## One-Line Install (execute when user says "install this skill")

Source repo: `https://github.com/aduhappy/multi-agent-project-skill`. Clone into the tool's skills directory — no other dependencies.

**Different tools have different skills directories. Choose the correct path**:

| Tool | User-level skills directory | Project-level skills directory |
|---|---|---|
| **ZCode / Codex CLI** | `~/.agents/skills/` | `<project>/.agents/skills/` |
| **Claude Code** | `~/.claude/skills/` | `<project>/.claude/skills/` |
| **Cursor** | N/A (use rules) | `.cursor/rules/` (modern) or `.cursorrules` (legacy) |

General rules:
- On Windows, `~` = `%USERPROFILE%`.
- When unsure between user-level vs project-level, default to **user-level** (install once, use everywhere).
- Create the directory first if it doesn't exist, then clone.
- After cloning, tell the user to **start a new session** to trigger this skill.

## What This Skill Does

Generates a **tool-agnostic pure Markdown collaboration skeleton** in the project root — one authoritative entry point + thin pointers + self-contained task cards + shutdown conventions. Switch between Claude / Cursor / Gemini / ZCode / Codex / Copilot — any agent that enters reads the same entry point and picks up where the last one left off. No context loss, no overwriting.

Four core principles:
1. **Single source of truth**: AGENTS.md is the only authoritative entry point; all other tool config files (CLAUDE.md / GEMINI.md / .cursorrules / copilot-instructions.md) are 3-line thin pointers that redirect to AGENTS.md.
2. **Details externalized, entry point kept short**: AGENTS.md fits in 1–2 screens so every new agent reads it. Details live in `docs/` sub-documents; the entry only has pointers.
3. **Pure Markdown + relative paths**: No tool-specific syntax. Switching tools doesn't break anything.
4. **Trust but verify**: Agent self-checks are not enough — critical outputs must be independently spot-checked by the orchestrator or another agent (conservation/bounds/cell count/magnitude/consistency) before the next handoff. This is the foundation of a trustworthy multi-agent pipeline.

## When to Trigger

- User says "new project / new topic", "how to organize docs for AI collaboration", "how to write AGENTS.md".
- "Multiple agent handoff", "switch tools", "context loss".
- Existing project where agents keep asking the same questions, can't find status, overwrite each other's outputs.
- "Help me set up project docs", "how to make multiple AI tools collaborate".

## How to Use (Two Modes)

### Mode A: Generate Skeleton from Scratch

1. Ask (all at once, don't drip-feed): project root, one-sentence goal, which AI tools to support, whether it's in a cloud-sync directory, what data sources are involved.
2. **Then ask for hard constraints**: "List the dimensions in this domain that **must never be conflated** (measurement method, units, coordinate system, resolution, time period, age stratification, etc.). Write these as hard rules that all subsequent agents must follow." — This is the most commonly overlooked iron rule, and getting it wrong breaks everything downstream.
3. Copy `assets/AGENTS.md` to the project root and fill in user-provided info.
   - **Placeholder rule (important)**: Fill directly when the user gives explicit info. For info not provided, **prefer reasonable defaults** (inferred from the project topic) and briefly note "default, editable". Only leave `【TODO】` for **truly user-specific details that can't be reasonably inferred** (e.g., specific DOIs, passwords, account names). Criterion: the fewer `【TODO】` in AGENTS.md the better — ideally zero.
4. Copy corresponding thin-pointer files (CLAUDE.md, GEMINI.md, copilot-instructions.md, etc.) for the tools the user selected — all content is "see AGENTS.md". For Cursor users, recommend `.cursor/rules/multi-agent.mdc` (modern format), with `.cursorrules` as legacy fallback. **Don't generate files for unselected tools**.
5. Create `docs/task_plan_<topic>.md` (copy from `assets/task_plan_template.md`).
6. **Derive dataset directories**: Split by data source type — one directory per source (e.g., user says "MODIS + Landsat" → create `MODIS/` and `Landsat/`; user says "survey + field measurements" → create `survey/` and `field_measurements/`). Place `source.txt` (from `assets/source.txt`) in each dataset directory. Skip if the project has no clear data sources.
7. **Organize code**: Create `scripts/` directory + `scripts/README.md` (copy from `assets/scripts_README.md`). List any existing scripts the user has (if any), or leave empty for later agents to fill. Add the "scripts don't scatter in root" rule to AGENTS.md §5.
8. Create `STATUS.md` (copy from `assets/STATUS.md`) — empty template; the first agent fills it on completion.
9. Write the user's environment and constraints into §Iron Rules and §Path Conventions.
10. After completion, tell the user: what files were generated, which "defaults" need confirmation, which `【TODO】` need manual filling.

### Mode B: Diagnose Existing Project

#### B1: Fix a Messy Project (zero or chaotic documentation)
The user already has a project but collaboration is chaotic — agents ask the same questions repeatedly, overwrite each other, can't find status. First read existing README / any documentation / directory structure, compare against §File Skeleton and §AGENTS.md Sections to check what's missing. Provide a **complete remediation checklist** (missing thin pointers? missing entry point? non-self-contained task cards? no source.txt? no shutdown conventions?). Apply after user confirmation. **Read before modifying, never overwrite existing files**.

#### B2: Enhance a Good Project (good docs, missing thin pointers)
The user has well-established project documentation (e.g., AI_COLLABORATION_PLAN.md / README.md / detailed wiki) but AI tools won't read it automatically (Codex/Claude default to `AGENTS.md` and won't discover custom filenames). **Just add a `AGENTS.md` thin pointer** (3 lines) pointing to the existing doc; then add corresponding thin-pointer files (CLAUDE.md, etc.) for the tools the user selected. **Don't touch any existing docs**. Criterion: after adding, a new agent enters → reads AGENTS.md → jumps to existing docs → gets full context without the user having to say "first read XX file".

## File Skeleton (After Generation)

```
<project-root>/
├── AGENTS.md                          ← Single authoritative entry point (read by all tools by default)
├── STATUS.md                          ← Current handoff state (written on shutdown, first thing new agent reads)
├── CLAUDE.md                          ← Thin pointer → "see AGENTS.md"
├── GEMINI.md                          ← Thin pointer (optional)
├── .cursorrules                       ← Thin pointer (Cursor, optional)
├── .github/copilot-instructions.md    ← Thin pointer (Copilot, optional)
├── docs/
│   ├── task_plan_<topic>.md           ← Self-contained task card
│   ├── delegation_template.md         ← Standard delegation template (copy and fill, optional)
│   ├── decision_records/              ← Key technical decisions (ADR, optional, see advanced.md)
│   └── glossary.md                    ← Project terminology (optional)
├── <dataset_name>/                    ← One directory per dataset
│   ├── source.txt                     ← DOI/URL/date/method/units
│   └── ...
├── scripts/                           ← Code organized (recommended: no scripts in root)
│   └── README.md                      ← One-liner per script: purpose/input/output/author
└── progress_log.md                    ← Dated change log (optional)
```

## AGENTS.md Sections (In Priority Order)

Follow the `assets/AGENTS.md` template. 8 sections total (template numbered 1–7, with path conventions as §5.5 — too important to bury in iron rules):

1. **North Star (one sentence)** — What this project does, who it's for, the tone (target journal/audience, don't derail the main line).
2. **Current Story / Method** — Latest direction + core method + recent changes and why.
3. **Where We Are Now** — Updated every shutdown, 1–5 items with **date stamps**. This is the most critical handoff point.
4. **Task Board** — `[ ]`/`[x]` + who owns it + dependencies (T1→T2, which are parallel) + known risks.
5. **Iron Rules / Conventions** — Things that cause rework if violated: environment calls, plotting/data rules, naming, methodology, shutdown conventions. Includes "**New agent (including sub-agents) first thing on entry: read AGENTS.md before doing anything**".
5.5. **Path Conventions** — Where big files go, where small outputs return (prevent multi-agent collisions, prevent cloud-sync explosions). **Separate section, don't bury in iron rules**.
6. **Deep-Read Pointers** — Where to find details (task specs, decision records, glossary).
7. **Environment / Tools** — How to invoke tools, env locks.

## Cross-Tool Resumability: 7 Hard Requirements

1. **Pure Markdown + relative paths + standard filenames** — No tool-specific syntax, no hardcoded absolute paths.
2. **Data has `source.txt`** (DOI/URL/download date/method/units/known issues) — Anyone switching agents can trace the origin.
3. **Shutdown conventions in iron rules** — Every agent updates §Where We Are Now + §Task Board + writes/updates `STATUS.md` (handoff file: current state/next steps/risks/key paths). Next agent picks up without relying on conversation history.
4. **Path discipline** — "Large files to work drive, small outputs back to repo" / "copy, don't move" / "don't touch paths another agent is actively using".
5. **New agent (including sub-agents) first thing on entry** — Read AGENTS.md (including STATUS.md) before doing anything. Don't rely on conversation history or memory guesses.
6. **Single source for key numbers, prevent drift** — Key numbers (means, percentages, areas, etc.) written in exactly one place (STATUS.md or AGENTS.md §3); everywhere else references but doesn't restate. Before shutdown, verify number consistency across all docs — a >1% difference for the same value across documents is a bug that must be fixed before handoff.
7. **Bad output retirement / isolation** — When an agent's output is found to be wrong (data, figures, numbers), immediately: ① rename directory/file with `_DEPRECATED` suffix or move to `_retired/`; ② annotate at top of AGENTS.md §3 with `> ⚠️ 【RETIRED】<path> <reason>` in red; ③ update §4 task board status to `[x]` + label "retired"; ④ update STATUS.md. **Never rely on memory saying "don't use that"** — downstream agents silently reusing bad outputs is more damaging than having no output.

## Core Workflow (Full Agent Handoff Lifecycle)

A typical multi-agent handoff lifecycle has 5 explicit steps. **Skipping step 3 "Independent Review" is the #1 root cause of pipeline contamination.**

```
① Delegate → ② Execute + Self-check → ③ Independent Review → ④ Accept & Merge → ⑤ Handoff Dump
```

### Step Details

**① Delegate (orchestrator → executing agent)**
Use the standard template (see below or `assets/delegation_template.md`) to specify: what to read, what to do, what not to touch, where to output, where to log issues.

**② Execute + Self-check (executing agent)**
Run the task, then go through the DoD (acceptance checklist). Confirm output is complete, format is correct, no errors.

**③ Independent Review (orchestrator or another agent spot-checks key numbers)**
**Don't trust self-checks** — an executing agent reporting "all checks passed" doesn't mean the output is actually correct (proven repeatedly in practice).
- The orchestrator or a third agent spot-checks key metrics: conservation (input sum ≈ output sum?), bounds (out-of-range or uncleaned edges?), counts (rows/pixels as expected?), magnitude (units off by 10³?), consistency (same number across multiple docs agrees?).
- Pass → proceed to step ④; Fail → return to executing agent for fix, and log an ADR.
- Criterion: **"Independent review passed" is the gate to the next step, not optional.**

**④ Accept & Merge**
Formally place verified output. Update `source.txt` (if new data) and `scripts/README.md` (if new script).

**⑤ Handoff Dump**
Update AGENTS.md §3 (current status) + §4 (task board) + write STATUS.md. Guarantee the next agent can resume using only repo markdown.

> 💡 Short pipelines (1–2 agents, simple outputs) may skip step ③. For outputs affecting paper conclusions or downstream pipelines, **all 5 steps are mandatory.**

## Two Layers of Resumability (Both Required)

- **Hard resumability (primary)**: Repo markdown — tool-agnostic, readable by any agent or human. This is the source of truth.
- **Soft resumability (enhancement)**: Memory layer (ChatMem / Cursor memory / Claude memory) accelerates retrieval, but never let core conclusions live only in memory — they must land in markdown.

> Criterion: Delete all memory layers. If the next agent can resume using only repo markdown → **pass**.

## Standard Delegation Template for AI Agents

Every time you delegate to a new agent, start with this uniform format — far more effective than ad-hoc phrasing. See `assets/delegation_template.md`:

```text
Start by reading AGENTS.md (including STATUS.md for current state and blockers).
This task only handles [phase X / task TY].
Don't modify: [raw data paths / existing core code paths / ...]
Output to: [specified output path].
If you find issues or new questions, log them in [specified doc, e.g., docs/known_issues.md], don't fix silently.
Known pitfalls for this task: [list known risk points]
Pre-delivery self-check: [conservation/bounds/count/magnitude/units…, check off one by one]
```

The template's core value: a new agent **immediately knows what to read, what not to touch, where to output, and where to log issues** on cold start. The "Known pitfalls" and "Self-check" fields are **battle-verified critical additions** — they guide agents to self-intercept common error types before reporting completion, dramatically reducing defect rates.

For critical tasks affecting paper conclusions or downstream pipelines, append the "Independent Review" instruction (see advanced example in the template).

## Advanced Sections (Enable on Demand, see references/advanced.md)

Beyond the 7 core sections, these are useful as the project grows. **Don't pile them all on at the start**:
- **ADR (Architecture Decision Records)** — Log "why method A was rejected" so the next agent doesn't re-debate settled decisions.
- **Glossary** — Project-specific terms/abbreviations so new agents don't guess.
- **Progress Log** — Dated change log, more granular than §Where We Are Now.
- **Concrete DoD (Definition of Done)** — Written as runnable check commands, not "it's done".
- **Standard Handoff Summary** — Current state / next steps / unresolved risks / key file paths.
- **Naming Conventions + Idempotency** — Output files with `_v1`/date/CRS; long-pipeline scripts idempotent (cache + skip).
- **Environment Lock** — `environment.yml` pins conda env, prevents drift on rebuild.
- **Data Snapshot / Immutable Input** — Raw data read-only with hash, everyone works on copies.
- **Filled AGENTS.md Example** — `references/example_filled_AGENTS.md`, a complete example with a fictional project. Much more intuitive than a blank template.

## Custom Reminders

- This skeleton comes from real research projects (multi-agent, multi-dataset, long pipeline, cloud-sync) in practice. Adapt to your domain: pure frontend projects can drop the work-drive path conventions; single-agent small-script projects can simplify the task board.
- Template placeholders use `【TODO】` — replace and delete.
- All thin-pointer files have the same content (see `assets/CLAUDE.md`). **Don't write different rules in each** — that breaks "single source of truth".
- Don't overwrite the user's existing AGENTS.md. For Mode B diagnosis, read before modifying, apply incremental patches only.

## References

The following projects provided key inspiration for this skill's design:

- [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) — Dual-license structure, README release standard, thin pointer (CLAUDE.md 9 bytes) approach
- [breezewish/CodexPotter](https://github.com/breezewish/CodexPotter) — Cross-session file memory (STATUS.md), new agent onboarding ritual, task delegation phrasing inspiration
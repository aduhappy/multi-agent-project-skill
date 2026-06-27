# Multi-Agent Project Skill

> Cross-agent, cross-tool resumable project skeleton generator. One authoritative entry point + thin pointers + self-contained task cards + shutdown conventions, all in pure Markdown. Switch between Claude / Cursor / Gemini / ZCode / Codex / Copilot — any agent that enters reads the same entry point and picks up where the last one left off.

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE-MIT)
[![License: CC BY-SA 4.0](https://img.shields.io/badge/Content-CC--BY--SA--4.0-green.svg)](LICENSE-CC-BY-SA-4.0)
[![agents.md](https://img.shields.io/badge/standard-agents.md-orange.svg)](https://agents.md/)

[🇨🇳 中文版](README.md)

---

## 🚀 Installation

### Option 1: Let Your Agent Install It (Recommended)

Just tell any AI agent (Claude / Cursor / Gemini / ZCode / Codex / Copilot, etc.):

> **Install `aduhappy/multi-agent-project-skill` as a skill**

The agent will auto-detect the OS, clone the repo to the right skills directory, and prompt you to start a new session to activate it. **No need to pick a platform or path manually.**

Target skills directories (the agent will pick the right one based on the current tool):

| Tool | User-level path | Project-level path |
|---|---|---|
| ZCode / Codex CLI | `~/.agents/skills/multi-agent-project` | `<project>/.agents/skills/multi-agent-project` |
| Claude Code | `~/.claude/skills/multi-agent-project` | `<project>/.claude/skills/multi-agent-project` |
| Cursor | N/A | `.cursor/rules/` (modern) or `.cursorrules` (legacy) |

### Option 2: Manual Clone (Fallback)

Repository: `https://github.com/aduhappy/multi-agent-project-skill.git`

```bash
# User-level (install once, available for all projects)
git clone https://github.com/aduhappy/multi-agent-project-skill.git ~/.agents/skills/multi-agent-project

# Project-level (only for one project)
git clone https://github.com/aduhappy/multi-agent-project-skill.git .agents/skills/multi-agent-project
```

> On Windows, `~` maps to `%USERPROFILE%`. If the skills directory doesn't exist, `mkdir` it first.

---

## What Is This

An [Agent Skill](https://agentskills.io/) that generates a **tool-agnostic pure Markdown collaboration skeleton** in the project root.

Design goal — **single source of truth**: `AGENTS.md` is the only authoritative entry point; all other tool config files (`CLAUDE.md` / `GEMINI.md` / `.cursorrules` / `.github/copilot-instructions.md`) are 3-line thin pointers redirecting to `AGENTS.md`. Switch AI tools freely — every agent reads the same entry, no context loss, no overwriting.

Four core principles:
1. **Single source of truth** — AGENTS.md is the only authoritative entry point
2. **Details externalized, entry point kept short** — Entry fits in 1–2 screens
3. **Pure Markdown + relative paths** — Switching tools doesn't break anything
4. **Trust but verify** — Agent self-checks aren't enough; critical outputs require independent review before handoff

### Differentiator vs Similar Skills

| Skill | Focus | Best For |
|---|---|---|
| [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) | Auto-generates `AGENTS.md` (from Makefile/package.json) | Software engineering projects |
| **This skill (multi-agent-project)** | **Multi-agent handoff skeleton** + task cards + data provenance + handoff conventions | **Research / data-intensive / multi-dataset / long-pipeline projects** |

Key differentiators:
- **Path conventions** — Big files to work drive, small outputs back to repo (prevents cloud-sync explosions / multi-agent collisions)
- **Dataset `source.txt`** — DOI/URL/date/method/units — any agent switch preserves traceability
- **Self-contained task cards** — Cold-start executable; zero-context agent can work directly (with "pre-delivery must-do" checklist + optional recommended model)
- **ADR + glossary + progress log** — Prevents the next agent from re-debating settled decisions or re-treading old ground
- **Shutdown conventions** — Every agent updates status + task board on exit, keeping the handoff chain intact
- **Independent review gate** — "Don't trust self-checks" — critical outputs must pass independent spot-check before the next step
- **Key number anti-drift** — Same number written in exactly one place; consistency verified at shutdown
- **Bad output retirement** — Wrong outputs immediately tagged and isolated; silent reuse is more damaging than no output
- **Delegation template with pitfalls + self-check** — Guides agents to self-intercept common error types before reporting done
- **AGENTS.md top TL;DR block** — 3-line speed-read (current stage / next step / blockers); new agent knows state without reading the whole file
- **STATUS.md incremental handoff** — Only records "what this round did / files touched / pitfalls hit"; no overlap with AGENTS.md §3 cumulative snapshot
- **check_handoff.py shutdown self-check** — Script verifies §3 date freshness / TL;DR filled / STATUS non-template / thin pointers exist; all pass = handoff qualified
- **Task card directory index** — Dependency chain + current status table; new agent knows which card to start with

### When to Trigger

Any of these phrases will trigger the skill:
- "Start a new project / new topic", "How to organize docs for AI collaboration", "How to write AGENTS.md"
- "Multiple agent handoff", "Switch tools", "Context loss"
- "Help me set up project docs", "How to make multiple AI tools collaborate"

### Compatibility

Follows the [agents.md](https://agents.md/) open standard (60k+ open-source projects), compatible with:

| Tool | Entry File | Support |
|---|---|---|
| Claude Code | `CLAUDE.md` → AGENTS.md | ✅ |
| Cursor | `.cursorrules` / `.cursor/rules/` | ✅ (`.cursorrules` legacy, `.cursor/rules/*.mdc` recommended) |
| Gemini CLI | `GEMINI.md` → AGENTS.md | ✅ |
| GitHub Copilot | `.github/copilot-instructions.md` | ✅ |
| OpenAI Codex | `AGENTS.md` | ✅ |
| ZCode | `AGENTS.md` | ✅ |
| Any text tool | `AGENTS.md` (pure Markdown) | ✅ |

## Just Want Templates, Not the Skill

Don't want to install as a skill? Just copy the template files from `assets/` to your project root:
- `assets/AGENTS.md` → your project's `AGENTS.md`
- `assets/CLAUDE.md` → your project's `CLAUDE.md`
- `assets/task_plan_template.md` → your project's `docs/task_plan_<topic>.md`
- `assets/source_EN.txt` → each dataset directory (or `source.txt`)

> ⚠️ **Chinese filenames**: The original templates use Chinese filenames like `任务规划_模板.md`, `委派任务模板.md`, `来源.txt`. If your toolchain has issues with this, rename to ASCII names (e.g., `task_plan.md`, `delegation_template.md`, `source.txt`) and update the pointers in AGENTS.md §6. Content is unaffected.

## Generated File Skeleton

```
<project-root>/
├── AGENTS.md                          ← Single authoritative entry point (7 sections)
├── STATUS.md                          ← Current handoff state (written on shutdown)
├── CLAUDE.md                          ← Thin pointer → "see AGENTS.md"
├── GEMINI.md                          ← Thin pointer
├── .cursorrules                       ← Thin pointer (Cursor)
├── .github/copilot-instructions.md    ← Thin pointer (Copilot)
├── docs/
│   ├── task_plan_<topic>.md           ← Self-contained task card
│   ├── decision_records/              ← Key technical decisions (ADR)
│   └── glossary.md                    ← Project terminology
├── <dataset_name>/
│   ├── source.txt                     ← DOI/URL/date/method/units
│   └── ...
├── scripts/                           ← Code organized (no scripts in root)
│   └── README.md                      ← Script index: purpose/input/output/author
└── progress_log.md                    ← Dated change log
```

## AGENTS.md Sections (In Priority Order)

Template numbered 1–7, with **path conventions as §5.5** (too important to bury in iron rules). 8 sections total:

1. **North Star** — What this project does, who it's for, the tone
2. **Current Story / Method** — Latest direction + core method + recent changes
3. **Where We Are Now** — Updated each shutdown, 1–5 items with date stamps (the most critical handoff point)
4. **Task Board** — `[ ]`/`[x]` + owner + dependencies + known risks
5. **Iron Rules / Conventions** — Things that cause rework: environment, plotting/data rules, naming, methodology, shutdown conventions
5.5. **Path Conventions** — Where big files go, where small outputs return (separate section to prevent cloud-sync / multi-agent collisions)
6. **Deep-Read Pointers** — Where to find details
7. **Environment / Tools** — How to invoke tools, env locks

> Entry fits in 1–2 screens, every agent reads it; details externalized. Full advanced sections at [`references/advanced.md`](references/advanced.md) (8 topics: ADR, glossary, progress log, concrete DoD, handoff format, naming conventions, environment lock, data snapshots).

## Cross-Tool Resumability: 7 Hard Requirements

1. **Pure Markdown + relative paths + standard filenames** — No tool-specific syntax
2. **Data has `source.txt`** (DOI/URL/date/method/units) — Any agent switch preserves traceability
3. **Shutdown conventions in iron rules** — Every agent updates §Where We Are Now + §Task Board + STATUS.md (handoff file that survives conversation resets)
4. **Path discipline** — "Large files to work drive, small outputs back to repo" / "copy, don't move"
5. **New agent's first action** — Read AGENTS.md (including STATUS.md) before doing anything
6. **Single source for key numbers** — Same number written in one place, referenced elsewhere; verified for consistency on shutdown
7. **Bad output retirement / isolation** — Wrong outputs immediately tagged `_DEPRECATED` + AGENTS.md red notice + task board update

> Requirements 6 and 7 come from hard-won lessons: multi-agent doc editing causes number drift (same value differs by 1%+), and downstream silent reuse of bad outputs is more damaging than having no output.

## Two Layers of Resumability (Both Required)

- **Hard resumability (primary)**: Repo markdown — tool-agnostic, readable by any agent or human. This is the source of truth.
- **Soft resumability (enhancement)**: Memory layer (Cursor memory / Claude memory) accelerates retrieval, but never let core conclusions live only in memory.

> Criterion: Delete all memory layers. If the next agent picks up using only repo markdown → **pass**.

## Standard Delegation Template

Every time you delegate to a new agent, start with this uniform format. See `assets/delegation_template.md`:

```text
Start by reading AGENTS.md (including STATUS.md).
Don't modify: [raw data paths / core code paths].
This task only handles: [phase X].
If you find issues, log them in: [specified doc].
Output to: [specified path].
Known pitfalls: [...]
Pre-delivery self-check: [conservation/bounds/count/magnitude/units…]
```

The "Known pitfalls" and "Self-check" fields are **battle-verified critical additions** that dramatically reduce defect rates.

## Origin

This skeleton comes from a real research project's multi-agent practice — multi-source datasets, long analysis pipeline (data acquisition → cleaning → modeling → reconstruction), cloud-sync workspace, Claude + Cursor + ZCode multi-tool handoff. Every hard-won lesson (agents overwriting each other's outputs, lost state, cloud-sync deadlock, next agent re-debating settled directions) has been hardened into iron rules.

## License

Dual license (same as [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill)):

- **Code / Scripts**: [MIT](LICENSE-MIT)
- **Documentation / Templates**: [CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0)

This project follows the [agents.md](https://agents.md/) open standard.

## References

Key inspirations:
- [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) — Dual license structure, README convention, thin pointer approach
- [breezewish/CodexPotter](https://github.com/breezewish/CodexPotter) — Cross-session file memory (STATUS.md), new agent onboarding ritual, task delegation phrasing inspiration
- [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) — Lifecycle hook-driven workflow, completion gate, session recovery patterns
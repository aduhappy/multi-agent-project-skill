# Task Plan: <topic>

> Each task card is **self-contained** — a zero-context agent can start working from just this card without asking questions.
> Use consistent numbering across cards in the same project (T1/T2…). Synchronize status in AGENTS.md §4 Task Board.

## T1 【Task Name】
- **Goal**: 【One sentence: what to produce】
- **Owner**: 【TODO: data agent / modeling agent / user】
- **⚙️ Recommended model** (optional): 【TODO: Claude Sonnet 4 / GLM / DeepSeek / MIMO — model suited for this task. Leave blank for any. Note: long-context multi-file reading prefers Claude; code generation prefers DeepSeek; Chinese writing prefers GLM】
- **Input** (exact path / URL / DOI):
  - 【TODO: data at `manual_download/X/xxx.csv`】
  - 【TODO: literature DOI: 10.xxxx/xxxxx】
- **Output** (exact destination):
  - 【TODO: `output/xxx.csv` (rows, columns, units)】
  - 【TODO: `figures/Fig_xxx.png` (resolution, dimensions)】
- **Environment**: 【TODO: base / dlcm env; need PYTHONIOENCODING=utf-8?】
- **Notes (pitfalls · iron rules)**:
  - 【TODO: unit conversion g/kg → Mg/ha】
  - 【TODO: method must be size_53µm; density method does not enter backbone】
  - 【TODO: discrete data resampling use near/mode】
- **Acceptance** (runnable check or visible output):
  - 【TODO: `python check.py` exits 0 / conservation deviation all < 0.5%】
  - 【TODO: figure X/Y axes have Chinese labels, no SimHei missing-glyph boxes】
- **Dependencies**: None / depends on T0
- **Known risks**: 【TODO: Dataset X has conservation deviation to flag; certain env package may fail to install】
- **Status**: ✅Completed 2026-06-15 / ⏳In Progress / ⬜Not Started
- **Pre-delivery must-do** (check off all before reporting done):
  - [ ] Acceptance checklist all passed
  - [ ] (Critical tasks) Independent review passed (see AGENTS.md §5 "Independent Review Gate")
  - [ ] Updated AGENTS.md §3 (cumulative snapshot, with date) + §4 task board status checked off
  - [ ] Wrote STATUS.md (incremental: what this round did / which files touched / pitfalls hit)
  - [ ] Key number consistency audit (same number across docs differs < 1%, see §5)
  - [ ] If new script: updated `scripts/README.md`; if new data: updated `source.txt`
- **📋 Dispatch prompt (copy-paste ready)** — fill the card's fields into the block below so the **user can copy it straight to any agent for a cold start** (field meanings in `delegation_template.md`). Every card ships with one, so nobody re-types the delegation wording:
  ````text
  Start by reading AGENTS.md (incl. STATUS.md) and the task card docs/task_plan_<topic>.md (T1); follow the card.
  Task: 【one-line goal】. 【If a specific skill/tool/env is needed: use X】.
  Iron rule: don't modify 【raw data / core code / the formal manuscript】 — only 【do this task / output to the given path】.
  Inputs: 【exact paths / DOIs】; output to: 【exact path + rows/cols/units/format】.
  Known pitfalls: 【list known risk points】.
  Pre-delivery self-check: 【acceptance checklist: conservation/bounds/count/magnitude/units…】.
  When done: update AGENTS.md §3 + §4 board, write STATUS.md (incremental), run python scripts/check_handoff.py.
  ````

## T2 【Task Name】
(Copy the structure above and fill)

## Dependency Graph
```
T1 → T2 → T4
T3 can run in parallel with T2
```

> ⚠️ **Output = Input for the next task**: The upstream task's output file path is the downstream task's input reference. Task cards must not just say "depends on" — the downstream "Input" field must **precisely reference the upstream output file path**. E.g., T1 outputs `outputs/baseline/result.csv` → T2 input writes `outputs/baseline/result.csv`, not "T1's results".
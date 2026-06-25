# AGENTS.md — Project Entry Point (Any AI agent entering this directory, read me first)

> **North Star**: 【TODO: one sentence on what this project does, who it's for, the tone. Example: Study X using method Y, target journal Z / audience W. Don't derail the main line AAA.】

> ⚡ **TL;DR (speed-read on entry, 3 lines is enough, details below)**
> - **Current stage**: 【TODO: e.g. T3 in progress】
> - **Next step**: 【TODO: first action, precise to file/command】
> - **Blockers**: 【TODO: None / waiting for user to confirm X / waiting for data】
> (This block is updated on every shutdown; full state in §3, task board in §4)

> ✅ **Onboarding ritual**: After reading this file, confirm you understand — ① North Star (§1) ② Current state and blockers (§3) ③ What iron rules constrain you (§5–5.5, especially "non-conflatable dimensions" and method/unit constraints). Every sub-agent entering later must also read this file first before doing anything.

---

## 1. North Star / Current Story (【TODO: date + who decided direction】)
- 【TODO: latest direction, 2–3 key points. Example: ① X increased ② Y decreased ③ Main driver is Z.】
- **Authoritative backing**: 【TODO: representative literature supporting this story + one-sentence justification】
- **Differentiator**: 【TODO: dimension others haven't addressed. Example: stand age + regional scope】

## 2. Method / Engine (Key Decisions)
- 【TODO: core method, recent changes and why. One sentence — details at §6 pointers / decision records】
- 【TODO: core data foundation (which dataset / which paper)】

## 3. Where We Are Now (Update on every shutdown — cumulative snapshot, incremental details sink to STATUS.md)
- ✅ 【TODO: most recent accomplishment, with date. Example 2026-06-15: Dataset X downloaded and cleaned at <path>】
- ✅ 【TODO: another completed item】
- ⏳ See §4 Task Board for remaining items
- `→ This round's incremental handoff (what this agent did / files touched / pitfalls hit) see STATUS.md`
- **Blockers** (if any — structure: problem / who's blocked / what was tried / waiting for whom / related docs):
  - 【TODO: Example: Dataset A method inconsistent with Paper B — compared 3 methods, none match (see `reports/xxx.md`), waiting for advisor decision on which to use. Write "None" if no blockers.】

> ⚠️ If any prior agent output has been found wrong and retired, list it here with path and date. See §5 "Bad output retirement" rule.

## 4. Next Task Board (Details at `docs/task_plan_<topic>.md`)
- [x] **T1【TODO】** — ✅ Completed 2026-06-15
- [ ] **T2【TODO】** (depends on T1, next·can start)
- [ ] **T3【TODO】** (depends on T2)
- [ ] **T4【TODO】**

## 5. Iron Rules / Conventions (Violations cause errors or rework)
- 【TODO: Environment rules. Example: Plotting uses base env, raster processing uses X env — they must not share a process (DLL conflict)】
- 【TODO: Data rules. Example: Discrete data resampling must be near/mode, never bilinear/cubic】
- 【TODO: Method/unit rules. Example: SOC fractions use 53µm size fractionation as backbone; density fractionation and chemical oxidation don't enter the backbone regression】
- 【TODO: Naming rules. Example: Chinese figures with ²/µ use mathtext ($^2$/$\mu$); SimHei missing glyphs produce boxes】
- 【TODO: Cross-dataset deduplication rules. Example: Deduplicate by DOI + coordinates (±0.01°) + approximate values】
- **Non-conflatable dimensions** (from setup): 【TODO: e.g., 53µm method ≠ density method; g/kg ≠ Mg/ha; Albers ≠ WGS84; topsoil ≠ subsoil — treat as separate analysis dimensions.】
- **Code organization**: Scripts go in `scripts/`, not scattered in root. Each new script updates `scripts/README.md` (purpose, input, output, author). Root directory only for entry files and thin pointers.
- **Shutdown convention**: Every agent updates §3 (cumulative snapshot, with date) + §4 task board + writes/updates `STATUS.md` (**incremental handoff**: what this round did / files touched / pitfalls hit, don't repeat §3). On shutdown run `python scripts/check_handoff.py` to self-check — verifies §3 date is fresh, TL;DR filled, STATUS.md non-template, thin pointers exist. All pass = handoff qualified.
- **Independent review gate (critical tasks)**: Outputs affecting paper conclusions or downstream pipelines must pass independent spot-check by the orchestrator or another agent (conservation/bounds/cell count/magnitude/document consistency) before being considered complete. "Self-checks passed" is not a completion criterion. Outputs are marked "PENDING REVIEW — do not use downstream" until independent review passes.
- **Single source for key numbers**: The same number (mean, percentage, area, statistic) is written in exactly one place (STATUS.md or AGENTS.md §3). Other locations reference but don't restate. Before shutdown, verify number consistency across all docs — a >1% difference for the same value is a bug; fix before handoff.
- **Bad output retirement**: If an agent's output is found to be wrong, immediately do four things: ① Rename directory/file with `_DEPRECATED` suffix or move to `_retired/`; ② Red-annotate `> ⚠️ 【RETIRED】<path> <reason>` at top of this section; ③ Update §4 task board status to `[x]` + label "retired"; ④ Update STATUS.md. **Never rely on memory saying "don't use that"** — silent downstream reuse of bad output is more damaging than having no output.

## 5.5 Path Conventions (Critical: Prevent cloud-sync explosions / multi-agent collisions)
Project root `【TODO: absolute path】` is in `【TODO: e.g., OneDrive】` and 【is / is not】 auto-synced. Large/voluminous/intermediate files **must never** be written directly in the project root, or sync will hang/crash.

| Directory | Purpose |
|---|---|
| `<project-root>\` | Small outputs (KB–few MB: CSVs, PNGs, scripts, md, final small rasters) |
| `【TODO: work drive, e.g. D:\scratch or /mnt/scratch】\` | Large/intermediate files (GB-level RF intermediate rasters, full packages — never in project) |
| `【TODO: temp dir】\` | General temp |

- **Criterion**: Single file >50MB or batch >dozen files → scratch; small files → project.
- Scripts **declare output paths as top-level constants** (e.g., `SCRATCH = r'F:\xxx_scratch'`, `PROJ_OUT = r'...\output'`) for easy inspection and drive relocation.
- Raw data sources (Zotero / manual downloads) are **read-only — don't write or delete**.

## 6. Deep-Read Pointers (Details live elsewhere, not here)
- **Task specs**: `docs/task_plan_<topic>.md` ← read before starting work
- **Key decisions (ADR)**: `docs/decision_records/` (why methods were rejected)
- **Glossary**: `docs/glossary.md` (project terms/abbreviations)
- **Key data / literature sources**: each dataset `<dataset_name>/source.txt`
- 【TODO: review reports, advisor debriefs, and other topic documents】

## 7. Environment / Tools (Always use full paths, don't add to PATH, don't install new Python)
【TODO: e.g., Anaconda at D:\software\tools\Anaconda】

| Environment | python.exe path | Purpose |
|---|---|---|
| base | `D:\...\python.exe` | Plotting, pandas, PDF reading |
| 【TODO】 | `D:\...\python.exe` | 【TODO】 |

- conda: `D:\...\condabin\conda.bat`　pip: `D:\...\Scripts\pip.exe`
- Version lock: `environment.yml` (see references/advanced.md)
- 【TODO: LibreOffice etc.: `C:\...\soffice.exe`】
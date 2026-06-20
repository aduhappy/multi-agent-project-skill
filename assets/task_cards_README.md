# Task Cards Directory Index

> New agent doesn't know which card to start with? Look here. This file is the **navigation index** for task cards, listing dependency chains and current status.
> For individual task card details see the corresponding `.md` file; for full board see AGENTS.md §4.

## Dependency Chain (who depends on whom, which can run in parallel)

```
T1 → T2 → T4
        ↘
T3 ─────→ T5 → T6 (T3 and T2 can run in parallel)
```

> Draw dependencies with ASCII, arrows mean "must complete before starting". Parallel branches side by side.

## Task Card List

| # | Task Name | Status | Recommended Model | Depends On | File |
|---|---|---|---|---|---|
| T1 | 【TODO: task name】 | ✅Completed / ⏳In Progress / ⬜Not Started | 【Claude/DeepSeek/GLM/—】 | None | `task_cards/T1_xxx.md` |
| T2 | 【TODO】 | ⬜Not Started | 【TODO】 | T1 | `task_cards/T2_xxx.md` |
| T3 | 【TODO】 | ⬜Not Started | 【TODO】 | None | `task_cards/T3_xxx.md` |
| T4 | 【TODO】 | ⬜Not Started | 【TODO】 | T2 | `task_cards/T4_xxx.md` |

> **New agent finding work**: Find the first ⬜ in the Status column, check if its dependencies are all ✅, if yes → start.
> **Naming convention**: Task card filename `T<number>_<short_topic>.md`, e.g. `T1_data_cleaning.md`.

## Current Recommended Entry

- **If picking up from scratch**: Start from the first ⬜ task, read backwards through its dependency task cards.
- **If taking over from a previous agent**: First read STATUS.md (incremental handoff), then AGENTS.md §3 (cumulative snapshot), finally locate the current task's card.

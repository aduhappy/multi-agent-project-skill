# STATUS.md — Incremental Handoff (Most Recent)

> This file **only records increments**: what this agent did this round, which files changed, what pitfalls were hit.
> For full cumulative state see AGENTS.md §3/§4; STATUS.md doesn't repeat the full picture, only "what changed since last time".
> Shutdown convention: Every agent must update this file on exit.

## Handoff (YYYY-MM-DD, agent: xxx)

- **What this agent did**: <what this agent did this round, 1–3 items, verb-first. E.g.: Completed T3 raster resampling, output 12 tifs>
- **Files touched**: <which files added/modified/deleted, exact paths. E.g.: new `outputs/t3/*.tif`, updated `scripts/reproject.py`>
- **Key number changes**: <new/revised key numbers this round. E.g.: MAOC mean 4.2 → 4.18 g/kg (fixed unit conversion bug)>
- **Pitfalls / warnings for the next agent**: <pitfalls this agent hit or points the next agent should watch. E.g.: some raster NoData is -9999 not 0, don't add directly>
- **Suggested next step**: <next agent's first action, precise to command/file. E.g.: first run `python scripts/check_t3.py` for acceptance>
- **Blockers**: <needs user confirmation X / waiting for data / waiting for external dependency. Write "None" if no blockers>

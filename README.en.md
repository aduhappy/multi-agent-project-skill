# Multi-Agent Project Skill

> A tool-agnostic, pure-Markdown project skeleton for seamless multi-agent handoffs across AI coding tools.
> **中文完整文档**：[`README.md`](README.md) · [`SKILL.md`](SKILL.md)

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE-MIT)
[![License: CC BY-SA 4.0](https://img.shields.io/badge/Content-CC--BY--SA--4.0-green.svg)](LICENSE-CC-BY-SA-4.0)
[![agents.md](https://img.shields.io/badge/standard-agents.md-orange.svg)](https://agents.md/)

## What It Is

`multi-agent-project` is an [Agent Skill](https://agentskills.io/) designed for research, data-intensive, and long-pipeline projects where multiple AI agents or tools work in relay. It generates and maintains:

- **One authoritative entry (`AGENTS.md`)**: North Star, current snapshot (§3), grep-friendly decision registry (§3.5), task board (§4), behavioral & unit invariants (§5), scratch/cloud-sync path rules (§5.5), and environment paths (§7). Supports both single-line (`Scope: line`) and multi-line root index (`Scope: index`) layouts.
- **Thin pointers**: `CLAUDE.md` (with `@AGENTS.md` import), `GEMINI.md`, `.cursor/rules/multi-agent.mdc`, and `.github/copilot-instructions.md` pointing to the same `AGENTS.md`.
- **Self-contained task cards, standalone rules & incremental handoffs**: Shared rules live in `文档/协作规矩.md` (replaceable on upgrade), one card per task (`assets/任务卡_模板.md`) under `文档/任务卡/`, and bounded 4-section handoffs (`≤800` chars) in `STATUS.md`.
- **Zero-dependency Python utilities**: `handoff_lib.py`, `check_handoff.py` (`H001–H009` + `A001–A018`, `--role`), `archive_status.py`, `sync_board.py`, `upgrade.py`, and `fingerprint.py`.

## Installation

Ask your agent:

> **Install `aduhappy/multi-agent-project-skill` as a skill**

Or clone manually (**keep the final directory name `multi-agent-project`** so `SKILL.md`'s `name` matches):

```bash
# Codex CLI / ZCode (user-level)
git clone https://github.com/aduhappy/multi-agent-project-skill.git ~/.agents/skills/multi-agent-project

# Claude Code (user-level)
git clone https://github.com/aduhappy/multi-agent-project-skill.git ~/.claude/skills/multi-agent-project
```

Start a new session after cloning. If you only want the templates without installing the skill, copy files directly from [`assets/`](assets/).

## Documentation (Chinese)

All templates and operational rules are maintained in Chinese as the single authoritative source:

- **Overview & Compatibility**: [`README.md`](README.md)
- **Skill Workflow (Mode A / Mode B / Mode C) & 10 Hard Rules**: [`SKILL.md`](SKILL.md)
- **Tool Installation Paths**: [`references/install.md`](references/install.md)
- **Filled `AGENTS.md` Example**: [`references/example_filled_AGENTS.md`](references/example_filled_AGENTS.md)
- **Multi-Line Projects & Advanced Patterns**: [`references/multi_line.md`](references/multi_line.md) · [`references/advanced.md`](references/advanced.md)

## License

Code & scripts: [MIT](LICENSE-MIT) · Templates & documentation: [CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0).

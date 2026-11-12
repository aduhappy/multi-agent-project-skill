# Multi-Agent Project Skill

> 跨 agent、跨软件可续接的项目文档骨架生成器。一个权威入口 + 薄指针 + 自包含任务卡 + 收工规矩，全用纯 Markdown——换 Claude / Cursor / Gemini / ZCode / Codex / Copilot 任何一个，agent 进来读同一份入口就能接上前任工作。
> **English Overview**: [`README.en.md`](README.en.md)

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE-MIT)
[![License: CC BY-SA 4.0](https://img.shields.io/badge/Content-CC--BY--SA--4.0-green.svg)](LICENSE-CC-BY-SA-4.0)
[![agents.md](https://img.shields.io/badge/standard-agents.md-orange.svg)](https://agents.md/)

---

## 🚀 安装

### 方式一：让 agent 自主安装（推荐）

直接对任何 AI agent（Claude / Cursor / Gemini / ZCode / Codex / Copilot 等）说一句：

> **把 `aduhappy/multi-agent-project-skill` 装成 skill**

agent 会自己判断操作系统、把仓库 clone 到本工具的 skills 目录、装完提示你新开会话即可触发。**无需手动选平台、无需手动挑路径。**（完整各工具路径见 [`references/install.md`](references/install.md)。）

| 工具 | 用户级路径 | 项目级路径 |
|---|---|---|
| ZCode / Codex CLI | `~/.agents/skills/multi-agent-project` | `<项目>/.agents/skills/multi-agent-project` |
| Claude Code | `~/.claude/skills/multi-agent-project` | `<项目>/.claude/skills/multi-agent-project` |
| Cursor | N/A | `.cursor/rules/`（现代）或 `.cursorrules`（legacy）|

### 方式二：手动 clone（备用）

仓库地址：`https://github.com/aduhappy/multi-agent-project-skill.git`

```bash
# 用户级（装一次，所有项目可用）
git clone https://github.com/aduhappy/multi-agent-project-skill.git ~/.agents/skills/multi-agent-project

# 项目级（仅某个项目）
git clone https://github.com/aduhappy/multi-agent-project-skill.git .agents/skills/multi-agent-project
```

> Windows 用户的 `~` 对应 `%USERPROFILE%`；若 skills 目录不存在，先 `mkdir` 再 clone。**末段目录名必须保持 `multi-agent-project`**。

---

## 这是什么

一个 [Agent Skill](https://agentskills.io/)：在项目根目录生成一套**软件无关的纯 Markdown 协同骨架**。支持单线 `line` 与多线根索引 `index` 两种 scope；根索引只导航，线级入口才承载详细状态。

设计目标——**真相只有一份**：`AGENTS.md` 是唯一权威入口，其他工具的约定文件（`CLAUDE.md` / `GEMINI.md` / `.cursor/rules/*.mdc` / `.github/copilot-instructions.md`）全是薄指针或导入，指向 `AGENTS.md`。换任何 AI 工具，agent 都读同一份入口，不丢上下文、不互相覆盖。

四条核心原则：
1. **真相只有一份** — `AGENTS.md` 是唯一权威入口
2. **细节外链、入口要短** — 入口 1–2 屏，细则下沉到 `文档/` 专题文件，超限由脚本归档
3. **纯 Markdown + 相对路径 + 标准库脚本** — 换工具不破，无第三方依赖
4. **信任但验证** — agent 自检不够，关键产物须按分级独立复核通过才放行下游

### 和同类 skill 的区别

| Skill | 定位 | 适用 |
|---|---|---|
| [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) | 自动生成 `AGENTS.md`（从 Makefile/package.json 提取命令） | 软件工程项目 |
| **本 skill（multi-agent-project）** | **多 agent 接力的协同骨架** + 任务卡 + 数据溯源 + handoff | **科研 / 数据密集 / 多数据集 / 长管线项目** |

本 skill 的差异化亮点：
- **路径约定（§5.5）**——大文件进工作盘、小产物回仓库（防云同步爆炸 / 多 agent 撞车）
- **数据集 `来源.txt`**——DOI/URL/日期/口径/单位，换人换 agent 都能溯源
- **自包含任务卡与目录索引**——一个任务一张卡（执行 + 独立复核同卡双提示词），`文档/任务卡_README.md` 集中管理依赖链与卡面规矩
- **决策登记表（§3.5）+ 决策记录 + 词汇表**——`ACTIVE`/`SUPERSEDED` 双向链防静默覆盖，避免下个 agent 重新踩坑
- **跨模型家族独立复核阀门**——分析建模必独立复核、论文头条数字必跨模型家族复核，重开最终交付物本身核对
- **关键数字与口径参数防漂移**——同一数字只在一处写定，口径抽进唯一 `config`，计数与派生数一律由脚本算出
- **`STATUS.md` 增量 handoff + 一键自检归档**——`check_handoff.py` 检查阻断项与提示项，`archive_status.py` 保持原换行符一键归档旧段

## 何时触发

说任一句都会触发（单文件小脚本、已有完善入口且无需改动、纯翻译或问答不触发）：
- "开新项目/新课题""怎么组织文档让 AI 协同""AGENTS.md 怎么写"
- "多个 agent 接力""换软件继续""上下文丢失"
- "帮我建个项目文档""怎么让多个 AI 工具协同"

## 兼容性

遵循 [agents.md](https://agents.md/) 开放标准，兼容：

| 工具 | 入口文件 | 支持 |
|---|---|---|
| Claude Code | `CLAUDE.md`（含 `@AGENTS.md` 自动导入）→ `AGENTS.md` | ✅ |
| Cursor | `.cursor/rules/*.mdc` / `.cursorrules` | ✅（推荐 `.cursor/rules/*.mdc`，`.cursorrules` 为 legacy）|
| Gemini CLI | `GEMINI.md` → `AGENTS.md` | ✅ |
| GitHub Copilot（IDE） | `.github/copilot-instructions.md` → `AGENTS.md` | ✅ |
| GitHub Copilot CLI | `AGENTS.md`、`.github/copilot-instructions.md`、`CLAUDE.md`、`GEMINI.md` | ✅（原生发现仓库根、当前目录及路径各层上述文件）|
| OpenAI Codex | `AGENTS.md` | ✅ |
| ZCode | `AGENTS.md` | ✅ |
| 任何文本工具 | `AGENTS.md`（纯 Markdown） | ✅ |

## 只要模板文件，不要 skill

不想装成 skill、只想要骨架文件？直接复制 [`assets/`](assets/) 目录下的模板与脚本到你的项目（单线拷 `assets/AGENTS.md`，多线课题根拷 `assets/ROOT_AGENTS.md`；协作规矩、任务卡与索引拷 `assets/协作规矩.md`、`assets/任务卡_模板.md`、`assets/任务卡_README.md`；脚本拷 `assets/handoff_lib.py`、`assets/check_handoff.py`、`assets/archive_status.py` 等到 `scripts/`）。
> 旧名说明：0.5.0 起 `assets/任务规划_模板.md` 改名为 `assets/任务卡_模板.md`。

> ⚠️ 中文文件名注意：如果你的 toolchain 对中文路径挑剔，在**你自己的项目里**改用 ASCII 文件名并更新线级入口指针；不要改变本 skill 的安装目录 `multi-agent-project`。

收工自检与归档：线级运行 `python scripts/check_handoff.py --scope line`（多线根用 `--scope index`），涵盖 `H001–H009` 阻断项与 `A001–A015` 提示项；体积超限时运行 `python scripts/archive_status.py` 归档旧段。技能仓库自身运行 `python tests/test_skill.py`。

## 骨架结构、入口板块与十条硬要求（唯一权威清单见 `SKILL.md`）

为避免 README 与技能定义出现双份清单漂移，详细规范统一维护在 [`SKILL.md`](SKILL.md) 中：

- **生成的文件骨架**：`AGENTS.md` + `STATUS.md` + 薄指针 + `文档/`（`任务卡/`、`任务卡_README.md`、可选 `环境坑.md`/`决策记录/`/`词汇表.md`）+ `<数据集>/来源.txt` + `scripts/`（`handoff_lib.py`、`check_handoff.py`、`archive_status.py`）。完整目录树见 [`SKILL.md` §文件骨架](SKILL.md#文件骨架)。
- **`AGENTS.md` 板块与边界**：顶部 `TL;DR` + `§1–§7`（含 `§3.5` 决策登记表、`§5` 行为铁律与 `§5.5` 路径约定分离）。各节职责见 [`SKILL.md` §AGENTS.md 板块与边界](SKILL.md#agentsmd-板块与边界照-assetsagentsmd-填)，填好完整样例见 [`references/example_filled_AGENTS.md`](references/example_filled_AGENTS.md)。
- **跨软件能续的 10 条硬要求与 5 步工作流**：纯 Markdown、数据带 `来源.txt`、角色与 scope 收工纪律、工作盘分流、进门先读并 grep 决策表、数字口径单一来源、坏产物退役隔离、工具/模型/家族留痕、双源交叉测量、按需记哈希。逐条说明见 [`SKILL.md` §跨软件能续的 10 条硬要求](SKILL.md#跨软件能续的-10-条硬要求)，按需进阶模块见 [`references/advanced.md`](references/advanced.md)。

## 两层续接（缺一不可）

- **硬续接（主依赖）**：仓库里的 Markdown，软件无关，任何 agent/人都能读——这是真相源。
- **软续接（增强）**：记忆层（Cursor memory / Claude memory）加速检索，但别让核心结论只活在记忆里，必须落回 Markdown。

> 判据：把所有记忆层删光，下个 agent 只靠仓库 Markdown 也能接上 → 合格。

## 起源

这套骨架来自真实科研项目的多 agent 实战——多源数据集、长分析管线（拉数据 → 清洗 → 建模 → 制图与报告）、云同步工作目录、多软件多模型家族接力。踩过的坑（agent 覆盖彼此产出、找不到状态、云同步卡死、下个 agent 重新质疑已定方向）都固化成了铁律与自检项。

## 许可证

双许可证（跟 [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) 一致）：

- **代码 / 脚本**：[MIT](LICENSE-MIT)
- **文档 / 模板内容**：[CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0)

本项目遵循 [agents.md](https://agents.md/) 开放标准。

## 参考

下列项目为本 skill 的设计提供了关键启发：

- [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) —— 双许可证结构、README 发布标配、薄指针的做法
- [breezewish/CodexPotter](https://github.com/breezewish/CodexPotter) —— 跨轮次文件记忆（`STATUS.md`）、新 agent 进门仪式、任务委派话术的灵感
- [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) —— 生命周期钩子驱动的工作流、完成闸门、会话恢复模式

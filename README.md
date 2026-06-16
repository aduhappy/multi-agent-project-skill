# Multi-Agent Project Skill

> 跨 agent、跨软件可续接的项目文档骨架生成器。一个权威入口 + 薄指针 + 自包含任务卡 + 收工规矩，全用纯 Markdown——换 Claude / Cursor / Gemini / ZCode / Codex / Copilot 任何一个，agent 进来读同一份入口就能接上前任工作。

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE-MIT)
[![License: CC BY-SA 4.0](https://img.shields.io/badge/Content-CC--BY--SA--4.0-green.svg)](LICENSE-CC-BY-SA-4.0)
[![agents.md](https://img.shields.io/badge/standard-agents.md-orange.svg)](https://agents.md/)

---

## 🚀 一行安装

**macOS / Linux：**
```bash
mkdir -p ~/.agents/skills && git clone https://github.com/aduhappy/multi-agent-project-skill.git ~/.agents/skills/multi-agent-project
```

**Windows（PowerShell）：**
```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null; git clone https://github.com/aduhappy/multi-agent-project-skill.git "$HOME\.agents\skills\multi-agent-project"
```

**Windows（cmd）：**
```cmd
mkdir "%USERPROFILE%\.agents\skills" 2>nul & git clone https://github.com/aduhappy/multi-agent-project-skill.git "%USERPROFILE%\.agents\skills\multi-agent-project"
```

> 💬 **对任何 AI agent 说一句「**把 `aduhappy/multi-agent-project-skill` 装成 skill**」即可**——它会自动执行上面的 clone 命令到 skills 目录。装完新开一个会话就能触发。

---

## 这是什么

一个 [Agent Skill](https://agentskills.io/)：在项目根目录生成一套**软件无关的纯 Markdown 协同骨架**。

设计目标——**真相只有一份**：`AGENTS.md` 是唯一权威入口，其他工具的约定文件（`CLAUDE.md` / `GEMINI.md` / `.cursorrules` / `.github/copilot-instructions.md`）全是 3 行薄指针，指向 `AGENTS.md`。换任何 AI 工具，agent 都读同一份入口，不丢上下文、不互相覆盖。

### 和同类 skill 的区别

| Skill | 定位 | 适用 |
|---|---|---|
| [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) | 自动生成 `AGENTS.md`（从 Makefile/package.json 提取命令） | 软件工程项目 |
| **本 skill（multi-agent-project）** | **多 agent 接力的协同骨架** + 任务卡 + 数据溯源 + handoff | **科研 / 数据密集 / 多数据集 / 长管线项目** |

本 skill 的差异化亮点：
- **路径约定**——大文件进工作盘、小产物回仓库（防云同步爆炸 / 多 agent 撞车）
- **数据集 `来源.txt`**——DOI/URL/日期/口径/单位，换人换 agent 都能溯源
- **自包含任务卡**——冷启动可执行，零上下文 agent 能直接动手
- **决策记录（ADR）+ 词汇表 + 进度日志**——防下个 agent 重新踩坑、重新质疑已定的事
- **收工规矩**——每个 agent 退出前更新现状 + 看板，保证接力不断

## 何时触发

说任一句都会触发：
- "开新项目/新课题""怎么组织文档让 AI 协同""AGENTS.md 怎么写"
- "多个 agent 接力""换软件继续""上下文丢失"
- "帮我建个项目文档""怎么让多个 AI 工具协同"

## 兼容性

遵循 [agents.md](https://agents.md/) 开放标准（60k+ 开源项目在用），兼容：

| 工具 | 入口文件 | 支持 |
|---|---|---|
| Claude Code | `CLAUDE.md` → AGENTS.md | ✅ |
| Cursor | `.cursorrules` / `.cursor/rules/` | ✅ |
| Gemini CLI | `GEMINI.md` → AGENTS.md | ✅ |
| GitHub Copilot | `.github/copilot-instructions.md` | ✅ |
| OpenAI Codex | `AGENTS.md` | ✅ |
| ZCode | `AGENTS.md` | ✅ |
| 任何文本工具 | `AGENTS.md`（纯 Markdown） | ✅ |

## 安装（其他方式）

顶部「一行安装」是**用户级**（装一次，所有项目可用），下面是两种补充：

### 项目级（仅某个项目用）

```bash
git clone https://github.com/aduhappy/multi-agent-project-skill.git .agents/skills/multi-agent-project
```

### 只想要模板文件，不要 skill

直接复制 `assets/` 目录下的文件到你的项目根：
- `assets/AGENTS.md` → 你的项目 `AGENTS.md`
- `assets/CLAUDE.md` → 你的项目 `CLAUDE.md`
- `assets/任务规划_模板.md` → 你的项目 `文档/任务规划_<主题>.md`
- `assets/来源.txt` → 各数据集目录

## 生成的文件骨架

```
<项目根>/
├── AGENTS.md                          ← 唯一权威入口（七板块）
├── CLAUDE.md                          ← 薄指针 → "以 AGENTS.md 为准"
├── GEMINI.md                          ← 薄指针
├── .cursorrules                       ← 薄指针（Cursor）
├── .github/copilot-instructions.md    ← 薄指针（Copilot）
├── 文档/
│   ├── 任务规划_<主题>.md             ← 自包含任务卡
│   ├── 决策记录/                      ← 关键技术决策（ADR）
│   └── 词汇表.md                      ← 项目术语
├── <数据集名>/
│   ├── 来源.txt                       ← DOI/URL/日期/口径
│   └── ...
└── 进度日志.md                        ← 带日期戳的变更流水
```

## AGENTS.md 的七个板块（顺序即优先级）

1. **一句话北极星**——项目到底干嘛、给谁、什么基调
2. **当前故事/方法**——最新方向 + 核心方法 + 最近换过什么
3. **现在在哪**——每次收工更新，1–5 条带日期戳（接力最关键的交接点）
4. **任务看板**——`[ ]`/`[x]` + 谁负责 + 依赖 + 已知风险
5. **铁律/约定**——违反会返工的：环境调用、绘图/数据规矩、命名、口径
6. **路径约定**——大文件去哪、小产物回哪（单独成节）
7. **深读指针 + 环境/工具**——细节去哪个文档、完整工具路径

> 入口控制在 1–2 屏，每个 agent 都得读完；细节全部外链。完整说明见 [`references/advanced.md`](references/advanced.md)（8 个进阶板块：ADR、词汇表、进度日志、验收具体化、handoff 格式、命名约定、环境锁、数据快照）。

## 跨软件能续的四个硬要求

1. **纯 Markdown + 相对路径 + 标准文件名**——别用某软件专属语法
2. **数据带 `来源.txt`**（DOI/URL/日期/口径/单位）——换人换 agent 都能溯源
3. **收工规矩写进铁律**——每个 agent 退出前更新 §现在在哪 + §任务看板
4. **路径纪律**——"大文件进工作盘、小产物回仓库""复制不剪切"

## 两层续接（缺一不可）

- **硬续接（主依赖）**：仓库里的 Markdown，软件无关，任何 agent/人都能读——这是真相源。
- **软续接（增强）**：记忆层（ChatMem / Cursor memory / Claude memory）加速检索，但别让核心结论只活在记忆里，必须落回 Markdown。

> 判据：把所有记忆层删光，下个 agent 只靠仓库 Markdown 也能接上 → 合格。

## 起源

这套骨架来自一个真实科研项目的多 agent 实战——多源数据集、长分析管线（拉数据 → 清洗 → 建模 → 重建）、云同步工作目录、Claude + Cursor + ZCode 多软件接力。踩过的坑（agent 覆盖彼此产出、找不到状态、云同步卡死、下个 agent 重新质疑已定方向）都固化成了铁律。

## 许可证

双许可证（跟 [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) 一致）：

- **代码 / 脚本**：[MIT](LICENSE-MIT)
- **文档 / 模板内容**：[CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0)

## 致谢

- [agents.md](https://agents.md/) —— 开放标准
- [netresearch/agent-rules-skill](https://github.com/netresearch/agent-rules-skill) —— 双许可证结构和软件工程向的参照
- [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) —— 社区索引

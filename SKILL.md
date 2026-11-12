---
name: multi-agent-project
description: 初始化或重构"跨 agent、跨软件可续接"的项目文档骨架。当用户开新项目/新课题、想建立多智能体协同工作流、提到 AGENTS.md / CLAUDE.md / GEMINI.md / .cursorrules / copilot-instructions / 项目记忆 / agent 接力 / 换软件继续 / 上下文丢失，或现有项目缺统一入口导致每个 agent 反复问相同问题、互相覆盖、接不上前任工作时使用。即使是"帮我建个项目文档""怎么让多个 AI 工具协同""开个新课题要准备什么"这类模糊请求也适用。不适用于单文件小脚本、已有完善入口且无需改动的项目、纯翻译或问答。
---

# 多 Agent 协同项目骨架（跨软件可续接）

> **安装**：clone `https://github.com/aduhappy/multi-agent-project-skill` 到宿主工具的 skills 目录，**末段目录名必须钉为 `multi-agent-project`**（各工具路径表见 [`references/install.md`](references/install.md)）。

## 这技能干嘛

在项目根目录生成一套**软件无关的纯 Markdown 协同骨架**——唯一权威入口 `AGENTS.md` + 薄指针 + 自包含任务卡 + 脚本自检与归档。换 Claude / Cursor / Gemini / ZCode / Codex / Copilot 任何一个，agent 进门读同一份入口即可续接前任工作，不丢上下文、不互相覆盖。

核心原则四条：
1. **真相只有一份**：`AGENTS.md` 是唯一权威入口；`CLAUDE.md` / `GEMINI.md` / `.cursorrules` / `copilot-instructions.md` 全是 3 行薄指针。
2. **细节外链、入口要短**：入口控制在 1–2 屏，细则下沉到 `文档/` 专题文件，超限由脚本归档。
3. **纯 Markdown + 相对路径 + 标准库脚本**：不依赖软件专属语法或第三方包。
4. **信任但验证**：关键产物按分级独立复核通过才放行下游；复核通过前标“待验，下游不得启用”。

**何时触发**：开新项目/新课题、建立多 AI 协同文档、现有项目上下文丢失或互相覆盖、把协同经验固化成可复用结构。**不适用**：单文件小脚本、已有完善 `AGENTS.md` 且无需改动的项目、纯翻译或问答。

## 怎么用（三种模式）

### 模式 A：从零生成骨架

0. **预置决策登记表**：在线级 `AGENTS.md` §3.5 预置空表（模板已带），建模/取数前先 grep 此表。
1. **先读后问**：先读项目已有 README、目录、文档与代码；能推断的给默认值并标“默认值，可改”，一次性问用户特有且无法推断的信息（项目根、是否多线、一句话目标、兼容工具、是否云同步盘、数据源）。
2. **问清“不可混用的维度”**：把本领域绝不能混用的口径/单位/坐标系/分辨率/时期写成 §5 硬规则。
3. **建入口**：**单线项目**拷 `assets/AGENTS.md`；**多线项目**拷 `assets/ROOT_AGENTS.md` 作根索引，并为每条线拷 `assets/AGENTS.md`（冷启动与四条规矩见 [`references/multi_line.md`](references/multi_line.md)）。未知项留 `【待填】`，已知项直接填入（填完前检查器 A014 有【待填】提示属正常）。
4. **复制薄指针**：按勾选工具复制 `assets/CLAUDE.md`、`assets/GEMINI.md`、`assets/multi-agent.mdc` → `.cursor/rules/multi-agent.mdc` 或 `assets/copilot-instructions.md` → `.github/copilot-instructions.md`，统一指向当前 scope 根 `AGENTS.md`（子目录配置仍指向上级 scope 根）。未勾选不生成。
5. **建规矩、任务卡与索引**：拷 `assets/协作规矩.md` → `文档/协作规矩.md`（唯一出处，项目不改；例外写 `AGENTS.md` §5“本项目例外”）、`assets/任务卡_README.md` → `文档/任务卡_README.md`，照 `assets/任务卡_模板.md` 建 `文档/任务卡/T1_<主题>.md`（一个任务一张卡，执行与独立复核同卡双提示词）。多树/迁移另拷 `assets/迁移协议.md`、`assets/经验教训.md`。
6. **权威层与可选专题文件**：拷 `assets/关键数字.md` → `文档/关键数字.md`（与 §3.5 决策表同为权威层）、`assets/对外名称对照.md` → `文档/对外名称对照.md`；按需拷 `assets/环境坑.md` → `文档/环境坑.md`，或建 `文档/决策记录/`、`文档/词汇表.md`（见 [`references/advanced.md`](references/advanced.md)）。
7. **数据集溯源**：每类数据目录放 `来源.txt`（拷 `assets/来源.txt`）；无明确数据源可跳过。
8. **脚本归位**：建 `scripts/` + `scripts/README.md`（`assets/scripts_README.md`），一起复制 `assets/handoff_lib.py`、`assets/check_handoff.py`、`assets/archive_status.py`、`assets/sync_board.py`、`assets/upgrade.py`、`assets/fingerprint.py` 到 `scripts/`（自定义目录可在项目根放 `handoff_config.json`）：
   - 看板同步：建卡或改状态后跑 `python scripts/sync_board.py`，自动同步 `AGENTS.md` §4（`board` 标记）与索引表（`cards` 标记），标记外不动。
   - 收工自检：主控跑 `python scripts/check_handoff.py --scope line|index`，执行/复核方跑 `--role executor|reviewer --card T<卡号>`（涵盖 H001–H009 与 A001–A018）。
   - 归档与指纹：超限时跑 `python scripts/archive_status.py` 保留最近 N 段交接、在用卡交接段与 §3 最近 5 条；非 git 或只读目录用 `python scripts/fingerprint.py snapshot/compare` 记哈希比对。
9. **建 `STATUS.md`**：拷 `assets/STATUS.md` 并填入首段交接（“谁做的”＋四节 ≤800 字，去掉 `YYYY-MM-DD` 占位符）。交接标题仅支持 `##` 或 `###`（`####` 及更深标题不算交接段），须含 `Handoff`/`交接` 或以日期/`T<卡号>+日期` 开头（`## 交回说明`、`## 归档说明` 不算交接段）。
10. **写入约束**：把环境路径、行为红线、工作盘分流分别填入线级 §7、§5、§5.5。
11. **验证交回**：跑 `python scripts/sync_board.py`、`python scripts/check_handoff.py` 与 `python scripts/archive_status.py --dry-run`，告知用户已生成文件、默认值和待确认项。

### 模式 B：诊断已有项目

- **B1 烂项目修补（零文档或协同混乱）**：对照下文骨架列出缺项清单，经用户确认后增量补齐，**绝不覆盖已有文件**。
- **B2 好项目增强（已有完善文档，只缺入口发现）**：不动已有文档，只加 3 行 `AGENTS.md` 薄指针指向现有主文档，按需加 `CLAUDE.md` 等薄指针。

### 模式 C：升级已有骨架（0.3.x / 0.4.x → 当前版本）

1. **先预览再执行**：跑 `python <技能目录>/assets/upgrade.py .` 看变更与手工清单；确认后加 `--apply` 写盘（旧文件备份至 `文档/_作废/升级前_<日期>/`，重复跑幂等无改动）。
2. **脚本自动四件事**：① 更新 `scripts/` 下技能脚本；② 写入新版 `文档/协作规矩.md`；③ 把索引里旧“卡面规矩”原样移存 `文档/_作废/卡面规矩_旧.md` 并留一行指针；④ 在索引卡清单表外加 `cards` 标记。**绝不写 `AGENTS.md`、已有任务卡、`STATUS.md`。**
3. **主控可选收尾**：按提示手工清理 `AGENTS.md` §5 重复通用条目、补“本项目例外”与规矩指针；如需自动同步 §4 看板，加上 `<!-- board:start -->`…`<!-- board:end -->` 后跑 `python scripts/sync_board.py`。

## 文件骨架

```
<项目根>/
├── AGENTS.md                          ← 线级唯一权威入口（TL;DR + §1–§7，含 §3.5 决策表、§5.5 路径约定）
├── STATUS.md                          ← 增量 handoff（每段四节 ≤800 字）
├── CLAUDE.md / GEMINI.md / ...        ← 薄指针 → 指向当前 scope 根 AGENTS.md（按需）
├── 文档/
│   ├── 协作规矩.md                    ← 卡面规矩 + 通用铁律 + 各角色须知唯一出处（技能整份提供，项目不改）
│   ├── 任务卡/T1_<主题>.md            ← 自包含任务卡（执行 + 独立复核同卡）
│   ├── 任务卡_README.md               ← 依赖链 + 任务卡清单（含 cards 标记）
│   ├── 关键数字.md / 对外名称对照.md  ← 关键数字权威表 / 内部名↔对外名对照表
│   ├── 环境坑.md                      ← 软件/环境/同步盘已知坑单一来源（可选）
│   ├── 迁移协议.md / 经验教训.md      ← 多树迁移协议 / 规则实测案例（可选）
│   └── 决策记录/ · 词汇表.md          ← 复杂决策详卡 · 术语表（可选）
├── <数据集名>/来源.txt                ← DOI/URL/日期/口径/单位
└── scripts/
    ├── README.md                      ← 脚本索引
    ├── handoff_lib.py                 ← 共享 Markdown 块级解析与路径配置库
    ├── check_handoff.py               ← 收工交接自检（H001–H009 + A001–A018，支持 --role）
    ├── archive_status.py              ← STATUS 与 AGENTS §3 一键归档（保留在用卡交接段）
    ├── sync_board.py                  ← 从任务卡自动同步 AGENTS §4 与索引卡清单表
    ├── upgrade.py                     ← 已有骨架一键升级（默认只预览，绝不写入口/卡/STATUS）
    └── fingerprint.py                 ← 目录/文件 SHA-256 快照与新增/删除/改动比对
```

## AGENTS.md 板块与边界（照 `assets/AGENTS.md` 填）

- **0. TL;DR**（3 行：当前阶段 / 下一步 / 阻塞）→ **1. 北极星** → **2. 方法/引擎** → **3. 现在在哪**（1–5 条带日期累计快照；增量细节下沉 `STATUS.md`，不重复）→ **3.5 决策登记表**（具约束力的决策唯一权威源，一行一决策，`ACTIVE`/`SUPERSEDED` 双向链，严禁静默覆盖或复制第二张表）→ **4. 任务看板** → **5. 铁律/约定** → **5.5 路径约定** → **6. 深读指针** → **7. 环境/工具**（含 `文档/环境坑.md` 指针）。
- **§5 铁律 vs §5.5 路径约定**：铁律管“能不能做”（不改原始数据、口径不混用、计数用脚本）；路径约定管“做了放哪”（>50MB 或大批量中间件进 scratch，小产物回项目根，防云同步爆炸）。完整填好范例见 [`references/example_filled_AGENTS.md`](references/example_filled_AGENTS.md)。

## 跨软件能续的 10 条硬要求

1. **纯 Markdown + 相对路径 + 标准文件名**。
2. **数据带 `来源.txt`**（DOI/URL/日期/口径/单位/已知问题）。
3. **收工按角色与 scope 执行**——各角色权限表见 `文档/协作规矩.md`；按 `--scope line|index` 跑 `check_handoff.py`。
4. **路径纪律**——大文件进工作盘、小产物回仓库；复制不剪切。
5. **进门先读当前 scope 入口**——读 `AGENTS.md` 与 `STATUS.md`，先 grep §3.5 决策表；多树/迁移项目首条动作跑 `git rev-parse --show-toplevel` 核对绝对路径。
6. **关键数字与口径参数单一来源**——口径/样本集抽进唯一 `config`，不在多脚本各自硬编码；计数和派生数一律由脚本算出。
7. **坏产物与旧脚本一并退役隔离**——标 `_DEPRECATED` 或移入 `_作废/`，在 §5 顶挂红字，同步 §4 与 `STATUS.md`。
8. **谁做的要留痕**——任务卡和 `STATUS.md` 写明工具、模型、家族和日期；家族按模型名写，未知写 `UNKNOWN`（不算复核通过）；论文结论/头条数字类复核须跨模型家族。
9. **关键测量双源交叉**——用失效模式不同的路径复算；不一致记 `UNKNOWN` 并停下游。
10. **哈希只记判据依赖的对象**——只给交付物、声称未改的输入记哈希，开工收尾比对，不给每份日志逐个算。

## 核心工作流（5 步）

`① 委派 → ② 执行 + 自检 → ③ 独立复核 → ④ 接收入库 → ⑤ handoff 落盘`

| 产物类型 | 示例 | 复核要求 |
|---|---|---|
| 纯文本/格式类 | 写作、格式转换、数据搬运 | 自检 + 脚本核数；成品可选一次阶段通读 |
| 分析/建模/参数选定 | 模型拟合、参数调优、样本清洗 | **必须独立复核** |
| 论文结论/头条数字 | 端点均值、百分比变化、方向判定 | **必须跨模型家族独立复核** |
| 数据整理/可视化 | CSV 清洗、图表生成 | 有自动化闸门并重开交付物核对时自检够 |

- **① 委派**：主控默认只读探查、出卡、答疑、收口，不亲自执行（用户明确要求或属单句/格式级小改除外，门槛见 `文档/协作规矩.md`）；只有 `⬜可派` 的卡可派，未裁定的标 `🟠待裁定（不可派）`。研究/分析类任务在结果出来前写死判读规则，不因结果改动；产出先落候选文件。
- **② 执行 + 自检**：开工改 `⏳执行中`；过闸门时**必须用脚本重开最终交付物本身**核对（导出图和日志不算）；发现卡面实质有错有权停下质疑（质疑不计为失败），程序性出入记“偏离”继续。
- **③ 独立复核**：复核方结论与执行方同等需可证伪证据；先查身份（论文结论/头条数字类同家族即停），再**先冷读成品**（核查类先用脚本自列全量清单），后对照卡面独立写代码重算；报告意见分 `## 会出错`（写出错场景）与 `## 建议`，末尾单独一行 `PASS` 或 `NEEDS_FIX`；**只按“会出错”返工**，最多 3 轮（细则见 `文档/协作规矩.md`）。
- **④ 接收入库 & ⑤ handoff 落盘**：主控执行“收口三查”（读“没做什么”与“会出错” → 脚本重开核交付物 → 同步入口与索引），更新 `来源.txt` / `scripts/README.md`；推翻或暂停结论时同步在 TL;DR 和故事段挂红旗。
- **两层续接**：**硬续接（主依赖）**靠仓库 Markdown 真相源；**软续接（增强）**靠工具记忆层加速检索，但核心结论必须落回 Markdown（判据：删光记忆层，下个 agent 只靠仓库 Markdown 也能接上）。

## 参考文档与自定义提醒

- **参考文档**：[`references/install.md`](references/install.md)（各工具安装路径） · [`references/multi_line.md`](references/multi_line.md)（并列多线课题） · [`references/advanced.md`](references/advanced.md)（标准委派话术、模型战绩表 `模型战绩.csv`、卡头任务契约四行、ADR/config/环境锁/数字审计等） · [`references/example_filled_AGENTS.md`](references/example_filled_AGENTS.md)（完整填好范例）。
- **自定义裁剪**：模板占位符统一为 `【待填】`；纯前端项目可简化 §5.5 工作盘，小项目跳过可选文件；薄指针内容保持统一，勿覆盖用户已有 `AGENTS.md`。

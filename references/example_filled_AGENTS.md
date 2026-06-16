# 填好的 AGENTS.md 样例（完整范例）

> 对照这个范例填你自己的 AGENTS.md——比空模板直观得多。
> 这是一个**虚构的工程项目**，仅用作样例；所有数据、路径、人名均为示例。

---

# AGENTS.md — 项目入口（任何智能体进到本文件夹，先读我）

> **一句话**：河床演变对桥梁基础冲刷的影响评估——基于多期 DEM 差分 + 水文模型。目标投《水利学报》或同级别中文期刊。别耽误主线的桥梁安全评估截止日期。

> ✅ **进门仪式**：读完本文件后，确认你已理解——①北极星（§1）②当前阶段和阻塞（§3）③受哪些铁律约束（§5–5.5）。之后每个子 agent 进入同样先读本文件再动手。

## 1. 北极星 / 当前故事（2026-06-10 与导师沟通定）
- **① 冲刷深度与桥墩稳定**：用两期 DEM 差分量化河床下切量，结合水力学公式评估桥墩安全系数。
- **② 关键发现**：2018-2025 年间桥址断面平均下切 1.2m，主墩位置局部冲刷 2.8m，已接近设计安全阈值。
- **权威背书**：参考《公路桥涵地基与基础设计规范》(JTG 3363-2019) + 前人区域冲刷研究报告。
- **差异化卖点**：高精度无人机 DEM（5cm 分辨率）差分 vs 传统断面测深——空间覆盖全、可出等值线图。

## 2. 方法 / 引擎
- 无人机航测 → Pix4D 建模 → CloudCompare DEM 差分 → HEC-RAS 水力学模拟 → 安全系数评估。
- 核心数据底座：两期 DEM（2018 洪水前、2025 洪水后）+ 上游水文站 30 年流量序列。

## 3. 现在在哪（每次收工更新）
- ✅ 2026-06-15：两期 DEM 差分完成，桥址段等值线图已出（`outputs/dem_diff_bridge.tif`）。
- ✅ 2026-06-14：水文数据已下载并清洗（`data/flow_daily_1990-2025.csv`）。
- ⏳ 正在进行：HEC-RAS 模型建好但未率定——等拿到实测断面数据。
- **阻塞**：
  - 实测断面数据缺失（桥址段 2019 年大修后未复测）——已联系管理所，预计 6 月 20 日前拿到。详见 `reports/missing_data.md`。
  - 无其他阻塞。

## 4. 下一步任务看板（细则见 `文档/任务规划_桥梁冲刷评估.md`）
- [x] **T1 UAV 航测与 DEM 生成** —— ✅完成 2026-06-10
- [x] **T2 DEM 差分分析** —— ✅完成 2026-06-15
- [x] **T3 水文数据整理** —— ✅完成 2026-06-14
- [ ] **T4 HEC-RAS 水力学建模**（依赖 T3，⏳进行中——阻塞：缺实测断面）
- [ ] **T5 安全系数评估与论文初稿**（依赖 T4）

## 5. 铁律 / 约定（违反会出错或返工）
- 原始 DEM（两期）在 `data/dem_raw/`，**只读**。
- UAV 建模用 Metashape env（`D:\software\conda\envs\metashape\python.exe`），水文分析用 `hydrology` env。**两套环境不可混用**（GIS 相关 DLL 冲突）。
- 中文图内 μ、±、² 等字符用 mathtext 渲染，SimHei 缺这些字形会显方框。
- **代码归位**：Python 脚本放 `scripts/`，每加一个同步更新 `scripts/README.md`。R 脚本放 `scripts/r/`。
- **收工规矩**：每个 agent 结束时更新 §3/§4 + 更新 `STATUS.md`。

## 5.5 路径约定（重要：避免 OneDrive 同步爆炸）
项目根 `F:\research\bridge_scour` 在 OneDrive 里同步。大文件不进根目录：

| 目录 | 用途 |
|---|---|
| `F:\research\bridge_scour\` | 小产物（CSV、PNG、脚本、md）|
| `F:\scratch\bridge\` | 大体积（DEM tif ~5GB、HEC-RAS 模型中间文件）|
| `F:\scratch\bridge\cache\` | 临时缓存 |

- 判据：单个 >50MB → scratch。

## 6. 深读指针
- **任务细则**：`文档/任务规划_桥梁冲刷评估.md`
- **关键决策**：`文档/决策记录/2026-06-10_选DEM差分还是断面法.md`（定了 DEM 差分方案，弃了传统断面测深）
- **词汇表**：`文档/词汇表.md`
- **委派任务话术**：`文档/委派任务模板.md`
- 数据溯源：`data/dem_raw/来源.txt`、`data/hydrology/来源.txt`

## 7. 环境 / 工具

| 环境 | python.exe 路径 | 用途 |
|---|---|---|
| base | `D:\software\anaconda3\python.exe` | 通用数据分析、pandas、matplotlib |
| hydrology | `D:\software\anaconda3\envs\hydrology\python.exe` | HEC-RAS 前后处理、水文分析 |
| metashape | `D:\software\conda\envs\metashape\python.exe` | UAV 航测建模（Agisoft Metashape API）|

- conda: `D:\software\anaconda3\condabin\conda.bat`
- 版本锁：`environment.yml`

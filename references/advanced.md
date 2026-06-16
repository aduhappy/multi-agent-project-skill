# 进阶板块（项目变大时按需启用）

> 核心七板块之外的可选增强。**不要一上来全堆**——小项目用不上，反而让入口变臃肿。
> 启用时，在 AGENTS.md §6 深读指针里放一行指针即可，主体内容下沉到本文件对应的文档。

## 1. 决策记录 ADR（Architecture Decision Record）
记"为什么选 A 不选 B、为什么弃用某方法"。价值：防止下个 agent 重新踩坑、重新质疑已定的事。

放 `文档/决策记录/<日期>_<主题>.md`，每条格式：
```markdown
# 决策：<一句话结论>
- 日期：YYYY-MM-DD
- 状态：采纳 / 已废弃 / 待定
- 背景：<遇到了什么问题>
- 选项：A... / B... / C...
- 决定：选 A
- 理由：<为什么，关键证据 / 谁拍板>
- 影响：<要改哪些代码 / 数据 / 流程>
```
在 AGENTS.md §2 或 §6 放一行指针："关键决策见 `文档/决策记录/`"。

## 2. 词汇表 / 缩写表
项目特有术语容易让新 agent 困惑。放 `文档/词汇表.md`：
```markdown
- <术语A> = <全称/定义>
- <缩写B> = <含义，尤其和通用义不同的项目特有口径>
- <易混淆对> = ...（如：X vs Y 的口径差异在哪里）
```
入口 §6 放指针。

## 3. 进度日志（带日期戳的变更流水）
比 AGENTS.md §3"现在在哪"更细。放 `进度日志.md`，**最新在上**：
```markdown
## YYYY-MM-DD
- 完成数据集 X 的下载清洗（N 条），落在 <路径>
- 发现数据问题 N 行，T2 须标记
- 方向/口径定案（决策来源：<谁/哪次会>）
```
§3 只保留"最新 1–5 条 + 指针 → 完整流水看 `进度日志.md`"。

## 4. 验收具体化（Definition of Done）
任务卡的"验收"字段**不要写"完成就行"**，要写成可运行检查：
- `python scripts/check_<quality>.py` → 输出某一致性指标全 < 阈值
- 图：X/Y 轴有中文标题、无缺字方框、分辨率 ≥ 300 dpi
- CSV：列名、行数、单位符合 schema
判据：换个 agent 跑同样检查能复现"通过/不通过"。

## 5. 标准 handoff 摘要格式
agent 收工时（除更新 AGENTS.md 外）给下任留一段结构化 handoff：
```markdown
## Handoff（YYYY-MM-DD，agent: xxx）
- 现状：<1–3 条>
- 下一步：<T3 关系建模，输入是 X，输出落在 Y>
- 未解决风险：<守恒偏差未清；某 env 装包失败>
- 关键文件路径：<3–5 个最重要的>
- 阻塞：<需用户确认 Z>
```
配合记忆层（ChatMem 等）用，但结论要落回 Markdown。

## 6. 命名约定 + 幂等性
- 输出文件命名带版本/日期/坐标系：`<output>_v1_20260615.tif`、`Fig_<topic>_<var>.png`，避免多 agent 产出同名覆盖。
- 长管线脚本**幂等**：有缓存（如已裁好的栅格）就跳过重算，重跑不从头开始。脚本开头：
  ```python
  import os, sys
  CACHE = r'F:\xxx_cache'
  os.makedirs(CACHE, exist_ok=True)
  FLAG = os.path.join(CACHE, 'done.flag')
  if os.path.exists(FLAG):
      print('skip (cached)'); sys.exit(0)
  # ... 干活 ...
  open(FLAG, 'w').close()
  ```
- 中间产物路径写常量置顶，方便核查与改盘。

## 7. 环境锁（防跨机器漂移）
anaconda env 的包版本钉死，避免换机器重建时漂移：
```bash
D:\software\...\condabin\conda.bat env export -n dlcm > environment.yml
```
把 `environment.yml` 进项目（小文件）。AGENTS.md §7 放路径，`environment.yml` 放版本。

## 8. 数据快照 / 不可变输入
- 原始数据**只读**，所有 agent 在副本上动。
- 数据集目录放 `来源.txt`（见模板）+ 可选 `manifest.txt`（文件名 + md5），校验没被改过。
- 判据：删掉所有中间产物，能从"原始 + 脚本"完整重跑出同样结果（可复现）。

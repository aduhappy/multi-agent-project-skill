# 脚本索引

> 每个脚本一行：**文件名 / 一句话干嘛 / 输入 / 输出 / 谁写的**。
> 新增脚本时同步更新此文件。这是零上下文 agent 快速定位入口的法宝。

| 脚本 | 干什么 | 输入 | 输出 | 作者 |
|---|---|---|---|---|
| `handoff_lib.py` | 共享 Markdown 块级解析、日期提取与目录配置库（供各脚本调用） | Markdown 文本、`handoff_config.json` | 结构化块与解析结果 | multi-agent-project |
| `check_handoff.py` | 收工交接自检（H001–H009 阻断项 + A001–A018 提醒项，支持 `--role`） | 项目根或线目录 | 终端检查报告与退出码 | multi-agent-project |
| `archive_status.py` | 一键归档 `STATUS.md` 旧交接段与 `AGENTS.md` §3 旧快照（保留在用卡交接段） | `STATUS.md`、`AGENTS.md` | `文档/*_归档_至<日期>.md` 与瘦身后入口 | multi-agent-project |
| `sync_board.py` | 从任务卡自动生成并同步 `AGENTS.md` §4 看板与索引卡清单表（只动标记内） | `文档/任务卡/*.md` | 更新标记内看板与索引表（支持 `--check`） | multi-agent-project |
| `upgrade.py` | 将已有 0.3.x/0.4.x 骨架升级到当前布局（默认仅预览，绝不写入口/卡/STATUS） | 项目根、技能 `assets/` | 更新脚本与规矩、备份旧件、打印手工清单 | multi-agent-project |
| `fingerprint.py` | 记录目录/文件的 SHA-256 指纹快照并比对新增、删除、改动 | 目标目录或快照 JSON | 快照 JSON 或差异汇总（支持 `--check`） | multi-agent-project |
| `run_main.py` | 【待填】 | 【待填】 | 【待填】 | 【待填】 |

## 已废弃 / 中间版

| 脚本 | 说明 | 替代者 |
|---|---|---|
| `【待填】` | 【待填】 | `【待填】` |

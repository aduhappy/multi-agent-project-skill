# 安装说明（用户让你“装这个 skill”时自主执行）

来源仓库：`https://github.com/aduhappy/multi-agent-project-skill`。clone 到本工具的 skills 目录即装好（纯 Markdown + Python 标准库脚本，无第三方依赖）。

> ⚠️ **目标目录名必须是 `multi-agent-project`（与 `SKILL.md` 的 `name:` 一致），不是仓库名 `multi-agent-project-skill`。**
> Claude Code / Codex 按**目录名**识别 skill——直接 `git clone <URL>` 会得到 `multi-agent-project-skill/`，与 `name` 不匹配。clone 时**显式指定目标目录**：`git clone <URL> ~/.claude/skills/multi-agent-project`。

**不同工具的 skills 目录不同，请按工具选对路径（末段目录名统一为 `multi-agent-project`）**：

| 工具 | 用户级安装路径 | 项目级安装路径 |
|---|---|---|
| **ZCode / Codex CLI** | `~/.agents/skills/multi-agent-project` | `<项目>/.agents/skills/multi-agent-project` |
| **Claude Code** | `~/.claude/skills/multi-agent-project` | `<项目>/.claude/skills/multi-agent-project` |
| **Cursor** | N/A（用 rules） | `.cursor/rules/`（现代格式）或 `.cursorrules`（legacy） |

通用原则：
- Windows 下 `~` = `%USERPROFILE%`。
- 用户级 vs 项目级拿不准时默认**用户级**（装一次处处可用）。
- 目录不存在先创建再 clone；clone 时把目标目录名钉成 `multi-agent-project`。clone 完告诉用户**新开一个会话**即可触发本 skill。

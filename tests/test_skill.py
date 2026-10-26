#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Smoke test for check_handoff.py: builds a tiny root index + line in a temp dir."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "assets" / "check_handoff.py"
TODAY = "2026-09-15"


def run(root: Path, *args: str) -> tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run(
        [sys.executable, "-B", str(CHECKER), str(root), "--today", TODAY, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    return result.returncode, result.stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(root: Path) -> Path:
    line = root / "03_paper"
    write(root / "AGENTS.md", "# AGENTS\n\n> **Scope: index**\n\n| 线 | 入口 |\n|---|---|\n| 论文 | `03_paper/AGENTS.md` |\n")
    write(line / "AGENTS.md",
          "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n> - **当前阶段**：初稿（2026-09-15）\n> - **下一步**：写方法\n> - **阻塞**：无\n\n"
          "## 3. 现在在哪\n- 2026-09-15：初稿完成\n\n## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n"
          "## 4. 任务看板\n- [x] T1 初稿\n- [ ] T2 方法\n")
    write(line / "STATUS.md", "# STATUS\n\n## Handoff（2026-09-15）\n- 本次做了什么：写完初稿，动了草稿文件，没有阻塞。\n")
    write(line / "CLAUDE.md", "# 本项目的权威入口是 AGENTS.md\n")
    return line


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        line = build(root)

        rc, out = run(root, "--scope", "index")
        check(rc == 0, "root index should pass:\n" + out)
        rc, out = run(line)
        check(rc == 0, "filled line should pass:\n" + out)

        write(line / "STATUS.md", "# STATUS\n\n## Handoff（2026-09-14）\n- 旧交接。\n\n## 2026-09-15 主控：补一段\n- 本次做了什么：改了看板。\n")
        rc, out = run(line)
        check(rc == 0, "newer non-Handoff heading must count for H006:\n" + out)
        write(line / "STATUS.md", "# STATUS\n\n## Handoff（2026-09-14）\n- 只有旧交接，内容写满五十个字以上，免得被当成模板。本次做了什么：写完初稿。\n")
        rc, out = run(line)
        check(rc == 1 and "[H006] ❌" in out, "STATUS older than §3 must fail:\n" + out)
        write(line / "STATUS.md", "# STATUS\n\n## 归档说明（旧段已移至 2026-09-15 归档文件）\n- 见归档。\n\n## Handoff（2026-09-14）\n- 只有旧交接，内容写满五十个字以上，免得被当成模板。本次做了什么：写完初稿。\n")
        rc, out = run(line)
        check(rc == 1 and "[H006] ❌" in out, "archive-note heading must not count as a handoff date:\n" + out)
        write(line / "STATUS.md", "# STATUS\n\n## Handoff（2026-09-15）\n- 本次做了什么：写完初稿，动了草稿文件，没有阻塞。\n")

        rc, out = run(line, "--scope", "index")
        check(rc == 1 and "[I002] ❌" in out, "line misused as index must fail:\n" + out)
        rc, out = run(root)
        check(rc == 1 and "[H002] ❌" in out, "root misused as line must fail:\n" + out)

        rc, out = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-10-20"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        ).returncode, ""
        check(rc == 1, "stale §3 date must fail")

        card = line / "文档" / "任务卡" / "T2_方法.md"
        write(card, "# T2 方法\n\n## 📋 执行方派发提示词\n```text\n做\n```\n")
        rc, out = run(line)
        check(rc == 0 and "[A005] ⚠️" in out and "T2_方法.md" in out, "card without reviewer prompt must warn A005:\n" + out)
        write(card, "# T2 方法\n\n## 📋 执行方派发提示词\n```text\n做\n```\n\n## 📋 独立复核方派发提示词\n```text\n核\n```\n")
        rc, out = run(line)
        check(rc == 0 and "[A005] ✅" in out, "card with both prompts must pass A005:\n" + out)
        check("[A006] ✅" in out, "small card with two prompts must pass A006:\n" + out)
        extra = "".join(f"\n## 📋 返修提示词 {i}\n```text\n改\n```\n" for i in range(2))
        write(card, card.read_text(encoding="utf-8") + extra)
        rc, out = run(line)
        check(rc == 0 and "[A006] ⚠️" in out and "4 段提示词" in out, "card with 4 prompts must warn A006:\n" + out)
        write(card, "# T2 方法\n\n## 📋 执行方提示词（整段复制）\n```text\n做\n```\n\n## 📋 复核方提示词\n```text\n核\n```\n"
              "\n## 📋 续跑执行方提示词\n```text\n续\n```\n\n## 📋 签核指令（整段复制）\n```text\n签\n```\n")
        rc, out = run(line)
        check("[A005] ✅" in out, "prompt headings without 派发 must still count for A005:\n" + out)
        check("[A006] ⚠️" in out and "4 段提示词" in out, "📋 heading without 提示词 must count for A006:\n" + out)

        agents = (line / "AGENTS.md").read_text(encoding="utf-8")
        write(card, "# T2 方法\n\n## 进度回写（执行方、复核方只改这一节）\n\n- 状态：✅已收口（D-02）\n- 执行方：略\n\n"
              "## 📋 执行方提示词\n```text\n做\n```\n\n## 📋 复核方提示词\n```text\n核\n```\n")
        write(line / "文档" / "任务卡_README.md", "| 卡 | 做什么 | 状态 | 文件 |\n|---|---|---|---|\n"
              "| T2 | 方法 | ✅已收口（D-02） | `任务卡/T2_方法.md` |\n")
        write(line / "AGENTS.md", agents.replace("- [ ] T2 方法", "- [x] **T2 方法** —— 已收口（D-02）"))
        rc, out = run(line)
        check(rc == 0 and "[A007] ✅" in out and "[A008] ✅" in out, "closed card synced everywhere must pass A007/A008:\n" + out)
        check("[A009] ✅" in out and "[A010] ✅" in out, "short 进度回写 rows and short §3 must pass A009/A010:\n" + out)
        write(line / "AGENTS.md", agents.replace("- [ ] T2 方法", "- [ ] 🟡 **T2 方法** —— 已交回").replace(
            "- 2026-09-15：初稿完成\n", "- 2026-09-15：初稿完成\n- 🟡 **T2 已交回待审查**（2026-09-14）\n"
            + "".join(f"- 2026-09-1{i}：第 {i} 条\n" for i in range(5))))
        rc, out = run(line)
        check(rc == 0 and "[A007] ⚠️" in out and "T2 卡面 ✅／§4 未勾" in out, "closed card unticked on §4 must warn A007:\n" + out)
        check("[A008] ⚠️" in out and "§3 7 条" in out and "待审查：T2" in out, "long §3 with stale 待审查 must warn A008:\n" + out)
        synced = agents.replace("- [ ] T2 方法", "- [x] **T2 方法** —— 已收口（D-02）")
        write(line / "AGENTS.md", synced)
        write(line / "文档" / "任务卡_README.md", "| 卡 | 做什么 | 状态 | 文件 |\n|---|---|---|---|\n"
              "| T2 | 方法 | ⬜可派（D-02） | `任务卡/T2_方法.md` |\n")
        rc, out = run(line)
        check(rc == 0 and "[A007] ⚠️" in out and "索引" in out and "[A008] ✅" in out, "index-only drift must warn A007 only:\n" + out)
        write(line / "文档" / "任务卡_README.md", "| 卡 | 做什么 | 状态 | 文件 |\n|---|---|---|---|\n"
              "| T2 | 方法 | ✅已收口（D-02） | `任务卡/T2_方法.md` |\n")
        write(line / "AGENTS.md", synced.replace("- 2026-09-15：初稿完成\n", "- 2026-09-15：初稿完成\n"
              + "".join(f"- 2026-09-1{i}：第 {i} 条\n" for i in range(5))))
        rc, out = run(line)
        check(rc == 0 and "[A008] ⚠️" in out and "§3 6 条" in out and "待审查：" not in out and "[A007] ✅" in out,
              "long §3 alone must warn A008 only:\n" + out)
        for stale_line in ("- 🟡 **T2 已交回待审查**（2026-09-14）\n", "- 2026-10-24：T2 已交回待审查\n"):
            write(line / "AGENTS.md", synced.replace("- 2026-09-15：初稿完成\n", "- 2026-09-15：初稿完成\n" + stale_line))
            rc, out = run(line)
            check(rc == 0 and "[A008] ⚠️" in out and "§3 2 条" in out and "待审查：T2" in out and "[A007] ✅" in out,
                  "stale 待审查 alone must warn A008 only:\n" + out)
        card_base = card.read_text(encoding="utf-8")
        row = "- 执行方："
        for size, expect in ((300, "✅"), (301, "⚠️")):
            write(card, card_base.replace("- 执行方：略", row + "字" * (size - len(row))))
            rc, out = run(line)
            check(rc == 0 and f"[A009] {expect}" in out and ("T2_方法.md「执行方」行 301 字" in out) == (size == 301),
                  f"进度回写 row of {size} chars must give A009 {expect} only above 300:\n" + out)
        write(card, card_base)

        base = "- 2026-09-15：初稿完成"
        for size, expect in ((600, "✅"), (601, "⚠️")):
            write(line / "AGENTS.md", agents.replace(base, base + "字" * (size - len(base))))
            rc, out = run(line)
            check(rc == 0 and f"[A010] {expect}" in out and ("第 1 条" in out) == (size == 601),
                  f"§3 item of {size} chars must give A010 {expect} only above 600:\n" + out)
        write(line / "AGENTS.md", agents.replace(base, base + "\n  - 缩进续行" + "字" * 590))
        rc, out = run(line)
        check(rc == 0 and "[A010] ⚠️" in out, "indented continuation lines must count toward the §3 item:\n" + out)

        write(line / "AGENTS.md", agents)
        write(line / "文档" / "任务卡_README.md", "# 索引\n" + "| T | 很长的说明 |\n" * 1200)
        rc, out = run(line)
        check(rc == 0 and "[A003] ⚠️" in out and "任务卡_README.md" in out, "oversized card index must warn A003:\n" + out)

        write(line / "STATUS.md", "# STATUS\n\n## Handoff（YYYY-MM-DD）\n- 【待填】\n")
        rc, out = run(line)
        check(rc == 1 and "[H005] ❌" in out, "template STATUS must fail:\n" + out)

        (line / "CLAUDE.md").write_text("以 README.md 为准，AGENTS.md 已废弃。\n", encoding="utf-8")
        rc, out = run(line)
        check("[H007] ❌" in out, "retired pointer must fail:\n" + out)
    print("All skill self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Smoke and regression tests for check_handoff.py, archive_status.py, and skill assets."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "assets" / "check_handoff.py"
ARCHIVER = REPO / "assets" / "archive_status.py"
TODAY = "2026-09-15"


def run(root: Path, *args: str) -> tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run(
        [sys.executable, "-B", str(CHECKER), str(root), "--today", TODAY, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    return result.returncode, result.stdout


def run_archiver(root: Path, *args: str) -> tuple[int, str, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run(
        [sys.executable, "-B", str(ARCHIVER), str(root), "--today", TODAY, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    return result.returncode, result.stdout, result.stderr


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


def test_asset_sizes() -> None:
    for rel, limit in (
        ("SKILL.md", 15_000),
        ("assets/任务卡_README.md", 15_000),
        ("assets/任务规划_模板.md", 15_000),
    ):
        fp = REPO / rel
        size = len(fp.read_bytes())
        check(size <= limit, f"{rel} exceeded {limit} bytes: {size}B")


def test_040_features() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        line = build(root)

        # --- A4: A006 lists largest 3 sections when card > 15KB (and ignores fenced ## headings) ---
        big_card = line / "文档" / "任务卡" / "T2_方法.md"
        write(
            big_card,
            "# T2 方法\n\n"
            "## 进度回写\n- 状态：⬜可派\n\n"
            + "## 第一大节\n" + ("甲" * 3200) + "\n\n"
            + "## 第二大节\n" + ("乙" * 2000) + "\n\n"
            + "## 📋 执行方派发提示词\n````text\n做\n## 假标题不能算独立节\n" + ("丙" * 1200) + "\n````\n\n"
            + "## 📋 独立复核方派发提示词\n````text\n核\n````\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A006] ⚠️" in out, "oversized card must warn A006:\n" + out)
        check(
            "最大三节：「第一大节」" in out and "「第二大节」" in out and "「📋 执行方派发提示词」" in out,
            "A006 must list largest 3 sections in order:\n" + out,
        )
        check("假标题" not in out, "fenced ## heading inside 4-backtick prompt must not be treated as a section:\n" + out)
        big_card.unlink()

        # --- A2: A011 latest handoff <= 800 chars and 4 sections present ---
        handoff_prefix = (
            "## Handoff（2026-09-15）\n"
            "- **谁做的**：工具 Antigravity / 模型 Gemini / 家族 Google；角色：执行方\n"
            "- **改了什么**：完成初稿。\n"
            "- **怎么验证的**：`python check.py` 输出 OK。\n"
            "- **没做什么**：无。\n"
            "- **不确定处**："
        )
        for target_len, expect in ((800, "✅"), (801, "⚠️")):
            pad = "字" * (target_len - len(handoff_prefix))
            write(line / "STATUS.md", "# STATUS\n\n" + handoff_prefix + pad + "\n")
            rc, out = run(line)
            check(
                rc == 0 and f"[A011] {expect}" in out,
                f"handoff of {target_len} chars must give A011 {expect}:\n" + out,
            )
            if target_len == 801:
                check("801 字（超 800 字）" in out, "A011 must report 801 chars over limit:\n" + out)

        # Missing one of the 4 sections (怎么验证的)
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-09-15）\n"
            "- **谁做的**：主控\n- **改了什么**：建卡。\n- **没做什么**：无。\n- **不确定处**：无。\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A011] ⚠️" in out and "缺节：怎么验证的" in out,
              "handoff missing 怎么验证的 must warn A011:\n" + out)

        # Subheading `### ` form + template trailing `> ⚠️` note must also pass A011
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-09-15）\n"
            "- **谁做的**：执行方\n"
            "### 改了什么\n新增脚本。\n"
            "### 怎么验证的\n`pytest` 0 failed。\n"
            "### 没做什么\n无。\n"
            "### 不确定处\n无。\n\n"
            "> ⚠️ 任务执行中以任务卡“进度回写”为准。\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A011] ✅" in out, "### 4-section handoff with trailing template note must pass A011:\n" + out)

        # --- A3: A012 review report trailing standalone PASS / NEEDS_FIX ---
        rc, out = run(line)
        check("[A012] ✅" in out and "暂无复核报告" in out, "no review files must pass A012:\n" + out)

        rev1 = line / "文档" / "T1_独立复核_GLM_2026-09-15.md"
        rev2 = line / "文档" / "T2_复核_Gemini_2026-09-15.md"
        card_with_fuhe = line / "文档" / "任务卡" / "T3_口径复核.md"
        deprecated_rev = line / "文档" / "_作废" / "T0_复核_old.md"

        write(rev1, "# T1 复核\n\n## 会出错\n无\n\n## 建议\n无\n\nPASS\n\n")
        write(rev2, "# T2 复核\n\n## 会出错\n1. 错（出错场景：空输入崩溃）\n\n## 建议\n无\n\nNEEDS_FIX\n")
        write(card_with_fuhe, "# T3 口径复核\n\n## 📋 执行方派发提示词\n做\n\n## 📋 复核方派发提示词\n核\n")
        write(deprecated_rev, "# 旧复核\n没有结论行也不应报错\n")
        rc, out = run(line)
        check(rc == 0 and "[A012] ✅" in out and "2 份复核报告" in out,
              "PASS and NEEDS_FIX review reports (ignoring task card & _作废) must pass A012:\n" + out)

        write(rev2, "# T2 复核\n\n总体通过，无须返修。\n")
        rc, out = run(line)
        check(rc == 0 and "[A012] ⚠️" in out and "T2_复核_Gemini_2026-09-15.md" in out,
              "review report without PASS/NEEDS_FIX must warn A012:\n" + out)

        write(rev2, "# T2 复核\n\n结论：PASS\n")
        rc, out = run(line)
        check(rc == 0 and "[A012] ⚠️" in out and "T2_复核_Gemini_2026-09-15.md" in out,
              "non-standalone PASS line must warn A012:\n" + out)
        write(rev2, "# T2 复核\n\n## 会出错\n无\n\n## 建议\n无\n\nPASS\n")

        # --- A1: archive_status.py pass and fail cases ---
        arc_rc, _, _ = run_archiver(root / "does_not_exist")
        check(arc_rc == 2, "archive_status on missing dir must exit 2")
        arc_rc, _, _ = run_archiver(line, "--keep", "0")
        check(arc_rc == 2, "archive_status with --keep 0 must exit 2")
        empty_dir = root / "empty_dir"
        empty_dir.mkdir()
        arc_rc, _, _ = run_archiver(empty_dir)
        check(arc_rc == 2, "archive_status on dir without STATUS/AGENTS must exit 2")

        # No-op when <= 10 handoffs and <= 5 §3 items
        before_status = (line / "STATUS.md").read_text(encoding="utf-8")
        arc_rc, arc_out, _ = run_archiver(line)
        check(arc_rc == 0 and "无需归档" in arc_out, "small STATUS must no-op cleanly:\n" + arc_out)
        check((line / "STATUS.md").read_text(encoding="utf-8") == before_status, "no-op must not touch STATUS.md")

        # Oversized STATUS.md (> 40KB, 14 sections from 2026-09-02 to 2026-09-15)
        many_blocks = []
        for day in range(2, 16):
            d_str = f"2026-09-{day:02d}"
            filler = "内" * (1100 if day < 15 else 80)
            many_blocks.append(
                f"## Handoff（{d_str}，T{day}）\n"
                f"- **谁做的**：执行方\n"
                f"- **改了什么**：第 {day} 轮产物 {filler}\n"
                f"- **怎么验证的**：`python verify.py` 通过\n"
                f"- **没做什么**：无\n"
                f"- **不确定处**：无"
            )
        write(line / "STATUS.md", "# STATUS.md — 增量 Handoff\n\n> 只记增量。\n\n" + "\n\n".join(many_blocks) + "\n")
        check(len((line / "STATUS.md").read_bytes()) > 40_000, "fixture STATUS.md must exceed 40KB")
        rc, out = run(line)
        check(rc == 0 and "[A003] ⚠️" in out and "STATUS.md" in out and "archive_status.py" in out,
              "oversized STATUS must warn A003 and suggest archive_status.py:\n" + out)

        # Dry-run must not write
        arc_rc, arc_out, _ = run_archiver(line, "--dry-run")
        check(arc_rc == 0 and "[DRY-RUN]" in arc_out, "dry-run must print preview:\n" + arc_out)
        check(len((line / "STATUS.md").read_bytes()) > 40_000, "dry-run must not shrink STATUS.md")

        # Actual archive (default --keep 10): archives 4 sections (09-02..09-05), keeps 10 (09-06..09-15)
        arc_rc, arc_out, _ = run_archiver(line)
        check(arc_rc == 0 and "已归档 4 段" in arc_out, "must archive 4 oldest sections:\n" + arc_out)
        new_st = (line / "STATUS.md").read_text(encoding="utf-8")
        check(len(new_st.encode("utf-8")) < 40_000, "archived STATUS.md must be under 40KB")
        check("> 更早的交接段已归档到 `文档/STATUS_归档_至2026-09-05.md`。" in new_st,
              "STATUS.md must contain > blockquote reference to archive file:\n" + new_st[:400])
        arch_file = line / "文档" / "STATUS_归档_至2026-09-05.md"
        check(arch_file.is_file(), "archive file must be created")
        arch_text = arch_file.read_text(encoding="utf-8")
        for day in (2, 3, 4, 5):
            check(f"2026-09-{day:02d}" in arch_text and f"2026-09-{day:02d}，T{day}" not in new_st,
                  f"day {day} must move from STATUS.md to archive file")
        for day in range(6, 16):
            check(f"2026-09-{day:02d}，T{day}" in new_st, f"recent day {day} must stay in STATUS.md")

        rc, out = run(line)
        check(rc == 0 and "[A003] ✅" in out and "[A011] ✅" in out and "[H006] ✅" in out,
              "post-archive line must pass H006, A003, and A011:\n" + out)

        # Second archive: first test same-day append (two sections dated 2026-09-05), then different-day link append
        cur_st = (line / "STATUS.md").read_text(encoding="utf-8").replace("2026-09-06，T6", "2026-09-05，T6_补")
        write(line / "STATUS.md", cur_st)
        arc_rc, _, _ = run_archiver(line, "--keep", "9")
        check(arc_rc == 0, "same-day append archive must succeed")
        same_day_text = arch_file.read_text(encoding="utf-8")
        check("2026-09-02，T2" in same_day_text and "2026-09-05，T6_补" in same_day_text,
              "same-day archive must append without overwriting earlier archived sections")
        check((line / "STATUS.md").read_text(encoding="utf-8").count("STATUS_归档_至2026-09-05.md") == 1,
              "same-day archive must not duplicate > reference link in STATUS.md")

        arc_rc, _, _ = run_archiver(line, "--keep", "8")
        check(arc_rc == 0, "third archive run must succeed")
        second_arch = line / "文档" / "STATUS_归档_至2026-09-07.md"
        check(second_arch.is_file() and "2026-09-07" in second_arch.read_text(encoding="utf-8"),
              "third archive must write new dated file")
        check(
            "`文档/STATUS_归档_至2026-09-05.md`、`文档/STATUS_归档_至2026-09-07.md`"
            in (line / "STATUS.md").read_text(encoding="utf-8"),
            "existing > archive quote line must append second archive link cleanly",
        )

        # AGENTS.md §3 archiving when §3 exceeds 5 items (8 snapshots + 1 阻塞 = 9 items -> keeps 4 + 1 = 5 items)
        sec3_many = "\n".join(f"- ✅ 2026-09-{d:02d}：完成里程碑 {d}" for d in range(8, 16))
        write(
            line / "AGENTS.md",
            "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n> - **当前阶段**：初稿（2026-09-15）\n> - **下一步**：写方法\n> - **阻塞**：无\n\n"
            f"## 3. 现在在哪\n{sec3_many}\n- **阻塞**：无\n- `→ 本轮增量 handoff 见 STATUS.md`\n\n"
            "## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n"
            "## 4. 任务看板\n- [x] T1 初稿\n- [ ] **T3 口径复核**\n",
        )
        rc, out = run(line)
        check("[A008] ⚠️" in out and "§3 9 条" in out, "9 bullets in §3 must warn A008 before archive:\n" + out)
        arc_rc, arc_out, _ = run_archiver(line)
        check(arc_rc == 0 and "AGENTS.md §3：已归档 4 条" in arc_out, "must archive 4 oldest §3 items:\n" + arc_out)
        agents_arch = line / "文档" / "AGENTS_归档_至2026-09-11.md"
        check(agents_arch.is_file() and "里程碑 8" in agents_arch.read_text(encoding="utf-8"),
              "AGENTS §3 archive file must contain oldest milestones")
        new_agents = (line / "AGENTS.md").read_text(encoding="utf-8")
        check("> 更早的 §3 快照已归档到 `文档/AGENTS_归档_至2026-09-11.md`。" in new_agents,
              "AGENTS.md §3 must include > archive quote line:\n" + new_agents)
        rc, out = run(line)
        check(rc == 0 and "[H003] ✅" in out and "[A008] ✅" in out,
              "archived AGENTS.md §3 must pass H003 and A008:\n" + out)


def test_r1_a007_merged_inline_states() -> None:
    """Fix 1: §4 line listing multiple cards with inline status emojis checks each card individually."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        write(cards_dir / "T10g_报告.md", "# T10g\n\n## 进度回写\n- 状态：✅已收口\n")
        write(cards_dir / "T10h_图集.md", "# T10h\n\n## 进度回写\n- 状态：🗄️作废（由 T12g 接续）\n")
        write(cards_dir / "T12a_分析.md", "# T12a\n\n## 进度回写\n- 状态：✅已收口\n")
        write(cards_dir / "T12b_配图.md", "# T12b\n\n## 进度回写\n- 状态：✅已收口\n")
        write(
            cards_dir / "T12g_图集40页.md",
            "# T12g\n\n## 进度回写\n- 状态：🟡待复核\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        write(
            cards_dir / "T13b_技能升级.md",
            "# T13b\n\n## 进度回写\n- 状态：⏳执行中\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        write(cards_dir / "T10_MVP.md", "# T10\n\n## 进度回写\n- 状态：🗄️作废\n")

        merged_sec4 = (
            "## 4. 任务看板\n"
            "- [x] **T10 MVP** —— 🗄️ 作废\n"
            "- [ ] **T10g 报告**✅、**T10h 图集**🗄️（由 T12g 接续）、**T12g 图集 40 页**⬜、"
            "**T12a/b 结构版**✅、**T13b 技能 0.4.0**⬜　- [ ] **T11 二期**（依赖 T10）\n"
        )
        base_agents = (line / "AGENTS.md").read_text(encoding="utf-8")
        write(line / "AGENTS.md", base_agents.split("## 4. 任务看板")[0] + merged_sec4)
        rc, out = run(line)
        check(
            rc == 0 and "[A007] ✅" in out,
            "merged §4 line with synced inline emojis must pass A007 without false alarm on T10g:\n" + out,
        )

        # Drift on non-first card (T13b closed on card, still ⬜ inline on §4) AND slash card (T12b ⬜ on card, ✅ inline)
        write(cards_dir / "T13b_技能升级.md", "# T13b\n\n## 进度回写\n- 状态：✅已收口\n")
        write(
            cards_dir / "T12b_配图.md",
            "# T12b\n\n## 进度回写\n- 状态：⬜可派\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        rc, out = run(line)
        check(
            rc == 0 and "[A007] ⚠️" in out and "T13b 卡面 ✅／§4 ⬜" in out and "T12b 卡面 ⬜／§4 ✅" in out,
            "merged §4 line must detect drift on later cards and slash-grouped cards:\n" + out,
        )
        check("T10g 卡面" not in out, "synced first card T10g must still not be falsely flagged:\n" + out)


def test_r1_index_template_no_collision() -> None:
    """Fix 2: Fresh skeleton copying assets/任务卡_README.md + real T1 card (⬜可派) passes A007 on first run."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        index_asset = (REPO / "assets" / "任务卡_README.md").read_text(encoding="utf-8")
        write(line / "文档" / "任务卡_README.md", index_asset)
        write(
            line / "文档" / "任务卡" / "T1_数据清洗.md",
            "# T1 数据清洗\n\n## 进度回写\n- 状态：⬜可派\n\n"
            "## 📋 执行方派发提示词\n做\n\n## 📋 独立复核方派发提示词\n核\n",
        )
        base_agents = (line / "AGENTS.md").read_text(encoding="utf-8")
        write(
            line / "AGENTS.md",
            base_agents.split("## 4. 任务看板")[0] + "## 4. 任务看板\n- [ ] **T1 数据清洗**\n",
        )
        rc, out = run(line)
        check(
            rc == 0 and "[A007] ✅" in out and "[A005] ✅" in out,
            "fresh skeleton with verbatim 任务卡_README.md template and T1 ⬜ card must pass A007 & A005:\n" + out,
        )


def test_r1_a005_skips_closed_and_deprecated() -> None:
    """Fix 3: A005 ignores closed (✅) and deprecated (🗄️) cards whose prompts were deleted at closure."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        write(cards_dir / "T1_已收口无提示词.md", "# T1\n\n## 进度回写\n- 状态：✅已收口\n")
        write(cards_dir / "T1d_已作废无提示词.md", "# T1d\n\n## 进度回写\n- 状态：🗄️作废（D-21）\n")
        write(
            cards_dir / "T2_在用齐全.md",
            "# T2\n\n## 进度回写\n- 状态：⬜可派\n\n## 📋 执行方派发提示词\n做\n\n## 📋 独立复核方派发提示词\n核\n",
        )
        base_agents = (line / "AGENTS.md").read_text(encoding="utf-8")
        write(
            line / "AGENTS.md",
            base_agents.split("## 4. 任务看板")[0]
            + "## 4. 任务看板\n- [x] **T1 已收口**\n- [x] **T1d 作废**\n- [ ] **T2 在用**\n",
        )
        rc, out = run(line)
        check(
            rc == 0 and "[A005] ✅" in out,
            "closed/deprecated cards without prompts must be skipped by A005:\n" + out,
        )

        # Active card (⏳执行中 / 🟡待复核) missing reviewer prompt must still trigger A005
        write(cards_dir / "T3_执行中缺复核.md", "# T3\n\n## 进度回写\n- 状态：⏳执行中\n\n## 📋 执行方派发提示词\n做\n")
        rc, out = run(line)
        check(
            rc == 0 and "[A005] ⚠️" in out and "T3_执行中缺复核.md" in out
            and "T1_已收口无提示词.md" not in out and "T1d_已作废无提示词.md" not in out,
            "A005 must flag only active card missing prompt, not closed/deprecated ones:\n" + out,
        )


def test_r1_h004_prose_vs_template_placeholders() -> None:
    """Fix 4: H004 allows normal prose ('例：', 'e.g.', 'TODO') while blocking unfilled templates."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        agents_tpl = (
            "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n"
            "{tldr_body}\n---\n\n"
            "## 3. 现在在哪\n- 2026-09-15：初稿完成\n\n## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n"
            "## 4. 任务看板\n- [x] T1 初稿\n"
        )
        # Normal prose containing 例：, e.g., TODO must PASS H004 (exit code 0)
        for valid_tldr in (
            "> - **当前阶段**：T1–T9 已收口（例：19 张图已换 GS(2024)0650 标准边界）\n> - **下一步**：派 T12g\n> - **阻塞**：无",
            "> - **当前阶段**：跑通自检脚本（e.g. check_handoff.py）\n> - **下一步**：清理源码 TODO 注释\n> - **阻塞**：无",
        ):
            write(line / "AGENTS.md", agents_tpl.format(tldr_body=valid_tldr))
            rc, out = run(line)
            check(rc == 0 and "[H004] ✅" in out, f"filled TL;DR prose must pass H004:\n{valid_tldr}\n{out}")

        # Raw assets/AGENTS.md TL;DR and unedited template phrases/placeholders must FAIL H004 (exit code 1)
        raw_asset_agents = (REPO / "assets" / "AGENTS.md").read_text(encoding="utf-8")
        write(
            line / "AGENTS.md",
            raw_asset_agents.replace("2026-06-15", TODAY),
        )
        rc, out = run(line)
        check(rc == 1 and "[H004] ❌" in out, "raw assets/AGENTS.md template must fail H004:\n" + out)

        for bad_tldr in (
            "> - **当前阶段**：【待填】\n> - **下一步**：写方法\n> - **阻塞**：无",
            "> - **当前阶段**：例 T3 进行中\n> - **下一步**：写方法\n> - **阻塞**：无",
            "> - **当前阶段**：已完成初稿\n> - **下一步**：第一个动作，精确到文件/命令\n> - **阻塞**：无",
            "> - **当前阶段**：已完成初稿\n> - **下一步**：写方法\n> - **阻塞**：无 / 等用户确认 X / 等数据下载",
            "> - **当前阶段**：[TODO]\n> - **下一步**：写方法\n> - **阻塞**：无",
            "> - **当前阶段**：初稿（YYYY-MM-DD）\n> - **下一步**：写方法\n> - **阻塞**：无",
            "> - **当前阶段**：\n> - **下一步**：写方法\n> - **阻塞**：无",
        ):
            write(line / "AGENTS.md", agents_tpl.format(tldr_body=bad_tldr))
            rc, out = run(line)
            check(rc == 1 and "[H004] ❌" in out, f"unfilled template TL;DR must fail H004:\n{bad_tldr}\n{out}")


def test_r1_asset_keywords_and_restored_refs() -> None:
    """Items 5 & 6: Keyword assertions on key templates and restored sentences in references."""
    status_tpl = (REPO / "assets" / "STATUS.md").read_text(encoding="utf-8")
    for kw in ("谁做的", "改了什么", "怎么验证的", "没做什么", "不确定处", "archive_status.py"):
        check(kw in status_tpl, f"assets/STATUS.md missing keyword: {kw}")

    readme_tpl = (REPO / "assets" / "任务卡_README.md").read_text(encoding="utf-8")
    for kw in (
        "## 会出错",
        "## 建议",
        "NEEDS_FIX",
        "只按“会出错”返工",
        "核查类卡不替复核方划范围",
        "闸门查交付物本身",
        "计数和派生数一律脚本给出",
        "主控收口三查",
    ):
        check(kw in readme_tpl, f"assets/任务卡_README.md missing keyword: {kw}")
    check("| T1 |" not in readme_tpl, "assets/任务卡_README.md must not have real '| T1 |' example row")

    agents_tpl = (REPO / "assets" / "AGENTS.md").read_text(encoding="utf-8")
    for kw in ("archive_status.py", "环境坑.md", "重开最终交付物", "计数与派生数一律由脚本", "决策登记表_全文.md"):
        check(kw in agents_tpl, f"assets/AGENTS.md missing keyword: {kw}")

    card_tpl = (REPO / "assets" / "任务规划_模板.md").read_text(encoding="utf-8")
    for kw in ("主控在立项前看过什么", "## 会出错", "NEEDS_FIX", "环境坑.md"):
        check(kw in card_tpl, f"assets/任务规划_模板.md missing keyword: {kw}")

    adv_ref = (REPO / "references" / "advanced.md").read_text(encoding="utf-8")
    for kw in (
        "模型战绩.csv",
        "任务契约",
        "两个不同字段，不得混用",
        "短链路（1–2 个 agent、产物简单）可跳过独立复核",
    ):
        check(kw in adv_ref, f"references/advanced.md missing keyword: {kw}")


def test_r1_a003_distinguishes_status_vs_agents() -> None:
    """Item 7: A003 message distinguishes STATUS overflow (archive_status.py) vs AGENTS overflow (§3.5)."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        base_agents = (line / "AGENTS.md").read_text(encoding="utf-8")
        big_table = "".join(f"| D-{i:03d} | {'决策内容填充' * 40} |\n" for i in range(1, 140))
        write(
            line / "AGENTS.md",
            base_agents.replace("| ID | 决策 |\n|---|---|\n", "| ID | 决策 |\n|---|---|\n" + big_table),
        )
        check(len((line / "AGENTS.md").read_bytes()) > 25_000, "fixture AGENTS.md must exceed 25KB")
        rc, out = run(line)
        check(
            rc == 0 and "[A003] ⚠️" in out and "AGENTS 超限多半在 §3.5" in out and "决策登记表_全文.md" in out,
            "AGENTS-only A003 warning must point to §3.5 migration:\n" + out,
        )
        check("STATUS 超限" not in out, "AGENTS-only overflow must not print STATUS 超限:\n" + out)


def main() -> int:
    test_asset_sizes()
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
        for size, expect in ((400, "✅"), (401, "⚠️")):
            write(card, card_base.replace("- 执行方：略", row + "字" * (size - len(row))))
            rc, out = run(line)
            check(rc == 0 and f"[A009] {expect}" in out and ("T2_方法.md「执行方」行 401 字" in out) == (size == 401),
                  f"进度回写 row of {size} chars must give A009 {expect} only above 400:\n" + out)
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

    test_040_features()
    test_r1_a007_merged_inline_states()
    test_r1_index_template_no_collision()
    test_r1_a005_skips_closed_and_deprecated()
    test_r1_h004_prose_vs_template_placeholders()
    test_r1_asset_keywords_and_restored_refs()
    test_r1_a003_distinguishes_status_vs_agents()
    print("All skill self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

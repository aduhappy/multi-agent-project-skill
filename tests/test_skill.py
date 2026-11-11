#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Smoke and regression tests for check_handoff.py, archive_status.py, and skill assets."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO / "assets"
CHECKER = ASSETS_DIR / "check_handoff.py"
ARCHIVER = ASSETS_DIR / "archive_status.py"
TODAY = "2026-09-15"

if str(ASSETS_DIR) not in sys.path:
    sys.path.insert(0, str(ASSETS_DIR))

import archive_status as archiver_mod  # noqa: E402
import check_handoff as checker_mod  # noqa: E402


def _clean_env() -> dict[str, str]:
    return dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")


def run(root: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-B", str(CHECKER), str(root), "--today", TODAY, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
    )
    return result.returncode, result.stdout


def run_archiver(root: Path, *args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-B", str(ARCHIVER), str(root), "--today", TODAY, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
    )
    return result.returncode, result.stdout, result.stderr


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes_eol(path: Path, text: str, eol: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    out = norm.replace("\n", "\r\n") if eol == "\r\n" else norm
    path.write_bytes(out.encode("utf-8"))


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

        # --- A006 lists largest 3 sections when active card > 15KB (and ignores fenced ## headings) ---
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

        # --- A011 handoff <= 800 chars and 4 sections present ---
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

        # --- A012 review report trailing standalone PASS / NEEDS_FIX ---
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

        # --- archive_status.py pass and fail cases ---
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
            filler = "内" * (3500 if day < 6 else (500 if day < 11 else 80))
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
    """§4 line listing multiple cards with inline status emojis checks each card individually."""
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
    """Fresh skeleton copying assets/任务卡_README.md + real T1 card (⬜可派) passes A007 on first run."""
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
            base_agents.split("## 4. 任务看板")[0] + "## 4. 任务看板\n- [x] **T0 初始化**\n- [ ] **T1 数据清洗**\n",
        )
        rc, out = run(line)
        check(
            rc == 0 and "[A007] ✅" in out and "[A005] ✅" in out,
            "fresh skeleton with verbatim 任务卡_README.md template and T1 ⬜ card must pass A007 & A005:\n" + out,
        )


def test_r1_a005_skips_closed_and_deprecated() -> None:
    """A005 ignores closed (✅) and deprecated (🗄️) cards whose prompts were deleted at closure."""
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

        write(cards_dir / "T3_执行中缺复核.md", "# T3\n\n## 进度回写\n- 状态：⏳执行中\n\n## 📋 执行方派发提示词\n做\n")
        rc, out = run(line)
        check(
            rc == 0 and "[A005] ⚠️" in out and "T3_执行中缺复核.md" in out
            and "T1_已收口无提示词.md" not in out and "T1d_已作废无提示词.md" not in out,
            "A005 must flag only active card missing prompt, not closed/deprecated ones:\n" + out,
        )


def test_r1_h004_prose_vs_template_placeholders() -> None:
    """H004 allows normal prose ('例：', 'e.g.', 'TODO') while blocking unfilled templates."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        agents_tpl = (
            "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n"
            "{tldr_body}\n---\n\n"
            "## 3. 现在在哪\n- 2026-09-15：初稿完成\n\n## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n"
            "## 4. 任务看板\n- [x] T1 初稿\n"
        )
        for valid_tldr in (
            "> - **当前阶段**：T1–T9 已收口（例：19 张图已换 GS(2024)0650 标准边界）\n> - **下一步**：派 T12g\n> - **阻塞**：无",
            "> - **当前阶段**：跑通自检脚本（e.g. check_handoff.py）\n> - **下一步**：清理源码 TODO 注释\n> - **阻塞**：无",
        ):
            write(line / "AGENTS.md", agents_tpl.format(tldr_body=valid_tldr))
            rc, out = run(line)
            check(rc == 0 and "[H004] ✅" in out, f"filled TL;DR prose must pass H004:\n{valid_tldr}\n{out}")

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
    """Keyword assertions on key templates and restored sentences in references."""
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
    """A003 message distinguishes STATUS overflow (archive_status.py) vs AGENTS overflow (§3.5)."""
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


# =====================================================================
# 0.4.1 Regression Tests (22 items: A1–A10, B1, C1–C8, D1–D3)
# =====================================================================


def test_041_a1_board_template() -> None:
    """A1: assets/AGENTS.md §4 uses unticked Tx/Ty/Tz; template-only board fails H008 and warns A004."""
    agents_tpl = (REPO / "assets" / "AGENTS.md").read_text(encoding="utf-8")
    sec4_tpl = checker_mod.section(agents_tpl, "4", {"任务看板", "下一步任务看板"})
    check("[x]" not in sec4_tpl.lower(), "assets/AGENTS.md §4 must not pre-tick any template task:\n" + sec4_tpl)
    check(not re.search(r"\bT[1-9]\b", sec4_tpl), "assets/AGENTS.md §4 must not use real T1..T9 IDs:\n" + sec4_tpl)
    check("Tx" in sec4_tpl and "Ty" in sec4_tpl, "assets/AGENTS.md §4 should use Tx/Ty placeholders:\n" + sec4_tpl)

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        write(
            line / "文档" / "任务卡" / "T1_数据清洗.md",
            "# T1 数据清洗\n\n## 进度回写\n- 状态：⬜可派\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        base_head = (line / "AGENTS.md").read_text(encoding="utf-8").split("## 4. 任务看板")[0]
        # Case 1: §4 copied directly from assets/AGENTS.md (only template placeholder lines)
        write(line / "AGENTS.md", base_head + sec4_tpl + "\n")
        rc, out = run(line)
        check(rc == 1 and "[H008] ❌" in out, "board with only template rows must fail H008:\n" + out)
        check("[A004] ⚠️" in out, "board with only template rows must not pass A004:\n" + out)
        check("[A007] ✅" in out, "template §4 must not collide with real T1 card on A007:\n" + out)

        # Case 2: Even if user left old pre-ticked `[x] **T1【待填】**`, H008 & A004 still reject template-only board
        write(
            line / "AGENTS.md",
            base_head + "## 4. 任务看板\n- [x] **T1【待填】** —— ✅完成 2026-06-15\n- [ ] **T2【待填】**\n",
        )
        rc, out = run(line)
        check(rc == 1 and "[H008] ❌" in out and "[A004] ⚠️" in out,
              "pre-ticked placeholder row must not count as real task or checked item:\n" + out)


def test_041_a2_status_placeholder_scope() -> None:
    """A2: Literal YYYY-MM-DD in STATUS prose/code blocks does not fail H005; template positions fail with clear detail."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        # Pasting checker hint text with literal YYYY-MM-DD inside 怎么验证的 (real bug reproduction)
        write(
            line / "STATUS.md",
            "# STATUS.md — 增量 Handoff\n\n"
            "## Handoff（2026-09-15，T13c 自检：🟡待复核）\n"
            "- **谁做的**：工具 Antigravity / 模型 Gemini / 家族 Google；角色：执行方\n"
            "### 改了什么\n修复检查器误报。\n"
            "### 怎么验证的\n"
            "之前空跑曾提示：未找到交接段（标题须含 Handoff 或以 YYYY-MM-DD 开头）；现复测输出全绿：\n"
            "```text\n--today YYYY-MM-DD  覆盖日期\n```\n"
            "### 没做什么\n无。\n"
            "### 不确定处\n无。\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[H005] ✅" in out, "YYYY-MM-DD quoted in prose/fenced block must pass H005:\n" + out)

        # Unfilled template heading must fail H005 and explain why (never print '已填')
        raw_status_tpl = (REPO / "assets" / "STATUS.md").read_text(encoding="utf-8")
        write(line / "STATUS.md", raw_status_tpl)
        rc, out = run(line)
        check(rc == 1 and "[H005] ❌" in out, "raw STATUS template must fail H005:\n" + out)
        h005_block = out.split("[H005]")[1].split("[H006]")[0]
        check("已填" not in h005_block and ("占位符" in h005_block or "真实日期" in h005_block),
              "failed H005 detail must explain what is missing instead of saying 已填:\n" + h005_block)


def test_041_a3_h003_vs_handoff_date() -> None:
    """A3: H003 compares §3 date against STATUS latest handoff date (falls back to today only when STATUS has no handoffs)."""
    doc = checker_mod.__doc__ or ""
    check("STATUS" in doc and ("最新交接" in doc or "交接日期" in doc),
          "check_handoff.py docstring must state H003 now compares with STATUS handoff date")

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        # Project paused for 35 days: §3 is 2026-09-14, STATUS latest handoff is 2026-09-15, today is 2026-10-20 -> PASS
        agents_txt = (line / "AGENTS.md").read_text(encoding="utf-8").replace("2026-09-15", "2026-09-14")
        write(line / "AGENTS.md", agents_txt)
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-09-15，T1 收口）\n"
            "- **谁做的**：主控\n- **改了什么**：T1 收口。\n- **怎么验证的**：脚本全过。\n- **没做什么**：无。\n- **不确定处**：无。\n",
        )
        res = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-10-20"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(res.returncode == 0 and "[H003] ✅" in res.stdout,
              "paused project (>30d since both §3 and STATUS) must pass H003:\n" + res.stdout)

        # New handoff on 2026-09-25 while §3 stayed at 2026-09-14 (lag = 11d > 7d) -> FAIL H003
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-09-25，T2 交回）\n"
            "- **谁做的**：执行方\n- **改了什么**：完成 T2。\n- **怎么验证的**：脚本全过。\n- **没做什么**：无。\n- **不确定处**：无。\n",
        )
        res2 = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-10-20"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(res2.returncode == 1 and "[H003] ❌" in res2.stdout,
              "§3 lagging >7 days behind STATUS latest handoff must fail H003:\n" + res2.stdout)

        # No handoff headings in STATUS at all -> fallback to comparing §3 against today -> FAIL H003
        write(line / "STATUS.md", "# STATUS\n\n本文件尚未写入交接段，仅记录建档日期 2026-09-15 供初始化核验使用，长度超过五十个字符。\n")
        res3 = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-10-20"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(res3.returncode == 1 and "[H003] ❌" in res3.stdout,
              "when STATUS has no handoff blocks, H003 must fall back to comparing against today:\n" + res3.stdout)


def test_041_a4_skip_closed_cards_and_reviews() -> None:
    """A4: A006, A009, A012 skip ✅/🗄️ cards (including letter-suffixed & no-underscore names) and report skipped counts."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        # Closed & deprecated cards that exceed 15KB and have >400-char rows + old review reports without PASS/NEEDS_FIX
        write(
            cards_dir / "T10b_配图.md",
            "# T10b\n\n## 进度回写\n- 状态：✅已收口\n- 执行方：" + ("甲" * 450) + "\n\n## 内容\n" + ("乙" * 5500),
        )
        write(
            cards_dir / "T10h图集.md",
            "# T10h\n\n## 进度回写\n- 状态：🗄️作废\n- 主控收口：" + ("丙" * 430) + "\n\n## 内容\n" + ("丁" * 5500),
        )
        write(line / "文档" / "T10b_复核_GLM_20261108.md", "# T10b 旧复核\n结论通过，无单独结论行。\n")
        write(line / "文档" / "T10bR1_复核_DeepSeek.md", "# T10b 返修复核\n同意收口。\n")
        write(line / "文档" / "T10h复核报告.md", "# T10h 无下划线复核报告\n已作废。\n")

        base_head = (line / "AGENTS.md").read_text(encoding="utf-8").split("## 4. 任务看板")[0]
        write(
            line / "AGENTS.md",
            base_head + "## 4. 任务看板\n- [ ] **T10b 配图**✅、**T10h 图集**🗄️\n- [x] **T1 初稿**\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A006] ✅" in out and "跳过 2 张收口/作废" in out,
              "A006 must skip closed/deprecated bloated cards and show skipped count:\n" + out)
        check("[A009] ✅" in out and "跳过 2 张收口/作废" in out,
              "A009 must skip closed/deprecated long rows and show skipped count:\n" + out)
        check("[A012] ✅" in out and "跳过 3 份收口/作废卡报告" in out,
              "A012 must skip review reports of closed/deprecated cards and show skipped count:\n" + out)

        # Active cards & unmatched/active review reports MUST still be checked
        write(
            cards_dir / "T12h_图集正式版.md",
            "# T12h\n\n## 进度回写\n- 状态：🟡待复核\n\n## 版式\n" + ("戊" * 5500)
            + "\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        write(
            cards_dir / "T12f_措施库两图.md",
            "# T12f\n\n## 进度回写\n- 状态：🔵待收口\n- 主控收口：" + ("己" * 457)
            + "\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        write(line / "文档" / "T12h_复核_混元.md", "# T12h 复核\n缺末尾结论行。\n")
        write(line / "文档" / "T99_复核_未知卡.md", "# 无对应卡的复核报告\n缺末尾结论行。\n")
        write(
            line / "AGENTS.md",
            base_head + "## 4. 任务看板\n- [ ] **T10b 配图**✅、**T10h 图集**🗄️、**T12h 图集正式版**⬜、**T12f 措施库**🔵\n- [x] **T1 初稿**\n",
        )
        rc, out = run(line)
        check("[A006] ⚠️" in out and "T12h_图集正式版.md" in out and "T10b" not in out,
              "A006 must flag only active oversized card T12h:\n" + out)
        check("[A009] ⚠️" in out and "T12f_措施库两图.md" in out and "T10b" not in out,
              "A009 must flag only active card T12f:\n" + out)
        check(
            "[A012] ⚠️" in out and "T12h_复核_混元.md" in out and "T99_复核_未知卡.md" in out
            and "T10b" not in out and "T10h" not in out,
            "A012 must flag active-card & unmatched review reports while skipping closed ones:\n" + out,
        )


def test_041_a5_a002_display_constants() -> None:
    """A5: A002 ignores *_COLORS / palette constants / inline noqa while catching caliber constant drift."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        write(
            line / "scripts" / "plot_map1.py",
            "ZONE_COLORS = {'I': '#1b9e77', 'II': '#d95f02'}\n"
            "FIG_PALETTE = ['#112233', '#445566']\n"
            "DAM = {'NO_DAM': '#ECEFF1', 'P1': '#B2E2E2'}\n"
            "TEMP_LABELS = ['甲', '乙']  # noqa: A002\n",
        )
        write(
            line / "scripts" / "plot_map2.py",
            "ZONE_COLORS = {'I': '#7570b3', 'II': '#e7298a'}\n"
            "FIG_PALETTE = ['#abcdef', '#fedcba']\n"
            "DAM = {'NO_DAM': '#E8EDF0', 'P1': '#F7FCFD'}\n"
            "TEMP_LABELS = ['甲', '丙']  # noqa: A002\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A002] ✅" in out,
              "display/color constants and # noqa: A002 lines must not trigger A002:\n" + out)

        # Caliber constant drift MUST still warn A002
        write(
            line / "scripts" / "plot_map1.py",
            (line / "scripts" / "plot_map1.py").read_text(encoding="utf-8")
            + "ZONE_NAMES = ['贺兰山', '银川平原']\n",
        )
        write(
            line / "scripts" / "plot_map2.py",
            (line / "scripts" / "plot_map2.py").read_text(encoding="utf-8")
            + "ZONE_NAMES = ['贺兰山', '银川平原', '六盘山']\n",
        )
        rc, out = run(line)
        check(
            rc == 0 and "[A002] ⚠️" in out and "ZONE_NAMES" in out
            and "ZONE_COLORS" not in out and "DAM:" not in out and "TEMP_LABELS" not in out,
            "A002 must report caliber constant ZONE_NAMES while keeping display constants excluded:\n" + out,
        )


def test_041_a6_a011_recent_five_handoffs() -> None:
    """A6: A011 inspects the most recent 5 handoff blocks (including ### subheadings and varied heading formats)."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))

        def _seg(head: str, body_pad: int = 10, omit_uncertain: bool = False) -> str:
            unc = "" if omit_uncertain else "### 不确定处\n无。\n"
            return (
                f"{head}\n"
                "- **谁做的**：执行方\n"
                f"### 改了什么\n{'改' * body_pad}\n"
                "### 怎么验证的\n`python check.py` 通过。\n"
                "### 没做什么\n无。\n"
                f"{unc}"
            ).rstrip()

        # 6 blocks: #1 (6th from end) is 900 chars (ignored); #3 (in recent 5) is 900 chars; #4 misses 不确定处; #6 (latest) is valid!
        segs = [
            _seg("## Handoff（2026-09-10，T1 旧超长段）", body_pad=820),
            _seg("## 交接（2026-09-11，T2）", body_pad=20),
            _seg("## Handoff（2026-09-12，T13a 复核：🔵待收口）", body_pad=820),
            _seg("## [2026-09-13] T13b 执行方", body_pad=20, omit_uncertain=True),
            _seg("## T13c 交回（2026-09-14）", body_pad=20),
            _seg("## Handoff（2026-09-15，主控收口）", body_pad=20),
        ]
        write(line / "STATUS.md", "# STATUS\n\n" + "\n\n".join(segs) + "\n")
        rc, out = run(line)
        check(
            rc == 0 and "[A011] ⚠️" in out
            and "T13a 复核" in out and "超 800 字" in out
            and "[2026-09-13] T13b 执行方" in out and "缺节：不确定处" in out
            and "T1 旧超长段" not in out,
            "A011 must check recent 5 blocks (catching #3 and #4 even when #6 is short) and ignore 6th-oldest #1:\n" + out,
        )


def test_041_a7_a013_decision_chain() -> None:
    """A7: A013 checks duplicate IDs and ACTIVE/SUPERSEDED chain consistency (supporting |r|>0.8 cells, blank lines, migrated-out targets)."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        base_agents = (line / "AGENTS.md").read_text(encoding="utf-8")

        valid_table = (
            "## 3.5 决策登记表\n\n"
            "| ID | 状态 | 决策 | 取值/口径 | 理由 | 日期 | 证据文档 | 取代了谁 | 被谁取代 |\n"
            "|----|------|------|-----------|------|------|----------|----------|----------|\n"
            "| D-01 | SUPERSEDED | 旧口径 | 初版 | 历史 | 2026-09-10 | ->a.md | -- | D-03 |\n\n"
            "| D-32 | ACTIVE | 因子筛选 | |r|>0.8 按优先级留一，VIF>10 剔除 | 去共线 | 2026-09-12 | ->b.md | -- | -- |\n"
            "| D-03 | ACTIVE | 新口径 | 修订版 | 复核修正 | 2026-09-14 | ->c.md | D-01 | -- |\n"
            "| D-60 | ACTIVE | 全文结构 | 9 章版 | 老师定 | 2026-09-15 | ->d.md | D-55 | -- |\n\n"
        )
        write(
            line / "AGENTS.md",
            base_agents.replace("## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n", valid_table),
        )
        rc, out = run(line)
        check(rc == 0 and "[A013] ✅" in out and "4 条决策链自洽" in out,
              "valid decision table (with blank line, |r|>0.8 pipe in cell, and migrated-out D-55) must pass A013:\n" + out)

        broken_table = (
            "## 3.5 决策登记表\n\n"
            "| ID | 状态 | 决策 | 取值/口径 | 理由 | 日期 | 证据文档 | 取代了谁 | 被谁取代 |\n"
            "|----|------|------|-----------|------|------|----------|----------|----------|\n"
            "| D-38 | ACTIVE | 水指标 | 产水量 | 初定 | 2026-09-10 | ->a.md | -- | -- |\n"
            "| D-51 | ACTIVE | 水源涵养 | 水量平衡法 | 修订 | 2026-09-12 | ->b.md | D-38 | -- |\n"
            "| D-38 | ACTIVE | 重复号 | 重复 | 误贴 | 2026-09-12 | ->b.md | -- | -- |\n"
            "| D-47 | SUPERSEDED | 旧交付 | 已废 | 改版 | 2026-09-13 | ->c.md | -- | -- |\n"
            "| D-20 | ACTIVE | 拦沙量 | 公式 | 有效 | 2026-09-14 | ->d.md | -- | D-21 |\n\n"
        )
        write(
            line / "AGENTS.md",
            base_agents.replace("## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n", broken_table),
        )
        rc, out = run(line)
        check(
            rc == 0 and "[A013] ⚠️" in out
            and "D-51／D-38" in out
            and "重复 ID：D-38" in out
            and "D-47 为 SUPERSEDED 但未填“被谁取代”" in out
            and "D-20 为 ACTIVE 但填了“被谁取代”" in out,
            "broken decision chain must report all 4 categories in A013:\n" + out,
        )


def test_041_a8_a014_agents_placeholders() -> None:
    """A8: A014 reports remaining 【待填】 counts by section and calls out unfilled §5 不可混用的维度."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        raw_agents = (REPO / "assets" / "AGENTS.md").read_text(encoding="utf-8")
        # Fill only TL;DR, §3, and §4 so H001-H009 pass, leaving remaining 【待填】 in §1, §2, §5, §5.5, §6, §7
        partially_filled = (
            raw_agents
            .replace("【待填：例 T3 进行中】", "T1 准备中（2026-09-15）")
            .replace("【待填：第一个动作，精确到文件/命令】", "运行 python scripts/clean.py")
            .replace("【待填：无 / 等用户确认 X / 等数据下载】", "无")
            .replace("- ✅ 【待填：最近完成的事，带日期。例 2026-06-15：数据集 X 已下载清洗，落在 <路径>】", "- ✅ 2026-09-15：完成骨架搭建")
            .replace("- ✅ 【待填：另一件完成的事】\n", "")
            .replace("  - 【待填：例：数据 A 的口径与文献 B 不一致，已对比三种口径均不匹配（详见 `reports/xxx.md`），等导师确认选哪种。无阻塞则填\"无\"。】", "  - 无")
        )
        partially_filled = re.sub(
            r"## 4\. 下一步任务看板.*?(?=\n## 5\.)",
            "## 4. 下一步任务看板\n- [x] **T0 骨架初始化**\n- [ ] **T1 数据清洗**\n",
            partially_filled,
            flags=re.DOTALL,
        )
        write(line / "AGENTS.md", partially_filled)
        rc, out = run(line)
        check(
            rc == 0 and "[A014] ⚠️" in out
            and "剩余" in out and "§1:" in out and "§5:" in out
            and "§5“不可混用的维度”尚未填写" in out,
            "partially filled Mode A skeleton must pass H-gates and warn A014 with section counts & §5 dimension alert:\n" + out,
        )


def test_041_a9_a015_missing_or_empty_cards_dir() -> None:
    """A9: Missing 文档/任务卡/ or 0 cards emits A015 advisory stating card checks were not executed."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        rc, out = run(line)
        check(
            rc == 0 and "[A015] ⚠️" in out and "未找到 文档/任务卡/" in out and "A005—A009" in out,
            "missing 文档/任务卡/ must warn A015:\n" + out,
        )
        (line / "文档" / "任务卡").mkdir(parents=True, exist_ok=True)
        rc2, out2 = run(line)
        check(
            rc2 == 0 and "[A015] ⚠️" in out2 and "0 张任务卡" in out2 and "A005—A009" in out2,
            "empty 文档/任务卡/ (0 cards) must warn A015:\n" + out2,
        )
        write(
            line / "文档" / "任务卡" / "T1_初稿.md",
            "# T1\n\n## 进度回写\n- 状态：✅已收口\n",
        )
        rc3, out3 = run(line)
        check(rc3 == 0 and "[A015] ✅" in out3, "non-empty 文档/任务卡/ must pass A015:\n" + out3)


def test_041_a10_summary_counts() -> None:
    """A10: Footer distinguishes fail count and advisory count; never says 全部通过 when advisories exist."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        # Make line 100% green (0 fails, 0 advisories)
        write(
            line / "文档" / "任务卡" / "T1_初稿.md",
            "# T1\n\n## 进度回写\n- 状态：✅已收口\n",
        )
        write(
            line / "文档" / "任务卡" / "T2_方法.md",
            "# T2\n\n## 进度回写\n- 状态：⬜可派\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-09-15）\n"
            "- **谁做的**：主控\n- **改了什么**：建项。\n- **怎么验证的**：自检通过。\n- **没做什么**：无。\n- **不确定处**：无。\n",
        )
        rc, out = run(line)
        check(rc == 0 and "0 项失败，0 条提示（全部通过）。" in out,
              "0 fails and 0 advisories must print '0 项失败，0 条提示（全部通过）。':\n" + out)

        # Trigger 1 advisory (delete cards dir -> A015 warns)
        for fp in (line / "文档" / "任务卡").glob("*.md"):
            fp.unlink()
        rc2, out2 = run(line)
        check(rc2 == 0 and "0 项失败，1 条提示。" in out2 and "全部通过" not in out2,
              "0 fails with 1 advisory must print '0 项失败，1 条提示。' and NOT '全部通过':\n" + out2)


def test_041_b1_archive_preserves_eol() -> None:
    """B1: archive_status.py preserves LF (0 CRLF) and CRLF (100% CRLF) across STATUS, AGENTS, and new archive files."""
    for eol_name, eol in (("LF", "\n"), ("CRLF", "\r\n")):
        with tempfile.TemporaryDirectory() as temp:
            line = Path(temp)
            blocks = []
            for day in range(4, 16):  # 12 handoffs -> archive 2, keep 10
                d_str = f"2026-09-{day:02d}"
                blocks.append(
                    f"### Handoff（{d_str}，T{day}）\n"
                    "- **谁做的**：执行方\n"
                    f"### 改了什么\n完成第 {day} 步。\n"
                    "### 怎么验证的\n脚本重开交付物核对通过。\n"
                    "### 没做什么\n无。\n"
                    "### 不确定处\n无。"
                )
            status_content = "# STATUS.md — 增量 Handoff\n\n> 只记增量。\n\n" + "\n\n".join(blocks) + "\n"
            sec3_bullets = "\n".join(f"- ✅ 2026-09-{d:02d}：快照 {d}" for d in range(9, 16))  # 7 items -> archive 3, keep 4+1
            agents_content = (
                "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n"
                "> - **当前阶段**：进行中\n> - **下一步**：下一步\n> - **阻塞**：无\n\n"
                f"## 3. 现在在哪\n{sec3_bullets}\n- **阻塞**：无\n- `→ 见 STATUS.md`\n\n"
                "## 4. 任务看板\n- [x] **T1 完成**\n"
            )
            write_bytes_eol(line / "STATUS.md", status_content, eol)
            write_bytes_eol(line / "AGENTS.md", agents_content, eol)

            before_blocks = checker_mod.handoff_blocks((line / "STATUS.md").read_bytes().decode("utf-8"))
            check(len(before_blocks) == 12, f"{eol_name}: expected 12 handoffs before archive, got {len(before_blocks)}")

            arc_rc, arc_out, arc_err = run_archiver(line, "--keep", "10", "--agents-keep", "5")
            check(arc_rc == 0, f"{eol_name}: archive_status failed: {arc_out}\n{arc_err}")

            status_arch = line / "文档" / "STATUS_归档_至2026-09-05.md"
            agents_arch = line / "文档" / "AGENTS_归档_至2026-09-11.md"
            check(status_arch.is_file() and agents_arch.is_file(), f"{eol_name}: archive files must exist")

            for target in (line / "STATUS.md", status_arch, line / "AGENTS.md", agents_arch):
                raw = target.read_bytes()
                crlf_cnt = raw.count(b"\r\n")
                lf_cnt = raw.count(b"\n")
                if eol == "\n":
                    check(crlf_cnt == 0 and lf_cnt > 0, f"LF input produced {crlf_cnt} CRLFs in {target.name}")
                else:
                    check(crlf_cnt > 0 and crlf_cnt == lf_cnt,
                          f"CRLF input produced bare LF in {target.name} (crlf={crlf_cnt}, lf={lf_cnt})")

            kept_blocks = checker_mod.handoff_blocks((line / "STATUS.md").read_bytes().decode("utf-8"))
            arch_blocks = checker_mod.handoff_blocks(status_arch.read_bytes().decode("utf-8"))
            check(
                len(kept_blocks) == 10 and len(arch_blocks) == 2 and len(kept_blocks) + len(arch_blocks) == len(before_blocks),
                f"{eol_name}: handoff count mismatch: before={len(before_blocks)}, kept={len(kept_blocks)}, arch={len(arch_blocks)}",
            )


def test_041_c1_agents_cross_family_review() -> None:
    """C1: assets/AGENTS.md §5 requires cross-model-family independent review for paper conclusions/headline numbers."""
    agents_tpl = (REPO / "assets" / "AGENTS.md").read_text(encoding="utf-8")
    sec5 = checker_mod.section(agents_tpl, "5", {"铁律 / 约定", "铁律"})
    check("必须跨模型家族独立复核" in sec5, "assets/AGENTS.md §5 must say 必须跨模型家族独立复核")
    check("复核人不同" not in sec5, "assets/AGENTS.md §5 must remove outdated （复核人不同） wording")


def test_041_c2_example_filled_agents() -> None:
    """C2: references/example_filled_AGENTS.md matches current template and passes H001–H009 + A001 in a temp project."""
    ex = (REPO / "references" / "example_filled_AGENTS.md").read_text(encoding="utf-8")
    for kw in ("Scope：line", "## 3.5 决策登记表", "必须跨模型家族独立复核", "文档/任务卡/"):
        check(kw in ex, f"references/example_filled_AGENTS.md missing required current-template element: {kw}")
    check("任务规划_桥梁冲刷评估.md" not in ex, "example_filled_AGENTS.md must not point to legacy flat plan file")

    with tempfile.TemporaryDirectory() as temp:
        proj = Path(temp)
        write(proj / "AGENTS.md", ex)
        write(proj / "CLAUDE.md", (REPO / "assets" / "CLAUDE.md").read_text(encoding="utf-8"))
        write(
            proj / "STATUS.md",
            "# STATUS.md — 增量 Handoff\n\n"
            "## Handoff（2026-06-15，T2 收口）\n"
            "- **谁做的**：主控 Claude / Anthropic\n"
            "- **改了什么**：完成 T2 两期 DEM 差分收口并登记 D-03。\n"
            "- **怎么验证的**：重开 `outputs/dem_diff_bridge.tif` 核对投影与中误差，运行 `check_handoff.py` 通过。\n"
            "- **没做什么**：T4 待断面到齐。\n"
            "- **不确定处**：无。\n",
        )
        for cid, st in (("T1_航测", "✅已收口"), ("T2_差分", "✅已收口"), ("T3_水文", "✅已收口"), ("T4_建模", "⏳执行中"), ("T5_初稿", "⬜可派")):
            write(
                proj / "文档" / "任务卡" / f"{cid}.md",
                f"# {cid}\n\n## 进度回写\n- 状态：{st}\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
            )
        res = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(proj), "--today", "2026-06-16"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        out = res.stdout
        check(res.returncode == 0, "example_filled_AGENTS.md project must exit 0:\n" + out)
        for hcode in (f"H00{i}" for i in range(1, 10)):
            check(f"[{hcode}] ✅ PASS" in out, f"example_filled_AGENTS.md must pass {hcode}:\n" + out)
        for acode in ("A001", "A013", "A014"):
            check(f"[{acode}] ✅ PASS" in out, f"example_filled_AGENTS.md must pass {acode}:\n" + out)


def test_041_c3_readme_dedup_no_progress_log() -> None:
    """C3: README.md links to SKILL.md instead of duplicating the 3 long checklists, and drops 进度日志.md."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    check("进度日志" not in readme, "README.md must remove SKILL.md-absent 进度日志 / 进度日志.md")
    for dup_heading in ("## 生成的文件骨架", "## AGENTS.md 的板块（顺序即优先级）", "## 跨软件能续的十个硬要求"):
        check(dup_heading not in readme, f"README.md must not maintain duplicate full section: {dup_heading}")
    check("SKILL.md#" in readme, "README.md summary must link to SKILL.md sections")


def test_041_c4_skill_description_and_size() -> None:
    """C4: SKILL.md frontmatter description includes inapplicable scenarios and file stays <= 15KB."""
    skill_bytes = (REPO / "SKILL.md").read_bytes()
    check(len(skill_bytes) <= 15_000, f"SKILL.md must stay <= 15000B, got {len(skill_bytes)}B")
    skill_text = skill_bytes.decode("utf-8")
    fm_match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", skill_text, re.DOTALL)
    check(bool(fm_match), "SKILL.md must have valid YAML frontmatter")
    desc_lines = [ln for ln in fm_match.group(1).splitlines() if ln.startswith("description:")]
    check(len(desc_lines) == 1, "SKILL.md frontmatter must contain description line")
    desc = desc_lines[0]
    for kw in ("不适用", "单文件小脚本", "纯翻译或问答"):
        check(kw in desc, f"SKILL.md frontmatter description missing '{kw}': {desc}")


def test_041_c5_claude_import_and_copilot_cli() -> None:
    """C5: assets/CLAUDE.md keeps prose instruction and adds @AGENTS.md import; README compatibility table covers Copilot CLI."""
    claude_md = (REPO / "assets" / "CLAUDE.md").read_text(encoding="utf-8")
    check("请先读本文件所在目录的 `AGENTS.md`" in claude_md, "assets/CLAUDE.md must retain 请先读... sentence")
    check(bool(re.search(r"(?m)^@AGENTS\.md\s*$", claude_md)),
          "assets/CLAUDE.md must have standalone @AGENTS.md import outside backticks:\n" + claude_md)
    check(checker_mod.pointer_ok(claude_md), "assets/CLAUDE.md must pass pointer_ok()")

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    check("Copilot CLI" in readme, "README.md compatibility table must include verified GitHub Copilot CLI row")


def test_041_c6_status_template_and_compat() -> None:
    """C6: assets/STATUS.md drops 现状一屏; checker and archiver work on both old (with 现状一屏) and new STATUS.md."""
    status_tpl = (REPO / "assets" / "STATUS.md").read_text(encoding="utf-8")
    check("现状一屏" not in status_tpl, "assets/STATUS.md must remove duplicate 现状一屏 block")

    for label, header_extra in (
        ("new_no_snapshot", ""),
        ("old_with_snapshot", "## 现状一屏（2026-09-01 更新）\n> **阶段**：T1 完成\n> **唯一闸门/阻塞**：无\n\n"),
    ):
        with tempfile.TemporaryDirectory() as temp:
            line = build(Path(temp))
            blocks = [
                f"## Handoff（2026-09-{d:02d}，T{d}）\n"
                "- **谁做的**：执行方\n- **改了什么**：更新。\n- **怎么验证的**：通过。\n- **没做什么**：无。\n- **不确定处**：无。"
                for d in range(4, 16)
            ]
            write(line / "STATUS.md", "# STATUS.md\n\n" + header_extra + "\n\n".join(blocks) + "\n")
            rc, out = run(line)
            check(rc == 0 and "[H005] ✅" in out and "[H006] ✅" in out and "[A011] ✅" in out,
                  f"{label}: checker failed before archive:\n{out}")
            arc_rc, arc_out, _ = run_archiver(line, "--keep", "10")
            check(arc_rc == 0 and "已归档 2 段" in arc_out, f"{label}: archiver failed:\n{arc_out}")
            rc2, out2 = run(line)
            check(rc2 == 0 and "[H005] ✅" in out2 and "[H006] ✅" in out2 and "[A011] ✅" in out2,
                  f"{label}: checker failed after archive:\n{out2}")


def test_041_c7_staged_sample_handoff_rule() -> None:
    """C7: assets/任务卡_README.md 卡面规矩 specifies keeping ⏳ and writing '样张待主控看' (not 🟡) for sample handoffs."""
    readme_tpl = (REPO / "assets" / "任务卡_README.md").read_text(encoding="utf-8")
    rules_sec = readme_tpl.split("## 卡面规矩", 1)[1].split("## 例行签核提示词", 1)[0]
    check(
        "样张待主控看" in rules_sec and "⏳" in rules_sec and "🟡" in rules_sec,
        "assets/任务卡_README.md 卡面规矩 must document staged sample handoff rule (⏳ + 样张待主控看, not 🟡)",
    )


def test_041_c8_english_files_cleanup() -> None:
    """C8: 6 English placeholder files removed; README.en.md is real English overview <= 60 lines."""
    removed = (
        "SKILL.en.md",
        "assets/AGENTS_EN.md",
        "assets/STATUS_EN.md",
        "assets/source_EN.txt",
        "assets/task_cards_README.md",
        "assets/task_plan_template.md",
    )
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    for rel in removed:
        check(not (REPO / rel).exists(), f"retired English placeholder file must be deleted: {rel}")
        check(Path(rel).name not in readme, f"README.md must not reference deleted file {rel}")

    en_path = REPO / "README.en.md"
    check(en_path.is_file(), "README.en.md must exist")
    en_text = en_path.read_text(encoding="utf-8")
    en_lines = en_text.splitlines()
    check(10 <= len(en_lines) <= 60, f"README.en.md must be 10..60 lines, got {len(en_lines)}")
    check("pending update" not in en_text.lower() and "temporarily retired" not in en_text.lower(),
          "README.en.md must be a real English overview, not a retired placeholder")
    for kw in ("AGENTS.md", "git clone", "README.md", "SKILL.md"):
        check(kw in en_text, f"README.en.md missing key content '{kw}'")
    check("README.en.md" in readme, "README.md should link to README.en.md")


def test_041_d1_github_actions_ci() -> None:
    """D1: GitHub Actions workflow runs tests/test_skill.py across Ubuntu, macOS, and Windows."""
    ci_file = REPO / ".github" / "workflows" / "ci.yml"
    check(ci_file.is_file(), ".github/workflows/ci.yml must exist")
    ci_text = ci_file.read_text(encoding="utf-8")
    for runner in ("ubuntu-latest", "macos-latest", "windows-latest"):
        check(runner in ci_text, f"ci.yml must include {runner}")
    check("tests/test_skill.py" in ci_text, "ci.yml must execute tests/test_skill.py")


def test_041_d2_no_assets_pycache() -> None:
    """D2: Running test_skill.py and scripts (even without -B) leaves no __pycache__ inside assets/."""
    for fp in (REPO / "tests" / "test_skill.py", CHECKER, ARCHIVER):
        src = fp.read_text(encoding="utf-8")
        check("dont_write_bytecode = True" in src, f"{fp.name} must set sys.dont_write_bytecode = True")

    # Spawn a subprocess WITHOUT -B or PYTHONDONTWRITEBYTECODE to invoke both scripts' --help
    env_no_b = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    env_no_b["PYTHONIOENCODING"] = "utf-8"
    for script in (CHECKER, ARCHIVER):
        res = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, env=env_no_b)
        check(res.returncode == 0, f"{script.name} --help failed")

    check(not (ASSETS_DIR / "__pycache__").exists(), "assets/__pycache__ must not exist after running tests/scripts")


def test_041_d3_versions_and_changelog() -> None:
    """D3: Both scripts expose __version__ == '0.4.1' and --version; CHANGELOG.md documents 0.4.1."""
    check(getattr(checker_mod, "__version__", None) == "0.4.1", "check_handoff.__version__ must be '0.4.1'")
    check(getattr(archiver_mod, "__version__", None) == "0.4.1", "archive_status.__version__ must be '0.4.1'")

    for script in (CHECKER, ARCHIVER):
        res = subprocess.run(
            [sys.executable, "-B", str(script), "--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        combined = (res.stdout + res.stderr).strip()
        check(res.returncode == 0 and "0.4.1" in combined, f"{script.name} --version must output 0.4.1, got: {combined}")

    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    check(bool(re.search(r"(?m)^##\s+0\.4\.1\b", changelog)), "CHANGELOG.md must have a ## 0.4.1 section")


def main() -> int:
    test_asset_sizes()

    test_041_a1_board_template()
    test_041_a2_status_placeholder_scope()
    test_041_a3_h003_vs_handoff_date()
    test_041_a4_skip_closed_cards_and_reviews()
    test_041_a5_a002_display_constants()
    test_041_a6_a011_recent_five_handoffs()
    test_041_a7_a013_decision_chain()
    test_041_a8_a014_agents_placeholders()
    test_041_a9_a015_missing_or_empty_cards_dir()
    test_041_a10_summary_counts()
    test_041_b1_archive_preserves_eol()
    test_041_c1_agents_cross_family_review()
    test_041_c2_example_filled_agents()
    test_041_c3_readme_dedup_no_progress_log()
    test_041_c4_skill_description_and_size()
    test_041_c5_claude_import_and_copilot_cli()
    test_041_c6_status_template_and_compat()
    test_041_c7_staged_sample_handoff_rule()
    test_041_c8_english_files_cleanup()
    test_041_d1_github_actions_ci()
    test_041_d2_no_assets_pycache()
    test_041_d3_versions_and_changelog()

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

        # 0.4.1 A3: paused project passes on later calendar date; §3 lagging behind newer STATUS handoff fails
        res_paused = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-10-20"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(res_paused.returncode == 0, "paused project must pass H003 under 0.4.1:\n" + res_paused.stdout)

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
        active_card_base = card_base.replace("✅已收口", "⏳执行中")
        row = "- 执行方："
        for size, expect in ((400, "✅"), (401, "⚠️")):
            write(card, active_card_base.replace("- 执行方：略", row + "字" * (size - len(row))))
            rc, out = run(line)
            check(rc == 0 and f"[A009] {expect}" in out and ("T2_方法.md「执行方」行 401 字" in out) == (size == 401),
                  f"进度回写 row of {size} chars on active card must give A009 {expect} only above 400:\n" + out)
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

    check(not (ASSETS_DIR / "__pycache__").exists(), "assets/__pycache__ must not exist at end of test suite")
    print("All skill self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

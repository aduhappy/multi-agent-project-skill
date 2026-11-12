#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Smoke and regression tests for check_handoff.py, archive_status.py, and skill assets."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO / "assets"
HANDOFF_LIB = ASSETS_DIR / "handoff_lib.py"
CHECKER = ASSETS_DIR / "check_handoff.py"
ARCHIVER = ASSETS_DIR / "archive_status.py"
TODAY = "2026-09-15"

_ORIG_SUBPROCESS_RUN = subprocess.run
_DUMP_DIR: Path | None = None
_DUMP_COUNTERS: dict[str, int] = {}


def _normalize_temp_paths(text: str, cmd: list[str]) -> str:
    tmp_root = Path(tempfile.gettempdir()).resolve()
    out = text
    for tok in cmd:
        try:
            p = Path(tok).resolve()
        except OSError:
            continue
        if p == tmp_root or tmp_root in p.parents:
            # Find the immediate child under system temp dir (e.g. .../Temp/tmpXYZ)
            cur = p
            while cur.parent != tmp_root and cur != cur.parent:
                cur = cur.parent
            for cand in sorted({str(cur), tok.split("does_not_exist")[0].rstrip("/\\")}, key=len, reverse=True):
                if cand and len(cand) > 3:
                    out = out.replace(cand, "<TMPDIR>")
    return out


def _tracing_subprocess_run(cmd, *args, **kwargs):
    res = _ORIG_SUBPROCESS_RUN(cmd, *args, **kwargs)
    if _DUMP_DIR is not None and isinstance(cmd, (list, tuple)):
        str_cmd = [str(x) for x in cmd]
        is_checker = str(CHECKER) in str_cmd
        is_archiver = str(ARCHIVER) in str_cmd
        if (is_checker or is_archiver) and not any(f in str_cmd for f in ("--help", "--version")):
            caller = "main_inline"
            frame = sys._getframe(1)
            while frame is not None:
                fname = frame.f_code.co_name
                if fname.startswith("test_"):
                    caller = fname
                    break
                frame = frame.f_back
            seq = _DUMP_COUNTERS.get(caller, 0) + 1
            _DUMP_COUNTERS[caller] = seq
            kind = "check" if is_checker else "archive"
            _DUMP_DIR.mkdir(parents=True, exist_ok=True)
            payload = f"rc={res.returncode}\n--- stdout ---\n{res.stdout or ''}"
            if res.stderr:
                payload += f"\n--- stderr ---\n{_normalize_temp_paths(res.stderr, str_cmd)}"
            (_DUMP_DIR / f"{caller}__{seq:03d}__{kind}.txt").write_bytes(payload.encode("utf-8"))
    return res


subprocess.run = _tracing_subprocess_run

if str(ASSETS_DIR) not in sys.path:
    sys.path.insert(0, str(ASSETS_DIR))

import archive_status as archiver_mod  # noqa: E402
import check_handoff as checker_mod  # noqa: E402
import handoff_lib as hl_mod  # noqa: E402


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
        ("assets/协作规矩.md", 25_000),
        ("assets/任务卡_README.md", 15_000),
        ("assets/任务卡_模板.md", 6_000),
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

        write(cards_dir / "T3_执行中少提示词.md", "# T3\n\n## 进度回写\n- 状态：⏳执行中\n\n## 📋 执行方派发提示词\n做\n")
        rc, out = run(line)
        check(
            rc == 0 and "[A005] ⚠️" in out and "T3_执行中少提示词.md" in out
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
    check("协作规矩.md" in readme_tpl, "assets/任务卡_README.md must point to 协作规矩.md")
    check("| T1 |" not in readme_tpl, "assets/任务卡_README.md must not have real '| T1 |' example row")

    rules_tpl = (REPO / "assets" / "协作规矩.md").read_text(encoding="utf-8")
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
        check(kw in rules_tpl, f"assets/协作规矩.md missing keyword: {kw}")

    agents_tpl = (REPO / "assets" / "AGENTS.md").read_text(encoding="utf-8")
    for kw in ("archive_status.py", "环境坑.md", "重开最终交付物", "计数与派生数一律由脚本", "决策登记表_全文.md"):
        check(kw in agents_tpl, f"assets/AGENTS.md missing keyword: {kw}")

    card_tpl = (REPO / "assets" / "任务卡_模板.md").read_text(encoding="utf-8")
    for kw in ("主控在立项前看过什么", "## 会出错", "NEEDS_FIX", "环境坑.md", "文档/协作规矩.md", "产物类型", "成品给谁看"):
        check(kw in card_tpl, f"assets/任务卡_模板.md missing keyword: {kw}")

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
        write(line / "文档" / "协作规矩.md", (REPO / "assets" / "协作规矩.md").read_text(encoding="utf-8"))
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
    """C7: 协作规矩.md specifies keeping ⏳ and writing '样张待主控看' (not 🟡) for sample handoffs; 任务卡_README.md points to it."""
    readme_tpl = (REPO / "assets" / "任务卡_README.md").read_text(encoding="utf-8")
    readme_rules_ptr = readme_tpl.split("## 卡面规矩", 1)[1].split("## 例行签核提示词", 1)[0]
    check("协作规矩.md" in readme_rules_ptr, "assets/任务卡_README.md 卡面规矩 must point to 协作规矩.md")
    rules_tpl = (REPO / "assets" / "协作规矩.md").read_text(encoding="utf-8")
    check(
        "样张待主控看" in rules_tpl and "⏳" in rules_tpl and "🟡" in rules_tpl,
        "assets/协作规矩.md must document staged sample handoff rule (⏳ + 样张待主控看, not 🟡)",
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
    for fp in (REPO / "tests" / "test_skill.py", HANDOFF_LIB, CHECKER, ARCHIVER):
        src = fp.read_text(encoding="utf-8")
        check("dont_write_bytecode = True" in src, f"{fp.name} must set sys.dont_write_bytecode = True")

    # Spawn a subprocess WITHOUT -B or PYTHONDONTWRITEBYTECODE to invoke both scripts' --help
    env_no_b = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    env_no_b["PYTHONIOENCODING"] = "utf-8"
    env_no_b["PYTHONUTF8"] = "1"
    for script in (CHECKER, ARCHIVER):
        res = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env_no_b,
        )
        check(res.returncode == 0, f"{script.name} --help failed")

    check(not (ASSETS_DIR / "__pycache__").exists(), "assets/__pycache__ must not exist after running tests/scripts")


def test_041_d3_versions_and_changelog() -> None:
    """D3: All three scripts expose __version__ == '0.4.2' and --version; CHANGELOG.md documents 0.4.2."""
    check(getattr(hl_mod, "__version__", None) == "0.4.2", "handoff_lib.__version__ must be '0.4.2'")
    check(getattr(checker_mod, "__version__", None) == "0.4.2", "check_handoff.__version__ must be '0.4.2'")
    check(getattr(archiver_mod, "__version__", None) == "0.4.2", "archive_status.__version__ must be '0.4.2'")

    for script in (CHECKER, ARCHIVER):
        res = subprocess.run(
            [sys.executable, "-B", str(script), "--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        combined = (res.stdout + res.stderr).strip()
        check(res.returncode == 0 and "0.4.2" in combined, f"{script.name} --version must output 0.4.2, got: {combined}")

    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    check(bool(re.search(r"(?m)^##\s+0\.4\.2\b", changelog)), "CHANGELOG.md must have a ## 0.4.2 section")
    check(bool(re.search(r"(?m)^##\s+0\.4\.1\b", changelog)), "CHANGELOG.md must preserve ## 0.4.1 section")


def test_041_r1_mixed_heading_levels_and_archive() -> None:
    """R1: Both ## and ### handoff headings form independent segments; latest handoff date spans all; archiver preserves count & order."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        # §3 is 2026-09-15; STATUS has ## Handoff (09-05) with ### inner headings, then ### 交接 (09-15)
        mixed_status = (
            "# STATUS\n\n"
            "## Handoff（2026-09-05，旧段）\n"
            "### 改了什么\n完成初版。\n### 怎么验证的\n脚本通过。\n### 没做什么\n无。\n### 不确定处\n无。\n\n"
            "## 附录记录\n\n"
            "### 交接（2026-09-15，新段三级标题）\n"
            "- **谁做的**：执行方\n- **改了什么**：完成返修。\n- **怎么验证的**：测试全过。\n- **没做什么**：无。\n- **不确定处**：无。\n"
        )
        write(line / "STATUS.md", mixed_status)
        blocks = checker_mod.handoff_blocks(mixed_status)
        _, arch_blocks, _ = archiver_mod.parse_status(mixed_status)
        check(len(blocks) == 2, f"checker must split ## and ### handoff into 2 blocks, got {len(blocks)}")
        check(len(arch_blocks) == 2, f"archiver must split ## and ### handoff into 2 blocks, got {len(arch_blocks)}")
        rc, out = run(line)
        check(rc == 0 and "[H003] ✅" in out and "[H006] ✅" in out and "[A011] ✅" in out,
              "mixed ## and ### handoff headings must use latest date 2026-09-15 and pass H003/H006/A011:\n" + out)

        # Reverse mixed order: ### (09-05) followed by ## (09-15), 12 total blocks -> archive keeps 10, archives 2, preserves order
        segs = []
        for day in range(4, 16):
            hashes = "##" if day % 2 == 0 else "###"
            d_str = f"2026-09-{day:02d}"
            if day in (6, 10, 14):
                segs.append(
                    f"{hashes} Handoff（{d_str}，第{day}段）\n"
                    f"### 改了什么\n改{day}。\n### 怎么验证的\n验{day}。\n### 没做什么\n无。\n### 不确定处\n无。"
                )
            else:
                segs.append(
                    f"{hashes} 交接（{d_str}，第{day}段）\n"
                    f"- **改了什么**：改{day}。\n- **怎么验证的**：验{day}。\n- **没做什么**：无。\n- **不确定处**：无。"
                )
        status_12 = "# STATUS.md\n\n## 现状一屏（2026-09-15 更新）\n> **阶段**：测试\n\n" + "\n\n".join(segs) + "\n"
        write(line / "STATUS.md", status_12)
        check(len(checker_mod.handoff_blocks(status_12)) == 12, "12 mixed blocks before archive")
        check(len(archiver_mod.parse_status(status_12)[1]) == 12, "archiver must see 12 mixed blocks")

        arc_rc, arc_out, _ = run_archiver(line, "--keep", "10")
        check(arc_rc == 0 and "已归档 2 段" in arc_out and "保留 10 段" in arc_out, "archiver output mismatch:\n" + arc_out)
        after_status = (line / "STATUS.md").read_text(encoding="utf-8")
        arch_file = line / "文档" / "STATUS_归档_至2026-09-05.md"
        check(arch_file.is_file(), "archived file up to 2026-09-05 must exist")
        kept_b = checker_mod.handoff_blocks(after_status)
        arch_b = checker_mod.handoff_blocks(arch_file.read_text(encoding="utf-8"))
        check(len(kept_b) == 10 and len(arch_b) == 2, f"segment count must be conserved (10+2), got {len(kept_b)}+{len(arch_b)}")
        check("2026-09-04" in arch_b[0] and "2026-09-05" in arch_b[1], "archived blocks order must be preserved")
        check("2026-09-06" in kept_b[0] and "2026-09-15" in kept_b[-1], "kept blocks order must be preserved")


def test_041_r2_card_state_ignores_fenced_blocks() -> None:
    """R2: single_card_state strips fenced code blocks inside 进度回写 before matching 状态 line."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        write(cards_dir / "T1_初稿.md", "# T1\n\n## 进度回写\n- 状态：✅已收口\n")

        # Case 1: fenced ✅ example BEFORE real ⬜可派 -> must read ⬜ (unticked T2 on §4 passes A007)
        write(
            cards_dir / "T2_方法.md",
            "# T2 方法\n\n## 进度回写\n"
            "```markdown\n- 状态：✅已收口\n```\n"
            "- 状态：⬜可派\n\n"
            "## 📋 执行方派发提示词\n做\n\n## 📋 独立复核方派发提示词\n核\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A007] ✅" in out, "fenced ✅ before real ⬜ must not cause A007 false alarm:\n" + out)

        # Case 2: ~~~ fenced ⬜ example BEFORE real ✅已收口 on a >16KB closed card without prompts -> must read ✅
        agents_closed = (line / "AGENTS.md").read_text(encoding="utf-8").replace("- [ ] T2 方法", "- [x] T2 方法")
        write(line / "AGENTS.md", agents_closed)
        write(
            cards_dir / "T2_方法.md",
            "# T2 方法\n\n## 进度回写\n"
            "~~~text\n- 状态：⬜可派\n~~~\n"
            "- 状态：✅已收口\n\n## 历史内容\n" + ("甲" * 6000) + "\n",
        )
        rc2, out2 = run(line)
        check(
            rc2 == 0 and "[A005] ✅" in out2 and "[A006] ✅" in out2 and "[A007] ✅" in out2,
            "fenced ⬜ before real ✅ must treat card as closed across A005/A006/A007:\n" + out2,
        )


def test_041_r3_non_hyphen_handoff_dates_and_clear_h005_h006() -> None:
    """R3: 2026/11/11, 2026.11.11, 2026年11月11日 recognized in handoffs; H005/H006 explain exact failure reason."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        for heading in (
            "## 交接（2026/09/15）",
            "## Handoff（2026.09.15）",
            "## 交接（2026年9月15日）",
            "## 2026/9/15 主控补记",
            "## T2（2026.9.15）",
        ):
            write(
                line / "STATUS.md",
                f"# STATUS\n\n{heading}\n"
                "- **谁做的**：执行方\n- **改了什么**：完成修改。\n- **怎么验证的**：脚本通过。\n- **没做什么**：无。\n- **不确定处**：无。\n",
            )
            rc, out = run(line)
            check(rc == 0 and "[H005] ✅" in out and "[H006] ✅" in out,
                  f"non-hyphen handoff heading '{heading}' must pass H005 & H006:\n{out}")

        # H005 & H006 clear messages when handoff has no date / future date / invalid date
        write(
            line / "STATUS.md",
            "# STATUS\n\n## 交接（待补日期）\n"
            "- **谁做的**：执行方\n- **改了什么**：写了超过五十个字的真实正文但忘了写日期，检查器应当说清原因。\n",
        )
        rc_nodate, out_nodate = run(line)
        check(
            rc_nodate == 1 and "未找到真实日期" in out_nodate and "STATUS None" not in out_nodate and "无有效日期" in out_nodate,
            "missing date in handoff must explain clearly in H005 and H006 without 'STATUS None':\n" + out_nodate,
        )

        write(
            line / "STATUS.md",
            "# STATUS\n\n## 交接（2099/01/01）\n"
            "- **谁做的**：执行方\n- **改了什么**：写了未来日期的正文超过五十个字，检查器应当指出是未来日期。\n",
        )
        rc_fut, out_fut = run(line)
        check(
            rc_fut == 1 and "未来日期" in out_fut and "晚于 today" in out_fut,
            "future date must explicitly report future date in H005 and H006:\n" + out_fut,
        )


def test_041_r4_sec3_placeholder_dates_ignored() -> None:
    """R4: Example dates on 【待填】 lines in §3 are excluded from H003/H006/H009; all-placeholder §3 says '§3 还是模板占位'."""
    with tempfile.TemporaryDirectory() as temp:
        proj = Path(temp)
        raw_agents = (REPO / "assets" / "AGENTS.md").read_text(encoding="utf-8")
        # Fill TL;DR and §4, leave §3 untouched (contains '【待填：...例 2026-06-15...】')
        semi_agents = (
            raw_agents
            .replace("【待填：例 T3 进行中】", "T1 进行中（2026-09-14）")
            .replace("【待填：第一个动作，精确到文件/命令】", "跑 python scripts/check_handoff.py")
            .replace("【待填：无 / 等用户确认 X / 等数据下载】", "无")
            .replace("- [ ] **Tx【待填：例 数据清洗（建真实卡后替换示例行）】**", "- [ ] **T1 数据清洗**")
        )
        write(proj / "AGENTS.md", semi_agents)
        write(proj / "CLAUDE.md", (REPO / "assets" / "CLAUDE.md").read_text(encoding="utf-8"))
        write(
            proj / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-09-15）\n"
            "- **谁做的**：执行方\n- **改了什么**：初始化。\n- **怎么验证的**：脚本。\n- **没做什么**：无。\n- **不确定处**：无。\n",
        )
        rc, out = run(proj)
        check(rc == 1 and "[H003] ❌" in out and "[H006] ❌" in out and "[H009] ✅" in out,
              "unfilled §3 must fail H003/H006 and not falsely fail H009:\n" + out)
        check("2026-06-15" not in out, "template example date 2026-06-15 in §3 must never leak into output:\n" + out)
        check("§3 还是模板占位" in out, "all-placeholder §3 must state '§3 还是模板占位':\n" + out)

        # Partially filled §3: real line has 2026-09-14, leftover 【待填】 line has newer date 2026-09-15 -> must use 2026-09-14
        partial_agents = semi_agents.replace(
            "- ✅ 【待填：另一件完成的事】",
            "- ✅ 2026-09-14：完成数据盘点\n- ✅ 【待填：例 2026-09-15：待补充示例】",
        )
        write(proj / "AGENTS.md", partial_agents)
        rc2, out2 = run(proj)
        check(rc2 == 0 and "§3 2026-09-14" in out2,
              "real §3 date 2026-09-14 must be used while ignoring date on leftover 【待填】 line:\n" + out2)


def test_041_s1_relaxed_state_line_and_unparsed_warning() -> None:
    """S1: Card state line allows space before colon and omitted list marker; unparseable card is named in A007."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        agents_all_done = (line / "AGENTS.md").read_text(encoding="utf-8").replace("- [ ] T2 方法", "- [x] T2 方法")
        write(line / "AGENTS.md", agents_all_done)
        cards_dir = line / "文档" / "任务卡"
        write(cards_dir / "T1_初稿.md", "# T1\n\n## 进度回写\n状态：✅已收口\n")
        write(cards_dir / "T2_方法.md", "# T2\n\n## 进度回写\n- 状态 : ✅已收口\n")
        rc, out = run(line)
        check(
            rc == 0 and "[A005] ✅" in out and "[A007] ✅" in out,
            "state lines without bullet ('状态：✅') or with space ('- 状态 : ✅') must parse as closed:\n" + out,
        )

        # Unparseable state line -> A007 names the card explicitly
        write(
            cards_dir / "T2_方法.md",
            "# T2\n\n## 进度回写\n- 状态：已完成但没写图标\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        rc2, out2 = run(line)
        check(
            rc2 == 0 and "[A007] ⚠️" in out2 and "状态行无法解析：T2_方法.md" in out2,
            "card with unparseable state line must be named in A007 warning:\n" + out2,
        )


def test_041_s3_decision_id_normalization() -> None:
    """S3: Decision IDs like D38 and D-38 (or D05 and D-05) are normalized before chain/duplicate checks."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        agents_base = (line / "AGENTS.md").read_text(encoding="utf-8")
        bad_norm_table = (
            "## 3.5 决策登记表\n"
            "| ID | 状态 | 决策 | 取值/口径 | 理由 | 日期 | 证据文档 | 取代了谁 | 被谁取代 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| D-38 | ACTIVE | 水口径 | 产水 | 旧 | 2026-09-10 | 方案 | -- | -- |\n"
            "| D-51 | ACTIVE | 水源涵养 | 平衡法 | 新 | 2026-09-12 | T4c | D38 | -- |\n"
        )
        write(line / "AGENTS.md", agents_base.replace("## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n", bad_norm_table))
        rc, out = run(line)
        check(
            rc == 0 and "[A013] ⚠️" in out and "D-51／D-38" in out,
            "D38 without hyphen referencing D-38 ACTIVE in table must trigger A013:\n" + out,
        )

        good_norm_table = bad_norm_table.replace(
            "| D-38 | ACTIVE | 水口径 | 产水 | 旧 | 2026-09-10 | 方案 | -- | -- |",
            "| D-38 | SUPERSEDED | 水口径 | 产水 | 旧 | 2026-09-10 | 方案 | -- | D51 |",
        )
        write(line / "AGENTS.md", agents_base.replace("## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n", good_norm_table))
        rc2, out2 = run(line)
        check(rc2 == 0 and "[A013] ✅" in out2, "valid chain using D38/D51 shorthand must pass A013:\n" + out2)


def test_041_s7_handoff_heading_words_and_docs() -> None:
    """S7: Headings like '## 交回说明' are NOT treated as handoffs; docs state recognized handoff heading words."""
    skill_md = (REPO / "SKILL.md").read_text(encoding="utf-8")
    status_tpl = (REPO / "assets" / "STATUS.md").read_text(encoding="utf-8")
    check("交回说明" in skill_md and "Handoff" in skill_md and "交接" in skill_md,
          "SKILL.md must document recognized handoff heading words and note '交回说明' is excluded")
    check("交回说明" in status_tpl, "assets/STATUS.md must note '交回说明' is not a handoff heading")

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        status_with_note = (
            "# STATUS\n\n"
            "## Handoff（2026-09-15）\n"
            "- **谁做的**：执行方\n- **改了什么**：初稿。\n- **怎么验证的**：通过。\n- **没做什么**：无。\n- **不确定处**：无。\n\n"
            "## 交回说明\n"
            "这里只是一段补充说明，不是交接段，不含四节。\n"
        )
        write(line / "STATUS.md", status_with_note)
        check(len(checker_mod.handoff_blocks(status_with_note)) == 1, "'## 交回说明' must not count as a handoff in checker")
        check(len(archiver_mod.parse_status(status_with_note)[1]) == 1, "'## 交回说明' must not count as a handoff in archiver")
        rc, out = run(line)
        check(rc == 0 and "[A011] ✅" in out, "'## 交回说明' must not cause A011 missing-sections warning:\n" + out)


def test_041_s8_subprocess_utf8_no_gbk_error() -> None:
    """S8: All text-mode subprocess calls in test_skill.py explicitly set encoding='utf-8'; bare run emits no stderr decode error."""
    import ast

    src = (REPO / "tests" / "test_skill.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("run", "Popen", "check_output"):
                kw_map = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                is_text = any(
                    k in kw_map and isinstance(kw_map[k], ast.Constant) and kw_map[k].value is True
                    for k in ("text", "universal_newlines")
                )
                if is_text:
                    enc_node = kw_map.get("encoding")
                    check(
                        isinstance(enc_node, ast.Constant) and str(enc_node.value).lower().replace("_", "-") == "utf-8",
                        f"subprocess.{node.func.attr} at line {node.lineno} with text=True must pass encoding='utf-8'",
                    )

    bare_env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    probe = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            f"import sys; sys.path.insert(0, {str(REPO / 'tests')!r}); import test_skill; test_skill.test_041_d2_no_assets_pycache()",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=bare_env,
    )
    check(
        probe.returncode == 0 and "UnicodeDecodeError" not in probe.stderr and "Traceback" not in probe.stderr,
        f"bare subprocess run emitted stderr error:\n{probe.stderr}",
    )


def test_041_s10_index_template_a011_recent_five() -> None:
    """S10: assets/协作规矩.md describes A011 as checking the recent 5 handoff blocks ('最近 5 段')."""
    rules_tpl = (REPO / "assets" / "协作规矩.md").read_text(encoding="utf-8")
    check(
        "最近 5 段交接 ≤800 字" in rules_tpl and "最新交接段 ≤800 字" not in rules_tpl,
        "assets/协作规矩.md must state '最近 5 段交接 ≤800 字' for A011",
    )


def test_041_r2_s1_sec3_heading_date_counted() -> None:
    """R2-S1: Date on the '## 3' heading line is counted toward §3 date (fixing R1 [1:] regression)."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-11-11，最新交接）\n"
            "- **谁做的**：主控\n- **改了什么**：跟进。\n- **怎么验证的**：通过。\n- **没做什么**：无。\n- **不确定处**：无。\n",
        )
        # Exact R1 bug scenario: heading has 2026-11-10, body latest is 2026-10-01, STATUS is 2026-11-11
        agents_s1 = (
            "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n"
            "> - **当前阶段**：收口中（2026-11-10）\n> - **下一步**：复查\n> - **阻塞**：无\n\n"
            "## 3. 现在在哪（截至 2026-11-10）\n"
            "- ✅ 2026-10-01：底座完成\n\n"
            "## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n"
            "## 4. 任务看板\n- [x] T1 初稿\n"
        )
        write(line / "AGENTS.md", agents_s1)
        res = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            res.returncode == 0 and "[H003] ✅" in res.stdout and "§3 2026-11-10" in res.stdout and "[H006] ✅" in res.stdout,
            "§3 heading date 2026-11-10 must be counted and pass H003/H006:\n" + res.stdout,
        )

        # Similar variant 1: '## 3 现在在哪（2026/11/10 更新）' (no dot, slash date) and no date in body bullets
        agents_s1_var = agents_s1.replace(
            "## 3. 现在在哪（截至 2026-11-10）\n- ✅ 2026-10-01：底座完成",
            "## 3 现在在哪（2026/11/10 更新）\n- ✅ 底座已完成（详见主表）",
        )
        write(line / "AGENTS.md", agents_s1_var)
        res_var = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            res_var.returncode == 0 and "[H003] ✅" in res_var.stdout and "§3 2026-11-10" in res_var.stdout,
            "slash date in '## 3 现在在哪（2026/11/10 更新）' without body dates must pass H003:\n" + res_var.stdout,
        )

        # Similar variant 2: placeholder date inside heading '## 3. 现在在哪（【待填：截至 2026-11-10】）' must NOT count
        agents_s1_ph = agents_s1.replace(
            "## 3. 现在在哪（截至 2026-11-10）\n- ✅ 2026-10-01：底座完成",
            "## 3. 现在在哪（【待填：截至 2026-11-10】）\n- ✅ 【待填：最近完成的事】",
        )
        write(line / "AGENTS.md", agents_s1_ph)
        res_ph = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            res_ph.returncode == 1 and "[H003] ❌" in res_ph.stdout and "§3 还是模板占位" in res_ph.stdout,
            "placeholder date inside §3 heading must still be stripped:\n" + res_ph.stdout,
        )


def test_041_r2_s2_inline_placeholder_span_stripping() -> None:
    """R2-S2: Strip only placeholder spans (【待填…】, YYYY-MM-DD, etc.) instead of whole line in §3 and TL;DR."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-11-11，最新交接）\n"
            "- **谁做的**：主控\n- **改了什么**：跟进。\n- **怎么验证的**：通过。\n- **没做什么**：无。\n- **不确定处**：无。\n",
        )

        def _make_agents(tldr_lines: str, sec3_lines: str) -> str:
            return (
                f"# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n{tldr_lines}\n\n"
                f"## 3. 现在在哪\n{sec3_lines}\n\n"
                "## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n"
                "## 4. 任务看板\n- [x] T1 初稿\n"
            )

        clean_tldr = "> - **当前阶段**：交付中（2026-11-10）\n> - **下一步**：收口\n> - **阻塞**：无"

        # Exact R1 bug scenario a: real date + inline 【待填：页数】 on the same §3 line
        write(
            line / "AGENTS.md",
            _make_agents(
                clean_tldr,
                "- ✅ 2026-10-01：底座完成\n- 🔶 交付（2026-11-10）：报告已发【待填：页数】",
            ),
        )
        res_a = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            res_a.returncode == 0 and "[H003] ✅" in res_a.stdout and "§3 2026-11-10" in res_a.stdout,
            "real date 2026-11-10 sharing line with 【待填：页数】 must be counted in §3:\n" + res_a.stdout,
        )

        # Exact R1 bug scenario b: real date + literal YYYY-MM-DD on the same §3 line
        write(
            line / "AGENTS.md",
            _make_agents(
                clean_tldr,
                "- ✅ 2026-10-01：底座完成\n- ✅ 2026-11-10：规定日期写 YYYY-MM-DD 格式",
            ),
        )
        res_b = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            res_b.returncode == 0 and "[H003] ✅" in res_b.stdout and "§3 2026-11-10" in res_b.stdout,
            "real date 2026-11-10 sharing line with literal YYYY-MM-DD must be counted in §3:\n" + res_b.stdout,
        )

        # Similar variant 1: same line has real 2026-11-10 AND newer example date inside 【待填：…】 / [TODO: …]
        write(
            line / "AGENTS.md",
            _make_agents(
                clean_tldr,
                "- ✅ 2026-10-01：底座\n- 🔶 交付（2026-11-10）：已发【待填：例 2026-11-14 补表】 [TODO: 2026/11/15 核对]",
            ),
        )
        res_c = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-15"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            res_c.returncode == 0 and "[H003] ✅" in res_c.stdout and "[H006] ✅" in res_c.stdout and "§3 2026-11-10" in res_c.stdout,
            "placeholder dates on the same line must be stripped while keeping real 2026-11-10:\n" + res_c.stdout,
        )

        # Similar variant 2: TL;DR line has real 2026-11-10 alongside literal YYYY-MM-DD / 【待填：页数】 (check H009 uses 2026-11-10, not older 2026-10-01)
        tldr_mixed = (
            "> - **当前阶段**：底座（2026-10-01）\n"
            "> - **下一步**：2026-11-10 交付件按 YYYY-MM-DD 归档【待填：页数】\n"
            "> - **阻塞**：无"
        )
        write(line / "AGENTS.md", _make_agents(tldr_mixed, "- ✅ 2026-11-10：交付完成"))
        res_d = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            "[H009] ✅" in res_d.stdout and "TL;DR 2026-11-10 vs §3 2026-11-10" in res_d.stdout,
            "TL;DR date extraction must also strip only placeholder spans and keep 2026-11-10 for H009:\n" + res_d.stdout,
        )

        # Similar variant 3: quoted unclosed “【待填” in §3 prose + real project STATUS prose mentioning 【待填】
        write(line / "AGENTS.md", _make_agents(clean_tldr, "- ✅ 排除“【待填”前缀误伤（2026-11-10）"))
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-11-11，T13c 复查）\n"
            "- **谁做的**：复核方\n"
            "- **改了什么**：修复把与【待填】同行的真实日期丢弃的问题。\n"
            "- **怎么验证的**：真实日期与【待填】同行用例通过。\n"
            "- **没做什么**：无。\n"
            "- **不确定处**：带【待填】行的口径已明确。\n",
        )
        res_e = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            res_e.returncode == 0 and "[H003] ✅" in res_e.stdout and "[H005] ✅" in res_e.stdout,
            "quoted unclosed 【待填 in §3 and prose mentioning 【待填】 in STATUS fields must pass H003 & H005:\n" + res_e.stdout,
        )


def test_041_r2_s3_top_level_card_state_and_html_comments() -> None:
    """R2-S3: Card state strips fenced blocks and <!-- --> comments, then matches only unindented top-level 状态 line; rules document '状态行顶格写'."""
    rules_tpl = (REPO / "assets" / "协作规矩.md").read_text(encoding="utf-8")
    check("状态行顶格写" in rules_tpl, "assets/协作规矩.md must state '状态行顶格写'")

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        write(cards_dir / "T1_初稿.md", "# T1\n\n## 进度回写\n- 状态：✅已收口\n")

        # Exact R1 bug scenario 1: 4-space indented code block with '- 状态：✅已收口' before real top-level '- 状态：⬜可派'
        write(
            cards_dir / "T2_方法.md",
            "# T2 方法\n\n## 进度回写\n"
            "示例写法：\n\n"
            "    - 状态：✅已收口\n\n"
            "- 状态：⬜可派\n\n"
            "## 📋 执行方派发提示词\n做\n\n## 📋 独立复核方派发提示词\n核\n",
        )
        rc1, out1 = run(line)
        check(
            rc1 == 0 and "[A007] ✅" in out1 and "1 张在用卡" in out1,
            "4-space indented example '- 状态：✅已收口' must be ignored so card stays ⬜:\n" + out1,
        )

        # Exact R1 bug scenario 2: multiline HTML comment '<!--\n- 状态：✅已收口\n-->' before real '- 状态：⬜可派'
        write(
            cards_dir / "T2_方法.md",
            "# T2 方法\n\n## 进度回写\n"
            "<!--\n- 状态：✅已收口\n-->\n"
            "- 状态：⬜可派\n\n"
            "## 📋 执行方派发提示词\n做\n\n## 📋 独立复核方派发提示词\n核\n",
        )
        rc2, out2 = run(line)
        check(
            rc2 == 0 and "[A007] ✅" in out2 and "1 张在用卡" in out2,
            "multiline HTML comment '<!-- - 状态：✅已收口 -->' must be ignored so card stays ⬜:\n" + out2,
        )

        # Similar variant 1: 2-space indent, tab indent, blockquote '> 状态：✅', and HTML comment with fake '## ' & unclosed fence
        write(
            cards_dir / "T2_方法.md",
            "# T2 方法\n\n## 进度回写\n"
            "  - 状态：✅已收口\n"
            "\t- 状态：✅已收口\n"
            "> 状态：✅已收口 / ⬜可派\n"
            "<!--\n## 假标题节\n```markdown\n- 状态：✅已收口\n-->\n"
            "- 状态：⬜可派\n\n"
            "## 📋 执行方派发提示词\n做\n\n## 📋 独立复核方派发提示词\n核\n",
        )
        rc3, out3 = run(line)
        check(
            rc3 == 0 and "[A007] ✅" in out3 and "1 张在用卡" in out3,
            "2-space/tab indent, blockquote, and multiline comment with ## heading must all be ignored:\n" + out3,
        )

        # Similar variant 2: only indented state line + template '> 状态：🟠...' legend -> must report unparseable, not read ⬜ or 🟠
        write(
            cards_dir / "T2_方法.md",
            "# T2 方法\n\n## 进度回写\n"
            "  - 状态：⬜可派\n"
            "> 状态：🟠待裁定（不可派）/ ⬜可派 / ✅已收口\n\n"
            "## 📋 执行方派发提示词\n做\n\n## 📋 独立复核方派发提示词\n核\n",
        )
        rc4, out4 = run(line)
        check(
            rc4 == 0 and "[A007] ⚠️" in out4 and "状态行无法解析：T2_方法.md" in out4,
            "card with only indented state line (plus blockquote legend) must report 状态行无法解析:\n" + out4,
        )


def test_041_r2_adv1_archive_nonempty_line_conservation() -> None:
    """R2-Adv1: Non-handoff sections/prose before archived segments move into archive file; all non-empty lines are conserved."""
    # Scenario 1 (chronological, exact R1 MARKER_ALPHA / MARKER_BETA scenario + indented prose)
    with tempfile.TemporaryDirectory() as temp:
        proj = Path(temp)
        segs = []
        for day in range(4, 16):  # 12 handoffs: 04, 05 archived; 06..15 kept
            d_str = f"2026-09-{day:02d}"
            prefix = ""
            if day == 5:
                prefix = "## 阶段背景备忘\nMARKER_ALPHA：这段非交接文字在被归档段之前，绝不能两边都丢。\n    INDENTED_ALPHA：四空格缩进备注行\n\n"
            elif day == 6:
                prefix = "## 里程碑过渡说明\nMARKER_BETA：这段非交接文字在首个保留段之前，应留在新 STATUS。\n\n"
            segs.append(
                f"{prefix}## Handoff（{d_str}，T{day}）\n"
                "- **谁做的**：执行方\n"
                f"- **改了什么**：第 {day} 步变更记录。\n"
                "- **怎么验证的**：脚本通过。\n"
                "- **没做什么**：无。\n"
                "- **不确定处**：无。"
            )
        before_text = (
            "# STATUS.md — 增量 Handoff\n\n> 本文件只记增量。\n\n"
            + "\n\n".join(segs)
            + "\n\n## 尾部附注\nMARKER_GAMMA：末尾非交接附注行。\n"
        )
        write(proj / "STATUS.md", before_text)
        before_nonempty = [ln for ln in before_text.splitlines() if ln.strip()]

        arc_rc, arc_out, _ = run_archiver(proj, "--keep", "10")
        check(arc_rc == 0 and "已归档 2 段" in arc_out, "archive_status must archive 2 segments:\n" + arc_out)

        new_status = (proj / "STATUS.md").read_text(encoding="utf-8")
        arch_file = proj / "文档" / "STATUS_归档_至2026-09-05.md"
        check(arch_file.is_file(), "archive file must exist")
        arch_text = arch_file.read_text(encoding="utf-8")

        check("MARKER_ALPHA" in arch_text and "INDENTED_ALPHA" in arch_text,
              "gap before archived block (MARKER_ALPHA) must be written into archive file:\n" + arch_text)
        check("MARKER_BETA" in new_status and "MARKER_GAMMA" in new_status,
              "gap before kept block (MARKER_BETA) and trailing note (MARKER_GAMMA) must stay in STATUS.md:\n" + new_status)

        combined_lines = set(new_status.splitlines()) | set(arch_text.splitlines())
        missing_lines = [ln for ln in before_nonempty if ln not in combined_lines]
        check(not missing_lines, f"non-empty lines lost after archiving: {missing_lines}")

    # Similar variant: reverse-chronological STATUS (newest on top, oldest at bottom) with gap before archived tail
    with tempfile.TemporaryDirectory() as temp:
        proj = Path(temp)
        rev_segs = []
        for day in range(15, 3, -1):  # 15..06 kept, 05..04 archived
            d_str = f"2026-09-{day:02d}"
            prefix = "## 早期散记\nMARKER_REV_GAP：倒序排布时旧段前面的散文字。\n\n" if day == 5 else ""
            rev_segs.append(
                f"{prefix}## Handoff（{d_str}，T{day}）\n"
                "- **谁做的**：执行方\n"
                f"- **改了什么**：倒序第 {day} 步。\n"
                "- **怎么验证的**：通过。\n"
                "- **没做什么**：无。\n"
                "- **不确定处**：无。"
            )
        rev_before = "# STATUS.md\n\n" + "\n\n".join(rev_segs) + "\n"
        write(proj / "STATUS.md", rev_before)
        rev_nonempty = [ln for ln in rev_before.splitlines() if ln.strip()]

        arc_rc2, _, _ = run_archiver(proj, "--keep", "10")
        check(arc_rc2 == 0, "reverse-chronological archive must succeed")
        new_rev = (proj / "STATUS.md").read_text(encoding="utf-8")
        arch_rev = (proj / "文档" / "STATUS_归档_至2026-09-05.md").read_text(encoding="utf-8")
        check("MARKER_REV_GAP" in arch_rev, "MARKER_REV_GAP in reverse-chrono STATUS must enter archive file")
        missing_rev = [ln for ln in rev_nonempty if ln not in (set(new_rev.splitlines()) | set(arch_rev.splitlines()))]
        check(not missing_rev, f"reverse-chrono non-empty lines lost after archiving: {missing_rev}")


def test_041_r2_adv2_7_h4_excluded_in_docs_and_a011() -> None:
    """R2-Adv2&7: #### and deeper headings are not handoff segments; SKILL.md, assets/STATUS.md, and A011 message state this explicitly."""
    skill_md = (REPO / "SKILL.md").read_text(encoding="utf-8")
    status_tpl = (REPO / "assets" / "STATUS.md").read_text(encoding="utf-8")
    check("####" in skill_md and "不算交接" in skill_md, "SKILL.md must state #### and deeper headings do not count as handoffs")
    check("####" in status_tpl and "不算交接" in status_tpl, "assets/STATUS.md must state #### and deeper headings do not count as handoffs")

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        for deep_head in ("#### Handoff（2026-09-15）", "##### 交接（2026-09-15）"):
            deep_status = (
                f"# STATUS\n\n{deep_head}\n"
                "- **谁做的**：执行方\n- **改了什么**：四级标题测试。\n- **怎么验证的**：脚本。\n- **没做什么**：无。\n- **不确定处**：无。\n"
            )
            write(line / "STATUS.md", deep_status)
            check(len(checker_mod.handoff_blocks(deep_status)) == 0, f"{deep_head} must not form a handoff block")
            rc, out = run(line)
            check(
                rc == 1 and "[H006] ❌" in out and "[A011] ⚠️" in out and "####" in out and "不算" in out,
                f"A011 warning on {deep_head} must note #### headings do not count, and V4 H006 must not fall back to heading date:\n{out}",
            )


def test_041_r2_adv3_changelog_notes_bare_jiaohui() -> None:
    """R2-Adv3: CHANGELOG.md records behavior change that bare '## 交回' no longer counts as a handoff heading."""
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    sec_041 = changelog.split("## 0.4.0", 1)[0]
    check(
        "## 交回" in sec_041 and "不再算交接" in sec_041,
        "CHANGELOG.md 0.4.1 section must document that bare '## 交回' no longer counts as a handoff:\n" + sec_041,
    )
    # Verify actual behavior matches CHANGELOG note (bare '## 交回（日期）' excluded, while '## T13c 交回（日期）' counts)
    for bare in ("## 交回", "## 交回（2026-09-15）", "### 交回备注"):
        s = f"# STATUS\n\n{bare}\n正文。\n"
        check(len(checker_mod.handoff_blocks(s)) == 0, f"bare '{bare}' without T<id>+date or leading date must not count")
    with_tid = "# STATUS\n\n## T13c 交回（2026-09-15）\n正文。\n"
    check(len(checker_mod.handoff_blocks(with_tid)) == 1, "'## T13c 交回（2026-09-15）' must still count as handoff")


def test_042_conv3_role() -> None:
    """0.4.2 Conv1 & Conv3: missing handoff_lib.py exits 2 with clear message; --role executor/reviewer skips AGENTS.md and checks STATUS + --card."""
    import shutil

    # Conv1: copying only the two CLI scripts without handoff_lib.py exits 2 with the exact prompt
    with tempfile.TemporaryDirectory() as temp:
        isolated = Path(temp) / "scripts"
        isolated.mkdir(parents=True)
        shutil.copy2(CHECKER, isolated / "check_handoff.py")
        shutil.copy2(ARCHIVER, isolated / "archive_status.py")
        for script_name in ("check_handoff.py", "archive_status.py"):
            res_no_lib = subprocess.run(
                [sys.executable, "-B", str(isolated / script_name)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
            )
            combined = (res_no_lib.stdout or "") + (res_no_lib.stderr or "")
            check(
                res_no_lib.returncode == 2 and "请把 handoff_lib.py 一起复制到同一目录" in combined,
                f"{script_name} without handoff_lib.py must exit 2 with copy hint:\nrc={res_no_lib.returncode}\n{combined}",
            )

    # Conv3: --role executor / reviewer skips all AGENTS.md checks, checks STATUS + optional --card
    with tempfile.TemporaryDirectory() as temp:
        proj = Path(temp)
        # Deliberately omit AGENTS.md completely (controller mode would fail H001/H003/H004/H006/H008)
        write(
            proj / "STATUS.md",
            "# STATUS.md\n\n"
            "## Handoff（2026-09-10，旧段故意缺节验证只查最近一段）\n"
            "- 旧段随便写写但超过五十个字，验证 executor 只查最近一段而不被历史旧段拖累。\n\n"
            "## Handoff（2026-09-15，T5 交回）\n"
            "- **谁做的**：工具 Antigravity / 模型 Gemini 4 Carbon / 家族 Google\n"
            "- **改了什么**：完成 T5 解析。\n"
            "- **怎么验证的**：测试全过。\n"
            "- **没做什么**：不推送。\n"
            "- **不确定处**：无。\n",
        )
        rc_ctrl, out_ctrl = run(proj)
        check(rc_ctrl == 1 and "[H001] ❌" in out_ctrl, "controller without AGENTS.md must fail H001")

        rc_exec, out_exec = run(proj, "--role", "executor")
        first_ln = out_exec.splitlines()[0] if out_exec.splitlines() else ""
        check(
            rc_exec == 0 and "角色=executor" in first_ln and "AGENTS.md" in first_ln and "[H001]" not in out_exec,
            f"--role executor must pass without AGENTS.md and explain skipped items on line 1:\n{out_exec}",
        )

        # Add card T5: executor filled, reviewer unfilled
        card_t5 = proj / "文档" / "任务卡" / "T5_解析模块.md"
        write(
            card_t5,
            "# T5 解析模块\n\n## 进度回写\n\n"
            "- 状态：🟡待复核\n"
            "- 执行方：工具【Antigravity】/ 模型【Gemini 4 Carbon】/ 家族【Google】/ 开工【2026-09-15】/ 交回【2026-09-15】；产物【handoff_lib.py】\n"
            "- 复核方：工具【】/ 模型【】/ 家族【】/ 日期【】；结论【】；报告【】\n",
        )
        rc_e_ok, out_e_ok = run(proj, "--role", "executor", "--card", "T5")
        check(rc_e_ok == 0 and "[A007] ✅" in out_e_ok and "[A009] ✅" in out_e_ok, f"executor with filled T5 must pass:\n{out_e_ok}")

        # Reviewer has not filled 工具/模型/家族 yet -> must fail A007
        rc_r_bad, out_r_bad = run(proj, "--role", "reviewer", "--card", "T5")
        check(
            rc_r_bad == 1 and "复核方未填" in out_r_bad and "角色=reviewer" in out_r_bad.splitlines()[0],
            f"reviewer with empty 工具/模型/家族 on T5 must fail:\n{out_r_bad}",
        )

        # Fill reviewer, then make progress row >400 chars -> must fail A009
        write(
            card_t5,
            "# T5 解析模块\n\n## 进度回写\n\n"
            "- 状态：🔵待收口\n"
            "- 执行方：工具【Antigravity】/ 模型【Gemini 4 Carbon】/ 家族【Google】\n"
            "- 复核方：工具【Devin】/ 模型【SWE-2 Max】/ 家族【Cognition】；说明【" + ("核" * 405) + "】\n",
        )
        rc_r_long, out_r_long = run(proj, "--role", "reviewer", "--card", "t5")
        check(rc_r_long == 1 and "[A009] ❌" in out_r_long and "行 " in out_r_long, f"reviewer >400 char row must fail A009:\n{out_r_long}")

        # Fix length, break state line -> must fail A007
        write(
            card_t5,
            "# T5 解析模块\n\n## 进度回写\n\n"
            "  - 状态：🔵待收口\n"
            "- 复核方：工具【Devin】/ 模型【SWE-2 Max】/ 家族【Cognition】\n",
        )
        rc_r_nostate, out_r_nostate = run(proj, "--role", "reviewer", "--card", "T5")
        check(rc_r_nostate == 1 and "状态行无法解析" in out_r_nostate, f"unparseable state line must fail A007:\n{out_r_nostate}")

        # Break latest STATUS handoff (>800 chars or missing section) -> must fail A011
        write(
            proj / "STATUS.md",
            "# STATUS.md\n\n## Handoff（2026-09-15，缺节交接）\n"
            "- **谁做的**：复核方\n- **改了什么**：写了超过五十个字的报告内容以通过非模板检查但故意漏掉后面三节。\n",
        )
        rc_bad_st, out_bad_st = run(proj, "--role", "reviewer")
        check(rc_bad_st == 1 and "[A011] ❌" in out_bad_st and "缺节" in out_bad_st, f"missing handoff sections must fail in reviewer role:\n{out_bad_st}")


def test_042_conv4_config() -> None:
    """0.4.2 Conv4: handoff_config.json configures docs_dir/cards_dir/index_file/review_dirs; bad JSON/keys warn & fallback without crashing."""
    import json

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        write(
            line / "STATUS.md",
            "# STATUS\n\n"
            + "\n\n".join(
                f"## Handoff（2026-09-{d:02d}，T{d}）\n"
                f"- **谁做的**：主控\n- **改了什么**：第 {d} 轮。\n- **怎么验证的**：通过。\n- **没做什么**：无。\n- **不确定处**：无。"
                for d in range(4, 16)
            )
            + "\n",
        )
        write(
            line / "文档" / "任务卡_README.md",
            "| 卡 | 做什么 | 状态 | 文件 |\n|---|---|---|---|\n| T1 | 初稿 | ✅已收口 | `任务卡/T1_初稿.md` |\n| T2 | 方法 | ⬜可派 | `任务卡/T2_方法.md` |\n",
        )
        write(line / "文档" / "任务卡" / "T1_初稿.md", "# T1\n\n## 进度回写\n- 状态：✅已收口\n")
        write(
            line / "文档" / "任务卡" / "T2_方法.md",
            "# T2\n\n## 进度回写\n- 状态：⬜可派\n\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
        )
        write(line / "文档" / "T2_复核_SWE2_2026-09-15.md", "# T2 复核\n\n## 会出错\n无\n\n## 建议\n无\n\nPASS\n")
        write(line / "文档" / "协作规矩.md", (REPO / "assets" / "协作规矩.md").read_text(encoding="utf-8"))

        rc_before, out_before = run(line)
        check(rc_before == 0, f"fixture before rename must pass:\n{out_before}")

        # Rename 文档 -> docs and write handoff_config.json -> byte-identical check_handoff output
        (line / "文档").rename(line / "docs")
        (line / "handoff_config.json").write_text(
            json.dumps(
                {
                    "docs_dir": "docs",
                    "cards_dir": "docs/任务卡",
                    "index_file": "docs/任务卡_README.md",
                    "review_dirs": ["docs", "reports"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        rc_after, out_after = run(line)
        check(
            rc_after == rc_before and out_after == out_before,
            f"check_handoff output after renaming 文档 -> docs with handoff_config.json must be byte-identical!\nBEFORE:\n{out_before}\nAFTER:\n{out_after}",
        )

        # archive_status writes archive files into configured docs_dir ("docs/")
        arc_rc, arc_out, _ = run_archiver(line, "--keep", "10")
        check(arc_rc == 0 and "docs/STATUS_归档_至2026-09-05.md" in arc_out, f"archiver must write to docs/:\n{arc_out}")
        check((line / "docs" / "STATUS_归档_至2026-09-05.md").is_file(), "archive file must be created inside docs/")
        check(not (line / "文档").exists(), "archiver must not recreate hardcoded 文档/")

        # Unknown key in handoff_config.json -> prints warning and uses default for missing keys, never crashes
        (line / "docs").rename(line / "文档")
        (line / "handoff_config.json").write_text('{"typo_key": "abc"}', encoding="utf-8")
        rc_unk, out_unk = run(line)
        check(rc_unk == 0 and "提示：handoff_config.json" in out_unk and "typo_key" in out_unk, f"unknown key must warn and fallback:\n{out_unk}")

        # Broken JSON -> prints warning and uses defaults, never crashes
        (line / "handoff_config.json").write_text("{broken json!!!", encoding="utf-8")
        rc_bad, out_bad = run(line)
        check(rc_bad == 0 and "提示：handoff_config.json 解析失败" in out_bad, f"broken JSON must warn and fallback:\n{out_bad}")
        arc_bad_rc, arc_bad_out, _ = run_archiver(line, "--dry-run")
        check(arc_bad_rc == 0 and "提示：handoff_config.json 解析失败" in arc_bad_out, f"archiver on broken JSON must warn and fallback:\n{arc_bad_out}")


def test_042_conv5_archive_keep_active_cards() -> None:
    """0.4.2 Conv5: archive_status keeps older handoff blocks mentioning active cards without consuming --keep N slots."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        segs = [
            f"## Handoff（2026-09-{d:02d}，{'T2 样张交回' if d in (2, 4) else f'T1 第{d}轮'}）\n"
            f"- **谁做的**：执行方\n- **改了什么**：第 {d} 轮内容 MARK_{d:02d}。\n- **怎么验证的**：通过。\n- **没做什么**：无。\n- **不确定处**：无。"
            for d in range(1, 15)
        ]
        orig_status = "# STATUS\n\n" + "\n\n".join(segs) + "\n"
        write(line / "STATUS.md", orig_status)

        # Case 1: T1 ✅ closed, T2 🔵 active -> --keep 10 keeps 10 newest (05..14) + 2 active T2 blocks (02, 04) = 12 kept, 2 archived (01, 03)
        cards_dir = line / "文档" / "任务卡"
        write(cards_dir / "T1_已收口.md", "# T1\n\n## 进度回写\n- 状态：✅已收口\n")
        write(cards_dir / "T2_图集.md", "# T2\n\n## 进度回写\n- 状态：🔵待收口\n")

        arc_rc, arc_out, _ = run_archiver(line, "--keep", "10")
        check(
            arc_rc == 0 and "已归档 2 段" in arc_out and "保留 12 段" in arc_out and "多留了 2 段" in arc_out,
            f"active T2 blocks must stay without eating keep=10 quota:\n{arc_out}",
        )
        new_st = (line / "STATUS.md").read_text(encoding="utf-8")
        arch_text = (line / "文档" / "STATUS_归档_至2026-09-03.md").read_text(encoding="utf-8")
        for d in (2, 4, *range(5, 15)):
            check(f"MARK_{d:02d}" in new_st and f"MARK_{d:02d}" not in arch_text, f"day {d} must remain in STATUS.md")
        for d in (1, 3):
            check(f"MARK_{d:02d}" in arch_text and f"MARK_{d:02d}" not in new_st, f"closed day {d} must move to archive")

        # Case 2: No task cards directory -> behaves identically to 0.4.1 (archives 4 oldest, keeps 10)
        line2 = build(Path(temp) / "nocards")
        write(line2 / "STATUS.md", orig_status)
        arc2_rc, arc2_out, _ = run_archiver(line2, "--keep", "10")
        check(
            arc2_rc == 0 and "已归档 4 段" in arc2_out and "保留 10 段" in arc2_out and "多留" not in arc2_out,
            f"missing cards dir must behave identically to 0.4.1:\n{arc2_out}",
        )


def test_042_v1_comment_boundaries() -> None:
    """0.4.2 V1: inline-code `<!--`, empty comments <!--> / <!--->, and unclosed <!-- never swallow subsequent 状态 lines."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        write(cards_dir / "T1_初稿.md", "# T1\n\n## 进度回写\n- 状态：✅已收口\n")

        for label, snippet in (
            ("inline code `<!--`", "- 说明：行内反引号里的 `<!--` 不是注释起点\n- 状态：⬜可派\n"),
            ("empty comment <!-->", "<!-->\n- 状态：⬜可派\n"),
            ("empty comment <!--->", "<!--->\n- 状态：⬜可派\n"),
            ("unclosed <!--", "备注：手滑写了没闭合的 <!-- 注释头\n- 状态：⬜可派\n"),
            (
                "bt_wrongread (`<!--` before real ⬜ and closed comment before fake ✅)",
                "- 说明：先出现 `<!--`\n- 状态：⬜可派\n<!-- 正常闭合 -->\n- 状态：✅已收口\n",
            ),
        ):
            write(
                cards_dir / "T2_方法.md",
                f"# T2 方法\n\n## 进度回写\n{snippet}\n## 📋 执行方提示词\n做\n\n## 📋 复核方提示词\n核\n",
            )
            rc, out = run(line)
            check(
                rc == 0 and "[A007] ✅" in out and "[A005] ✅" in out and "1 张在用卡" in out,
                f"V1 failed on {label}:\n{out}",
            )


def test_042_v2_bare_placeholder_dates() -> None:
    """0.4.2 V2: bare template-example dates (e.g. '例 T3 进行中（2026-06-15）', '例 2026-06-15：数据集 X...') excluded from §3 and TL;DR dates."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        write(
            line / "STATUS.md",
            "# STATUS\n\n## Handoff（2026-11-11，最新交接）\n"
            "- **谁做的**：主控\n- **改了什么**：更新。\n- **怎么验证的**：通过。\n- **没做什么**：无。\n- **不确定处**：无。\n",
        )
        # Exact R2 S2-g scenario: TL;DR has bare '例 T3 进行中（2026-06-15）', §3 has real 2026-11-10 -> H009 must NOT read 2026-06-15
        agents_s2g = (
            "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n"
            "> - **当前阶段**：例 T3 进行中（2026-06-15）\n> - **下一步**：派 T4\n> - **阻塞**：无\n\n"
            "## 3. 现在在哪\n- ✅ 2026-11-10：底座完成\n\n"
            "## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n## 4. 任务看板\n- [x] T1 初稿\n"
        )
        write(line / "AGENTS.md", agents_s2g)
        res = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            "[H009] ✅" in res.stdout and "2026-06-15" not in res.stdout,
            f"bare '例 T3 进行中（2026-06-15）' must not leak 2026-06-15 into H009:\n{res.stdout}",
        )

        # Bare §3 template sentence without 【待填】 brackets -> §3 date must be None ('§3 还是模板占位'), not 2026-06-15
        agents_sec3_bare = (
            "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n"
            "> - **当前阶段**：底座推进中\n> - **下一步**：清洗数据\n> - **阻塞**：无\n\n"
            "## 3. 现在在哪\n- ✅ 最近完成的事，带日期。例 2026-06-15：数据集 X 已下载清洗，落在 data/\n\n"
            "## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n## 4. 任务看板\n- [x] T1 初稿\n"
        )
        write(line / "AGENTS.md", agents_sec3_bare)
        res2 = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-11-11"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
        )
        check(
            "2026-06-15" not in res2.stdout and "§3 还是模板占位" in res2.stdout,
            f"bare §3 example sentence must report 还是模板占位 without 2026-06-15:\n{res2.stdout}",
        )


def test_042_v3_commented_handoff_headings() -> None:
    """0.4.2 V3: commented-out handoff headings in STATUS.md are not counted as segments by checker or archiver."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        segs = [
            f"## Handoff（2026-09-{d:02d}，T1 第{d}轮）\n"
            f"- **谁做的**：主控\n- **改了什么**：完成第 {d} 轮。\n- **怎么验证的**：通过。\n- **没做什么**：无。\n- **不确定处**：无。"
            for d in range(6, 16)  # exactly 10 real segments
        ]
        status_txt = (
            "# STATUS.md\n\n"
            "<!--\n## Handoff（2020-01-01，注释里的模板旧段）\n- 缺四节也不该报错\n-->\n\n"
            "<!-- ## Handoff（2099-12-31，单行注释里的未来段） -->\n\n"
            + "\n\n".join(segs)
            + "\n"
        )
        write(line / "STATUS.md", status_txt)

        check(len(checker_mod.handoff_blocks(status_txt)) == 10, "checker must ignore commented handoff headings (count=10)")
        check(len(archiver_mod.parse_status(status_txt)[1]) == 10, "archiver must ignore commented handoff headings (count=10)")

        rc, out = run(line)
        check(
            rc == 0 and "[H003] ✅" in out and "[H006] ✅" in out and "[A011] ✅" in out,
            f"commented handoff headings must not pollute H003/H006/A011:\n{out}",
        )

        # With --keep 10 and 10 real segments (+ 2 commented phantom headings), archiver must treat as <=10 and no-op!
        arc_rc, arc_out, _ = run_archiver(line, "--keep", "10")
        check(
            arc_rc == 0 and "共 10 段交接（≤ 10），无需归档" in arc_out,
            f"archiver must count 10 segments and no-op instead of archiving commented heading:\n{arc_out}",
        )


def test_042_v4_h006_fallback_body_only() -> None:
    """0.4.2 V4: When STATUS has no handoff blocks, H006 fallback ignores non-handoff headings and labels body fallback source."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        # Case 1: Only non-handoff heading '## 附录（2026-09-15）' has >= §3 date; body has older 2026-09-01 -> H006 MUST FAIL
        write(
            line / "STATUS.md",
            "# STATUS.md\n\n## 附录（2026-09-15）\n"
            "本节只是背景附录文字，建档正文日期是 2026-09-01，用来验证非交接小节标题里的日期不能顶替交接日期通过检查。\n",
        )
        rc1, out1 = run(line)
        check(
            rc1 == 1 and "[H006] ❌" in out1 and "STATUS 正文" in out1 and "2026-09-01" in out1,
            f"non-handoff heading date 2026-09-15 must not satisfy H006 fallback:\n{out1}",
        )

        # Case 2: Body has valid >= §3 date 2026-09-15 without handoff blocks -> H006 passes and explicitly states source
        write(
            line / "STATUS.md",
            "# STATUS.md\n\n## 背景说明\n"
            "本文件尚无交接段标题，但在正文里记录了最新建档推进日期 2026-09-15，应走正文兜底并写明来源。\n",
        )
        rc2, out2 = run(line)
        check(
            rc2 == 0 and "[H006] ✅" in out2 and "来自 STATUS 正文兜底" in out2,
            f"H006 fallback pass must explicitly state date comes from STATUS 正文:\n{out2}",
        )


def test_042_v5_h3_progress_section() -> None:
    """0.4.2 V5: '### 进度回写' is recognized identically to '## 进度回写' across A005/A006/A007/A009 and --role."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        write(cards_dir / "T1_初稿.md", "# T1\n\n### 进度回写\n- 状态：✅已收口\n")
        write(
            cards_dir / "T2_方法.md",
            "# T2 方法\n\n### 进度回写（三级标题）\n"
            "- 状态：⬜可派\n"
            "- 执行方：工具【Antigravity】/ 模型【Gemini 4 Carbon】/ 家族【Google】\n\n"
            "### 📋 执行方派发提示词\n做\n\n### 📋 独立复核方派发提示词\n核\n",
        )
        rc, out = run(line)
        check(
            rc == 0 and "[A005] ✅" in out and "[A007] ✅" in out and "2 张卡有“进度回写”" in out,
            f"### 进度回写 must be parsed cleanly without 状态行无法解析:\n{out}",
        )


def test_042_v6_card_id_case_and_collision() -> None:
    """0.4.2 V6: card ID comparison is case-insensitive; colliding card IDs warn and name both files."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        # Lowercase filename t1_初稿.md closed ✅ while §4 has unticked '- [ ] T1 初稿' and index has 'T1 | ⬜' -> case-insensitive drift!
        base_agents = (line / "AGENTS.md").read_text(encoding="utf-8")
        write(line / "AGENTS.md", base_agents.replace("- [x] T1 初稿", "- [ ] T1 初稿"))
        write(line / "文档" / "任务卡_README.md", "| 卡号 | 状态 |\n|---|---|\n| T1 | ⬜ |\n")
        write(cards_dir / "t1_初稿.md", "# t1\n\n## 进度回写\n- 状态：✅已收口\n")
        rc1, out1 = run(line)
        check(
            rc1 == 0
            and "[A007] ⚠️" in out1
            and "t1 卡面 ✅／§4 未勾" in out1
            and "t1 卡面 ✅／索引 ⬜" in out1,
            f"lowercase card file t1_初稿.md must match uppercase T1 in §4 and index:\n{out1}",
        )

        # Fix §4 & index, then add colliding card file T1_补充.md -> must warn and name both t1_初稿.md and T1_补充.md!
        write(line / "AGENTS.md", base_agents)
        write(line / "文档" / "任务卡_README.md", "| 卡号 | 状态 |\n|---|---|\n| T1 | ✅ |\n")
        write(cards_dir / "T1_补充.md", "# T1 补充\n\n## 进度回写\n- 状态：✅已收口\n")
        rc2, out2 = run(line)
        check(
            rc2 == 0 and "[A007] ⚠️" in out2 and "卡号重复" in out2 and "t1_初稿.md" in out2 and "T1_补充.md" in out2,
            f"duplicate card ID across files must warn and name both files:\n{out2}",
        )


def test_042_v7_misplaced_review_in_cards_dir() -> None:
    """0.4.2 V7: files containing '复核' inside cards_dir are not checked as cards, and emit a misplaced-review hint."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        cards_dir = line / "文档" / "任务卡"
        write(
            cards_dir / "T1_初稿.md",
            "# T1 初稿\n\n## 进度回写\n- 状态：✅已收口\n\n## 📋 执行方派发提示词\n做\n\n## 📋 独立复核方派发提示词\n核\n",
        )
        # Put a review report (no prompts, no 进度回写) into 文档/任务卡/ by mistake
        write(cards_dir / "T1_复核_SWE2_2026-09-15.md", "# T1 复核\n\n## 会出错\n无\n\n## 建议\n无\n\nPASS\n")
        rc, out = run(line)
        check(
            rc == 0
            and "[A005] ✅" in out
            and "[A007] ✅" in out
            and "[A015] ⚠️" in out
            and "复核报告放错目录" in out
            and "T1_复核_SWE2_2026-09-15.md" in out,
            f"misplaced review in cards_dir must not fail A005/A007 and must warn on A015:\n{out}",
        )


def test_042_v8_multiple_decision_tables() -> None:
    """0.4.2 V8: multiple decision tables in AGENTS.md emit a warning AND both tables have replacement chains checked."""
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        two_tables_agents = (
            "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n"
            "> - **当前阶段**：初稿（2026-09-15）\n> - **下一步**：写方法\n> - **阻塞**：无\n\n"
            "## 3. 现在在哪\n- 2026-09-15：初稿完成\n\n"
            "## 3.5 决策登记表\n"
            "| ID | 状态 | 决策 | 取代了谁 | 被谁取代 |\n"
            "|---|---|---|---|---|\n"
            "| D-01 | ACTIVE | 初版口径 | -- | -- |\n\n"
            "## 3.5 补充决策登记表\n"
            "| ID | 状态 | 决策 | 取代了谁 | 被谁取代 |\n"
            "|---|---|---|---|---|\n"
            "| D-02 | SUPERSEDED | 二版口径 | -- | -- |\n\n"
            "## 4. 任务看板\n- [x] T1 初稿\n"
        )
        write(line / "AGENTS.md", two_tables_agents)
        rc, out = run(line)
        check(
            rc == 0
            and "[A013] ⚠️" in out
            and "2 张决策登记表" in out
            and "D-02 为 SUPERSEDED 但未填" in out,
            f"V8 must warn on 2 decision tables AND check replacement chain in 2nd table:\n{out}",
        )


def test_042_v9_a002_numeric_and_tuples() -> None:
    """0.4.2 V9: A002 detects numeric collections & tuples, and docstring states list/set/tuple literal scope."""
    doc_txt = (checker_mod.__doc__ or "") + "\n" + (getattr(checker_mod, "check_script_constants_a002", None).__doc__ or "")
    check(
        "只看列表、集合、元组字面量" in doc_txt,
        f"A002 docstring must explicitly state '只看列表、集合、元组字面量', got:\n{doc_txt}",
    )
    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        write(line / "scripts" / "s1.py", "YEARS = [2019, 2020]\nZONES = ('I', 'II')\n")
        write(line / "scripts" / "s2.py", "YEARS = [2019, 2020, 2021]\nZONES = ('I', 'II', 'III')\n")
        rc, out = run(line)
        check(
            rc == 0 and "[A002] ⚠️" in out and "YEARS:" in out and "ZONES:" in out,
            f"V9 A002 must detect drift in numeric list YEARS and tuple ZONES:\n{out}",
        )
        # Matching numeric set/tuple/list with identical elements must PASS A002
        write(line / "scripts" / "s2.py", "YEARS = (2020, 2019)\nZONES = ['II', 'I']\n")
        rc2, out2 = run(line)
        check(rc2 == 0 and "[A002] ✅" in out2, f"identical numeric/tuple sets must pass A002:\n{out2}")


def test_042_conv1_three_files_and_missing_lib() -> None:
    """0.4.2 Conv1: SKILL.md, scripts_README.md, README.md, README.en.md list 3 scripts; missing handoff_lib.py exits 2."""
    for rel in ("SKILL.md", "assets/scripts_README.md", "README.md", "README.en.md"):
        txt = (REPO / rel).read_text(encoding="utf-8")
        for fn in ("handoff_lib.py", "check_handoff.py", "archive_status.py"):
            check(fn in txt, f"{rel} must list {fn}")

    with tempfile.TemporaryDirectory() as temp:
        tdir = Path(temp) / "scripts"
        tdir.mkdir(parents=True)
        for src in (CHECKER, ARCHIVER):
            dst = tdir / src.name
            dst.write_bytes(src.read_bytes())
            res = subprocess.run(
                [sys.executable, "-B", str(dst), str(Path(temp))],
                capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_env(),
            )
            combined = (res.stdout + res.stderr).strip()
            check(
                res.returncode == 2 and "请把 handoff_lib.py 一起复制到同一目录" in combined,
                f"{src.name} without handoff_lib.py must exit 2 with copy hint, got rc={res.returncode}: {combined}",
            )


def test_042_gate3_syntax_variants() -> None:
    """0.4.2 Gate 3: table-driven syntax variants (>=12 per entrypoint across all 6 entrypoints + all review bug examples)."""
    from datetime import date as d

    # 1. 取卡面状态 (hl_mod.parse_card_state) — 15 variants
    card_state_cases = [
        ("c01_h2_standard", "# T1\n## 进度回写\n- 状态：⏳执行中\n", "⏳"),
        ("c02_h3_progress_v5", "# T1\n### 进度回写（只改本节）\n- 状态：🟡待复核\n", "🟡"),
        ("c03_h4_ignored", "# T1\n#### 进度回写\n- 状态：✅已收口\n", None),
        ("c04_fenced_bt_dir1_rev0_bug2", "# T1\n## 进度回写\n```markdown\n- 状态：✅已收口\n```\n- 状态：⬜可派\n", "⬜"),
        ("c05_fenced_tilde_dir2_rev0_bug2", "# T1\n## 进度回写\n~~~\n- 状态：⬜可派\n~~~\n- 状态：✅已收口\n", "✅"),
        ("c06_indented_code_rev1_bug1", "# T1\n## 进度回写\n示例写法：\n\n    - 状态：✅已收口\n\n- 状态：⬜可派\n", "⬜"),
        ("c07_single_and_multi_comments_rev1_bug1", "# T1\n## 进度回写\n<!-- - 状态：✅ -->\n<!--\n- 状态：✅已收口\n-->\n- 状态：🔵待收口\n", "🔵"),
        ("c08_inline_code_comment_rev2_adv1", "# T1\n## 进度回写\n说明：勿写裸 `<!--` 标记\n- 状态：⬜可派\n", "⬜"),
        ("c09_empty_comments_rev2_adv1", "# T1\n## 进度回写\n<!-->\n<!--->\n- 状态：🟡待复核\n", "🟡"),
        ("c10_unclosed_comment_and_fence", "# T1\n## 进度回写\n手滑 <!-- 未闭合\n```python\nx = 1\n- 状态：✅已收口\n", "✅"),
        ("c11_star_halfwidth_colon_spaces_rev0_adv1", "# T1\n## 进度回写\n* 状态 : ⏳执行中   \n", "⏳"),
        ("c12_plus_bold_fullwidth_colon", "# T1\n## 进度回写\n+ **状态** ： ⛔退回\n", "⛔"),
        ("c13_bare_no_bullet_rev0_adv1", "# T1\n## 进度回写\n状态：🗄️作废\n", "🗄"),
        ("c14_bom_crlf_trailing_ws", "\ufeff# T1\r\n## 进度回写   \r\n- 状态：✅已收口   \r\n", "✅"),
        ("c15_blockquote_and_sublist_ignored", "# T1\n## 进度回写\n> - 状态：✅已收口\n  - 状态：✅已收口\n- 状态：⬜可派\n", "⬜"),
    ]
    check(len(card_state_cases) >= 12, "Entrypoint 1 must have >= 12 variants")
    for name, md, expected in card_state_cases:
        got = hl_mod.parse_card_state(md)
        check(got == expected, f"[Gate3:parse_card_state:{name}] expected {expected!r}, got {got!r}")

    # 2. 分交接段 (hl_mod.handoff_blocks + hl_mod.handoffs_latest_date) — 14 variants
    ref_today = d(2026, 11, 11)
    handoff_cases = [
        ("h01_mixed_h2_then_h3_rev0_bug1", "## Handoff（2026-11-05）\n旧\n\n### 交接（2026-11-11）\n新\n", 2, d(2026, 11, 11)),
        ("h02_mixed_h3_then_h2", "### 交接（2026-11-01）\n一\n\n## Handoff（2026-11-09）\n二\n", 2, d(2026, 11, 9)),
        ("h03_h4_excluded_rev1_adv2", "#### Handoff（2026-11-11）\n正文\n", 0, None),
        ("h04_slash_dot_cn_dates_rev0_bug3", "## 交接（2026/11/08）\nA\n## 交接（2026.11.09）\nB\n## 交接（2026年11月11日）\nC\n", 3, d(2026, 11, 11)),
        ("h05_fenced_bt_and_tilde_fake", "## Handoff（2026-11-05）\n```md\n## Handoff（2026-11-11）\n```\n~~~\n### 交接（2026-11-10）\n~~~\n", 1, d(2026, 11, 5)),
        ("h06_indented_code_fake", "## Handoff（2026-11-05）\n示例：\n\n    ## Handoff（2026-11-11）\n", 1, d(2026, 11, 5)),
        ("h07_commented_out_handoff_rev2_adv3", "<!-- ## Handoff（2020-01-01） -->\n<!--\n## Handoff（2026-11-11）\n-->\n## Handoff（2026-11-08）\n真\n", 1, d(2026, 11, 8)),
        ("h08_unclosed_comment_and_fence", "前言 <!-- 未闭合\n```\n## Handoff（2026-11-10）\n真\n", 1, d(2026, 11, 10)),
        ("h09_inline_code_dates_and_comment", "## Handoff `<!-- 2026-12-01`（2026-11-09）\n正文 `2026-11-11`\n", 1, d(2026, 11, 9)),
        ("h10_jiaohui_shuoming_excluded_rev0_adv7", "## 交回说明\nA\n## 交回（2026-11-05）\nB\n## T13c 交回（2026-11-10）\nC\n", 1, d(2026, 11, 10)),
        ("h11_inner_4sec_subheadings", "## Handoff: 2026-11-10\n### 改了什么\nA\n### 怎么验证的\nB\n### 没做什么\nC\n### 不确定处\nD\n", 1, d(2026, 11, 10)),
        ("h12_colons_bullets_trailing_ws", "## 交接 : 2026-11-07   \n* 改了什么：A\n+ 怎么验证的: B\n- 没做什么：C\n- 不确定处: D\n", 1, d(2026, 11, 7)),
        ("h13_bom_crlf_trailing_note", "\ufeff# STATUS\r\n\r\n## Handoff（2026-11-09）\r\n正文\r\n\r\n> ⚠️ 提示\r\n", 1, d(2026, 11, 9)),
        ("h14_table_with_blank_line_inside_seg", "## 2026-11-06 收工\n| 项 | 值 |\n|---|---|\n| A | 1 |\n\n| B | 2 |\n", 1, d(2026, 11, 6)),
    ]
    check(len(handoff_cases) >= 12, "Entrypoint 2 must have >= 12 variants")
    for name, md, exp_cnt, exp_dt in handoff_cases:
        blks = hl_mod.handoff_blocks(md)
        _, arch_blks, _ = hl_mod.parse_status(md)
        got_dt = hl_mod.handoffs_latest_date(blks, ref_today)
        check(
            len(blks) == exp_cnt and len(arch_blks) == exp_cnt and got_dt == exp_dt,
            f"[Gate3:handoff:{name}] expected ({exp_cnt}, {exp_dt}), got ({len(blks)}/{len(arch_blks)}, {got_dt})",
        )

    # 3. 取 §3 日期 (hl_mod.extract_sec3_info) — 14 variants
    sec3_cases = [
        ("s01_template_example_rev0_bug4", "## 3. 现在在哪\n- 【待填：例 2026-06-15 完成底座】\n", None, True),
        ("s02_bare_example_rev2_adv2", "## 3. 现在在哪\n- 例 T3 进行中（2026-06-15）\n- 2026-11-07：底座完成\n", d(2026, 11, 7), False),
        ("s03_heading_date_rev1_bug2", "## 3. 现在在哪（截至 2026-11-10）\n- 2026-10-01：旧条\n", d(2026, 11, 10), False),
        ("s04_inline_placeholder_rev1_bug3a", "## 3. 现在在哪\n- 2026-10-01：旧\n- 🔶 交付（2026-11-10）：报告已发【待填：页数】\n", d(2026, 11, 10), False),
        ("s05_literal_ymd_rev1_bug3b", "## 3. 现在在哪\n- 2026-10-01：旧\n- ✅ 2026-11-10：日期写 YYYY-MM-DD 格式\n", d(2026, 11, 10), False),
        ("s06_fenced_bt_and_tilde", "## 3. 现在在哪\n- 2026-11-05：真\n```\n2026-11-11\n```\n~~~\n2026-11-10\n~~~\n", d(2026, 11, 5), False),
        ("s07_indented_code_vs_continuation", "## 3. 现在在哪\n- 2026-11-05：真\n  续行 2026-11-08\n\n    2026-11-11 缩进代码\n", d(2026, 11, 8), False),
        ("s08_single_and_multi_comments", "## 3. 现在在哪\n<!-- 2026-11-11 -->\n<!--\n2026-11-10\n-->\n- 2026-11-06：真\n", d(2026, 11, 6), False),
        ("s09_unclosed_comment_and_fence", "## 3. 现在在哪\n<!-- 未闭合\n```\n- 2026-11-09：真\n", d(2026, 11, 9), False),
        ("s10_inline_code_date_ignored", "## 3. 现在在哪\n- 2026-11-06：跑 `--today 2026-11-11` 通过\n", d(2026, 11, 6), False),
        ("s11_h3_h4_subheadings_kept", "## 3. 现在在哪\n### 阶段一\n* 2026-11-04 : A\n#### 细节\n+ 2026-11-09：B\n## 4. 任务看板\n- 2026-11-11\n", d(2026, 11, 9), False),
        ("s12_slash_dot_cn_bom_crlf", "\ufeff## 3. 现在在哪   \r\n* 2026/11/03: A   \r\n+ 2026.11.06：B\r\n- 2026年11月10日：C\r\n", d(2026, 11, 10), False),
        ("s13_archive_quote_excluded", "## 3. 现在在哪\n> 更早快照见 `文档/AGENTS_归档_至2026-11-11.md`。\n- 2026-11-07：真\n", d(2026, 11, 7), False),
        ("s14_english_title_table_blank_line", "## Where We Are Now\n| 阶段 | 日期 |\n|---|---|\n| T1 | 2026-11-05 |\n\n| T2 | 2026-11-08 |\n", d(2026, 11, 8), False),
    ]
    check(len(sec3_cases) >= 12, "Entrypoint 3 must have >= 12 variants")
    for name, md, exp_dt, exp_ph in sec3_cases:
        info = hl_mod.extract_sec3_info(md, ref_today)
        check(
            info.latest_date == exp_dt and info.is_placeholder == exp_ph,
            f"[Gate3:sec3:{name}] expected ({exp_dt}, {exp_ph}), got ({info.latest_date}, {info.is_placeholder})",
        )

    # 4. 取 TL;DR (hl_mod.extract_tldr_info) — 14 variants
    tldr_cases = [
        ("t01_blockquote_standard", "> ⚡ **TL;DR**\n> - **当前阶段**：T1–T9 ✅（2026-11-07）\n> - **下一步**：T10\n\n## 1. 北极星\n", True, True, d(2026, 11, 7)),
        ("t02_bare_example_rev2_adv2", "> ⚡ **TL;DR**\n> - **当前阶段**：例 T3 进行中（2026-06-15）\n> - **下一步**：待定\n", True, False, None),
        ("t03_inline_placeholder_rev1_bug3", "> ⚡ **TL;DR**\n> - **当前阶段**：2026-11-10 已交稿【待填：页码】\n", True, False, d(2026, 11, 10)),
        ("t04_prose_eg_todo_ok", "> ⚡ **TL;DR**\n> - **当前阶段**：清 TODO（例：标准边界，2026-11-09，e.g. check）\n", True, True, d(2026, 11, 9)),
        ("t05_h3_tldr_heading", "### ⚡ TL;DR\n* 当前阶段 : 完成（2026/11/08）\n+ 下一步：收口\n## 1. 北极星\n2026-11-11\n", True, True, d(2026, 11, 8)),
        ("t06_h2_with_h4_sub_colons_bullets", "## TL;DR\n#### 摘要\n- 当前阶段: 2026.11.06\n* 下一步：2026年11月09日\n+ 阻塞: 无\n---\n", True, True, d(2026, 11, 9)),
        ("t07_fenced_bt_and_tilde_ignored", "```md\n> ⚡ **TL;DR**\n> - 2026-11-11\n```\n> ⚡ **TL;DR**\n> - **当前阶段**：真（2026-11-06）\n~~~\n2026-11-10\n~~~\n---\n", True, True, d(2026, 11, 6)),
        ("t08_indented_code_ignored", "    > ⚡ **TL;DR**\n    > - 2026-11-11\n\n> ⚡ **TL;DR**\n> - **当前阶段**：真（2026-11-05）\n", True, True, d(2026, 11, 5)),
        ("t09_single_and_multi_comments", "<!-- > ⚡ **TL;DR** 2026-11-11 -->\n> ⚡ **TL;DR**\n<!--\n2026-11-10\n-->\n> - **当前阶段**：真（2026-11-07）\n", True, True, d(2026, 11, 7)),
        ("t10_unclosed_comment_and_fence", "<!-- 未闭合\n```\n> ⚡ **TL;DR**\n> - **当前阶段**：真（2026-11-08）\n", True, True, d(2026, 11, 8)),
        ("t11_inline_code_ignored", "> ⚡ **TL;DR**\n> - **当前阶段**：修 `<!-- 2026-11-11`（2026-11-09）\n", True, True, d(2026, 11, 9)),
        ("t12_bom_crlf_trailing_ws", "\ufeff> ⚡ **TL;DR**   \r\n> - **当前阶段**：完成（2026-11-08）   \r\n\r\n## 1. 北极星\r\n", True, True, d(2026, 11, 8)),
        ("t13_table_with_blank_line", "## TL;DR\n| 项 | 值 |\n|---|---|\n| 阶段 | 2026-11-04 |\n\n| 更新 | 2026-11-09 |\n## 1. 北极星\n", True, True, d(2026, 11, 9)),
        ("t14_missing_tldr", "# AGENTS\n\n## 1. 北极星\n2026-11-10\n", False, False, None),
    ]
    check(len(tldr_cases) >= 12, "Entrypoint 4 must have >= 12 variants")
    for name, md, exp_found, exp_filled, exp_dt in tldr_cases:
        ti = hl_mod.extract_tldr_info(md, ref_today)
        got_filled = ti.exists and not ti.unfilled
        check(
            ti.exists == exp_found and got_filled == exp_filled and ti.latest_date == exp_dt,
            f"[Gate3:tldr:{name}] expected ({exp_found}, {exp_filled}, {exp_dt}), got ({ti.exists}, {got_filled}, {ti.latest_date})",
        )

    # 5. 读决策表 (hl_mod.parse_decision_tables) — 14 variants
    decision_cases = [
        ("d01_h2_standard", "## 3.5 决策登记表\n| ID | 状态 | 决策 | 取代了谁 | 被谁取代 |\n|---|---|---|---|---|\n| D-01 | ACTIVE | 口径 | -- | -- |\n", 1, ["D-1"]),
        ("d02_h3_title", "### 决策登记表（权威）\n| ID | 状态 | 决策 |\n|---|---|---|\n| D-02 | ACTIVE | 口径 |\n", 1, ["D-2"]),
        ("d03_h4_inside_not_stopping", "## 3.5 决策登记表\n#### 子表\n| ID | 状态 | 决策 |\n|---|---|---|\n| D-03 | ACTIVE | 口径 |\n", 1, ["D-3"]),
        ("d04_two_sections_rev0_adv6_v8", "## 3.5 决策登记表\n| ID | 状态 |\n|---|---|\n| D-01 | ACTIVE |\n\n## 3.5 补充表\n| ID | 状态 |\n|---|---|\n| D-02 | ACTIVE |\n", 2, ["D-1", "D-2"]),
        ("d05_two_tables_same_sec_v8", "## 3.5 决策登记表\n| ID | 状态 |\n|---|---|\n| D-01 | ACTIVE |\n\n说明段落\n\n| ID | 状态 |\n|---|---|\n| D-02 | ACTIVE |\n", 2, ["D-1", "D-2"]),
        ("d06_blank_lines_in_table", "## 3.5 决策登记表\n| ID | 状态 |\n\n|---|---|\n| D-01 | ACTIVE |\n\n| D-02 | SUPERSEDED |\n", 1, ["D-1", "D-2"]),
        ("d07_id_norm_rev0_adv3", "## 3.5 决策登记表\n| ID | 状态 | 取代了谁 | 被谁取代 |\n|---|---|---|---|\n| d-038 | SUPERSEDED | -- | D51 |\n| D-51 | ACTIVE | D38 | -- |\n", 1, ["D-38", "D-51"]),
        ("d08_inline_code_and_escaped_pipes", "## 3.5 决策登记表\n| ID | 状态 | 决策 | 取代了谁 | 被谁取代 |\n|---|---|---|---|---|\n| D-09 | ACTIVE | 含 `x|y` 与 a\\|b | -- | -- |\n", 1, ["D-9"]),
        ("d09_fenced_bt_and_tilde_ignored", "## 3.5 决策登记表\n```\n| ID | 状态 |\n|---|---|\n| D-99 | ACTIVE |\n```\n~~~\n| ID | 状态 |\n|---|---|\n| D-98 | ACTIVE |\n~~~\n| ID | 状态 |\n|---|---|\n| D-01 | ACTIVE |\n", 1, ["D-1"]),
        ("d10_indented_table_supported", "## 3.5 决策登记表\n    | ID | 状态 |\n    |---|---|\n    | D-04 | ACTIVE |\n", 1, ["D-4"]),
        ("d11_single_and_multi_comments", "## 3.5 决策登记表\n<!-- | D-99 | ACTIVE | -->\n<!--\n| ID | 状态 |\n|---|---|\n| D-98 | ACTIVE |\n-->\n| ID | 状态 |\n|---|---|\n| D-05 | ACTIVE <!-- 注释 --> |\n", 1, ["D-5"]),
        ("d12_unclosed_comment_and_fence", "## 3.5 决策登记表\n备注 <!-- 未闭合\n```\n| ID | 状态 |\n|---|---|\n| D-06 | ACTIVE |\n", 1, ["D-6"]),
        ("d13_cn_headers_colons_bullets", "## 3.5 决策登记表\n| 编号 | 状态 | 说明: 含 -/*/+ | 取代了谁 | 被谁取代 |\n|---|---|---|---|---|\n| D-07 | ACTIVE | a:b：c   | D-01、D-02 | — |\n", 1, ["D-7"]),
        ("d14_bom_crlf_placeholder_skipped", "\ufeff## 3.5 决策登记表   \r\n| ID | 状态 |\r\n|---|---|\r\n| 【待填：D-01】 | ACTIVE |\r\n| D-08 | ACTIVE |   \r\n", 1, ["D-8"]),
    ]
    check(len(decision_cases) >= 12, "Entrypoint 5 must have >= 12 variants")
    for name, md, exp_tcnt, exp_ids in decision_cases:
        tbls = hl_mod.parse_decision_tables(md, all_sections=True)
        got_ids = [r.norm_id for t in tbls for r in t.rows]
        check(
            len(tbls) == exp_tcnt and got_ids == exp_ids,
            f"[Gate3:decision:{name}] expected ({exp_tcnt}, {exp_ids}), got ({len(tbls)}, {got_ids})",
        )

    # 6. 读看板行 (hl_mod.parse_board_items + checker_mod.sec4_card_drifts) — 14 variants
    board_cases = [
        ("b01_dash_star_plus_bullets", "## 4. 任务看板\n- [x] **T1**\n* [ ] **T2**\n+ [X] **T3**\n", [True, False, True], {"T1": ("✅", "T1.md"), "T2": ("⬜", "T2.md"), "T3": ("🗄", "T3.md")}, []),
        ("b02_multi_cards_inline_emoji", "## 4. 任务看板\n- [ ] **T10g**✅、**T10b**⬜　- [x] **T11**\n", [False], {"T10g": ("✅", "T10g.md"), "T10b": ("⬜", "T10b.md"), "T11": ("✅", "T11.md")}, []),
        ("b03_case_insensitive_slash_rev0_adv2_v6", "## 4. 任务看板\n- [ ] **T12a/b**✅\n- [ ] **T1 初稿**\n", [False, False], {"t12a": ("✅", "t12a.md"), "T12B": ("✅", "T12B.md"), "t1": ("✅", "t1.md")}, ["t1 卡面 ✅／§4 未勾"]),
        ("b04_parens_dependency_masked", "## 4. 任务看板\n- [ ] **T11 二期**（依赖 T10，由 T12g 接续）\n", [False], {"T10": ("✅", "T10.md"), "T12g": ("✅", "T12g.md"), "T11": ("⬜", "T11.md")}, []),
        ("b05_template_placeholders", "## 4. 任务看板\n- [ ] **T1 【待填】**\n- [ ] Tx 示例：任务\n- [x] **T2 真任务**\n", [False, False, True], {"T2": ("✅", "T2.md")}, []),
        ("b06_h3_h4_kept_stops_at_h2", "## 4. 任务看板\n### 一期\n- [x] **T1**\n#### 细节\n- [ ] **T2**\n## 5. 铁律\n- [x] **T99**\n", [True, False], {"T1": ("✅", "T1.md"), "T2": ("⏳", "T2.md"), "T99": ("⬜", "T99.md")}, []),
        ("b07_fenced_bt_and_tilde_ignored", "## 4. 任务看板\n```\n- [x] **T99**\n```\n~~~\n- [ ] **T98**\n~~~\n- [x] **T1**\n", [True], {"T99": ("⬜", "T99.md"), "T1": ("✅", "T1.md")}, []),
        ("b08_indented_code_and_sublist_ignored", "## 4. 任务看板\n- [x] **T1**\n    - [ ] **T99 子项**\n\n    - [x] **T98 缩进代码**\n", [True], {"T1": ("✅", "T1.md"), "T99": ("✅", "T99.md"), "T98": ("⬜", "T98.md")}, []),
        ("b09_single_and_multi_comments", "## 4. 任务看板\n<!-- - [x] **T99** -->\n<!--\n- [x] **T98**\n-->\n- [x] **T1** <!-- 备注 -->\n", [True], {"T99": ("⬜", "T99.md"), "T1": ("✅", "T1.md")}, []),
        ("b10_unclosed_comment_and_fence", "## 4. 任务看板\n<!-- 未闭合\n```\n- [x] **T1**\n", [True], {"T1": ("✅", "T1.md")}, []),
        ("b11_inline_code_card_ignored", "## 4. 任务看板\n- [x] **T1** —— 参看 `T2` 脚本\n", [True], {"T1": ("✅", "T1.md"), "T2": ("⬜", "T2.md")}, []),
        ("b12_colons_trailing_ws", "## 4. 任务看板\n- [x] **T1**：初稿   \n* [ ] **T2**: 方法   \n", [True, False], {"T1": ("✅", "T1.md"), "T2": ("⬜", "T2.md")}, []),
        ("b13_bom_crlf_continuation", "\ufeff## 4. 任务看板\r\n- [x] **T1**   \r\n  续行说明\r\n", [True], {"T1": ("✅", "T1.md")}, []),
        ("b14_table_with_blank_line_alongside", "## 4. 任务看板\n| 批 | 说明 |\n|---|---|\n| 1 | A |\n\n| 2 | B |\n\n- [x] **T1**\n", [True], {"T1": ("✅", "T1.md")}, []),
    ]
    check(len(board_cases) >= 12, "Entrypoint 6 must have >= 12 variants")
    for name, md, exp_checked, st_map, exp_drifts in board_cases:
        items = hl_mod.parse_board_items(md)
        got_checked = [it.checked for it in items]
        got_drifts = checker_mod.sec4_card_drifts(items, st_map)
        check(
            got_checked == exp_checked and got_drifts == exp_drifts,
            f"[Gate3:board:{name}] expected ({exp_checked}, {exp_drifts}), got ({got_checked}, {got_drifts})",
        )


def test_042_gate4_fuzz_mutations() -> None:
    """0.4.2 Gate 4: fixed seed, 200 random mutations x 7 files (AGENTS.md, STATUS.md, 5 cards) -> no crash, <=5s, line conservation."""
    import contextlib
    import random
    import time
    from io import StringIO

    rng = random.Random(20261111)
    tokens = ["<!--", "-->", "<!-->", "```", "~~~", "## 乱改小节", "### 交接（2026-09-15）", "- 状态：⬜可派", "`<!--`"]

    def _mutate(text: str) -> str:
        ls = text.splitlines()
        for _ in range(rng.randint(1, 5)):
            op = rng.choice(("delete", "swap", "insert", "append"))
            if op == "delete" and ls:
                del ls[rng.randrange(len(ls))]
            elif op == "swap" and len(ls) >= 2:
                i, j = rng.sample(range(len(ls)), 2)
                ls[i], ls[j] = ls[j], ls[i]
            elif op == "insert":
                ls.insert(rng.randint(0, len(ls)), rng.choice(tokens))
            elif op == "append" and ls:
                idx = rng.randrange(len(ls))
                ls[idx] = ls[idx] + " " + rng.choice(tokens)
        return "\n".join(ls) + "\n"

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        # Enrich AGENTS.md (7 §3 entries) and STATUS.md (12 handoff blocks) + 5 cards so archiver actively archives!
        sec3_items = "\n".join(f"- 2026-09-{d_i:02d}：阶段快照 {d_i}" for d_i in range(8, 16))
        write(
            line / "AGENTS.md",
            "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n"
            "> - **当前阶段**：T5 进行中（2026-09-15）\n> - **下一步**：推进 T5\n> - **阻塞**：无\n\n"
            f"## 3. 现在在哪\n{sec3_items}\n- `→ 本轮增量见 STATUS.md`\n\n"
            "## 3.5 决策登记表\n| ID | 状态 | 决策 | 取代了谁 | 被谁取代 |\n|---|---|---|---|---|\n"
            "| D-01 | SUPERSEDED | 旧 | -- | D-02 |\n| D-02 | ACTIVE | 新 | D-01 | -- |\n\n"
            "## 4. 任务看板\n- [x] **T1**\n- [x] **T2**\n- [ ] **T3**\n- [ ] **T4**\n- [ ] **T5**\n",
        )
        segs = [
            f"## Handoff（2026-09-{d_i:02d}，T{(d_i % 5) + 1}）\n"
            "- **谁做的**：执行方\n- **改了什么**：改动。\n- **怎么验证的**：自检。\n- **没做什么**：无。\n- **不确定处**：无。"
            for d_i in range(4, 16)
        ]
        write(line / "STATUS.md", "# STATUS\n\n> 更早的交接段已归档到 `文档/STATUS_归档_至2026-09-01.md`。\n\n" + "\n\n".join(segs) + "\n")
        cards_dir = line / "文档" / "任务卡"
        card_rels: list[Path] = []
        for idx_c, st_c in enumerate(("✅已收口", "✅已收口", "⬜可派", "⏳执行中", "🟡待复核"), 1):
            rel = Path("文档") / "任务卡" / f"T{idx_c}_卡{idx_c}.md"
            card_rels.append(rel)
            write(
                line / rel,
                f"# T{idx_c}\n\n## 进度回写\n- 状态：{st_c}\n- 执行方：工具【A】/ 模型【B】/ 家族【C】\n\n"
                "## 📋 执行方派发提示词\n```text\n做\n```\n\n## 📋 独立复核方派发提示词\n```text\n核\n```\n",
            )

        targets = [Path("AGENTS.md"), Path("STATUS.md"), *card_rels]
        orig = {rel: (line / rel).read_text(encoding="utf-8") for rel in targets}

        for rel in targets:
            for it in range(200):
                for r2, txt2 in orig.items():
                    (line / r2).write_text(txt2, encoding="utf-8")
                for af in (line / "文档").glob("*_归档_*.md"):
                    af.unlink()

                (line / rel).write_text(_mutate(orig[rel]), encoding="utf-8")
                before_st = [ln for ln in (line / "STATUS.md").read_text(encoding="utf-8").splitlines() if ln.strip()]
                before_ag = [ln for ln in (line / "AGENTS.md").read_text(encoding="utf-8").splitlines() if ln.strip()]

                t0 = time.perf_counter()
                buf = StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    rc_c = checker_mod.main([str(line), "--scope", "line", "--today", TODAY])
                dt_c = time.perf_counter() - t0
                check(rc_c in (0, 1) and dt_c <= 5.0, f"Gate4 checker failed/slow on {rel}#{it}: rc={rc_c}, dt={dt_c:.2f}s")

                t1 = time.perf_counter()
                buf2 = StringIO()
                with contextlib.redirect_stdout(buf2), contextlib.redirect_stderr(buf2):
                    rc_a = archiver_mod.main([str(line), "--keep", "6", "--agents-keep", "4", "--today", TODAY])
                dt_a = time.perf_counter() - t1
                check(rc_a == 0 and dt_a <= 5.0, f"Gate4 archiver failed/slow on {rel}#{it}: rc={rc_a}, dt={dt_a:.2f}s")

                after_st = [ln.rstrip() for ln in (line / "STATUS.md").read_text(encoding="utf-8").splitlines()]
                for af in (line / "文档").glob("STATUS_归档_*.md"):
                    after_st.extend(ln.rstrip() for ln in af.read_text(encoding="utf-8").splitlines())
                after_st_set = set(after_st)
                lost_st = [
                    ln for ln in before_st
                    if ln.rstrip() not in after_st_set
                    and not (ln.lstrip().startswith(">") and "STATUS_归档_" in ln and any(a.startswith(ln.rstrip().rstrip("。")) for a in after_st))
                ]
                check(not lost_st, f"Gate4 STATUS lost lines on {rel}#{it}: {lost_st[:3]}")

                after_ag = [ln.rstrip() for ln in (line / "AGENTS.md").read_text(encoding="utf-8").splitlines()]
                for af in (line / "文档").glob("AGENTS_归档_*.md"):
                    after_ag.extend(ln.rstrip() for ln in af.read_text(encoding="utf-8").splitlines())
                after_ag_set = set(after_ag)
                lost_ag = [
                    ln for ln in before_ag
                    if ln.rstrip() not in after_ag_set
                    and not (ln.lstrip().startswith(">") and "AGENTS_归档_" in ln and any(a.startswith(ln.rstrip().rstrip("。")) for a in after_ag))
                ]
                check(not lost_ag, f"Gate4 AGENTS lost lines on {rel}#{it}: {lost_ag[:3]}")


def test_050_conv1_collab_rules() -> None:
    """0.5.0 Conv1: assets/协作规矩.md header/hash/6 sections, pointer in 任务卡_README.md, and A016 missing/version/tamper checks."""
    rules_fp = ASSETS_DIR / "协作规矩.md"
    check(rules_fp.is_file(), "assets/协作规矩.md must exist")
    raw_rules = rules_fp.read_bytes().decode("utf-8")
    first_ln, sep, _ = raw_rules.replace("\r\n", "\n").partition("\n")
    m = hl_mod.RULES_HEADER_RE.match(first_ln)
    check(bool(m and sep), f"assets/协作规矩.md line 1 must match fixed header format, got: {first_ln!r}")
    decl_ver, decl_sha = m.group(1), m.group(2).lower()
    check(decl_ver == "0.5.0", f"assets/协作规矩.md line 1 version must be 0.5.0, got: {decl_ver}")
    actual_sha = hl_mod.compute_rules_body_sha256(raw_rules)
    check(actual_sha == decl_sha, f"assets/协作规矩.md body sha256 mismatch: header={decl_sha}, actual={actual_sha}")

    doc = hl_mod.parse_markdown(raw_rules)
    h2_titles = [b.title for b in doc.blocks if b.kind == "heading" and b.level == 2]
    expected_h2 = list(hl_mod.RULES_REQUIRED_SECTIONS)
    check(h2_titles == expected_h2, f"assets/协作规矩.md level-2 headings must be exact {expected_h2}, got {h2_titles}")

    readme_txt = (ASSETS_DIR / "任务卡_README.md").read_text(encoding="utf-8")
    readme_rules_sec = readme_txt.split("## 卡面规矩", 1)[1].split("## 例行签核提示词", 1)[0].strip()
    non_empty_ptr = [ln for ln in readme_rules_sec.splitlines() if ln.strip() and not ln.startswith("（")]
    check(
        len(non_empty_ptr) <= 2 and "文档/协作规矩.md" in readme_rules_sec and "谁改卡面哪里" not in readme_rules_sec,
        f"assets/任务卡_README.md ## 卡面规矩 must retain only pointer to 文档/协作规矩.md, got:\n{readme_rules_sec}",
    )

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        # 1. Missing 协作规矩.md -> A016 advisory warn (rc == 0, 0 FAIL)
        rc_miss, out_miss = run(line)
        check(
            rc_miss == 0 and "[A016] ⚠️" in out_miss and "未找到 文档/协作规矩.md" in out_miss,
            f"missing 协作规矩.md must warn A016 without failing:\n{out_miss}",
        )

        # 2. Intact 协作规矩.md (both LF and CRLF) -> A016 passes
        for eol in ("\n", "\r\n"):
            write_bytes_eol(line / "文档" / "协作规矩.md", raw_rules, eol)
            rc_ok, out_ok = run(line)
            check(rc_ok == 0 and "[A016] ✅" in out_ok, f"intact 协作规矩.md ({eol!r}) must pass A016:\n{out_ok}")

        # 3. Version lower than script version (v0.4.0 with valid hash) -> A016 warns '版本低于脚本版本'
        old_ver_rules = hl_mod.stamp_rules_header(raw_rules, "0.4.0")
        write(line / "文档" / "协作规矩.md", old_ver_rules)
        rc_old, out_old = run(line)
        check(
            rc_old == 0 and "[A016] ⚠️" in out_old and "版本低于脚本版本" in out_old,
            f"older rules version must warn A016 '版本低于脚本版本':\n{out_old}",
        )

        # 4. Modifying 1 character in body -> A016 warns '被改过'
        tampered = raw_rules.replace("谁改卡面哪里", "谁改卡面何处", 1)
        write(line / "文档" / "协作规矩.md", tampered)
        rc_tamp, out_tamp = run(line)
        check(
            rc_tamp == 0 and "[A016] ⚠️" in out_tamp and "被改过" in out_tamp,
            f"1-char modification in 协作规矩.md body must warn A016 '被改过':\n{out_tamp}",
        )


def test_050_conv2_card_template_and_a017() -> None:
    """0.5.0 Convention 2: assets/任务卡_模板.md (<=6KB, 3-line header, <=8-line prompts) + A017 reviewer family check."""
    tpl_path = ASSETS_DIR / "任务卡_模板.md"
    check(tpl_path.is_file(), "assets/任务卡_模板.md must exist")
    check(not (ASSETS_DIR / "任务规划_模板.md").exists(), "old assets/任务规划_模板.md must be renamed away")

    readme_root = (REPO / "README.md").read_text(encoding="utf-8")
    check(
        "任务规划_模板.md" in readme_root and "任务卡_模板.md" in readme_root,
        "README.md must retain 1-line note explaining old name 任务规划_模板.md -> 任务卡_模板.md",
    )

    raw_bytes = tpl_path.read_bytes()
    check(len(raw_bytes) <= 6_000, f"assets/任务卡_模板.md must be <= 6000B, got {len(raw_bytes)}B")
    tpl_text = raw_bytes.decode("utf-8")
    top3 = tpl_text.splitlines()[:3]
    check(
        len(top3) == 3
        and top3[0].startswith("# T1 ")
        and top3[1].startswith("> 依赖：")
        and top3[2].startswith("> 产物类型：")
        and "成品给谁看：" in top3[2],
        f"assets/任务卡_模板.md must start with fixed 3-line header, got: {top3}",
    )

    prompts = list(re.finditer(r"````text\n(.*?)\n````", tpl_text, re.S))
    check(len(prompts) == 2, f"assets/任务卡_模板.md must have exact 2 prompt blocks, got {len(prompts)}")
    exec_lines = prompts[0].group(1).splitlines()
    rev_lines = prompts[1].group(1).splitlines()
    check(len(exec_lines) + 2 <= 8, f"executor prompt must be <= 8 lines (even with fences), got {len(exec_lines) + 2}")
    check(len(rev_lines) + 2 <= 8, f"reviewer prompt must be <= 8 lines (even with fences), got {len(rev_lines) + 2}")
    check(
        any(ln.startswith("先读：文档/协作规矩.md 的执行方须知") for ln in exec_lines),
        f"executor prompt 先读 must begin with 文档/协作规矩.md 的执行方须知:\n{prompts[0].group(1)}",
    )
    check(
        any(ln.startswith("先读：文档/协作规矩.md 的复核方须知") for ln in rev_lines),
        f"reviewer prompt 先读 must begin with 文档/协作规矩.md 的复核方须知:\n{prompts[1].group(1)}",
    )

    # Verify parse_card_header on filled vs template cards
    hdr_tpl = hl_mod.parse_card_header(tpl_text, "T1_示例")
    check(hdr_tpl.card_id == "T1" and hdr_tpl.artifact_type == "", f"unfilled template header should leave artifact_type empty: {hdr_tpl}")
    hdr_filled = hl_mod.parse_card_header(
        "# T8 OPGD归因\n> 依赖：T2、T7\n> 产物类型：头条数字　成品给谁看：对外\n\n## 进度回写\n- 状态：✅已收口\n",
        "T8_OPGD归因",
    )
    check(
        hdr_filled.card_id == "T8"
        and hdr_filled.task_name == "OPGD归因"
        and hdr_filled.depends == "T2、T7"
        and hdr_filled.artifact_type == "头条数字"
        and hdr_filled.audience == "对外",
        f"filled header parse mismatch: {hdr_filled}",
    )

    with tempfile.TemporaryDirectory() as temp:
        line = build(Path(temp))
        write(line / "文档" / "协作规矩.md", (ASSETS_DIR / "协作规矩.md").read_text(encoding="utf-8"))
        c1 = line / "文档" / "任务卡" / "T1_初稿.md"

        # 1. 分析建模 closed card with empty reviewer family -> A017 warn (rc==0, advisory only)
        write(
            c1,
            "# T1 初稿\n> 依赖：无\n> 产物类型：分析建模　成品给谁看：内部\n\n"
            "## 进度回写\n- 状态：✅已收口\n"
            "- 执行方：工具【Codex】/ 模型【GPT-6】/ 家族【OpenAI】\n"
            "- 复核方：工具【】/ 模型【】/ 家族【】\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A017] ⚠️" in out and "T1（分析建模）复核方家族为空" in out, f"missing reviewer family on 分析建模 must warn A017:\n{out}")

        # 2. 分析建模 closed card with UNKNOWN reviewer family -> A017 warn
        write(
            c1,
            "# T1 初稿\n> 依赖：无\n> 产物类型：分析建模　成品给谁看：内部\n\n"
            "## 进度回写\n- 状态：✅已收口\n"
            "- 执行方：工具【Codex】/ 模型【GPT-6】/ 家族【OpenAI】\n"
            "- 复核方：工具【Cursor】/ 模型【未知】/ 家族【UNKNOWN】\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A017] ⚠️" in out and "UNKNOWN" in out, f"UNKNOWN reviewer family must warn A017:\n{out}")

        # 3. 分析建模 closed card with same non-empty family -> A017 passes (cross-family only required for 头条数字)
        write(
            c1,
            "# T1 初稿\n> 依赖：无\n> 产物类型：分析建模　成品给谁看：内部\n\n"
            "## 进度回写\n- 状态：✅已收口\n"
            "- 执行方：工具【Codex】/ 模型【GPT-6】/ 家族【OpenAI】\n"
            "- 复核方：工具【Cursor】/ 模型【GPT-6-mini】/ 家族【OpenAI】\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A017] ✅" in out, f"分析建模 with non-empty reviewer family must pass A017:\n{out}")

        # 4. 头条数字 closed card with same family (case-insensitive) -> A017 warn
        write(
            c1,
            "# T1 初稿\n> 依赖：无\n> 产物类型：头条数字　成品给谁看：对外\n\n"
            "## 进度回写\n- 状态：✅已收口\n"
            "- 执行方：工具【Codex】/ 模型【GPT-6】/ 家族【OpenAI】\n"
            "- 复核方：工具【Cursor】/ 模型【o4】/ 家族【openai】\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A017] ⚠️" in out and "同家族" in out, f"头条数字 with same family must warn A017:\n{out}")

        # 5. 头条数字 closed card with cross-family reviewer -> A017 passes
        write(
            c1,
            "# T1 初稿\n> 依赖：无\n> 产物类型：头条数字　成品给谁看：对外\n\n"
            "## 进度回写\n- 状态：✅已收口\n"
            "- 执行方：工具【Codex】/ 模型【GPT-6】/ 家族【OpenAI】\n"
            "- 复核方：工具【Claude Code】/ 模型【GLM-5.3】/ 家族【智谱】\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A017] ✅" in out, f"头条数字 with cross-family reviewer must pass A017:\n{out}")

        # 6. Deprecated 🗄️ or active ⏳ 头条数字 card without reviewer -> A017 skips (passes)
        write(
            c1,
            "# T1 初稿\n> 依赖：无\n> 产物类型：头条数字　成品给谁看：对外\n\n"
            "## 进度回写\n- 状态：🗄️作废\n- 执行方：略\n- 复核方：\n",
        )
        rc, out = run(line)
        check(rc == 0 and "[A017] ✅" in out, f"deprecated 🗄️ card must not trigger A017:\n{out}")


def main(argv: list[str] | None = None) -> int:
    global _DUMP_DIR
    parser = argparse.ArgumentParser(description="Run multi-agent-project skill self-tests")
    parser.add_argument("--dump-dir", help="Optional directory to dump every temp-project checker/archiver output")
    args = parser.parse_args(argv)
    _DUMP_COUNTERS.clear()
    _DUMP_DIR = Path(args.dump_dir).expanduser().resolve() if args.dump_dir else None

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
    test_041_r1_mixed_heading_levels_and_archive()
    test_041_r2_card_state_ignores_fenced_blocks()
    test_041_r3_non_hyphen_handoff_dates_and_clear_h005_h006()
    test_041_r4_sec3_placeholder_dates_ignored()
    test_041_s1_relaxed_state_line_and_unparsed_warning()
    test_041_s3_decision_id_normalization()
    test_041_s7_handoff_heading_words_and_docs()
    test_041_s8_subprocess_utf8_no_gbk_error()
    test_041_s10_index_template_a011_recent_five()
    test_041_r2_s1_sec3_heading_date_counted()
    test_041_r2_s2_inline_placeholder_span_stripping()
    test_041_r2_s3_top_level_card_state_and_html_comments()
    test_041_r2_adv1_archive_nonempty_line_conservation()
    test_041_r2_adv2_7_h4_excluded_in_docs_and_a011()
    test_041_r2_adv3_changelog_notes_bare_jiaohui()

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

    test_042_conv3_role()
    test_042_conv4_config()
    test_042_conv5_archive_keep_active_cards()
    test_042_v1_comment_boundaries()
    test_042_v2_bare_placeholder_dates()
    test_042_v3_commented_handoff_headings()
    test_042_v4_h006_fallback_body_only()
    test_042_v5_h3_progress_section()
    test_042_v6_card_id_case_and_collision()
    test_042_v7_misplaced_review_in_cards_dir()
    test_042_v8_multiple_decision_tables()
    test_042_v9_a002_numeric_and_tuples()
    test_042_conv1_three_files_and_missing_lib()
    test_042_gate3_syntax_variants()
    test_042_gate4_fuzz_mutations()

    test_050_conv1_collab_rules()
    test_050_conv2_card_template_and_a017()

    check(not (ASSETS_DIR / "__pycache__").exists(), "assets/__pycache__ must not exist at end of test suite")
    print("All skill self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

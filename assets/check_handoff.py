#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_handoff.py — 收工交接自检脚本（multi-agent-project skill 配套）

用法：
    # 在项目根目录运行（推荐，脚本会以 cwd 为项目根）
    python scripts/check_handoff.py

    # 显式指定项目根
    python scripts/check_handoff.py /path/to/project

    # 从任何位置运行，自动用 cwd
    python check_handoff.py

检查项（每项 pass/fail，全部 pass 才算交接合格）：
  1. AGENTS.md 存在且非空
  2. AGENTS.md §3 "现在在哪" 有近 7 天内的日期戳（防止收工没更新）
  3. AGENTS.md TL;DR 块（顶部 ⚡ 标记）的"当前阶段"不是占位符
  4. STATUS.md 存在、非空、非模板（有真实 Handoff 日期，不是 YYYY-MM-DD）
  5. STATUS.md 的 Handoff 日期 >= AGENTS.md §3 最近日期（增量不能比累计旧）
  6. 勾选的薄指针文件至少存在一个且指向 AGENTS.md（CLAUDE.md / GEMINI.md / .cursorrules / copilot-instructions.md）
  7. §4 看板有至少一项已勾选（防止收工后看板全未开始）

退出码：0 = 全过，1 = 有失败项。
"""
import os
import re
import sys
from datetime import datetime, timedelta

# 项目根：命令行参数优先，否则用当前工作目录
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
TODAY = datetime.now()
RECENT = TODAY - timedelta(days=7)

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))


# ---------- 1. AGENTS.md 存在且非空 ----------
agents_path = os.path.join(ROOT, "AGENTS.md")
agents_text = ""
if os.path.exists(agents_path):
    with open(agents_path, encoding="utf-8") as f:
        agents_text = f.read()
check("AGENTS.md 存在且非空", len(agents_text.strip()) > 100,
      "文件缺失或过短" if len(agents_text.strip()) <= 100 else f"{len(agents_text)} chars")


# ---------- 2. §3 有近 7 天日期戳 ----------
# 只搜 §3 节内日期，避免被参考文献/来源.txt 等处的日期污染
sec3 = re.search(r"(?:^## 3\.|^## 现在在哪|^## Where We Are Now).*?(?=^## )", agents_text, re.MULTILINE | re.DOTALL)
if not sec3:
    sec3 = re.search(r"## 3\.", agents_text, re.MULTILINE)
if not sec3:
    sec3 = re.search(r"现在在哪|Where We Are Now", agents_text)

dates_in_agents = re.findall(r"20\d{2}-\d{2}-\d{2}", sec3.group(0) if sec3 else "")
recent_in_agents = False
latest_agents_date = None
if dates_in_agents:
    for d in dates_in_agents:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            if latest_agents_date is None or dt > latest_agents_date:
                latest_agents_date = dt
            if dt >= RECENT:
                recent_in_agents = True
        except ValueError:
            pass
check("§3 有近 7 天日期戳", recent_in_agents,
      f"最近日期 {latest_agents_date} 超过 7 天，可能收工没更新 AGENTS.md" if latest_agents_date and not recent_in_agents
      else (f"最近日期 {latest_agents_date}" if latest_agents_date else "AGENTS.md 里没找到任何日期"))


# ---------- 3. TL;DR 块不是占位符 ----------
# 匹配中英文两种 TL;DR 写法
tldr_section = re.search(r"⚡.*?(?:当前阶段|Current stage).*?(?=✅|---)", agents_text, re.DOTALL)
tldr_ok = False
if tldr_section:
    blob = tldr_section.group(0)
    # 占位符判定：含【待填 或 TODO 或 例
    tldr_ok = "【待填" not in blob and "TODO" not in blob and "例" not in blob and "e.g." not in blob.lower()
check("AGENTS.md TL;DR 块已填（非占位符）", tldr_ok,
      "TL;DR 块还含【待填/TODO，收工时应更新当前阶段" if not tldr_ok else "已填")


# ---------- 4. STATUS.md 存在、非空、非模板 ----------
status_path = os.path.join(ROOT, "STATUS.md")
status_text = ""
status_real = False
if os.path.exists(status_path):
    with open(status_path, encoding="utf-8") as f:
        status_text = f.read()
    # 非模板判定：有真实日期（不是 YYYY-MM-DD）且非空
    has_real_date = bool(re.search(r"20\d{2}-\d{2}-\d{2}", status_text)) and "YYYY-MM-DD" not in status_text
    has_content = len(status_text.strip()) > 50
    status_real = has_real_date and has_content
check("STATUS.md 存在且非模板", status_real,
      "STATUS.md 缺失/为空/还是模板（YYYY-MM-DD 未替换）" if not status_real else "已填真实 handoff")


# ---------- 5. STATUS.md 日期 >= AGENTS.md §3 最近日期 ----------
dates_in_status = re.findall(r"20\d{2}-\d{2}-\d{2}", status_text)
latest_status_date = None
if dates_in_status:
    for d in dates_in_status:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            if latest_status_date is None or dt > latest_status_date:
                latest_status_date = dt
        except ValueError:
            pass
cross_ok = False
cross_detail = "STATUS.md 无有效日期"
if latest_status_date and latest_agents_date:
    cross_ok = latest_status_date >= latest_agents_date
    cross_detail = (f"STATUS {latest_status_date} >= AGENTS {latest_agents_date}" if cross_ok
                    else f"STATUS {latest_status_date} < AGENTS {latest_agents_date} —— 增量比累计旧，收工时 STATUS.md 没更新")
elif latest_status_date:
    cross_detail = f"STATUS {latest_status_date}（AGENTS 无日期可比较）"
check("STATUS.md 日期 >= AGENTS.md §3 日期", cross_ok, cross_detail)


# ---------- 6. 薄指针文件至少一个存在且指向 AGENTS.md ----------
thin_pointers = ["CLAUDE.md", "GEMINI.md", ".cursorrules",
                 ".github/copilot-instructions.md"]
found_pointer = False
pointer_detail = "没找到任何薄指针文件"
for p in thin_pointers:
    pp = os.path.join(ROOT, p)
    if os.path.exists(pp):
        with open(pp, encoding="utf-8") as f:
            pc = f.read()
        if "AGENTS.md" in pc:
            found_pointer = True
            pointer_detail = f"{p} 指向 AGENTS.md"
            break
        else:
            pointer_detail = f"{p} 存在但不指向 AGENTS.md"
check("薄指针文件存在且指向 AGENTS.md", found_pointer, pointer_detail)


# ---------- 7. §4 看板有已勾选项 ----------
sec4 = re.search(r"(?:^## 4\.|^## 下一步任务看板|^## Next Task Board|^## 任务看板).*?(?=^## )", agents_text, re.MULTILINE | re.DOTALL)
sec4_has_checked = False
sec4_detail = "未找到 §4 看板"
if sec4:
    sec4_text = sec4.group(0)
    checked = re.findall(r"\[x\]", sec4_text)
    unchecked = re.findall(r"\[\s?\]", sec4_text)
    sec4_has_checked = len(checked) >= 1
    sec4_detail = f"§4 看板：{len(checked)} 已完成 / {len(unchecked)} 未完成"
check("§4 看板有至少一项已勾选", sec4_has_checked, sec4_detail)


# ---------- 8. TL;DR 最新日期 >= §3 最近日期（TL;DR 和 §3 不矛盾） ----------
tldr_dates = re.findall(r"20\d{2}-\d{2}-\d{2}", tldr_section.group(0)) if tldr_section else []
tldr_latest = None
for d in tldr_dates:
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        if tldr_latest is None or dt > tldr_latest:
            tldr_latest = dt
    except ValueError:
        pass
tldr_vs_sec3_ok = True  # 无日期时不扣分，仅做可用时检查
tldr_vs_sec3_detail = "TL;DR 无日期或 §3 无日期，跳过"
if tldr_latest and latest_agents_date:
    tldr_vs_sec3_ok = tldr_latest >= latest_agents_date - timedelta(days=1)  # 允许 1 天偏差（TL;DR 可能忘记更新日期但在同一天）
    tldr_vs_sec3_detail = (f"TL;DR {tldr_latest} vs §3 {latest_agents_date} 一致" if tldr_vs_sec3_ok
                           else f"TL;DR {tldr_latest} < §3 {latest_agents_date} —— TL;DR 日期比 §3 旧，TL;DR 收工没更新")
check("TL;DR 和 §3 日期无矛盾", tldr_vs_sec3_ok, tldr_vs_sec3_detail)


# ---------- 汇总 ----------
print("=" * 60)
print("  收工交接自检（check_handoff.py）")
print("=" * 60)
all_pass = True
for name, ok, detail in results:
    status = PASS if ok else FAIL
    if not ok:
        all_pass = False
    print(f"  {status}  {name}")
    if detail:
        print(f"           {detail}")
print("=" * 60)
if all_pass:
    print("  🎉 全部通过，交接合格。")
    sys.exit(0)
else:
    fails = sum(1 for _, ok, _ in results if not ok)
    print(f"  ⚠️ {fails} 项未通过，收工前请补齐再交接。")
    sys.exit(1)

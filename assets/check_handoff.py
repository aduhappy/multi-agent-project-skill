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

    # 老项目搁置多日后重开，放宽“近 N 天”新鲜度阈值（默认 7）
    python scripts/check_handoff.py --days 30

检查项（每项 pass/fail，全部 pass 才算交接合格）：
  1. AGENTS.md 存在且非空
  2. AGENTS.md §3 "现在在哪" 有近 7 天内的日期戳（防止收工没更新）
  3. AGENTS.md TL;DR 块（顶部 ⚡ 标记）的"当前阶段"不是占位符
  4. STATUS.md 存在、非空、非模板（有真实 Handoff 日期，不是 YYYY-MM-DD）
  5. STATUS.md 的 Handoff 日期 >= AGENTS.md §3 最近日期（增量不能比累计旧）
  6. 勾选的薄指针文件至少存在一个且指向 AGENTS.md（CLAUDE.md / GEMINI.md / .cursorrules / copilot-instructions.md）
  7. §4 看板存在（存在即 PASS；“有任务却一项没勾”只作 advisory D，不硬 FAIL——全新项目首棒合法）
  8. TL;DR 最新日期 >= §3 最近日期（TL;DR 和 §3 不矛盾）

另有 4 项语义自检（advisory，只警告不判失败）：
  A. 决策登记表存在（具约束力的口径/排除清单别只埋在 STATUS 长叙事里）
  B. 多脚本口径漂移检测（同一大写常量集合在不同脚本里成员不一致——H28 类接力事故）
  C. 入口/交接文件体积失控（AGENTS.md 应 1–2 屏、STATUS.md 应只记增量）
  D. §4 看板有任务却一项没勾（刚搭骨架属正常，否则多半是收工忘了更新看板）

注：检查 3（TL;DR 占位符）只认 【待填/【TODO/TODO】/例：/e.g. 记号，不裸查“例”（避免误杀“比例/案例”）。
    检查 4/6 认 Windows GBK 控制台，脚本已强制 UTF-8 输出，可安全被管道/重定向捕获。
    --days N 覆盖“近 N 天”新鲜度阈值（默认 7）。

退出码：0 = 全过（含仅 advisory 警告），1 = 有失败项。
"""
import os
import re
import sys
from datetime import datetime, timedelta

# Windows 中文环境（GBK 控制台）下，emoji/中文会在管道或重定向时触发 UnicodeEncodeError。
# agent 跑脚本几乎必然是被捕获输出的场景，所以强制把 stdout/stderr 切到 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    enc = getattr(_stream, "encoding", None)
    if enc and enc.lower().replace("-", "") not in ("utf8",):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

# 参数解析：位置参数=项目根（默认 cwd）；--days N 覆盖“近 N 天”新鲜度阈值（默认 7）。
FRESH_DAYS = 7
_positional = []
_args = sys.argv[1:]
_i = 0
while _i < len(_args):
    a = _args[_i]
    if a in ("--days", "-d"):
        _i += 1
        if _i < len(_args):
            try:
                FRESH_DAYS = int(_args[_i])
            except ValueError:
                pass
    elif a.startswith("--days="):
        try:
            FRESH_DAYS = int(a.split("=", 1)[1])
        except ValueError:
            pass
    elif a in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    else:
        _positional.append(a)
    _i += 1

ROOT = os.path.abspath(_positional[0]) if _positional else os.getcwd()
TODAY = datetime.now()
RECENT = TODAY - timedelta(days=FRESH_DAYS)

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
    # fallback：抓 §3 标题到文末（末节没有后继 `## ` 时上面的 lookahead 会失配）
    sec3 = re.search(r"(?:^## 3\.|^## 现在在哪|^## Where We Are Now).*", agents_text, re.MULTILINE | re.DOTALL)

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
check(f"§3 有近 {FRESH_DAYS} 天日期戳", recent_in_agents,
      f"最近日期 {latest_agents_date:%Y-%m-%d} 超过 {FRESH_DAYS} 天，可能收工没更新 AGENTS.md（老项目重开可加 --days）" if latest_agents_date and not recent_in_agents
      else (f"最近日期 {latest_agents_date:%Y-%m-%d}" if latest_agents_date else "AGENTS.md 里没找到任何日期"))


# ---------- 3. TL;DR 块不是占位符 ----------
# 匹配中英文两种 TL;DR 写法
tldr_section = re.search(r"⚡.*?(?:当前阶段|Current stage).*?(?=✅|---)", agents_text, re.DOTALL)
tldr_ok = False
if tldr_section:
    blob = tldr_section.group(0)
    # 占位符判定：只认模板真正的占位记号。
    # 不能裸查“例”——“比例/案例/示例/惯例”都含“例”会误杀真实内容（已实测踩坑）。
    # 模板里的示例统一写成「例：」，所以用「例：」而非「例」来匹配。
    tldr_ok = ("【待填" not in blob and "【TODO" not in blob
               and "TODO】" not in blob and "例：" not in blob and "e.g." not in blob.lower())
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
# Cursor 现代格式：.cursor/rules/ 下任意 .mdc 都算薄指针（SKILL 推荐这种，别只认 legacy .cursorrules）
cursor_rules_dir = os.path.join(ROOT, ".cursor", "rules")
if os.path.isdir(cursor_rules_dir):
    for fn in sorted(os.listdir(cursor_rules_dir)):
        if fn.endswith(".mdc"):
            thin_pointers.append(os.path.join(".cursor", "rules", fn))
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


# ---------- 7. §4 看板存在（存在即 PASS；“有任务却一项没勾”只作 advisory）----------
# 不硬性要求“至少一项已勾选”——全新项目第一棒合法地全未勾选，硬 FAIL 是误报。
sec4 = re.search(r"(?:^## 4\.|^## 下一步任务看板|^## Next Task Board|^## 任务看板).*?(?=^## )", agents_text, re.MULTILINE | re.DOTALL)
if not sec4:
    sec4 = re.search(r"(?:^## 4\.|^## 下一步任务看板|^## Next Task Board|^## 任务看板).*", agents_text, re.MULTILINE | re.DOTALL)
sec4_present = bool(sec4)
sec4_checked = sec4_unchecked = 0
if sec4:
    sec4_text = sec4.group(0)
    sec4_checked = len(re.findall(r"\[x\]", sec4_text, re.IGNORECASE))
    sec4_unchecked = len(re.findall(r"\[\s?\]", sec4_text))
check("§4 看板存在", sec4_present,
      (f"§4 看板：{sec4_checked} 已完成 / {sec4_unchecked} 未完成" if sec4_present else "未找到 §4 看板"))


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


# ---------- 语义漂移自检（advisory，只警告不判失败）----------
# 这两项不计入 pass/fail，只提醒——针对"决策埋没"和"多脚本口径漂移"两类隐蔽接力事故。
warnings = []


def warn(name, detail=""):
    warnings.append((name, detail))


# A. 决策登记表是否存在（具约束力决策应收口到有界可查的一处，而非埋在 STATUS 长叙事）
registry_found = "决策登记表" in agents_text or "决策登记表" in status_text
registry_file = os.path.join(ROOT, "文档", "决策登记表.md")
if os.path.exists(registry_file):
    registry_found = True
if not registry_found:
    warn("缺决策登记表",
         "没找到『决策登记表』——具约束力的口径/排除清单/选定参数建议收口到一张有界可 grep 的表"
         "（见 references/advanced.md §1a），别只躺在 STATUS 长叙事里被下家漏读。")


# B. 多脚本口径漂移：同一大写常量集合在不同脚本里编码不一致（H28 类事故）
scripts_dir = os.path.join(ROOT, "scripts")
const_re = re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*=\s*(\{[^{}]*\}|\[[^\[\]]*\])", re.MULTILINE)
const_map = {}  # NAME -> { normalized_rhs -> set(files) }
if os.path.isdir(scripts_dir):
    for root_dir, _, files in os.walk(scripts_dir):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(root_dir, fn)
            try:
                with open(fp, encoding="utf-8") as f:
                    code = f.read()
            except Exception:
                continue
            for m in const_re.finditer(code):
                name, rhs = m.group(1), m.group(2)
                # 归一化：取出引号内的成员，排序后比对（忽略空白/顺序）
                members = tuple(sorted(re.findall(r"['\"]([^'\"]+)['\"]", rhs)))
                if not members:
                    continue
                const_map.setdefault(name, {}).setdefault(members, set()).add(
                    os.path.relpath(fp, ROOT))
    for name, variants in const_map.items():
        if len(variants) > 1:
            lines = "; ".join(
                f"{list(v)} = {{{', '.join(mem)}}}" for mem, v in variants.items())
            warn(f"口径漂移：常量 {name} 在多脚本里成员不一致",
                 f"{lines} —— 抽进唯一 config 让各脚本读取，并核对决策登记表（见 advanced.md §1c）。")


# C. 入口/交接文件体积失控（advisory）——AGENTS.md 该是 1–2 屏必读，STATUS.md 该只记增量。
#    实测过：入口涨到 60KB、STATUS 涨到 130KB+，就没人读全了，铁律就靠不住了。
AGENTS_SOFT_LIMIT = 25_000   # ~1–2 屏；超了说明细节没下沉到 §6 指针文档
STATUS_SOFT_LIMIT = 40_000   # STATUS 只记最近增量；超了说明旧 handoff 没归档到进度日志
agents_bytes = len(agents_text.encode("utf-8"))
status_bytes = len(status_text.encode("utf-8"))
if agents_bytes > AGENTS_SOFT_LIMIT:
    warn("AGENTS.md 偏大（入口应 1–2 屏）",
         f"{agents_bytes // 1000}KB > {AGENTS_SOFT_LIMIT // 1000}KB —— 把细节下沉到 §6 指针文档"
         "（任务规划/决策登记表/进度日志），入口只留必读的北极星+现状+铁律。")
if status_bytes > STATUS_SOFT_LIMIT:
    warn("STATUS.md 偏大（应只记最近增量）",
         f"{status_bytes // 1000}KB > {STATUS_SOFT_LIMIT // 1000}KB —— 旧 handoff 归档到 `进度日志.md`，"
         "STATUS 只留最近一两次交接；仍有效的坑上浮到 AGENTS.md §5 铁律。")

# D. 看板有任务却一项没勾（advisory）——刚搭骨架属正常，否则可能是收工忘了更新看板。
if sec4_present and (sec4_checked + sec4_unchecked) > 0 and sec4_checked == 0:
    warn("§4 看板全未勾选",
         "有任务但一项都没勾——若是刚搭骨架属正常；否则收工时记得把完成项勾成 [x]。")


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
if warnings:
    print("-" * 60)
    for name, detail in warnings:
        print(f"  ⚠️ WARN  {name}")
        if detail:
            print(f"           {detail}")
print("=" * 60)
if all_pass:
    msg = "  🎉 全部通过，交接合格。"
    if warnings:
        msg += f"（另有 {len(warnings)} 条 advisory 提醒，建议处理但不阻塞）"
    print(msg)
    sys.exit(0)
else:
    fails = sum(1 for _, ok, _ in results if not ok)
    print(f"  ⚠️ {fails} 项未通过，收工前请补齐再交接。")
    sys.exit(1)

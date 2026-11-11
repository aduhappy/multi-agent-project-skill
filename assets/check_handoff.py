#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_handoff.py — 收工交接自检（multi-agent-project skill 配套）

用法：
    python scripts/check_handoff.py                    # 以当前目录为线级项目根
    python scripts/check_handoff.py PATH --days 30     # 指定根、放宽新鲜度窗口
    python scripts/check_handoff.py PATH --scope index # 多线课题的根索引

线级检查（--scope line，默认）：
  H001 AGENTS.md 存在且非空
  H002 线级入口没有声明 Scope: index（声明了就该用 --scope index）
  H003 §3「现在在哪」有近 N 天的日期
  H004 TL;DR 已填（不是模板占位符）
  H005 STATUS.md 存在、非模板、有真实日期
  H006 STATUS 最新交接日期 >= §3 最近日期（交接标题＝含 Handoff，或标题以日期开头）
  H007 至少一个薄指针指向 AGENTS.md（没有薄指针也算通过）
  H008 §4 看板存在且有任务行
  H009 TL;DR 日期与 §3 不矛盾（任一方没日期则跳过）
  A001–A012 只提示不阻断：决策登记表、多脚本常量漂移、入口与任务卡索引体积、
             看板全未勾、任务卡缺执行方或独立复核方派发提示词、任务卡过大（列最大三节）、
             卡面状态与 §4 看板／任务卡索引对不上、§3 超 5 条或挂着已收口卡的“待审查”、
             “进度回写”单行超 400 字、§3 单条超 600 字、
             STATUS 最新交接段 ≤800 字且四节齐、复核报告末尾单独一行 PASS 或 NEEDS_FIX
             （A005—A009 只查 文档/任务卡/ 顶层的卡；提示词段＝标题带 📋 或“提示词”，A005 跳过已收口 ✅ 与作废 🗄️ 卡；
              A007、A008 只读“进度回写”节的“状态：”行，只比收口（✅/🗄️）与否，§4 一行多卡带内联状态符号时逐卡比对；
              A009 只数“进度回写”节里以 - 或 * 开头的行；A010 的一条＝§3 顶层列表项连同缩进的续行；
              A011 查 STATUS 最新交接段的字数与四节：改了什么 / 怎么验证的 / 没做什么 / 不确定处
              （不强制正则检“谁做的”行标签；假设交接段按时间正序追加在末尾或整体倒序置顶，段间不夹非交接同级 ## 节）；
              A012 查 文档/ 与 reports/ 下文件名含“复核”的 .md，排除任务卡与作废目录，非复核方法文档勿以“复核”命名）

根索引检查（--scope index）：
  I001 根 AGENTS.md 存在；I002 声明为索引；I003 表里列出的线级 AGENTS.md 都存在

退出码：0 = 没有阻断项失败；1 = 有失败；2 = 根目录不存在。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DATE_RE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
PROMPT_HEAD_RE = re.compile(r"(?m)^#{1,6}\s.*(?:📋|提示词).*$")
STATE_RE = re.compile(r"🟠|⬜|⏳|🟡|🔵|✅|⛔|🗄")
CLOSED = ("✅", "🗄")
PLACEHOLDER_RE = re.compile(
    r"【待填|【TODO|TODO】|\[TODO\b|<TODO\b|YYYY-MM-DD|<fill|\[fill|<待填|\[待填"
    r"|例\s*T3\s*进行中"
    r"|第一个动作，精确到文件/命令"
    r"|无\s*/\s*等用户确认\s*X\s*/\s*等数据下载"
    r"|e\.g\.\s*T3\s+in\s+progress"
    r"|first\s+action,\s*precise\s+to\s+file/command"
    r"|None\s*/\s*waiting\s+for\s+user\s+to\s+confirm\s+X",
    re.I,
)
EMPTY_TLDR_FIELD_RE = re.compile(
    r"(?m)^>?\s*[-*]\s*\**(?:当前阶段|下一步|阻塞|Current\s+stage|Next\s+step|Blockers?)\**\s*[:：]\s*(?:TODO|TBD|待填)?\s*$",
    re.I,
)
SLASH_CARDS_RE = re.compile(r"(?<![A-Za-z0-9-])([A-Za-z]+\d+)([a-z](?:/[a-z])+)(?![A-Za-z0-9-])")
GENERIC_TASK_RE = re.compile(r"(?<![A-Za-z0-9-])T\d+[A-Za-z0-9-]*(?![A-Za-z0-9-])")
CLAUSE_SEP_RE = re.compile(r"[、，,;；|]")
HANDOFF_SECTIONS = (
    ("改了什么", re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*\**改了什么")),
    ("怎么验证的", re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*\**怎么验证")),
    ("没做什么", re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*\**没做什么")),
    ("不确定处", re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*\**不确定处")),
)
SKIP_REVIEW_DIRS = {"任务卡", "决策记录", "原始资料", "_作废", "归档"}

findings: list[tuple[str, str, bool, str, bool]] = []  # code, name, ok, detail, advisory


def add(code: str, name: str, ok: bool, detail: str = "", advisory: bool = False) -> None:
    findings.append((code, name, ok, detail, advisory))


def read(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def unfenced_indices(lines: list[str]) -> set[int]:
    out: set[int] = set()
    fence_char, fence_len = "", 0
    for i, ln in enumerate(lines):
        m = FENCE_RE.match(ln)
        if not fence_char:
            if m and (m.group(1)[0] == "~" or "`" not in m.group(2)):
                fence_char, fence_len = m.group(1)[0], len(m.group(1))
                continue
            out.add(i)
        elif m and m.group(1)[0] == fence_char and len(m.group(1)) >= fence_len and not m.group(2).strip():
            fence_char, fence_len = "", 0
    return out


def section(text: str, number: str, titles: set[str]) -> str:
    """Level-2 section ``## 3`` / ``## 3.`` / exact title, up to the next ``## ``."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## ") and (
            re.match(rf"^## {number}(?:\.(?!\d)|\s|$)", line) or line[3:].strip() in titles
        ):
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            return "\n".join(lines[i:end])
    return ""


def strip_fenced(text: str) -> str:
    lines = text.splitlines()
    keep = unfenced_indices(lines)
    return "\n".join(ln for i, ln in enumerate(lines) if i in keep)


def dates(text: str, today: date) -> list[date]:
    result = []
    for token in DATE_RE.findall(text):
        try:
            value = datetime.strptime(token, "%Y-%m-%d").date()
        except ValueError:
            continue
        if value <= today:
            result.append(value)
    return result


def latest(text: str, today: date) -> Optional[date]:
    found = dates(text, today)
    return max(found) if found else None


def pointer_ok(text: str) -> bool:
    if "AGENTS.md" not in text:
        return False
    positive = re.search(
        r"(?is)(?:see|read|先读|以|权威入口|authoritative|scope\s+root|project\s+root|line\s+root)[^\n]{0,180}AGENTS\.md"
        r"|AGENTS\.md[^\n]{0,180}(?:权威|authoritative|先读|read|scope\s+root|project\s+root|line\s+root)",
        text,
    )
    negative = re.search(
        r"(?is)(?:不存在|没有|不要|never\s+(?:read|use|follow))[^\n]{0,60}AGENTS\.md"
        r"|AGENTS\.md[^\n]{0,30}(?:已?废弃|已?弃用|不再使用|deprecated|no\s+longer)",
        text,
    )
    return bool(positive and not negative)


def handoff_blocks(status: str) -> list[str]:
    lines = status.splitlines()
    unfenced = unfenced_indices(lines)
    headings: list[tuple[int, int, str]] = []
    for i in sorted(unfenced):
        m = re.match(r"^\s*(#{1,6})\s+(.*)$", lines[i])
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))

    handoffs = [
        (i, lvl, t) for i, lvl, t in headings
        if lvl >= 2 and (re.search(r"(?i)handoff", t) or re.match(r"^\d{4}-\d{2}-\d{2}", t))
    ]
    if not handoffs:
        return []

    top_lvl = min(lvl for _, lvl, _ in handoffs)
    starts = [i for i, lvl, _ in handoffs if lvl == top_lvl]
    blocks: list[str] = []
    for idx, start in enumerate(starts):
        end = next((i for i, lvl, _ in headings if i > start and lvl <= top_lvl), len(lines))
        seg = lines[start:end]
        if idx == len(starts) - 1:
            while seg and not seg[-1].strip():
                seg.pop()
            while seg and re.match(r"^>\s*⚠️", seg[-1].strip()):
                seg.pop()
                while seg and not seg[-1].strip():
                    seg.pop()
        blocks.append("\n".join(seg).strip())
    return blocks


def top_card_sections(text: str, k: int = 3) -> str:
    lines = text.splitlines()
    unfenced = unfenced_indices(lines)
    secs: list[tuple[str, list[str]]] = []
    cur_title, cur_lines = "(卡头)", []
    for i, ln in enumerate(lines):
        if i in unfenced and ln.startswith("## "):
            secs.append((cur_title, cur_lines))
            cur_title, cur_lines = ln[3:].strip(), [ln]
        else:
            cur_lines.append(ln)
    secs.append((cur_title, cur_lines))
    sized = []
    for t, ls in secs:
        if not "\n".join(ls).strip():
            continue
        prefix = re.split(r"[（(]", t)[0].strip()
        label = (prefix if len(prefix) >= 6 else t)[:20].rstrip()
        sized.append((label, len("\n".join(ls).encode("utf-8"))))
    sized.sort(key=lambda x: x[1], reverse=True)
    return " / ".join(f"「{t}」{b}B" for t, b in sized[:k])


def collect_review_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for sub in ("文档", "reports"):
        base = root / sub
        if not base.is_dir():
            continue
        for fp in sorted(base.rglob("*.md")):
            rel_parts = fp.relative_to(base).parts[:-1]
            if any(
                p in SKIP_REVIEW_DIRS or p.startswith("_") or p.endswith("_DEPRECATED")
                for p in rel_parts
            ):
                continue
            if fp.stem.endswith("_DEPRECATED"):
                continue
            if "复核" in fp.stem:
                found.append(fp)
    return found


def line_checks(root: Path, days: int, today: date) -> None:
    agents = read(root / "AGENTS.md")
    status = read(root / "STATUS.md")
    add("H001", "AGENTS.md 存在且非空", len(agents.strip()) > 100, f"{len(agents)} chars" if agents else "missing")
    declared_index = bool(re.search(r"(?m)^>\s*\*\*Scope[:：]\s*index\*\*", agents))
    add("H002", "线级入口未声明为根索引", not declared_index, "请改用 --scope index" if declared_index else "line scope")

    sec3_date = latest(strip_fenced(section(agents, "3", {"现在在哪", "Where We Are Now"})), today)
    add(
        "H003",
        f"§3 有近 {days} 天日期",
        bool(sec3_date and sec3_date >= today - timedelta(days=days)),
        f"最近日期 {sec3_date}" if sec3_date else "§3 没有有效日期",
    )

    match = re.search(r"(?im)^[^\n]*TL;DR[^\n]*.*?(?=^---\s*$|^##\s|\Z)", agents, re.DOTALL)
    tldr = match.group(0) if match else ""
    tldr_unfilled = not tldr.strip() or bool(PLACEHOLDER_RE.search(tldr) or EMPTY_TLDR_FIELD_RE.search(tldr))
    add("H004", "TL;DR 已填（非占位符）", not tldr_unfilled,
        "已填" if not tldr_unfilled else "缺失或仍含占位符")

    add("H005", "STATUS.md 存在且非模板",
        len(status.strip()) > 50 and bool(dates(status, today)) and "YYYY-MM-DD" not in status,
        "已填" if status else "missing")

    # 交接标题：含 Handoff，或标题正文以日期开头（如 “## 2026-09-19 主控：…”）；归档说明等其他标题不算
    heads = "\n".join(
        line for line in status.splitlines()
        if re.match(r"^\s*#{1,6}\s+", line)
        and (re.search(r"(?i)handoff", line) or re.match(r"^\s*#{1,6}\s+\d{4}-\d{2}-\d{2}", line))
    )
    status_date = latest(heads, today) or latest(status, today)
    add("H006", "STATUS 最新交接日期 >= §3 日期", bool(status_date and sec3_date and status_date >= sec3_date),
        f"STATUS {status_date} vs §3 {sec3_date}")

    pointers = [root / n for n in ("CLAUDE.md", "GEMINI.md", ".cursorrules", ".github/copilot-instructions.md")]
    if (root / ".cursor" / "rules").is_dir():
        pointers += sorted((root / ".cursor" / "rules").glob("*.mdc"))
    existing = [p for p in pointers if p.is_file()]
    valid = [p.relative_to(root).as_posix() for p in existing if pointer_ok(read(p))]
    add("H007", "薄指针至少一个指向 AGENTS.md", not existing or bool(valid),
        ", ".join(valid) if valid else ("未生成薄指针" if not existing else "没有有效指针"))

    sec4 = section(agents, "4", {"任务看板", "下一步任务看板", "Next Task Board"})
    add("H008", "§4 看板存在且有任务行", bool(re.search(r"(?m)^\s*[-*]\s*\[[ xX]\]", sec4)))

    tldr_date = latest(strip_fenced(tldr), today)
    conflict = bool(tldr_date and sec3_date and tldr_date < sec3_date - timedelta(days=1))
    add("H009", "TL;DR 日期与 §3 不矛盾", not conflict, f"TL;DR {tldr_date} vs §3 {sec3_date}")

    advisories(root, agents, status, sec4, today)


def advisories(root: Path, agents: str, status: str, sec4: str, today: date) -> None:
    registry = "决策登记表" in agents or "决策登记表" in status or (root / "文档" / "决策登记表.md").is_file()
    add("A001", "决策登记表存在", registry, "" if registry else "具约束力的决策应收口到一张可 grep 的表", True)

    const_re = re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*=\s*(\{[^{}]*\}|\[[^\[\]]*\])", re.M)
    seen: dict[str, dict[tuple[str, ...], list[str]]] = {}
    scripts = root / "scripts"
    for fp in sorted(scripts.rglob("*.py")) if scripts.is_dir() else []:
        for m in const_re.finditer(read(fp)):
            members = tuple(sorted(re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))))
            if members:
                seen.setdefault(m.group(1), {}).setdefault(members, []).append(fp.name)
    drift = [f"{name}: {list(v.values())}" for name, v in seen.items() if len(v) > 1]
    add("A002", "多脚本同名常量集合一致", not drift, "; ".join(drift), True)

    index = read(root / "文档" / "任务卡_README.md")
    agents_sz = len(agents.encode("utf-8"))
    status_sz = len(status.encode("utf-8"))
    index_sz = len(index.encode("utf-8"))
    big = [f"{n} {sz // 1000}KB" for n, sz, limit in
           (("AGENTS.md", agents_sz, 25_000), ("STATUS.md", status_sz, 40_000), ("任务卡_README.md", index_sz, 15_000))
           if sz > limit]
    a003_hints = []
    if status_sz > 40_000:
        a003_hints.append(
            "STATUS 超限可运行 python scripts/archive_status.py 归档旧交接段"
            "（原样移到 文档/STATUS_归档_至<日期>.md，入口留一行 > 引用，不要写成带日期的标题）"
        )
    if agents_sz > 25_000:
        a003_hints.append(
            "AGENTS 超限多半在 §3.5 决策登记表，需按决策表规矩把全文原样迁到 文档/决策记录/决策登记表_全文.md、§3.5 改短行索引"
            "（若在 §3 快照超 5 条，也可跑 archive_status.py 归档 §3 旧条）"
        )
    if index_sz > 15_000:
        a003_hints.append("任务卡索引超限请精简表内细节（细节留各卡或归档已收口旧批）")
    add("A003", "AGENTS ≤25KB、STATUS ≤40KB、任务卡索引 ≤15KB", not big,
        "；".join([", ".join(big), *a003_hints]) if big else "", True)

    checked = len(re.findall(r"(?m)^\s*[-*]\s*\[[xX]\]", sec4))
    unchecked = len(re.findall(r"(?m)^\s*[-*]\s*\[\s?\]", sec4))
    add("A004", "§4 看板至少勾了一项", not (unchecked and not checked), f"{checked} 勾 / {unchecked} 未勾", True)

    cards_dir = root / "文档" / "任务卡"
    cards = sorted(cards_dir.glob("*.md")) if cards_dir.is_dir() else []
    active_cards = []
    lacking = []
    for fp in cards:
        text = read(fp)
        if single_card_state(text) in CLOSED:
            continue
        active_cards.append(fp)
        heads = PROMPT_HEAD_RE.findall(strip_fenced(text))
        if not (any("执行" in h for h in heads) and any("复核" in h for h in heads)):
            lacking.append(fp.name)
    closed_cnt = len(cards) - len(active_cards)
    a005_ok = f"{len(active_cards)} 张在用卡（跳过 {closed_cnt} 张收口/作废）" if closed_cnt else f"{len(active_cards)} 张卡"
    add("A005", "任务卡同时带执行方和独立复核方提示词", not lacking,
        (f"{len(lacking)} 张缺：" + "、".join(lacking[:5]) + ("…" if len(lacking) > 5 else "")
         + "；一个任务一张卡，复核写在同一张卡里（已收口 ✅ 与作废 🗄️ 卡不查）") if lacking else a005_ok, True)

    bloated = []
    for fp in cards:
        text = read(fp)
        size = len(text.encode("utf-8"))
        prompts = len(PROMPT_HEAD_RE.findall(text))
        if size > 15_000:
            bloated.append(f"{fp.name}（{size // 1000}KB，{prompts} 段提示词；最大三节：{top_card_sections(text)}）")
        elif prompts > 3:
            bloated.append(f"{fp.name}（{size // 1000}KB，{prompts} 段提示词）")
    add("A006", "任务卡 ≤15KB、提示词段 ≤3", not bloated,
        (f"{len(bloated)} 张：" + "；".join(bloated[:6]) + ("…" if len(bloated) > 6 else "")
         + "；超限部分该挪到 STATUS 或开新卡，就地改并删用过的提示词（见 任务卡_README.md 卡面规矩）") if bloated else "", True)

    states = card_states(cards)
    sec3 = section(agents, "3", {"现在在哪", "Where We Are Now"})
    drift = []
    for row in (ln for ln in index.splitlines() if ln.lstrip().startswith("|")):
        cells = [c.strip(" *`") for c in row.strip().strip("|").split("|")]
        # 卡号通常在第一列；第一列是序号等时退回“卡文件名出现在这一行”
        for cid, (state, name) in states.items():
            mark = STATE_RE.search("|".join(cells[1:]))
            if (cells[0] == cid or name in row) and mark and (mark.group(0) in CLOSED) != (state in CLOSED):
                drift.append(f"{cid} 卡面 {state}／索引 {mark.group(0)}")
    drift.extend(sec4_card_drifts(sec4, states))
    add("A007", "卡面状态与 §4 看板、任务卡索引一致（只比收口与否）", not drift,
        ("；".join(drift[:6]) + ("…" if len(drift) > 6 else "") + "；对不上以卡面为准，主控收口时同步 §4 与索引")
        if drift else f"{len(states)} 张卡有“进度回写”", True)

    items = [ln for ln in sec3.splitlines() if re.match(r"^[-*]\s+(?!`?→)", ln)]
    stale = sorted({cid for ln in sec3.splitlines() if re.search(r"待审查|待复核|待收口|已交回|🟡|🔵", ln)
                    for cid in [subject_card(ln, states)] if cid and states[cid][0] in CLOSED})
    add("A008", "§3 ≤5 条、不挂已收口卡的“待审查”", len(items) <= 5 and not stale,
        f"§3 {len(items)} 条" + (f"；卡面已收口仍挂待审查：{'、'.join(stale)}" if stale else "")
        + ("；§3 只留 1–5 条累计快照，旧条移到归档" if len(items) > 5 or stale else ""), True)

    long_rows = []
    for fp in cards:
        text = read(fp)
        head = re.search(r"(?m)^##\s*进度回写.*$", text)
        body = text[head.end():].split("\n## ", 1)[0] if head else ""
        long_rows += [f"{fp.name}「{re.split('[:：]', ln.strip().lstrip('-* '))[0][:12]}」行 {len(ln.strip())} 字"
                      for ln in body.splitlines() if re.match(r"^\s*[-*]\s", ln) and len(ln.strip()) > 400]
    add("A009", "“进度回写”每行 ≤400 字", not long_rows,
        ("；".join(long_rows[:4]) + ("…" if len(long_rows) > 4 else "")
         + "；一句话结果之外的细节写进 STATUS 或结果说明") if long_rows else "", True)

    entries, cur = [], None
    for ln in sec3.splitlines()[1:]:
        if re.match(r"^[-*]\s+(?!`?→)", ln):
            cur = [ln]
            entries.append(cur)
        elif re.match(r"^\S", ln):
            cur = None
        elif cur is not None:
            cur.append(ln)
    sizes = [len("\n".join(e).strip()) for e in entries]
    wordy = [f"第 {i} 条（{e[0].lstrip('-* ')[:14]}…）{n} 字"
             for i, (e, n) in enumerate(zip(entries, sizes), 1) if n > 600]
    add("A010", "§3 每条 ≤600 字", not wordy,
        ("；".join(wordy[:4]) + ("…" if len(wordy) > 4 else "")
         + "；细节写进 STATUS，§3 只留累计快照；不要往 §3 追加执行方交回长段") if wordy else "", True)

    blocks = handoff_blocks(status)
    if not blocks:
        add("A011", "STATUS 最新交接段 ≤800 字且四节齐", False,
            "未找到交接段（标题须含 Handoff 或以 YYYY-MM-DD 开头）", True)
    else:
        d_first, d_last = latest(blocks[0], today), latest(blocks[-1], today)
        latest_seg = blocks[0] if (d_first and d_last and d_first > d_last) else blocks[-1]
        seg_len = len(latest_seg.strip())
        unfence_seg = strip_fenced(latest_seg)
        missing_secs = [label for label, pat in HANDOFF_SECTIONS if not pat.search(unfence_seg)]
        a011_ok = seg_len <= 800 and not missing_secs
        if a011_ok:
            a011_detail = f"{seg_len} 字，四节齐"
        else:
            parts = [f"最新交接段 {seg_len} 字" + ("（超 800 字）" if seg_len > 800 else "")]
            if missing_secs:
                parts.append("缺节：" + "、".join(missing_secs))
            parts.append("须含“改了什么 / 怎么验证的 / 没做什么 / 不确定处”四节且 ≤800 字")
            a011_detail = "；".join(parts)
        add("A011", "STATUS 最新交接段 ≤800 字且四节齐", a011_ok, a011_detail, True)

    review_files = collect_review_files(root)
    bad_reviews = []
    for fp in review_files:
        non_empty = [ln.strip() for ln in read(fp).splitlines() if ln.strip()]
        if not non_empty or non_empty[-1] not in ("PASS", "NEEDS_FIX"):
            bad_reviews.append(fp.name)
    add("A012", "复核报告末尾有单独一行 PASS 或 NEEDS_FIX", not bad_reviews,
        (f"{len(bad_reviews)} 份缺结论行：" + "、".join(bad_reviews[:5]) + ("…" if len(bad_reviews) > 5 else "")
         + "；复核报告末尾须单独一行只写 PASS 或 NEEDS_FIX")
        if bad_reviews else (f"{len(review_files)} 份复核报告" if review_files else "暂无复核报告"), True)


def card_re(cid: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9-]){re.escape(cid)}(?![A-Za-z0-9-])")


def subject_card(line: str, states: dict[str, tuple[str, str]]) -> Optional[str]:
    """这一条说的是哪张卡：第一段加粗里最先出现的卡号；没有加粗才看整行。
    约定：§3 条目若有加粗，卡号写进第一段加粗；不回退到整行，免得把顺带提到的卡当成主题。"""
    bold = re.search(r"\*\*(.+?)\*\*", line)
    text = bold.group(1) if bold else line
    hits = [(m.start(), cid) for cid in states for m in [card_re(cid).search(text)] if m]
    return min(hits)[1] if hits else None


def _mask_parens_for_sec4(text: str, states: dict[str, tuple[str, str]]) -> str:
    """屏蔽括号内的依赖/接续说明（如“（依赖 T10）”“（由 T12g 接续）”），保留纯状态括号（如“（✅）”）。"""
    def _repl(m: re.Match[str]) -> str:
        inner = m.group(0)
        if GENERIC_TASK_RE.search(inner) or any(card_re(cid).search(inner) for cid in states):
            return " " * len(inner)
        return "".join(ch if STATE_RE.match(ch) else " " for ch in inner)

    return re.sub(r"（[^（）]*）|\([^()]*\)", _repl, text)


def _sec4_item_groups(body: str, states: dict[str, tuple[str, str]]) -> tuple[str, list[tuple[int, int, list[str]]]]:
    """提取单条 §4 勾选行（去掉行首 `- [ ]`）中的卡号组 [(start, end, [cid, ...]), ...]。"""
    masked = _mask_parens_for_sec4(body, states)
    bold_spans = [m.span() for m in re.finditer(r"\*\*(.+?)\*\*", masked)]

    def _in_bold(pos: int) -> bool:
        return any(bs <= pos < be for bs, be in bold_spans)

    def _allowed_unbolded(start: int) -> bool:
        prev_seps = [m.end() for m in CLAUSE_SEP_RE.finditer(masked[:start])]
        clause_start = prev_seps[-1] if prev_seps else 0
        prefix_in_clause = masked[clause_start:start]
        if re.fullmatch(r"[\s🟠⬜⏳🟡🔵✅⛔🗄\ufe0f]*", prefix_in_clause):
            return True
        if not bold_spans and re.search(r"[🟠⬜⏳🟡🔵✅⛔🗄]\ufe0f?\s*$", masked[:start]):
            return True
        return False

    raw_hits: list[tuple[int, int, list[str]]] = []
    for m in SLASH_CARDS_RE.finditer(masked):
        s, e = m.span()
        if _in_bold(s) or _allowed_unbolded(s):
            base = m.group(1)
            raw_hits.append((s, e, [f"{base}{ch}" for ch in m.group(2).split("/")]))

    for cid in sorted(states, key=len, reverse=True):
        for m in card_re(cid).finditer(masked):
            s, e = m.span()
            if _in_bold(s) or _allowed_unbolded(s):
                raw_hits.append((s, e, [cid]))

    for m in GENERIC_TASK_RE.finditer(masked):
        s, e = m.span()
        if _in_bold(s) or _allowed_unbolded(s):
            raw_hits.append((s, e, [m.group(0)]))

    raw_hits.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    groups: list[tuple[int, int, list[str]]] = []
    last_e = -1
    for s, e, cids in raw_hits:
        if s >= last_e:
            groups.append((s, e, cids))
            last_e = e
    return masked, groups


def sec4_card_drifts(sec4: str, states: dict[str, tuple[str, str]]) -> list[str]:
    """核对 §4 看板与卡面收口状态：单卡行看行首勾选框；一行多卡时优先看各卡同子句的内联状态符号。"""
    drifts: list[str] = []
    for line_match in re.finditer(r"(?m)^\s*[-*]\s*\[([ xX]?)\](.*)$", sec4):
        sub_parts = re.split(r"\s+[-*]\s*\[([ xX]?)\]", line_match.group(2))
        sub_items = [(line_match.group(1), sub_parts[0])]
        for k in range(1, len(sub_parts), 2):
            sub_items.append((sub_parts[k], sub_parts[k + 1]))

        for box, body in sub_items:
            box_done = box in ("x", "X")
            masked, groups = _sec4_item_groups(body, states)
            if not groups:
                continue
            if sum(len(g[2]) for g in groups) <= 1:
                cid = groups[0][2][0]
                if cid in states and box_done != (states[cid][0] in CLOSED):
                    drifts.append(f"{cid} 卡面 {states[cid][0]}／§4 {'已勾' if box_done else '未勾'}")
                continue

            for idx, (s, e, cids) in enumerate(groups):
                next_s = groups[idx + 1][0] if idx + 1 < len(groups) else len(masked)
                after = masked[e:next_s]
                if idx + 1 < len(groups):
                    sep = CLAUSE_SEP_RE.search(after)
                    own_after = after[: sep.start()] if sep else after
                else:
                    own_after = after
                mark_m = STATE_RE.search(own_after)
                if not mark_m:
                    prev_e = groups[idx - 1][1] if idx > 0 else 0
                    before = masked[prev_e:s]
                    if idx == 0:
                        own_before = before
                    else:
                        seps = list(CLAUSE_SEP_RE.finditer(before))
                        own_before = before[seps[-1].end() :] if seps else ""
                    mark_m = STATE_RE.search(own_before)

                for cid in cids:
                    if cid not in states:
                        continue
                    card_st = states[cid][0]
                    if mark_m:
                        inline_st = mark_m.group(0)
                        if (inline_st in CLOSED) != (card_st in CLOSED):
                            drifts.append(f"{cid} 卡面 {card_st}／§4 {inline_st}")
                    elif box_done != (card_st in CLOSED):
                        drifts.append(f"{cid} 卡面 {card_st}／§4 {'已勾' if box_done else '未勾'}")
    return drifts


def single_card_state(text: str) -> Optional[str]:
    head = re.search(r"(?m)^##\s*进度回写.*$", text)
    body = text[head.end():].split("\n## ", 1)[0] if head else ""
    line = re.search(r"(?m)^\s*[-*]\s*\**状态\**[:：](.*)$", body)
    mark = STATE_RE.search(line.group(1)) if line else None
    return mark.group(0) if mark else None


def card_states(cards: list[Path]) -> dict[str, tuple[str, str]]:
    """卡号（文件名第一个 _ 之前）→（“进度回写”节里“状态：”行的第一个状态符号, 文件名）。"""
    states = {}
    for fp in cards:
        mark = single_card_state(read(fp))
        if mark:
            states[fp.stem.split("_")[0]] = (mark, fp.name)
    return states


def index_checks(root: Path) -> None:
    text = read(root / "AGENTS.md")
    add("I001", "根 AGENTS.md 存在", bool(text.strip()))
    declared = bool(re.search(r"(?mi)^>\s*\*\*Scope[:：]\s*index\*\*", text)) or bool(
        re.search(r"根索引|课题总索引|本文件只是索引|root\s+index", text, re.I) and not section(text, "3", {"现在在哪"})
    )
    add("I002", "根 AGENTS.md 声明为索引", declared, "" if declared else "缺少 Scope: index 标记，或混入了线级 §3")
    paths = sorted({p.replace("\\", "/") for p in re.findall(r"([\w.\-一-鿿/\\]+/AGENTS\.md)", text)})
    missing = [p for p in paths if not (root / p).is_file()]
    add("I003", "列出的线级 AGENTS.md 都存在", bool(paths) and not missing,
        ("missing: " + ", ".join(missing)) if missing else f"{len(paths)} 条线" if paths else "没列出线级入口")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="收工交接自检")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--days", "-d", type=int, default=7)
    parser.add_argument("--scope", choices=("line", "index"), default="line")
    parser.add_argument("--today", help="YYYY-MM-DD，覆盖检查日期（测试用）")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"[H000] ❌ FAIL 项目根不是目录：{root}", file=sys.stderr)
        return 2
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()

    findings.clear()
    if args.scope == "index":
        index_checks(root)
    else:
        line_checks(root, args.days, today)

    print("=" * 60)
    print(f"  收工交接自检 | scope={args.scope} | today={today}")
    print("=" * 60)
    failed = 0
    for code, name, ok, detail, advisory in findings:
        mark = "✅ PASS" if ok else ("⚠️ WARN" if advisory else "❌ FAIL")
        failed += 0 if ok or advisory else 1
        print(f"  [{code}] {mark}  {name}" + (f"\n             {detail}" if detail else ""))
    print("=" * 60)
    print(f"  {failed} 项失败。" if failed else "  全部通过（WARN 只是提示）。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

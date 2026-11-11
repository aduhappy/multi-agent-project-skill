#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_handoff.py — 收工交接自检（multi-agent-project skill 配套）

用法：
    python scripts/check_handoff.py                    # 以当前目录为线级项目根
    python scripts/check_handoff.py PATH --days 30     # 指定根、放宽新鲜度窗口
    python scripts/check_handoff.py PATH --scope index # 多线课题的根索引
    python scripts/check_handoff.py --version          # 查看脚本版本号

线级检查（--scope line，默认）：
  H001 AGENTS.md 存在且非空
  H002 线级入口没有声明 Scope: index（声明了就该用 --scope index）
  H003 §3「现在在哪」日期未落后 STATUS 最新交接超过 N 天
       （0.4.1 改：改为与 STATUS 最新交接日期比，有比 §3 新 N 天以上的交接而 §3 没跟上才失败，
        项目停工超 N 天不再失败；STATUS 没有交接时退回与今天比）
  H004 TL;DR 已填（不是模板占位符）
  H005 STATUS.md 存在、非模板、有真实日期（仅在标题、“现状”行、字段占位等模板位置判未填）
  H006 STATUS 最新交接日期 >= §3 最近日期
       （交接标题仅认 ## 或 ###，#### 及更深标题不算；须含 Handoff/交接，或以日期 / T<卡号>+日期 开头；
        “交回说明”等不算交接；日期支持 YYYY-MM-DD、YYYY/MM/DD、YYYY.MM.DD、YYYY年MM月DD日）
  H007 至少一个薄指针指向 AGENTS.md（没有薄指针也算通过）
  H008 §4 看板存在且有真实任务行（仅含模板占位行不算）
  H009 TL;DR 日期与 §3 不矛盾（任一方没日期则跳过）
  A001–A015 只提示不阻断：
       A001 决策登记表存在
       A002 多脚本同名口径常量集合一致（自动排除 *_COLORS 等显示/配色常量，支持 # noqa: A002 豁免）
       A003 入口与任务卡索引体积（AGENTS ≤25KB、STATUS ≤40KB、任务卡索引 ≤15KB）
       A004 §4 看板至少勾了一项（模板占位行不算）
       A005 在用任务卡同时带执行方和独立复核方派发提示词（跳过 ✅/🗄️）
       A006 在用任务卡 ≤15KB、提示词段 ≤3（超限时列最大三节；跳过 ✅/🗄️）
       A007 卡面状态与 §4 看板／任务卡索引一致（状态行顶格写；只比收口与否，支持一行多卡内联状态）
       A008 §3 ≤5 条、不挂已收口卡的“待审查”
       A009 在用任务卡“进度回写”单行 ≤400 字（跳过 ✅/🗄️）
       A010 §3 单条 ≤600 字（顶层列表项连同缩进续行）
       A011 STATUS 最近 5 段交接（不足 5 段查全部）≤800 字且四节齐
       A012 未收口或无对应卡的复核报告末尾有单独一行 PASS 或 NEEDS_FIX（跳过 ✅/🗄️ 对应卡报告）
       A013 §3.5 决策登记表无重复 ID 且取代链自洽（乙已迁出表外不报）
       A014 AGENTS.md 剩余【待填】按节统计，§5“不可混用的维度”未填单独点名
       A015 任务卡目录存在且非空（缺失或 0 张卡时提示卡类检查未做）

根索引检查（--scope index）：
  I001 根 AGENTS.md 存在；I002 声明为索引；I003 表里列出的线级 AGENTS.md 都存在

退出码：0 = 没有阻断项失败；1 = 有阻断项失败；2 = 根目录不存在。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

sys.dont_write_bytecode = True

__version__ = "0.4.1"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DATE_RE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
FLEX_DATE_TOKEN_RE = re.compile(
    r"(?<!\d)(20\d{2})(?:([-/.])(\d{1,2})\2(\d{1,2})(?![-/.]?\d)|\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日)"
)
HEADING_DATE_START_RE = re.compile(
    r"^[\[（(【]?\s*20\d{2}(?:([-/.])\d{1,2}\1\d{1,2}(?![-/.]?\d)|\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"
)
DATE_PLACEHOLDER_RE = re.compile(r"YYYY[-/.]MM[-/.]DD|YYYY\s*年\s*MM\s*月\s*DD\s*日", re.I)
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
PROMPT_HEAD_RE = re.compile(r"(?m)^#{1,6}\s.*(?:📋|提示词).*$")
STATE_RE = re.compile(r"🟠|⬜|⏳|🟡|🔵|✅|⛔|🗄")
CARD_STATE_LINE_RE = re.compile(r"(?m)^(?:[-*+][ \t]+)?\**状态\**[ \t]*[:：]\**(.*)$")
CLOSED = ("✅", "🗄")
PLACEHOLDER_SPAN_RE = re.compile(
    r"【\s*(?:待填|TODO|fill)(?:[^【】\n]|【[^【】\n]*】)*】"
    r"|【[^【】\n]*TODO\s*】"
    r"|\[\s*(?:待填|TODO|fill)\b(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]"
    r"|<\s*(?:待填|TODO|fill)\b(?:[^<>\n]|<[^<>\n]*>)*>"
    r"|YYYY[-/.]MM[-/.]DD"
    r"|YYYY\s*年\s*MM\s*月\s*DD\s*日",
    re.I,
)
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
STATUS_TEMPLATE_PROMPT_RE = re.compile(
    r"工具【】\s*/\s*模型【】"
    r"|【新增/修改/删除了哪些文件"
    r"|【跑过的命令与结果原文摘要"
    r"|【明确未做项"
    r"|【风险、UNKNOWN"
    r"|【3\s*行描述当前阶段】"
    r"|【只写本轮必须交接的数字"
    r"|【1\s*行当前依赖/阻塞",
    re.I,
)
STATUS_FIELD_PLACEHOLDER_RE = re.compile(
    r"【待填|【TODO|TODO】|\[TODO\b|<TODO\b|<fill|\[fill|<待填|\[待填"
    r"|工具【】\s*/\s*模型【】"
    r"|【新增/修改/删除了哪些文件"
    r"|【跑过的命令与结果原文摘要"
    r"|【明确未做项"
    r"|【风险、UNKNOWN"
    r"|【3\s*行描述当前阶段】"
    r"|【只写本轮必须交接的数字"
    r"|【1\s*行当前依赖/阻塞",
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
    ("改了什么", re.compile(r"(?m)^\s*>?\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*[\*【\[]*改了什么")),
    ("怎么验证的", re.compile(r"(?m)^\s*>?\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*[\*【\[]*怎么验证")),
    ("没做什么", re.compile(r"(?m)^\s*>?\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*[\*【\[]*没做什么")),
    ("不确定处", re.compile(r"(?m)^\s*>?\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*[\*【\[]*不确定处")),
)
HANDOFF_INNER_HEAD_RE = re.compile(
    r"^(?:[-*+]|\d+[.、)])?\s*[\*【\[]*(?:谁做的|改了什么|怎么验证|没做什么|不确定处)"
)
DISPLAY_CONST_RE = re.compile(
    r"(?:^|_)(?:COLORS?|PALETTES?|CMAPS?|COLORMAPS?|STYLES?|FONTS?|MARKERS?|HATCH(?:ES)?|LINESTYLES?|ALPHAS?|SIZES?|WIDTHS?)$"
)
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$")
DECISION_ID_RE = re.compile(r"[A-Za-z]+-\d+[A-Za-z0-9]*|[A-Za-z]+\d+[A-Za-z0-9]*")
EMPTY_CELL_VALUES = {"", "-", "--", "---", "—", "——", "–", "无", "none", "n/a", "/"}
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
    unfenced = unfenced_indices(lines)
    esc = re.escape(number)
    for i in sorted(unfenced):
        line = lines[i]
        if line.startswith("## ") and (
            re.match(rf"^## {esc}(?:\.(?!\d)|\s|$)", line) or line[3:].strip() in titles
        ):
            end = next((j for j in range(i + 1, len(lines)) if j in unfenced and lines[j].startswith("## ")), len(lines))
            return "\n".join(lines[i:end])
    return ""


def strip_fenced(text: str) -> str:
    lines = text.splitlines()
    keep = unfenced_indices(lines)
    return "\n".join(ln for i, ln in enumerate(lines) if i in keep)


def strip_placeholder_spans(text: str) -> str:
    """Remove inline placeholder spans (e.g. 【待填：...】, [TODO: ...], YYYY-MM-DD) while keeping surrounding text."""
    return PLACEHOLDER_SPAN_RE.sub(" ", text)


def strip_fenced_and_html_comments(text: str) -> str:
    """Strip fenced code blocks and HTML comments (including multiline <!-- ... -->) in a single pass."""
    out_lines: list[str] = []
    fence_char, fence_len = "", 0
    in_comment = False

    def _clean_normal_segment(seg: str) -> tuple[str, bool]:
        buf: list[str] = []
        pos = 0
        while True:
            idx = seg.find("<!--", pos)
            if idx == -1:
                buf.append(seg[pos:])
                return "".join(buf), False
            buf.append(seg[pos:idx])
            end_idx = seg.find("-->", idx + 4)
            if end_idx == -1:
                buf.append(" ")
                return "".join(buf), True
            buf.append(" ")
            pos = end_idx + 3

    for ln in text.splitlines():
        if fence_char:
            m = FENCE_RE.match(ln)
            if m and m.group(1)[0] == fence_char and len(m.group(1)) >= fence_len and not m.group(2).strip():
                fence_char, fence_len = "", 0
            continue
        if in_comment:
            end_idx = ln.find("-->")
            if end_idx == -1:
                continue
            cleaned_tail, in_comment = _clean_normal_segment(ln[end_idx + 3 :])
            out_lines.append(" " + cleaned_tail)
            continue
        m = FENCE_RE.match(ln)
        if m and (m.group(1)[0] == "~" or "`" not in m.group(2)):
            fence_char, fence_len = m.group(1)[0], len(m.group(1))
            continue
        cleaned_ln, in_comment = _clean_normal_segment(ln)
        out_lines.append(cleaned_ln)

    return "\n".join(out_lines)


def scan_dates(text: str) -> tuple[list[date], list[str]]:
    """Return (valid_calendar_dates, invalid_date_tokens) supporting -, /, ., and 年月日."""
    valid: list[date] = []
    invalid: list[str] = []
    for m in FLEX_DATE_TOKEN_RE.finditer(text):
        year = int(m.group(1))
        if m.group(3) is not None:
            month, day = int(m.group(3)), int(m.group(4))
        else:
            month, day = int(m.group(5)), int(m.group(6))
        try:
            valid.append(date(year, month, day))
        except ValueError:
            invalid.append(m.group(0).strip())
    return valid, invalid


def dates(text: str, today: date) -> list[date]:
    valid, _ = scan_dates(text)
    return [d for d in valid if d <= today]


def latest(text: str, today: date) -> Optional[date]:
    found = dates(text, today)
    return max(found) if found else None


def pointer_ok(text: str) -> bool:
    if "AGENTS.md" not in text:
        return False
    if re.search(r"(?m)^\s*@AGENTS\.md\s*$", strip_fenced(text)):
        positive_import = True
    else:
        positive_import = False
    positive = positive_import or bool(
        re.search(
            r"(?is)(?:see|read|先读|以|权威入口|authoritative|scope\s+root|project\s+root|line\s+root)[^\n]{0,180}AGENTS\.md"
            r"|AGENTS\.md[^\n]{0,180}(?:权威|authoritative|先读|read|scope\s+root|project\s+root|line\s+root)",
            text,
        )
    )
    negative = re.search(
        r"(?is)(?:不存在|没有|不要|never\s+(?:read|use|follow))[^\n]{0,60}AGENTS\.md"
        r"|AGENTS\.md[^\n]{0,30}(?:已?废弃|已?弃用|不再使用|deprecated|no\s+longer)",
        text,
    )
    return bool(positive and not negative)


def is_handoff_heading(title: str) -> bool:
    """Recognized handoff headings: contain Handoff/交接, start with date, or start with T<id> + date.
    Headings like '## 交回说明' or '## 归档说明' are NOT handoff headings."""
    t = title.strip()
    if re.search(r"归档|archive|现状一屏|current\s+snapshot", t, re.I):
        return False
    return bool(
        re.search(r"(?i)handoff|交接", t)
        or HEADING_DATE_START_RE.match(t)
        or (re.match(r"^[\[（(【]?\s*T\d+[A-Za-z0-9-]*\b", t, re.I) and FLEX_DATE_TOKEN_RE.search(t))
    )


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
        if lvl in (2, 3) and is_handoff_heading(t) and not HANDOFF_INNER_HEAD_RE.match(t)
    ]
    if not handoffs:
        return []

    handoff_starts = {i for i, _, _ in handoffs}
    blocks: list[str] = []
    for idx, (start, cur_lvl, _) in enumerate(handoffs):
        end = next(
            (
                i for i, lvl, t in headings
                if i > start
                and (
                    i in handoff_starts
                    or lvl < cur_lvl
                    or (lvl == cur_lvl and not HANDOFF_INNER_HEAD_RE.match(t))
                )
            ),
            len(lines),
        )
        seg = lines[start:end]
        while seg and not seg[-1].strip():
            seg.pop()
        if idx == len(handoffs) - 1:
            while seg and re.match(r"^>\s*⚠️", seg[-1].strip()):
                seg.pop()
                while seg and not seg[-1].strip():
                    seg.pop()
        blocks.append("\n".join(seg).strip())
    return blocks


def is_template_task_line(line: str) -> bool:
    body = re.sub(r"^\s*[-*]\s*\[[ xX]?\]\s*", "", line).strip()
    if not body:
        return True
    if PLACEHOLDER_RE.search(body):
        return True
    if re.search(r"(?<![A-Za-z0-9-])T[xyz](?![A-Za-z0-9-])", body) and re.search(r"示例|例[:：\s]", body):
        return True
    return False


def _is_unfilled_placeholder_value(val: str) -> bool:
    """True when a non-empty field value is still a template prompt or consists solely of placeholder spans."""
    if not val:
        return False
    if STATUS_TEMPLATE_PROMPT_RE.search(val):
        return True
    return not strip_placeholder_spans(val).strip(" \t—–-:：;；,，。/|.·()（）[]【】<>")


def check_status_h005(status: str, today: date) -> tuple[bool, str]:
    if not status.strip():
        return False, "STATUS.md 不存在或为空"

    lines = status.splitlines()
    unfenced_set = unfenced_indices(lines)
    unfenced_lines = [lines[i] for i in sorted(unfenced_set)]
    unfenced_text = "\n".join(unfenced_lines)

    reasons: list[str] = []
    if len(status.strip()) <= 50:
        reasons.append(f"内容过短（{len(status.strip())} 字，需 >50 字）")

    all_valid, invalid_tokens = scan_dates(unfenced_text)
    le_today = [d for d in all_valid if d <= today]
    future_dates = [d for d in all_valid if d > today]
    if not le_today:
        if future_dates:
            reasons.append(f"缺少不晚于 today（{today}）的真实日期（仅检测到未来日期 {future_dates[0]}）")
        elif invalid_tokens:
            reasons.append(f"缺少有效真实日期（检测到非法日历日期「{invalid_tokens[0]}」）")
        else:
            reasons.append("未找到真实日期（支持 YYYY-MM-DD、YYYY/MM/DD、YYYY.MM.DD、YYYY年MM月DD日）")

    for ln in unfenced_lines:
        hm = re.match(r"^\s*(#{2,6})\s+(.*)$", ln)
        if hm:
            no_code = re.sub(r"`[^`]*`", "", hm.group(2)).strip()
            has_real_date = bool(scan_dates(no_code)[0])
            if DATE_PLACEHOLDER_RE.search(no_code) and not has_real_date:
                reasons.append(f"标题仍含日期占位符「{hm.group(2).strip()[:28]}」")
            elif STATUS_FIELD_PLACEHOLDER_RE.search(no_code) and not has_real_date:
                reasons.append(f"标题仍含模板占位符「{hm.group(2).strip()[:28]}」")
            continue

        snap_m = re.match(
            r"^\s*>\s*\**(阶段|当前阶段|底座(?:/关键数字)?|关键数字|唯一闸门(?:/阻塞)?|阻塞)\**\s*[:：]\s*(.*)$",
            ln,
        )
        if snap_m:
            val = re.sub(r"`[^`]*`", "", snap_m.group(2)).strip()
            if not val or _is_unfilled_placeholder_value(val):
                reasons.append(f"“现状”行「{snap_m.group(1)}」仍为占位符或未填")
            continue

        if re.match(r"^\s*[-*+]\s*(?:【待填[^】]*】|\[TODO\]|<TODO>|YYYY[-/.]MM[-/.]DD)\s*$", ln, re.I):
            reasons.append("交接条目仍为未填模板占位符")
            continue

        fld_m = re.match(
            r"^\s*(?:[-*+]|\d+[.)])?\s*\**(谁做的|改了什么|怎么验证(?:的)?|没做什么|不确定处|本次做了什么)\**\s*[:：]\s*(.*)$",
            ln,
        )
        if fld_m:
            raw_val = re.sub(r"`[^`]*`", "", fld_m.group(2)).strip()
            if _is_unfilled_placeholder_value(raw_val):
                reasons.append(f"交接字段「{fld_m.group(1)}」仍含模板占位符")

    if not reasons:
        return True, "已填"
    dedup: list[str] = []
    for r in reasons:
        if r not in dedup:
            dedup.append(r)
    return False, "；".join(dedup[:4])


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


def extract_card_id(stem: str) -> str:
    if "_" in stem:
        return stem.split("_")[0]
    m = re.match(r"^([A-Za-z]+\d+[A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)", stem)
    return m.group(1) if m else stem


def review_card_id(fp: Path, states: dict[str, tuple[str, str]]) -> Optional[str]:
    if not states:
        return None
    stem = fp.stem
    ci_map = {cid.upper(): cid for cid in states}
    head = stem.split("_")[0].upper()
    if head in ci_map:
        return ci_map[head]
    for cid in sorted(states, key=len, reverse=True):
        if re.match(rf"^{re.escape(cid)}(?:(?![A-Za-z0-9])|[Rr]\d+(?![A-Za-z0-9]))", stem, re.I):
            return cid
    return None


def check_decision_chain_a013(agents: str) -> tuple[bool, str]:
    lines = agents.splitlines()
    unfenced = unfenced_indices(lines)
    sec_start: Optional[int] = None
    sec_lvl = 2
    sec_end = len(lines)
    for i in sorted(unfenced):
        m = re.match(r"^(#{2,3})\s+(.*)$", lines[i])
        if not m:
            continue
        lvl, title = len(m.group(1)), m.group(2).strip()
        if sec_start is None:
            if re.match(r"^3\.5(?:\.(?!\d)|\s|$)", title) or "决策登记表" in title:
                sec_start, sec_lvl = i, lvl
        elif lvl <= sec_lvl:
            sec_end = i
            break

    if sec_start is None:
        return True, "未设 §3.5 表"

    def _split_row(raw_ln: str) -> list[str]:
        escaped = raw_ln.strip().replace(r"\|", "\x00")
        if escaped.startswith("|"):
            escaped = escaped[1:]
        if escaped.endswith("|"):
            escaped = escaped[:-1]
        return [c.replace("\x00", "|").strip() for c in escaped.split("|")]

    header_cols: Optional[list[str]] = None
    in_decision_table = False
    id_col = 0
    st_col: Optional[int] = None
    rep_col: Optional[int] = None
    rep_by_col: Optional[int] = None
    rows: list[tuple[str, str, str, str, list[str], list[str]]] = []

    table_lines = [
        (idx, lines[idx].strip())
        for idx in range(sec_start + 1, sec_end)
        if idx in unfenced and lines[idx].strip().startswith("|")
    ]

    for pos, (idx, ln) in enumerate(table_lines):
        cells = _split_row(ln)
        if all(re.fullmatch(r"[:\-\s]*", c) for c in cells):
            continue
        next_is_sep = False
        if pos + 1 < len(table_lines) and table_lines[pos + 1][0] == idx + 1:
            next_cells = _split_row(table_lines[pos + 1][1])
            if all(re.fullmatch(r"[:\-\s]*", c) for c in next_cells):
                next_is_sep = True

        clean_cells = [c.strip(" *`") for c in cells]
        if header_cols is None or next_is_sep:
            if any(c.upper() in ("ID", "编号", "决策ID") for c in clean_cells):
                header_cols = clean_cells
                in_decision_table = True
                id_col = 0
                st_col = rep_col = rep_by_col = None
                for ci, cname in enumerate(clean_cells):
                    cu = cname.upper()
                    if cu in ("ID", "编号", "决策ID"):
                        id_col = ci
                    elif cname in ("状态", "Status", "STATUS"):
                        st_col = ci
                    elif "取代了谁" in cname or cname in ("取代", "Supersedes"):
                        rep_col = ci
                    elif "被谁取代" in cname or cname in ("被取代", "Superseded by"):
                        rep_by_col = ci
            elif next_is_sep:
                in_decision_table = False
            continue

        if not in_decision_table or header_cols is None:
            continue

        # Support cells containing unescaped `|` (e.g. `|r|>0.8` in middle text column)
        n_head = len(header_cols)
        raw_id = clean_cells[id_col] if id_col < len(clean_cells) else ""
        if not raw_id or raw_id.startswith("【") or PLACEHOLDER_RE.search(raw_id):
            continue
        raw_st = (clean_cells[st_col] if st_col is not None and st_col < len(clean_cells) else "").upper()

        def _get_tail_col(col_idx: Optional[int]) -> str:
            if col_idx is None:
                return ""
            if len(clean_cells) >= n_head and col_idx >= n_head - 2:
                return clean_cells[col_idx - n_head]
            return clean_cells[col_idx] if col_idx < len(clean_cells) else ""

        raw_rep = _get_tail_col(rep_col)
        raw_rep_by = _get_tail_col(rep_by_col)

        def _norm_id(tok: str) -> str:
            m = re.match(r"^([A-Za-z]+)-?0*(\d+)([A-Za-z0-9]*)$", tok.strip())
            if not m:
                return tok.strip().upper()
            return f"{m.group(1).upper()}-{int(m.group(2))}{m.group(3).upper()}"

        def _parse_ids(val: str) -> list[str]:
            v = val.strip(" *`")
            if v.lower() in EMPTY_CELL_VALUES or PLACEHOLDER_RE.search(v):
                return []
            return [_norm_id(t) for t in DECISION_ID_RE.findall(v)]

        rows.append((raw_id, _norm_id(raw_id), raw_st, raw_rep, raw_rep_by, _parse_ids(raw_rep), _parse_ids(raw_rep_by)))

    if not rows:
        return True, "0 条已登记决策"

    issues: list[str] = []
    seen_ids: dict[str, int] = {}
    by_id: dict[str, tuple[str, str, str, str, list[str], list[str]]] = {}
    for disp_id, norm_cid, st, raw_rep, raw_rep_by, rep_ids, rep_by_ids in rows:
        seen_ids[norm_cid] = seen_ids.get(norm_cid, 0) + 1
        if seen_ids[norm_cid] == 2:
            issues.append(f"重复 ID：{disp_id}")
        by_id.setdefault(norm_cid, (disp_id, st, raw_rep, raw_rep_by, rep_ids, rep_by_ids))

    if st_col is not None and rep_by_col is not None:
        reported_pairs: set[tuple[str, str]] = set()
        for disp_id, norm_cid, st, raw_rep, raw_rep_by, rep_ids, rep_by_ids in rows:
            is_rep_by_empty = raw_rep_by.strip(" *`").lower() in EMPTY_CELL_VALUES
            if st == "SUPERSEDED" and not rep_by_ids:
                issues.append(f"{disp_id} 为 SUPERSEDED 但未填“被谁取代”")
            elif st == "ACTIVE" and not is_rep_by_empty:
                issues.append(f"{disp_id} 为 ACTIVE 但填了“被谁取代”（{raw_rep_by}）")

            if rep_col is not None:
                for target in rep_ids:
                    if target not in by_id:
                        continue  # 乙不在表内（已迁出）不报
                    t_disp, t_st, _, t_raw_rep_by, _, t_rep_by_ids = by_id[target]
                    if t_st != "SUPERSEDED" or norm_cid not in t_rep_by_ids:
                        reported_pairs.add((norm_cid, target))
                        issues.append(
                            f"{disp_id}／{t_disp}（{disp_id} 写取代 {t_disp}，但 {t_disp} 状态={t_st or '空'}、被谁取代={t_raw_rep_by or '空'}）"
                        )
                if st == "SUPERSEDED":
                    for newer in rep_by_ids:
                        if newer not in by_id or (newer, norm_cid) in reported_pairs:
                            continue
                        n_disp, _, n_raw_rep, _, n_rep_ids, _ = by_id[newer]
                        if norm_cid not in n_rep_ids:
                            reported_pairs.add((newer, norm_cid))
                            issues.append(
                                f"{n_disp}／{disp_id}（{disp_id} 写被 {n_disp} 取代，但 {n_disp} 取代了谁={n_raw_rep or '空'}）"
                            )

    if issues:
        return False, f"{len(issues)} 处不一致：" + "；".join(issues[:6]) + ("…" if len(issues) > 6 else "")
    return True, f"{len(rows)} 条决策链自洽"


def check_agents_placeholders_a014(agents: str) -> tuple[bool, str]:
    lines = agents.splitlines()
    unfenced = unfenced_indices(lines)

    cur_sec = "顶部/TL;DR"
    sec_order: list[str] = [cur_sec]
    sec_counts: dict[str, int] = {cur_sec: 0}

    for i in sorted(unfenced):
        ln = lines[i]
        if ln.startswith("## "):
            m_num = re.match(r"^##\s+(\d+(?:\.\d+)?)\b", ln)
            cur_sec = f"§{m_num.group(1)}" if m_num else ln[3:].strip()[:14]
            if cur_sec not in sec_counts:
                sec_order.append(cur_sec)
                sec_counts[cur_sec] = 0
            cnt_h = len(re.findall(r"【待填", ln))
            sec_counts[cur_sec] += cnt_h
        else:
            sec_counts[cur_sec] += len(re.findall(r"【待填", ln))

    non_zero = [(s, sec_counts[s]) for s in sec_order if sec_counts[s] > 0]
    total = sum(c for _, c in non_zero)

    sec5 = strip_fenced(section(agents, "5", {"铁律 / 约定", "铁律/约定", "铁律"}))
    dim_unfilled = False
    if sec5:
        sec5_lines = sec5.splitlines()[1:]
        dim_idx = next((idx for idx, l in enumerate(sec5_lines) if re.search(r"不可混用的?维度", l)), None)
        if dim_idx is not None:
            dim_buf = [sec5_lines[dim_idx]]
            for l in sec5_lines[dim_idx + 1 :]:
                if re.match(r"^[-*]\s+", l) or l.startswith("## "):
                    break
                dim_buf.append(l)
            dim_text = "\n".join(dim_buf)
            if PLACEHOLDER_RE.search(dim_text):
                dim_unfilled = True
            else:
                cleaned = re.sub(
                    r"^[-*]\s*\**不可混用的?维度\**(?:（[^）]*）|\([^)]*\))?\s*[:：]?\s*",
                    "",
                    dim_text,
                ).strip()
                if not cleaned:
                    dim_unfilled = True

    if total == 0 and not dim_unfilled:
        return True, ""

    parts: list[str] = []
    if total > 0:
        parts.append(f"剩余 {total} 处【待填】（" + "、".join(f"{s}: {c}" for s, c in non_zero) + "）")
    if dim_unfilled:
        parts.append("§5“不可混用的维度”尚未填写")
    return False, "；".join(parts)


def line_checks(root: Path, days: int, today: date) -> None:
    agents = read(root / "AGENTS.md")
    status = read(root / "STATUS.md")
    add("H001", "AGENTS.md 存在且非空", len(agents.strip()) > 100, f"{len(agents)} chars" if agents else "missing")
    declared_index = bool(re.search(r"(?m)^>\s*\*\*Scope[:：]\s*index\*\*", agents))
    add("H002", "线级入口未声明为根索引", not declared_index, "请改用 --scope index" if declared_index else "line scope")

    sec3_unfenced = strip_fenced(section(agents, "3", {"现在在哪", "Where We Are Now"}))
    sec3_lines = sec3_unfenced.splitlines() if sec3_unfenced else []
    sec3_has_placeholder = any(
        PLACEHOLDER_SPAN_RE.search(ln) or PLACEHOLDER_RE.search(ln) for ln in sec3_lines
    )
    sec3_real_text = strip_placeholder_spans("\n".join(sec3_lines))
    sec3_date = latest(sec3_real_text, today)
    sec3_is_placeholder = sec3_date is None and sec3_has_placeholder
    sec3_missing_msg = "§3 还是模板占位" if sec3_is_placeholder else "§3 没有有效日期"

    blocks = handoff_blocks(status)
    if blocks:
        head_lines = "\n".join(b.splitlines()[0] for b in blocks if b.splitlines())
        handoff_date = latest(head_lines, today) or latest("\n\n".join(strip_fenced(b) for b in blocks), today)
    else:
        handoff_date = None

    if handoff_date is not None:
        h003_ok = bool(sec3_date and sec3_date >= handoff_date - timedelta(days=days))
        h003_detail = f"§3 {sec3_date} vs STATUS 最新交接 {handoff_date}" if sec3_date else sec3_missing_msg
    else:
        h003_ok = bool(sec3_date and sec3_date >= today - timedelta(days=days))
        h003_detail = (
            f"§3 {sec3_date} vs today {today}（STATUS 无交接，退回与今天比）"
            if sec3_date
            else sec3_missing_msg
        )
    add("H003", f"§3 日期未落后最新交接超 {days} 天", h003_ok, h003_detail)

    match = re.search(r"(?im)^[^\n]*TL;DR[^\n]*.*?(?=^---\s*$|^##\s|\Z)", agents, re.DOTALL)
    tldr = match.group(0) if match else ""
    tldr_unfilled = not tldr.strip() or bool(PLACEHOLDER_RE.search(tldr) or EMPTY_TLDR_FIELD_RE.search(tldr))
    add("H004", "TL;DR 已填（非占位符）", not tldr_unfilled,
        "已填" if not tldr_unfilled else "缺失或仍含占位符")

    h005_ok, h005_detail = check_status_h005(status, today)
    add("H005", "STATUS.md 存在且非模板", h005_ok, h005_detail)

    # 交接标题：## 或 ###，含 Handoff/交接，或以日期 / T<卡号>+日期 开头（“交回说明”“归档说明”等不算）
    status_unfenced = strip_fenced(status)
    non_arch_lines = "\n".join(
        ln for ln in status_unfenced.splitlines()
        if not (re.match(r"^\s*#{1,6}\s+", ln) and re.search(r"归档|archive", ln, re.I))
    )
    status_date = handoff_date or latest(non_arch_lines, today)
    h006_ok = bool(status_date and sec3_date and status_date >= sec3_date)
    if h006_ok:
        h006_detail = f"STATUS {status_date} vs §3 {sec3_date}"
    else:
        st_valid, st_invalid = scan_dates(non_arch_lines)
        st_future = [d for d in st_valid if d > today]
        if status_date is None and sec3_date is None:
            h006_detail = f"STATUS 未读出有效交接日期，且 {sec3_missing_msg}"
        elif status_date is None:
            if not status.strip():
                h006_detail = f"STATUS.md 不存在或为空（vs §3 {sec3_date}）"
            elif st_future:
                h006_detail = f"STATUS 日期晚于 today（{st_future[0]} > {today}，vs §3 {sec3_date}）"
            elif st_invalid:
                h006_detail = f"STATUS 含非法日历日期「{st_invalid[0]}」（vs §3 {sec3_date}）"
            elif blocks:
                h006_detail = f"STATUS 已识别 {len(blocks)} 段交接但无有效日期（vs §3 {sec3_date}）"
            else:
                h006_detail = f"STATUS 未找到交接段或有效日期（vs §3 {sec3_date}）"
        elif sec3_date is None:
            h006_detail = f"{sec3_missing_msg}（STATUS 最新交接 {status_date}）"
        else:
            h006_detail = f"STATUS 最新交接日期落后于 §3（STATUS {status_date} < §3 {sec3_date}）"
    add("H006", "STATUS 最新交接日期 >= §3 日期", h006_ok, h006_detail)

    pointers = [root / n for n in ("CLAUDE.md", "GEMINI.md", ".cursorrules", ".github/copilot-instructions.md")]
    if (root / ".cursor" / "rules").is_dir():
        pointers += sorted((root / ".cursor" / "rules").glob("*.mdc"))
    existing = [p for p in pointers if p.is_file()]
    valid = [p.relative_to(root).as_posix() for p in existing if pointer_ok(read(p))]
    add("H007", "薄指针至少一个指向 AGENTS.md", not existing or bool(valid),
        ", ".join(valid) if valid else ("未生成薄指针" if not existing else "没有有效指针"))

    sec4 = section(agents, "4", {"任务看板", "下一步任务看板", "Next Task Board"})
    sec4_unfenced = strip_fenced(sec4)
    all_box_lines = re.findall(r"(?m)^\s*[-*]\s*\[[ xX]?\].*$", sec4_unfenced)
    real_box_lines = [ln for ln in all_box_lines if not is_template_task_line(ln)]
    h008_detail = (
        f"{len(real_box_lines)} 行任务"
        if real_box_lines
        else ("仅含模板占位行，请替换为真实任务" if all_box_lines else "未找到任务行")
    )
    add("H008", "§4 看板存在且有任务行", bool(real_box_lines), h008_detail)

    tldr_real_lines = strip_placeholder_spans(strip_fenced(tldr))
    tldr_date = latest(tldr_real_lines, today)
    conflict = bool(tldr_date and sec3_date and tldr_date < sec3_date - timedelta(days=1))
    h009_rhs = f"§3 {sec3_date}" if sec3_date else (sec3_missing_msg if sec3_is_placeholder else "§3 None")
    add("H009", "TL;DR 日期与 §3 不矛盾", not conflict, f"TL;DR {tldr_date} vs {h009_rhs}")

    advisories(root, agents, status, sec4, blocks, today)


def advisories(root: Path, agents: str, status: str, sec4: str, blocks: list[str], today: date) -> None:
    registry = "决策登记表" in agents or "决策登记表" in status or (root / "文档" / "决策登记表.md").is_file()
    add("A001", "决策登记表存在", registry, "" if registry else "具约束力的决策应收口到一张可 grep 的表", True)

    const_re = re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*=\s*(\{[^{}]*\}|\[[^\[\]]*\])([^\n]*)$", re.M)
    seen: dict[str, dict[tuple[str, ...], list[str]]] = {}
    scripts = root / "scripts"
    for fp in sorted(scripts.rglob("*.py")) if scripts.is_dir() else []:
        script_text = read(fp)
        for m in const_re.finditer(script_text):
            cname, cbody, ctail = m.group(1), m.group(2), m.group(3)
            full_stmt = m.group(0)
            if re.search(r"#\s*(?:noqa(?:\s*:\s*A002)?|a002\s*:\s*ignore|check_handoff\s*:\s*ignore)\b", full_stmt, re.I):
                continue
            if DISPLAY_CONST_RE.search(cname):
                continue
            members = tuple(sorted(re.findall(r"['\"]([^'\"]+)['\"]", cbody)))
            if not members:
                continue
            if all(HEX_COLOR_RE.match(x) for x in members):
                continue
            if cbody.lstrip().startswith("{") and ":" in cbody:
                dict_vals = re.findall(r":\s*['\"]([^'\"]+)['\"]", cbody)
                if dict_vals and len(dict_vals) == cbody.count(":") and all(HEX_COLOR_RE.match(v) for v in dict_vals):
                    continue
            rel_name = fp.relative_to(scripts).as_posix()
            seen.setdefault(cname, {}).setdefault(members, []).append(rel_name)
    drift_consts = [f"{name}: {list(v.values())}" for name, v in seen.items() if len(v) > 1]
    add("A002", "多脚本同名常量集合一致", not drift_consts, "; ".join(drift_consts), True)

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

    sec4_unfenced = strip_fenced(sec4)
    all_box_lines = re.findall(r"(?m)^\s*[-*]\s*\[[ xX]?\].*$", sec4_unfenced)
    real_box_lines = [ln for ln in all_box_lines if not is_template_task_line(ln)]
    tpl_box_cnt = len(all_box_lines) - len(real_box_lines)
    checked = sum(1 for ln in real_box_lines if re.match(r"^\s*[-*]\s*\[[xX]\]", ln))
    unchecked = len(real_box_lines) - checked
    a004_ok = checked > 0 or (not real_box_lines and not tpl_box_cnt)
    a004_detail = f"{checked} 勾 / {unchecked} 未勾" + (f"（忽略 {tpl_box_cnt} 行模板占位）" if tpl_box_cnt else "")
    add("A004", "§4 看板至少勾了一项", a004_ok, a004_detail, True)

    cards_dir = root / "文档" / "任务卡"
    cards_dir_exists = cards_dir.is_dir()
    cards = sorted(cards_dir.glob("*.md")) if cards_dir_exists else []
    active_cards: list[tuple[Path, str]] = []
    unparsed_cards: list[str] = []
    lacking: list[str] = []
    for fp in cards:
        text = read(fp)
        st_mark = single_card_state(text)
        if st_mark is None:
            unparsed_cards.append(fp.name)
        elif st_mark in CLOSED:
            continue
        active_cards.append((fp, text))
        heads = PROMPT_HEAD_RE.findall(strip_fenced(text))
        if not (any("执行" in h for h in heads) and any("复核" in h for h in heads)):
            lacking.append(fp.name)
    closed_cnt = len(cards) - len(active_cards)
    unparsed_note = (
        f"（其中状态行无法解析、暂按在用卡检查：{'、'.join(unparsed_cards[:5])}）"
        if unparsed_cards
        else ""
    )
    skip_note = (
        f"{len(active_cards)} 张在用卡（跳过 {closed_cnt} 张收口/作废）{unparsed_note}"
        if closed_cnt
        else (f"{len(active_cards)} 张卡{unparsed_note}" if cards else "无任务卡（未检查）")
    )
    add("A005", "任务卡同时带执行方和独立复核方提示词", not lacking,
        (f"{len(lacking)} 张缺：" + "、".join(lacking[:5]) + ("…" if len(lacking) > 5 else "")
         + unparsed_note
         + "；一个任务一张卡，复核写在同一张卡里（已收口 ✅ 与作废 🗄️ 卡不查）") if lacking else skip_note, True)

    bloated = []
    for fp, text in active_cards:
        size = len(text.encode("utf-8"))
        prompts = len(PROMPT_HEAD_RE.findall(strip_fenced(text)))
        if size > 15_000:
            bloated.append(f"{fp.name}（{size // 1000}KB，{prompts} 段提示词；最大三节：{top_card_sections(text)}）")
        elif prompts > 3:
            bloated.append(f"{fp.name}（{size // 1000}KB，{prompts} 段提示词）")
    add("A006", "任务卡 ≤15KB、提示词段 ≤3", not bloated,
        (f"{len(bloated)} 张在用卡超限（跳过 {closed_cnt} 张收口/作废）{unparsed_note}：" + "；".join(bloated[:6])
         + ("…" if len(bloated) > 6 else "")
         + "；超限部分该挪到 STATUS 或开新卡，就地改并删用过的提示词（见 任务卡_README.md 卡面规矩）")
        if bloated else skip_note, True)

    states = card_states(cards)
    sec3 = section(agents, "3", {"现在在哪", "Where We Are Now"})
    drift = []
    for row in (ln for ln in index.splitlines() if ln.lstrip().startswith("|")):
        cells = [c.strip(" *`") for c in row.strip().strip("|").split("|")]
        for cid, (state, name) in states.items():
            mark = STATE_RE.search("|".join(cells[1:]))
            if (cells[0] == cid or name in row) and mark and (mark.group(0) in CLOSED) != (state in CLOSED):
                drift.append(f"{cid} 卡面 {state}／索引 {mark.group(0)}")
    drift.extend(sec4_card_drifts(sec4, states))
    a007_issues: list[str] = []
    if unparsed_cards:
        a007_issues.append(
            "状态行无法解析：" + "、".join(unparsed_cards[:5]) + ("…" if len(unparsed_cards) > 5 else "")
        )
    if drift:
        a007_issues.append("；".join(drift[:6]) + ("…" if len(drift) > 6 else ""))
    add("A007", "卡面状态与 §4 看板、任务卡索引一致（只比收口与否）", not a007_issues,
        ("；".join(a007_issues) + "；对不上以卡面为准，主控收口时同步 §4 与索引")
        if a007_issues else (f"{len(states)} 张卡有“进度回写”" if cards else "无任务卡（未检查）"), True)

    items = [ln for ln in sec3.splitlines() if re.match(r"^[-*]\s+(?!`?→)", ln)]
    stale = sorted({cid for ln in sec3.splitlines() if re.search(r"待审查|待复核|待收口|已交回|🟡|🔵", ln)
                    for cid in [subject_card(ln, states)] if cid and states[cid][0] in CLOSED})
    add("A008", "§3 ≤5 条、不挂已收口卡的“待审查”", len(items) <= 5 and not stale,
        f"§3 {len(items)} 条" + (f"；卡面已收口仍挂待审查：{'、'.join(stale)}" if stale else "")
        + ("；§3 只留 1–5 条累计快照，旧条移到归档" if len(items) > 5 or stale else ""), True)

    long_rows = []
    for fp, text in active_cards:
        body = progress_section_unfenced(text)
        long_rows += [f"{fp.name}「{re.split('[:：]', ln.strip().lstrip('-* '))[0][:12]}」行 {len(ln.strip())} 字"
                      for ln in body.splitlines() if re.match(r"^\s*[-*]\s", ln) and len(ln.strip()) > 400]
    add("A009", "“进度回写”每行 ≤400 字", not long_rows,
        ("；".join(long_rows[:4]) + ("…" if len(long_rows) > 4 else "")
         + (f"（跳过 {closed_cnt} 张收口/作废）" if closed_cnt else "")
         + unparsed_note
         + "；一句话结果之外的细节写进 STATUS 或结果说明") if long_rows else skip_note, True)

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

    if not blocks:
        add("A011", "STATUS 最近 5 段交接 ≤800 字且四节齐", False,
            "未找到交接段（仅认 ## 或 ### 标题，#### 及更深标题不算；须含 Handoff/交接，或以日期 / T<卡号>+日期 开头；“交回说明”等不算交接）", True)
    else:
        d_first = latest(blocks[0].splitlines()[0], today) or latest(blocks[0], today)
        d_last = latest(blocks[-1].splitlines()[0], today) or latest(blocks[-1], today)
        rev_order = bool(d_first and d_last and d_first > d_last)
        recent_blocks = blocks[:5] if rev_order else blocks[-5:]
        bad_segs: list[str] = []
        for seg in recent_blocks:
            seg_title = seg.splitlines()[0].lstrip("#").strip()[:36]
            seg_len = len(seg.strip())
            unfence_seg = strip_fenced(seg)
            missing_secs = [label for label, pat in HANDOFF_SECTIONS if not pat.search(unfence_seg)]
            if seg_len > 800 or missing_secs:
                seg_issues = [f"{seg_len} 字" + ("（超 800 字）" if seg_len > 800 else "")]
                if missing_secs:
                    seg_issues.append("缺节：" + "、".join(missing_secs))
                bad_segs.append(f"「{seg_title}」" + "，".join(seg_issues))
        latest_seg = recent_blocks[0] if rev_order else recent_blocks[-1]
        latest_len = len(latest_seg.strip())
        a011_ok = not bad_segs
        if a011_ok:
            a011_detail = f"最近 {len(recent_blocks)} 段均合规（最新 {latest_len} 字，四节齐）"
        else:
            a011_detail = (
                f"最近 {len(recent_blocks)} 段中 {len(bad_segs)} 段不合规："
                + "；".join(bad_segs)
                + "；须含“改了什么 / 怎么验证的 / 没做什么 / 不确定处”四节且 ≤800 字"
            )
        add("A011", "STATUS 最近 5 段交接 ≤800 字且四节齐", a011_ok, a011_detail, True)

    review_files = collect_review_files(root)
    checked_reviews: list[Path] = []
    skipped_reviews = 0
    bad_reviews: list[str] = []
    for fp in review_files:
        rcid = review_card_id(fp, states)
        if rcid is not None and states[rcid][0] in CLOSED:
            skipped_reviews += 1
            continue
        checked_reviews.append(fp)
        non_empty = [ln.strip() for ln in read(fp).splitlines() if ln.strip()]
        if not non_empty or non_empty[-1] not in ("PASS", "NEEDS_FIX"):
            bad_reviews.append(fp.name)
    if not review_files:
        a012_ok_detail = "暂无复核报告"
    elif skipped_reviews:
        a012_ok_detail = f"{len(checked_reviews)} 份复核报告（跳过 {skipped_reviews} 份收口/作废卡报告）"
    else:
        a012_ok_detail = f"{len(checked_reviews)} 份复核报告"
    add("A012", "复核报告末尾有单独一行 PASS 或 NEEDS_FIX", not bad_reviews,
        (f"{len(bad_reviews)} 份缺结论行"
         + (f"（已跳过 {skipped_reviews} 份收口/作废卡报告）" if skipped_reviews else "")
         + "：" + "、".join(bad_reviews[:5]) + ("…" if len(bad_reviews) > 5 else "")
         + "；复核报告末尾须单独一行只写 PASS 或 NEEDS_FIX")
        if bad_reviews else a012_ok_detail, True)

    a013_ok, a013_detail = check_decision_chain_a013(agents)
    add("A013", "§3.5 决策登记表无重复 ID 且取代链自洽", a013_ok, a013_detail, True)

    a014_ok, a014_detail = check_agents_placeholders_a014(agents)
    add("A014", "AGENTS.md 无遗留【待填】且“不可混用的维度”已填", a014_ok, a014_detail, True)

    if not cards_dir_exists:
        a015_ok, a015_detail = False, "未找到 文档/任务卡/ 目录，卡类检查（A005—A009）均未执行"
    elif not cards:
        a015_ok, a015_detail = False, "文档/任务卡/ 下有 0 张任务卡，卡类检查（A005—A009）均未执行"
    else:
        a015_ok, a015_detail = True, f"{len(cards)} 张任务卡"
    add("A015", "任务卡目录存在且非空", a015_ok, a015_detail, True)


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
    sec4_unfenced = strip_fenced(sec4)
    for line_match in re.finditer(r"(?m)^\s*[-*]\s*\[([ xX]?)\](.*)$", sec4_unfenced):
        sub_parts = re.split(r"\s+[-*]\s*\[([ xX]?)\]", line_match.group(2))
        sub_items = [(line_match.group(1), sub_parts[0])]
        for k in range(1, len(sub_parts), 2):
            sub_items.append((sub_parts[k], sub_parts[k + 1]))

        for box, body in sub_items:
            if is_template_task_line(f"- [{box}]{body}"):
                continue
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


def progress_section_unfenced(text: str) -> str:
    """Return unfenced, uncommented lines inside the '## 进度回写' section of a task card."""
    cleaned = strip_fenced_and_html_comments(text)
    lines = cleaned.splitlines()
    start: Optional[int] = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s*进度回写", ln):
            start = i
            break
    if start is None:
        return ""
    end = next(
        (j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start + 1 : end])


def single_card_state(text: str) -> Optional[str]:
    body = progress_section_unfenced(text)
    line = CARD_STATE_LINE_RE.search(body)
    mark = STATE_RE.search(line.group(1)) if line else None
    return mark.group(0) if mark else None


def card_states(cards: list[Path]) -> dict[str, tuple[str, str]]:
    """卡号（文件名第一个 _ 之前，或无下划线时的前缀编号）→（“进度回写”节里“状态：”行的第一个状态符号, 文件名）。"""
    states = {}
    for fp in cards:
        mark = single_card_state(read(fp))
        if mark:
            states[extract_card_id(fp.stem)] = (mark, fp.name)
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
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
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
    warned = 0
    for code, name, ok, detail, advisory in findings:
        mark = "✅ PASS" if ok else ("⚠️ WARN" if advisory else "❌ FAIL")
        if not ok:
            if advisory:
                warned += 1
            else:
                failed += 1
        print(f"  [{code}] {mark}  {name}" + (f"\n             {detail}" if detail else ""))
    print("=" * 60)
    if failed == 0 and warned == 0:
        print("  0 项失败，0 条提示（全部通过）。")
    elif failed == 0:
        print(f"  0 项失败，{warned} 条提示。")
    else:
        print(f"  {failed} 项失败，{warned} 条提示。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

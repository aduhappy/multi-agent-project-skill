#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_handoff.py — 收工交接自检（multi-agent-project skill 配套）

用法：
    python scripts/check_handoff.py                                  # 以当前目录为线级项目根（默认 --role controller）
    python scripts/check_handoff.py PATH --days 30                   # 指定根、放宽新鲜度窗口
    python scripts/check_handoff.py PATH --scope index               # 多线课题的根索引
    python scripts/check_handoff.py PATH --role executor --card T13d # 执行方/复核方收工自检（跳过 AGENTS.md）
    python scripts/check_handoff.py --version                        # 查看脚本版本号

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

退出码：0 = 没有阻断项失败；1 = 有阻断项失败；2 = 根目录不存在或缺依赖模块。
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

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    import handoff_lib as hl
    from handoff_lib import handoff_blocks, pointer_ok, section  # noqa: F401
except ImportError:
    print("错误：未找到 handoff_lib.py，请把 handoff_lib.py 一起复制到同一目录。", file=sys.stderr)
    raise SystemExit(2)

DISPLAY_CONST_RE = re.compile(
    r"(?:^|_)(?:COLORS?|PALETTES?|CMAPS?|COLORMAPS?|STYLES?|FONTS?|MARKERS?|HATCH(?:ES)?|LINESTYLES?|ALPHAS?|SIZES?|WIDTHS?)$"
)
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$")
SKIP_REVIEW_DIRS = {"决策记录", "原始资料", "_作废", "归档"}

findings: list[tuple[str, str, bool, str, bool]] = []  # code, name, ok, detail, advisory


def add(code: str, name: str, ok: bool, detail: str = "", advisory: bool = False) -> None:
    findings.append((code, name, ok, detail, advisory))


def _is_unfilled_placeholder_value(val: str) -> bool:
    """True when a non-empty field value is still a template prompt or consists solely of placeholder spans."""
    if not val:
        return False
    if hl.STATUS_TEMPLATE_PROMPT_RE.search(val):
        return True
    return not hl.strip_placeholder_spans(val).strip(" \t—–-:：;；,，。/|.·()（）[]【】<>")


def check_status_h005(status: str, today: date) -> tuple[bool, str]:
    if not status.strip():
        return False, "STATUS.md 不存在或为空"

    doc = hl.parse_markdown(status)
    active_blocks = [
        b
        for b in doc.blocks
        if b.kind != "fenced_code" and (not hl._STATUS_SKIP_COMMENTED_HEADINGS or b.kind != "html_comment")
    ]
    unfenced_text = "\n".join(
        b.raw_text if not hl._STATUS_SKIP_COMMENTED_HEADINGS else b.visible_text(include_code=True)
        for b in active_blocks
    )

    reasons: list[str] = []
    if len(status.strip()) <= 50:
        reasons.append(f"内容过短（{len(status.strip())} 字，需 >50 字）")

    all_valid, invalid_tokens = hl.scan_dates(unfenced_text)
    le_today = [d for d in all_valid if d <= today]
    future_dates = [d for d in all_valid if d > today]
    if not le_today:
        if future_dates:
            reasons.append(f"缺少不晚于 today（{today}）的真实日期（仅检测到未来日期 {future_dates[0]}）")
        elif invalid_tokens:
            reasons.append(f"缺少有效真实日期（检测到非法日历日期「{invalid_tokens[0]}」）")
        else:
            reasons.append("未找到真实日期（支持 YYYY-MM-DD、YYYY/MM/DD、YYYY.MM.DD、YYYY年MM月DD日）")

    for b in active_blocks:
        if b.kind == "heading" and b.level >= 2:
            no_code = b.non_code_text().strip()
            has_real_date = bool(hl.scan_dates(no_code)[0])
            if hl.DATE_PLACEHOLDER_RE.search(no_code) and not has_real_date:
                reasons.append(f"标题仍含日期占位符「{b.title[:28]}」")
            elif hl.STATUS_FIELD_PLACEHOLDER_RE.search(no_code) and not has_real_date:
                reasons.append(f"标题仍含模板占位符「{b.title[:28]}」")
            continue

        if b.kind == "indented_code":
            continue

        raw_lines = b.lines if not hl._STATUS_SKIP_COMMENTED_HEADINGS else b.visible_lines(include_code=True)
        nocode_lines = b.visible_lines(include_code=False)
        for ln_raw, ln_nc in zip(raw_lines, nocode_lines):
            snap_m = re.match(
                r"^\s*>\s*\**(阶段|当前阶段|底座(?:/关键数字)?|关键数字|唯一闸门(?:/阻塞)?|阻塞)\**\s*[:：]\s*(.*)$",
                ln_nc,
            )
            if snap_m:
                val = snap_m.group(2).strip()
                if not val or _is_unfilled_placeholder_value(val):
                    reasons.append(f"“现状”行「{snap_m.group(1)}」仍为占位符或未填")
                continue

            if re.match(r"^\s*[-*+]\s*(?:【待填[^】]*】|\[TODO\]|<TODO>|YYYY[-/.]MM[-/.]DD)\s*$", ln_raw, re.I):
                reasons.append("交接条目仍为未填模板占位符")
                continue

            fld_m = re.match(
                r"^\s*(?:[-*+]|\d+[.)])?\s*\**(谁做的|改了什么|怎么验证(?:的)?|没做什么|不确定处|本次做了什么)\**\s*[:：]\s*(.*)$",
                ln_nc,
            )
            if fld_m:
                raw_val = fld_m.group(2).strip()
                if _is_unfilled_placeholder_value(raw_val):
                    reasons.append(f"交接字段「{fld_m.group(1)}」仍含模板占位符")

    if not reasons:
        return True, "已填"
    dedup: list[str] = []
    for r in reasons:
        if r not in dedup:
            dedup.append(r)
    return False, "；".join(dedup[:4])


def collect_review_files(root: Path, cfg: hl.HandoffConfig) -> list[Path]:
    found: list[Path] = []
    seen_paths: set[Path] = set()
    cards_resolved = (root / cfg.cards_dir).resolve()
    for sub in cfg.review_dirs:
        base = root / sub
        if not base.is_dir():
            continue
        for fp in sorted(base.rglob("*.md")):
            fp_res = fp.resolve()
            if fp_res in seen_paths:
                continue
            if fp_res.parent == cards_resolved or cards_resolved in fp_res.parents:
                continue
            rel_parts = fp.relative_to(base).parts[:-1]
            if any(
                p in SKIP_REVIEW_DIRS or p.startswith("_") or p.endswith("_DEPRECATED")
                for p in rel_parts
            ):
                continue
            if fp.stem.endswith("_DEPRECATED"):
                continue
            if "复核" in fp.stem:
                seen_paths.add(fp_res)
                found.append(fp)
    return found


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
    tables = hl.parse_decision_tables(agents, all_sections=False)
    if not tables:
        doc = hl.parse_markdown(agents)
        has_sec = any(
            b.kind == "heading"
            and b.level in (2, 3)
            and (re.match(r"^3\.5(?:\.(?!\d)|\s|$)", b.title) or "决策登记表" in b.title)
            for b in doc.blocks
        )
        return (True, "0 条已登记决策") if has_sec else (True, "未设 §3.5 表")

    rows = [r for tbl in tables for r in tbl.rows]
    if not rows:
        return True, "0 条已登记决策"

    issues: list[str] = []
    seen_ids: dict[str, int] = {}
    by_id: dict[str, hl.DecisionRow] = {}
    for r in rows:
        seen_ids[r.norm_id] = seen_ids.get(r.norm_id, 0) + 1
        if seen_ids[r.norm_id] == 2:
            issues.append(f"重复 ID：{r.disp_id}")
        by_id.setdefault(r.norm_id, r)

    for tbl in tables:
        if not (tbl.has_status_col and tbl.has_replaced_by_col):
            continue
        reported_pairs: set[tuple[str, str]] = set()
        for r in tbl.rows:
            is_rep_by_empty = r.raw_replaced_by.strip(" *`").lower() in hl.EMPTY_CELL_VALUES
            if r.status == "SUPERSEDED" and not r.replaced_by_ids:
                issues.append(f"{r.disp_id} 为 SUPERSEDED 但未填“被谁取代”")
            elif r.status == "ACTIVE" and not is_rep_by_empty:
                issues.append(f"{r.disp_id} 为 ACTIVE 但填了“被谁取代”（{r.raw_replaced_by}）")

            if tbl.has_replaces_col:
                for target in r.replaces_ids:
                    if target not in by_id:
                        continue  # 乙不在表内（已迁出）不报
                    tr = by_id[target]
                    if tr.status != "SUPERSEDED" or r.norm_id not in tr.replaced_by_ids:
                        reported_pairs.add((r.norm_id, target))
                        issues.append(
                            f"{r.disp_id}／{tr.disp_id}（{r.disp_id} 写取代 {tr.disp_id}，但 {tr.disp_id} 状态={tr.status or '空'}、被谁取代={tr.raw_replaced_by or '空'}）"
                        )
                if r.status == "SUPERSEDED":
                    for newer in r.replaced_by_ids:
                        if newer not in by_id or (newer, r.norm_id) in reported_pairs:
                            continue
                        nr = by_id[newer]
                        if r.norm_id not in nr.replaces_ids:
                            reported_pairs.add((newer, r.norm_id))
                            issues.append(
                                f"{nr.disp_id}／{r.disp_id}（{r.disp_id} 写被 {nr.disp_id} 取代，但 {nr.disp_id} 取代了谁={nr.raw_replaces or '空'}）"
                            )

    if issues:
        return False, f"{len(issues)} 处不一致：" + "；".join(issues[:6]) + ("…" if len(issues) > 6 else "")
    return True, f"{len(rows)} 条决策链自洽"


def check_agents_placeholders_a014(agents: str) -> tuple[bool, str]:
    doc = hl.parse_markdown(agents)
    cur_sec = "顶部/TL;DR"
    sec_order: list[str] = [cur_sec]
    sec_counts: dict[str, int] = {cur_sec: 0}

    for b in doc.blocks:
        if b.kind == "fenced_code":
            continue
        if b.kind == "heading" and b.level == 2 and b.indent == 0:
            m_num = re.match(r"^(\d+(?:\.\d+)?)\b", b.title)
            cur_sec = f"§{m_num.group(1)}" if m_num else b.title[:14]
            if cur_sec not in sec_counts:
                sec_order.append(cur_sec)
                sec_counts[cur_sec] = 0
            sec_counts[cur_sec] += b.raw_text.count("【待填")
        else:
            sec_counts[cur_sec] += b.raw_text.count("【待填")

    non_zero = [(s, sec_counts[s]) for s in sec_order if sec_counts[s] > 0]
    total = sum(c for _, c in non_zero)

    sec5_blocks = hl.extract_section_blocks(doc, "5", {"铁律 / 约定", "铁律/约定", "铁律"})
    dim_unfilled = False
    for b in sec5_blocks[1:]:
        if b.kind in ("fenced_code", "html_comment"):
            continue
        b_txt = b.visible_text(include_code=True)
        if re.search(r"不可混用的?维度", b_txt):
            if hl.PLACEHOLDER_RE.search(b_txt):
                dim_unfilled = True
            else:
                cleaned = re.sub(
                    r"^[-*+]\s*\**不可混用的?维度\**(?:（[^）]*）|\([^)]*\))?\s*[:：]?\s*",
                    "",
                    b_txt,
                ).strip()
                if not cleaned:
                    dim_unfilled = True
            break

    if total == 0 and not dim_unfilled:
        return True, ""

    parts: list[str] = []
    if total > 0:
        parts.append(f"剩余 {total} 处【待填】（" + "、".join(f"{s}: {c}" for s, c in non_zero) + "）")
    if dim_unfilled:
        parts.append("§5“不可混用的维度”尚未填写")
    return False, "；".join(parts)


def card_re(cid: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9-]){re.escape(cid)}(?![A-Za-z0-9-])")


def subject_card(line: str, states: dict[str, tuple[str, str]]) -> Optional[str]:
    """这一条说的是哪张卡：第一段加粗里最先出现的卡号；没有加粗才看整行。"""
    bold = re.search(r"\*\*(.+?)\*\*", line)
    text = bold.group(1) if bold else line
    hits = [(m.start(), cid) for cid in states for m in [card_re(cid).search(text)] if m]
    return min(hits)[1] if hits else None


def _mask_parens_for_sec4(text: str, states: dict[str, tuple[str, str]]) -> str:
    """屏蔽括号内的依赖/接续说明（如“（依赖 T10）”“（由 T12g 接续）”），保留纯状态括号（如“（✅）”）。"""
    def _repl(m: re.Match[str]) -> str:
        inner = m.group(0)
        if hl.GENERIC_TASK_RE.search(inner) or any(card_re(cid).search(inner) for cid in states):
            return " " * len(inner)
        return "".join(ch if hl.STATE_RE.match(ch) else " " for ch in inner)

    return re.sub(r"（[^（）]*）|\([^()]*\)", _repl, text)


def _sec4_item_groups(body: str, states: dict[str, tuple[str, str]]) -> tuple[str, list[tuple[int, int, list[str]]]]:
    """提取单条 §4 勾选子句中的卡号组 [(start, end, [cid, ...]), ...]。"""
    masked = _mask_parens_for_sec4(body, states)
    bold_spans = [m.span() for m in re.finditer(r"\*\*(.+?)\*\*", masked)]

    def _in_bold(pos: int) -> bool:
        return any(bs <= pos < be for bs, be in bold_spans)

    def _allowed_unbolded(start: int) -> bool:
        prev_seps = [m.end() for m in hl.CLAUSE_SEP_RE.finditer(masked[:start])]
        clause_start = prev_seps[-1] if prev_seps else 0
        prefix_in_clause = masked[clause_start:start]
        if re.fullmatch(r"[\s🟠⬜⏳🟡🔵✅⛔🗄\ufe0f]*", prefix_in_clause):
            return True
        if not bold_spans and re.search(r"[🟠⬜⏳🟡🔵✅⛔🗄]\ufe0f?\s*$", masked[:start]):
            return True
        return False

    raw_hits: list[tuple[int, int, list[str]]] = []
    for m in hl.SLASH_CARDS_RE.finditer(masked):
        s, e = m.span()
        if _in_bold(s) or _allowed_unbolded(s):
            base = m.group(1)
            raw_hits.append((s, e, [f"{base}{ch}" for ch in m.group(2).split("/")]))

    for cid in sorted(states, key=len, reverse=True):
        for m in card_re(cid).finditer(masked):
            s, e = m.span()
            if _in_bold(s) or _allowed_unbolded(s):
                raw_hits.append((s, e, [cid]))

    for m in hl.GENERIC_TASK_RE.finditer(masked):
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


def sec4_card_drifts(board_items: list[hl.BoardItem], states: dict[str, tuple[str, str]]) -> list[str]:
    """核对 §4 看板与卡面收口状态：单卡行看行首勾选框；一行多卡时优先看各卡同子句的内联状态符号。"""
    drifts: list[str] = []
    for item in board_items:
        for box_done, body_raw, body_nc in item.sub_items:
            if hl.is_template_task_body(body_raw):
                continue
            masked, groups = _sec4_item_groups(body_nc, states)
            if not groups:
                continue
            if sum(len(g[2]) for g in groups) <= 1:
                cid = groups[0][2][0]
                if cid in states and box_done != (states[cid][0] in hl.CLOSED):
                    drifts.append(f"{cid} 卡面 {states[cid][0]}／§4 {'已勾' if box_done else '未勾'}")
                continue

            for idx, (s, e, cids) in enumerate(groups):
                next_s = groups[idx + 1][0] if idx + 1 < len(groups) else len(masked)
                after = masked[e:next_s]
                if idx + 1 < len(groups):
                    sep = hl.CLAUSE_SEP_RE.search(after)
                    own_after = after[: sep.start()] if sep else after
                else:
                    own_after = after
                mark_m = hl.STATE_RE.search(own_after)
                if not mark_m:
                    prev_e = groups[idx - 1][1] if idx > 0 else 0
                    before = masked[prev_e:s]
                    if idx == 0:
                        own_before = before
                    else:
                        seps = list(hl.CLAUSE_SEP_RE.finditer(before))
                        own_before = before[seps[-1].end() :] if seps else ""
                    mark_m = hl.STATE_RE.search(own_before)

                for cid in cids:
                    if cid not in states:
                        continue
                    card_st = states[cid][0]
                    if mark_m:
                        inline_st = mark_m.group(0)
                        if (inline_st in hl.CLOSED) != (card_st in hl.CLOSED):
                            drifts.append(f"{cid} 卡面 {card_st}／§4 {inline_st}")
                    elif box_done != (card_st in hl.CLOSED):
                        drifts.append(f"{cid} 卡面 {card_st}／§4 {'已勾' if box_done else '未勾'}")
    return drifts


def card_states(cards: list[Path]) -> dict[str, tuple[str, str]]:
    """卡号 → （“进度回写”节里“状态：”行的状态符号, 文件名）。"""
    states: dict[str, tuple[str, str]] = {}
    for fp in cards:
        mark = hl.parse_card_state(hl.read_utf8(fp))
        if mark:
            states[hl.extract_card_id(fp.stem)] = (mark, fp.name)
    return states


def line_checks(root: Path, cfg: hl.HandoffConfig, days: int, today: date) -> None:
    agents = hl.read_utf8(root / "AGENTS.md")
    status = hl.read_utf8(root / "STATUS.md")
    agents_doc = hl.parse_markdown(agents)

    add("H001", "AGENTS.md 存在且非空", len(agents.strip()) > 100, f"{len(agents)} chars" if agents else "missing")
    declared_index = any(
        re.match(r"^>\s*\*\*Scope[:：]\s*index\*\*", ln)
        for b in agents_doc.blocks
        if b.kind == "paragraph"
        for ln in b.lines
    )
    add("H002", "线级入口未声明为根索引", not declared_index, "请改用 --scope index" if declared_index else "line scope")

    s3 = hl.extract_sec3_info(agents, today)
    sec3_date = s3.latest_date
    sec3_is_placeholder = s3.is_placeholder
    sec3_missing_msg = s3.missing_msg

    blocks = hl.handoff_blocks(status)
    handoff_date = hl.handoffs_latest_date(blocks, today)

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

    tldr_info = hl.extract_tldr_info(agents, today)
    add(
        "H004",
        "TL;DR 已填（非占位符）",
        not tldr_info.unfilled,
        "已填" if not tldr_info.unfilled else "缺失或仍含占位符",
    )

    h005_ok, h005_detail = check_status_h005(status, today)
    add("H005", "STATUS.md 存在且非模板", h005_ok, h005_detail)

    fb_date, st_valid, st_invalid, _ = hl.status_fallback_scan(status, today)
    status_date = handoff_date or fb_date
    h006_ok = bool(status_date and sec3_date and status_date >= sec3_date)
    if h006_ok:
        h006_detail = f"STATUS {status_date} vs §3 {sec3_date}"
    else:
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
    valid = [p.relative_to(root).as_posix() for p in existing if pointer_ok(hl.read_utf8(p))]
    add(
        "H007",
        "薄指针至少一个指向 AGENTS.md",
        not existing or bool(valid),
        ", ".join(valid) if valid else ("未生成薄指针" if not existing else "没有有效指针"),
    )

    board_items = hl.parse_board_items(agents)
    real_board_items = [it for it in board_items if not it.is_template]
    h008_detail = (
        f"{len(real_board_items)} 行任务"
        if real_board_items
        else ("仅含模板占位行，请替换为真实任务" if board_items else "未找到任务行")
    )
    add("H008", "§4 看板存在且有任务行", bool(real_board_items), h008_detail)

    tldr_date = tldr_info.latest_date
    conflict = bool(tldr_date and sec3_date and tldr_date < sec3_date - timedelta(days=1))
    h009_rhs = f"§3 {sec3_date}" if sec3_date else (sec3_missing_msg if sec3_is_placeholder else "§3 None")
    add("H009", "TL;DR 日期与 §3 不矛盾", not conflict, f"TL;DR {tldr_date} vs {h009_rhs}")

    advisories(root, cfg, agents, agents_doc, s3, board_items, status, blocks, today)


def advisories(
    root: Path,
    cfg: hl.HandoffConfig,
    agents: str,
    agents_doc: hl.ParsedDoc,
    s3: hl.Sec3Info,
    board_items: list[hl.BoardItem],
    status: str,
    blocks: list[str],
    today: date,
) -> None:
    registry = "决策登记表" in agents or "决策登记表" in status or (root / cfg.docs_dir / "决策登记表.md").is_file()
    add("A001", "决策登记表存在", registry, "" if registry else "具约束力的决策应收口到一张可 grep 的表", True)

    const_re = re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*=\s*(\{[^{}]*\}|\[[^\[\]]*\])([^\n]*)$", re.M)
    seen: dict[str, dict[tuple[str, ...], list[str]]] = {}
    scripts = root / "scripts"
    for fp in sorted(scripts.rglob("*.py")) if scripts.is_dir() else []:
        script_text = hl.read_utf8(fp)
        for m in const_re.finditer(script_text):
            cname, cbody = m.group(1), m.group(2)
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

    index = hl.read_utf8(root / cfg.index_file)
    index_disp = Path(cfg.index_file).name
    agents_sz = len(agents.encode("utf-8"))
    status_sz = len(status.encode("utf-8"))
    index_sz = len(index.encode("utf-8"))
    big = [
        f"{n} {sz // 1000}KB"
        for n, sz, limit in (
            ("AGENTS.md", agents_sz, 25_000),
            ("STATUS.md", status_sz, 40_000),
            (index_disp, index_sz, 15_000),
        )
        if sz > limit
    ]
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
    add(
        "A003",
        "AGENTS ≤25KB、STATUS ≤40KB、任务卡索引 ≤15KB",
        not big,
        "；".join([", ".join(big), *a003_hints]) if big else "",
        True,
    )

    real_board_items = [it for it in board_items if not it.is_template]
    tpl_box_cnt = len(board_items) - len(real_board_items)
    checked = sum(1 for it in real_board_items if it.checked)
    unchecked = len(real_board_items) - checked
    a004_ok = checked > 0 or (not real_board_items and not tpl_box_cnt)
    a004_detail = f"{checked} 勾 / {unchecked} 未勾" + (f"（忽略 {tpl_box_cnt} 行模板占位）" if tpl_box_cnt else "")
    add("A004", "§4 看板至少勾了一项", a004_ok, a004_detail, True)

    cards_dir = root / cfg.cards_dir
    cards_dir_exists = cards_dir.is_dir()
    cards = sorted(cards_dir.glob("*.md")) if cards_dir_exists else []
    active_cards: list[tuple[Path, str]] = []
    unparsed_cards: list[str] = []
    lacking: list[str] = []
    for fp in cards:
        text = hl.read_utf8(fp)
        st_mark = hl.parse_card_state(text)
        if st_mark is None:
            unparsed_cards.append(fp.name)
        elif st_mark in hl.CLOSED:
            continue
        active_cards.append((fp, text))
        heads = hl.extract_prompt_headings(text)
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
    add(
        "A005",
        "任务卡同时带执行方和独立复核方提示词",
        not lacking,
        (
            f"{len(lacking)} 张缺："
            + "、".join(lacking[:5])
            + ("…" if len(lacking) > 5 else "")
            + unparsed_note
            + "；一个任务一张卡，复核写在同一张卡里（已收口 ✅ 与作废 🗄️ 卡不查）"
        )
        if lacking
        else skip_note,
        True,
    )

    bloated = []
    for fp, text in active_cards:
        size = len(text.encode("utf-8"))
        prompts = len(hl.extract_prompt_headings(text))
        if size > 15_000:
            bloated.append(f"{fp.name}（{size // 1000}KB，{prompts} 段提示词；最大三节：{hl.top_card_sections(text)}）")
        elif prompts > 3:
            bloated.append(f"{fp.name}（{size // 1000}KB，{prompts} 段提示词）")
    add(
        "A006",
        "任务卡 ≤15KB、提示词段 ≤3",
        not bloated,
        (
            f"{len(bloated)} 张在用卡超限（跳过 {closed_cnt} 张收口/作废）{unparsed_note}："
            + "；".join(bloated[:6])
            + ("…" if len(bloated) > 6 else "")
            + "；超限部分该挪到 STATUS 或开新卡，就地改并删用过的提示词（见 任务卡_README.md 卡面规矩）"
        )
        if bloated
        else skip_note,
        True,
    )

    states = card_states(cards)
    idx_doc = hl.parse_markdown(index)
    drift = []
    for b in idx_doc.blocks:
        if b.kind != "table_row" or b.is_separator:
            continue
        row_raw = b.lines[0]
        cells = [c.strip(" *`") for c in b.cells]
        for cid, (state, name) in states.items():
            mark = hl.STATE_RE.search("|".join(cells[1:]))
            if (cells[0] == cid or name in row_raw) and mark and (mark.group(0) in hl.CLOSED) != (state in hl.CLOSED):
                drift.append(f"{cid} 卡面 {state}／索引 {mark.group(0)}")
    drift.extend(sec4_card_drifts(board_items, states))
    a007_issues: list[str] = []
    if unparsed_cards:
        a007_issues.append(
            "状态行无法解析：" + "、".join(unparsed_cards[:5]) + ("…" if len(unparsed_cards) > 5 else "")
        )
    if drift:
        a007_issues.append("；".join(drift[:6]) + ("…" if len(drift) > 6 else ""))
    add(
        "A007",
        "卡面状态与 §4 看板、任务卡索引一致（只比收口与否）",
        not a007_issues,
        ("；".join(a007_issues) + "；对不上以卡面为准，主控收口时同步 §4 与索引")
        if a007_issues
        else (f"{len(states)} 张卡有“进度回写”" if cards else "无任务卡（未检查）"),
        True,
    )

    sec3_blocks = hl.extract_section_blocks(agents_doc, "3", {"现在在哪", "Where We Are Now"})
    non_ptr_entries = [
        blk_lines
        for _, blk_lines in s3.entries
        if blk_lines and not re.match(r"^[-*+]\s+`?→", blk_lines[0])
    ]
    sec3_vis_lines = [
        ln
        for b in sec3_blocks[1:]
        if b.kind not in ("fenced_code", "indented_code", "html_comment")
        for ln in b.visible_lines(include_code=True)
    ]
    stale = sorted(
        {
            cid
            for ln in sec3_vis_lines
            if re.search(r"待审查|待复核|待收口|已交回|🟡|🔵", ln)
            for cid in [subject_card(ln, states)]
            if cid and states[cid][0] in hl.CLOSED
        }
    )
    add(
        "A008",
        "§3 ≤5 条、不挂已收口卡的“待审查”",
        len(non_ptr_entries) <= 5 and not stale,
        f"§3 {len(non_ptr_entries)} 条"
        + (f"；卡面已收口仍挂待审查：{'、'.join(stale)}" if stale else "")
        + ("；§3 只留 1–5 条累计快照，旧条移到归档" if len(non_ptr_entries) > 5 or stale else ""),
        True,
    )

    long_rows = []
    for fp, text in active_cards:
        for label, n_chars, _ in hl.extract_card_progress_rows(text):
            if n_chars > 400:
                long_rows.append(f"{fp.name}「{label}」行 {n_chars} 字")
    add(
        "A009",
        "“进度回写”每行 ≤400 字",
        not long_rows,
        (
            "；".join(long_rows[:4])
            + ("…" if len(long_rows) > 4 else "")
            + (f"（跳过 {closed_cnt} 张收口/作废）" if closed_cnt else "")
            + unparsed_note
            + "；一句话结果之外的细节写进 STATUS 或结果说明"
        )
        if long_rows
        else skip_note,
        True,
    )

    sizes = [len("\n".join(e).strip()) for e in non_ptr_entries]
    wordy = [
        f"第 {i} 条（{e[0].lstrip('-*+ ')[:14]}…）{n} 字"
        for i, (e, n) in enumerate(zip(non_ptr_entries, sizes), 1)
        if n > 600
    ]
    add(
        "A010",
        "§3 每条 ≤600 字",
        not wordy,
        (
            "；".join(wordy[:4])
            + ("…" if len(wordy) > 4 else "")
            + "；细节写进 STATUS，§3 只留累计快照；不要往 §3 追加执行方交回长段"
        )
        if wordy
        else "",
        True,
    )

    if not blocks:
        add(
            "A011",
            "STATUS 最近 5 段交接 ≤800 字且四节齐",
            False,
            "未找到交接段（仅认 ## 或 ### 标题，#### 及更深标题不算；须含 Handoff/交接，或以日期 / T<卡号>+日期 开头；“交回说明”等不算交接）",
            True,
        )
    else:
        d_first = hl.block_latest_date(blocks[0], today)
        d_last = hl.block_latest_date(blocks[-1], today)
        rev_order = bool(d_first and d_last and d_first > d_last)
        recent_blocks = blocks[:5] if rev_order else blocks[-5:]
        bad_segs: list[str] = []
        for seg in recent_blocks:
            seg_doc = hl.parse_markdown(seg)
            seg_title = (
                seg_doc.blocks[0].title[:36]
                if seg_doc.blocks and seg_doc.blocks[0].kind == "heading"
                else seg.splitlines()[0].lstrip("#").strip()[:36]
            )
            seg_len = len(seg.strip())
            missing_secs = hl.missing_handoff_sections(seg)
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

    review_files = collect_review_files(root, cfg)
    checked_reviews: list[Path] = []
    skipped_reviews = 0
    bad_reviews: list[str] = []
    for fp in review_files:
        rcid = review_card_id(fp, states)
        if rcid is not None and states[rcid][0] in hl.CLOSED:
            skipped_reviews += 1
            continue
        checked_reviews.append(fp)
        non_empty = [ln.strip() for ln in hl.read_utf8(fp).splitlines() if ln.strip()]
        if not non_empty or non_empty[-1] not in ("PASS", "NEEDS_FIX"):
            bad_reviews.append(fp.name)
    if not review_files:
        a012_ok_detail = "暂无复核报告"
    elif skipped_reviews:
        a012_ok_detail = f"{len(checked_reviews)} 份复核报告（跳过 {skipped_reviews} 份收口/作废卡报告）"
    else:
        a012_ok_detail = f"{len(checked_reviews)} 份复核报告"
    add(
        "A012",
        "复核报告末尾有单独一行 PASS 或 NEEDS_FIX",
        not bad_reviews,
        (
            f"{len(bad_reviews)} 份缺结论行"
            + (f"（已跳过 {skipped_reviews} 份收口/作废卡报告）" if skipped_reviews else "")
            + "："
            + "、".join(bad_reviews[:5])
            + ("…" if len(bad_reviews) > 5 else "")
            + "；复核报告末尾须单独一行只写 PASS 或 NEEDS_FIX"
        )
        if bad_reviews
        else a012_ok_detail,
        True,
    )

    a013_ok, a013_detail = check_decision_chain_a013(agents)
    add("A013", "§3.5 决策登记表无重复 ID 且取代链自洽", a013_ok, a013_detail, True)

    a014_ok, a014_detail = check_agents_placeholders_a014(agents)
    add("A014", "AGENTS.md 无遗留【待填】且“不可混用的维度”已填", a014_ok, a014_detail, True)

    if not cards_dir_exists:
        a015_ok, a015_detail = False, f"未找到 {cfg.cards_dir}/ 目录，卡类检查（A005—A009）均未执行"
    elif not cards:
        a015_ok, a015_detail = False, f"{cfg.cards_dir}/ 下有 0 张任务卡，卡类检查（A005—A009）均未执行"
    else:
        a015_ok, a015_detail = True, f"{len(cards)} 张任务卡"
    add("A015", "任务卡目录存在且非空", a015_ok, a015_detail, True)


def index_checks(root: Path) -> None:
    text = hl.read_utf8(root / "AGENTS.md")
    doc = hl.parse_markdown(text)
    add("I001", "根 AGENTS.md 存在", bool(text.strip()))
    has_scope_idx = any(
        re.match(r"^>\s*\*\*Scope[:：]\s*index\*\*", ln, re.I)
        for b in doc.blocks
        if b.kind == "paragraph"
        for ln in b.lines
    )
    declared = has_scope_idx or bool(
        re.search(r"根索引|课题总索引|本文件只是索引|root\s+index", text, re.I)
        and not hl.find_section_range(doc, "3", {"现在在哪"})
    )
    add("I002", "根 AGENTS.md 声明为索引", declared, "" if declared else "缺少 Scope: index 标记，或混入了线级 §3")
    paths = sorted(
        {
            p.replace("\\", "/")
            for b in doc.blocks
            if b.kind != "fenced_code"
            for p in re.findall(r"([\w.\-一-鿿/\\]+/AGENTS\.md)", b.raw_text)
        }
    )
    missing = [p for p in paths if not (root / p).is_file()]
    add(
        "I003",
        "列出的线级 AGENTS.md 都存在",
        bool(paths) and not missing,
        ("missing: " + ", ".join(missing)) if missing else f"{len(paths)} 条线" if paths else "没列出线级入口",
    )


def role_checks(root: Path, cfg: hl.HandoffConfig, role: str, card_arg: Optional[str], today: date) -> None:
    """Checks for --role executor / reviewer: never reads or checks AGENTS.md."""
    status = hl.read_utf8(root / "STATUS.md")
    h005_ok, h005_detail = check_status_h005(status, today)
    add("H005", "STATUS.md 存在且非模板", h005_ok, h005_detail, False)

    blocks = hl.handoff_blocks(status)
    if not blocks:
        add(
            "A011",
            "STATUS 最近交接段 ≤800 字且四节齐",
            False,
            "未找到交接段（仅认 ## 或 ### 标题，#### 及更深标题不算；须含 Handoff/交接，或以日期 / T<卡号>+日期 开头；“交回说明”等不算交接）",
            False,
        )
    else:
        d_first = hl.block_latest_date(blocks[0], today)
        d_last = hl.block_latest_date(blocks[-1], today)
        rev_order = bool(d_first and d_last and d_first > d_last)
        latest_seg = blocks[0] if rev_order else blocks[-1]
        seg_doc = hl.parse_markdown(latest_seg)
        seg_title = (
            seg_doc.blocks[0].title[:36]
            if seg_doc.blocks and seg_doc.blocks[0].kind == "heading"
            else latest_seg.splitlines()[0].lstrip("#").strip()[:36]
        )
        seg_len = len(latest_seg.strip())
        missing_secs = hl.missing_handoff_sections(latest_seg)
        if seg_len > 800 or missing_secs:
            seg_issues = [f"{seg_len} 字" + ("（超 800 字）" if seg_len > 800 else "")]
            if missing_secs:
                seg_issues.append("缺节：" + "、".join(missing_secs))
            add(
                "A011",
                "STATUS 最近交接段 ≤800 字且四节齐",
                False,
                f"「{seg_title}」" + "，".join(seg_issues) + "；须含“改了什么 / 怎么验证的 / 没做什么 / 不确定处”四节且 ≤800 字",
                False,
            )
        else:
            add("A011", "STATUS 最近交接段 ≤800 字且四节齐", True, f"最新段合规（{seg_len} 字，四节齐）", False)

    if card_arg:
        target_id = card_arg.strip()
        cards_dir = root / cfg.cards_dir
        cards = sorted(cards_dir.glob("*.md")) if cards_dir.is_dir() else []
        matched = [fp for fp in cards if hl.extract_card_id(fp.stem).upper() == target_id.upper()]
        if not matched:
            matched = [fp for fp in cards if fp.stem.upper() == target_id.upper() or fp.name.upper() == target_id.upper()]
        role_label = "执行方" if role == "executor" else "复核方"
        if not matched:
            add("A007", f"任务卡 {target_id} 状态行与{role_label}身份已填", False, f"未找到任务卡 {target_id}", False)
            add("A009", "本卡“进度回写”每行 ≤400 字", False, f"未找到任务卡 {target_id}", False)
        else:
            fp = matched[0]
            card_text = hl.read_utf8(fp)
            st_mark = hl.parse_card_state(card_text)
            id_ok, id_detail = hl.check_card_role_identity(card_text, role)
            card_issues: list[str] = []
            if st_mark is None:
                card_issues.append(f"状态行无法解析：{fp.name}")
            if not id_ok:
                card_issues.append(f"{fp.name}：{id_detail}")
            add(
                "A007",
                f"任务卡 {target_id} 状态行与{role_label}身份已填",
                not card_issues,
                "；".join(card_issues) if card_issues else f"{fp.name} 状态 {st_mark}，{id_detail}",
                False,
            )
            long_rows = [
                f"{fp.name}「{label}」行 {n_chars} 字"
                for label, n_chars, _ in hl.extract_card_progress_rows(card_text)
                if n_chars > 400
            ]
            add(
                "A009",
                "本卡“进度回写”每行 ≤400 字",
                not long_rows,
                ("；".join(long_rows) + "；一句话结果之外的细节写进 STATUS 或结果说明") if long_rows else f"{fp.name} 合规",
                False,
            )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="收工交接自检")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--days", "-d", type=int, default=7)
    parser.add_argument("--scope", choices=("line", "index"), default="line")
    parser.add_argument("--role", choices=("controller", "executor", "reviewer"), default="controller")
    parser.add_argument("--card", help="指定任务卡卡号（如 T13d），配合 --role executor/reviewer 检查本卡")
    parser.add_argument("--today", help="YYYY-MM-DD，覆盖检查日期（测试用）")
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"[H000] ❌ FAIL 项目根不是目录：{root}", file=sys.stderr)
        return 2
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    cfg = hl.load_handoff_config(root)
    for w in cfg.warnings:
        print(f"提示：{w}")

    findings.clear()
    if args.role in ("executor", "reviewer"):
        card_note = f"与任务卡 {args.card}" if args.card else "（未传 --card，跳过单卡检查）"
        print(
            f"角色={args.role}（已跳过 AGENTS.md 全部检查项 H001–H004/H006–H009 及主控全局项，仅查 STATUS.md 最近交接段{card_note}）"
        )
        role_checks(root, cfg, args.role, args.card, today)
        print("=" * 60)
        print(f"  收工交接自检 | role={args.role}" + (f" | card={args.card}" if args.card else "") + f" | today={today}")
        print("=" * 60)
    else:
        if args.scope == "index":
            index_checks(root)
        else:
            line_checks(root, cfg, args.days, today)
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

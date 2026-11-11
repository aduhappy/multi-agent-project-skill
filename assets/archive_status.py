#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""archive_status.py — 一键归档 STATUS.md 旧交接段与 AGENTS.md §3 旧快照（multi-agent-project 配套）

用法：
    python scripts/archive_status.py                      # 保留 STATUS 最近 10 段、AGENTS §3 最近 5 条
    python scripts/archive_status.py PATH --keep 10       # 指定项目根与保留段数
    python scripts/archive_status.py PATH --dry-run       # 只预览不写盘
    python scripts/archive_status.py --version            # 查看脚本版本号

行为：
  - STATUS.md：交接段数 > --keep（默认 10）时，保留最近 N 段，其余原样移到
    文档/STATUS_归档_至<日期>.md（同日归档文件已存在则追加），并在入口头部留一行 `>` 引用。
    （交接标题支持 `##` 或 `###`，须含 `Handoff`/`交接`，或以日期 / `T<卡号>+日期` 开头；“交回说明”等不算交接；
     日期支持 YYYY-MM-DD、YYYY/MM/DD、YYYY.MM.DD、YYYY年MM月DD日。）
  - AGENTS.md：§3 可归档快照条数 > --agents-keep（默认 5）时，保留最近 M 条（保留“阻塞”与 `→` 指针行），
    其余原样移到 文档/AGENTS_归档_至<日期>.md，并在 §3 留一行 `>` 引用。
    （若 AGENTS.md 超 25KB 是因 §3.5 决策登记表过长，需按 §3.5 规矩手动迁出全文，本脚本不拆决策表。）
  - 换行符保持：写回原文件时保持原文件的 LF 或 CRLF；新建归档文件的换行符与对应源文件（默认 STATUS.md）一致。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
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
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEAD_RE = re.compile(r"^\s*(#{1,6})\s+(.*)$")
HANDOFF_INNER_HEAD_RE = re.compile(
    r"^(?:[-*+]|\d+[.、)])?\s*[\*【\[]*(?:谁做的|改了什么|怎么验证|没做什么|不确定处)"
)


def detect_eol(raw_bytes: bytes) -> str:
    crlf = raw_bytes.count(b"\r\n")
    bare_lf = raw_bytes.count(b"\n") - crlf
    return "\r\n" if crlf > bare_lf else "\n"


def read_utf8_and_eol(path: Path) -> tuple[str, str]:
    raw_bytes = path.read_bytes()
    return raw_bytes.decode("utf-8-sig"), detect_eol(raw_bytes)


def read_utf8(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def write_with_eol(path: Path, text: str, eol: str) -> None:
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    out = norm.replace("\n", "\r\n") if eol == "\r\n" else norm
    path.write_bytes(out.encode("utf-8"))


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


def extract_dates(text: str, today: date) -> list[date]:
    found: list[date] = []
    for m in FLEX_DATE_TOKEN_RE.finditer(text):
        year = int(m.group(1))
        if m.group(3) is not None:
            month, day = int(m.group(3)), int(m.group(4))
        else:
            month, day = int(m.group(5)), int(m.group(6))
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d <= today:
            found.append(d)
    return found


def latest_date(text: str, today: date) -> Optional[date]:
    ds = extract_dates(text, today)
    return max(ds) if ds else None


def is_handoff_title(title: str) -> bool:
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


def _parse_status_with_gaps(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Split STATUS.md into (preamble_lines, handoff_blocks, gaps_before_each_block, postamble_lines)."""
    lines = text.splitlines()
    unfenced = unfenced_indices(lines)
    headings: list[tuple[int, int, str]] = []
    for i in sorted(unfenced):
        m = HEAD_RE.match(lines[i])
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))

    handoff_heads = [
        (i, lvl, t) for i, lvl, t in headings
        if lvl in (2, 3) and is_handoff_title(t) and not HANDOFF_INNER_HEAD_RE.match(t)
    ]
    if not handoff_heads:
        return lines, [], [], []

    handoff_starts = {i for i, _, _ in handoff_heads}
    first_start = handoff_heads[0][0]
    preamble = lines[:first_start]

    blocks: list[str] = []
    gaps: list[str] = []
    postamble: list[str] = []
    prev_end = first_start
    for idx, (start, cur_lvl, _) in enumerate(handoff_heads):
        gap_str = "\n".join(lines[prev_end:start]).strip() if idx > 0 else ""
        gaps.append(gap_str)
        next_end = next(
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
        seg_lines = lines[start:next_end]
        if idx == len(handoff_heads) - 1:
            trailing_non_handoff = lines[next_end:]
            while seg_lines and not seg_lines[-1].strip():
                seg_lines.pop()
            footer_tmp: list[str] = []
            while seg_lines and re.match(r"^>\s*⚠️", seg_lines[-1].strip()):
                footer_tmp.append(seg_lines.pop())
                while seg_lines and not seg_lines[-1].strip():
                    seg_lines.pop()
            postamble = list(reversed(footer_tmp)) + trailing_non_handoff
        blocks.append("\n".join(seg_lines).strip())
        prev_end = next_end
    return preamble, blocks, gaps, postamble


def parse_status(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split STATUS.md into (preamble_lines, handoff_blocks, postamble_lines)."""
    preamble, blocks, _, postamble = _parse_status_with_gaps(text)
    return preamble, blocks, postamble


def upsert_quote_ref(lines: list[str], marker: str, default_prefix: str, ref_rel: str) -> list[str]:
    ref_token = f"`{ref_rel}`"
    out = list(lines)
    for i, ln in enumerate(out):
        if ln.lstrip().startswith(">") and marker in ln:
            if ref_token in ln:
                return out
            stripped = ln.rstrip()
            if stripped.endswith("。"):
                out[i] = stripped[:-1] + f"、{ref_token}。"
            else:
                out[i] = stripped + f"、{ref_token}"
            return out
    while out and not out[-1].strip():
        out.pop()
    if out:
        out.append("")
    out.append(f"> {default_prefix} {ref_token}。")
    return out


def append_or_create_archive(
    arch_path: Path, header_title: str, header_note: str, body: str, default_eol: str
) -> None:
    arch_path.parent.mkdir(parents=True, exist_ok=True)
    chunk = body.strip() + "\n"
    if arch_path.is_file() and arch_path.stat().st_size > 0:
        existing_raw, arch_eol = read_utf8_and_eol(arch_path)
        existing = existing_raw.rstrip()
        write_with_eol(arch_path, existing + "\n\n" + chunk, arch_eol)
    else:
        header = f"# {header_title}\n\n> {header_note}\n\n"
        write_with_eol(arch_path, header + chunk, default_eol)


def archive_status_file(root: Path, keep: int, today: date, dry_run: bool) -> Optional[str]:
    status_path = root / "STATUS.md"
    if not status_path.is_file():
        print("STATUS.md：不存在，跳过。")
        return None

    raw_bytes = status_path.read_bytes()
    status_eol = detect_eol(raw_bytes)
    raw = raw_bytes.decode("utf-8-sig")
    before_bytes = len(raw_bytes)
    preamble, blocks, gaps, postamble = _parse_status_with_gaps(raw)
    total = len(blocks)
    if total <= keep:
        print(f"STATUS.md：共 {total} 段交接（≤ {keep}），无需归档（{before_bytes}B）。")
        return status_eol

    d_first = latest_date(blocks[0].splitlines()[0], today) or latest_date(blocks[0], today)
    d_last = latest_date(blocks[-1].splitlines()[0], today) or latest_date(blocks[-1], today)
    if d_first and d_last and d_first > d_last:
        kept_indices = list(range(keep))
        arch_indices = list(range(keep, total))
    else:
        arch_indices = list(range(total - keep))
        kept_indices = list(range(total - keep, total))

    to_archive = [blocks[i] for i in arch_indices]
    kept_chunks: list[str] = []
    first_kept = kept_indices[0]
    if first_kept > 0 and not gaps[first_kept] and blocks[first_kept].startswith("### "):
        prev_containers = [g for g in gaps[:first_kept] if g.startswith("## ")]
        if prev_containers:
            kept_chunks.append(prev_containers[-1])
    for ki in kept_indices:
        if gaps[ki]:
            kept_chunks.append(gaps[ki])
        kept_chunks.append(blocks[ki])

    arch_dates = [
        d
        for b in to_archive
        for d in [latest_date(b.splitlines()[0], today) or latest_date(b, today)]
        if d is not None
    ]
    arch_date_str = max(arch_dates).isoformat() if arch_dates else today.isoformat()
    rel_arch = f"文档/STATUS_归档_至{arch_date_str}.md"
    arch_path = root / "文档" / f"STATUS_归档_至{arch_date_str}.md"

    new_preamble = upsert_quote_ref(
        preamble,
        marker="STATUS_归档_",
        default_prefix="更早的交接段已归档到",
        ref_rel=rel_arch,
    )
    parts = ["\n".join(new_preamble).rstrip(), "\n\n".join(kept_chunks)]
    if postamble and "\n".join(postamble).strip():
        parts.append("\n".join(postamble).strip())
    new_status_lf = "\n\n".join(p for p in parts if p) + "\n"
    new_status_final = new_status_lf.replace("\n", "\r\n") if status_eol == "\r\n" else new_status_lf
    after_bytes = len(new_status_final.encode("utf-8"))

    if dry_run:
        print(
            f"[DRY-RUN] STATUS.md：将归档 {len(to_archive)} 段 → {rel_arch}，保留 {len(kept_indices)} 段；"
            f"体积 {before_bytes}B → {after_bytes}B。"
        )
        return status_eol

    append_or_create_archive(
        arch_path,
        header_title=f"STATUS 归档（原样迁出，至 {arch_date_str}）",
        header_note="自 `STATUS.md` 原样移出的旧交接段，只作历史查阅；当前状态以 `AGENTS.md` §3 与 `STATUS.md` 为准。",
        body="\n\n".join(to_archive),
        default_eol=status_eol,
    )
    write_with_eol(status_path, new_status_lf, status_eol)
    warn_tail = "（注意：仍 >40KB，可调小 --keep）" if after_bytes > 40_000 else ""
    print(
        f"STATUS.md：已归档 {len(to_archive)} 段 → {rel_arch}，保留 {len(kept_indices)} 段；"
        f"体积 {before_bytes}B → {after_bytes}B{warn_tail}。"
    )
    return status_eol


def archive_agents_sec3(
    root: Path, agents_keep: int, today: date, dry_run: bool, status_eol: Optional[str] = None
) -> None:
    agents_path = root / "AGENTS.md"
    if not agents_path.is_file():
        return

    raw_bytes = agents_path.read_bytes()
    agents_eol = detect_eol(raw_bytes)
    raw = raw_bytes.decode("utf-8-sig")
    before_bytes = len(raw_bytes)
    lines = raw.splitlines()
    unfenced = unfenced_indices(lines)

    sec3_start: Optional[int] = None
    sec3_end = len(lines)
    for i in sorted(unfenced):
        ln = lines[i]
        if ln.startswith("## "):
            if sec3_start is None:
                if re.match(r"^## 3(?:\.(?!\d)|\s|$)", ln) or ln[3:].strip() in {"现在在哪", "Where We Are Now"}:
                    sec3_start = i
            else:
                sec3_end = i
                break

    if sec3_start is None:
        return

    sec_head = lines[sec3_start]
    body_lines = lines[sec3_start + 1 : sec3_end]

    # Parse §3 body into blocks: quote/other lines, archivable bullet entries, trailer entries (阻塞 / →)
    lead_lines: list[str] = []
    entries: list[tuple[str, list[str]]] = []  # kind ('archivable' | 'trailer'), lines
    cur_kind: Optional[str] = None
    cur_buf: list[str] = []

    def flush() -> None:
        nonlocal cur_kind, cur_buf
        if cur_kind is not None and cur_buf:
            entries.append((cur_kind, cur_buf))
        cur_kind, cur_buf = None, []

    for ln in body_lines:
        if re.match(r"^[-*]\s+", ln):
            flush()
            if re.match(r"^[-*]\s+`?→", ln) or re.match(r"^[-*]\s+\**(?:阻塞|Blockers?)\**[:：]?", ln, re.I):
                cur_kind = "trailer"
            else:
                cur_kind = "archivable"
            cur_buf = [ln]
        elif cur_kind is not None:
            if not ln.strip() or re.match(r"^\s+", ln):
                cur_buf.append(ln)
            else:
                flush()
                lead_lines.append(ln)
        else:
            lead_lines.append(ln)
    flush()

    archivable = [(idx, blk) for idx, (kind, blk) in enumerate(entries) if kind == "archivable"]
    trailer_bullets = sum(
        1 for kind, blk in entries
        if kind == "trailer" and blk and re.match(r"^[-*]\s+(?!`?→)", blk[0])
    )
    snap_budget = max(1, agents_keep - trailer_bullets)
    if len(archivable) <= snap_budget:
        if before_bytes > 25_000:
            print(
                f"AGENTS.md：{before_bytes}B（>25KB），但 §3 总条数 {len(archivable) + trailer_bullets}（≤ {agents_keep}），"
                "体积主要在 §3.5 决策登记表等其他节（可按 §3.5 说明迁出全文）。"
            )
        return

    # Decide chronological vs reverse-chronological order among archivable entries
    first_d = latest_date("\n".join(archivable[0][1]), today)
    last_d = latest_date("\n".join(archivable[-1][1]), today)
    reverse_chrono = bool(first_d and last_d and first_d > last_d)

    scored = []
    for pos, (entry_idx, blk) in enumerate(archivable):
        d = latest_date("\n".join(blk), today)
        tie = -pos if reverse_chrono else pos
        scored.append(((d or date.min, tie), entry_idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    keep_indices = {entry_idx for _, entry_idx in scored[:snap_budget]}

    to_archive_blocks = ["\n".join(blk).rstrip() for idx, (kind, blk) in enumerate(entries)
                         if kind == "archivable" and idx not in keep_indices]
    kept_entry_lines: list[str] = []
    for idx, (kind, blk) in enumerate(entries):
        if kind == "trailer" or idx in keep_indices:
            while blk and not blk[-1].strip():
                blk = blk[:-1]
            kept_entry_lines.extend(blk)

    arch_dates = [d for b in to_archive_blocks for d in [latest_date(b, today)] if d is not None]
    arch_date_str = max(arch_dates).isoformat() if arch_dates else "历史"
    rel_arch = f"文档/AGENTS_归档_至{arch_date_str}.md"
    arch_path = root / "文档" / f"AGENTS_归档_至{arch_date_str}.md"

    clean_lead = [ln for ln in lead_lines if ln.strip()]
    updated_lead = upsert_quote_ref(
        clean_lead,
        marker="AGENTS_归档_",
        default_prefix="更早的 §3 快照已归档到",
        ref_rel=rel_arch,
    )
    updated_lead = [ln for ln in updated_lead if ln.strip()]

    new_sec3_lines = [sec_head] + updated_lead + kept_entry_lines + [""]
    new_lines = lines[:sec3_start] + new_sec3_lines + lines[sec3_end:]
    new_agents_lf = "\n".join(new_lines).rstrip() + "\n"
    new_agents_final = new_agents_lf.replace("\n", "\r\n") if agents_eol == "\r\n" else new_agents_lf
    after_bytes = len(new_agents_final.encode("utf-8"))

    if dry_run:
        print(
            f"[DRY-RUN] AGENTS.md §3：将归档 {len(to_archive_blocks)} 条 → {rel_arch}，"
            f"保留 {len(keep_indices)} 条快照（含阻塞共 {len(keep_indices) + trailer_bullets} 条）；体积 {before_bytes}B → {after_bytes}B。"
        )
        return

    arch_default_eol = status_eol if status_eol is not None else agents_eol
    append_or_create_archive(
        arch_path,
        header_title=f"AGENTS §3 归档（原样迁出，至 {arch_date_str}）",
        header_note="自 `AGENTS.md` §3 原样移出的旧快照条目，只作历史查阅；当前状态以 `AGENTS.md` §3 与 `STATUS.md` 为准。",
        body="\n\n".join(to_archive_blocks),
        default_eol=arch_default_eol,
    )
    write_with_eol(agents_path, new_agents_lf, agents_eol)
    print(
        f"AGENTS.md §3：已归档 {len(to_archive_blocks)} 条 → {rel_arch}，"
        f"保留 {len(keep_indices)} 条快照（含阻塞共 {len(keep_indices) + trailer_bullets} 条）；体积 {before_bytes}B → {after_bytes}B。"
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="归档 STATUS.md 旧交接段与 AGENTS.md §3 旧快照")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--keep", "-k", type=int, default=10, help="STATUS.md 保留最近 N 段交接（默认 10）")
    parser.add_argument("--agents-keep", type=int, default=5, help="AGENTS.md §3 保留最近 M 条快照（默认 5）")
    parser.add_argument("--today", help="YYYY-MM-DD，覆盖今天日期（测试用）")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写文件")
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.keep < 1 or args.agents_keep < 1:
        print("错误：--keep 与 --agents-keep 必须 >= 1", file=sys.stderr)
        return 2

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"错误：项目根不是目录：{root}", file=sys.stderr)
        return 2
    if not (root / "STATUS.md").is_file() and not (root / "AGENTS.md").is_file():
        print(f"错误：未找到 STATUS.md 或 AGENTS.md：{root}", file=sys.stderr)
        return 2

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    status_eol = archive_status_file(root, args.keep, today, args.dry_run)
    archive_agents_sec3(root, args.agents_keep, today, args.dry_run, status_eol=status_eol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

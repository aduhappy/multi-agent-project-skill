#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""archive_status.py — 一键归档 STATUS.md 旧交接段与 AGENTS.md §3 旧快照（multi-agent-project 配套）

用法：
    python scripts/archive_status.py                      # 保留 STATUS 最近 10 段、AGENTS §3 最近 5 条
    python scripts/archive_status.py PATH --keep 10       # 指定项目根与保留段数
    python scripts/archive_status.py PATH --dry-run       # 只预览不写盘

行为：
  - STATUS.md：交接段数 > --keep（默认 10）时，保留最近 N 段，其余原样移到
    文档/STATUS_归档_至<日期>.md（同日归档文件已存在则追加），并在入口头部留一行 `>` 引用。
  - AGENTS.md：§3 可归档快照条数 > --agents-keep（默认 5）时，保留最近 M 条（保留“阻塞”与 `→` 指针行），
    其余原样移到 文档/AGENTS_归档_至<日期>.md，并在 §3 留一行 `>` 引用。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DATE_RE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEAD_RE = re.compile(r"^\s*(#{1,6})\s+(.*)$")


def read_utf8(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


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
    for tok in DATE_RE.findall(text):
        try:
            d = datetime.strptime(tok, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d <= today:
            found.append(d)
    return found


def latest_date(text: str, today: date) -> Optional[date]:
    ds = extract_dates(text, today)
    return max(ds) if ds else None


def is_handoff_title(title: str) -> bool:
    t = title.strip()
    return bool(re.search(r"(?i)handoff", t) or re.match(r"^\d{4}-\d{2}-\d{2}", t))


def parse_status(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split STATUS.md into (preamble_lines, handoff_blocks, postamble_lines)."""
    lines = text.splitlines()
    unfenced = unfenced_indices(lines)
    headings: list[tuple[int, int, str]] = []
    for i in sorted(unfenced):
        m = HEAD_RE.match(lines[i])
        if m:
            headings.append((i, len(m.group(1)), m.group(2)))

    handoff_heads = [(i, lvl, t) for i, lvl, t in headings if lvl >= 2 and is_handoff_title(t)]
    if not handoff_heads:
        return lines, [], []

    top_lvl = min(lvl for _, lvl, _ in handoff_heads)
    top_handoff_starts = [i for i, lvl, _ in handoff_heads if lvl == top_lvl]
    first_start = top_handoff_starts[0]
    preamble = lines[:first_start]

    blocks: list[str] = []
    postamble: list[str] = []
    for idx, start in enumerate(top_handoff_starts):
        next_same_or_higher = next(
            (i for i, lvl, _ in headings if i > start and lvl <= top_lvl),
            len(lines),
        )
        seg_lines = lines[start:next_same_or_higher]
        # If this is the last handoff block, detach trailing template `> ⚠️` note or non-handoff sections
        if idx == len(top_handoff_starts) - 1:
            trailing_non_handoff = lines[next_same_or_higher:]
            while seg_lines and not seg_lines[-1].strip():
                seg_lines.pop()
            footer_tmp: list[str] = []
            while seg_lines and re.match(r"^>\s*⚠️", seg_lines[-1].strip()):
                footer_tmp.append(seg_lines.pop())
                while seg_lines and not seg_lines[-1].strip():
                    seg_lines.pop()
            postamble = list(reversed(footer_tmp)) + trailing_non_handoff
        blocks.append("\n".join(seg_lines).strip())
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


def append_or_create_archive(arch_path: Path, header_title: str, header_note: str, body: str) -> None:
    arch_path.parent.mkdir(parents=True, exist_ok=True)
    chunk = body.strip() + "\n"
    if arch_path.is_file() and arch_path.stat().st_size > 0:
        existing = read_utf8(arch_path).rstrip()
        arch_path.write_text(existing + "\n\n" + chunk, encoding="utf-8")
    else:
        header = f"# {header_title}\n\n> {header_note}\n\n"
        arch_path.write_text(header + chunk, encoding="utf-8")


def archive_status_file(root: Path, keep: int, today: date, dry_run: bool) -> None:
    status_path = root / "STATUS.md"
    if not status_path.is_file():
        print("STATUS.md：不存在，跳过。")
        return

    raw = read_utf8(status_path)
    before_bytes = len(raw.encode("utf-8"))
    preamble, blocks, postamble = parse_status(raw)
    total = len(blocks)
    if total <= keep:
        print(f"STATUS.md：共 {total} 段交接（≤ {keep}），无需归档（{before_bytes}B）。")
        return

    d_first = latest_date(blocks[0], today)
    d_last = latest_date(blocks[-1], today)
    if d_first and d_last and d_first > d_last:
        kept = blocks[:keep]
        to_archive = blocks[keep:]
    else:
        to_archive = blocks[:-keep]
        kept = blocks[-keep:]

    arch_dates = [d for b in to_archive for d in [latest_date(b, today)] if d is not None]
    arch_date_str = max(arch_dates).isoformat() if arch_dates else today.isoformat()
    rel_arch = f"文档/STATUS_归档_至{arch_date_str}.md"
    arch_path = root / "文档" / f"STATUS_归档_至{arch_date_str}.md"

    new_preamble = upsert_quote_ref(
        preamble,
        marker="STATUS_归档_",
        default_prefix="更早的交接段已归档到",
        ref_rel=rel_arch,
    )
    parts = ["\n".join(new_preamble).rstrip(), "\n\n".join(kept)]
    if postamble and "\n".join(postamble).strip():
        parts.append("\n".join(postamble).strip())
    new_status = "\n\n".join(p for p in parts if p) + "\n"
    after_bytes = len(new_status.encode("utf-8"))

    if dry_run:
        print(
            f"[DRY-RUN] STATUS.md：将归档 {len(to_archive)} 段 → {rel_arch}，保留 {len(kept)} 段；"
            f"体积 {before_bytes}B → {after_bytes}B。"
        )
        return

    append_or_create_archive(
        arch_path,
        header_title=f"STATUS 归档（原样迁出，至 {arch_date_str}）",
        header_note="自 `STATUS.md` 原样移出的旧交接段，只作历史查阅；当前状态以 `AGENTS.md` §3 与 `STATUS.md` 为准。",
        body="\n\n".join(to_archive),
    )
    status_path.write_text(new_status, encoding="utf-8")
    warn_tail = "（注意：仍 >40KB，可调小 --keep）" if after_bytes > 40_000 else ""
    print(
        f"STATUS.md：已归档 {len(to_archive)} 段 → {rel_arch}，保留 {len(kept)} 段；"
        f"体积 {before_bytes}B → {after_bytes}B{warn_tail}。"
    )


def archive_agents_sec3(root: Path, agents_keep: int, today: date, dry_run: bool) -> None:
    agents_path = root / "AGENTS.md"
    if not agents_path.is_file():
        return

    raw = read_utf8(agents_path)
    before_bytes = len(raw.encode("utf-8"))
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
    new_agents = "\n".join(new_lines).rstrip() + "\n"
    after_bytes = len(new_agents.encode("utf-8"))

    if dry_run:
        print(
            f"[DRY-RUN] AGENTS.md §3：将归档 {len(to_archive_blocks)} 条 → {rel_arch}，"
            f"保留 {len(keep_indices)} 条快照（含阻塞共 {len(keep_indices) + trailer_bullets} 条）；体积 {before_bytes}B → {after_bytes}B。"
        )
        return

    append_or_create_archive(
        arch_path,
        header_title=f"AGENTS §3 归档（原样迁出，至 {arch_date_str}）",
        header_note="自 `AGENTS.md` §3 原样移出的旧快照条目，只作历史查阅；当前状态以 `AGENTS.md` §3 与 `STATUS.md` 为准。",
        body="\n".join(to_archive_blocks),
    )
    agents_path.write_text(new_agents, encoding="utf-8")
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
    archive_status_file(root, args.keep, today, args.dry_run)
    archive_agents_sec3(root, args.agents_keep, today, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

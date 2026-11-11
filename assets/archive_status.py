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
    （交接标题仅支持 `##` 或 `###`，`####` 及更深标题不算；须含 `Handoff`/`交接`，或以日期 / `T<卡号>+日期` 开头；
     “交回说明”等不算交接；日期支持 YYYY-MM-DD、YYYY/MM/DD、YYYY.MM.DD、YYYY年MM月DD日。）
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

__version__ = "0.4.2"

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
    from handoff_lib import parse_status  # noqa: F401
except ImportError:
    print("错误：未找到 handoff_lib.py，请把 handoff_lib.py 一起复制到同一目录。", file=sys.stderr)
    raise SystemExit(2)


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
    chunk = body.strip("\r\n").rstrip() + "\n"
    if arch_path.is_file() and arch_path.stat().st_size > 0:
        existing_raw, arch_eol = hl.read_utf8_and_eol(arch_path)
        existing = existing_raw.rstrip()
        hl.write_with_eol(arch_path, existing + "\n\n" + chunk, arch_eol)
    else:
        header = f"# {header_title}\n\n> {header_note}\n\n"
        hl.write_with_eol(arch_path, header + chunk, default_eol)


def archive_status_file(
    root: Path, cfg: hl.HandoffConfig, keep: int, today: date, dry_run: bool
) -> Optional[str]:
    status_path = root / "STATUS.md"
    if not status_path.is_file():
        print("STATUS.md：不存在，跳过。")
        return None

    raw_bytes = status_path.read_bytes()
    status_eol = hl.detect_eol(raw_bytes)
    raw = raw_bytes.decode("utf-8-sig")
    before_bytes = len(raw_bytes)
    sdoc = hl.parse_status_document(raw)
    preamble, blocks, gaps, postamble = sdoc.preamble, sdoc.blocks, sdoc.gaps, sdoc.postamble
    total = len(blocks)
    if total <= keep:
        print(f"STATUS.md：共 {total} 段交接（≤ {keep}），无需归档（{before_bytes}B）。")
        return status_eol

    d_first = hl.block_latest_date(blocks[0], today)
    d_last = hl.block_latest_date(blocks[-1], today)
    if d_first and d_last and d_first > d_last:
        quota_kept = set(range(keep))
        cand_arch = list(range(keep, total))
    else:
        cand_arch = list(range(total - keep))
        quota_kept = set(range(total - keep, total))

    active_cids = hl.collect_active_card_ids(root, cfg)
    pinned_arch = {
        idx for idx in cand_arch if hl.block_mentions_active_card(blocks[idx], active_cids)
    }
    extra_kept = len(pinned_arch)
    arch_indices = [idx for idx in cand_arch if idx not in pinned_arch]
    kept_indices = sorted(quota_kept | pinned_arch)

    if not arch_indices:
        prefix = "[DRY-RUN] " if dry_run else ""
        print(
            f"{prefix}STATUS.md：共 {total} 段交接，保留 {len(kept_indices)} 段（因此多留了 {extra_kept} 段），无需归档（{before_bytes}B）。"
        )
        return status_eol

    to_archive = [blocks[i] for i in arch_indices]
    arch_chunks: list[str] = []
    for ai in arch_indices:
        if gaps[ai]:
            arch_chunks.append(gaps[ai])
        arch_chunks.append(blocks[ai])

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
        for d in [hl.block_latest_date(b, today)]
        if d is not None
    ]
    arch_date_str = max(arch_dates).isoformat() if arch_dates else today.isoformat()
    rel_arch = f"{cfg.docs_dir}/STATUS_归档_至{arch_date_str}.md"
    arch_path = root / cfg.docs_dir / f"STATUS_归档_至{arch_date_str}.md"

    new_preamble = upsert_quote_ref(
        preamble,
        marker="STATUS_归档_",
        default_prefix="更早的交接段已归档到",
        ref_rel=rel_arch,
    )
    parts = ["\n".join(new_preamble).rstrip(), "\n\n".join(kept_chunks)]
    post_str = hl.trim_blank_lines(postamble) if postamble else ""
    if post_str:
        parts.append(post_str)
    new_status_lf = "\n\n".join(p for p in parts if p) + "\n"
    new_status_final = new_status_lf.replace("\n", "\r\n") if status_eol == "\r\n" else new_status_lf
    after_bytes = len(new_status_final.encode("utf-8"))

    extra_note = f"（因此多留了 {extra_kept} 段）" if extra_kept else ""
    if dry_run:
        print(
            f"[DRY-RUN] STATUS.md：将归档 {len(to_archive)} 段 → {rel_arch}，保留 {len(kept_indices)} 段{extra_note}；"
            f"体积 {before_bytes}B → {after_bytes}B。"
        )
        return status_eol

    append_or_create_archive(
        arch_path,
        header_title=f"STATUS 归档（原样迁出，至 {arch_date_str}）",
        header_note="自 `STATUS.md` 原样移出的旧交接段，只作历史查阅；当前状态以 `AGENTS.md` §3 与 `STATUS.md` 为准。",
        body="\n\n".join(arch_chunks),
        default_eol=status_eol,
    )
    hl.write_with_eol(status_path, new_status_lf, status_eol)
    warn_tail = "（注意：仍 >40KB，可调小 --keep）" if after_bytes > 40_000 else ""
    print(
        f"STATUS.md：已归档 {len(to_archive)} 段 → {rel_arch}，保留 {len(kept_indices)} 段{extra_note}；"
        f"体积 {before_bytes}B → {after_bytes}B{warn_tail}。"
    )
    return status_eol


def archive_agents_sec3(
    root: Path,
    cfg: hl.HandoffConfig,
    agents_keep: int,
    today: date,
    dry_run: bool,
    status_eol: Optional[str] = None,
) -> None:
    agents_path = root / "AGENTS.md"
    if not agents_path.is_file():
        return

    raw_bytes = agents_path.read_bytes()
    agents_eol = hl.detect_eol(raw_bytes)
    raw = raw_bytes.decode("utf-8-sig")
    before_bytes = len(raw_bytes)

    s3 = hl.extract_sec3_info(raw, today)
    if not s3.exists:
        return

    lines = raw.splitlines()
    entries = s3.entries
    archivable = [(idx, blk) for idx, (kind, blk) in enumerate(entries) if kind == "archivable"]
    trailer_bullets = sum(
        1
        for kind, blk in entries
        if kind == "trailer" and blk and re.match(r"^[-*+]\s+(?!`?→)", blk[0])
    )
    snap_budget = max(1, agents_keep - trailer_bullets)
    if len(archivable) <= snap_budget:
        if before_bytes > 25_000:
            print(
                f"AGENTS.md：{before_bytes}B（>25KB），但 §3 总条数 {len(archivable) + trailer_bullets}（≤ {agents_keep}），"
                "体积主要在 §3.5 决策登记表等其他节（可按 §3.5 说明迁出全文）。"
            )
        return

    first_d = hl.latest_date("\n".join(archivable[0][1]), today)
    last_d = hl.latest_date("\n".join(archivable[-1][1]), today)
    reverse_chrono = bool(first_d and last_d and first_d > last_d)

    scored = []
    for pos, (entry_idx, blk) in enumerate(archivable):
        d = hl.latest_date("\n".join(blk), today)
        tie = -pos if reverse_chrono else pos
        scored.append(((d or date.min, tie), entry_idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    keep_indices = {entry_idx for _, entry_idx in scored[:snap_budget]}

    to_archive_blocks = [
        "\n".join(blk).rstrip()
        for idx, (kind, blk) in enumerate(entries)
        if kind == "archivable" and idx not in keep_indices
    ]
    kept_entry_lines: list[str] = []
    for idx, (kind, blk) in enumerate(entries):
        if kind == "trailer" or idx in keep_indices:
            while blk and not blk[-1].strip():
                blk = blk[:-1]
            kept_entry_lines.extend(blk)

    arch_dates = [d for b in to_archive_blocks for d in [hl.latest_date(b, today)] if d is not None]
    arch_date_str = max(arch_dates).isoformat() if arch_dates else "历史"
    rel_arch = f"{cfg.docs_dir}/AGENTS_归档_至{arch_date_str}.md"
    arch_path = root / cfg.docs_dir / f"AGENTS_归档_至{arch_date_str}.md"

    clean_lead = [ln for ln in s3.lead_lines if ln.strip()]
    updated_lead = upsert_quote_ref(
        clean_lead,
        marker="AGENTS_归档_",
        default_prefix="更早的 §3 快照已归档到",
        ref_rel=rel_arch,
    )
    updated_lead = [ln for ln in updated_lead if ln.strip()]

    new_sec3_lines = [s3.heading_line] + updated_lead + kept_entry_lines + [""]
    new_lines = lines[: s3.start_line] + new_sec3_lines + lines[s3.end_line :]
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
    hl.write_with_eol(agents_path, new_agents_lf, agents_eol)
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
    cfg = hl.load_handoff_config(root)
    for w in cfg.warnings:
        print(f"提示：{w}")
    status_eol = archive_status_file(root, cfg, args.keep, today, args.dry_run)
    archive_agents_sec3(root, cfg, args.agents_keep, today, args.dry_run, status_eol=status_eol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

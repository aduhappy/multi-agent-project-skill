#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""sync_board.py — 从任务卡自动生成 AGENTS.md §4 看板与任务卡索引清单（multi-agent-project 配套）

用法：
    python scripts/sync_board.py                  # 同步当前目录的 AGENTS.md 与任务卡索引
    python scripts/sync_board.py PATH             # 指定项目或线级根目录
    python scripts/sync_board.py PATH --check     # 只比对不写盘（不一致退出码为 1）
    python scripts/sync_board.py --version        # 查看脚本版本号

行为：
  - 只改两对标记之间的内容：
    1) `AGENTS.md` §4 里的 `<!-- board:start -->` … `<!-- board:end -->`
    2) 任务卡索引里的 `<!-- cards:start -->` … `<!-- cards:end -->`
  - 标记外内容逐字节不动（保持原 BOM 与 LF/CRLF 换行符）；没有标记的文件不写，打印添加标记的方法；
    标记未闭合或顺序异常时拒绝写入并返回退出码 1。
  - 按卡号自然序排列，任务名超过 30 字截断为 30 字（29 字 + `…`），表格单元格内自动转义 `|`。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass
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
except ImportError as _exc:
    if getattr(_exc, "name", None) in (None, "handoff_lib"):
        print("错误：未找到 handoff_lib.py，请把 handoff_lib.py 一起复制到同一目录。", file=sys.stderr)
        raise SystemExit(2)
    raise


@dataclass(frozen=True)
class CardBoardRow:
    card_id: str
    task_name: str
    short_name: str
    checked: bool
    state_sym: Optional[str]
    state_label: str
    depends: str
    rel_to_index: str
    filename: str


@dataclass(frozen=True)
class MarkerSpan:
    state: str  # "missing" | "malformed" | "ok"
    inner_start: int = 0
    inner_end: int = 0
    eol: bytes = b"\n"
    detail: str = ""


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    updated_files: list[str]
    unchanged_files: list[str]
    drifted_files: list[str]
    missing_marker_hints: list[str]
    errors: list[str]
    dup_issues: list[str]
    unparsed_files: list[str]
    card_count: int


def natural_card_sort_key(card_id: str, filename: str = "") -> tuple[object, ...]:
    tokens = re.findall(r"\d+|\D+", card_id)
    key_parts: list[tuple[int, object]] = [
        (0, int(tok)) if tok.isdigit() else (1, tok.casefold())
        for tok in tokens
    ]
    return (tuple(key_parts), card_id.casefold(), filename.casefold())


def truncate_task_name(name: str, limit: int = 30) -> str:
    clean = re.sub(r"\s+", " ", name).strip()
    if len(clean) <= limit:
        return clean
    prefix = clean[: limit - 1].rstrip()
    if prefix.endswith("\\"):
        prefix = prefix[:-1].rstrip()
    return prefix + "…"


def escape_md_cell(val: str) -> str:
    s = re.sub(r"\s+", " ", val).strip()
    while s.endswith("\\") and not s.endswith("\\\\"):
        s = s[:-1].rstrip()
    return re.sub(r"(?<!\\)\|", r"\\|", s)


def collect_cards(root: Path, cfg: hl.HandoffConfig) -> tuple[list[CardBoardRow], list[str], list[str]]:
    cards_dir = root / cfg.cards_dir
    if not cards_dir.is_dir():
        return [], [], []

    index_parent = (root / cfg.index_file).parent
    raw_cards = sorted(fp for fp in cards_dir.glob("*.md") if "复核" not in fp.stem)
    rows: list[CardBoardRow] = []
    by_cid_files: dict[str, list[str]] = {}
    by_cid_disp: dict[str, str] = {}
    unparsed_files: list[str] = []

    for fp in raw_cards:
        text = hl.read_utf8(fp)
        hdr = hl.parse_card_header(text, fp.stem)
        cid = (hdr.card_id or hl.extract_card_id(fp.stem)).strip()
        tname = hdr.task_name or fp.stem
        short_name = truncate_task_name(tname, 30)
        sym, state_label = hl.parse_card_state_label(text)
        if sym is None:
            unparsed_files.append(fp.name)
            checked = False
            state_label = "❓未知状态"
        else:
            checked = sym in hl.CLOSED

        cu = cid.upper()
        by_cid_disp.setdefault(cu, cid)
        by_cid_files.setdefault(cu, []).append(fp.name)

        try:
            rel_idx = Path(os.path.relpath(fp, index_parent)).as_posix()
        except ValueError:
            rel_idx = fp.as_posix()

        rows.append(
            CardBoardRow(
                card_id=cid,
                task_name=tname,
                short_name=short_name,
                checked=checked,
                state_sym=sym,
                state_label=state_label,
                depends=hdr.depends or "—",
                rel_to_index=rel_idx,
                filename=fp.name,
            )
        )

    dup_issues = [
        f"卡号重复（{by_cid_disp[cu]}）：{'、'.join(fnames)}"
        for cu, fnames in by_cid_files.items()
        if len(fnames) > 1
    ]
    rows.sort(key=lambda r: natural_card_sort_key(r.card_id, r.filename))
    return rows, dup_issues, unparsed_files


def _code_line_indices(raw_bytes: bytes) -> set[int]:
    txt = raw_bytes.decode("utf-8", errors="replace")
    if txt.startswith("\ufeff"):
        txt = txt[1:]
    doc = hl.parse_markdown(txt, strip_comments=False)
    code_lines: set[int] = set()
    for b in doc.blocks:
        if b.kind in ("fenced_code", "indented_code"):
            code_lines.update(range(b.start_line, b.end_line))
    return code_lines


def find_marker_span_bytes(raw_bytes: bytes, tag: str) -> MarkerSpan:
    code_lines = _code_line_indices(raw_bytes)
    start_re = re.compile(rb"^(?:\xef\xbb\xbf)?[ \t]*<!--\s*" + tag.encode("ascii") + rb":start\s*-->[ \t]*(?:\r?\n|$)")
    end_re = re.compile(rb"^(?:\xef\xbb\xbf)?[ \t]*<!--\s*" + tag.encode("ascii") + rb":end\s*-->[ \t]*(?:\r?\n|$)")

    starts: list[tuple[int, int, int, bytes]] = []
    ends: list[tuple[int, int, int, bytes]] = []
    offset = 0
    for idx, raw_ln in enumerate(raw_bytes.splitlines(keepends=True)):
        ln_start = offset
        ln_end = offset + len(raw_ln)
        offset = ln_end
        if idx in code_lines:
            continue
        if start_re.match(raw_ln):
            starts.append((idx, ln_start, ln_end, raw_ln))
        elif end_re.match(raw_ln):
            ends.append((idx, ln_start, ln_end, raw_ln))

    if not starts and not ends:
        return MarkerSpan(state="missing")
    if len(starts) > 1 or len(ends) > 1:
        return MarkerSpan(
            state="malformed",
            detail=f"发现多组 <!-- {tag}:start/end --> 标记（start={len(starts)}，end={len(ends)}），请只保留一对",
        )
    if len(starts) == 1 and not ends:
        return MarkerSpan(
            state="malformed",
            detail=f"只有 <!-- {tag}:start --> 缺少闭合的 <!-- {tag}:end -->，拒绝写入",
        )
    if len(ends) == 1 and not starts:
        return MarkerSpan(
            state="malformed",
            detail=f"只有 <!-- {tag}:end --> 缺少开头的 <!-- {tag}:start -->，拒绝写入",
        )

    s_idx, _, s_end, s_raw = starts[0]
    e_idx, e_start, _, _ = ends[0]
    if s_idx >= e_idx:
        return MarkerSpan(
            state="malformed",
            detail=f"<!-- {tag}:end --> 出现在 <!-- {tag}:start --> 之前，拒绝写入",
        )

    if s_raw.endswith(b"\r\n"):
        eol = b"\r\n"
    elif s_raw.endswith(b"\n"):
        eol = b"\n"
    else:
        eol = b"\r\n" if hl.detect_eol(raw_bytes) == "\r\n" else b"\n"
    return MarkerSpan(state="ok", inner_start=s_end, inner_end=e_start, eol=eol)


def render_board_lines(rows: list[CardBoardRow]) -> list[str]:
    return [
        f"- [{'x' if r.checked else ' '}] **{r.card_id} {r.short_name}** —— {r.state_label}"
        for r in rows
    ]


def _prefix_has_table_header(prefix_bytes: bytes) -> bool:
    txt = prefix_bytes.decode("utf-8", errors="replace")
    non_empty = [ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("<!--")]
    if len(non_empty) < 2:
        return False
    return (
        non_empty[-2].startswith("|")
        and non_empty[-1].startswith("|")
        and bool(re.fullmatch(r"\|[\s:|\-]+\|?", non_empty[-1]))
    )


def render_cards_lines(rows: list[CardBoardRow], *, include_header: bool = True) -> list[str]:
    out: list[str] = []
    if include_header:
        out.extend(["| 编号 | 任务名 | 状态 | 依赖 | 文件 |", "|---|---|---|---|---|"])
    for r in rows:
        out.append(
            f"| {escape_md_cell(r.card_id)} | {escape_md_cell(r.short_name)} | "
            f"{escape_md_cell(r.state_label)} | {escape_md_cell(r.depends)} | `{r.rel_to_index}` |"
        )
    return out


def compute_synced_bytes(raw_bytes: bytes, span: MarkerSpan, tag: str, rows: list[CardBoardRow]) -> bytes:
    if tag == "board":
        lines = render_board_lines(rows)
    else:
        inc_hdr = not _prefix_has_table_header(raw_bytes[: span.inner_start])
        lines = render_cards_lines(rows, include_header=inc_hdr)
    inner = (span.eol.join(ln.encode("utf-8") for ln in lines) + span.eol) if lines else b""
    return raw_bytes[: span.inner_start] + inner + raw_bytes[span.inner_end :]


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def sync_project(root: Path, *, check_only: bool = False, cfg: Optional[hl.HandoffConfig] = None) -> SyncResult:
    if cfg is None:
        cfg = hl.load_handoff_config(root)
        for w in cfg.warnings:
            print(f"提示：{w}", file=sys.stderr)

    rows, dup_issues, unparsed_files = collect_cards(root, cfg)
    updated: list[str] = []
    unchanged: list[str] = []
    drifted: list[str] = []
    hints: list[str] = []
    errors: list[str] = []

    targets = [
        ("AGENTS.md", root / "AGENTS.md", "board", "请在 AGENTS.md §4 看板列表上下加 <!-- board:start --> 与 <!-- board:end -->"),
        (
            cfg.index_file,
            root / cfg.index_file,
            "cards",
            f"请在 {cfg.index_file} 任务卡清单表上下加 <!-- cards:start --> 与 <!-- cards:end -->",
        ),
    ]

    for disp_name, fp, tag, add_hint in targets:
        if not fp.is_file():
            hints.append(f"{disp_name} 不存在，跳过（{add_hint}）")
            continue
        raw_bytes = fp.read_bytes()
        span = find_marker_span_bytes(raw_bytes, tag)
        if span.state == "missing":
            hints.append(f"{disp_name} 未找到 <!-- {tag}:start --> … <!-- {tag}:end --> 标记，未写入（{add_hint}）")
            continue
        if span.state == "malformed":
            errors.append(f"{disp_name} 标记错误：{span.detail}（{add_hint}）")
            continue
        if not rows:
            hints.append(f"{cfg.cards_dir}/ 下暂无任务卡，保留 {disp_name} 现有标记区内容不变")
            unchanged.append(disp_name)
            continue

        new_bytes = compute_synced_bytes(raw_bytes, span, tag, rows)
        if new_bytes == raw_bytes:
            unchanged.append(disp_name)
        elif check_only:
            drifted.append(disp_name)
        else:
            _atomic_write_bytes(fp, new_bytes)
            updated.append(disp_name)

    if check_only:
        ok = not errors and not drifted and not dup_issues and not unparsed_files
    else:
        ok = not errors

    return SyncResult(
        ok=ok,
        updated_files=updated,
        unchanged_files=unchanged,
        drifted_files=drifted,
        missing_marker_hints=hints,
        errors=errors,
        dup_issues=dup_issues,
        unparsed_files=unparsed_files,
        card_count=len(rows),
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="从任务卡生成 AGENTS.md §4 看板与任务卡索引清单（仅替换标记之间内容）")
    parser.add_argument("path", nargs="?", default=".", help="项目或线级根目录（默认当前目录）")
    parser.add_argument("--check", action="store_true", help="只比对不写盘；不一致或标记异常时返回退出码 1")
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    res = sync_project(root, check_only=args.check)

    for w in res.dup_issues:
        print(f"警告：{w}", file=sys.stderr)
    if res.unparsed_files:
        print("警告：状态行无法解析：" + "、".join(res.unparsed_files), file=sys.stderr)
    for err in res.errors:
        print(f"错误：{err}", file=sys.stderr)
    for h in res.missing_marker_hints:
        print(f"提示：{h}")

    if args.check:
        if res.drifted_files:
            print(
                f"不一致（共 {res.card_count} 张卡）："
                + "、".join(res.drifted_files)
                + " 标记区内容与卡面不同步（请运行 python scripts/sync_board.py）"
            )
        elif res.ok:
            print(f"一致（共 {res.card_count} 张卡）：标记区内容与卡面完全同步。")
    else:
        if res.updated_files:
            print(f"已更新（共 {res.card_count} 张卡）：" + "、".join(res.updated_files))
        elif not res.errors:
            print(f"无需更新（共 {res.card_count} 张卡）：无变化。")

    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

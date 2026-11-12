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
    标记未闭合、顺序异常或标记区内含非看板/非卡清单内容时拒绝写入并返回退出码 1。
  - 按卡号自然序排列；任务名与依赖按“卡头新格式（一级标题＋`> 依赖：`）→ 现有索引表同卡号行 → 卡文件名下划线后部分”取值；
    状态符号与状态词以卡面为准，现有索引行状态后的括号备注原样保留；任务名不截断，生成行列宽不做对齐。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

sys.dont_write_bytecode = True

__version__ = "0.5.1"

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
    if isinstance(_exc, ModuleNotFoundError) and getattr(_exc, "name", None) == "handoff_lib":
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


def normalize_task_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()


def escape_md_cell(val: str) -> str:
    s = re.sub(r"\s+", " ", val).strip()
    while s.endswith("\\") and not s.endswith("\\\\"):
        s = s[:-1].rstrip()
    parts: list[str] = []
    for sp in hl.parse_inlines(s):
        if sp.kind == "code":
            parts.append(sp.raw)
        else:
            parts.append(re.sub(r"(?<!\\)\|", r"\\|", sp.raw))
    return "".join(parts)


@dataclass(frozen=True)
class ExistingIndexCardRow:
    card_id: str
    task_name: str
    state_cell: str
    depends: str
    filename_key: str


def _match_cards_header_columns(hdr_cells: Sequence[str]) -> Optional[tuple[int, int, int, Optional[int], Optional[int]]]:
    """Return (id_col, name_col, state_col, dep_col, file_col) if hdr_cells is a valid cards table header."""
    if not hl.is_cards_table_header(hdr_cells):
        return None
    cleaned = [re.sub(r"[*_~`\s]+", "", re.sub(r"<!--.*?-->", "", c, flags=re.S)) for c in hdr_cells]
    used: set[int] = set()
    req_cols: list[int] = []
    for kw in hl.CARDS_TABLE_REQUIRED_COLS:
        found = next((idx for idx, txt in enumerate(cleaned) if idx not in used and kw in txt), None)
        if found is None:
            return None
        used.add(found)
        req_cols.append(found)
    id_col, name_col, state_col = req_cols
    dep_col = next((idx for idx, txt in enumerate(cleaned) if idx not in used and "依赖" in txt), None)
    if dep_col is not None:
        used.add(dep_col)
    file_col = next((idx for idx, txt in enumerate(cleaned) if idx not in used and "文件" in txt), None)
    return id_col, name_col, state_col, dep_col, file_col


def _group_table_blocks(blocks: Sequence[hl.Block], start_ln: int, end_ln: int) -> list[list[hl.Block]]:
    tbl_rows = [b for b in blocks if b.kind == "table_row" and start_ln <= b.start_line and b.end_line <= end_ln]
    tables: list[list[hl.Block]] = []
    for row in tbl_rows:
        if tables and row.start_line == tables[-1][-1].end_line:
            tables[-1].append(row)
        else:
            tables.append([row])
    return tables


def parse_existing_index_cards(
    raw_bytes: bytes,
) -> tuple[dict[str, list[ExistingIndexCardRow]], dict[tuple[str, str], ExistingIndexCardRow]]:
    """Extract existing card checklist rows from index bytes (whether wrapped in cards markers or unmarked)."""
    if not raw_bytes:
        return {}, {}

    chosen_hdr: Optional[tuple[str, ...]] = None
    data_blocks: list[hl.Block] = []

    span = find_marker_span_bytes(raw_bytes, "cards")
    if span.state == "ok":
        inner_txt = raw_bytes[span.inner_start : span.inner_end].decode("utf-8", errors="replace")
        inner_doc = hl.parse_markdown(inner_txt)
        prefix_hdr = _extract_prefix_table_header(raw_bytes[: span.inner_start])
        if prefix_hdr is not None and hl.is_cards_table_header(prefix_hdr[1]):
            chosen_hdr = prefix_hdr[1]
            data_blocks = [b for b in inner_doc.blocks if b.kind == "table_row" and not b.is_separator]
        else:
            for tbl in _group_table_blocks(inner_doc.blocks, 0, len(inner_doc.lines)):
                if len(tbl) >= 2 and not tbl[0].is_separator and tbl[1].is_separator and hl.is_cards_table_header(tbl[0].cells):
                    chosen_hdr = tbl[0].cells
                    data_blocks = [b for b in tbl[2:] if not b.is_separator]
                    break

    if chosen_hdr is None:
        full_txt = raw_bytes.decode("utf-8-sig", errors="replace")
        doc = hl.parse_markdown(full_txt)
        sec_start = 0
        sec_end = len(doc.lines)
        found_list_sec = False
        for b in doc.blocks:
            if b.kind == "heading" and b.level <= 2:
                if not found_list_sec and b.level == 2 and ("任务卡清单" in b.title or "卡清单" in b.title):
                    found_list_sec = True
                    sec_start = b.start_line
                elif found_list_sec:
                    sec_end = b.start_line
                    break
        cand_groups = _group_table_blocks(doc.blocks, sec_start, sec_end) if found_list_sec else []
        matching = [
            t
            for t in cand_groups
            if len(t) >= 2 and not t[0].is_separator and t[1].is_separator and hl.is_cards_table_header(t[0].cells)
        ]
        if not matching:
            excluded: list[tuple[int, int]] = []
            cur_excl: Optional[int] = None
            for b in doc.blocks:
                if b.kind == "heading" and b.level <= 2:
                    if cur_excl is not None:
                        excluded.append((cur_excl, b.start_line))
                        cur_excl = None
                    if b.level == 2 and any(k in b.title for k in ("卡面规矩", "规矩", "规范", "规则", "要求", "约束", "谁改")):
                        cur_excl = b.start_line
            if cur_excl is not None:
                excluded.append((cur_excl, len(doc.lines)))
            non_rules = [b for b in doc.blocks if not any(es <= b.start_line and b.end_line <= ee for es, ee in excluded)]
            matching = [
                t
                for t in _group_table_blocks(non_rules, 0, len(doc.lines))
                if len(t) >= 2 and not t[0].is_separator and t[1].is_separator and hl.is_cards_table_header(t[0].cells)
            ]
        if matching:
            chosen_hdr = matching[0][0].cells
            data_blocks = [b for b in matching[0][2:] if not b.is_separator]

    if chosen_hdr is None:
        return {}, {}
    col_map = _match_cards_header_columns(chosen_hdr)
    if col_map is None:
        return {}, {}
    id_col, name_col, state_col, dep_col, file_col = col_map

    by_id: dict[str, list[ExistingIndexCardRow]] = {}
    by_id_file: dict[tuple[str, str], ExistingIndexCardRow] = {}
    target_cols = len(chosen_hdr)
    for b in data_blocks:
        row_cells = _rejoin_unbalanced_paren_cells(b.cells, target_cols)
        raw_cid = row_cells[id_col].strip(" *`") if id_col < len(row_cells) else ""
        if not raw_cid or raw_cid.startswith("【") or hl.PLACEHOLDER_RE.search(raw_cid):
            continue
        raw_name = row_cells[name_col].strip() if name_col < len(row_cells) else ""
        if raw_cid.upper() in ("TX", "TY", "TZ") and ("【例" in raw_name or "示例" in raw_name):
            continue
        if hl.PLACEHOLDER_RE.search(raw_name) or (raw_name.startswith("【") and raw_name.endswith("】")):
            raw_name = ""
        raw_state = row_cells[state_col].strip() if state_col < len(row_cells) else ""
        raw_dep = row_cells[dep_col].strip() if dep_col is not None and dep_col < len(row_cells) else ""
        if hl.PLACEHOLDER_RE.search(raw_dep) or (raw_dep.startswith("【") and raw_dep.endswith("】")):
            raw_dep = ""
        raw_file = row_cells[file_col].strip(" *`") if file_col is not None and file_col < len(row_cells) else ""
        fname_key = Path(raw_file).name.lower() if raw_file and raw_file not in ("—", "-", "--") else ""

        row_obj = ExistingIndexCardRow(
            card_id=raw_cid,
            task_name=raw_name,
            state_cell=raw_state,
            depends=raw_dep,
            filename_key=fname_key,
        )
        cu = raw_cid.upper()
        by_id.setdefault(cu, []).append(row_obj)
        if fname_key:
            by_id_file.setdefault((cu, fname_key), row_obj)
    return by_id, by_id_file


def match_cards_to_index_rows(
    card_entries: Sequence[tuple[str, Path]],
    idx_by_id: dict[str, list[ExistingIndexCardRow]],
    idx_by_id_file: dict[tuple[str, str], ExistingIndexCardRow],
) -> dict[Path, Optional[ExistingIndexCardRow]]:
    """Map each card file to its existing index row without cross-contaminating duplicate card_ids."""
    disk_fnames = {fp.name.lower() for _, fp in card_entries}
    used_rows: set[int] = set()
    matched: dict[Path, Optional[ExistingIndexCardRow]] = {}

    # Pass 1: exact (card_id, filename) match
    for cid, fp in card_entries:
        cu = cid.upper()
        exact = idx_by_id_file.get((cu, fp.name.lower()))
        if exact is not None:
            matched[fp] = exact
            used_rows.add(id(exact))

    # Pass 2: fallback by card_id only when the index row has no filename or its filename is not another disk card
    for cid, fp in card_entries:
        if fp in matched:
            continue
        cu = cid.upper()
        chosen: Optional[ExistingIndexCardRow] = None
        for cand in idx_by_id.get(cu, ()):
            if id(cand) in used_rows:
                continue
            if cand.filename_key and cand.filename_key in disk_fnames:
                continue
            chosen = cand
            used_rows.add(id(cand))
            break
        matched[fp] = chosen

    return matched


def _paren_depth(text: str) -> int:
    depth = 0
    for sp in hl.parse_inlines(text):
        if sp.kind == "code":
            continue
        for ch in sp.raw:
            if ch in ("（", "("):
                depth += 1
            elif ch in ("）", ")") and depth > 0:
                depth -= 1
    return depth


def _rejoin_unbalanced_paren_cells(cells: Sequence[str], target_cols: int) -> list[str]:
    out = list(cells)
    if len(out) <= target_cols:
        return out
    idx = 0
    while idx < len(out) - 1 and len(out) > target_cols:
        if _paren_depth(out[idx]) > 0:
            out[idx] = f"{out[idx]} | {out[idx + 1]}".strip()
            del out[idx + 1]
        else:
            idx += 1
    return out


def extract_index_state_note(state_cell: str, card_sym: Optional[str]) -> str:
    """Extract trailing parenthetical note from existing index state cell verbatim."""
    s = state_cell.strip()
    if not s:
        return ""
    m_st = hl.STATE_RE.search(s)
    if m_st:
        tail = s[m_st.end() :].lstrip("\ufe0f \t*")
        m_w = re.match(r"^([^\s（(【\[<；;，,。/|`*—–\-]*)(.*)$", tail)
        rem = (m_w.group(2) if m_w else tail).strip()
        if rem and (rem[0] not in ("（", "(") or rem[-1] not in ("）", ")")):
            m_p = re.search(r"([（(].*[）)])$", rem)
            rem = m_p.group(1).strip() if m_p else ""
    else:
        m_p = re.search(r"([（(].*[）)])$", s)
        rem = m_p.group(1).strip() if m_p else ""

    if not rem or rem[0] not in ("（", "(") or rem[-1] not in ("）", ")"):
        return ""
    if hl.PLACEHOLDER_RE.search(rem):
        return ""
    if rem in ("（不可派）", "(不可派)") and card_sym != "🟠":
        return ""
    return rem


def resolve_card_fields(
    hdr: hl.CardHeaderInfo,
    fp: Path,
    idx_row: Optional[ExistingIndexCardRow],
) -> tuple[str, str]:
    """Resolve (task_name, depends) following 0.5.1 Convention 1 priority order:
    1) New card header (# H1 + > 依赖：) -> 2) Existing index row -> 3) Filename after '_'."""
    if hdr.has_new_header:
        tname = hdr.task_name or fp.stem
        dep = hdr.depends or "—"
        return normalize_task_name(tname), dep

    stem_after_us = fp.stem.split("_", 1)[1].strip() if "_" in fp.stem else ""
    fallback_name = stem_after_us if stem_after_us else (hdr.task_name or fp.stem)

    if idx_row is not None:
        tname = idx_row.task_name if idx_row.task_name else fallback_name
        dep = idx_row.depends if idx_row.depends else "—"
        return normalize_task_name(tname), dep

    return normalize_task_name(fallback_name), "—"


def collect_cards(
    root: Path,
    cfg: hl.HandoffConfig,
    *,
    index_raw_override: Optional[bytes] = None,
) -> tuple[list[CardBoardRow], list[str], list[str]]:
    cards_dir = root / cfg.cards_dir
    if not cards_dir.is_dir():
        return [], [], []

    idx_fp = root / cfg.index_file
    if index_raw_override is not None:
        idx_bytes = index_raw_override
    elif idx_fp.is_file():
        idx_bytes = idx_fp.read_bytes()
    else:
        idx_bytes = b""
    idx_by_id, idx_by_id_file = parse_existing_index_cards(idx_bytes)

    index_parent = idx_fp.parent
    raw_cards = sorted(fp for fp in cards_dir.glob("*.md") if "复核" not in fp.stem)
    parsed_cards: list[tuple[Path, str, hl.CardHeaderInfo, str]] = []
    for fp in raw_cards:
        text = hl.read_utf8(fp)
        hdr = hl.parse_card_header(text, fp.stem)
        cid = (hdr.card_id or hl.extract_card_id(fp.stem)).strip()
        parsed_cards.append((fp, text, hdr, cid))

    idx_row_map = match_cards_to_index_rows([(cid, fp) for fp, _, _, cid in parsed_cards], idx_by_id, idx_by_id_file)

    rows: list[CardBoardRow] = []
    by_cid_files: dict[str, list[str]] = {}
    by_cid_disp: dict[str, str] = {}
    unparsed_files: list[str] = []

    for fp, text, hdr, cid in parsed_cards:
        cu = cid.upper()
        idx_row = idx_row_map.get(fp)

        tname, dep = resolve_card_fields(hdr, fp, idx_row)
        sym, base_state_label = hl.parse_card_state_label(text)
        if sym is None:
            unparsed_files.append(fp.name)
            checked = False
            state_label = "❓未知状态"
        else:
            checked = sym in hl.CLOSED
            note = extract_index_state_note(idx_row.state_cell, sym) if idx_row is not None else ""
            state_label = base_state_label + note

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
                short_name=tname,
                checked=checked,
                state_sym=sym,
                state_label=state_label,
                depends=dep,
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


def _extract_prefix_table_header(prefix_bytes: bytes) -> Optional[tuple[str, tuple[str, ...]]]:
    """If prefix ends right after a Markdown table header + separator row, return (raw_header_line, header_cells)."""
    txt = prefix_bytes.decode("utf-8", errors="replace")
    raw_lines = [ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("<!--")]
    if len(raw_lines) < 2 or not (
        raw_lines[-2].startswith("|")
        and raw_lines[-1].startswith("|")
        and bool(re.fullmatch(r"\|[\s:|\-]+\|?", raw_lines[-1]))
    ):
        return None
    doc = hl.parse_markdown(txt)
    non_cm = [b for b in doc.blocks if b.kind != "html_comment"]
    if (
        len(non_cm) >= 2
        and non_cm[-2].kind == "table_row"
        and non_cm[-1].kind == "table_row"
        and not non_cm[-2].is_separator
        and non_cm[-1].is_separator
        and non_cm[-1].start_line == non_cm[-2].end_line
    ):
        return non_cm[-2].lines[0].strip(), non_cm[-2].cells
    return None


def _prefix_has_table_header(prefix_bytes: bytes) -> bool:
    return _extract_prefix_table_header(prefix_bytes) is not None


def validate_board_marker_region(raw_bytes: bytes, span: MarkerSpan) -> tuple[bool, str]:
    """Verify existing content inside board marker region consists only of task checkbox list items (or is empty)."""
    inner_txt = raw_bytes[span.inner_start : span.inner_end].decode("utf-8", errors="replace")
    inner_doc = hl.parse_markdown(inner_txt)
    content_blocks = [b for b in inner_doc.blocks if b.kind != "html_comment"]
    if not content_blocks:
        return True, ""

    kind_labels = {
        "table_row": "表格",
        "heading": "标题",
        "paragraph": "普通段落",
        "fenced_code": "代码块",
        "indented_code": "缩进代码块",
    }
    for b in content_blocks:
        sample = b.lines[0].strip()[:40] if b.lines else ""
        if b.kind != "list_item":
            lbl = kind_labels.get(b.kind, b.kind)
            return (
                False,
                f"board 标记区内含非看板内容（发现{lbl} `{sample}`；标记内只应包含 `- [ ]` / `- [x]` 任务看板行），为防误覆盖拒绝写入",
            )
        if b.bullet not in ("-", "*", "+") or b.checkbox is None:
            return (
                False,
                f"board 标记区内含非看板列表项（`{sample}` 缺少 `[ ]` / `[x]` 勾选框），为防误覆盖拒绝写入",
            )
    return True, ""


def validate_cards_marker_region(raw_bytes: bytes, span: MarkerSpan) -> tuple[bool, str]:
    """Verify existing table header in/above cards marker region contains '编号', '任务名', '状态' before overwriting."""
    inner_txt = raw_bytes[span.inner_start : span.inner_end].decode("utf-8", errors="replace")
    inner_doc = hl.parse_markdown(inner_txt)
    content_blocks = [b for b in inner_doc.blocks if b.kind != "html_comment"]

    prefix_hdr = _extract_prefix_table_header(raw_bytes[: span.inner_start])
    if prefix_hdr is not None:
        hdr_raw, hdr_cells = prefix_hdr
        if not hl.is_cards_table_header(hdr_cells):
            return (
                False,
                f"cards 标记上方现有表头 `{hdr_raw}` 不符合卡清单表要求（须同时含“编号”“任务名”“状态”三列），拒绝写入",
            )
        cleaned = [re.sub(r"[*_~`\s]+", "", re.sub(r"<!--.*?-->", "", c, flags=re.S)) for c in hdr_cells]
        if len(cleaned) != 5 or not ("编号" in cleaned[0] and "任务名" in cleaned[1] and "状态" in cleaned[2]):
            return (
                False,
                f"cards 标记置于表头下方时现有表头 `{hdr_raw}` 列顺序与生成行不一致，请将 <!-- cards:start --> 移至表头上方，拒绝写入",
            )
        if any(b.kind != "table_row" or b.is_separator for b in content_blocks):
            return False, "cards 标记置于表头下方时标记内含非数据行内容，拒绝覆盖写入"
        for b1, b2 in zip(content_blocks, content_blocks[1:]):
            if b2.start_line != b1.end_line:
                return False, "cards 标记区内存在多段表格，为防误覆盖拒绝写入"
        return True, ""

    if not content_blocks:
        # Empty <!-- cards:start --> ... <!-- cards:end --> has no existing content at risk
        return True, ""

    if any(b.kind != "table_row" for b in content_blocks):
        return (
            False,
            "cards 标记区内含非表格内容，为防误覆盖拒绝写入（标记内只应包含表头含“编号”“任务名”“状态”三列的卡清单表）",
        )
    for b1, b2 in zip(content_blocks, content_blocks[1:]):
        if b2.start_line != b1.end_line:
            return False, "cards 标记区内存在多张表格，为防误覆盖其他表格拒绝写入（请只用标记包裹卡清单表）"

    hdr_blk = content_blocks[0]
    hdr_raw = hdr_blk.lines[0].strip()
    if hdr_blk.is_separator:
        return False, f"cards 标记区内缺少表头行（首行为分隔行 `{hdr_raw}`），拒绝写入"
    if len(content_blocks) < 2 or not content_blocks[1].is_separator:
        return False, f"cards 标记区内缺少表格分隔行（首行 `{hdr_raw}`），拒绝写入"
    if not hl.is_cards_table_header(hdr_blk.cells):
        return (
            False,
            f"cards 标记区内现有表头 `{hdr_raw}` 不符合卡清单表要求（须同时含“编号”“任务名”“状态”三列），拒绝写入",
        )
    return True, ""


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
        if tag == "board":
            b_ok, b_err = validate_board_marker_region(raw_bytes, span)
            if not b_ok:
                errors.append(f"{disp_name}：{b_err}")
                continue
        elif tag == "cards":
            hdr_ok, hdr_err = validate_cards_marker_region(raw_bytes, span)
            if not hdr_ok:
                errors.append(f"{disp_name}：{hdr_err}")
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

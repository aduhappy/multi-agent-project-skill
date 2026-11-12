#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""upgrade.py — 将已有 multi-agent-project 项目骨架升级到当前版本（默认仅预览，绝不动入口/任务卡/STATUS）

用法：
    python <skill>/assets/upgrade.py [PATH]              # 默认只预览（同 --dry-run），不写盘
    python <skill>/assets/upgrade.py [PATH] --apply      # 执行升级（写盘前自动备份到 文档/_作废/升级前_<日期>/）
    python scripts/upgrade.py [PATH] --skill-dir DIR     # 从项目内调用时可显式指定技能仓库或 assets 目录
    python scripts/upgrade.py --version                  # 查看脚本版本号

四项自动操作（仅 --apply 时写盘）：
  1. 替换 `scripts/` 下的技能配套脚本（handoff_lib.py、check_handoff.py、archive_status.py、sync_board.py、upgrade.py 等）
  2. 写入新版 `<docs_dir>/协作规矩.md`
  3. 将任务卡索引里旧的“## 卡面规矩”整节原样移存至 `<docs_dir>/_作废/卡面规矩_旧.md`，原处仅留一行指针
  4. 在任务卡索引的卡清单表上下加上 `<!-- cards:start -->` 与 `<!-- cards:end -->` 标记

硬性边界：
  - **任何情况下绝不写入** `AGENTS.md`、已有任务卡（`<cards_dir>/*.md`）、`STATUS.md`。
  - `AGENTS.md` 需手工调整处仅打印核对清单（§5 与规矩文件重复可删的条目、§4 如何添加看板标记）。
  - 幂等可重入：重复运行或中途中断后重跑不会重复修改，已是最新布局的项目运行无任何改动。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence

sys.dont_write_bytecode = True

__version__ = "0.5.0"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
try:
    import handoff_lib as hl
except ImportError as _exc:
    if isinstance(_exc, ModuleNotFoundError) and getattr(_exc, "name", None) == "handoff_lib":
        print("错误：未找到 handoff_lib.py，请把 handoff_lib.py 一起复制到同一目录。", file=sys.stderr)
        raise SystemExit(2)
    raise

try:
    import sync_board as sb
except ImportError as _sb_exc:
    if isinstance(_sb_exc, ModuleNotFoundError) and getattr(_sb_exc, "name", None) == "sync_board":
        sb = None  # type: ignore[assignment]
    else:
        raise


_SKILL_SCRIPT_NAMES: tuple[str, ...] = (
    "handoff_lib.py",
    "check_handoff.py",
    "archive_status.py",
    "sync_board.py",
    "upgrade.py",
    "fingerprint.py",
)

_DUP_SEC5_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("代码归位", re.compile(r"代码归位")),
    ("收工规矩", re.compile(r"收工规矩")),
    ("独立复核分级阀门", re.compile(r"独立复核分级阀门")),
    ("开跑先自证身份", re.compile(r"开跑先自证身份")),
    ("关键测量双源交叉", re.compile(r"关键测量双源交叉")),
    ("关键数字单一来源", re.compile(r"关键数字单一来源")),
    ("坏产物退役隔离", re.compile(r"坏产物退役隔离")),
)

_SUSPECT_RULES_KEYWORDS: tuple[str, ...] = ("规矩", "规范", "谁改", "纪律", "约定", "铁律", "须知", "守则")
_LEGACY_RULES_SIGNATURES: tuple[str, ...] = ("谁改卡面哪里", "停止条件分两类", "别让卡越写越大", "复核意见分两节")
_CN_HEADING_LEVELS: dict[int, str] = {3: "三", 4: "四", 5: "五", 6: "六"}


@dataclass(frozen=True)
class PlannedWrite:
    rel_path: str
    abs_path: Path
    new_bytes: bytes
    existed: bool
    summary: str
    backup_needed: bool = True


@dataclass(frozen=True)
class IndexTransformResult:
    new_bytes: bytes
    extracted_old_rules: Optional[bytes]
    changes: list[str]
    cards_status: str  # "added" | "already_marked" | "not_found" | "malformed" | "no_index"
    rules_status: str = "not_found"  # "migrated" | "already_pointer" | "not_found" | "no_index"
    suspected_rules_headings: tuple[str, ...] = ()
    wrapped_table_header: str = ""
    wrapped_table_lines: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class UpgradeReport:
    applied: bool
    writes: list[PlannedWrite]
    backup_dir: Optional[Path]
    backed_up_files: list[str]
    agents_dup_items: list[str]
    agents_needs_board_markers: bool
    agents_needs_exception_subsec: bool
    index_rel: str = "文档/任务卡_README.md"
    cards_status: str = "no_index"
    rules_status: str = "no_index"
    suspected_rules_headings: tuple[str, ...] = ()
    wrapped_table_header: str = ""
    wrapped_table_lines: tuple[int, int] = (0, 0)


def resolve_skill_assets(explicit_skill_dir: Optional[str] = None) -> Path:
    candidates: list[Path] = []
    if explicit_skill_dir:
        p = Path(explicit_skill_dir).expanduser().resolve()
        candidates.extend([p, p / "assets"])
    candidates.extend([_HERE, _HERE.parent / "assets"])
    home = Path.home()
    for sub in (
        ".mirasim/skills/multi-agent-project/assets",
        ".agents/skills/multi-agent-project/assets",
        ".claude/skills/multi-agent-project/assets",
        ".gemini/skills/multi-agent-project/assets",
        ".codex/skills/multi-agent-project/assets",
    ):
        candidates.append((home / sub).resolve())

    for cand in candidates:
        if (cand / hl.RULES_FILENAME).is_file() and (cand / "check_handoff.py").is_file():
            return cand
    raise FileNotFoundError(
        "未定位到技能仓库的 assets/ 目录（需含 协作规矩.md 与 check_handoff.py）；请通过 --skill-dir 指定技能目录。"
    )


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


def _assert_never_protected(target: Path, root: Path, cfg: hl.HandoffConfig) -> None:
    resolved = target.resolve()
    agents_p = (root / "AGENTS.md").resolve()
    status_p = (root / "STATUS.md").resolve()
    cards_dir_p = (root / cfg.cards_dir).resolve()
    if resolved == agents_p or resolved == status_p:
        raise RuntimeError(f"安全拦截：upgrade.py 严禁写入受保护文件 {resolved}")
    try:
        resolved.relative_to(cards_dir_p)
    except ValueError:
        pass
    else:
        raise RuntimeError(f"安全拦截：upgrade.py 严禁写入任务卡目录内文件 {resolved}")


def _is_already_rules_pointer(sec_lines: list[str]) -> bool:
    body_non_empty = [ln.strip() for ln in sec_lines[1:] if ln.strip()]
    if not body_non_empty or len(body_non_empty) > 3:
        return False
    joined = "\n".join(body_non_empty)
    if "协作规矩.md" not in joined:
        return False
    return not any(kw in joined for kw in ("谁改卡面哪里", "别让卡越写越大", "停止条件分两类"))


def _collect_suspected_rules_headings(doc: hl.MarkdownDoc, lines: list[str]) -> tuple[str, ...]:
    """Find H2+ headings suspected to be renamed/demoted rules sections when `## 卡面规矩` is absent."""
    suspects: list[str] = []
    seen_starts: set[int] = set()
    for b in doc.blocks:
        if b.kind == "heading" and b.level >= 2:
            if any(kw in b.title for kw in _SUSPECT_RULES_KEYWORDS):
                seen_starts.add(b.start_line)
                hashes = "#" * b.level
                if b.level == 2:
                    suspects.append(f"`{hashes} {b.title}`（第 {b.start_line + 1} 行）")
                else:
                    lvl_cn = _CN_HEADING_LEVELS.get(b.level, str(b.level))
                    suspects.append(f"`{hashes} {b.title}`（{lvl_cn}级标题，第 {b.start_line + 1} 行）")

    # Fallback: scan H2 sections whose body contains legacy rules signatures even if title lacked keywords
    h2_blocks = [b for b in doc.blocks if b.kind == "heading" and b.level <= 2]
    for idx, hb in enumerate(h2_blocks):
        if hb.level != 2 or hb.start_line in seen_starts:
            continue
        sec_end = h2_blocks[idx + 1].start_line if idx + 1 < len(h2_blocks) else len(lines)
        sec_txt = "\n".join(lines[hb.start_line : sec_end])
        if any(sig in sec_txt for sig in _LEGACY_RULES_SIGNATURES):
            suspects.append(f"`## {hb.title}`（第 {hb.start_line + 1} 行，正文含旧规矩内容）")
    return tuple(suspects)


def _group_contiguous_tables(blocks: Sequence[hl.Block], start_ln: int, end_ln: int) -> list[list[hl.Block]]:
    tbl_rows = [
        b for b in blocks if b.kind == "table_row" and start_ln <= b.start_line and b.end_line <= end_ln
    ]
    tables: list[list[hl.Block]] = []
    for row in tbl_rows:
        if tables and row.start_line == tables[-1][-1].end_line:
            tables[-1].append(row)
        else:
            tables.append([row])
    return tables


def _transform_index_file(
    raw_bytes: bytes,
    cfg: hl.HandoffConfig,
) -> IndexTransformResult:
    """Transform index file: archive old rules section & wrap matching card checklist table."""
    eol_str = hl.detect_eol(raw_bytes)
    has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
    text = raw_bytes.decode("utf-8-sig")
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    trailing_nl = norm.endswith("\n")
    lines = norm.splitlines()
    orig_line_nums = list(range(1, len(lines) + 1))
    changes: list[str] = []
    extracted_old_rules: Optional[bytes] = None

    # Step A: Move old `## 卡面规矩` section to 卡面规矩_旧.md and leave 1-line pointer
    doc = hl.parse_markdown("\n".join(lines))
    rules_start: Optional[int] = None
    rules_end: Optional[int] = None
    for b in doc.blocks:
        if b.kind == "heading" and b.level <= 2:
            if rules_start is None:
                if b.level == 2 and b.title.startswith("卡面规矩"):
                    rules_start = b.start_line
            else:
                rules_end = b.start_line
                break
    if rules_start is not None and rules_end is None:
        rules_end = len(lines)

    if rules_start is not None and rules_end is not None:
        sec_slice = lines[rules_start:rules_end]
        if _is_already_rules_pointer(sec_slice):
            rules_status = "already_pointer"
            suspected_headings: tuple[str, ...] = ()
        else:
            rules_status = "migrated"
            suspected_headings = ()
            old_trimmed = list(sec_slice)
            while old_trimmed and not old_trimmed[-1].strip():
                old_trimmed.pop()
            extracted_old_rules = (eol_str.join(old_trimmed) + eol_str).encode("utf-8")
            heading_ln = sec_slice[0]
            pointer_ln = (
                f"> 卡面规矩、通用铁律与各角色须知已迁入 `{cfg.docs_dir}/{hl.RULES_FILENAME}`"
                f"（唯一出处，项目不改它；旧版原文存档于 `{cfg.docs_dir}/_作废/卡面规矩_旧.md`）。"
            )
            replacement = [heading_ln, "", pointer_ln]
            if rules_end < len(lines):
                replacement.append("")
            orig_head_ln = orig_line_nums[rules_start]
            lines = lines[:rules_start] + replacement + lines[rules_end:]
            orig_line_nums = (
                orig_line_nums[:rules_start]
                + [orig_head_ln]
                + [0] * (len(replacement) - 1)
                + orig_line_nums[rules_end:]
            )
            changes.append(f"将旧“卡面规矩”节迁出至 {cfg.docs_dir}/_作废/卡面规矩_旧.md 并留指针")
    else:
        rules_status = "not_found"
        suspected_headings = _collect_suspected_rules_headings(doc, lines)

    # Step B: Wrap card checklist table (must contain '编号', '任务名', '状态') with <!-- cards:start/end -->
    current_bytes_probe = ("\n".join(lines) + ("\n" if trailing_nl else "")).encode("utf-8")
    if sb is not None:
        marker_state = sb.find_marker_span_bytes(current_bytes_probe, "cards").state
    else:
        marker_state = "ok" if re.search(r"<!--\s*cards:(?:start|end)\s*-->", "\n".join(lines)) else "missing"

    cards_status = "already_marked" if marker_state == "ok" else ("malformed" if marker_state == "malformed" else "not_found")
    wrapped_hdr = ""
    wrapped_span = (0, 0)

    if marker_state == "missing":
        doc2 = hl.parse_markdown("\n".join(lines))
        sec_start = 0
        sec_end = len(lines)
        found_list_sec = False
        for b in doc2.blocks:
            if b.kind == "heading" and b.level <= 2:
                if not found_list_sec and b.level == 2 and ("任务卡清单" in b.title or "卡清单" in b.title):
                    found_list_sec = True
                    sec_start = b.start_line
                elif found_list_sec:
                    sec_end = b.start_line
                    break
        if found_list_sec:
            cand_tables = _group_contiguous_tables(doc2.blocks, sec_start, sec_end)
        else:
            excluded_ranges: list[tuple[int, int]] = []
            cur_excl: Optional[int] = None
            for b in doc2.blocks:
                if b.kind == "heading" and b.level <= 2:
                    if cur_excl is not None:
                        excluded_ranges.append((cur_excl, b.start_line))
                        cur_excl = None
                    if b.level == 2 and any(k in b.title for k in ("卡面规矩", "规矩", "规范", "谁改")):
                        cur_excl = b.start_line
            if cur_excl is not None:
                excluded_ranges.append((cur_excl, len(lines)))
            non_rules_blocks = [
                b
                for b in doc2.blocks
                if not any(es <= b.start_line and b.end_line <= ee for es, ee in excluded_ranges)
            ]
            cand_tables = _group_contiguous_tables(non_rules_blocks, 0, len(lines))
        matching_tables = [
            tbl
            for tbl in cand_tables
            if len(tbl) >= 2
            and not tbl[0].is_separator
            and tbl[1].is_separator
            and hl.is_cards_table_header(tbl[0].cells)
        ]
        if matching_tables:
            chosen = matching_tables[0]
            first_tbl_ln = chosen[0].start_line
            last_tbl_ln = chosen[-1].end_line
            orig_s = orig_line_nums[first_tbl_ln] or (first_tbl_ln + 1)
            orig_e = orig_line_nums[last_tbl_ln - 1] or last_tbl_ln
            wrapped_hdr = lines[first_tbl_ln].strip()
            wrapped_span = (orig_s, orig_e)
            cards_status = "added"
            lines = (
                lines[:first_tbl_ln]
                + ["<!-- cards:start -->"]
                + lines[first_tbl_ln:last_tbl_ln]
                + ["<!-- cards:end -->"]
                + lines[last_tbl_ln:]
            )
            changes.append(
                "在任务卡清单表上下添加 <!-- cards:start --> 与 <!-- cards:end --> 标记"
                f"（第 {orig_s}–{orig_e} 行，表头第 {orig_s} 行：{wrapped_hdr}）"
            )
        else:
            cards_status = "not_found"

    if not changes:
        return IndexTransformResult(
            new_bytes=raw_bytes,
            extracted_old_rules=None,
            changes=[],
            cards_status=cards_status,
            rules_status=rules_status,
            suspected_rules_headings=suspected_headings,
            wrapped_table_header=wrapped_hdr,
            wrapped_table_lines=wrapped_span,
        )

    rebuilt = eol_str.join(lines) + (eol_str if trailing_nl else "")
    out_bytes = (b"\xef\xbb\xbf" if has_bom else b"") + rebuilt.encode("utf-8")
    return IndexTransformResult(
        new_bytes=out_bytes,
        extracted_old_rules=extracted_old_rules,
        changes=changes,
        cards_status=cards_status,
        rules_status=rules_status,
        suspected_rules_headings=suspected_headings,
        wrapped_table_header=wrapped_hdr,
        wrapped_table_lines=wrapped_span,
    )


def inspect_agents_readonly(root: Path) -> tuple[list[str], bool, bool]:
    """Read AGENTS.md without modifying it; return (dup_sec5_items, needs_board_markers, needs_exception_subsec)."""
    ag_fp = root / "AGENTS.md"
    if not ag_fp.is_file():
        return [], True, True
    raw = ag_fp.read_bytes()
    txt = hl.read_utf8(ag_fp)
    doc = hl.parse_markdown(txt, strip_comments=False)

    sec5_blocks = hl.extract_section_blocks(doc, "5", {"铁律 / 约定", "铁律/约定", "铁律"})
    dup_items: list[str] = []
    has_exc_subsec = False
    for b in sec5_blocks[1:]:
        vis = b.visible_text(include_code=True)
        if "本项目例外" in vis:
            has_exc_subsec = True
        if b.kind == "list_item" and b.indent == 0:
            first_ln = b.visible_lines(include_code=True)[0] if b.visible_lines(include_code=True) else ""
            for label, pat in _DUP_SEC5_PATTERNS:
                if pat.search(first_ln) and label not in dup_items:
                    dup_items.append(label)

    if sb is not None:
        needs_markers = sb.find_marker_span_bytes(raw, "board").state == "missing"
    else:
        needs_markers = not bool(re.search(r"<!--\s*board:start\s*-->", txt))
    return dup_items, needs_markers, not has_exc_subsec


def plan_and_run_upgrade(
    root: Path,
    *,
    apply: bool = False,
    skill_assets: Optional[Path] = None,
    today: Optional[date] = None,
) -> UpgradeReport:
    cfg = hl.load_handoff_config(root)
    for w in cfg.warnings:
        print(f"提示：{w}", file=sys.stderr)

    assets_dir = skill_assets if skill_assets is not None else resolve_skill_assets()
    cur_day = today or datetime.now().date()
    planned: list[PlannedWrite] = []

    # 1. Scripts in scripts/
    scripts_dir = root / "scripts"
    for fn in _SKILL_SCRIPT_NAMES:
        src_fp = assets_dir / fn
        if not src_fp.is_file():
            continue
        dst_fp = scripts_dir / fn
        _assert_never_protected(dst_fp, root, cfg)
        src_bytes = src_fp.read_bytes()
        existed = dst_fp.is_file()
        if existed and dst_fp.read_bytes() == src_bytes:
            continue
        rel = dst_fp.relative_to(root).as_posix()
        planned.append(
            PlannedWrite(
                rel_path=rel,
                abs_path=dst_fp,
                new_bytes=src_bytes,
                existed=existed,
                summary=("更新脚本 " if existed else "新增脚本 ") + rel,
                backup_needed=existed,
            )
        )

    # 2. <docs_dir>/协作规矩.md
    rules_src = assets_dir / hl.RULES_FILENAME
    rules_dst = root / cfg.docs_dir / hl.RULES_FILENAME
    _assert_never_protected(rules_dst, root, cfg)
    rules_bytes = rules_src.read_bytes()
    rules_existed = rules_dst.is_file()
    if not rules_existed or rules_dst.read_bytes() != rules_bytes:
        rel = rules_dst.relative_to(root).as_posix()
        planned.append(
            PlannedWrite(
                rel_path=rel,
                abs_path=rules_dst,
                new_bytes=rules_bytes,
                existed=rules_existed,
                summary=("更新规矩文件 " if rules_existed else "新增规矩文件 ") + rel,
                backup_needed=rules_existed,
            )
        )

    # 3 & 4. <index_file>: move old ## 卡面规矩 to <docs_dir>/_作废/卡面规矩_旧.md + add cards markers
    index_fp = root / cfg.index_file
    index_rel = cfg.index_file
    cards_status = "no_index"
    rules_status = "no_index"
    suspected_headings: tuple[str, ...] = ()
    wrapped_hdr = ""
    wrapped_span = (0, 0)
    if index_fp.is_file():
        _assert_never_protected(index_fp, root, cfg)
        index_rel = index_fp.relative_to(root).as_posix()
        idx_orig = index_fp.read_bytes()
        idx_res = _transform_index_file(idx_orig, cfg)
        cards_status = idx_res.cards_status
        rules_status = idx_res.rules_status
        suspected_headings = idx_res.suspected_rules_headings
        wrapped_hdr = idx_res.wrapped_table_header
        wrapped_span = idx_res.wrapped_table_lines
        if idx_res.extracted_old_rules is not None:
            archive_old_fp = root / cfg.docs_dir / "_作废" / "卡面规矩_旧.md"
            _assert_never_protected(archive_old_fp, root, cfg)
            old_existed = archive_old_fp.is_file()
            if not old_existed or archive_old_fp.read_bytes() != idx_res.extracted_old_rules:
                rel_old = archive_old_fp.relative_to(root).as_posix()
                planned.append(
                    PlannedWrite(
                        rel_path=rel_old,
                        abs_path=archive_old_fp,
                        new_bytes=idx_res.extracted_old_rules,
                        existed=old_existed,
                        summary=f"归档旧卡面规矩至 {rel_old}",
                        backup_needed=old_existed,
                    )
                )
        if idx_res.new_bytes != idx_orig:
            planned.append(
                PlannedWrite(
                    rel_path=index_rel,
                    abs_path=index_fp,
                    new_bytes=idx_res.new_bytes,
                    existed=True,
                    summary=f"修改 {index_rel}（{'；'.join(idx_res.changes)}）",
                    backup_needed=True,
                )
            )

    dup_items, needs_board_markers, needs_exc_subsec = inspect_agents_readonly(root)

    backup_dir: Optional[Path] = None
    backed_up: list[str] = []
    if apply and planned:
        existing_to_backup = [pw for pw in planned if pw.existed and pw.backup_needed]
        if existing_to_backup:
            backup_dir = root / cfg.docs_dir / "_作废" / f"升级前_{cur_day.isoformat()}"
            _assert_never_protected(backup_dir, root, cfg)
            for pw in existing_to_backup:
                b_dst = backup_dir / pw.rel_path
                _assert_never_protected(b_dst, root, cfg)
                # Preserve earliest pre-upgrade backup if interrupted and re-run on the same day
                if not b_dst.exists():
                    _atomic_write_bytes(b_dst, pw.abs_path.read_bytes())
                backed_up.append(b_dst.relative_to(root).as_posix())

        for pw in planned:
            _assert_never_protected(pw.abs_path, root, cfg)
            _atomic_write_bytes(pw.abs_path, pw.new_bytes)

    return UpgradeReport(
        applied=apply,
        writes=planned,
        backup_dir=backup_dir,
        backed_up_files=backed_up,
        agents_dup_items=dup_items,
        agents_needs_board_markers=needs_board_markers,
        agents_needs_exception_subsec=needs_exc_subsec,
        index_rel=index_rel,
        cards_status=cards_status,
        rules_status=rules_status,
        suspected_rules_headings=suspected_headings,
        wrapped_table_header=wrapped_hdr,
        wrapped_table_lines=wrapped_span,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="将已有 multi-agent-project 项目升级到当前布局（默认只预览，--apply 才写盘；绝不写 AGENTS.md / 任务卡 / STATUS.md）"
    )
    parser.add_argument("path", nargs="?", default=".", help="待升级的项目或线级根目录（默认当前目录）")
    parser.add_argument("--apply", action="store_true", help="实际写盘执行升级（默认仅预览）")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写盘（默认行为）")
    parser.add_argument("--skill-dir", help="技能仓库根目录或 assets/ 目录（自动探测不到时指定）")
    parser.add_argument("--today", help="备份目录日期覆盖 YYYY-MM-DD（仅测试用）")
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.apply and args.dry_run:
        print("错误：--apply 与 --dry-run 不能同时指定。", file=sys.stderr)
        return 2

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"错误：目录不存在：{root}", file=sys.stderr)
        return 2

    cur_day = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else datetime.now().date()
    try:
        assets_dir = resolve_skill_assets(args.skill_dir)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    rep = plan_and_run_upgrade(root, apply=args.apply, skill_assets=assets_dir, today=cur_day)
    mode_str = "已执行升级（--apply）" if rep.applied else "升级预览（默认只读，加 --apply 才写盘）"
    print(f"=== {mode_str} | 目标：{root} ===")
    print("受保护不写文件：AGENTS.md、STATUS.md、已有任务卡（均未触碰）")

    cfg = hl.load_handoff_config(root)
    if not rep.writes:
        print("文件变更：0 项（已是最新状态，无需改动）。")
    else:
        print(f"文件变更（共 {len(rep.writes)} 项）：")
        for pw in rep.writes:
            print(f"  - {pw.summary}")
        if rep.applied and rep.backup_dir is not None:
            print(f"升级前备份目录：{rep.backup_dir.relative_to(root).as_posix()}/（共 {len(rep.backed_up_files)} 个文件）")
        elif not rep.applied:
            print(f"写盘前将备份原有文件至：{cfg.docs_dir}/_作废/升级前_{cur_day.isoformat()}/")

    rules_sum_map = {
        "migrated": "已迁出" if rep.applied else "待迁出",
        "already_pointer": "已完成",
        "not_found": "未做",
        "no_index": "无索引",
    }
    cards_sum_map = {
        "added": f"已圈定第 {rep.wrapped_table_lines[0]}–{rep.wrapped_table_lines[1]} 行（表头：{rep.wrapped_table_header}）",
        "already_marked": "已有标记",
        "not_found": "未找到卡清单表（需人工加标记）",
        "malformed": "已有标记但格式有误",
        "no_index": "无索引",
    }
    print(
        f"汇总：文件变更 {len(rep.writes)} 项｜规矩迁移：{rules_sum_map.get(rep.rules_status, rep.rules_status)}"
        f"｜卡清单标记：{cards_sum_map.get(rep.cards_status, rep.cards_status)}"
    )

    if rep.rules_status == "not_found":
        print(
            f"\n⚠️ 警告：旧规矩未迁出！在 {rep.index_rel} 中未找到 `## 卡面规矩` 二级标题节（规矩迁移：未做）。"
        )
        if rep.suspected_rules_headings:
            print("  索引中疑似规矩节的标题：" + "、".join(rep.suspected_rules_headings))
        else:
            print("  索引中未检出含“规矩 / 规范 / 谁改”等词的疑似标题。")
        print(
            f"  请主控人工移走旧规矩节（归档至 {cfg.docs_dir}/_作废/卡面规矩_旧.md），并在原处只留一行指向 `{cfg.docs_dir}/{hl.RULES_FILENAME}` 的指针。"
        )

    if rep.cards_status == "not_found":
        print(
            f"\n⚠️ 未找到卡清单表，请人工加标记：在 {rep.index_rel} 中未找到表头同时含“编号”“任务名”“状态”三列的表格，未自动加标记。"
        )
        print(f"  请在 {rep.index_rel} 的卡清单表上下手工添加如下标记写法：")
        print("    <!-- cards:start -->")
        print("    | 编号 | 任务名 | 状态 | 依赖 | 文件 |")
        print("    |---|---|---|---|---|")
        print("    ...")
        print("    <!-- cards:end -->")

    print("\n--- AGENTS.md 手工整理清单（脚本不自动修改 AGENTS.md） ---")
    if rep.agents_dup_items:
        print(
            "1. §5 与 `文档/协作规矩.md` 重复、可由主控手工删除并改为一行指针的通用条目："
            + "、".join(rep.agents_dup_items)
        )
    else:
        print("1. §5 未检出与 `文档/协作规矩.md` 重复的通用条目。")
    if rep.agents_needs_exception_subsec:
        print("2. §5 建议新增 `### 本项目例外` 小节（存放项目特有例外，不直接改 `文档/协作规矩.md`）。")
    else:
        print("2. §5 已含“本项目例外”。")
    if rep.agents_needs_board_markers:
        print("3. §4 任务看板列表上下可手工加上两行标记，之后运行 `python scripts/sync_board.py` 自动同步：")
        print("     <!-- board:start -->")
        print("     ...（将由 sync_board.py 从卡面自动生成）...")
        print("     <!-- board:end -->")
    else:
        print("3. §4 已含 `<!-- board:start --> … <!-- board:end -->` 标记，可直接运行 `python scripts/sync_board.py`。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

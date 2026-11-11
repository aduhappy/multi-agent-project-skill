#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""handoff_lib.py — multi-agent-project 共享 Markdown 块级解析与日期/配置工具库（纯标准库）

先把一篇 Markdown 切成带类型的块：
  - heading       标题（含层级 1–6 与行内代码标注）
  - list_item     列表项（含顶层续行、缩进列数、勾选框）
  - table_row     表格行（含单元格切分与分隔行标记）
  - fenced_code   围栏代码块（``` 或 ~~~；未闭合围栏按普通文字处理，不吞后续内容）
  - indented_code 缩进代码块（4 空格或 Tab 顶层代码块）
  - html_comment  HTML 注释块（单行或多行 <!-- ... -->）
  - paragraph     普通段落（含引用行 > ...）
行内反引号代码段以 InlineSpan(kind="code") 单独标出。
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

sys.dont_write_bytecode = True

__version__ = "0.4.1"

DATE_RE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
FLEX_DATE_TOKEN_RE = re.compile(
    r"(?<!\d)(20\d{2})(?:([-/.])(\d{1,2})\2(\d{1,2})(?![-/.]?\d)|\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日)"
)
HEADING_DATE_START_RE = re.compile(
    r"^[\[（(【]?\s*20\d{2}(?:([-/.])\d{1,2}\1\d{1,2}(?![-/.]?\d)|\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"
)
DATE_PLACEHOLDER_RE = re.compile(r"YYYY[-/.]MM[-/.]DD|YYYY\s*年\s*MM\s*月\s*DD\s*日", re.I)
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEAD_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$")
NO_SPACE_PROGRESS_HEAD_RE = re.compile(r"^ {0,3}(#{2,3})(进度回写.*)$")
LIST_ITEM_RE = re.compile(r"^([ \t]*)([-*+]|\d+[.)])(?:[ \t]+(.*)|[ \t]*)$")
CHECKBOX_PREFIX_RE = re.compile(r"^\[([ xX]?)\](.*)$")
PROMPT_TITLE_RE = re.compile(r"(?:📋|提示词)")
STATE_RE = re.compile(r"🟠|⬜|⏳|🟡|🔵|✅|⛔|🗄")
CARD_STATE_LINE_RE = re.compile(r"^(?:[-*+][ \t]+)?\**状态\**[ \t]*[:：]\**(.*)$")
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
_INLINE_DATE_EXPR = r"20\d{2}(?:[-/.]\d{1,2}[-/.]\d{1,2}|\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"
BARE_DATE_EXAMPLE_RE = re.compile(
    rf"(?:(?:例|示例)\s*[:：]?\s*T[0-9A-Za-z]+\s*进行中|e\.g\.[,\s:]*T[0-9A-Za-z]+\s+in\s+progress)"
    rf"(?:\s*(?:[（(][^）)\n]*[）)]|{_INLINE_DATE_EXPR}))?"
    rf"|(?:最近完成的事，带日期[。，,\s]*)?(?:例|示例|e\.g\.)\s*[:：,]?\s*{_INLINE_DATE_EXPR}"
    r"(?:\s*[:：]?\s*(?:数据集\s*X|Dataset\s*X)[^\n；;。）)]*)?",
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
    r"^>?\s*[-*+]\s*\**(?:当前阶段|下一步|阻塞|Current\s+stage|Next\s+step|Blockers?)\**\s*[:：]\s*(?:TODO|TBD|待填)?\s*$",
    re.I,
)
HANDOFF_INNER_HEAD_RE = re.compile(
    r"^(?:[-*+]|\d+[.、)])?\s*[\*【\[]*(?:谁做的|改了什么|怎么验证|没做什么|不确定处)"
)
HANDOFF_SECTIONS = (
    ("改了什么", re.compile(r"^\s*>?\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*[\*【\[]*改了什么")),
    ("怎么验证的", re.compile(r"^\s*>?\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*[\*【\[]*怎么验证")),
    ("没做什么", re.compile(r"^\s*>?\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*[\*【\[]*没做什么")),
    ("不确定处", re.compile(r"^\s*>?\s*(?:[-*+]|\d+[.)]|#{2,6})?\s*[\*【\[]*不确定处")),
)
SLASH_CARDS_RE = re.compile(r"(?<![A-Za-z0-9-])([A-Za-z]+\d+)([a-z](?:/[a-z])+)(?![A-Za-z0-9-])")
GENERIC_TASK_RE = re.compile(r"(?<![A-Za-z0-9-])T\d+[A-Za-z0-9-]*(?![A-Za-z0-9-])")
CLAUSE_SEP_RE = re.compile(r"[、，,;；|]")
DECISION_ID_RE = re.compile(r"[A-Za-z]+-\d+[A-Za-z0-9]*|[A-Za-z]+\d+[A-Za-z0-9]*")
EMPTY_CELL_VALUES = {"", "-", "--", "---", "—", "——", "–", "无", "none", "n/a", "/"}

# Compatibility switch isolated for Step 3 atomic commit (V3)
_STATUS_SKIP_COMMENTED_HEADINGS = False


# =====================================================================
# File & EOL Helpers
# =====================================================================


def detect_eol(raw_bytes: bytes) -> str:
    crlf = raw_bytes.count(b"\r\n")
    bare_lf = raw_bytes.count(b"\n") - crlf
    return "\r\n" if crlf > bare_lf else "\n"


def read_utf8_and_eol(path: Path) -> tuple[str, str]:
    raw_bytes = path.read_bytes()
    return raw_bytes.decode("utf-8-sig"), detect_eol(raw_bytes)


def read_utf8(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def write_with_eol(path: Path, text: str, eol: str) -> None:
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    out = norm.replace("\n", "\r\n") if eol == "\r\n" else norm
    path.write_bytes(out.encode("utf-8"))


# =====================================================================
# Configurable Directory Layout (handoff_config.json)
# =====================================================================

CONFIG_FILENAME = "handoff_config.json"
DEFAULT_DOCS_DIR = "文档"
DEFAULT_CARDS_DIR = "文档/任务卡"
DEFAULT_INDEX_FILE = "文档/任务卡_README.md"
DEFAULT_REVIEW_DIRS: tuple[str, ...] = ("文档", "reports")
ALLOWED_CONFIG_KEYS = frozenset({"docs_dir", "cards_dir", "index_file", "review_dirs"})


@dataclass(frozen=True)
class HandoffConfig:
    docs_dir: str = DEFAULT_DOCS_DIR
    cards_dir: str = DEFAULT_CARDS_DIR
    index_file: str = DEFAULT_INDEX_FILE
    review_dirs: tuple[str, ...] = DEFAULT_REVIEW_DIRS
    warnings: tuple[str, ...] = ()


def _clean_rel_path(val: object) -> Optional[str]:
    if not isinstance(val, str):
        return None
    s = val.strip().replace("\\", "/").strip("/")
    return s if s else None


def load_handoff_config(root: Path) -> HandoffConfig:
    """Load optional <root>/handoff_config.json. Never raises; falls back to defaults with warnings."""
    cfg_path = root / CONFIG_FILENAME
    if not cfg_path.is_file():
        return HandoffConfig()

    try:
        raw = cfg_path.read_bytes().decode("utf-8-sig")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return HandoffConfig(warnings=(f"{CONFIG_FILENAME} 解析失败（{exc}），已使用默认目录配置。",))

    if not isinstance(data, dict):
        return HandoffConfig(warnings=(f"{CONFIG_FILENAME} 顶层须为 JSON 对象，已使用默认目录配置。",))

    warns: list[str] = []
    unknown = sorted(set(data.keys()) - ALLOWED_CONFIG_KEYS)
    if unknown:
        warns.append(
            f"{CONFIG_FILENAME} 含未识别的键 {', '.join(unknown)}（仅支持 docs_dir、cards_dir、index_file、review_dirs），已忽略并用默认值。"
        )

    docs_dir = DEFAULT_DOCS_DIR
    if "docs_dir" in data:
        cleaned = _clean_rel_path(data["docs_dir"])
        if cleaned is not None:
            docs_dir = cleaned
        else:
            warns.append(f"{CONFIG_FILENAME} 键 docs_dir 值无效，已使用默认值 {DEFAULT_DOCS_DIR!r}。")

    cards_dir = DEFAULT_CARDS_DIR
    if "cards_dir" in data:
        cleaned = _clean_rel_path(data["cards_dir"])
        if cleaned is not None:
            cards_dir = cleaned
        else:
            warns.append(f"{CONFIG_FILENAME} 键 cards_dir 值无效，已使用默认值 {DEFAULT_CARDS_DIR!r}。")

    index_file = DEFAULT_INDEX_FILE
    if "index_file" in data:
        cleaned = _clean_rel_path(data["index_file"])
        if cleaned is not None:
            index_file = cleaned
        else:
            warns.append(f"{CONFIG_FILENAME} 键 index_file 值无效，已使用默认值 {DEFAULT_INDEX_FILE!r}。")

    review_dirs = DEFAULT_REVIEW_DIRS
    if "review_dirs" in data:
        rv = data["review_dirs"]
        if isinstance(rv, list) and all(isinstance(x, str) and x.strip() for x in rv):
            review_dirs = tuple(x.strip().replace("\\", "/").strip("/") for x in rv)
        else:
            warns.append(f"{CONFIG_FILENAME} 键 review_dirs 须为非空字符串列表，已使用默认值 {list(DEFAULT_REVIEW_DIRS)!r}。")

    return HandoffConfig(
        docs_dir=docs_dir,
        cards_dir=cards_dir,
        index_file=index_file,
        review_dirs=review_dirs,
        warnings=tuple(warns),
    )


# =====================================================================
# Inline & Block AST
# =====================================================================


@dataclass(frozen=True)
class InlineSpan:
    kind: str  # "text" | "code" | "comment"
    raw: str
    content: str


@dataclass(frozen=True)
class Block:
    kind: str  # "heading" | "list_item" | "table_row" | "fenced_code" | "indented_code" | "html_comment" | "paragraph"
    start_line: int
    end_line: int
    lines: tuple[str, ...]
    line_inlines: tuple[tuple[InlineSpan, ...], ...] = ()
    level: int = 0
    title: str = ""
    indent: int = 0
    bullet: str = ""
    checkbox: Optional[str] = None
    cells: tuple[str, ...] = ()
    is_separator: bool = False

    @property
    def raw_text(self) -> str:
        return "\n".join(self.lines)

    def visible_lines(self, include_code: bool = True) -> list[str]:
        out: list[str] = []
        for spans in self.line_inlines:
            parts: list[str] = []
            for sp in spans:
                if sp.kind == "comment":
                    parts.append(" ")
                elif sp.kind == "code":
                    if include_code:
                        parts.append(sp.raw)
                else:
                    parts.append(sp.raw)
            out.append("".join(parts))
        return out

    def visible_text(self, include_code: bool = True) -> str:
        return "\n".join(self.visible_lines(include_code=include_code))

    def non_code_text(self) -> str:
        return self.visible_text(include_code=False)


@dataclass(frozen=True)
class ParsedDoc:
    lines: tuple[str, ...]
    blocks: tuple[Block, ...]


def parse_inlines(text: str) -> tuple[InlineSpan, ...]:
    """Tokenize a single line into InlineSpan('text' | 'code'), following CommonMark backtick matching."""
    if "`" not in text:
        return (InlineSpan("text", text, text),) if text else ()
    spans: list[InlineSpan] = []
    n = len(text)
    pos = 0
    text_start = 0
    while pos < n:
        if text[pos] != "`":
            pos += 1
            continue
        run_end = pos
        while run_end < n and text[run_end] == "`":
            run_end += 1
        tick_len = run_end - pos
        # Search for matching exact-length closing backtick run
        search_pos = run_end
        close_start = -1
        while search_pos < n:
            idx = text.find("`", search_pos)
            if idx == -1:
                break
            c_end = idx
            while c_end < n and text[c_end] == "`":
                c_end += 1
            if c_end - idx == tick_len:
                close_start = idx
                break
            search_pos = c_end
        if close_start != -1:
            if pos > text_start:
                raw_txt = text[text_start:pos]
                spans.append(InlineSpan("text", raw_txt, raw_txt))
            raw_code = text[pos : close_start + tick_len]
            inner = text[run_end:close_start]
            spans.append(InlineSpan("code", raw_code, inner))
            pos = close_start + tick_len
            text_start = pos
        else:
            pos = run_end
    if text_start < n:
        raw_txt = text[text_start:]
        spans.append(InlineSpan("text", raw_txt, raw_txt))
    return tuple(spans)


def _col_indent(line: str) -> int:
    col = 0
    for ch in line:
        if ch == " ":
            col += 1
        elif ch == "\t":
            col += 4 - (col % 4)
        else:
            break
    return col


def _find_closing_fence(lines: list[str], open_idx: int, fence_char: str, fence_len: int) -> Optional[int]:
    for j in range(open_idx + 1, len(lines)):
        m = FENCE_RE.match(lines[j])
        if m and m.group(1)[0] == fence_char and len(m.group(1)) >= fence_len and not m.group(2).strip():
            return j
    return None


def _split_table_cells(spans: tuple[InlineSpan, ...]) -> tuple[str, ...]:
    """Split a Markdown table row into stripped cell strings, ignoring `|` inside inline code and `\\|`."""
    # Reconstruct visible text with inline-code pipes masked
    buf: list[str] = []
    code_pipes: list[str] = []
    for sp in spans:
        if sp.kind == "comment":
            buf.append(" ")
        elif sp.kind == "code":
            idx = len(code_pipes)
            code_pipes.append(sp.raw)
            buf.append(f"\x01CODE{idx}\x01")
        else:
            buf.append(sp.raw)
    joined = "".join(buf).strip().replace(r"\|", "\x00")
    if joined.startswith("|"):
        joined = joined[1:]
    if joined.endswith("|"):
        joined = joined[:-1]
    cells: list[str] = []
    for raw_c in joined.split("|"):
        restored = raw_c.replace("\x00", "|")
        for idx, raw_code in enumerate(code_pipes):
            restored = restored.replace(f"\x01CODE{idx}\x01", raw_code)
        cells.append(restored.strip())
    return tuple(cells)


def _has_closing_comment_ahead(lines: list[str], after_line: int) -> bool:
    for k in range(after_line + 1, len(lines)):
        if "-->" in lines[k]:
            return True
    return False


def _tokenize_line_with_comments(
    lines: list[str], line_idx: int, in_comment: bool
) -> tuple[tuple[InlineSpan, ...], bool]:
    """Tokenize a non-fenced line with inline-code precedence, <!--> empty comments, and unclosed <!-- safety."""
    line = lines[line_idx]
    spans: list[InlineSpan] = []
    pos = 0
    n_ln = len(line)

    if in_comment:
        end_idx = line.find("-->")
        if end_idx == -1:
            return (InlineSpan("comment", line, line),), True
        spans.append(InlineSpan("comment", line[: end_idx + 3], line[:end_idx]))
        pos = end_idx + 3
        in_comment = False

    while pos < n_ln:
        bt_idx = line.find("`", pos)
        cm_idx = line.find("<!--", pos)

        if bt_idx == -1 and cm_idx == -1:
            raw_txt = line[pos:]
            spans.append(InlineSpan("text", raw_txt, raw_txt))
            break

        if bt_idx != -1 and (cm_idx == -1 or bt_idx < cm_idx):
            if bt_idx > pos:
                raw_txt = line[pos:bt_idx]
                spans.append(InlineSpan("text", raw_txt, raw_txt))
            run_end = bt_idx
            while run_end < n_ln and line[run_end] == "`":
                run_end += 1
            tick_len = run_end - bt_idx
            search_pos = run_end
            close_start = -1
            while search_pos < n_ln:
                idx = line.find("`", search_pos)
                if idx == -1:
                    break
                c_end = idx
                while c_end < n_ln and line[c_end] == "`":
                    c_end += 1
                if c_end - idx == tick_len:
                    close_start = idx
                    break
                search_pos = c_end
            if close_start != -1:
                raw_code = line[bt_idx : close_start + tick_len]
                inner = line[run_end:close_start]
                spans.append(InlineSpan("code", raw_code, inner))
                pos = close_start + tick_len
            else:
                raw_ticks = line[bt_idx:run_end]
                spans.append(InlineSpan("text", raw_ticks, raw_ticks))
                pos = run_end
            continue

        # cm_idx != -1 and comes before any backtick
        if cm_idx > pos:
            raw_txt = line[pos:cm_idx]
            spans.append(InlineSpan("text", raw_txt, raw_txt))

        if line.startswith("<!-->", cm_idx):
            spans.append(InlineSpan("comment", "<!-->", ""))
            pos = cm_idx + 5
            continue
        if line.startswith("<!--->", cm_idx):
            spans.append(InlineSpan("comment", "<!--->", ""))
            pos = cm_idx + 6
            continue

        end_idx = line.find("-->", cm_idx + 4)
        if end_idx != -1:
            spans.append(InlineSpan("comment", line[cm_idx : end_idx + 3], line[cm_idx + 4 : end_idx]))
            pos = end_idx + 3
            continue

        if _has_closing_comment_ahead(lines, line_idx):
            spans.append(InlineSpan("comment", line[cm_idx:], line[cm_idx + 4 :]))
            in_comment = True
            break

        # Unclosed '<!--' with no closing '-->' anywhere ahead -> treat as literal text, never swallow subsequent lines
        spans.append(InlineSpan("text", "<!--", "<!--"))
        pos = cm_idx + 4

    return tuple(spans), in_comment


def _spans_visible_str(spans: tuple[InlineSpan, ...]) -> str:
    return "".join(" " if sp.kind == "comment" else sp.raw for sp in spans)


def _is_pure_comment_spans(spans: tuple[InlineSpan, ...]) -> bool:
    has_comment = any(sp.kind == "comment" for sp in spans)
    if not has_comment:
        return False
    return all(sp.kind == "comment" or not sp.raw.strip() for sp in spans)


def parse_markdown(text: str, *, strip_comments: Optional[bool] = None) -> ParsedDoc:
    """Parse a Markdown document into typed Block objects with inline code & comment spans."""
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    n = len(lines)
    blocks: list[Block] = []
    do_comments = True if strip_comments is None else strip_comments

    # Pass 1: identify closed fenced code blocks and tokenize comments/inlines on remaining lines
    fenced_ranges: dict[int, int] = {}
    idx = 0
    in_comment = False
    line_spans: list[Optional[tuple[InlineSpan, ...]]] = [None] * n

    while idx < n:
        ln = lines[idx]
        if not in_comment:
            fm = FENCE_RE.match(ln)
            if fm and (fm.group(1)[0] == "~" or "`" not in fm.group(2)):
                close_idx = _find_closing_fence(lines, idx, fm.group(1)[0], len(fm.group(1)))
                if close_idx is not None:
                    fenced_ranges[idx] = close_idx + 1
                    idx = close_idx + 1
                    continue
        if do_comments:
            spans, in_comment = _tokenize_line_with_comments(lines, idx, in_comment)
        else:
            spans = parse_inlines(ln)
        line_spans[idx] = spans
        idx += 1

    # Pass 2: group lines into typed blocks
    i = 0
    while i < n:
        if i in fenced_ranges:
            end_i = fenced_ranges[i]
            blocks.append(
                Block(
                    kind="fenced_code",
                    start_line=i,
                    end_line=end_i,
                    lines=tuple(lines[i:end_i]),
                )
            )
            i = end_i
            continue

        spans = line_spans[i] or ()
        if _is_pure_comment_spans(spans):
            j = i + 1
            while j < n and j not in fenced_ranges and _is_pure_comment_spans(line_spans[j] or ()):
                j += 1
            blocks.append(
                Block(
                    kind="html_comment",
                    start_line=i,
                    end_line=j,
                    lines=tuple(lines[i:j]),
                    line_inlines=tuple(line_spans[k] or () for k in range(i, j)),
                )
            )
            i = j
            continue

        vis = _spans_visible_str(spans)
        if not vis.strip():
            i += 1
            continue

        # Table row (supports optional indentation so indented tables remain table_row)
        if vis.lstrip().startswith("|"):
            cells = _split_table_cells(spans)
            is_sep = bool(cells) and all(re.fullmatch(r"[:\-\s]*", c) for c in cells)
            blocks.append(
                Block(
                    kind="table_row",
                    start_line=i,
                    end_line=i + 1,
                    lines=(lines[i],),
                    line_inlines=(spans,),
                    indent=_col_indent(vis),
                    cells=cells,
                    is_separator=is_sep,
                )
            )
            i += 1
            continue

        col = _col_indent(vis)
        # Indented code block (>= 4 columns at block start)
        if col >= 4:
            j = i + 1
            while j < n and j not in fenced_ranges:
                sp_j = line_spans[j] or ()
                if _is_pure_comment_spans(sp_j):
                    break
                vis_j = _spans_visible_str(sp_j)
                if not vis_j.strip():
                    # Keep blank line inside indented_code only if followed by another >=4-indented line
                    k = j + 1
                    while k < n and k not in fenced_ranges and not _spans_visible_str(line_spans[k] or ()).strip():
                        if _is_pure_comment_spans(line_spans[k] or ()):
                            break
                        k += 1
                    if (
                        k < n
                        and k not in fenced_ranges
                        and not _is_pure_comment_spans(line_spans[k] or ())
                        and _col_indent(_spans_visible_str(line_spans[k] or ())) >= 4
                        and not _spans_visible_str(line_spans[k] or ()).lstrip().startswith("|")
                    ):
                        j = k + 1
                        continue
                    break
                if _col_indent(vis_j) >= 4 and not vis_j.lstrip().startswith("|"):
                    j += 1
                else:
                    break
            blocks.append(
                Block(
                    kind="indented_code",
                    start_line=i,
                    end_line=j,
                    lines=tuple(lines[i:j]),
                    line_inlines=tuple(line_spans[k] or () for k in range(i, j)),
                    indent=col,
                )
            )
            i = j
            continue

        # Heading (ATX H1-H6, plus no-space ##进度回写 compatibility)
        hm = HEAD_RE.match(vis) or NO_SPACE_PROGRESS_HEAD_RE.match(vis)
        if hm:
            lvl = len(hm.group(1))
            raw_title = (hm.group(2) or "").strip()
            blocks.append(
                Block(
                    kind="heading",
                    start_line=i,
                    end_line=i + 1,
                    lines=(lines[i],),
                    line_inlines=(parse_inlines(raw_title),),
                    level=lvl,
                    title=raw_title,
                    indent=col,
                )
            )
            i += 1
            continue

        # List item (with continuation lines for top-level list items)
        lm = LIST_ITEM_RE.match(vis)
        if lm:
            bullet = lm.group(2)
            rest = lm.group(3) or ""
            cb_m = CHECKBOX_PREFIX_RE.match(rest) if bullet in ("-", "*", "+") else None
            checkbox = cb_m.group(1) if cb_m else None
            j = i + 1
            if col == 0:
                while j < n and j not in fenced_ranges:
                    sp_j = line_spans[j] or ()
                    if _is_pure_comment_spans(sp_j):
                        break
                    vis_j = _spans_visible_str(sp_j)
                    if not vis_j.strip():
                        # Look ahead past blank lines for indented continuation (<4 cols; >=4 after blank is indented_code)
                        k = j + 1
                        while k < n and k not in fenced_ranges:
                            sp_k = line_spans[k] or ()
                            if _is_pure_comment_spans(sp_k) or _spans_visible_str(sp_k).strip():
                                break
                            k += 1
                        if k < n and k not in fenced_ranges and not _is_pure_comment_spans(line_spans[k] or ()):
                            vis_k = _spans_visible_str(line_spans[k] or ())
                            col_k = _col_indent(vis_k)
                            if 0 < col_k < 4 and not HEAD_RE.match(vis_k) and not vis_k.lstrip().startswith("|"):
                                j = k + 1
                                continue
                        break
                    col_j = _col_indent(vis_j)
                    if col_j > 0 and not HEAD_RE.match(vis_j) and not vis_j.lstrip().startswith("|"):
                        j += 1
                    else:
                        break
            blocks.append(
                Block(
                    kind="list_item",
                    start_line=i,
                    end_line=j,
                    lines=tuple(lines[i:j]),
                    line_inlines=tuple(line_spans[k] or () for k in range(i, j)),
                    indent=col,
                    bullet=bullet,
                    checkbox=checkbox,
                )
            )
            i = j
            continue

        # Ordinary paragraph (consecutive plain/blockquote lines)
        j = i + 1
        while j < n and j not in fenced_ranges:
            sp_j = line_spans[j] or ()
            if _is_pure_comment_spans(sp_j):
                break
            vis_j = _spans_visible_str(sp_j)
            if not vis_j.strip():
                break
            col_j = _col_indent(vis_j)
            if (
                col_j >= 4
                or vis_j.lstrip().startswith("|")
                or HEAD_RE.match(vis_j)
                or NO_SPACE_PROGRESS_HEAD_RE.match(vis_j)
                or LIST_ITEM_RE.match(vis_j)
            ):
                break
            j += 1
        blocks.append(
            Block(
                kind="paragraph",
                start_line=i,
                end_line=j,
                lines=tuple(lines[i:j]),
                line_inlines=tuple(line_spans[k] or () for k in range(i, j)),
                indent=col,
            )
        )
        i = j

    return ParsedDoc(lines=tuple(lines), blocks=tuple(blocks))


# =====================================================================
# Shared Date & Placeholder Helpers
# =====================================================================


def strip_placeholder_spans(text: str) -> str:
    """Remove inline placeholder spans and bare template example dates while keeping surrounding text."""
    cleaned = PLACEHOLDER_SPAN_RE.sub(" ", text)
    return BARE_DATE_EXAMPLE_RE.sub(" ", cleaned)


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


def extract_dates(text: str, today: date) -> list[date]:
    valid, _ = scan_dates(text)
    return [d for d in valid if d <= today]


def latest_date(text: str, today: date) -> Optional[date]:
    found = extract_dates(text, today)
    return max(found) if found else None


# =====================================================================
# Section Slicing & Thin Pointer Check
# =====================================================================


def find_section_range(doc: ParsedDoc, number: str, titles: set[str]) -> Optional[tuple[int, int, Block]]:
    """Find level-2 section matching `number` (e.g. '3', '4', '5') or exact title in `titles`."""
    esc = re.escape(number)
    num_re = re.compile(rf"^{esc}(?:\.(?!\d)|\s|$)")
    start_block: Optional[Block] = None
    for b in doc.blocks:
        if b.kind == "heading" and b.level == 2:
            if start_block is None:
                if num_re.match(b.title) or b.title in titles:
                    start_block = b
            else:
                return start_block.start_line, b.start_line, start_block
    if start_block is not None:
        return start_block.start_line, len(doc.lines), start_block
    return None


def extract_section_blocks(doc: ParsedDoc, number: str, titles: set[str]) -> list[Block]:
    rng = find_section_range(doc, number, titles)
    if rng is None:
        return []
    s, e, _ = rng
    return [b for b in doc.blocks if s <= b.start_line and b.end_line <= e]


def section(text: str, number: str, titles: set[str]) -> str:
    """Level-2 section raw slice up to the next level-2 heading."""
    doc = parse_markdown(text)
    rng = find_section_range(doc, number, titles)
    if rng is None:
        return ""
    s, e, _ = rng
    return "\n".join(doc.lines[s:e])


def non_code_blocks_text(blocks: list[Block], *, include_inline_code: bool = True) -> str:
    return "\n".join(
        b.visible_text(include_code=include_inline_code)
        for b in blocks
        if b.kind not in ("fenced_code", "indented_code", "html_comment")
    )


def pointer_ok(text: str) -> bool:
    if "AGENTS.md" not in text:
        return False
    doc = parse_markdown(text)
    positive_import = any(
        ln.strip() == "@AGENTS.md"
        for b in doc.blocks
        if b.kind not in ("fenced_code", "indented_code", "html_comment")
        for ln in b.visible_lines(include_code=False)
    )
    visible_all = "\n".join(b.raw_text for b in doc.blocks if b.kind != "html_comment") or text
    positive = positive_import or bool(
        re.search(
            r"(?is)(?:see|read|先读|以|权威入口|authoritative|scope\s+root|project\s+root|line\s+root)[^\n]{0,180}AGENTS\.md"
            r"|AGENTS\.md[^\n]{0,180}(?:权威|authoritative|先读|read|scope\s+root|project\s+root|line\s+root)",
            visible_all,
        )
    )
    negative = re.search(
        r"(?is)(?:不存在|没有|不要|never\s+(?:read|use|follow))[^\n]{0,60}AGENTS\.md"
        r"|AGENTS\.md[^\n]{0,30}(?:已?废弃|已?弃用|不再使用|deprecated|no\s+longer)",
        visible_all,
    )
    return bool(positive and not negative)


# =====================================================================
# Entrypoint 1: 取卡面状态 (Card Progress & State Parsing)
# =====================================================================


def extract_card_id(stem: str) -> str:
    if "_" in stem:
        return stem.split("_")[0]
    m = re.match(r"^([A-Za-z]+\d+[A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)", stem)
    return m.group(1) if m else stem


def collect_active_card_ids(root: Path, cfg: HandoffConfig) -> list[str]:
    """Return card IDs of active task cards (parsed state present and not in ✅/🗄️) under cards_dir."""
    cards_dir = root / cfg.cards_dir
    if not cards_dir.is_dir():
        return []
    out: list[str] = []
    seen: set[str] = set()
    for fp in sorted(cards_dir.glob("*.md")):
        if "复核" in fp.stem:
            continue
        st = parse_card_state(read_utf8(fp))
        if st is None or st in CLOSED:
            continue
        cid = extract_card_id(fp.stem)
        if cid and cid.upper() not in seen:
            seen.add(cid.upper())
            out.append(cid)
    return out


def block_mentions_active_card(seg: str, active_cids: list[str]) -> bool:
    """True when a handoff segment's heading mentions any active card ID (including T12a/b slash groups)."""
    if not active_cids:
        return False
    seg_doc = parse_markdown(seg)
    if not seg_doc.blocks or seg_doc.blocks[0].kind != "heading":
        head_text = seg.splitlines()[0] if seg.splitlines() else ""
    else:
        head_text = seg_doc.blocks[0].visible_text(include_code=True)
    active_upper = {c.upper() for c in active_cids}
    for m in SLASH_CARDS_RE.finditer(head_text):
        base = m.group(1)
        for ch in m.group(2).split("/"):
            if f"{base}{ch}".upper() in active_upper:
                return True
    for cid in active_cids:
        if re.search(rf"(?<![A-Za-z0-9-]){re.escape(cid)}(?![A-Za-z0-9-])", head_text, re.I):
            return True
    return False


def extract_progress_blocks(doc: ParsedDoc) -> list[Block]:
    """Return content blocks inside the '## 进度回写' section of a task card."""
    start_idx: Optional[int] = None
    start_lvl = 2
    for idx, b in enumerate(doc.blocks):
        if b.kind == "heading" and b.level == 2 and b.title.startswith("进度回写"):
            start_idx = idx
            start_lvl = b.level
            break
    if start_idx is None:
        return []
    out: list[Block] = []
    for b in doc.blocks[start_idx + 1 :]:
        if b.kind == "heading" and b.level <= start_lvl:
            break
        out.append(b)
    return out


def parse_card_state(text: str) -> Optional[str]:
    """Extract card state emoji from top-level 状态 line inside 进度回写 section."""
    doc = parse_markdown(text, strip_comments=True)
    for b in extract_progress_blocks(doc):
        if b.kind == "list_item":
            if b.indent != 0:
                continue
            candidates = [(b.line_inlines[0], b.visible_lines(include_code=False)[0], b.visible_lines(include_code=True)[0])]
        elif b.kind == "paragraph":
            candidates = list(
                zip(
                    b.line_inlines,
                    b.visible_lines(include_code=False),
                    b.visible_lines(include_code=True),
                )
            )
        else:
            continue

        for _, non_code_ln, with_code_ln in candidates:
            if not non_code_ln or non_code_ln[0] in (" ", "\t", ">"):
                continue
            m = CARD_STATE_LINE_RE.match(non_code_ln)
            if m:
                mark = STATE_RE.search(m.group(1))
                if not mark:
                    m_full = CARD_STATE_LINE_RE.match(with_code_ln)
                    if m_full:
                        mark = STATE_RE.search(m_full.group(1))
                return mark.group(0) if mark else None
    return None


def extract_card_progress_rows(text: str) -> list[tuple[str, int, str]]:
    """Return [(field_label, char_len, stripped_line), ...] for top-level bullet rows in 进度回写."""
    doc = parse_markdown(text, strip_comments=True)
    rows: list[tuple[str, int, str]] = []
    for b in extract_progress_blocks(doc):
        if b.kind == "list_item" and b.bullet in ("-", "*", "+"):
            for ln in b.visible_lines(include_code=True):
                if re.match(r"^\s*[-*+]\s", ln):
                    s = ln.strip()
                    label = re.split(r"[:：]", s.lstrip("-*+ "))[0][:12]
                    rows.append((label, len(s), s))
    return rows


def check_card_role_identity(text: str, role: str) -> tuple[bool, str]:
    """Check inside 进度回写 that the role's own line ('执行方' or '复核方') has 工具/模型/家族 filled."""
    role_label = "执行方" if role == "executor" else "复核方"
    line_re = re.compile(rf"^(?:[-*+][ \t]+)?\**{role_label}\**[ \t]*[:：](.*)$")
    doc = parse_markdown(text, strip_comments=True)
    role_rest: Optional[str] = None
    for b in extract_progress_blocks(doc):
        if b.kind == "list_item" and b.indent == 0:
            cands = b.visible_lines(include_code=True)[:1]
        elif b.kind == "paragraph":
            cands = [ln for ln in b.visible_lines(include_code=True) if ln and ln[0] not in (" ", "\t", ">")]
        else:
            continue
        for ln in cands:
            m = line_re.match(ln.strip())
            if m:
                role_rest = m.group(1).strip()
                break
        if role_rest is not None:
            break

    if role_rest is None:
        return False, f"缺少“{role_label}”行"

    def _clean_val(v: str) -> str:
        s = strip_placeholder_spans(v).strip(" \t—–-:：;；,，。/|.·()（）[]【】<>")
        if not s or PLACEHOLDER_RE.search(v):
            return ""
        return s

    fields = ("工具", "模型", "家族")
    if any(k in role_rest for k in fields):
        missing: list[str] = []
        vals: list[str] = []
        for k in fields:
            m_brk = re.search(rf"{k}\s*【([^【】]*)】", role_rest)
            if not m_brk:
                m_brk = re.search(rf"{k}\s*\[([^\[\]]*)\]", role_rest)
            if not m_brk:
                m_brk = re.search(rf"{k}\s*[（(]([^（）()]*)[）)]", role_rest)
            if m_brk is not None:
                val = _clean_val(m_brk.group(1))
            else:
                m_kv = re.search(rf"{k}\s*[:：]?\s*([^/；;，,\n【\[\(（]+)", role_rest)
                val = _clean_val(m_kv.group(1)) if m_kv else ""
            if not val:
                missing.append(k)
            else:
                vals.append(f"{k}={val}")
        if missing:
            return False, f"{role_label}未填：{'、'.join(missing)}"
        return True, " / ".join(vals)

    # Fallback: slash-separated 'Tool / Model / Family' without explicit labels
    head_clause = re.split(r"[；;]", role_rest)[0]
    parts = [_clean_val(p) for p in head_clause.split("/")]
    parts = [p for p in parts if p]
    if len(parts) >= 3:
        return True, " / ".join(parts[:3])
    return False, f"{role_label}未填全工具/模型/家族"


def extract_prompt_headings(text: str) -> list[str]:
    doc = parse_markdown(text)
    return [b.title for b in doc.blocks if b.kind == "heading" and PROMPT_TITLE_RE.search(b.title)]


def top_card_sections(text: str, k: int = 3) -> str:
    doc = parse_markdown(text)
    h2_starts = [b.start_line for b in doc.blocks if b.kind == "heading" and b.level == 2]
    secs: list[tuple[str, list[str]]] = []
    if not h2_starts:
        secs.append(("(卡头)", list(doc.lines)))
    else:
        secs.append(("(卡头)", list(doc.lines[: h2_starts[0]])))
        for idx, s in enumerate(h2_starts):
            e = h2_starts[idx + 1] if idx + 1 < len(h2_starts) else len(doc.lines)
            title = doc.lines[s].lstrip()[2:].strip()
            secs.append((title, list(doc.lines[s:e])))
    sized: list[tuple[str, int]] = []
    for t, ls in secs:
        if not "\n".join(ls).strip():
            continue
        prefix = re.split(r"[（(]", t)[0].strip()
        label = (prefix if len(prefix) >= 6 else t)[:20].rstrip()
        sized.append((label, len("\n".join(ls).encode("utf-8"))))
    sized.sort(key=lambda x: x[1], reverse=True)
    return " / ".join(f"「{t}」{b}B" for t, b in sized[:k])


# =====================================================================
# Entrypoint 2: 分交接段 (STATUS.md Segmentation)
# =====================================================================


@dataclass(frozen=True)
class StatusDocument:
    preamble: list[str]
    blocks: list[str]
    gaps: list[str]
    postamble: list[str]


def is_handoff_heading(title: str) -> bool:
    """Recognized handoff headings: contain Handoff/交接, start with date, or start with T<id> + date.
    Headings like '## 交回说明' or '## 归档说明' are NOT handoff headings."""
    t = title.strip()
    if not t:
        return False
    if re.search(r"归档|archive|现状一屏|current\s+snapshot", t, re.I):
        return False
    return bool(
        re.search(r"(?i)handoff|交接", t)
        or HEADING_DATE_START_RE.match(t)
        or (re.match(r"^[\[（(【]?\s*T\d+[A-Za-z0-9-]*\b", t, re.I) and FLEX_DATE_TOKEN_RE.search(t))
    )


def trim_blank_lines(ls: list[str]) -> str:
    s = 0
    e = len(ls)
    while s < e and not ls[s].strip():
        s += 1
    while e > s and not ls[e - 1].strip():
        e -= 1
    return "\n".join(ls[s:e])


def parse_status_document(text: str) -> StatusDocument:
    """Split STATUS.md into preamble, handoff blocks, inter-block gaps, and postamble using block AST."""
    doc = parse_markdown(text)
    lines = list(doc.lines)
    headings: list[tuple[int, int, str]] = []

    if _STATUS_SKIP_COMMENTED_HEADINGS:
        for b in doc.blocks:
            if b.kind == "heading":
                clean_title = b.non_code_text().strip()
                headings.append((b.start_line, b.level, clean_title))
    else:
        fenced_lines = {
            ln_idx
            for b in doc.blocks
            if b.kind == "fenced_code"
            for ln_idx in range(b.start_line, b.end_line)
        }
        for i, ln in enumerate(lines):
            if i in fenced_lines:
                continue
            m = re.match(r"^\s*(#{1,6})\s+(.*)$", ln)
            if m:
                t_no_code = "".join(
                    sp.raw for sp in parse_inlines(m.group(2).strip()) if sp.kind == "text"
                ).strip()
                headings.append((i, len(m.group(1)), t_no_code))

    handoff_heads = [
        (i, lvl, t)
        for i, lvl, t in headings
        if lvl in (2, 3) and is_handoff_heading(t) and not HANDOFF_INNER_HEAD_RE.match(t)
    ]
    if not handoff_heads:
        return StatusDocument(preamble=lines, blocks=[], gaps=[], postamble=[])

    handoff_starts = {i for i, _, _ in handoff_heads}
    first_start = handoff_heads[0][0]
    preamble = lines[:first_start]

    blocks: list[str] = []
    gaps: list[str] = []
    postamble: list[str] = []
    prev_end = first_start
    for idx, (start, cur_lvl, _) in enumerate(handoff_heads):
        gap_str = trim_blank_lines(lines[prev_end:start]) if idx > 0 else ""
        gaps.append(gap_str)
        next_end = next(
            (
                i
                for i, lvl, t in headings
                if i > start
                and (
                    i in handoff_starts
                    or lvl < cur_lvl
                    or (lvl == cur_lvl and not HANDOFF_INNER_HEAD_RE.match(t))
                )
            ),
            len(lines),
        )
        seg_lines = list(lines[start:next_end])
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
        blocks.append(trim_blank_lines(seg_lines))
        prev_end = next_end

    return StatusDocument(preamble=preamble, blocks=blocks, gaps=gaps, postamble=postamble)


def parse_status(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split STATUS.md into (preamble_lines, handoff_blocks, postamble_lines)."""
    sdoc = parse_status_document(text)
    return sdoc.preamble, sdoc.blocks, sdoc.postamble


def handoff_blocks(status: str) -> list[str]:
    """Return stripped handoff blocks in STATUS.md."""
    return [b.strip() for b in parse_status_document(status).blocks]


def block_latest_date(seg: str, today: date) -> Optional[date]:
    """Extract date of a single handoff block: heading first, then non-code body."""
    seg_doc = parse_markdown(seg)
    if not seg_doc.blocks:
        return None
    first = seg_doc.blocks[0]
    if first.kind == "heading":
        d = latest_date(first.non_code_text(), today)
        if d is not None:
            return d
    body_txt = non_code_blocks_text(list(seg_doc.blocks), include_inline_code=False)
    return latest_date(body_txt, today)


def handoffs_latest_date(blocks: list[str], today: date) -> Optional[date]:
    """Extract latest date across handoff blocks: headings first, then non-code bodies."""
    if not blocks:
        return None
    head_parts: list[str] = []
    body_parts: list[str] = []
    for seg in blocks:
        seg_doc = parse_markdown(seg)
        if not seg_doc.blocks:
            continue
        if seg_doc.blocks[0].kind == "heading":
            head_parts.append(seg_doc.blocks[0].non_code_text())
        body_parts.append(non_code_blocks_text(list(seg_doc.blocks), include_inline_code=False))
    return latest_date("\n".join(head_parts), today) or latest_date("\n\n".join(body_parts), today)


def status_fallback_scan(status: str, today: date) -> tuple[Optional[date], list[date], list[str], str]:
    """Scan fallback dates in STATUS.md when no dated handoff block exists."""
    doc = parse_markdown(status)
    lines_buf: list[str] = []
    for b in doc.blocks:
        if b.kind in ("fenced_code", "indented_code"):
            continue
        if _STATUS_SKIP_COMMENTED_HEADINGS and b.kind == "html_comment":
            continue
        if b.kind == "heading" and re.search(r"归档|archive", b.title, re.I):
            continue
        lines_buf.append(b.raw_text if not _STATUS_SKIP_COMMENTED_HEADINGS else b.visible_text(include_code=False))
    joined = "\n".join(lines_buf)
    valid, invalid = scan_dates(joined)
    le_today = [d for d in valid if d <= today]
    return (max(le_today) if le_today else None), valid, invalid, "STATUS 正文"


def missing_handoff_sections(seg: str) -> list[str]:
    """Return missing required 4-section labels in a single handoff segment using parsed blocks."""
    seg_doc = parse_markdown(seg)
    visible_lines: list[str] = []
    for b in seg_doc.blocks:
        if b.kind in ("fenced_code", "indented_code", "html_comment"):
            continue
        if b.kind == "heading":
            visible_lines.append(b.lines[0])
        else:
            visible_lines.extend(b.visible_lines(include_code=False))
    joined = "\n".join(visible_lines)
    return [label for label, pat in HANDOFF_SECTIONS if not any(pat.search(ln) for ln in joined.splitlines())]


# =====================================================================
# Entrypoint 3: 取 §3 日期与条目 (AGENTS.md §3 Parsing)
# =====================================================================


@dataclass(frozen=True)
class Sec3Info:
    exists: bool
    latest_date: Optional[date]
    is_placeholder: bool
    missing_msg: str
    heading_line: str
    start_line: int
    end_line: int
    lead_lines: list[str]
    entries: list[tuple[str, list[str]]]  # ('archivable' | 'trailer', raw_lines)


def extract_sec3_info(agents_text: str, today: date) -> Sec3Info:
    doc = parse_markdown(agents_text)
    rng = find_section_range(doc, "3", {"现在在哪", "Where We Are Now"})
    if rng is None:
        return Sec3Info(False, None, False, "§3 没有有效日期", "", 0, 0, [], [])
    s, e, head_blk = rng
    sec_blocks = [b for b in doc.blocks if s <= b.start_line and b.end_line <= e]

    vis_lines: list[str] = []
    for b in sec_blocks:
        if b.kind in ("fenced_code", "indented_code", "html_comment"):
            continue
        if b.kind == "heading":
            vis_lines.append(" ".join(b.visible_lines(include_code=False)))
        else:
            vis_lines.extend(b.visible_lines(include_code=False))

    has_placeholder = any(
        PLACEHOLDER_SPAN_RE.search(ln) or PLACEHOLDER_RE.search(ln) or BARE_DATE_EXAMPLE_RE.search(ln)
        for ln in vis_lines
    )
    real_text = strip_placeholder_spans("\n".join(vis_lines))
    sec3_date = latest_date(real_text, today)
    is_ph = sec3_date is None and has_placeholder
    missing_msg = "§3 还是模板占位" if is_ph else "§3 没有有效日期"

    lead_lines: list[str] = []
    entries: list[tuple[str, list[str]]] = []
    for b in sec_blocks[1:]:
        if b.kind == "list_item" and b.indent == 0 and b.bullet in ("-", "*", "+"):
            first_ln = b.lines[0]
            is_ptr = bool(re.match(r"^[-*+]\s+`?→", first_ln))
            is_blk = bool(re.match(r"^[-*+]\s+\**(?:阻塞|Blockers?)\**[:：]?", first_ln, re.I))
            kind = "trailer" if (is_ptr or is_blk) else "archivable"
            entries.append((kind, list(b.lines)))
        else:
            lead_lines.extend(b.lines)

    return Sec3Info(
        exists=True,
        latest_date=sec3_date,
        is_placeholder=is_ph,
        missing_msg=missing_msg,
        heading_line=doc.lines[s],
        start_line=s,
        end_line=e,
        lead_lines=lead_lines,
        entries=entries,
    )


# =====================================================================
# Entrypoint 4: 取 TL;DR (AGENTS.md TL;DR Parsing)
# =====================================================================


@dataclass(frozen=True)
class TldrInfo:
    exists: bool
    unfilled: bool
    latest_date: Optional[date]
    raw_text: str


def extract_tldr_info(agents_text: str, today: date) -> TldrInfo:
    doc = parse_markdown(agents_text)
    start_b_idx: Optional[int] = None
    for idx, b in enumerate(doc.blocks):
        if b.kind in ("fenced_code", "indented_code", "html_comment"):
            continue
        if b.kind == "heading" and b.level == 2:
            if re.search(r"TL;DR", b.title, re.I):
                start_b_idx = idx
            break
        if re.search(r"TL;DR", b.visible_text(include_code=True), re.I):
            start_b_idx = idx
            break

    if start_b_idx is None:
        return TldrInfo(exists=False, unfilled=True, latest_date=None, raw_text="")

    tldr_blocks: list[Block] = []
    first_blk = doc.blocks[start_b_idx]
    for b in doc.blocks[start_b_idx:]:
        if b is not first_blk and b.kind == "heading" and b.level == 2:
            break
        if b.kind == "paragraph" and any(re.match(r"^---\s*$", ln) for ln in b.lines):
            # Keep any lines in this paragraph before `---`
            pre_hr = []
            pre_inlines = []
            for ln, sp in zip(b.lines, b.line_inlines):
                if re.match(r"^---\s*$", ln):
                    break
                pre_hr.append(ln)
                pre_inlines.append(sp)
            if pre_hr:
                tldr_blocks.append(
                    Block(
                        kind="paragraph",
                        start_line=b.start_line,
                        end_line=b.start_line + len(pre_hr),
                        lines=tuple(pre_hr),
                        line_inlines=tuple(pre_inlines),
                    )
                )
            break
        tldr_blocks.append(b)

    content_blocks = [
        b for b in tldr_blocks if b.kind not in ("fenced_code", "indented_code", "html_comment")
    ]
    raw_text = "\n".join(b.raw_text for b in content_blocks)
    vis_non_code_lines: list[str] = []
    vis_with_code_lines: list[str] = []
    for b in content_blocks:
        if b.kind == "heading":
            vis_non_code_lines.append(" ".join(b.visible_lines(include_code=False)))
            vis_with_code_lines.append(b.lines[0])
        else:
            vis_non_code_lines.extend(b.visible_lines(include_code=False))
            vis_with_code_lines.extend(b.visible_lines(include_code=True))

    vis_with_code = "\n".join(vis_with_code_lines)
    vis_non_code = "\n".join(vis_non_code_lines)
    has_empty_field = any(EMPTY_TLDR_FIELD_RE.match(ln) for ln in vis_with_code_lines)
    unfilled = not vis_with_code.strip() or bool(PLACEHOLDER_RE.search(vis_non_code) or has_empty_field)
    tldr_date = latest_date(strip_placeholder_spans(vis_non_code), today)
    return TldrInfo(exists=True, unfilled=unfilled, latest_date=tldr_date, raw_text=raw_text)


# =====================================================================
# Entrypoint 5: 读决策表 (Decision Registry Table Parsing)
# =====================================================================


@dataclass(frozen=True)
class DecisionRow:
    disp_id: str
    norm_id: str
    status: str
    raw_replaces: str
    raw_replaced_by: str
    replaces_ids: tuple[str, ...]
    replaced_by_ids: tuple[str, ...]


@dataclass(frozen=True)
class DecisionTable:
    section_title: str
    header_cols: tuple[str, ...]
    has_status_col: bool
    has_replaces_col: bool
    has_replaced_by_col: bool
    rows: tuple[DecisionRow, ...]


def normalize_decision_id(tok: str) -> str:
    m = re.match(r"^([A-Za-z]+)-?0*(\d+)([A-Za-z0-9]*)$", tok.strip())
    if not m:
        return tok.strip().upper()
    return f"{m.group(1).upper()}-{int(m.group(2))}{m.group(3).upper()}"


def _parse_decision_ids(val: str) -> tuple[str, ...]:
    v = val.strip(" *`")
    if v.lower() in EMPTY_CELL_VALUES or PLACEHOLDER_RE.search(v):
        return ()
    return tuple(normalize_decision_id(t) for t in DECISION_ID_RE.findall(v))


def _extract_tables_from_blocks(section_title: str, tbl_blocks: list[Block]) -> list[DecisionTable]:
    tables: list[DecisionTable] = []
    cur_header: Optional[list[str]] = None
    in_dec = False
    id_col = 0
    st_col: Optional[int] = None
    rep_col: Optional[int] = None
    rep_by_col: Optional[int] = None
    cur_rows: list[DecisionRow] = []

    def _flush() -> None:
        nonlocal cur_header, in_dec, cur_rows
        if in_dec and cur_header is not None:
            tables.append(
                DecisionTable(
                    section_title=section_title,
                    header_cols=tuple(cur_header),
                    has_status_col=st_col is not None,
                    has_replaces_col=rep_col is not None,
                    has_replaced_by_col=rep_by_col is not None,
                    rows=tuple(cur_rows),
                )
            )
        cur_header = None
        in_dec = False
        cur_rows = []

    for pos, b in enumerate(tbl_blocks):
        if b.is_separator:
            continue
        next_is_sep = (
            pos + 1 < len(tbl_blocks)
            and tbl_blocks[pos + 1].is_separator
            and tbl_blocks[pos + 1].start_line == b.start_line + 1
        )
        clean_cells = [c.strip(" *`") for c in b.cells]
        if cur_header is None or next_is_sep:
            if in_dec and next_is_sep:
                _flush()
            if any(c.upper() in ("ID", "编号", "决策ID") for c in clean_cells):
                cur_header = clean_cells
                in_dec = True
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
                cur_rows = []
            elif next_is_sep:
                in_dec = False
            continue

        if not in_dec or cur_header is None:
            continue

        n_head = len(cur_header)
        raw_id = clean_cells[id_col] if id_col < len(clean_cells) else ""
        if not raw_id or raw_id.startswith("【") or PLACEHOLDER_RE.search(raw_id):
            continue
        raw_st = (clean_cells[st_col] if st_col is not None and st_col < len(clean_cells) else "").upper()

        def _get_tail(col_idx: Optional[int]) -> str:
            if col_idx is None:
                return ""
            if len(clean_cells) >= n_head and col_idx >= n_head - 2:
                return clean_cells[col_idx - n_head]
            return clean_cells[col_idx] if col_idx < len(clean_cells) else ""

        raw_rep = _get_tail(rep_col)
        raw_rep_by = _get_tail(rep_by_col)
        cur_rows.append(
            DecisionRow(
                disp_id=raw_id,
                norm_id=normalize_decision_id(raw_id),
                status=raw_st,
                raw_replaces=raw_rep,
                raw_replaced_by=raw_rep_by,
                replaces_ids=_parse_decision_ids(raw_rep),
                replaced_by_ids=_parse_decision_ids(raw_rep_by),
            )
        )

    _flush()
    return tables


def parse_decision_tables(agents_text: str, *, all_sections: bool = False) -> list[DecisionTable]:
    """Extract decision registry tables from §3.5 / '决策登记表' sections."""
    doc = parse_markdown(agents_text)
    sections: list[tuple[str, list[Block]]] = []
    i = 0
    nb = len(doc.blocks)
    while i < nb:
        b = doc.blocks[i]
        if b.kind == "heading" and b.level in (2, 3):
            if re.match(r"^3\.5(?:\.(?!\d)|\s|$)", b.title) or "决策登记表" in b.title:
                sec_lvl = b.level
                sec_title = b.title
                tbls: list[Block] = []
                j = i + 1
                while j < nb:
                    bj = doc.blocks[j]
                    if bj.kind == "heading" and bj.level <= sec_lvl:
                        break
                    if bj.kind == "table_row":
                        tbls.append(bj)
                    j += 1
                sections.append((sec_title, tbls))
                if not all_sections:
                    break
                i = j
                continue
        i += 1

    out: list[DecisionTable] = []
    for stitle, tbls in sections:
        out.extend(_extract_tables_from_blocks(stitle, tbls))
    return out


# =====================================================================
# Entrypoint 6: 读看板行 (AGENTS.md §4 Task Board Parsing)
# =====================================================================


@dataclass(frozen=True)
class BoardItem:
    checked: bool
    is_template: bool
    raw_body: str
    non_code_body: str
    sub_items: tuple[tuple[bool, str, str], ...] = ()  # (checked, raw_body, non_code_body)


def is_template_task_body(body: str) -> bool:
    s = body.strip()
    if not s:
        return True
    if PLACEHOLDER_RE.search(s):
        return True
    if re.search(r"(?<![A-Za-z0-9-])T[xyz](?![A-Za-z0-9-])", s) and re.search(r"示例|例[:：\s]", s):
        return True
    return False


def parse_board_items(agents_or_sec4: str) -> list[BoardItem]:
    """Parse task checkbox lines from AGENTS.md §4 (or a standalone §4 snippet) using block AST."""
    doc = parse_markdown(agents_or_sec4)
    sec4_blocks = extract_section_blocks(doc, "4", {"任务看板", "下一步任务看板", "Next Task Board"})
    target_blocks = sec4_blocks if sec4_blocks else list(doc.blocks)

    items: list[BoardItem] = []
    box_line_re = re.compile(r"^\s*[-*+]\s*\[([ xX]?)\](.*)$")
    inline_split_re = re.compile(r"\s+[-*+]\s*\[([ xX]?)\]")

    for b in target_blocks:
        if b.kind != "list_item":
            continue
        vis_with_code = b.visible_lines(include_code=True)
        vis_no_code = b.visible_lines(include_code=False)
        for ln_code, ln_nocode in zip(vis_with_code, vis_no_code):
            if _col_indent(ln_code) >= 4:
                continue
            m_code = box_line_re.match(ln_code)
            m_nocode = box_line_re.match(ln_nocode)
            if not m_code or not m_nocode:
                continue
            parts_code = inline_split_re.split(m_code.group(2))
            parts_nocode = inline_split_re.split(m_nocode.group(2))
            sub_code = [(m_code.group(1), parts_code[0])]
            for k in range(1, len(parts_code), 2):
                sub_code.append((parts_code[k], parts_code[k + 1]))
            sub_nocode = [(m_nocode.group(1), parts_nocode[0])]
            for k in range(1, len(parts_nocode), 2):
                sub_nocode.append((parts_nocode[k], parts_nocode[k + 1]))

            subs: list[tuple[bool, str, str]] = []
            for idx_sub, (box, body_code) in enumerate(sub_code):
                body_nc = sub_nocode[idx_sub][1] if idx_sub < len(sub_nocode) else body_code
                subs.append((box in ("x", "X"), body_code, body_nc))

            line_body_code = m_code.group(2)
            line_body_nc = m_nocode.group(2)
            items.append(
                BoardItem(
                    checked=m_code.group(1) in ("x", "X"),
                    is_template=is_template_task_body(line_body_code),
                    raw_body=line_body_code,
                    non_code_body=line_body_nc,
                    sub_items=tuple(subs),
                )
            )
    return items

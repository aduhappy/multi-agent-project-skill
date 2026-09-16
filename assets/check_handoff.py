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
  H006 STATUS 的 Handoff 日期 >= §3 最近日期
  H007 至少一个薄指针指向 AGENTS.md（没有薄指针也算通过）
  H008 §4 看板存在且有任务行
  H009 TL;DR 日期与 §3 不矛盾（任一方没日期则跳过）
  A001–A004 只提示不阻断：决策登记表、多脚本常量漂移、文件体积、看板全未勾

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
PLACEHOLDER_RE = re.compile(r"例：|e\.g\.|\bTODO\b|【待填|YYYY-MM-DD|<fill|\[fill", re.I)

findings: list[tuple[str, str, bool, str, bool]] = []  # code, name, ok, detail, advisory


def add(code: str, name: str, ok: bool, detail: str = "", advisory: bool = False) -> None:
    findings.append((code, name, ok, detail, advisory))


def read(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


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
    out, fenced = [], False
    for line in text.splitlines():
        if line.strip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            out.append(line)
    return "\n".join(out)


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
    add("H004", "TL;DR 已填（非占位符）", bool(tldr.strip()) and not PLACEHOLDER_RE.search(tldr),
        "已填" if tldr and not PLACEHOLDER_RE.search(tldr) else "缺失或仍含占位符")

    add("H005", "STATUS.md 存在且非模板",
        len(status.strip()) > 50 and bool(dates(status, today)) and "YYYY-MM-DD" not in status,
        "已填" if status else "missing")

    handoff_heads = "\n".join(
        line for line in status.splitlines() if re.match(r"^\s*#{1,6}\s+", line) and re.search(r"(?i)handoff", line)
    )
    status_date = latest(handoff_heads, today) or latest(status, today)
    add("H006", "STATUS Handoff 日期 >= §3 日期", bool(status_date and sec3_date and status_date >= sec3_date),
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

    advisories(root, agents, status, sec4)


def advisories(root: Path, agents: str, status: str, sec4: str) -> None:
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

    big = [f"{n} {len(t.encode('utf-8')) // 1000}KB" for n, t, limit in
           (("AGENTS.md", agents, 25_000), ("STATUS.md", status, 40_000)) if len(t.encode("utf-8")) > limit]
    add("A003", "AGENTS ≤25KB、STATUS ≤40KB", not big, ", ".join(big), True)

    checked = len(re.findall(r"(?m)^\s*[-*]\s*\[[xX]\]", sec4))
    unchecked = len(re.findall(r"(?m)^\s*[-*]\s*\[\s?\]", sec4))
    add("A004", "§4 看板至少勾了一项", not (unchecked and not checked), f"{checked} 勾 / {unchecked} 未勾", True)


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

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Smoke test for check_handoff.py: builds a tiny root index + line in a temp dir."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "assets" / "check_handoff.py"
TODAY = "2026-09-15"


def run(root: Path, *args: str) -> tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run(
        [sys.executable, "-B", str(CHECKER), str(root), "--today", TODAY, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    return result.returncode, result.stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(root: Path) -> Path:
    line = root / "03_paper"
    write(root / "AGENTS.md", "# AGENTS\n\n> **Scope: index**\n\n| 线 | 入口 |\n|---|---|\n| 论文 | `03_paper/AGENTS.md` |\n")
    write(line / "AGENTS.md",
          "# AGENTS\n\n> **Scope: line**\n\n> ⚡ **TL;DR**\n> - **当前阶段**：初稿（2026-09-15）\n> - **下一步**：写方法\n> - **阻塞**：无\n\n"
          "## 3. 现在在哪\n- 2026-09-15：初稿完成\n\n## 3.5 决策登记表\n| ID | 决策 |\n|---|---|\n\n"
          "## 4. 任务看板\n- [x] T1 初稿\n- [ ] T2 方法\n")
    write(line / "STATUS.md", "# STATUS\n\n## Handoff（2026-09-15）\n- 本次做了什么：写完初稿，动了草稿文件，没有阻塞。\n")
    write(line / "CLAUDE.md", "# 本项目的权威入口是 AGENTS.md\n")
    return line


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        line = build(root)

        rc, out = run(root, "--scope", "index")
        check(rc == 0, "root index should pass:\n" + out)
        rc, out = run(line)
        check(rc == 0, "filled line should pass:\n" + out)

        rc, out = run(line, "--scope", "index")
        check(rc == 1 and "[I002] ❌" in out, "line misused as index must fail:\n" + out)
        rc, out = run(root)
        check(rc == 1 and "[H002] ❌" in out, "root misused as line must fail:\n" + out)

        rc, out = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(line), "--today", "2026-10-20"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        ).returncode, ""
        check(rc == 1, "stale §3 date must fail")

        write(line / "STATUS.md", "# STATUS\n\n## Handoff（YYYY-MM-DD）\n- 【待填】\n")
        rc, out = run(line)
        check(rc == 1 and "[H005] ❌" in out, "template STATUS must fail:\n" + out)

        (line / "CLAUDE.md").write_text("以 README.md 为准，AGENTS.md 已废弃。\n", encoding="utf-8")
        rc, out = run(line)
        check("[H007] ❌" in out, "retired pointer must fail:\n" + out)
    print("All skill self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

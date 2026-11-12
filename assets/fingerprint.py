#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fingerprint.py — 受保护目录与关键文件的 SHA-256 指纹快照与前后比对工具（纯标准库）

用法：
    python scripts/fingerprint.py snapshot <目录或文件…> -o before.json
    python scripts/fingerprint.py snapshot <目录或文件…> > before.json
    python scripts/fingerprint.py compare before.json after.json [--check]
    python scripts/fingerprint.py compare before.json <目录或文件…> [--check]
    python scripts/fingerprint.py --version

说明：
  - `snapshot` 递归扫描给定目录或文件（自动跳过 `__pycache__` 与 `.git`），将每个文件的 SHA-256 与字节数记入 JSON。
  - `compare` 比对两份快照（或一份旧快照与当前目录），按“新增 / 删除 / 改动”三类列出全部差异；加 `--check` 时若有差异返回退出码 1。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.dont_write_bytecode = True

__version__ = "0.5.0"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_SKIP_DIRS = frozenset({"__pycache__", ".git"})


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
    return h.hexdigest(), total


def _iter_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        raise FileNotFoundError(f"路径不存在：{target}")
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        p_dir = Path(dirpath)
        for fn in sorted(filenames):
            fp = p_dir / fn
            if fp.is_file():
                found.append(fp)
    return found


def _compute_common_root(resolved_targets: list[Path], explicit_root: Optional[Path] = None) -> Path:
    if explicit_root is not None:
        return explicit_root.resolve()
    if len(resolved_targets) == 1:
        t = resolved_targets[0]
        return t if t.is_dir() else t.parent
    try:
        common = Path(os.path.commonpath([str(p if p.is_dir() else p.parent) for p in resolved_targets]))
        return common.resolve()
    except ValueError:
        return Path.cwd().resolve()


def build_snapshot(targets: list[Path], *, base_root: Optional[Path] = None) -> dict[str, Any]:
    if not targets:
        raise ValueError("至少需要指定一个目录或文件。")
    resolved = [p.resolve() for p in targets]
    for p in resolved:
        if not p.exists():
            raise FileNotFoundError(f"路径不存在：{p}")
    root = _compute_common_root(resolved, base_root)
    files_map: dict[str, dict[str, Any]] = {}
    for tgt in resolved:
        for fp in _iter_files(tgt):
            try:
                key = fp.relative_to(root).as_posix()
            except ValueError:
                key = fp.as_posix()
            digest, size = _sha256_file(fp)
            files_map[key] = {"sha256": digest, "size": size}
    sorted_files = {k: files_map[k] for k in sorted(files_map.keys())}
    return {
        "tool": "multi-agent-project/fingerprint",
        "version": __version__,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": root.as_posix(),
        "targets": [p.as_posix() for p in resolved],
        "file_count": len(sorted_files),
        "files": sorted_files,
    }


def load_snapshot_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes().decode("utf-8-sig")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise ValueError(f"无效的指纹快照 JSON：{path}")
    return data


def _is_snapshot_json_file(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
        return isinstance(data, dict) and isinstance(data.get("files"), dict) and data.get("tool", "").endswith("fingerprint")
    except Exception:
        return False


def diff_snapshots(old_snap: dict[str, Any], new_snap: dict[str, Any]) -> dict[str, list[str]]:
    old_files: dict[str, Any] = old_snap.get("files", {})
    new_files: dict[str, Any] = new_snap.get("files", {})
    old_keys = set(old_files.keys())
    new_keys = set(new_files.keys())
    added = sorted(new_keys - old_keys)
    deleted = sorted(old_keys - new_keys)
    modified: list[str] = []
    for k in sorted(old_keys & new_keys):
        old_sha = old_files[k]["sha256"] if isinstance(old_files[k], dict) else str(old_files[k])
        new_sha = new_files[k]["sha256"] if isinstance(new_files[k], dict) else str(new_files[k])
        if old_sha != new_sha:
            modified.append(k)
    return {"added": added, "deleted": deleted, "modified": modified}


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content.encode("utf-8"))
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="记录目录/文件的 SHA-256 指纹快照并比对新增、删除、改动")
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("snapshot", help="扫描目录或文件，输出 SHA-256 指纹 JSON")
    p_snap.add_argument("paths", nargs="+", help="要记录指纹的一个或多个目录/文件")
    p_snap.add_argument("-o", "--output", help="输出 JSON 文件路径（省略则打印到标准输出）")
    p_snap.add_argument("--root", help="可选相对路径基准目录（默认取目标公共根目录）")

    p_cmp = sub.add_parser("compare", help="比对旧快照与新快照（或当前目录），列出新增、删除、改动")
    p_cmp.add_argument("old_snapshot", help="基准快照 JSON 文件路径")
    p_cmp.add_argument("targets", nargs="*", help="新快照 JSON 文件路径，或要实时扫描的目录/文件（省略则按旧快照记录的 targets 重扫）")
    p_cmp.add_argument("--check", action="store_true", help="若存在任何新增、删除或改动则返回退出码 1")
    p_cmp.add_argument("--json", action="store_true", help="以 JSON 格式输出比对结果")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2

    if args.cmd == "snapshot":
        try:
            base_r = Path(args.root).resolve() if args.root else None
            snap = build_snapshot([Path(p) for p in args.paths], base_root=base_r)
        except (FileNotFoundError, ValueError) as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 2
        text = json.dumps(snap, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            out_fp = Path(args.output)
            _atomic_write_text(out_fp, text)
            print(f"已写入指纹快照：{out_fp}（共 {snap['file_count']} 个文件）")
        else:
            sys.stdout.write(text)
        return 0

    if args.cmd == "compare":
        old_fp = Path(args.old_snapshot)
        if not old_fp.is_file():
            print(f"错误：快照文件不存在：{old_fp}", file=sys.stderr)
            return 2
        try:
            old_snap = load_snapshot_json(old_fp)
        except Exception as exc:
            print(f"错误：读取快照失败：{exc}", file=sys.stderr)
            return 2

        try:
            if len(args.targets) == 1 and _is_snapshot_json_file(Path(args.targets[0])):
                new_snap = load_snapshot_json(Path(args.targets[0]))
            else:
                scan_list = [Path(p) for p in args.targets] if args.targets else [Path(p) for p in old_snap.get("targets", [])]
                if not scan_list:
                    print("错误：未指定要比对的新快照或目标目录。", file=sys.stderr)
                    return 2
                old_root = Path(old_snap["root"]) if old_snap.get("root") else None
                new_snap = build_snapshot(scan_list, base_root=old_root)
        except (FileNotFoundError, ValueError) as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 2

        diff = diff_snapshots(old_snap, new_snap)
        has_diff = bool(diff["added"] or diff["deleted"] or diff["modified"])
        if args.json:
            sys.stdout.write(json.dumps(diff, ensure_ascii=False, indent=2) + "\n")
        else:
            print(
                f"指纹比对汇总：新增 {len(diff['added'])}，删除 {len(diff['deleted'])}，改动 {len(diff['modified'])}"
                + ("（完全一致）" if not has_diff else "")
            )
            for label, key in (("新增", "added"), ("删除", "deleted"), ("改动", "modified")):
                for item in diff[key]:
                    print(f"  [{label}] {item}")
        return 1 if (args.check and has_diff) else 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

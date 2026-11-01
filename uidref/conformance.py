#!/usr/bin/env python3
"""uidref 一致性测试运行器。

用法::

    python conformance.py vectors/                  # 自测参考实现
    python conformance.py vectors/ --impl mymod     # 测任意 Python 实现

契约：实现须提供 ``parse_xml(xml) -> Snapshot``，Snapshot 须暴露
``package`` / ``rotation`` / 可迭代的 elements；每个 element 须有
``ref`` / ``role`` / ``label`` / ``bounds``（含 x1,y1,x2,y2）/ 各布尔标志。

退出码 0 = 全部通过。
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path


def load_impl(name: str | None):
    if name:
        return importlib.import_module(name)
    import uidref

    return uidref


def elem_dict(e) -> dict:
    return {
        "ref": e.ref,
        "role": e.role,
        "label": e.label,
        "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
        "center": [e.bounds.cx, e.bounds.cy],
        "clickable": e.clickable,
        "long_clickable": e.long_clickable,
        "scrollable": e.scrollable,
        "editable": e.editable,
        "checked": e.checked,
        "disabled": e.disabled,
        "password": e.password,
    }


def snap_dict(s) -> dict:
    return {
        "package": s.package,
        "rotation": s.rotation,
        "elements": [elem_dict(e) for e in s],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="uidref 一致性测试")
    ap.add_argument("vectors", type=Path)
    ap.add_argument("--impl", help="Python 模块名，提供 parse_xml")
    args = ap.parse_args()

    impl = load_impl(args.impl)
    files = sorted(args.vectors.glob("*.json"))
    if not files:
        print(f"在 {args.vectors} 下没找到向量文件", file=sys.stderr)
        return 2

    total = failed_files = 0
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        errs = []
        for i, c in enumerate(d["cases"]):
            total += 1
            try:
                got = snap_dict(impl.parse_xml(c["in"]))
            except Exception as e:  # noqa: BLE001
                errs.append(f"  case#{i} 抛异常 {type(e).__name__}: {e}")
                continue
            if got != c["out"]:
                errs.append(
                    f"  case#{i} why={c['why'][:40]}\n"
                    f"      期望 {json.dumps(c['out'], ensure_ascii=False)}\n"
                    f"      实得 {json.dumps(got, ensure_ascii=False)}"
                )
        if errs:
            failed_files += 1
            print(f"FAIL {f.name} — {d['title']}")
            for e in errs:
                print(e)
        else:
            print(f"ok   {f.name:34s} {d['title']:26s} ({len(d['cases'])} cases)")

    print()
    print(f"向量文件 {len(files)} 个，用例 {total} 条，失败文件 {failed_files} 个")
    return 1 if failed_files else 0


if __name__ == "__main__":
    raise SystemExit(main())

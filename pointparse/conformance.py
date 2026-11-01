#!/usr/bin/env python3
"""pointparse 一致性测试运行器。

用法::

    python conformance.py vectors/                  # 自测参考实现
    python conformance.py vectors/ --impl mymod     # 测任意 Python 实现

契约（任何语言的实现都应按此暴露一个函数）::

    parse_point(raw) -> (x, y, source_format)
                       | NO_POINT
                       | AMBIGUOUS

向量文件的 ``in`` 是 JSON 可序列化的输入（字符串、数组、对象、null、数字）。
退出码 0 = 全部通过。
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

NO_POINT = "nopoint"
AMBIGUOUS = "ambig"


def load_impl(name: str | None):
    if name:
        return importlib.import_module(name)
    import pointparse

    class _Ref:
        @staticmethod
        def parse_point(raw):
            try:
                p = pointparse.parse_point(raw)
            except pointparse.NoPointFound:
                return [NO_POINT]
            except pointparse.Ambiguity:
                return [AMBIGUOUS]
            return ["ok", p.x, p.y, p.source_format]

    return _Ref


def main() -> int:
    ap = argparse.ArgumentParser(description="pointparse 一致性测试")
    ap.add_argument("vectors", type=Path)
    ap.add_argument("--impl", help="Python 模块名，提供 parse_point(raw)")
    args = ap.parse_args()

    impl = load_impl(args.impl)
    files = sorted(args.vectors.glob("*.json"))
    if not files:
        print(f"在 {args.vectors} 下没找到向量文件", file=sys.stderr)
        return 2

    total = 0
    failed_files = 0
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        errs = []
        for i, c in enumerate(d["cases"]):
            total += 1
            try:
                got = list(impl.parse_point(c["in"]))
            except Exception as e:  # noqa: BLE001
                got = ["error", type(e).__name__]
            if got != c["out"]:
                errs.append(f"  case#{i} in={c['in']!r}\n      期望 {c['out']}\n      实得 {got}")
        if errs:
            failed_files += 1
            print(f"FAIL {f.name} — {d['title']}")
            for e in errs:
                print(e)
        else:
            print(f"ok   {f.name} — {d['title']}  ({len(d['cases'])} cases)")

    print()
    print(f"向量文件 {len(files)} 个，用例 {total} 条，失败文件 {failed_files} 个")
    return 1 if failed_files else 0


if __name__ == "__main__":
    raise SystemExit(main())

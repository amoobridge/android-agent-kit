#!/usr/bin/env python3
"""screenpoint 一致性测试运行器。

用法::

    python conformance.py vectors/                     # 自测参考实现
    python conformance.py vectors/ --impl mymod        # 测任意 Python 实现
    python conformance.py vectors/ --emit-cli-cmd ... # 测任意语言实现

契约（任何语言的实现都应按此暴露四个函数）::

    map_point(x, y, src, dst, fit)      -> [x, y]          浮点
    map_rect(x, y, w, h, src, dst, fit) -> [x, y, w, h]    浮点
    to_device_pixel(x, y, src, dst, fit)-> [x, y, clamped] 整数 + 钳制标记

``src`` / ``dst`` 的 JSON 形状见向量文件；``fit`` 为 ``stretch|fit|crop``。
退出码 0 = 全部通过。
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
from pathlib import Path

TOL = 1e-9


def load_space(d: dict):
    from screenpoint import CoordinateSpace

    kind = d["kind"]
    if kind == "pixel":
        return CoordinateSpace.pixel("space", d["width"], d["height"])
    if kind == "normalized":
        return CoordinateSpace.normalized("space", d["width"], d["height"], grid_n=d["grid_n"])
    raise SystemExit(f"未知空间类型：{kind!r}")


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0, abs_tol=TOL)


def check_vector(path: Path, impl) -> list[str]:
    from screenpoint import FitMode

    v = json.loads(path.read_text(encoding="utf-8"))
    src = load_space(v["src"])
    dst = load_space(v["dst"])
    fit = FitMode(v["fit"])
    errs: list[str] = []

    for i, c in enumerate(v["cases"]):
        ix, iy = c["in"]
        ox, oy = c["out"]
        try:
            if "clamped" in c:
                rx, ry, rc = impl.to_device_pixel(ix, iy, src, dst, fit)
                if rx != ox or ry != oy:
                    errs.append(f"  case#{i} in={c['in']} 期望 [{ox},{oy}] 实得 [{rx},{ry}]")
                if bool(rc) != bool(c["clamped"]):
                    errs.append(f"  case#{i} in={c['in']} clamped 期望 {c['clamped']} 实得 {rc}")
            else:
                rx, ry = impl.map_point(ix, iy, src, dst, fit)
                if not (close(rx, ox) and close(ry, oy)):
                    errs.append(f"  case#{i} in={c['in']} 期望 [{ox},{oy}] 实得 [{rx},{ry}]")
        except Exception as e:  # noqa: BLE001
            errs.append(f"  case#{i} in={c['in']} 抛出异常：{type(e).__name__}: {e}")

    return errs


def reference_impl():
    from screenpoint import map_point, map_rect, to_device_pixel

    class _Impl:
        @staticmethod
        def map_point(x, y, src, dst, fit):
            r = map_point(_P(x, y), src, dst, fit=fit)
            return [r.x, r.y]

        @staticmethod
        def map_rect(x, y, w, h, src, dst, fit):
            from screenpoint import Rect

            r = map_rect(Rect(x, y, w, h), src, dst, fit=fit)
            return [r.x, r.y, r.width, r.height]

        @staticmethod
        def to_device_pixel(x, y, src, dst, fit):
            r = to_device_pixel(_P(x, y), src, dst, fit=fit)
            return [r.x, r.y, r.clamped]

    return _Impl


def _P(x, y):
    from screenpoint import Point

    return Point(x, y)


def main() -> int:
    ap = argparse.ArgumentParser(description="screenpoint 一致性测试")
    ap.add_argument("vectors", type=Path, help="向量目录")
    ap.add_argument("--impl", help="Python 模块名，提供 map_point/map_rect/to_device_pixel")
    args = ap.parse_args()

    if args.impl:
        impl = importlib.import_module(args.impl)
    else:
        impl = reference_impl()

    files = sorted(args.vectors.glob("*.json"))
    if not files:
        print(f"在 {args.vectors} 下没找到向量文件", file=sys.stderr)
        return 2

    total_cases = 0
    failed_files = 0
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        total_cases += len(data["cases"])
        errs = check_vector(f, impl)
        if errs:
            failed_files += 1
            print(f"FAIL {f.name} — {data['title']}")
            for e in errs:
                print(e)
        else:
            print(f"ok   {f.name} — {data['title']}  ({len(data['cases'])} cases)")

    print()
    print(f"向量文件 {len(files)} 个，用例 {total_cases} 条，失败文件 {failed_files} 个")
    return 1 if failed_files else 0


if __name__ == "__main__":
    raise SystemExit(main())

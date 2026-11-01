#!/usr/bin/env python3
"""语言无关的一致性验证工具。

给**外部实现方**用：不管你的实现用什么语言，只要提供一个
「XML 进、JSON 出」的命令，就能对着 uidref 的 43 条黄金向量自测。

契约（全部字段必须存在，缺一个就算不符）::

    $ <你的命令> < input.xml > output.json

    {
      "package": "com.example",
      "rotation": 0,
      "elements": [
        {
          "ref": "e1", "role": "item", "label": "OK",
          "bounds": [0, 0, 100, 100],
          "center": [50, 50],
          "clickable": true, "long_clickable": false, "scrollable": false,
          "editable": false, "checked": false, "disabled": false,
          "password": false
        }
      ]
    }

    · bounds 是 [x1, y1, x2, y2]，半开区间
    · center 是真正被 tap 的点：floor((x1+x2)/2), floor((y1+y2)/2)
      **必须向负无穷取整**，不是向零截断——负坐标下两者差 1
    · ref 从 "e1" 起按前序深度优先文档序连续编号
    · 布尔一律 JSON true/false，不是 "true" 字符串

用法::

    # 测 Node 实现
    python tools/verify_impl.py vectors/ --cmd "node js/my_impl.js"

    # 测 Rust 实现（先编译）
    python tools/verify_impl.py vectors/ --cmd "./target/release/uidref"

    # 测 Python 实现（自带一个薄包装脚本）
    python tools/verify_impl.py vectors/ --cmd "python my_wrapper.py"

    # 单条调试
    python tools/verify_impl.py vectors/ --cmd "node x.js" --case label-inheritance-001:0

退出码 0 = 全部通过；1 = 有不符；2 = 用法/环境错误。
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ELEMENT_FIELDS = (
    "ref", "role", "label", "bounds", "center",
    "clickable", "long_clickable", "scrollable",
    "editable", "checked", "disabled", "password",
)
# 布尔字段显式列出，不用切片——曾用 ELEMENT_FIELDS[4:] 切片，
# 在 bounds 后插入 center 后切片起点错位，把 center 当成布尔校验。
BOOL_FIELDS = (
    "clickable", "long_clickable", "scrollable",
    "editable", "checked", "disabled", "password",
)
TOP_FIELDS = ("package", "rotation", "elements")


def run_impl(cmd: str, xml: str) -> dict:
    """把 XML 喂给实现，拿回结构化 JSON。"""
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml)
        path = f.name
    try:
        r = subprocess.run(
            shlex.split(cmd) + [path],
            capture_output=True, text=True, timeout=60,
        )
    finally:
        Path(path).unlink(missing_ok=True)

    if r.returncode != 0:
        # 取**第一行含 Error/error 的**——Node 的栈回溯最后一行只有版本号，
        # 取最后一行等于没取。找不到就退回第一行。
        lines = [l for l in (r.stderr or r.stdout or "").strip().splitlines() if l.strip()]
        hit = next((l for l in lines if "rror" in l), None)
        raise RuntimeError(f"命令退出码 {r.returncode}：{hit or (lines[0] if lines else '(无输出)')}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        head = (r.stdout or "")[:200].replace("\n", "\\n")
        raise RuntimeError(f"stdout 不是合法 JSON（{e}）：{head}") from e


def validate_shape(out: dict) -> list[str]:
    """检查字段是否齐全、类型是否正确。"""
    errs = []
    for k in TOP_FIELDS:
        if k not in out:
            errs.append(f"缺顶层字段 {k!r}")
    if errs:
        return errs
    if not isinstance(out["package"], str):
        errs.append(f"package 应为字符串，实为 {type(out['package']).__name__}")
    if not isinstance(out["rotation"], int) or isinstance(out["rotation"], bool):
        errs.append(f"rotation 应为整数，实为 {out['rotation']!r}")
    if not isinstance(out["elements"], list):
        errs.append("elements 应为数组")
        return errs
    for i, e in enumerate(out["elements"]):
        if not isinstance(e, dict):
            errs.append(f"elements[{i}] 应为对象")
            continue
        for k in ELEMENT_FIELDS:
            if k not in e:
                errs.append(f"elements[{i}] 缺字段 {k!r}")
        if "bounds" in e:
            b = e["bounds"]
            if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, int) for v in b)):
                errs.append(f"elements[{i}].bounds 应为 4 个整数：{b!r}")
        if "center" in e:
            c = e["center"]
            if not (isinstance(c, list) and len(c) == 2 and all(isinstance(v, int) for v in c)):
                errs.append(f"elements[{i}].center 应为 2 个整数：{c!r}")
        for k in BOOL_FIELDS:
            if k in e and not isinstance(e[k], bool):
                errs.append(f"elements[{i}].{k} 应为布尔，实为 {e[k]!r}")
    return errs


def diff(expect: dict, got: dict) -> list[str]:
    out = []
    if expect["package"] != got["package"]:
        out.append(f"package: 期望 {expect['package']!r} / 实得 {got['package']!r}")
    if expect["rotation"] != got["rotation"]:
        out.append(f"rotation: 期望 {expect['rotation']} / 实得 {got['rotation']}")
    a, b = expect["elements"], got["elements"]
    if len(a) != len(b):
        out.append(f"元素数: 期望 {len(a)} / 实得 {len(b)}")
    for i in range(min(len(a), len(b))):
        for k in ELEMENT_FIELDS:
            av, bv = a[i].get(k), b[i].get(k)
            if av != bv:
                out.append(f"elements[{i}].{k}: 期望 {av!r} / 实得 {bv!r}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="语言无关的 uidref 一致性验证",
        epilog="实现方只需提供「XML 进 JSON 出」的命令，见本文件 docstring 的契约。",
    )
    ap.add_argument("vectors", type=Path, nargs="?", default=ROOT / "vectors")
    ap.add_argument("--cmd", required=True,
                    help="你的实现命令，如 'node js/my_impl.js'（末位参数是 XML 文件路径）")
    ap.add_argument("--case", help="只跑某一条，格式 向量id:序号，如 label-inheritance-001:0")
    ap.add_argument("--show", action="store_true", help="打印每条用例的实际输出")
    args = ap.parse_args()

    files = sorted(args.vectors.glob("*.json"))
    if not files:
        print(f"在 {args.vectors} 下没找到向量文件", file=sys.stderr)
        return 2

    only = None
    if args.case:
        vid, _, idx = args.case.partition(":")
        only = (vid, int(idx or 0))

    total = passed = 0
    failed_files = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        if only and d["id"] != only[0]:
            continue
        errs = []
        for i, c in enumerate(d["cases"]):
            if only and i != only[1]:
                continue
            total += 1
            try:
                got = run_impl(args.cmd, c["in"])
            except Exception as e:  # noqa: BLE001
                errs.append(f"  case#{i} 执行失败：{e}")
                continue
            shape = validate_shape(got)
            if shape:
                errs.append(f"  case#{i} 输出形状不符：")
                errs.extend(f"      {x}" for x in shape[:6])
                continue
            dd = diff(c["out"], got)
            if dd:
                errs.append(f"  case#{i} why={c['why'][:48]}")
                errs.extend(f"      {x}" for x in dd[:8])
            else:
                passed += 1
                if args.show:
                    print(f"  case#{i} ✓ {c['why'][:48]}")
        if errs:
            failed_files.append(f.name)
            print(f"FAIL {f.name} — {d['title']}")
            errs and print("\n".join(errs))
        elif not only:
            print(f"ok   {f.name:34s} {d['title']}（{len(d['cases'])} cases）")

    print(f"\n用例 {total} 条，通过 {passed}，失败 {total - passed}，失败文件 {len(failed_files)} 个")
    if failed_files:
        print("未通过：" + ", ".join(failed_files))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

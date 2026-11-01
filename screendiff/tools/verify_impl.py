#!/usr/bin/env python3
"""语言无关的一致性验证工具（screendiff）。

给**外部实现方**用：不管你的实现用什么语言，只要提供一个
「JSON 对进、ChangeSet 出」的命令，就能对着黄金向量自测。

契约::

    $ <你的命令> < case.json > out.json

    case.json:
    {
      "prev": [{"ref":"e1","role":"item","label":"甲","bounds":[0,0,100,100],
                "class_name":"","resource_id":"", ...七个布尔}],
      "cur":  [ ... ]
    }

    out.json（全部字段必须存在）:
    {
      "matched": [{"prev_ref":"e1","cur_ref":"e1","changes":[]}],
      "added":   [{"ref":"e2","role":"btn","label":"确定"}],
      "removed": [],
      "is_identical": false,
      "counts": {"matched":1,"added":1,"removed":0,
                 "moved":0,"state_changed":0,"label_changed":0}
    }

    · changes 是变化类列表，unchanged 时为空数组
    · matched / added / removed 的顺序必须与参考实现一致
    · 布尔一律 JSON true/false

用法::

    python tools/verify_impl.py vectors/ --cmd "node js/impl.js"
    python tools/verify_impl.py vectors/ --cmd "./target/release/screendiff"

    # 单条调试
    python tools/verify_impl.py vectors/ --cmd "node js/impl.js" --case matching-001:0

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

ELEMENT_FIELDS = ("prev_ref", "cur_ref", "changes")
BRIEF_FIELDS = ("ref", "role", "label")
TOP_FIELDS = ("matched", "added", "removed", "is_identical", "counts")
COUNT_FIELDS = ("matched", "added", "removed", "moved",
                "state_changed", "label_changed")
BOOL_FIELDS = ("clickable", "long_clickable", "scrollable", "editable",
               "checked", "disabled", "password")


def run_impl(cmd: str, case: dict) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(case["in"], f, ensure_ascii=False)
        path = f.name
    try:
        r = subprocess.run(shlex.split(cmd) + [path],
                           capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)

    if r.returncode != 0:
        lines = [l for l in (r.stderr or r.stdout or "").strip().splitlines() if l.strip()]
        hit = next((l for l in lines if "rror" in l), None)
        raise RuntimeError(f"命令退出码 {r.returncode}：{hit or (lines[0] if lines else '(无输出)')}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        head = (r.stdout or "")[:200].replace("\n", "\\n")
        raise RuntimeError(f"stdout 不是合法 JSON（{e}）：{head}") from e


def validate_shape(out: dict) -> list[str]:
    errs = []
    for k in TOP_FIELDS:
        if k not in out:
            errs.append(f"缺顶层字段 {k!r}")
    if errs:
        return errs
    for i, m in enumerate(out["matched"]):
        for k in ELEMENT_FIELDS:
            if k not in m:
                errs.append(f"matched[{i}] 缺字段 {k!r}")
        if "changes" in m and not isinstance(m["changes"], list):
            errs.append(f"matched[{i}].changes 应为数组")
    for k in ("added", "removed"):
        for i, e in enumerate(out[k]):
            for kk in BRIEF_FIELDS:
                if kk not in e:
                    errs.append(f"{k}[{i}] 缺字段 {kk!r}")
    if not isinstance(out["is_identical"], bool):
        errs.append(f"is_identical 应为布尔，实为 {out['is_identical']!r}")
    for k in COUNT_FIELDS:
        if k not in out["counts"]:
            errs.append(f"counts 缺字段 {k!r}")
    return errs


def diff(expect: dict, got: dict) -> list[str]:
    out = []
    if len(expect["matched"]) != len(got["matched"]):
        out.append(f"matched 数：期望 {len(expect['matched'])} / 实得 {len(got['matched'])}")
    else:
        for i, (a, b) in enumerate(zip(expect["matched"], got["matched"])):
            for k in ELEMENT_FIELDS:
                if a[k] != b[k]:
                    out.append(f"matched[{i}].{k}: 期望 {a[k]!r} / 实得 {b[k]!r}")
    for k in ("added", "removed"):
        if len(expect[k]) != len(got[k]):
            out.append(f"{k} 数：期望 {len(expect[k])} / 实得 {len(got[k])}")
        else:
            for i, (a, b) in enumerate(zip(expect[k], got[k])):
                for kk in BRIEF_FIELDS:
                    if a[kk] != b[kk]:
                        out.append(f"{k}[{i}].{kk}: 期望 {a[kk]!r} / 实得 {b[kk]!r}")
    if expect["is_identical"] != got["is_identical"]:
        out.append(f"is_identical: 期望 {expect['is_identical']} / 实得 {got['is_identical']}")
    if expect["counts"] != got["counts"]:
        out.append(f"counts: 期望 {expect['counts']} / 实得 {got['counts']}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="语言无关的 screendiff 一致性验证",
        epilog="实现方只需提供「JSON 对进、ChangeSet 出」的命令，见 docstring 契约。")
    ap.add_argument("vectors", type=Path, nargs="?", default=ROOT / "vectors")
    ap.add_argument("--cmd", required=True,
                    help="你的实现命令，如 'node js/impl.js'（末位参数是 case.json 路径）")
    ap.add_argument("--case", help="只跑某一条，格式 向量id:序号")
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
                got = run_impl(args.cmd, c)
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
                errs.append(f"  case#{i} why={c['why'][:44]}")
                errs.extend(f"      {x}" for x in dd[:8])
            else:
                passed += 1
                if args.show:
                    print(f"  case#{i} ✓ {c['why'][:44]}")
        if errs:
            failed_files.append(f.name)
            print(f"FAIL {f.name} — {d['title']}")
            print("\n".join(errs))
        elif not only:
            print(f"ok   {f.name:24s} {d['title']}（{len(d['cases'])} cases）")

    print(f"\n用例 {total} 条，通过 {passed}，失败 {total - passed}，失败文件 {len(failed_files)} 个")
    if failed_files:
        print("未通过：" + ", ".join(failed_files))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

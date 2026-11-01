#!/usr/bin/env python3
"""screendiff · Python 侧一致性运行器。

    python conformance.py vectors/

对每个向量文件里的每条用例，用参考实现算一遍，与期望输出逐字段比对。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screendiff.core import Element, diff  # noqa: E402

FIELDS = ("prev_ref", "cur_ref", "changes")
TOP = ("matched", "added", "removed", "is_identical", "counts")


def _load(seq) -> list[Element]:
    return [Element(
        ref=e["ref"], role=e["role"], label=e["label"], bounds=tuple(e["bounds"]),
        class_name=e.get("class_name", ""), resource_id=e.get("resource_id", ""),
        **{f: bool(e.get(f, False)) for f in
           ("clickable", "long_clickable", "scrollable", "editable",
            "checked", "disabled", "password")},
    ) for e in seq]


def run(vectors: Path) -> int:
    files = sorted(vectors.glob("*.json"))
    if not files:
        print(f"在 {vectors} 下没找到向量文件", file=sys.stderr)
        return 2

    total = passed = 0
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        errs = []
        for i, c in enumerate(d["cases"]):
            total += 1
            got = diff(_load(c["in"]["prev"]), _load(c["in"]["cur"])).to_dict()
            exp = c["out"]
            for k in TOP:
                if k not in got:
                    errs.append(f"case#{i} 缺顶层字段 {k!r}")
            if len(got["matched"]) != len(exp["matched"]):
                errs.append(f"case#{i} matched 数：期望 {len(exp['matched'])} / 实得 {len(got['matched'])}")
            else:
                for j, (a, b) in enumerate(zip(exp["matched"], got["matched"])):
                    for k in FIELDS:
                        if a[k] != b[k]:
                            errs.append(f"case#{i} matched[{j}].{k}: 期望 {a[k]!r} / 实得 {b[k]!r}")
            for k in ("added", "removed"):
                if len(got[k]) != len(exp[k]):
                    errs.append(f"case#{i} {k} 数：期望 {len(exp[k])} / 实得 {len(got[k])}")
                else:
                    for j, (a, b) in enumerate(zip(exp[k], got[k])):
                        for kk in ("ref", "role", "label"):
                            if a[kk] != b[kk]:
                                errs.append(f"case#{i} {k}[{j}].{kk}: 期望 {a[kk]!r} / 实得 {b[kk]!r}")
            if got["is_identical"] != exp["is_identical"]:
                errs.append(f"case#{i} is_identical: 期望 {exp['is_identical']} / 实得 {got['is_identical']}")
            if got["counts"] != exp["counts"]:
                errs.append(f"case#{i} counts: 期望 {exp['counts']} / 实得 {got['counts']}")
            if not errs or all(f"case#{i} " not in e for e in errs):
                passed += 1
        status = "ok  " if not errs else "FAIL"
        print(f"{status} {f.name:24s} {d['title']}（{len(d['cases'])} cases）")
        for e in errs:
            print("     ", e)
    print(f"\n向量文件 {len(files)} 个，用例 {total} 条，失败文件 "
          f"{sum(1 for f in files if _failed(f))} 个")
    return 0 if passed == total else 1


def _failed(f: Path) -> bool:
    d = json.loads(f.read_text(encoding="utf-8"))
    for c in d["cases"]:
        got = diff(_load(c["in"]["prev"]), _load(c["in"]["cur"])).to_dict()
        if got != c["out"]:
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1] if len(sys.argv) > 1 else "vectors")))

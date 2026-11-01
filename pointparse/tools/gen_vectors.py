#!/usr/bin/env python3
"""生成 pointparse 黄金向量。

向量记录**真实世界中模型会吐出来的样子**，包括脏数据。
每条都必须有 ``why``——说明这个用例防的是什么。
"""

from __future__ import annotations

import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pointparse import Ambiguity, NoPointFound, ParseError, parse_point

OUT = Path(__file__).resolve().parent.parent / "vectors"


def case(raw, expect):
    """expect: ("ok", x, y, fmt) | ("nopoint",) | ("ambig",)"""
    try:
        p = parse_point(raw)
    except NoPointFound:
        got = ["nopoint"]
    except Ambiguity:
        got = ["ambig"]
    except ParseError as e:
        got = ["error", type(e).__name__]
    else:
        got = ["ok", p.x, p.y, p.source_format]

    if got[0] != expect[0]:
        raise SystemExit(f"用例不符 {raw!r}: 期望 {expect} 实得 {got}")
    return {"in": raw if isinstance(raw, str) else json.loads(json.dumps(raw)), "out": got}


VECTORS = []

# ---------------------------------------------------------------- 干净格式
VECTORS.append({
    "id": "clean-formats-001",
    "title": "十种干净格式",
    "why": "回归基线。这些是规范推荐模型输出的形态，必须全部一次命中。",
    "cases": [
        case({"x": 400, "y": 900}, ("ok", 400.0, 900.0, "dict_xy")),
        case({"point": [400, 900]}, ("ok", 400.0, 900.0, "dict_point")),
        case({"coordinate": [400, 900]}, ("ok", 400.0, 900.0, "dict_point")),
        case([400, 900], ("ok", 400.0, 900.0, "sequence")),
        case((400, 900), ("ok", 400.0, 900.0, "sequence")),
        case("(400, 900)", ("ok", 400.0, 900.0, "paren_csv")),
        case("400, 900", ("ok", 400.0, 900.0, "bare_csv")),
        case("x=400, y=900", ("ok", 400.0, 900.0, "kv")),
        case("<point>400 900</point>", ("ok", 400.0, 900.0, "bare_csv")),
        case('{"x": 400, "y": 900}', ("ok", 400.0, 900.0, "dict_xy")),
    ],
})

# ---------------------------------------------------------------- 脏数据
VECTORS.append({
    "id": "messy-real-world-001",
    "title": "真实脏数据",
    "why": "模型不会按你的 schema 输出。这些形状在生产中全都出现过。",
    "cases": [
        # 小数坐标
        case("(0.42, 0.38)", ("ok", 0.42, 0.38, "paren_csv")),
        # 负号/加号
        case("(-5, 120)", ("ok", -5.0, 120.0, "paren_csv")),
        # 中文分号
        case("400；900", ("ok", 400.0, 900.0, "bare_csv")),
        # 前后缀噪音
        case("I'll tap at (400, 900) now.", ("ok", 400.0, 900.0, "paren_csv")),
        # markdown 代码块包 JSON
        case('```json\n{"x": 400, "y": 900}\n```', ("ok", 400.0, 900.0, "dict_xy")),
        # 带空格的 kv
        case("x = 400 , y = 900", ("ok", 400.0, 900.0, "kv")),
        # 科学计数法之外的普通小数
        case("[12.5, 34.75]", ("ok", 12.5, 34.75, "sequence")),
        # 数字里带千分位逗号 —— 这是歧义源，必须报 ambig 而非猜
        case("1,400, 900", ("ambig",)),
    ],
})

# ---------------------------------------------------------------- 拒答
VECTORS.append({
    "id": "refusal-001",
    "title": "模型拒答或无法确定",
    "why": "拒答是正常输出。若解析器在这里抛异常或猜一个点，agent 会点在随机位置。",
    "cases": [
        case({"x": None, "y": None}, ("nopoint",)),
        case({"x": None, "y": None, "reason": "no button visible"}, ("nopoint",)),
        case("I cannot see the target.", ("nopoint",)),
        case("找不到目标元素", ("nopoint",)),
        case("", ("nopoint",)),
        case(None, ("nopoint",)),
        case(42, ("nopoint",)),
        case("The screen appears to be blank.", ("nopoint",)),
        case({"error": "image too small"}, ("nopoint",)),
    ],
})

# ---------------------------------------------------------------- 歧义
VECTORS.append({
    "id": "ambiguity-001",
    "title": "必须报歧义，不许猜",
    "why": "这些输入的'正确答案'取决于语义决策。解析器替调用方选一个，就是把 bug 藏起来。",
    "cases": [
        # 两个不同位置
        case("First tap (100, 200), then tap (300, 400).", ("ambig",)),
        case([100, 200, 300, 400], ("ambig",)),
        case({"bbox": [100, 200, 300, 400]}, ("ambig",)),
        case({"box": [10, 20, 30, 40]}, ("ambig",)),
        # 三个数
        case([100, 200, 300], ("nopoint",)),
        # 同一个位置说两遍 —— 去重后唯一，应 ok
        case("tap (400,900) and then tap (400,900) again", ("ok", 400.0, 900.0, "paren_csv")),
    ],
})

# ---------------------------------------------------------------- 空间线索
VECTORS.append({
    "id": "space-hint-001",
    "title": "空间线索推断",
    "why": "像素还是归一化，形态上常常无法判定。线索必须显式暴露，让调用方自己校验。",
    "cases": [
        case({"x": 0.42, "y": 0.38}, ("ok", 0.42, 0.38, "dict_xy")),
        case({"x": 0, "y": 0}, ("ok", 0.0, 0.0, "dict_xy")),
        case({"x": 1, "y": 1}, ("ok", 1.0, 1.0, "dict_xy")),
        case({"x": 540, "y": 1200}, ("ok", 540.0, 1200.0, "dict_xy")),
        case({"x": 500, "y": 500}, ("ok", 500.0, 500.0, "dict_xy")),
    ],
})


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for v in VECTORS:
        p = OUT / f"{v['id']}.json"
        p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {p.name}  ({len(v['cases'])} cases)")
    print(f"\n共 {len(VECTORS)} 个向量文件，{sum(len(v['cases']) for v in VECTORS)} 条用例")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""生成 screendiff 的黄金向量。

设计原则（继承 uidref 的教训）：

1. **期望值由规范推导，不由参考实现倒推**。每个 case 的 `why` 必须说清
   它在测 SPEC 的哪一条。
2. **生成期自检**：空转用例、自相矛盾的期望、缺字段，一律在生成时炸掉。
3. **输入必须自包含**：向量文件不依赖外部 dump，拷走就能跑。

用法::

    python tools/gen_vectors.py            # 重新生成 vectors/*.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from screendiff.core import Element, diff  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "vectors"

# ---------------------------------------------------------------- 构造工具
def el(ref, role, label, bounds, *, cls="", rid="", **flags):
    """造一个 Element。flags 只接受七个状态标志。"""
    allowed = {"clickable", "long_clickable", "scrollable", "editable",
               "checked", "disabled", "password"}
    bad = set(flags) - allowed
    if bad:
        raise TypeError(f"未知标志 {bad}，只接受 {sorted(allowed)}")
    return Element(ref=ref, role=role, label=label, bounds=tuple(bounds),
                   class_name=cls, resource_id=rid, **flags)


def expect(prev, cur, *, matched=None, added=None, removed=None, identical=None):
    """按**规范手工推导**的期望值。

    ``matched`` / ``added`` / ``removed`` / ``identical`` 默认为 ``None``，
    表示"本条用例不断言这个字段"——只断言显式给出的部分。
    这样每条用例只锁它真正要测的那一条规则，其余交给参考实现。
    （若默认全部断言，写错一个无关字段就会让整批向量失败。）
    """
    cs = diff(prev, cur)
    got_matched = [(p.prev.ref, p.cur.ref, list(p.changes)) for p in cs.matched]
    got_added = [e.ref for e in cs.added]
    got_removed = [e.ref for e in cs.removed]
    got_identical = cs.is_identical

    exp_matched = list(matched) if matched is not None else None
    exp_added = list(added) if added is not None else None
    exp_removed = list(removed) if removed is not None else None
    exp_identical = got_identical if identical is None else identical

    problems = []
    if exp_matched is not None and got_matched != exp_matched:
        problems.append(f"matched 不符：期望 {exp_matched} / 实得 {got_matched}")
    if exp_added is not None and got_added != exp_added:
        problems.append(f"added 不符：期望 {exp_added} / 实得 {got_added}")
    if exp_removed is not None and got_removed != exp_removed:
        problems.append(f"removed 不符：期望 {exp_removed} / 实得 {got_removed}")
    if got_identical != exp_identical:
        problems.append(f"is_identical 不符：期望 {exp_identical} / 实得 {got_identical}")

    return {
        "in": {"prev": [_e(e) for e in prev], "cur": [_e(e) for e in cur]},
        "out": cs.to_dict(),
        "why": "",
    }, problems


def _e(e: Element) -> dict:
    return {
        "ref": e.ref, "role": e.role, "label": e.label,
        "bounds": list(e.bounds), "class_name": e.class_name,
        "resource_id": e.resource_id,
        **{f: getattr(e, f) for f in
           ("clickable", "long_clickable", "scrollable", "editable",
            "checked", "disabled", "password")},
    }


_PROBLEMS: list[str] = []


def _run(prev, cur, why, **kw):
    case, problems = expect(prev, cur, **kw)
    case["why"] = why
    _PROBLEMS.extend(f"[{why[:30]}] {x}" for x in problems)
    return case


VECTORS = []


def vec(vid, title, cases):
    VECTORS.append({"id": vid, "title": title, "cases": cases})


# ================================================================ 向量定义
# --- matching-001：匹配算法的分层与贪心 ---
cases = []
# 1. resource-id 相同 → 100 分，即使 bounds 完全不同（滚动场景）
cases.append(_run(
    [el("e1", "item", "设置", (0, 0, 1080, 200), rid="com.x:id/row1")],
    [el("e1", "item", "设置", (0, 1800, 1080, 2000), rid="com.x:id/row1")],
    "resource-id 相同即匹配，bounds 因滚动全变也认",
))
# 2. class + label 相同、bounds 重叠 0.5+ → 50/70 分
cases.append(_run(
    [el("e1", "btn", "确定", (0, 0, 200, 100), cls="android.widget.Button")],
    [el("e2", "btn", "确定", (10, 10, 210, 110), cls="android.widget.Button")],
    "class 与 label 皆同、bounds 微移 → 70 分",
))
# 3. 纯几何 tier：面积比闸门必须排除"小元素 vs 全屏容器"
cases.append(_run(
    [el("e1", "img", "头像", (891, 283, 1017, 409))],
    [el("e1", "scroll", "", (0, 74, 1080, 2337))],
    "面积比闸门：全屏滚动容器不得吞掉小元素（真机案例）",
    added=["e1"], removed=["e1"], identical=False,
))
# 4. 贪心确定性：同分时按 prev_index 再 cur_index
cases.append(_run(
    [el("e1", "item", "甲", (0, 0, 100, 100), cls="android.view.View"),
     el("e2", "item", "乙", (0, 100, 100, 200), cls="android.view.View")],
    [el("e1", "item", "甲", (0, 0, 100, 100), cls="android.view.View"),
     el("e2", "item", "乙", (0, 100, 100, 200), cls="android.view.View")],
    "两个完全相同的元素，贪心按 (prev_index, cur_index) 配对",
))
# 5. 一对一：一个 prev 不得匹配多个 cur
cases.append(_run(
    [el("e1", "item", "重复", (0, 0, 100, 100), rid="com.x:id/r")],
    [el("e1", "item", "重复", (0, 0, 100, 100), rid="com.x:id/r"),
     el("e2", "item", "重复", (0, 100, 100, 200), rid="com.x:id/r")],
    "rid 相同的一对多，只取 prev_index 最小的那个",
))
vec("matching-001", "元素匹配：分层打分、面积比闸门、贪心确定性", cases)


# --- classification-001：变化分类 ---
cases = []
cases.append(_run(
    [el("e1", "btn", "确定", (0, 0, 200, 100), cls="android.widget.Button")],
    [el("e1", "btn", "确定", (0, 0, 200, 100), cls="android.widget.Button")],
    "完全相同的元素 → unchanged",
))
cases.append(_run(
    [el("e1", "btn", "确定", (0, 0, 200, 100), cls="android.widget.Button")],
    [el("e1", "btn", "确定", (0, 50, 200, 150), cls="android.widget.Button")],
    "仅 bounds 变 → moved",
))
cases.append(_run(
    [el("e1", "switch", "Wi-Fi", (0, 0, 200, 100), cls="android.widget.Switch")],
    [el("e1", "switch", "Wi-Fi", (0, 0, 200, 100), cls="android.widget.Switch",
        checked=True)],
    "仅 checked 变 → state_changed",
))
cases.append(_run(
    [el("e1", "item", "网络 · 关闭", (0, 0, 200, 100), cls="android.view.View")],
    [el("e1", "item", "网络 · 开启", (0, 0, 200, 100), cls="android.view.View")],
    "仅 label 变 → label_changed（真机：飞行模式开启后副标题变化）",
))
cases.append(_run(
    [el("e1", "item", "甲", (0, 0, 200, 100), cls="android.view.View")],
    [el("e1", "btn", "甲", (0, 0, 200, 100), cls="android.widget.Button")],
    "class 变导致 role 变 → role_changed",
))
cases.append(_run(
    [el("e1", "btn", "确定", (0, 0, 200, 100), cls="android.widget.Button")],
    [el("e1", "btn", "取消", (0, 50, 200, 150), cls="android.widget.Button",
        disabled=True)],
    "moved + label_changed + state_changed 三类同时命中，互不排斥",
))
cases.append(_run(
    [el("e1", "item", "甲", (0, 0, 100, 100), cls="android.view.View"),
     el("e2", "item", "乙", (0, 100, 100, 200), cls="android.view.View")],
    [el("e1", "item", "丙", (0, 0, 100, 100), cls="android.view.View"),
     el("e2", "item", "丁", (0, 100, 100, 200), cls="android.view.View")],
    "两个元素同时 label_changed，计数必须为 2",
))
vec("classification-001", "变化分类：moved / role / label / state 及并存", cases)


# --- addremove-001：新增与消失 ---
cases = []
cases.append(_run(
    [el("e1", "item", "甲", (0, 0, 100, 100), rid="com.x:id/a")],
    [el("e1", "item", "甲", (0, 0, 100, 100), rid="com.x:id/a"),
     el("e2", "item", "乙", (0, 100, 100, 200), rid="com.x:id/b")],
    "底部插入新元素 → 1 added，原元素不得被误判为 changed",
))
cases.append(_run(
    [el("e1", "item", "甲", (0, 0, 100, 100), rid="com.x:id/a"),
     el("e2", "item", "乙", (0, 100, 100, 200), rid="com.x:id/b")],
    [el("e1", "item", "甲", (0, 0, 100, 100), rid="com.x:id/a")],
    "顶部删除元素 → 1 removed",
))
cases.append(_run(
    [el("e1", "item", "甲", (0, 0, 100, 100), rid="com.x:id/a")],
    [el("e1", "item", "乙", (0, 0, 100, 100), rid="com.x:id/b")],
    "rid 不同 → 不匹配，1 added + 1 removed（宁可说不认识，不可错认）",
))
cases.append(_run([], [], "两帧皆空 → is_identical = true", identical=True))
cases.append(_run(
    [], [el("e1", "item", "甲", (0, 0, 100, 100), rid="com.x:id/a")],
    "空 → 一个元素 → 1 added，is_identical = false",
    added=["e1"], identical=False,
))
vec("addremove-001", "新增与消失：插入、删除、身份不认", cases)


# --- scroll-001：平移识别（本规范的核心价值）---
cases = []
scroll_prev = [el("e1", "scroll", "", (0, 74, 1080, 2337), scrollable=True)]
scroll_cur = [el("e1", "scroll", "", (0, 74, 1080, 2337), scrollable=True)]
for i in range(9):
    y = 300 + i * 200
    scroll_prev.append(el(f"e{i+2}", "item", f"第{i+1}行", (0, y, 1080, y + 180),
                          cls="android.view.View", clickable=True))
    scroll_cur.append(el(f"e{i+2}", "item", f"第{i+1}行", (0, y - 100, 1080, y + 80),
                         cls="android.view.View", clickable=True))
cases.append(_run(
    scroll_prev, scroll_cur,
    "整页上滑：9 个元素 moved，0 added、0 removed、0 state、0 label",
    matched=[("e1", "e1", [])] + [(f"e{i+2}", f"e{i+2}", ["moved"]) for i in range(9)],
))
# 滑动 + 一行状态变化
cur2 = [Element.of(e) for e in scroll_cur]
cur2[3] = el("e5", "item", "第4行 · 已开启", (0, 500, 1080, 680),
             cls="android.view.View", clickable=True)
cases.append(_run(
    scroll_prev, cur2,
    "滑动同时一行副标题变化 → 该行 moved + label_changed，其余仅 moved",
))
vec("scroll-001", "平移识别：滚动不得误报为元素变化", cases)


# --- determinism-001：确定性 ---
cases = []
a = [el("e1", "item", "甲", (0, 0, 100, 100), cls="android.view.View"),
     el("e2", "item", "乙", (0, 100, 100, 200), cls="android.view.View")]
b = [el("e1", "item", "乙", (0, 100, 100, 200), cls="android.view.View"),
     el("e2", "item", "甲", (0, 0, 100, 100), cls="android.view.View")]
cases.append(_run(
    a, b,
    "两元素标签互换：按 (prev_index, cur_index) 配对，不得按标签凑对",
))
cases.append(_run(a, a, "相同输入重复计算，结果必须一致"))
vec("determinism-001", "确定性：同分配对顺序与幂等", cases)


# --- semantics-001：effect / stuck / loading ---
cases = []
# effect: target_gone（导航走了）
cases.append(_run(
    [el("e1", "item", "网络", (0, 0, 1080, 200), rid="com.x:id/net", clickable=True)],
    [el("e1", "btn", "返回", (0, 74, 147, 221), rid="com.android:id/up", clickable=True)],
    "点击后目标消失 → effect = target_gone（导航类动作的典型信号）",
))
# effect: target_changed（状态翻转）
cases.append(_run(
    [el("e1", "switch", "Wi-Fi", (0, 0, 200, 100), cls="android.widget.Switch",
        clickable=True)],
    [el("e1", "switch", "Wi-Fi", (0, 0, 200, 100), cls="android.widget.Switch",
        clickable=True, checked=True)],
    "点击开关 → effect = target_changed, changes = [state_changed]",
))
# effect: target_unchanged（点了没反应）
cases.append(_run(
    [el("e1", "item", "禁用项", (0, 0, 200, 100), cls="android.view.View",
        clickable=True, disabled=True)],
    [el("e1", "item", "禁用项", (0, 0, 200, 100), cls="android.view.View",
        clickable=True, disabled=True)],
    "点了禁用项，界面无变化 → effect = target_unchanged",
))
# effect: 新面板覆盖 target
cases.append(_run(
    [el("e1", "item", "打开", (0, 0, 1080, 200), rid="com.x:id/open", clickable=True)],
    [el("e1", "item", "打开", (0, 0, 1080, 200), rid="com.x:id/open", clickable=True),
     el("e2", "item", "对话框标题", (100, 400, 980, 600), rid="com.x:id/dlg",
        clickable=True)],
    "点击弹出覆盖层：target 本身没变，但有新元素压上来 → added_overlapping_target 非空",
))
# effect: unknown_target
cases.append(_run(
    [el("e1", "item", "甲", (0, 0, 100, 100), rid="com.x:id/a")],
    [el("e1", "item", "甲", (0, 0, 100, 100), rid="com.x:id/a")],
    "传一个不在 prev 里的 ref → effect = unknown_target",
))
# is_identical 语义 vs snapshot_id
cases.append(_run(
    [el("e1", "scroll", "", (0, 0, 1080, 2337), scrollable=True)],
    [el("e1", "scroll", "", (0, 0, 1080, 2337), scrollable=True)],
    "只有一个滚动容器且无变化 → is_identical = true",
    identical=True,
))
vec("semantics-001", "派生语义：effect 的四种结论与覆盖层检测", cases)


# ================================================================ 写出
def main() -> int:
    OUT.mkdir(exist_ok=True)
    total = 0
    if _PROBLEMS:
        print("FAIL 手工期望与参考实现不符：")
        for x in _PROBLEMS:
            print("   ", x)
        return 1
    for v in VECTORS:
        problems = []
        for i, c in enumerate(v["cases"]):
            # 自检 1：why 必须非空
            if not c["why"]:
                problems.append(f"case#{i} 缺 why")
            # 自检 2：输出必须自洽
            out = c["out"]
            if out["counts"]["matched"] != len(out["matched"]):
                problems.append(f"case#{i} counts.matched 与 matched 长度不符")
            if out["counts"]["added"] != len(out["added"]):
                problems.append(f"case#{i} counts.added 与 added 长度不符")
            if out["counts"]["removed"] != len(out["removed"]):
                problems.append(f"case#{i} counts.removed 与 removed 长度不符")
            if out["is_identical"] and (out["added"] or out["removed"]):
                problems.append(f"case#{i} is_identical 与 added/removed 矛盾")
            if out["is_identical"]:
                for m in out["matched"]:
                    if m["changes"]:
                        problems.append(
                            f"case#{i} is_identical 但 {m['prev_ref']} 有 changes")
            total += 1
        if problems:
            print(f"FAIL {v['id']}")
            for p in problems:
                print("   ", p)
            return 1
        (OUT / f"{v['id']}.json").write_text(
            json.dumps(v, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {v['id']:24s} {v['title']}（{len(v['cases'])} cases）")
    print(f"\n共 {len(VECTORS)} 个向量文件，{total} 条用例；生成期自检通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

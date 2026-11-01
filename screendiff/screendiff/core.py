"""screendiff · 跨快照元素匹配与变化分类。

两条硬规则（SPEC §4 / §5）：

1. **匹配必须确定性**。排序键 `(-score, prev_index, cur_index)` 完全确定，
   不依赖字典序、哈希值、并发顺序。
2. **平移不是变化**。bounds 变了归 `moved`，与 added / removed / state_changed
   分开统计。逐位比对会把滚动误报成"所有元素都变了"。

输入是 uidref 的 Snapshot（鸭子类型：只要有 `.elements`，每个元素有
`ref` / `role` / `label` / `bounds` / `class_name` / `resource_id` 及
七个布尔标志即可）。本模块不 import uidref，避免硬依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

__all__ = [
    "Element", "ChangeSet", "MatchedPair", "Effect", "diff", "effect_of",
    "is_stuck", "is_loading", "CHANGE_KINDS",
]

# 参与 state_changed 判定的七个标志（SPEC §5）
_STATE_FLAGS = (
    "clickable", "long_clickable", "scrollable",
    "editable", "checked", "disabled", "password",
)

# 变化类。顺序即契约里的枚举顺序，实现必须一致。
CHANGE_KINDS = ("moved", "role_changed", "label_changed", "state_changed")

# is_loading 的角色集合（SPEC §6.3，应该级）
_LOADING_ROLES = frozenset({"progress", "scroll"})
_INTERACTIVE_ROLES = frozenset(
    {"btn", "input", "switch", "item", "radio", "check", "slider"})


# ---------------------------------------------------------------- 输入适配
def _bounds_tuple(b: Any) -> tuple[int, int, int, int]:
    """把 bounds 规成 (x1, y1, x2, y2)。uidref 的 Bounds 或四元组都吃。"""
    if isinstance(b, (tuple, list)) and len(b) == 4:
        return (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
    return (int(b.x1), int(b.y1), int(b.x2), int(b.y2))


@dataclass(frozen=True, slots=True)
class Element:
    """匹配用的最小元素视图。与 uidref.Element 字段对齐。"""

    ref: str
    role: str
    label: str
    bounds: tuple[int, int, int, int]
    class_name: str = ""
    resource_id: str = ""
    clickable: bool = False
    long_clickable: bool = False
    scrollable: bool = False
    editable: bool = False
    checked: bool = False
    disabled: bool = False
    password: bool = False

    @classmethod
    def of(cls, e: Any) -> "Element":
        """从任意有这些属性的对象**或 dict**构造。

        bounds 支持 Bounds 对象或四元组。dict 形式直接来自黄金向量，
        这样 diff() 可以吃向量原文，不必先转一道。
        """
        if isinstance(e, dict):
            get = e.get
        else:
            get = lambda k, d=None: getattr(e, k, d)  # noqa: E731
        return cls(
            ref=get("ref", ""), role=get("role", ""), label=get("label", ""),
            bounds=_bounds_tuple(get("bounds")),
            class_name=get("class_name", "") or "",
            resource_id=get("resource_id", "") or "",
            **{f: bool(get(f, False)) for f in _STATE_FLAGS},
        )

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bounds
        return max(0, x2 - x1) * max(0, y2 - y1)


def _elements_of(snapshot: Any) -> list[Element]:
    """接受 uidref Snapshot、Element 列表、或 dict 列表。"""
    if isinstance(snapshot, Sequence) and not isinstance(snapshot, (str, bytes)):
        items: Iterable[Any] = snapshot
    else:
        items = getattr(snapshot, "elements", snapshot)
    out = []
    for e in items:
        out.append(e if isinstance(e, Element) else Element.of(e))
    return out


# ---------------------------------------------------------------- 打分
def _overlap(a: Element, b: Element) -> float:
    """bounds 重叠率 = 交面积 / min(两者面积)。任一面为 0 则 0。"""
    ax1, ay1, ax2, ay2 = a.bounds
    bx1, by1, bx2, by2 = b.bounds
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    denom = min(a.area, b.area)
    if denom == 0:
        return 0.0
    return inter / denom


def _score(p: Element, c: Element) -> int:
    """候选对打分。SPEC §4.1。0 = 不是候选。

    **三个身份 tier 都要求对应字段非空**——空字符串等于"没有这个信号"，
    两个都没有 class_name 的元素不构成"类名相同"。
    （2026-10-27 踩过：不加非空判断时，两个匿名元素因 class_name 都为空
    而被判为同类，进而靠几何重叠匹配上，误报率很高。）
    """
    if p.resource_id and p.resource_id == c.resource_id:
        return 100
    if p.class_name and p.class_name == c.class_name and p.label and p.label == c.label:
        return 70
    ov = _overlap(p, c)
    if p.class_name and p.class_name == c.class_name and ov >= 0.5:
        return 50
    if p.label and p.label == c.label and ov >= 0.5:
        return 35
    if ov >= 0.8 and _size_ratio(p, c) >= 0.5:
        return 20
    return 0


def _size_ratio(a: Element, b: Element) -> float:
    """min(area) / max(area)。任一面为 0 则 0。

    **为什么纯几何 tier 需要这道闸**（2026-10-27 真机案例）：
    设置主页的滚动容器 bounds 是 [0,74][1080,2337]，几乎覆盖全屏。
    它与页面上**任何**元素的重叠率都 ≥ 0.8。于是"头像图片"这种
    在新页面里没有对应物的元素，会被贪心匹配到新页面的滚动容器上，
    报告"头像变成了滚动容器"——一个完全错误的匹配。

    加上面积比闸门后，小元素 vs 全屏容器的比值趋近 0，直接排除。
    """
    aa, ba = a.area, b.area
    if aa == 0 or ba == 0:
        return 0.0
    return min(aa, ba) / max(aa, ba)


# ---------------------------------------------------------------- 结果类型
@dataclass(frozen=True, slots=True)
class MatchedPair:
    prev: Element
    cur: Element

    @property
    def moved(self) -> bool:
        return self.prev.bounds != self.cur.bounds

    @property
    def role_changed(self) -> bool:
        return self.prev.role != self.cur.role

    @property
    def label_changed(self) -> bool:
        return self.prev.label != self.cur.label

    @property
    def state_changed(self) -> bool:
        return any(
            getattr(self.prev, f) != getattr(self.cur, f) for f in _STATE_FLAGS
        )

    @property
    def changes(self) -> tuple[str, ...]:
        return tuple(
            k for k in CHANGE_KINDS
            if getattr(self, k)
        )

    @property
    def unchanged(self) -> bool:
        return not self.changes


@dataclass(frozen=True, slots=True)
class ChangeSet:
    prev_elements: tuple[Element, ...]
    cur_elements: tuple[Element, ...]
    matched: tuple[MatchedPair, ...]
    added: tuple[Element, ...]
    removed: tuple[Element, ...]

    @property
    def is_identical(self) -> bool:
        """SPEC §5.1。注意：语义判定，不等于 snapshot_id 相等。"""
        if self.added or self.removed:
            return False
        return all(p.unchanged for p in self.matched)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "matched": len(self.matched),
            "added": len(self.added),
            "removed": len(self.removed),
            "moved": sum(1 for p in self.matched if p.moved),
            "state_changed": sum(1 for p in self.matched if p.state_changed),
            "label_changed": sum(1 for p in self.matched if p.label_changed),
        }

    def to_dict(self) -> dict:
        """一致性契约输出（SPEC §8.1）。"""
        return {
            "matched": [
                {
                    "prev_ref": p.prev.ref,
                    "cur_ref": p.cur.ref,
                    "changes": list(p.changes),
                }
                for p in self.matched
            ],
            "added": [
                {"ref": e.ref, "role": e.role, "label": e.label}
                for e in self.added
            ],
            "removed": [
                {"ref": e.ref, "role": e.role, "label": e.label}
                for e in self.removed
            ],
            "is_identical": self.is_identical,
            "counts": self.counts,
        }


# ---------------------------------------------------------------- 匹配
def diff(prev: Any, cur: Any) -> ChangeSet:
    """跨快照元素匹配。SPEC §4。"""
    P = _elements_of(prev)
    C = _elements_of(cur)

    # 候选对：分数 > 0 的全部 (i, j)
    cands: list[tuple[int, int, int]] = []
    for i, p in enumerate(P):
        for j, c in enumerate(C):
            s = _score(p, c)
            if s > 0:
                cands.append((-s, i, j))

    # SPEC §4.3：按 (-score, prev_index, cur_index) 升序 = 分数降序 + 下标升序
    cands.sort()

    used_p: set[int] = set()
    used_c: set[int] = set()
    pairs: list[tuple[int, int, MatchedPair]] = []
    for _, i, j in cands:
        if i in used_p or j in used_c:
            continue
        used_p.add(i)
        used_c.add(j)
        pairs.append((i, j, MatchedPair(P[i], C[j])))

    # matched 按 (prev_index, cur_index) 升序，保证输出确定（SPEC §4.4）
    # 注意：不能用 list.index() 排序——Element 是值对象，两个字段完全
    # 相同的元素会让 index() 指向同一个，排序结果不确定。
    pairs.sort(key=lambda t: (t[0], t[1]))
    added = tuple(c for j, c in enumerate(C) if j not in used_c)
    removed = tuple(p for i, p in enumerate(P) if i not in used_p)

    return ChangeSet(
        tuple(P), tuple(C), tuple(p for _, _, p in pairs), added, removed,
    )


# ---------------------------------------------------------------- 派生语义
@dataclass(frozen=True, slots=True)
class Effect:
    """`effect(target_ref)` 的结果。SPEC §6.1。"""

    conclusion: str                     # unknown_target / target_gone /
                                        # target_changed / target_unchanged
    changes: tuple[str, ...] = ()
    added_count: int = 0
    removed_count: int = 0
    added_overlapping_target: tuple[Element, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "conclusion": self.conclusion,
            "changes": list(self.changes),
            "added_count": self.added_count,
            "removed_count": self.removed_count,
            "added_overlapping_target": [
                {"ref": e.ref, "role": e.role, "label": e.label}
                for e in self.added_overlapping_target
            ],
        }


def effect_of(cs: ChangeSet, target_ref: str) -> Effect:
    """我点了 prev 里的 target_ref，起作用了吗？SPEC §6.1。"""
    base = dict(added_count=len(cs.added), removed_count=len(cs.removed))

    # 1. target 不在 prev
    prev_refs = {e.ref for e in cs.prev_elements}
    if target_ref not in prev_refs:
        return Effect("unknown_target", **base)

    # 2. target 消失
    if any(e.ref == target_ref for e in cs.removed):
        return Effect("target_gone", **base)

    # 3. 找到 matched 对
    pair = next((p for p in cs.matched if p.prev.ref == target_ref), None)
    if pair is None:  # 理论不可达：非 removed 必 matched
        return Effect("unknown_target", **base)

    # 4. 覆盖 target 的新元素（点击后弹出面板的情形）
    covering = tuple(
        e for e in cs.added if _overlap(pair.prev, e) >= 0.5
    )
    kw = {**base, "added_overlapping_target": covering}

    if pair.unchanged:
        return Effect("target_unchanged", changes=(), **kw)
    return Effect("target_changed", changes=pair.changes, **kw)


def is_stuck(history: Sequence[ChangeSet], n: int = 3) -> bool:
    """最近 n 帧是否两两无变化。SPEC §6.2。

    这是 Agent 的止损条件：连续 n 步界面无变化，说明动作没生效。
    """
    if n < 2 or len(history) < n:
        return False
    return all(cs.is_identical for cs in history[-n:])


def is_loading(cur: Any) -> bool:
    """加载态启发式。SPEC §6.3，**应该级**，规范不强制。"""
    els = _elements_of(cur)
    if len(els) > 2:
        return False
    roles = {e.role for e in els}
    if not roles & _LOADING_ROLES:
        return False
    return not (roles & _INTERACTIVE_ROLES)

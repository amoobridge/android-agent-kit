"""跨滚动稳定元素键。

**问题**：`ref` 是文档序下标，页面一跳或一滚就整体平移（提案03 已量化：
跨页导航 100% 重指派）。双闸门让这种失效**报错**而不是静默点错，
但代价是每次滚动后引用全作废，必须重新 dump。

本模块提供第二种寻址方式：**内容派生的稳定键**。

    ref   表达「我看到的那一行」——身份，界面一变即失效
    key   表达「叫 X 的那一类行」——描述，滚动后仍然有效

## 键的构造

    rid:<resource-id>          有 resource-id 且非结构性时优先
    lbl:<class>:<label>        否则用 类名 + 标签
    anon:<class>               两者皆空时退化

基键在同一快照内重复 k 次时，追加 `#<序号>`（0 起，按文档序）消解冲突。

## 已知边界（重要）

序号只在**重复组成员不变**时稳定。若滚动导致重复组多了一行，
组内后续元素的序号会平移——与 ref 同类的问题，只是爆炸半径小得多
（只影响同标签的行，而不是整页）。

本模块不解决这个问题，只把它**测出来**：`collision_report()` 报告
每个快照内的基键重复情况，`stability_report()` 报告滚动序列上
键的实际存活率。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "uidref"))

import uidref  # noqa: E402
from uidref.model import Element, Snapshot, is_structural_id  # noqa: E402


# ---------------------------------------------------------------- 键构造
def base_key(el: Element) -> str:
    """元素的内容派生基键（不含冲突消解序号）。"""
    rid = (el.resource_id or "").strip()
    if rid and not is_structural_id(rid):
        return f"rid:{rid}"
    cls = el.class_name.rsplit(".", 1)[-1] or "View"
    label = (el.label or "").strip()
    if label:
        return f"lbl:{cls}:{label}"
    return f"anon:{cls}"


def key_of(el: Element, base_counts: dict[str, int] | None = None) -> str:
    """元素的完整键。基键重复时追加 `#<序号>`。"""
    b = base_key(el)
    if base_counts is None:
        return b
    n = base_counts.get(b, 1)
    return f"{b}#0" if n == 1 else b


def key_map(snap: Snapshot) -> dict[str, Element]:
    """快照的 ref → key 映射。同一键对应多个元素时，后者覆盖前者。

    ⚠️ 这是**有损**的：键冲突时不报错，静默保留最后一个。
    调用方应配合 `collision_report()` 检查冲突数。
    """
    counts: dict[str, int] = {}
    for el in snap:
        counts[base_key(el)] = counts.get(base_key(el), 0) + 1
    out: dict[str, Element] = {}
    seen: dict[str, int] = {}
    for el in snap:
        b = base_key(el)
        k = seen.get(b, 0)
        seen[b] = k + 1
        out[f"{b}#{k}" if counts[b] > 1 else b] = el
    return out


def resolve_key(snap: Snapshot, key: str) -> Element | None:
    """键 → 元素。找不到返回 None。

    不得 抛异常，也 不得 回退到"最接近的"元素——
    回退会把"找错了"伪装成"找到了"。
    """
    return key_map(snap).get(key)


# ---------------------------------------------------------------- 报告
@dataclass
class Collision:
    base: str
    count: int
    refs: tuple[str, ...]


def collision_report(snap: Snapshot) -> list[Collision]:
    """快照内基键重复情况。count > 1 即需要序号消解。"""
    groups: dict[str, list[str]] = {}
    for el in snap:
        groups.setdefault(base_key(el), []).append(el.ref)
    return sorted(
        (Collision(b, len(r), tuple(r)) for b, r in groups.items() if len(r) > 1),
        key=lambda c: -c.count,
    )


@dataclass
class Stability:
    """一个键在滚动序列上的表现。"""

    key: str
    present: tuple[int, ...]        # 出现在哪些快照上
    labels: tuple[str, ...]         # 各次出现时的标签

    @property
    def survived(self) -> int:
        """连续存活的快照数（从第 0 帧算起）。"""
        n = 0
        for i in self.present:
            if i == n:
                n += 1
            else:
                break
        return n

    @property
    def label_drifted(self) -> bool:
        return len(set(self.labels)) > 1


def stability_report(snaps: list[Snapshot]) -> dict[str, Stability]:
    """跨快照统计每个键的出现情况。"""
    acc: dict[str, Stability] = {}
    for i, s in enumerate(snaps):
        for k, el in key_map(s).items():
            st = acc.get(k)
            if st is None:
                acc[k] = Stability(k, (i,), (el.label,))
            else:
                acc[k] = Stability(k, st.present + (i,), st.labels + (el.label,))
    return acc


def track(snaps: list[Snapshot], key: str) -> list[int | None]:
    """返回该键在各快照上的 ref；不存在则为 None。

    这就是稳定键的用途：跨滚动跟踪同一行，拿到它每一帧的 ref。
    """
    return [key_map(s).get(key).ref if key in key_map(s) else None for s in snaps]


__all__ = [
    "base_key", "key_of", "key_map", "collision_report", "resolve_key",
    "stability_report", "track", "Collision", "Stability", "uidref",
]

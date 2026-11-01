"""跨页跟踪的信任分级。

**要解决的问题**：`screendiff` 的跨页匹配会**静默产生假匹配**。

真实数据（`dumps/`，系统设置主页 vs 通知子页）：

    diff(home1, sub1) → matched 8, added 2, removed 3

8 个匹配**全部标签不同**——「Network & internet」配到「App notifications」、
「Storage」配到「Notifications on lock screen」。而 `matched 8` 这个数字
看起来完全合理，调用方无从知道这 8 个全是垃圾。

这就是 screendiff 边界清单第 1 条（全屏容器与任何元素重叠率都高）
在跨页场景下的表现。**本模块不修 screendiff，而是给它的输出加一层审计。**

## 三条规则

1. **同屏判定用 snapshot_id**，不用匹配。真实数据：home1/home2/home3
   三次进入同一界面，snapshot_id 完全相同。
2. **跨页共有元素用键交集**，不用匹配。真实数据：home ∩ sub = **空集**。
3. **跨页解析只认身份 tier**（非结构性 rid / label+class），
   **绝不认几何 tier**。几何匹配跨页必假。

## 与 screendiff / scrollkey 的分工

| | 回答的问题 | 匹配依据 |
|---|---|---|
| screendiff | 两份快照怎么比对 | 几何 + 身份 |
| scrollkey | 一个元素怎么跨快照指代 | 纯内容 |
| **crosstrack** | **跨页时什么能信** | **只认身份，且把不信的标出来** |
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "uidref"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "screendiff"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scrollkey"))

import uidref  # noqa: E402
from scrollkey import base_key, key_map  # noqa: E402
from uidref.model import Element, Snapshot, is_structural_id  # noqa: E402


# ---------------------------------------------------------------- 同屏判定
def same_screen(a: Snapshot, b: Snapshot) -> bool:
    """两次观察是否是**同一界面同一内容**。

    依据 snapshot_id（内容哈希）。真实数据：home1/home2/home3 三次进入
    同一设置主页，id 完全相同；sub1/sub2 两次进入通知子页，id 也相同。

    ⚠️ **反向不成立**：id 不同**不代表**是不同的界面。
    滚动会改变内容，从而改变 id（scrollkey 已量化：83% 共有行换 ref）。
    所以 `same_screen() == False` 只能说"内容变了"，不能说"换页了"。
    """
    return a.snapshot_id == b.snapshot_id


# ---------------------------------------------------------------- 跨页共有
def shared_keys(a: Snapshot, b: Snapshot) -> set[str]:
    """两份快照按**内容身份**共有的键。

    这才是"两个界面真正共有的元素"——不掺任何几何推断。
    """
    return set(key_map(a)) & set(key_map(b))


# ---------------------------------------------------------------- 信任分级
TIER_RID = "rid"              # 非结构性 resource-id 相同：最强
TIER_LABEL_CLASS = "label_class"   # 类名 + 标签相同：强
TIER_ANON = "anon_class"      # 仅类名相同：弱，跨页不可信
TIER_NONE = "none"            # 无身份依据：只可能来自几何匹配

_CROSS_PAGE_TRUSTED = {TIER_RID, TIER_LABEL_CLASS}


def identity_tier(prev_el: Element, cur_el: Element) -> str:
    """两个元素之间的身份依据强度。"""
    rp = (prev_el.resource_id or "").strip()
    rc = (cur_el.resource_id or "").strip()
    if rp and rp == rc and not is_structural_id(rp):
        return TIER_RID
    if (prev_el.label or "").strip() and prev_el.label == cur_el.label \
            and prev_el.class_name == cur_el.class_name:
        return TIER_LABEL_CLASS
    if prev_el.class_name == cur_el.class_name:
        return TIER_ANON
    return TIER_NONE


@dataclass
class CrossMatch:
    """跨页解析一个引用的结果。"""

    requested_ref: str
    found: bool
    tier: str
    ambiguous: bool
    element: Element | None = None
    candidates: tuple[str, ...] = ()

    @property
    def trusted(self) -> bool:
        """跨页场景下这个解析能不能信。

        只有 rid / label+class 两级可信。anon 和 none 一律不可信——
        两个匿名 ScrollView 说明不了任何事。
        """
        return self.found and self.tier in _CROSS_PAGE_TRUSTED and not self.ambiguous


def resolve_across(prev: Snapshot, cur: Snapshot, ref: str) -> CrossMatch:
    """在 cur 上解析 prev 里的 ref，**只认身份 tier**。

    找不到就返回 `found=False`，**不得**回退到"位置最接近的"元素——
    那正是 screendiff 跨页静默假匹配的成因。
    """
    src = {e.ref: e for e in prev}.get(ref)
    if src is None:
        return CrossMatch(ref, False, TIER_NONE, False)

    k = base_key(src)
    km = key_map(cur)
    hits = [(kk, e) for kk, e in km.items() if base_key(e) == k]
    if not hits:
        return CrossMatch(ref, False, TIER_NONE, False)

    ambiguous = len(hits) > 1
    el = hits[0][1]
    return CrossMatch(ref, True, identity_tier(src, el), ambiguous, el,
                      tuple(e.ref for _, e in hits))


# ---------------------------------------------------------------- 审计
@dataclass
class AuditedDiff:
    """给 screendiff 的 diff 输出加一层身份审计。"""

    verdict: str                                  # same_screen / different_screen
    justified: tuple = ()                         # 身份站得住的匹配
    geometric_only: tuple = ()                    # 只靠几何匹配上的
    shared_keys: frozenset = frozenset()

    @property
    def false_match_rate(self) -> float:
        tot = len(self.justified) + len(self.geometric_only)
        return len(self.geometric_only) / tot if tot else 0.0

    def summary(self) -> str:
        return (f"{self.verdict}: justified={len(self.justified)} "
                f"geometric_only={len(self.geometric_only)} "
                f"false_match_rate={self.false_match_rate:.0%} "
                f"shared_keys={len(self.shared_keys)}")


def audit_diff(prev: Snapshot, cur: Snapshot) -> AuditedDiff:
    """审计 screendiff 的匹配：哪些有身份依据，哪些只靠几何。

    **这是本模块的核心价值**：它把 screendiff 跨页的静默假匹配
    变成显式的 `geometric_only` 列表。

    注意 `TIER_ANON` 归入 geometric_only——两个同 class 的匿名元素
    在跨页场景下不构成身份依据（见 SPEC 边界④）。
    """
    from screendiff import diff as sd_diff

    cs = sd_diff(prev, cur)
    ok, bad = [], []
    for p in cs.matched:
        (ok if identity_tier(p.prev, p.cur) in _CROSS_PAGE_TRUSTED else bad).append(p)
    return AuditedDiff(
        verdict="same_screen" if same_screen(prev, cur) else "different_screen",
        justified=tuple(ok), geometric_only=tuple(bad),
        shared_keys=frozenset(shared_keys(prev, cur)),
    )


__all__ = [
    "same_screen", "shared_keys", "identity_tier", "resolve_across",
    "audit_diff", "CrossMatch", "AuditedDiff",
    "TIER_RID", "TIER_LABEL_CLASS", "TIER_ANON", "TIER_NONE",
    "uidref",
]

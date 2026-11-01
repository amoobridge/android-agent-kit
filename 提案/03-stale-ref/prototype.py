"""stale-ref 双闸门原型。

**这是原型，不是 uidref 的修改。** 按"已有产出不动"的约束，
提案的 API 变更在这里以可运行的形式给出，供审计后合入 uidref。

核心一句话：把失效判据从「下标是否越界」升级为「快照是否仍是那一份」。

    snap.resolve("e5")                    # 旧：只看下标
    snap.resolve("e5", since=snap_id)     # 新：还要看快照身份

因为 snapshot_id 是内容哈希，「界面没变」与「引用仍有效」因此等价。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "uidref"))

import uidref  # noqa: E402
from uidref.model import Element, Snapshot  # noqa: E402


class StaleRefError(Exception):
    """引用失效。

    ``reason`` 让调用方能区分两种失效，从而决定下一步：

    ====================  ==========================================
    ``ref_gone``          下标越界 —— 重新搜索或重新 dump
    ``snapshot_mismatch`` 快照已变 —— **必须**重新 dump 再决策
    ====================  ==========================================

    第二种是原来漏掉的：下标合法，但指向了别的内容。
    """

    def __init__(self, ref: str, reason: str, detail: str = ""):
        self.ref = ref
        self.reason = reason
        self.detail = detail
        super().__init__(f"ref {ref!r} 失效（{reason}）{detail}".rstrip())


def resolve(snap: Snapshot, ref: str, since: str | None = None) -> Element:
    """双闸门解析。

    闸门一 ``ref_gone``        下标不在快照内
    闸门二 ``snapshot_mismatch``  ``since`` 与当前快照 id 不一致

    ``since`` 为 ``None`` 时只过闸门一 —— 这是**旧行为**，
    保留它只为兼容；新代码一律传 ``since``。
    """
    # 闸门二先判：快照都变了，下标合不合法已经无所谓
    if since is not None and since != snap.snapshot_id:
        raise StaleRefError(
            ref, "snapshot_mismatch",
            f"：引用来自 {since}，当前快照是 {snap.snapshot_id}")

    el = snap.get(ref)
    if el is None:
        raise StaleRefError(ref, "ref_gone", f"：当前快照只有 {len(snap)} 个元素")
    return el


def reassigned_refs(prev: Snapshot, cur: Snapshot) -> list[tuple[str, str, str]]:
    """列出两边都存在、但内容已不同的 ref。

    这就是原实现漏掉的那一类失效。返回 ``(ref, 旧标签, 新标签)``。
    """
    out = []
    for e in prev:
        other = cur.get(e.ref)
        if other is not None and other.label != e.label:
            out.append((e.ref, e.label, other.label))
    return out


__all__ = ["StaleRefError", "resolve", "reassigned_refs", "uidref"]

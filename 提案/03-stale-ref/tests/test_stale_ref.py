"""stale-ref 双闸门的验证。

全部基于 ``screendiff/dumps/`` 的**真实 dump**，不构造数据。
12 条，分四组：

**TestReassignmentIsCaught**   重指派必须被拒（原实现漏掉的那类）
**TestNoFalseRejection**       没变就不能误拒（否则没人会用）
**TestReasonIsDistinguishable** 两种失效必须可区分
**TestRealDeviceEvidence**     用真实迁移量化覆盖面
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "uidref"))
sys.path.insert(0, str(HERE))

import uidref  # noqa: E402
from prototype import StaleRefError, reassigned_refs, resolve  # noqa: E402

DUMPS = ROOT / "screendiff" / "dumps"


def _load(name: str) -> uidref.Snapshot:
    return uidref.parse_file(DUMPS / f"{name}.xml")


# ==================================================== 重指派必须被拒
class TestReassignmentIsCaught:
    def test_cross_screen_reassignment_rejected(self):
        """跨页导航：c1 的 e5 在 c2 上指向完全不同的行。"""
        prev, cur = _load("c1"), _load("c2")
        with pytest.raises(StaleRefError) as ei:
            resolve(cur, "e5", since=prev.snapshot_id)
        assert ei.value.reason == "snapshot_mismatch"

    def test_same_screen_label_change_rejected(self):
        """同页内标签变化也算失效——界面看起来"还是那一页"。"""
        prev, cur = _load("c2"), _load("c3")
        assert any(r == "e3" for r, _, _ in reassigned_refs(prev, cur))
        with pytest.raises(StaleRefError) as ei:
            resolve(cur, "e3", since=prev.snapshot_id)
        assert ei.value.reason == "snapshot_mismatch"

    def test_old_behaviour_would_have_succeeded(self):
        """★ 证明这是真缺口：旧行为（不传 since）在同样的输入下**不报错**。

        这条测试是提案存在的理由。若它失败，说明 uidref 已经修好了。
        """
        prev, cur = _load("c1"), _load("c2")
        el = cur.get("e5")                    # 旧实现走的路径
        assert el is not None, "下标合法，所以旧实现会静默放行"
        assert el.label != prev.get("e5").label, "且它指向了别的内容"

    def test_pure_scroll_also_rejected(self):
        """纯滚动零重指派，但快照 id 仍不同 → 仍拒绝。

        安全性优先：宁可多 dump 一次，也不冒点错的风险。
        """
        prev, cur = _load("c3"), _load("d1")
        assert reassigned_refs(prev, cur) == [], "纯滚动本就不重指派"
        with pytest.raises(StaleRefError) as ei:
            resolve(cur, "e5", since=prev.snapshot_id)
        assert ei.value.reason == "snapshot_mismatch"


# ==================================================== 不能误拒
class TestNoFalseRejection:
    def test_same_snapshot_resolves(self):
        s = _load("c2")
        assert resolve(s, "e5", since=s.snapshot_id).ref == "e5"

    def test_identical_content_keeps_id(self):
        """同一份 XML 解析两次 → id 相同 → 引用继续有效。

        这是双闸门不会造成误拒的根本原因：snapshot_id 是内容哈希。
        """
        a = uidref.parse_xml((DUMPS / "c2.xml").read_text(encoding="utf-8"))
        b = uidref.parse_xml((DUMPS / "c2.xml").read_text(encoding="utf-8"))
        assert a.snapshot_id == b.snapshot_id
        assert resolve(b, "e5", since=a.snapshot_id).ref == "e5"

    def test_since_none_keeps_legacy_behaviour(self):
        """不传 since 只过闸门一 —— 兼容旧调用，但不推荐。"""
        s = _load("c1")
        assert resolve(s, "e5").ref == "e5"


# ==================================================== 两种失效可区分
class TestReasonIsDistinguishable:
    def test_ref_gone(self):
        s = _load("c2")
        with pytest.raises(StaleRefError) as ei:
            resolve(s, "e999", since=s.snapshot_id)
        assert ei.value.reason == "ref_gone"

    def test_snapshot_mismatch_takes_precedence(self):
        """快照已变时，即使下标合法也报 mismatch——先判身份再判存在。"""
        prev, cur = _load("c2"), _load("c1")
        with pytest.raises(StaleRefError) as ei:
            resolve(cur, "e999", since=prev.snapshot_id)
        assert ei.value.reason == "snapshot_mismatch"

    def test_reasons_differ(self):
        s = _load("c2")
        r1 = r2 = None
        try:
            resolve(s, "e999", since=s.snapshot_id)
        except StaleRefError as e:
            r1 = e.reason
        try:
            resolve(s, "e5", since="s000000000000")
        except StaleRefError as e:
            r2 = e.reason
        assert r1 == "ref_gone" and r2 == "snapshot_mismatch"
        assert r1 != r2, "调用方要靠 reason 决定下一步，必须可区分"


# ==================================================== 真机证据量化
class TestRealDeviceEvidence:
    """把提案 §4 的那张表变成可执行断言。"""

    # 数字是**全部 11 个元素**的重指派数，不是抽样。
    # 第一版只数了 e1..e6，得出"6/6"——低估了近一半。
    MIGRATIONS = [
        ("c1", "c2", 11),  # 跨页导航：11/11，100%
        ("c1", "c3", 11),  # 跨页导航：11/11
        ("c1", "d1", 11),  # 跨页导航：11/11
        ("c2", "c3", 1),   # 同页标签变化：1/11
        ("c2", "d1", 1),   # 同页标签变化：1/11
        ("c3", "d1", 0),   # 纯滚动：0/11 但 id 仍变
    ]

    @pytest.mark.parametrize("a,b,n", MIGRATIONS)
    def test_reassignment_count(self, a, b, n):
        prev, cur = _load(a), _load(b)
        assert len(reassigned_refs(prev, cur)) == n

    def test_all_migrations_change_snapshot_id(self):
        for a, b, _ in self.MIGRATIONS:
            assert _load(a).snapshot_id != _load(b).snapshot_id, \
                f"{a}→{b} 快照 id 未变，则双闸门无从判断"

    def test_cross_screen_reassigns_everything(self):
        """★ 跨页导航是 **100%** 重指派，不是"大部分"。

        三组跨页迁移（c1→c2 / c1→c3 / c1→d1）全是 11/11。
        也就是说页面一跳，上一页的每一个 ref 都指向了别的内容。
        这不是边缘情况，是导航后的常态。
        """
        for dst in ("c2", "c3", "d1"):
            prev, cur = _load("c1"), _load(dst)
            n = len(reassigned_refs(prev, cur))
            assert n == len(prev), f"c1→{dst} 只有 {n}/{len(prev)} 被重指派"

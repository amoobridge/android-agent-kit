"""crosstrack 的验证。

核心证据来自 `dumps/` 里 5 份真实 dump：系统设置主页三次进入
（home1/home2/home3）+ 通知子页两次进入（sub1/sub2）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "uidref"))
sys.path.insert(0, str(ROOT / "screendiff"))
sys.path.insert(0, str(ROOT / "scrollkey"))
sys.path.insert(0, str(HERE.parent))

import uidref  # noqa: E402
from crosstrack import (audit_diff, identity_tier, resolve_across,  # noqa: E402
                        same_screen, shared_keys, TIER_ANON, TIER_LABEL_CLASS,
                        TIER_NONE, TIER_RID)
from scrollkey import base_key  # noqa: E402
from uidref.model import Bounds, Element  # noqa: E402

DUMPS = HERE.parent / "dumps"
H = uidref.parse_file(DUMPS / "home1.xml")
H2 = uidref.parse_file(DUMPS / "home2.xml")
H3 = uidref.parse_file(DUMPS / "home3.xml")
S1 = uidref.parse_file(DUMPS / "sub1.xml")
S2 = uidref.parse_file(DUMPS / "sub2.xml")


def _el(ref="e1", cls="android.widget.LinearLayout", label="", rid="",
        bounds=(0, 0, 100, 100)) -> Element:
    return Element(ref=ref, role="item", label=label, bounds=Bounds(*bounds),
                   clickable=True, long_clickable=False, scrollable=False,
                   editable=False, checked=False, disabled=False, password=False,
                   depth=1, class_name=cls, resource_id=rid)


# ================================================================ 同屏判定
class TestSameScreen:
    def test_same_screen_three_times(self):
        """★ 三次进入同一设置主页，snapshot_id 完全相同。"""
        assert same_screen(H, H2) and same_screen(H2, H3)

    def test_same_screen_subpage_twice(self):
        assert same_screen(S1, S2)

    def test_different_screen(self):
        assert not same_screen(H, S1)

    def test_id_inequality_does_not_imply_page_change(self):
        """★ 反向不成立：滚动会改 id，但那是同一页。

        这条把"snapshot_id 不等于 ≠ 换页"钉住，防止被误用成换页判据。
        """
        a = _el(label="A")
        b = _el(label="B")
        assert not same_screen(_snap([a]), _snap([b])), "内容不同 id 不同"
        assert not same_screen(_snap([a]), _snap([a, b])), "滚动后 id 也不同"
        # 但这两组都是"同一页"——所以 id 不等不能推出换页


# ================================================================ 跨页共有
class TestSharedKeys:
    def test_no_shared_keys_across_pages(self):
        """★ 跨页键交集为空——这才是"两个界面真正共有的元素"。"""
        assert shared_keys(H, S1) == set()

    def test_shared_keys_same_screen(self):
        assert len(shared_keys(S1, S2)) == 10

    def test_shared_keys_is_identity_only(self):
        """键交集不得掺几何位置。"""
        a = _el(ref="e1", label="X", bounds=(0, 0, 100, 100))
        b = _el(ref="e9", label="X", bounds=(0, 900, 100, 1000))
        assert base_key(a) == base_key(b), "位置不同不影响键"
        assert shared_keys(_snap([a]), _snap([b])) == {base_key(a)}


# ================================================================ 信任分级
class TestIdentityTier:
    def test_rid_tier(self):
        a = _el(rid="com.android.settings:id/recycler_view")
        b = _el(ref="e9", rid="com.android.settings:id/recycler_view")
        assert identity_tier(a, b) == TIER_RID

    def test_structural_rid_is_not_a_tier(self):
        a = _el(rid="content_parent")
        b = _el(ref="e9", rid="content_parent")
        assert identity_tier(a, b) == TIER_ANON, "结构性 id 不构成身份依据"

    def test_label_class_tier(self):
        a = _el(label="Battery · Charged")
        b = _el(ref="e9", label="Battery · Charged")
        assert identity_tier(a, b) == TIER_LABEL_CLASS

    def test_label_must_match_for_label_tier(self):
        """标签不同就**不配**拿 label_class 级。

        注意此时 tier 是 anon_class（类名仍相同），不是 none——
        级差是逐级降的：rid > label+class > class > 无。
        关键是它**不可信**，不是它等于 none。
        """
        a = _el(label="Battery · Charged")
        b = _el(ref="e9", label="Storage · 51% used")
        assert identity_tier(a, b) == TIER_ANON
        assert identity_tier(a, b) != TIER_LABEL_CLASS
        m = resolve_across(_snap([a]), _snap([b]), "e1")
        assert m.trusted is False

    def test_class_must_match(self):
        a = _el(cls="android.widget.Button", label="X")
        b = _el(ref="e9", cls="android.widget.ImageButton", label="X")
        assert identity_tier(a, b) == TIER_NONE

    def test_anon_tier(self):
        a = _el()
        b = _el(ref="e9")
        assert identity_tier(a, b) == TIER_ANON

    def test_anon_is_not_cross_page_trusted(self):
        """★ 边界④：两个同 class 匿名元素跨页不可信。"""
        m = resolve_across(_snap([_el()]), _snap([_el(ref="e7")]), "e1")
        assert m.found and m.tier == TIER_ANON and m.trusted is False


# ================================================================ 审计
class TestAuditDiff:
    def test_cross_page_all_matches_are_false(self):
        """★★ 本模块的核心证据。

        screendiff 对 主页 vs 通知子页 报 `matched 8`，
        而这 8 个**全部**只靠几何匹配上、标签全不同。
        没有审计的话，`matched 8` 看起来完全合理。
        """
        a = audit_diff(H, S1)
        assert a.verdict == "different_screen"
        assert len(a.geometric_only) == 8
        assert len(a.justified) == 0
        assert a.false_match_rate == 1.0

    def test_cross_page_false_matches_have_different_labels(self):
        a = audit_diff(H, S1)
        for p in a.geometric_only:
            assert p.prev.label != p.cur.label, \
                f"{p.prev.ref}→{p.cur.ref} 标签相同却被判假匹配"

    def test_same_screen_mostly_justified(self):
        a = audit_diff(S1, S2)
        assert a.verdict == "same_screen"
        assert len(a.justified) == 9
        assert a.false_match_rate < 0.2

    def test_the_one_geometric_only_is_anonymous(self):
        """同页那 1 个 geometric_only 是匿名 ScrollView 对——保守判假，可接受。"""
        a = audit_diff(S1, S2)
        assert len(a.geometric_only) == 1
        p = a.geometric_only[0]
        assert identity_tier(p.prev, p.cur) == TIER_ANON

    def test_audit_does_not_modify_screendiff(self):
        """增量原则：审计是叠加层，不改 screendiff 的输出。"""
        from screendiff import diff as sd_diff
        raw = sd_diff(H, S1)
        assert len(raw.matched) == 8, "screendiff 原始输出不变"
        assert len(audit_diff(H, S1).geometric_only) == 8


# ================================================================ 跨页解析
class TestResolveAcross:
    def test_cross_page_row_is_gone(self):
        """★ 主页的「Network & internet」在子页上不存在 → found=False。

        不得回退到"位置最接近的"——那正是静默假匹配的成因。
        """
        m = resolve_across(H, S1, "e5")
        assert m.found is False and m.tier == TIER_NONE and m.trusted is False

    def test_same_screen_row_resolves(self):
        m = resolve_across(S1, S2, "e3")
        assert m.found and m.tier == TIER_RID and m.trusted is True
        assert m.element.ref == "e3"

    def test_missing_ref_in_prev(self):
        m = resolve_across(H, S1, "e999")
        assert m.found is False

    def test_ambiguous_is_not_trusted(self):
        """同名多行时必须报 ambiguous，且不得自动选一个。"""
        prev = _snap([_el(ref="e1", label="Off")])
        cur = _snap([_el(ref="e1", label="Off"), _el(ref="e2", label="Off")])
        m = resolve_across(prev, cur, "e1")
        assert m.found and m.ambiguous and m.trusted is False
        assert len(m.candidates) == 2

    def test_no_geometric_fallback(self):
        """★ 位置接近但内容不同 → 必须找不到，不许猜。"""
        prev = _snap([_el(ref="e1", label="Alpha", bounds=(0, 0, 1080, 200))])
        cur = _snap([_el(ref="e1", label="Beta", bounds=(0, 0, 1080, 200))])
        m = resolve_across(prev, cur, "e1")
        assert m.found is False, "标签不同就不许跨页解析"


def _snap(els):
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<hierarchy rotation="0">']
    for i, e in enumerate(els):
        parts.append(
            f'<node index="{i}" text="{e.label}" resource-id="{e.resource_id}" '
            f'class="{e.class_name}" package="com.android.settings" '
            f'content-desc="" checkable="false" checked="false" clickable="true" '
            f'enabled="true" focusable="false" focused="false" scrollable="false" '
            f'long-clickable="false" password="false" selected="false" '
            f'bounds="[{e.bounds.x1},{e.bounds.y1}][{e.bounds.x2},{e.bounds.y2}]">'
            f'</node>')
    parts.append("</hierarchy>")
    return uidref.parse_xml("".join(parts))

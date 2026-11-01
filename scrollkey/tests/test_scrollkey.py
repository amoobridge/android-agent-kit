"""scrollkey 的验证。

分四组：

**TestBaseKey**              基键构造规则（含结构性 id 排除）
**TestCollisionDisambiguation** 冲突消解序号（合成向量——真实数据里没有冲突）
**TestRealData**             真实滚动序列的稳定性与 ref_churn 对照
**TestBoundaries**           把 SPEC §4 的已知边界钉成断言
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "uidref"))
sys.path.insert(0, str(HERE.parent))

import uidref  # noqa: E402
from uidref.model import Element  # noqa: E402
from scrollkey import (base_key, collision_report, key_map,  # noqa: E402
                       resolve_key, stability_report, track)

DUMPS = HERE.parent / "dumps"
UIDREF_DUMPS = ROOT / "uidref" / "dumps"


def _el(ref="e1", cls="android.widget.LinearLayout", label="",
        rid="", bounds=(0, 0, 100, 100)) -> Element:
    """按 uidref.model.Element 的真实字段构造。"""
    from uidref.model import Bounds
    return Element(
        ref=ref, role="item", label=label, bounds=Bounds(*bounds),
        clickable=True, long_clickable=False, scrollable=False,
        editable=False, checked=False, disabled=False, password=False,
        depth=1, class_name=cls, resource_id=rid,
    )


# ================================================================ 基键
class TestBaseKey:
    def test_rid_priority(self):
        assert base_key(_el(rid="com.android.settings:id/search_action_bar")) \
            == "rid:com.android.settings:id/search_action_bar"

    def test_structural_id_excluded(self):
        """结构性 id 不得作为基键——它无语义且常被多个元素共用。

        两种情况分别断言：有标签时退到 lbl，无标签时退到 anon。
        都不许出现 ``rid:content_parent``。
        """
        assert base_key(_el(rid="content_parent")) == "anon:LinearLayout"
        assert base_key(_el(rid="id/content")) == "anon:LinearLayout"
        assert base_key(_el(rid="content_parent", label="Battery")) \
            == "lbl:LinearLayout:Battery"
        assert "rid:content_parent" not in base_key(_el(rid="content_parent"))

    def test_label_form(self):
        assert base_key(_el(label="Battery · Charged")) \
            == "lbl:LinearLayout:Battery · Charged"

    def test_anon_when_both_empty(self):
        assert base_key(_el()) == "anon:LinearLayout"

    def test_class_short(self):
        assert base_key(_el(cls="android.view.ViewGroup", label="x")) \
            == "lbl:ViewGroup:x"

    def test_class_short_when_no_dot(self):
        assert base_key(_el(cls="View", label="x")) == "lbl:View:x"


# ================================================================ 冲突消解
class TestCollisionDisambiguation:
    """真实数据里 0 冲突，所以这组是**合成向量**。

    但消解逻辑恰恰是最容易写错的部分，必须有判据。
    """

    def _snap(self, labels):
        import uidref as u
        parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<hierarchy rotation="0">']
        for i, lb in enumerate(labels):
            parts.append(
                # 标签放 text 属性——uidref 从 text/content-desc 取，
                # **不读元素体文本**。放错地方会得到一片 anon 键。
                f'<node index="{i}" text="{lb}" resource-id="" '
                f'class="android.widget.LinearLayout" '
                f'package="com.android.settings" content-desc="" '
                f'checkable="false" checked="false" clickable="true" '
                f'enabled="true" focusable="false" focused="false" '
                f'scrollable="false" long-clickable="false" '
                f'password="false" selected="false" '
                f'bounds="[0,{i*100}][1080,{i*100+80}]"></node>')
        parts.append("</hierarchy>")
        return u.parse_xml("".join(parts))

    def test_no_suffix_when_unique(self):
        s = self._snap(["A", "B"])
        assert set(key_map(s)) == {"lbl:LinearLayout:A", "lbl:LinearLayout:B"}

    def test_suffix_zero_based_document_order(self):
        s = self._snap(["Off", "Off", "Off"])
        ks = list(key_map(s))
        assert ks == ["lbl:LinearLayout:Off#0",
                      "lbl:LinearLayout:Off#1",
                      "lbl:LinearLayout:Off#2"]

    def test_resolve_key_returns_right_element(self):
        s = self._snap(["Off", "Off"])
        km = key_map(s)
        assert km["lbl:LinearLayout:Off#0"].ref == "e1"
        assert km["lbl:LinearLayout:Off#1"].ref == "e2"

    def test_resolve_missing_returns_none(self):
        s = self._snap(["A"])
        assert resolve_key(s, "lbl:LinearLayout:Z") is None

    def test_ordinal_shifts_when_group_grows_in_front(self):
        """★ 已知边界 4.1：组前插入一行，后续序号整体平移。"""
        before = self._snap(["Off", "Off"])
        after = self._snap(["Off", "Off", "Off"])
        assert resolve_key(after, "lbl:LinearLayout:Off#1").ref == "e2", \
            "此时 #1 仍是原来的 #1"
        before3 = self._snap(["X", "Off", "Off"])
        assert resolve_key(before3, "lbl:LinearLayout:Off#0").ref == "e2", \
            "组前插入后，#0 指向了新的第一行——原 #0 变成 #1"

    def test_collision_report_counts(self):
        s = self._snap(["Off", "Off", "A"])
        c = collision_report(s)
        assert len(c) == 1 and c[0].count == 2 and c[0].refs == ("e1", "e2")


# ================================================================ 真实数据
class TestRealData:
    """滚动序列 + uidref 的 16 个真实界面。"""

    SNAPS = [uidref.parse_file(DUMPS / f"s{i}.xml") for i in range(5)]

    def test_zero_collisions_on_real_data(self):
        """★ 16 个真实界面 + 5 帧滚动序列，132+ 元素，0 冲突。

        但**不得**据此声称"安卓 UI 无冲突"——样本恰好标签唯一。
        """
        n = 0
        for s in self.SNAPS:
            assert collision_report(s) == []
            n += len(s)
        for p in sorted(UIDREF_DUMPS.glob("*.xml")):
            assert collision_report(uidref.parse_file(p)) == []
            n += len(uidref.parse_file(p))
        assert n > 130, f"样本量 {n} 过小，此断言无意义"

    def test_key_survives_scroll_while_ref_churns(self):
        """★ 核心价值：键跨滚动存活，而 ref 每帧都变。"""
        target = "lbl:LinearLayout:Sound & vibration · Volume, haptics, Do Not Disturb"
        refs = track(self.SNAPS, target)
        assert refs[:4] == ["e11", "e9", "e6", "e4"], "ref 每帧都在变"
        assert len(set(refs[:4])) == 4, "四次观察四个不同 ref"
        # 键始终是同一个字符串
        assert target in key_map(self.SNAPS[0])
        assert target in key_map(self.SNAPS[3])

    def test_rid_key_survives_all_frames(self):
        k = "rid:com.android.settings:id/search_action_bar"
        refs = track(self.SNAPS, k)
        assert refs == ["e3", "e1", "e1", "e1", "e1"]

    def test_stability_report_survived(self):
        rep = stability_report(self.SNAPS)
        k = "rid:com.android.settings:id/main_content_scrollable_container"
        assert rep[k].survived == 5
        assert rep[k].label_drifted is False

    def test_ref_churn_is_high(self):
        """对照组：没有键的话，每次滚动要重新推断多少行。"""
        churn = 0
        for i in range(4):
            a, b = self.SNAPS[i], self.SNAPS[i + 1]
            shared = {e.label for e in a} & {e.label for e in b}
            ra = {e.label: e.ref for e in a}
            rb = {e.label: e.ref for e in b}
            churn += sum(1 for lb in shared if ra[lb] != rb[lb])
        assert churn >= 20, f"ref_churn={churn}，滚动序列上换手极其频繁"

    def test_key_does_not_save_redump(self):
        """★ 边界 4.3：键不能省掉重新观察。

        这条测试把"键的边界"钉住，防止以后被宣传成不用重新 dump。
        """
        s = self.SNAPS[3]
        k = "lbl:LinearLayout:Sound & vibration · Volume, haptics, Do Not Disturb"
        el = resolve_key(s, k)
        assert el is not None and el.ref == "e4"
        # 要拿到 bounds 仍然需要当前快照
        assert el.bounds.cy > 0


# ================================================================ 边界
class TestBoundaries:
    def test_label_drift_changes_key(self):
        """★ 边界 4.2：标签变了就是键变了——显式化，不隐藏。"""
        a = _el(ref="e1", label="Airplane mode · Off")
        b = _el(ref="e1", label="Airplane mode · On")
        assert base_key(a) != base_key(b), "标签变化必须显式反映为键变化"

    def test_anon_key_is_weak(self):
        """★ 边界 4.4：匿名元素的键只多一层 class 过滤。"""
        els = [_el(ref=f"e{i}", label="") for i in range(1, 5)]
        bases = {base_key(e) for e in els}
        assert bases == {"anon:LinearLayout"}, "四个匿名元素同一个基键"
        assert len(key_map(_snap_from(els))) == 4, "靠序号才区分得开"

    def test_no_geometric_matching(self):
        """键匹配必须是纯内容的，不得掺几何位置。

        掺了位置就继承了 screendiff 已记录的全屏容器误配问题。
        """
        a = _el(ref="e1", label="X", bounds=(0, 0, 100, 100))
        b = _el(ref="e9", label="X", bounds=(0, 900, 100, 1000))
        assert base_key(a) == base_key(b), "位置不同不影响键"


def _snap_from(els):
    import uidref as u
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<hierarchy rotation="0">']
    for i, e in enumerate(els):
        parts.append(
            f'<node index="{i}" text="" resource-id="" class="{e.class_name}" '
            f'package="com.android.settings" content-desc="" checkable="false" '
            f'checked="false" clickable="true" enabled="true" focusable="false" '
            f'focused="false" scrollable="false" long-clickable="false" '
            f'password="false" selected="false" '
            f'bounds="[0,{i*100}][1080,{i*100+80}]"></node>')
    parts.append("</hierarchy>")
    return u.parse_xml("".join(parts))

"""imespec 测试：黄金向量 + 元测试 + 真机证据复算。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from core import (Rect, audit_from_files, audit_xml, ime_from_windows,
                  ime_rect, occlusion, parse_bounds, parse_rect_flat,
                  reachability)
from vectors import (BOUNDS, OCCLUSION, UNKNOWN, WINDOWS, iter_cases)
from vectors_lib import xml_root_from


# --------------------------------------------------------------------- #
# 黄金向量
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("case", list(iter_cases()), ids=lambda c: c["id"])
def test_golden_vector(case):
    if "s" in case:                                    # bounds 解析
        parser = (parse_rect_flat if case.get("parser") == "flat"
                  else parse_bounds)
        got = parser(case["s"])
        want = Rect(*case["expect"]) if case["expect"] else None
        assert got == want, f"{case['id']}: {got} != {want}"

    elif "el" in case:                                 # 遮挡判定
        r = occlusion(case["el"], IME_RECT)
        assert abs(r - case["expect_ratio"]) < 1e-9, \
            f"{case['id']}: ratio {r} != {case['expect_ratio']}"
        assert reachability(case["el"], IME_RECT) == case["expect_reach"]

    elif "windows" in case:                            # IME 识别
        w = ime_from_windows(case["windows"])
        if case["expect_ime"] is None:
            assert w is None, case["id"]
        else:
            assert ime_rect(w) == Rect(*case["expect_ime"]), case["id"]

    elif "nodes" in case:                              # unknown
        root = xml_root_from(case["nodes"])
        got = audit_xml(root, None)
        assert got["ime_known"] == case["expect_ime_known"]
        if case.get("expect_all_unknown"):
            for it in got["items"]:
                assert it["reachability"] == "unknown", case["id"]
                assert it["occlusion_ratio"] is None, case["id"]
        if "expect_count" in case:
            assert got["clickable_count"] == case["expect_count"]


IME_RECT = Rect(0, 1517, 1080, 2400)


# --------------------------------------------------------------------- #
# 元测试：用例不能空转
# --------------------------------------------------------------------- #

class TestNotVacuous:
    """A 级：输入变异必须改变输出（抓死用例）
    B 级：定向变异必须复原输出（抓"测的是别的东西"）
    """

    def test_a_bounds_parser_varies(self):
        assert parse_bounds("[0,0][10,10]") != parse_bounds("[0,0][10,11]")
        assert parse_bounds("[0,0][10,10]") != parse_bounds("")

    def test_b_occlusion_flips_on_overlap(self):
        """定向变异：元素从键盘上方移到键盘内，结论必须翻转。"""
        above = Rect(0, 1000, 1080, 1517)
        inside = Rect(0, 1600, 1080, 1800)
        assert reachability(above, IME_RECT) == "reachable"
        assert reachability(inside, IME_RECT) == "occluded"

    def test_b_ime_presence_flips_known(self):
        """定向变异：有/无 IME 窗口信息，ime_known 必须翻转。"""
        root = xml_root_from([{"text": "x", "clickable": "true",
                               "bounds": "[0,1600][1080,1800]"}])
        assert audit_xml(root, IME_RECT)["ime_known"] is True
        assert audit_xml(root, None)["ime_known"] is False

    def test_b_type_two_required(self):
        """反向：只有 type==1 的窗口不得被当成 IME（C2）。"""
        wins = [{"type": 1, "title": "English (US) (QWERTY)",
                 "bounds_in_screen": "0 1517 1080 2400"}]
        assert ime_from_windows(wins) is None, "按标题匹配了，违反 C2"

    def test_b_title_change_keeps_ime(self):
        """反向：标题变了但 type 仍是 2，必须仍识别为 IME。"""
        a = ime_from_windows([{"type": 2, "title": "A",
                               "bounds_in_screen": "0 1517 1080 2400"}])
        b = ime_from_windows([{"type": 2, "title": "B",
                               "bounds_in_screen": "0 1517 1080 2400"}])
        assert a is not None and b is not None

    def test_c_audit_keys_present(self):
        r = audit_xml(xml_root_from([]), None)
        for k in ("ime_known", "clickable_count", "occluded_count",
                  "partially_occluded_count", "unreachable_count",
                  "unreachable_ratio", "items"):
            assert k in r, f"audit 缺字段 {k}"

    def test_c_item_keys_present(self):
        root = xml_root_from([{"text": "x", "clickable": "true",
                               "bounds": "[0,0][10,10]"}])
        it = audit_xml(root, IME_RECT)["items"][0]
        for k in ("text", "bounds", "clickable", "occlusion_ratio",
                  "reachability"):
            assert k in it, f"item 缺字段 {k}"


# --------------------------------------------------------------------- #
# 真机证据复算（防回归）
# --------------------------------------------------------------------- #

class TestRealEvidence:
    """从 data/ 里的真机 dump 复算，验证规范与实现一致。"""

    def test_keyboard_up_38_percent_unreachable(self):
        r = audit_from_files("data/dump_keyboard_up.xml",
                             "data/windows_keyboard_up.json")
        assert r["ime_known"] is True
        assert r["clickable_count"] == 13
        # ★ 实测：4 个完全遮挡 + 1 个部分遮挡 = 5/13 = 38.5%
        assert r["occluded_count"] == 4
        assert r["partially_occluded_count"] == 1
        assert r["unreachable_count"] == 5
        assert abs(r["unreachable_ratio"] - 5 / 13) < 1e-9

    def test_keyboard_occupies_bottom_36_percent(self):
        r = audit_from_files("data/dump_keyboard_up.xml",
                             "data/windows_keyboard_up.json")
        # 键盘 0,1517,1080,2400；屏幕 2400 → 36.8%
        ime = ime_rect(ime_from_windows(
            __import__("json").loads(
                open("data/windows_keyboard_up.json",
                     encoding="utf-8").read())["windows"]))
        assert ime == Rect(0, 1517, 1080, 2400)
        assert abs((ime.y2 - ime.y1) / 2400 - 883 / 2400) < 1e-9

    def test_xml_has_no_ime_nodes(self):
        """★ 核心负发现：XML 里没有任何键盘节点。"""
        root = ET.parse("data/dump_keyboard_up.xml").getroot()
        pkgs = {n.get("package") for n in root.iter("node")}
        assert pkgs == {"com.google.android.settings.intelligence"}, \
            f"XML 里出现了非 App 的 package: {pkgs}"

    def test_xml_only_cannot_judge(self):
        """只有 XML 时必须报 unknown，即使键盘真的弹着。"""
        root = ET.parse("data/dump_keyboard_up.xml").getroot()
        r = audit_xml(root, None)
        assert r["ime_known"] is False
        assert all(i["reachability"] == "unknown" for i in r["items"])


# ---------------------------------------------------------------------------
# 齐 SPEC 一致性条件的覆盖缺口
# ---------------------------------------------------------------------------

class TestSpecConditions:
    """SPEC C1–C6 的逐条断言。

    用 tools/check_spec_coverage.py 扫出这些条件此前**没有对应断言**
    （SPEC 写了必须，但测试里找不到）。逐条补上。
    """

    # ---- C4：遮挡比按面积算，不得用 y 坐标大小比较 ----
    def test_c4_occlusion_by_area_not_y(self):
        """★ C4：遮挡比 = overlap / element.area，按面积算。

        第一版构造错了：我拿两个元素比遮挡比大小，
        而遮挡比已归一化到元素自身面积，B 完全在键盘内就是 1.0，
        A 只遮一部分反而更低。**构造反例前要先搞清归一化基准。**

        C4 真正要防的是：用 y 坐标比较（`el.y1 > ime.y1` 之类）
        判定"是否被遮挡"。反例是**一个 y 起点在键盘上方、但被完全遮挡的元素**——
        不，正确的反例是：一个 y 起点远低于键盘、面积重叠却更大的元素。

        构造：
          A：y1 在键盘**上方**（1400 < 1517），但向下延伸到键盘深处
          B：y1 在键盘**内**（1600），但很快结束（1800）
        → 若按 `y1 > ime.y1` 判遮挡，只有 B 算被遮挡；
          按面积重叠，A 的重叠远大于 B。
        """
        ime = Rect(0, 1517, 1080, 2400)
        a = Rect(0, 1400, 1080, 2337)      # 起于键盘上方，伸入键盘 820px
        b = Rect(100, 1600, 200, 1800)     # 起于键盘内，仅 200px 高
        assert a.y1 < ime.y1 < b.y1, "构造失败：A 的 y1 应在上，B 的 y1 应在下"
        # 面积重叠：A 远大于 B
        assert a.overlap(ime) > b.overlap(ime), "构造失败：A 的面积重叠应更大"
        # ★ 按面积算：A 的重叠非零
        assert a.overlap(ime) > 0, "C4：A 与键盘有面积重叠，必须判为被遮挡"
        # ★ 若用 y 坐标比较（`el.y1 >= ime.y1` 才算遮挡），A 会被判为未遮挡
        y_based_verdict = (a.y1 >= ime.y1)
        assert y_based_verdict is False, "y 比较会漏掉 A——这正是 C4 要禁的"
        assert a.overlap(ime) > 0, "而面积算判 A 被遮挡——两者结论相反"

    def test_c4_ratio_is_normalized_to_element_area(self):
        """遮挡比归一化到**元素自身**面积，不是屏幕面积。

        第一版就是没搞清这一点才构造错。同一块重叠，
        小元素的比值高于大元素。
        """
        ime = Rect(0, 1517, 1080, 2400)
        small = Rect(100, 1600, 200, 1800)   # 完全在键盘内 → 1.0
        large = Rect(0, 1400, 1080, 2337)    # 大部分在键盘内
        assert occlusion(small, ime) == 1.0
        assert 0 < occlusion(large, ime) < 1.0
        # 面积重叠是 large 更大，但比值相反
        assert large.overlap(ime) > small.overlap(ime)
        assert occlusion(small, ime) > occlusion(large, ime), (
            "归一化基准是元素自身面积——小元素完全被遮时比值更高")

    # ---- C5：遮挡比恰好 1.0 判 occluded ----
    def test_c5_exact_full_occlusion_is_occluded(self):
        """★ C5：遮挡比恰好 1.0 必须判 occluded（不是 partially）。"""
        ime = Rect(0, 1517, 1080, 2400)
        exact = Rect(100, 1600, 200, 1800)      # 完全在键盘内
        assert exact.overlap(ime) == exact.area, "构造失败：应完全在键盘内"
        assert occlusion(exact, ime) == 1.0
        assert reachability(exact, ime) == "occluded"

    def test_c5_near_full_is_partial(self):
        """边界：接近 1.0 但不是 1.0 → partially。"""
        ime = Rect(0, 1517, 1080, 2400)
        near = Rect(0, 1400, 1080, 2337)        # 顶部一小段在键盘外
        ratio = occlusion(near, ime)
        assert 0.0 < ratio < 1.0, f"构造失败：应为部分遮挡，实为 {ratio}"
        assert reachability(near, ime) == "partially_occluded"

    # ---- C6：parse_bounds 正确处理内部逗号 ----
    def test_c6_bounds_comma_inside_numbers(self):
        """★ C6：逗号在数字内部，不能当分隔符。

        我说过「有专门向量」——实际没有。
        第一版实现的错误：把 `][` 和 `[]` 换掉后 split，
        得到 `['0,1548', '1080,1712]`，`int('0,1548')` 直接 ValueError。
        """
        r = parse_bounds("[0,1548][1080,1712]")
        assert r is not None, "C6：含内部逗号的 bounds 必须解析成功"
        assert (r.x1, r.y1, r.x2, r.y2) == (0, 1548, 1080, 1712)

    def test_c6_bounds_zero_coords(self):
        """`[0,0][1080,2400]` 这类全零坐标。"""
        r = parse_bounds("[0,0][1080,2400]")
        assert r is not None
        assert (r.x1, r.y1, r.x2, r.y2) == (0, 0, 1080, 2400)

    def test_c6_bounds_malformed_returns_none(self):
        """畸形输入返回 None，不抛异常。"""
        for bad in ["", "[0,1548]", "[a,b][c,d]", "[0,1548][1080]", "garbage"]:
            assert parse_bounds(bad) is None, f"{bad!r} 应返回 None"

    def test_c6_bounds_distinct_values_differ(self):
        """仅最后一位不同的两个 bounds 必须解析成不同 Rect。

        这是逗号陷阱的判别式：若把 `,` 当分隔符，
        `[0,1548][1080,1712]` 会解析失败或错位。
        """
        r1 = parse_bounds("[0,1548][1080,1712]")
        r2 = parse_bounds("[0,1548][1080,1713]")
        assert r1 != r2, "仅末位不同的 bounds 必须不同"
        assert r2.y2 == 1713

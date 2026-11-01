"""blindspot 测试：黄金向量 + 元测试 + 真机证据复算。"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from core import (Rect, blind_regions, cross_check, cross_check_from_files, parse_bounds, parse_rect_flat, ime_agreement)
from vectors import iter_cases
from vectors_lib import xml_root_from

try:
    from PIL import Image as _Image
    _HAS_PIL = True
except ImportError:  # Pillow 未安装；见 requirements.txt
    _HAS_PIL = False

requires_pil = pytest.mark.skipif(
    not _HAS_PIL, reason="Pillow 未安装，见 requirements.txt")


@pytest.mark.parametrize("case", list(iter_cases()), ids=lambda c: c["id"])
def test_golden_vector(case):
    if "s" in case:
        parser = (parse_rect_flat if case.get("parser") == "flat"
                  else parse_bounds)
        got = parser(case["s"])
        want = Rect(*case["expect"]) if case["expect"] else None
        assert got == want, f"{case['id']}: {got} != {want}"

    elif "windows" in case:
        got = blind_regions(case["windows"])
        want = [Rect(*t) for t in case["expect"]]
        assert got == want, f"{case['id']}: {got} != {want}"

    elif "nodes" in case:
        root = xml_root_from(case["nodes"])
        r = cross_check(root, [], None)
        # 手动把盲区塞进去（cross_check 从 windows 取）
        from core import phantom_clickables
        ph = phantom_clickables(root, [Rect(0, 1517, 1080, 2400)])
        assert len(ph) == case["expect_count"], \
            f"{case['id']}: {len(ph)} != {case['expect_count']}"
        if ph:
            assert abs(ph[0]["occlusion_ratio"] - case["expect_ratio"]) < 1e-9


# --------------------------------------------------------------------- #
# 元测试
# --------------------------------------------------------------------- #

class TestNotVacuous:

    def test_a_bounds_varies(self):
        assert parse_bounds("[0,0][10,10]") != parse_bounds("[0,0][10,11]")
        assert parse_bounds("[0,0][10,10]") != parse_bounds("")

    def test_b_blind_presence_flips_phantom(self):
        """定向变异：有无盲区，幻影数必须翻转。"""
        root = xml_root_from([{"clickable": "true",
                               "bounds": "[0,1712][1080,1935]", "text": ""}])
        assert len(cross_check(root, [], None)["phantoms"]) == 0
        wins = [{"type": 2, "title": "kbd",
                 "bounds_in_screen": "0 1517 1080 2400"}]
        r = cross_check(root, wins, None)
        assert r["phantom_count"] == 1

    def test_b_type_two_required(self):
        """反向：type==1 即使标题像输入法也不得算盲区（C1）。"""
        wins = [{"type": 1, "title": "English (US) (QWERTY)",
                 "bounds_in_screen": "0 1517 1080 2400"}]
        assert blind_regions(wins) == []

    def test_b_unverified_type_not_added(self):
        """反向：未验证的窗口类型不得加入盲区（C2）。"""
        for t in (2004, 2038, 2000, 2011, 2032):
            assert blind_regions([{"type": t, "title": "x",
                                   "bounds_in_screen": "0 0 10 10"}]) == [], t

    def test_b_screenshot_none_not_verified(self):
        """没有截图时不得假装验证过（C4）。"""
        root = xml_root_from([{"clickable": "true",
                               "bounds": "[0,1712][1080,1935]", "text": ""}])
        r = cross_check(root, [{"type": 2, "title": "k",
                                "bounds_in_screen": "0 1517 1080 2400"}], None)
        assert r["phantom_count"] == 1
        assert r["screenshot_agrees"] is None

    def test_c_keys_present(self):
        r = cross_check(xml_root_from([]), [], None)
        for k in ("blind_regions", "clickable_count", "phantom_count",
                  "phantom_ratio", "phantoms", "screenshot_agrees"):
            assert k in r, f"缺字段 {k}"


# --------------------------------------------------------------------- #
# 真机证据复算
# --------------------------------------------------------------------- #

class TestRealEvidence:

    def test_phantom_5_of_13(self):
        r = cross_check_from_files("data/dump_before_tap.xml",
                                   "data/windows_keyboard_up.json")
        assert r["clickable_count"] == 13
        assert r["phantom_count"] == 5
        assert abs(r["phantom_ratio"] - 5 / 13) < 1e-9

    @requires_pil
    def test_screenshot_agrees(self):
        """截图确认盲区确实不是 App 内容（C3）。"""
        r = cross_check_from_files("data/dump_before_tap.xml",
                                   "data/windows_keyboard_up.json",
                                   "data/screencap_keyboard_up.png")
        assert r["screenshot_agrees"] is True
        assert r["screenshot_regions"][0]["same_as_app"] is False

    def test_behavioral_evidence_recorded(self):
        """行为证据：点击落在键盘上，搜索框 net → netv。"""
        d = json.loads(open("data/behavioral_evidence.json",
                            encoding="utf-8").read())
        assert d["before"]["search_field_text"] == "net"
        assert d["after"]["search_field_text"] == "netv"
        assert d["silent_failure"] is True
        # 用两份 dump 独立复算，不信 JSON 里的自述
        def field(p):
            for n in ET.parse(p).getroot().iter("node"):
                if n.get("bounds") == "[126,136][933,325]":
                    return n.get("text")
        assert field("data/dump_before_tap.xml") == "net"
        assert field("data/dump_after_tap.xml") == "netv"

    def test_xml_has_no_keyboard_package(self):
        """XML 里没有任何键盘节点。"""
        root = ET.parse("data/dump_before_tap.xml").getroot()
        pkgs = {n.get("package") for n in root.iter("node")}
        assert pkgs == {"com.google.android.settings.intelligence"}


# ---------------------------------------------------------------------------
# 齐 SPEC 一致性条件覆盖缺口
# ---------------------------------------------------------------------------

class TestSpecConditions:
    """SPEC C5–C7 的逐条断言。"""

    def test_c5_overlap_by_area_not_y(self):
        """★ C5：判定重叠必须用面积，不得用 y 坐标大小比较。

        反例：一个 y1 在 IME 上方、但向下伸入 IME 的元素。
        按 `y1 >= ime.y1` 判重叠会漏掉它。
        """
        ime = Rect(0, 1517, 1080, 2400)
        el = Rect(0, 1400, 1080, 2337)
        assert el.y1 < ime.y1, "构造失败：y1 应在 IME 上方"
        assert el.overlap(ime) > 0, "C5：有面积重叠，必须判为重叠"
        # y 比较会给出相反结论
        assert (el.y1 >= ime.y1) is False, "y 比较会漏掉——正是 C5 要禁的"

    def test_c6_bounds_comma_inside_numbers(self):
        """★ C6：`[0,1548][1080,1712]` 的逗号在数字内部。"""
        r = parse_bounds("[0,1548][1080,1712]")
        assert r is not None, "C6：含内部逗号必须解析成功"
        assert (r.x1, r.y1, r.x2, r.y2) == (0, 1548, 1080, 1712)

    def test_c6_bounds_malformed_returns_none(self):
        for bad in ["", "[0,1548]", "[a,b][c,d]", "garbage"]:
            assert parse_bounds(bad) is None

    def test_c6_bounds_distinct_values_differ(self):
        r1 = parse_bounds("[0,1548][1080,1712]")
        r2 = parse_bounds("[0,1548][1080,1713]")
        assert r1 != r2 and r2.y2 == 1713

    # ---- C7：截图与 IME bounds 不一致时显式报告 ----
    def test_c7_agreement_none_without_screenshot(self):
        """★ C7：没有截图时报 None，不假装验证过。"""
        r = ime_agreement(None, 1517)
        assert r["agreement"] is None, "缺通道时必须报 None"
        assert "无法比对" in r["reason"]

    def test_c7_agreement_none_without_window(self):
        r = ime_agreement(1517, None)
        assert r["agreement"] is None

    def test_c7_exact_match_agrees(self):
        """精确相等（真机实测：截图取色 y=1517，窗口 IME bounds y1=1517）。"""
        r = ime_agreement(1517, 1517)
        assert r["agreement"] is True
        assert r["delta"] == 0

    def test_c7_mismatch_is_reported_not_silenced(self):
        """★ C7：不一致必须显式报告，不得静默取其一。"""
        r = ime_agreement(1517, 1500)
        assert r["agreement"] is False
        assert r["delta"] == 17
        assert "17px" in r["reason"], "不一致必须给出量化原因"

    def test_c7_tolerance_respected(self):
        """容差内算一致（不同设备 IME 报的 bounds 可能有几像素抖动）。"""
        assert ime_agreement(1517, 1515, tolerance=5)["agreement"] is True
        assert ime_agreement(1517, 1510, tolerance=5)["agreement"] is False

    # ---- C3：截图是参考通道，冲突时 XML 错 ----
    @requires_pil
    def test_c3_screenshot_is_reference_channel(self):
        """★ C3：`cross_check` 有截图时必须给出 App 参考区域。

        参考区域是盲区上方的同宽条带——没有它就无法回答
        「盲区里是不是 App 内容」（第一版没传 app_ref，
        `verified` 恒为 False）。
        """
        xml = (
            '<hierarchy><node bounds="[0,1517][1080,2400]" '
            'clickable="true" text="btn"/></hierarchy>'
        )
        windows = [{"type": 2, "title": "kbd",
                    "bounds_in_screen": "0 1517 1080 2400"}]
        from PIL import Image
        img = Image.new("RGB", (1080, 2400), (232, 231, 239))
        for y in range(1517, 2400):
            for x in range(1080):
                img.putpixel((x, y), (241, 240, 247))
        root = ET.fromstring(xml)
        out = cross_check(root, windows, img=img)
        assert out["screenshot_agrees"] is not None, (
            "C3：有截图时必须给出截图验证结论，不许报 None")
        assert "app_reference" in out, (
            "C3：必须给出 App 参考区域——否则无法区分盲区与 App 内容")

    def test_c3_without_screenshot_reports_none(self):
        """没有截图时 `screenshot_agrees` 必须报 None，不假装验证过。"""
        xml = (
            '<hierarchy><node bounds="[0,1517][1080,2400]" '
            'clickable="true" text="btn"/></hierarchy>'
        )
        windows = [{"type": 2, "title": "kbd", "bounds_in_screen": "0 1517 1080 2400"}]
        out = cross_check(ET.fromstring(xml), windows, img=None)
        assert out["screenshot_agrees"] is None

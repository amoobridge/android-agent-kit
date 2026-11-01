"""pointparse 自测：实现细节与不变量。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pointparse import (
    Ambiguity,
    NoPointFound,
    ParsedPoint,
    SpaceHint,
    infer_space,
    parse_point,
    parse_points,
)

VECTORS = Path(__file__).resolve().parent.parent / "vectors"


# ---------------------------------------------------------------- 空间线索
class TestInferSpace:
    def test_unit_floats_are_normalized(self):
        assert infer_space(0.42, 0.38) is SpaceHint.NORMALIZED_UNIT

    def test_pixel_ints_within_image(self):
        assert infer_space(400, 900, width=1080, height=2400) is SpaceHint.PIXEL_INT

    def test_ints_beyond_image_fall_to_grid_1000(self):
        # 500x500 的图上给 (600, 700) —— 不可能是像素
        h = infer_space(600, 700, width=500, height=500)
        assert h is SpaceHint.NORMALIZED_1000

    def test_zero_zero_is_not_claimed_as_unit(self):
        # (0,0) 与 (1,1) 在两种解释下都合法 —— 故意不给强线索
        assert infer_space(0, 0, width=1080, height=2400) is SpaceHint.PIXEL_INT

    def test_unknown_for_odd_values(self):
        assert infer_space(-5, 120) is SpaceHint.UNKNOWN

    def test_no_probability_ever_returned(self):
        """线索是枚举，不是分数。不允许'60% 概率是像素'这种输出。"""
        for args in [(0.5, 0.5), (400, 900), (600, 700)]:
            r = infer_space(*args)
            assert isinstance(r, SpaceHint)


# ---------------------------------------------------------------- 干净格式
class TestCleanFormats:
    @pytest.mark.parametrize(
        "raw,expect_x,expect_y,fmt",
        [
            ({"x": 400, "y": 900}, 400, 900, "dict_xy"),
            ({"point": [400, 900]}, 400, 900, "dict_point"),
            ([400, 900], 400, 900, "sequence"),
            ((400, 900), 400, 900, "sequence"),
            ("(400, 900)", 400, 900, "paren_csv"),
            ("400, 900", 400, 900, "bare_csv"),
            ("x=400, y=900", 400, 900, "kv"),
            ('{"x": 400, "y": 900}', 400, 900, "dict_xy"),
        ],
    )
    def test_parses(self, raw, expect_x, expect_y, fmt):
        p = parse_point(raw)
        assert (p.x, p.y) == (expect_x, expect_y)
        assert p.source_format == fmt

    def test_raw_is_kept_for_audit(self):
        p = parse_point("(400, 900)")
        assert p.raw == "(400, 900)"


# ---------------------------------------------------------------- 拒答
class TestRefusal:
    @pytest.mark.parametrize(
        "raw",
        [
            {"x": None, "y": None},
            {"x": None, "y": None, "reason": "no button visible"},
            "I cannot see the target.",
            "找不到目标元素",
            "",
            None,
            42,
            "The screen appears to be blank.",
            {"error": "image too small"},
        ],
    )
    def test_no_point(self, raw):
        with pytest.raises(NoPointFound):
            parse_point(raw)

    def test_no_point_is_valueerror_subclass(self):
        """调用方可以用一个 except 抓住全部解析失败。"""
        assert issubclass(NoPointFound, ValueError)
        assert issubclass(Ambiguity, ValueError)


# ---------------------------------------------------------------- 歧义
class TestAmbiguity:
    @pytest.mark.parametrize(
        "raw",
        [
            "First tap (100, 200), then tap (300, 400).",
            [100, 200, 300, 400],
            {"bbox": [100, 200, 300, 400]},
            {"box": [10, 20, 30, 40]},
            "1,400, 900",  # 千分位歧义
        ],
    )
    def test_ambiguous(self, raw):
        with pytest.raises(Ambiguity):
            parse_point(raw)

    def test_same_point_twice_is_not_ambiguous(self):
        """重复同一个位置应当去重后唯一通过。"""
        p = parse_point("tap (400,900) and then tap (400,900) again")
        assert (p.x, p.y) == (400, 900)

    def test_ambiguity_carries_candidates(self):
        with pytest.raises(Ambiguity) as ei:
            parse_point([100, 200, 300, 400])
        assert ei.value.candidates


# ---------------------------------------------------------------- 脏数据
class TestMessy:
    def test_markdown_wrapped_json(self):
        p = parse_point('```json\n{"x": 400, "y": 900}\n```')
        assert (p.x, p.y) == (400, 900)

    def test_json_with_surrounding_prose(self):
        p = parse_point('Sure! Here you go: {"x": 12, "y": 34} Hope that helps.')
        assert (p.x, p.y) == (12, 34)

    def test_single_quoted_json(self):
        p = parse_point("{'x': 12, 'y': 34}")
        assert (p.x, p.y) == (12, 34)

    def test_trailing_comma_json(self):
        p = parse_point('{"x": 12, "y": 34,}')
        assert (p.x, p.y) == (12, 34)

    def test_chinese_semicolon(self):
        p = parse_point("400；900")
        assert (p.x, p.y) == (400, 900)

    def test_prose_with_parens(self):
        p = parse_point("I'll tap at (400, 900) now.")
        assert (p.x, p.y) == (400, 900)

    def test_xml_tag(self):
        p = parse_point("<point>400 900</point>")
        assert (p.x, p.y) == (400, 900)

    def test_negative_coordinates(self):
        p = parse_point("(-5, 120)")
        assert (p.x, p.y) == (-5, 120)

    def test_float_coordinates(self):
        p = parse_point("[12.5, 34.75]")
        assert (p.x, p.y) == (12.5, 34.75)


# ---------------------------------------------------------------- parse_points
class TestParsePoints:
    def test_returns_all_candidates_without_choosing(self):
        ps = parse_points("First tap (100, 200), then tap (300, 400).")
        assert len(ps) == 2
        assert (ps[0].x, ps[0].y) == (100, 200)
        assert (ps[1].x, ps[1].y) == (300, 400)

    def test_list_of_pairs(self):
        ps = parse_points([[1, 2], [3, 4]])
        assert len(ps) == 2

    def test_single_still_works(self):
        ps = parse_points("(400, 900)")
        assert len(ps) == 1


# ---------------------------------------------------------------- 不变量
class TestInvariants:
    def test_never_returns_nan_or_inf(self):
        for raw in ["(nan, 900)", "(inf, 1)"]:
            with pytest.raises((NoPointFound, Ambiguity, ValueError)):
                parse_point(raw)

    def test_idempotent_on_parsed_point(self):
        p = parse_point("(400, 900)")
        assert parse_point(p) is p

    def test_parsed_point_is_frozen(self):
        p = parse_point("(400, 900)")
        with pytest.raises(Exception):
            p.x = 1  # type: ignore[misc]

    def test_source_format_is_always_set(self):
        for raw in [{"x": 1, "y": 2}, "(3, 4)", "5, 6"]:
            assert parse_point(raw).source_format


# ---------------------------------------------------------------- 向量完备性
class TestVectorsWellFormed:
    def test_every_vector_has_why(self):
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            assert d.get("why"), f"{f.name} 缺少 why"

    def test_every_vector_has_cases(self):
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            assert len(d["cases"]) >= 3

    def test_vector_ids_unique(self):
        ids = [json.loads(f.read_text(encoding="utf-8"))["id"] for f in sorted(VECTORS.glob("*.json"))]
        assert len(ids) == len(set(ids))

    def test_vectors_match_implementation(self):
        """向量必须与当前实现一致——否则向量该更新或实现该修。"""
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for c in d["cases"]:
                try:
                    p = parse_point(c["in"])
                    got = ["ok", p.x, p.y, p.source_format]
                except NoPointFound:
                    got = ["nopoint"]
                except Ambiguity:
                    got = ["ambig"]
                assert got == c["out"], f"{f.name}: {c['in']!r}"

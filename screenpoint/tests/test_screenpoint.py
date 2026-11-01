"""screenpoint 参考实现自测。

与 conformance.py 的区别：这里测**实现细节与不变量**，那里测**规范符合性**。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from screenpoint import (
    CoordinateSpace,
    FitMode,
    GridKind,
    MappingError,
    Point,
    Rect,
    Size,
    map_point,
    map_rect,
    scale_transform,
    to_device_pixel,
)

VECTORS = Path(__file__).resolve().parent.parent / "vectors"


# ---------------------------------------------------------------- 类型校验
class TestSize:
    def test_rejects_zero(self):
        with pytest.raises(ValueError):
            Size(0, 100)

    def test_rejects_negative(self):
        with pytest.raises(ValueError):
            Size(100, -1)

    def test_rejects_float(self):
        with pytest.raises(TypeError):
            Size(100.5, 100)  # type: ignore[arg-type]

    def test_aspect(self):
        assert math.isclose(Size(1080, 2400).aspect, 0.45)


class TestCoordinateSpace:
    def test_pixel_rejects_grid_n(self):
        with pytest.raises(ValueError):
            CoordinateSpace("x", Size(100, 100), kind=GridKind.PIXEL, grid_n=1000)

    def test_pixel_classmethod_rejects_grid_n(self):
        with pytest.raises(TypeError):
            CoordinateSpace.pixel("x", 100, 100, grid_n=1000)  # type: ignore[call-arg]

    def test_normalized_requires_grid_n(self):
        with pytest.raises(ValueError):
            CoordinateSpace("x", Size(100, 100), kind=GridKind.NORMALIZED)

    def test_kind_accepts_string(self):
        s = CoordinateSpace("x", Size(10, 10), kind="normalized", grid_n=1000)
        assert s.kind is GridKind.NORMALIZED
        assert s.is_normalized

    def test_normalized_rejects_nonpositive_grid(self):
        with pytest.raises(ValueError):
            CoordinateSpace.normalized("x", 100, 100, grid_n=0)

    def test_rejects_unknown_origin(self):
        with pytest.raises(ValueError):
            CoordinateSpace("x", Size(10, 10), origin="center")  # type: ignore[arg-type]


# ---------------------------------------------------------------- 恒等式
class TestIdentity:
    def test_same_size_any_fit_is_identity(self):
        a = CoordinateSpace.pixel("a", 1080, 2400)
        for fit in FitMode:
            r = map_point(Point(123, 456), a, a, fit=fit)
            assert (r.x, r.y) == (123.0, 456.0), fit

    def test_corners_survive_roundtrip(self):
        dev = CoordinateSpace.pixel("dev", 1080, 2400)
        shot = CoordinateSpace.pixel("shot", 756, 1680)
        for fit in FitMode:
            fwd = map_point(Point(0, 0), dev, shot, fit=fit)
            back = map_point(fwd, shot, dev, fit=fit)
            assert math.isclose(back.x, 0.0, abs_tol=1e-9), fit
            assert math.isclose(back.y, 0.0, abs_tol=1e-9), fit


# ---------------------------------------------------------------- 模式差异
class TestFitModes:
    def test_stretch_uses_independent_axes(self):
        t = scale_transform(Size(800, 600), Size(1080, 1920), fit=FitMode.STRETCH)
        assert math.isclose(t.scale_x, 1080 / 800)
        assert math.isclose(t.scale_y, 1920 / 600)
        assert t.scale_x != t.scale_y

    def test_fit_pillarbox_offset_is_vertical(self):
        t = scale_transform(Size(1080, 1920), Size(1080, 2400), fit=FitMode.FIT)
        assert math.isclose(t.scale_x, 1.0)
        assert math.isclose(t.offset_x, 0.0)
        assert math.isclose(t.offset_y, 240.0)

    def test_fit_offsets_never_negative(self):
        """FIT 模式下偏移恒非负——内容完整装入，只可能有留白。"""
        for sw, sh, dw, dh in [
            (1080, 1920, 1080, 2400),
            (1920, 1080, 1080, 2400),
            (800, 600, 1080, 1920),
            (2400, 1080, 1080, 1920),
        ]:
            t = scale_transform(Size(sw, sh), Size(dw, dh), fit=FitMode.FIT)
            assert t.offset_x >= 0.0, (sw, sh, dw, dh)
            assert t.offset_y >= 0.0, (sw, sh, dw, dh)

    def test_fit_letterbox_is_vertical_padding(self):
        """宽内容进窄屏：宽度恰好铺满，上下留白。"""
        t = scale_transform(Size(1920, 1080), Size(1080, 2400), fit=FitMode.FIT)
        assert math.isclose(t.offset_x, 0.0)
        assert t.offset_y > 0

    def test_crop_offsets_can_be_negative(self):
        """CROP 下内容被裁，偏移为负——这是与 FIT 的关键区别。"""
        t = scale_transform(Size(1080, 1080), Size(1080, 2400), fit=FitMode.CROP)
        assert t.offset_x < 0
        assert math.isclose(t.offset_y, 0.0)

    def test_crop_scale_uses_max(self):
        t = scale_transform(Size(1080, 1080), Size(1080, 2400), fit=FitMode.CROP)
        assert math.isclose(t.scale_x, 2400 / 1080)
        assert math.isclose(t.scale_y, 2400 / 1080)

    def test_fit_and_crop_offsets_share_formula(self):
        s = Size(1080, 1080)
        d = Size(1080, 2400)
        tf = scale_transform(s, d, fit=FitMode.FIT)
        tc = scale_transform(s, d, fit=FitMode.CROP)
        assert math.isclose(tf.offset_x, (d.width - s.width * tf.scale_x) / 2)
        assert math.isclose(tc.offset_x, (d.width - s.width * tc.scale_x) / 2)


# ---------------------------------------------------------------- 归一化
class TestNormalized:
    def test_grid_1000_to_pixels(self):
        sp = CoordinateSpace.normalized("m", 1080, 2400, grid_n=1000)
        dev = CoordinateSpace.pixel("d", 1080, 2400)
        r = map_point(Point(500, 500), sp, dev, fit=FitMode.STRETCH)
        assert math.isclose(r.x, 540.0)
        assert math.isclose(r.y, 1200.0)

    def test_grid_1_to_pixels(self):
        sp = CoordinateSpace.normalized("m", 1080, 2400, grid_n=1)
        dev = CoordinateSpace.pixel("d", 1080, 2400)
        r = map_point(Point(0.5, 0.5), sp, dev, fit=FitMode.STRETCH)
        assert math.isclose(r.x, 540.0)
        assert math.isclose(r.y, 1200.0)

    def test_normalized_to_scaled_is_single_step(self):
        sp = CoordinateSpace.normalized("m", 1080, 2400, grid_n=1000)
        dev = CoordinateSpace.pixel("d", 1440, 3200)
        r = map_point(Point(500, 500), sp, dev, fit=FitMode.STRETCH)
        assert math.isclose(r.x, 720.0)
        assert math.isclose(r.y, 1600.0)

    def test_pixel_to_normalized_roundtrip(self):
        sp = CoordinateSpace.normalized("m", 1080, 2400, grid_n=1000)
        dev = CoordinateSpace.pixel("d", 1080, 2400)
        fwd = map_point(Point(540, 1200), dev, sp, fit=FitMode.STRETCH)
        assert math.isclose(fwd.x, 500.0)
        back = map_point(fwd, sp, dev, fit=FitMode.STRETCH)
        assert math.isclose(back.x, 540.0)


# ---------------------------------------------------------------- 取整与钳制
class TestRounding:
    def test_half_up_not_bankers(self):
        # 3x3 -> 10x10，比例 10/3。x=1 -> 3.333 -> 3；x=2 -> 6.667 -> 7
        src = CoordinateSpace.pixel("s", 3, 3)
        dst = CoordinateSpace.pixel("d", 10, 10)
        r = to_device_pixel(Point(2, 2), src, dst, fit=FitMode.STRETCH)
        assert (r.x, r.y) == (7, 7)

    def test_exact_half_rounds_up(self):
        # 构造 0.5 场景：1 -> 1.5 (3->4.5? ) 用 2x2 -> 3x3: 1 -> 1.5
        src = CoordinateSpace.pixel("s", 2, 2)
        dst = CoordinateSpace.pixel("d", 3, 3)
        r = to_device_pixel(Point(1, 1), src, dst, fit=FitMode.STRETCH)
        assert (r.x, r.y) == (2, 2)  # half-up，不是 banker's 的 2（偶数）也巧合是2

    def test_half_up_distinguishes_from_bankers(self):
        # 2x2 -> 5x5: 1 -> 2.5 -> half-up = 3, bankers = 2
        src = CoordinateSpace.pixel("s", 2, 2)
        dst = CoordinateSpace.pixel("d", 5, 5)
        r = to_device_pixel(Point(1, 1), src, dst, fit=FitMode.STRETCH)
        assert (r.x, r.y) == (3, 3)

    def test_clamping_reports_flag(self):
        src = CoordinateSpace.pixel("s", 1000, 1000)
        dst = CoordinateSpace.pixel("d", 1080, 2400)
        r = to_device_pixel(Point(5000, 5000), src, dst, fit=FitMode.STRETCH)
        assert (r.x, r.y) == (1079, 2399)
        assert r.clamped is True

    def test_negative_clamps_to_zero(self):
        src = CoordinateSpace.pixel("s", 1000, 1000)
        dst = CoordinateSpace.pixel("d", 1080, 2400)
        r = to_device_pixel(Point(-50, -50), src, dst, fit=FitMode.STRETCH)
        assert (r.x, r.y) == (0, 0)
        assert r.clamped is True

    def test_in_range_not_clamped(self):
        src = CoordinateSpace.pixel("s", 1000, 1000)
        dst = CoordinateSpace.pixel("d", 1080, 2400)
        r = to_device_pixel(Point(500, 500), src, dst, fit=FitMode.STRETCH)
        assert r.clamped is False


# ---------------------------------------------------------------- 矩形
class TestRect:
    def test_rect_uses_corner_transform(self):
        src = CoordinateSpace.pixel("s", 100, 100)
        dst = CoordinateSpace.pixel("d", 200, 200)
        r = map_rect(Rect(10, 20, 30, 40), src, dst, fit=FitMode.STRETCH)
        assert math.isclose(r.x, 20.0)
        assert math.isclose(r.y, 40.0)
        assert math.isclose(r.width, 60.0)
        assert math.isclose(r.height, 80.0)

    def test_rect_center_preserved_under_fit(self):
        src = CoordinateSpace.pixel("s", 1080, 1920)
        dst = CoordinateSpace.pixel("d", 1080, 2400)
        r = map_rect(Rect(0, 0, 1080, 1920), src, dst, fit=FitMode.FIT)
        assert math.isclose(r.center.x, 540.0)
        assert math.isclose(r.center.y, 1200.0)

    def test_rect_helpers(self):
        r = Rect(10, 20, 30, 40)
        assert (r.left, r.top, r.right, r.bottom) == (10, 20, 40, 60)
        assert r.center.x == 25 and r.center.y == 40


# ---------------------------------------------------------------- 真实链路回归
class TestRealChains:
    def test_pixel8_half_scale_tap(self):
        """Pixel 8: 1080x2400 → 756x1680（0.7）。模型点 (400,900) 应落在 (571,1286)。"""
        shot = CoordinateSpace.pixel("model_view", 756, 1680)
        dev = CoordinateSpace.pixel("device", 1080, 2400)
        r = to_device_pixel(Point(400, 900), shot, dev, fit=FitMode.STRETCH)
        assert r.x == 571
        assert r.y == 1286
        assert r.clamped is False

    def test_anthropic_1568_budget(self):
        """Anthropic 1568 长边预算：1080x2400 → 702x1568。"""
        shot = CoordinateSpace.pixel("model_view", 702, 1568)
        dev = CoordinateSpace.pixel("device", 1080, 2400)
        r = to_device_pixel(Point(351, 784), shot, dev, fit=FitMode.STRETCH)
        assert r.x == 540
        assert r.y == 1200

    def test_no_intermediate_rounding_drift(self):
        """链式两步不得比一步多出 >1px 误差。"""
        a = CoordinateSpace.pixel("a", 1080, 2400)
        b = CoordinateSpace.pixel("b", 756, 1680)
        c = CoordinateSpace.pixel("c", 403, 896)
        one = map_point(Point(400, 900), a, c, fit=FitMode.STRETCH)
        step1 = map_point(Point(400, 900), a, b, fit=FitMode.STRETCH)
        step2 = map_point(step1, b, c, fit=FitMode.STRETCH)
        assert math.isclose(one.x, step2.x, abs_tol=1e-6)
        assert math.isclose(one.y, step2.y, abs_tol=1e-6)


# ---------------------------------------------------------------- 向量完备性
class TestVectorsWellFormed:
    def test_every_vector_has_why(self):
        for f in sorted(VECTORS.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            assert data.get("why"), f"{f.name} 缺少 why 字段"

    def test_every_vector_has_cases(self):
        for f in sorted(VECTORS.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            assert len(data["cases"]) >= 3, f"{f.name} 用例过少"

    def test_vector_ids_unique(self):
        ids = [json.loads(f.read_text(encoding="utf-8"))["id"] for f in sorted(VECTORS.glob("*.json"))]
        assert len(ids) == len(set(ids)), "向量 id 重复"

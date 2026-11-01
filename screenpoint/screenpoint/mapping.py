"""screenpoint · 坐标映射。

核心主张：**反算由确定性代码完成，不得委托给模型。**

所有映射函数保持浮点精度，取整只发生在 :func:`to_device_pixel` 这一步，
且规则唯一（四舍五入，half-up）。禁止在链路中间取整。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .core import CoordinateSpace, FitMode, MappingError, Point, Rect, Size

__all__ = [
    "map_point",
    "map_rect",
    "to_device_pixel",
    "scale_transform",
    "Transform",
]


@dataclass(frozen=True, slots=True)
class Transform:
    """src 像素空间 → dst 像素空间的仿射变换：``dst = src * scale + offset``。"""

    scale_x: float
    scale_y: float
    offset_x: float
    offset_y: float

    def apply(self, p: Point) -> Point:
        return Point(p.x * self.scale_x + self.offset_x, p.y * self.scale_y + self.offset_y)

    def apply_rect(self, r: Rect) -> Rect:
        top_left = self.apply(Point(r.x, r.y))
        bottom_right = self.apply(Point(r.right, r.bottom))
        return Rect(
            x=top_left.x,
            y=top_left.y,
            width=bottom_right.x - top_left.x,
            height=bottom_right.y - top_left.y,
        )

    @property
    def is_identity(self) -> bool:
        return (
            math.isclose(self.scale_x, 1.0, rel_tol=0, abs_tol=1e-12)
            and math.isclose(self.scale_y, 1.0, rel_tol=0, abs_tol=1e-12)
            and math.isclose(self.offset_x, 0.0, abs_tol=1e-12)
            and math.isclose(self.offset_y, 0.0, abs_tol=1e-12)
        )


def scale_transform(src: Size, dst: Size, *, fit: FitMode) -> Transform:
    """计算 src 像素空间到 dst 像素空间的变换。

    - ``STRETCH``：两轴独立缩放，宽高比失真。
    - ``FIT``：等比缩放完整装入，留白居中（letterbox / pillarbox）。
    - ``CROP``：等比缩放完全覆盖，超出部分裁掉。

    FIT 与 CROP 的偏移公式相同，区别只在缩放系数的取法。
    """
    if fit is FitMode.STRETCH:
        return Transform(
            scale_x=dst.width / src.width,
            scale_y=dst.height / src.height,
            offset_x=0.0,
            offset_y=0.0,
        )

    if fit is FitMode.FIT:
        s = min(dst.width / src.width, dst.height / src.height)
    elif fit is FitMode.CROP:
        s = max(dst.width / src.width, dst.height / src.height)
    else:  # pragma: no cover - 枚举封闭
        raise MappingError(f"未知 fit 模式：{fit!r}")

    return Transform(
        scale_x=s,
        scale_y=s,
        offset_x=(dst.width - src.width * s) / 2.0,
        offset_y=(dst.height - src.height * s) / 2.0,
    )


def _to_pixel(space: CoordinateSpace, p: Point) -> Point:
    """把空间内的点换算成该空间自身尺寸下的像素坐标（浮点）。"""
    if not space.is_normalized:
        return p
    n = space.grid_n
    if n is None:  # pragma: no cover - 构造时已校验
        raise MappingError("NORMALIZED 空间缺少 grid_n")
    return Point(p.x / n * space.size.width, p.y / n * space.size.height)


def _from_pixel(space: CoordinateSpace, p: Point) -> Point:
    """把该空间自身尺寸下的像素坐标，换算成空间内的表示。"""
    if not space.is_normalized:
        return p
    n = space.grid_n
    if n is None:  # pragma: no cover - 构造时已校验
        raise MappingError("NORMALIZED 空间缺少 grid_n")
    return Point(p.x / space.size.width * n, p.y / space.size.height * n)


def _check_in_space(space: CoordinateSpace, p: Point, *, strict: bool) -> None:
    """检查点是否落在 src 空间内。越界是模型错误，必须显式处理。"""
    if not strict:
        return
    limit_x = space.grid_n if space.is_normalized else space.size.width
    limit_y = space.grid_n if space.is_normalized else space.size.height
    tol = 1e-9
    if p.x < -tol or p.y < -tol or p.x > limit_x + tol or p.y > limit_y + tol:
        raise MappingError(
            f"点 {p} 越出空间 {space} 的值域 [0,{limit_x:g}]x[0,{limit_y:g}]"
        )


def map_point(p: Point, src: CoordinateSpace, dst: CoordinateSpace, *, fit: FitMode) -> Point:
    """把点从 ``src`` 空间映射到 ``dst`` 空间，返回浮点结果。

    ``fit`` 是**必填关键字参数**——你必须知道截图是怎么产生的。
    猜一个模式比报错更危险。
    """
    _check_in_space(src, p, strict=False)
    px_src = _to_pixel(src, p)
    t = scale_transform(src.size, dst.size, fit=fit)
    px_dst = t.apply(px_src)
    return _from_pixel(dst, px_dst)


def map_rect(r: Rect, src: CoordinateSpace, dst: CoordinateSpace, *, fit: FitMode) -> Rect:
    """把矩形从 ``src`` 空间映射到 ``dst`` 空间。

    用对角点变换而非缩放宽高，保证 FIT/CROP 下几何一致。
    """
    px_tl = _to_pixel(src, Point(r.x, r.y))
    px_br = _to_pixel(src, Point(r.right, r.bottom))
    t = scale_transform(src.size, dst.size, fit=fit)
    tl = _from_pixel(dst, t.apply(px_tl))
    br = _from_pixel(dst, t.apply(px_br))
    return Rect(x=tl.x, y=tl.y, width=br.x - tl.x, height=br.y - tl.y)


def _round_half_up(v: float) -> int:
    """四舍五入。唯一取整规则，全库统一。"""
    return int(math.floor(v + 0.5))


@dataclass(frozen=True, slots=True)
class DevicePixel:
    """取整 + 钳制后的最终结果。"""

    x: int
    y: int
    clamped: bool

    @property
    def point(self) -> Point:
        return Point(float(self.x), float(self.y))

    def __str__(self) -> str:  # pragma: no cover - 人类可读
        flag = " (clamped)" if self.clamped else ""
        return f"({self.x}, {self.y}){flag}"


def to_device_pixel(
    p: Point,
    src: CoordinateSpace,
    device: CoordinateSpace,
    *,
    fit: FitMode,
) -> DevicePixel:
    """一步到位：模型指点 → 设备可点击的整数像素。

    这是 agent 侧唯一应该调用的函数。链路：
    浮点映射 → 取整（half-up）→ 钳制到 [0, size-1] → 上报是否钳制。
    """
    mapped = map_point(p, src, device, fit=fit)
    x = _round_half_up(mapped.x)
    y = _round_half_up(mapped.y)
    max_x = device.size.width - 1
    max_y = device.size.height - 1
    clamped = False
    if x < 0:
        x, clamped = 0, True
    elif x > max_x:
        x, clamped = max_x, True
    if y < 0:
        y, clamped = 0, True
    elif y > max_y:
        y, clamped = max_y, True
    return DevicePixel(x=x, y=y, clamped=clamped)

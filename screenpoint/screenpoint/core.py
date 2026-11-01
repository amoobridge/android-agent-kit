"""screenpoint · 核心类型。

坐标空间的三个不可省要素：名字、尺寸、约定。
没有空间声明的坐标是噪音。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class FitMode(str, Enum):
    """截图相对屏幕的缩放模式。数学不同，必须显式声明。"""

    #: 各轴独立拉伸。宽高比失真，但坐标是线性比例。
    STRETCH = "stretch"
    #: 等比缩放至完整装入，剩余留白（letterbox / pillarbox）。
    FIT = "fit"
    #: 等比缩放至完全覆盖，超出部分裁掉。
    CROP = "crop"


class GridKind(str, Enum):
    """坐标数值的含义。"""

    #: 像素坐标，原点在左上，单位 1 px。
    PIXEL = "pixel"
    #: 归一化网格。UI-TARS / Gemini 类模型常用，值域 [0, N]。
    NORMALIZED = "normalized"


@dataclass(frozen=True, slots=True)
class Size:
    """尺寸。宽高必须为正整数。"""

    width: int
    height: int

    def __post_init__(self) -> None:
        if not isinstance(self.width, int) or not isinstance(self.height, int):
            raise TypeError(f"Size 需要整数宽高，得到 {self.width!r} x {self.height!r}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Size 宽高必须为正，得到 {self.width}x{self.height}")

    @property
    def aspect(self) -> float:
        return self.width / self.height

    def __str__(self) -> str:  # pragma: no cover - 人类可读
        return f"{self.width}x{self.height}"


@dataclass(frozen=True, slots=True)
class Point:
    """一个点。允许小数（模型返回的常是估算值）。"""

    x: float
    y: float

    def __str__(self) -> str:  # pragma: no cover - 人类可读
        return f"({self.x:g}, {self.y:g})"


@dataclass(frozen=True, slots=True)
class Rect:
    """轴对齐矩形，左上原点。"""

    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2, self.y + self.height / 2)

    def __str__(self) -> str:  # pragma: no cover - 人类可读
        return f"[{self.x:g},{self.y:g} {self.width:g}x{self.height:g}]"


@dataclass(frozen=True, slots=True)
class CoordinateSpace:
    """一个具名坐标空间。

    Parameters
    ----------
    name:
        空间名，仅用于错误信息与调试。
    size:
        空间的像素尺寸。
    kind:
        数值含义。``PIXEL`` 时为像素；``NORMALIZED`` 时为归一化网格。
    grid_n:
        归一化网格的上界。``kind=NORMALIZED`` 时必填，常见 1000 或 1。
    origin:
        ``"top_left"``（默认，唯一受支持值）。
    """

    name: str
    size: Size
    kind: GridKind = GridKind.PIXEL
    grid_n: float | None = None
    origin: Final[str] = "top_left"

    def __post_init__(self) -> None:
        # 容许传入字符串形式的 kind，转成枚举后冻结
        if isinstance(self.kind, str):
            object.__setattr__(self, "kind", GridKind(self.kind))
        if self.origin != "top_left":
            raise ValueError(f"暂不支持 origin={self.origin!r}，仅支持 top_left")
        if self.kind is GridKind.NORMALIZED:
            if self.grid_n is None:
                raise ValueError("NORMALIZED 空间必须给出 grid_n")
            if self.grid_n <= 0:
                raise ValueError(f"grid_n 必须为正，得到 {self.grid_n!r}")
        elif self.grid_n is not None:
            raise ValueError("PIXEL 空间不应给出 grid_n")

    # -- 便捷构造 -------------------------------------------------------
    @classmethod
    def pixel(cls, name: str, width: int, height: int) -> CoordinateSpace:
        return cls(name=name, size=Size(width, height))

    @classmethod
    def normalized(cls, name: str, width: int, height: int, grid_n: float = 1000.0) -> CoordinateSpace:
        """归一化网格空间。

        ``size`` 仍是真实像素尺寸（用于把网格映射回像素），``grid_n``
        是模型使用的数值上界。
        """
        return cls(name=name, size=Size(width, height), kind=GridKind.NORMALIZED, grid_n=float(grid_n))

    # -- 判定 -----------------------------------------------------------
    @property
    def is_normalized(self) -> bool:
        return self.kind is GridKind.NORMALIZED

    def __str__(self) -> str:  # pragma: no cover - 人类可读
        if self.is_normalized:
            return f"{self.name}<norm {self.grid_n:g} over {self.size}>"
        return f"{self.name}<{self.size}>"


class MappingError(ValueError):
    """映射失败。调用方必须处理，不得静默继续。"""


__all__ = [
    "FitMode",
    "GridKind",
    "Size",
    "Point",
    "Rect",
    "CoordinateSpace",
    "MappingError",
]

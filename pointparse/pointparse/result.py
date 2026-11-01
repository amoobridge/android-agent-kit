"""pointparse · 结果类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SpaceHint(str, Enum):
    """从数值形态推断出的坐标空间线索。**只是线索，不是结论。**"""

    #: 两个都是整数，且在图像像素范围内 —— 大概率是像素坐标
    PIXEL_INT = "pixel_int"
    #: 两个都是 [0,1] 内的小数 —— 大概率是归一化（grid_n=1）
    NORMALIZED_UNIT = "normalized_unit"
    #: 两个都是 [0,1000] 内的整数，但超出图像像素范围 —— 大概率归一化 1000
    NORMALIZED_1000 = "normalized_1000"
    #: 形态无法判定
    UNKNOWN = "unknown"


class ParseError(ValueError):
    """解析失败基类。"""


class NoPointFound(ParseError):
    """模型没有给出可解析的指点。

    包含拒答、纯文字、空响应、明确说"看不到"等情况。
    **这不是异常状况**，是模型的正常输出之一，调用方必须能处理。
    """

    def __init__(self, raw, reason: str = "no point found"):
        self.raw = raw
        self.reason = reason
        super().__init__(f"{reason}: {raw!r}")


class Ambiguity(ParseError):
    """输出里有多个候选指点，无法唯一确定。

    典型：模型一次说了两个位置；或返回的是 bbox 而不是 point；
    或像素/归一化两种解释都成立。
    """

    def __init__(self, raw, candidates: list, reason: str = "ambiguous"):
        self.raw = raw
        self.candidates = list(candidates)
        self.reason = reason
        super().__init__(f"{reason}: {len(self.candidates)} candidates from {raw!r}")


@dataclass(frozen=True, slots=True)
class ParsedPoint:
    """一个成功解析出的指点。

    Attributes
    ----------
    x, y:
        数值。可能是像素也可能是归一化，见 ``space_hint``。
    space_hint:
        形态推断。**调用方必须结合自己声明的空间校验**，不能直接用。
    source_format:
        命中的格式名，用于审计与回归。
    raw:
        原始输入，便于出错时回溯。
    """

    x: float
    y: float
    space_hint: SpaceHint
    source_format: str
    raw: object = field(default=None, repr=False)

    @property
    def is_integral(self) -> bool:
        return float(self.x).is_integer() and float(self.y).is_integer()

    def __str__(self) -> str:  # pragma: no cover - 人类可读
        return f"({self.x:g}, {self.y:g}) [{self.space_hint.value} via {self.source_format}]"


__all__ = [
    "SpaceHint",
    "ParseError",
    "NoPointFound",
    "Ambiguity",
    "ParsedPoint",
]

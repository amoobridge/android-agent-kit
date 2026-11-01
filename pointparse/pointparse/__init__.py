"""pointparse · 解析模型返回的指点。

配套 screenpoint：screenpoint 管"代码怎么算"，pointparse 管"模型到底指了哪"。

核心主张与 screenpoint 一致：**宁可报错，不要猜。**
歧义时返回 AMBIGUOUS，由调用方决定，不替它选一个。
"""

from __future__ import annotations

from .result import (
    Ambiguity,
    NoPointFound,
    ParseError,
    ParsedPoint,
    SpaceHint,
)
from .parse import infer_space, parse_point, parse_points

__version__ = "0.1.0"

__all__ = [
    "Ambiguity",
    "NoPointFound",
    "ParseError",
    "ParsedPoint",
    "SpaceHint",
    "infer_space",
    "parse_point",
    "parse_points",
    "__version__",
]

"""screendiff · 跨快照元素匹配与变化分类。"""

from .core import (
    CHANGE_KINDS, ChangeSet, Effect, Element, MatchedPair,
    diff, effect_of, is_loading, is_stuck,
)

__version__ = "0.1.0"
__all__ = [
    "CHANGE_KINDS", "ChangeSet", "Effect", "Element", "MatchedPair",
    "diff", "effect_of", "is_loading", "is_stuck",
]

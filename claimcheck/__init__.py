"""claimcheck · 经验性声明的验证等级。

**核心规则**：单次观测只能产生假设，不能产生结论。
"""

from .core import (Claim, DANGER_SIGNALS, Level, LEVEL_NAMES,
                   MIN_LEVEL_FOR_SPEC, MUST_MARK_UNVERIFIED,
                   REPRO_PROTOCOL, classify, danger_signals,
                   must_mark_unverified, refute, required_marker,
                   repro_checklist, should_verify_before_writing)

__all__ = [
    "Claim", "Level", "LEVEL_NAMES", "MIN_LEVEL_FOR_SPEC",
    "MUST_MARK_UNVERIFIED", "DANGER_SIGNALS", "REPRO_PROTOCOL",
    "classify", "danger_signals", "must_mark_unverified", "refute",
    "required_marker", "repro_checklist", "should_verify_before_writing",
]

__version__ = "0.1.0"

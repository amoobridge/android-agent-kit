"""swipefind 黄金向量。"""

from __future__ import annotations

from core import (Rect, absorbed_by_keyboard, gesture_length,
                  is_at_top, is_exhausted, likely_effective, parse_bounds,
                  parse_rect_flat, recovery_ratio)

IME = Rect(0, 1517, 1080, 2400)

# --------------------------------------------------------------------- #
# bounds 解析
# --------------------------------------------------------------------- #

BOUNDS = [
    {"kind": "bounds", "id": "standard", "s": "[126,136][933,325]",
     "expect": (126, 136, 933, 325)},
    {"kind": "bounds", "id": "no-space", "s": "[0,1548][1080,1712]",
     "expect": (0, 1548, 1080, 1712)},
    {"kind": "bounds", "id": "flat", "s": "0 1517 1080 2400",
     "expect": (0, 1517, 1080, 2400), "parser": "flat"},
    {"kind": "bounds", "id": "empty", "s": "", "expect": None},
    {"kind": "bounds", "id": "garbage", "s": "xx", "expect": None},
]

# --------------------------------------------------------------------- #
# 手势长度（实测：非单调）
# --------------------------------------------------------------------- #

# ★ kind 字段显式声明用例测哪个函数。不靠 id 后缀猜——
#   那正是 uidref 向量空转事故的同款错误来源。
LENGTH = [
    {"kind": "length", "id": "100px-short", "d": 100, "expect": "short"},
    {"kind": "length", "id": "300px-short", "d": 300, "expect": "short"},
    {"kind": "length", "id": "600px-sweet", "d": 600, "expect": "sweet"},
    {"kind": "length", "id": "900px-sweet", "d": 900, "expect": "sweet"},
    # ★★ 非单调：比 900 更长，反而无效
    {"kind": "length", "id": "1200px-too-long", "d": 1200,
     "expect": "too_long"},
    {"kind": "length", "id": "1500px-too-long", "d": 1500,
     "expect": "too_long"},
    {"kind": "length", "id": "zero-invalid", "d": 0, "expect": "invalid"},
    {"kind": "length", "id": "negative-invalid", "d": -50,
     "expect": "invalid"},
]

EFFECTIVE = [
    {"kind": "effective", "id": "short-unlikely", "d": 100,
     "expect": "unlikely"},
    {"kind": "effective", "id": "sweet-likely", "d": 600,
     "expect": "likely"},
    {"kind": "effective", "id": "too-long-unlikely", "d": 1500,
     "expect": "unlikely"},
]

# --------------------------------------------------------------------- #
# 键盘吸收（实测 3/3）
# --------------------------------------------------------------------- #

ABSORB = [
    {"kind": "absorb", "id": "start-inside-ime",
     "why": "★ 实测：起点在键盘内 → 被吸收，往字段写字。",
     "g": (540, 2000, 540, 1000), "expect": True},
    {"kind": "absorb", "id": "start-inside-ime-diagonal",
     "why": "★ 实测斜滑同样被吸收。",
     "g": (700, 2100, 380, 1200), "expect": True},
    {"kind": "absorb", "id": "start-inside-ime-short",
     "why": "★ 实测短滑也被吸收。",
     "g": (540, 1900, 540, 1600), "expect": True},
    {"kind": "absorb", "id": "start-outside-ime",
     "why": "★ 实测对照：起点在 App 区 → 不写入。",
     "g": (540, 1400, 540, 400), "expect": False},
    {"kind": "absorb", "id": "start-above-ime-end-inside",
     "why": "起点在上方、终点穿进键盘 → 按起点判，不吸收。",
     "g": (540, 1000, 540, 2000), "expect": False},
    {"kind": "absorb", "id": "no-ime",
     "why": "没有键盘 → 无从吸收。",
     "g": (540, 2000, 540, 1000), "expect": False, "ime": None},
]

# --------------------------------------------------------------------- #
# 终止与恢复
# --------------------------------------------------------------------- #

EXHAUST = [
    {"kind": "exhaust", "id": "empty", "steps": [], "expect": False},
    {"kind": "exhaust", "id": "one-step", "steps": [{"new": 9, "gone": 2}], "expect": False},
    {"kind": "exhaust", "id": "two-zero",
     "steps": [{"new": 9, "gone": 2}, {"new": 5, "gone": 9},
               {"new": 0, "gone": 0}, {"new": 0, "gone": 0}],
     "expect": True},
    {"kind": "exhaust", "id": "one-zero-only",
     "why": "只观察一步为 0 不足以判定——可能是渲染延迟。",
     "steps": [{"new": 9, "gone": 2}, {"new": 0, "gone": 0}],
     "expect": False},
    {"kind": "exhaust", "id": "oscillating",
     "why": "有新有旧交替 → 未到底。",
     "steps": [{"new": 3, "gone": 3}, {"new": 0, "gone": 0},
               {"new": 2, "gone": 1}],
     "expect": False},
]

RECOVERY = [
    {"kind": "recovery", "id": "full", "i": {"a", "b", "c"}, "a": {"a", "b", "c"},
     "expect": 1.0},
    {"kind": "recovery", "id": "partial", "i": {"a", "b", "c", "d"}, "a": {"a", "b"},
     "expect": 0.5},
    {"kind": "recovery", "id": "none", "i": {"a"}, "a": {"z"}, "expect": 0.0},
    {"kind": "recovery", "id": "empty-initial", "i": set(), "a": {"a"}, "expect": 0.0},
]

ALL = BOUNDS + LENGTH + EFFECTIVE + ABSORB + EXHAUST + RECOVERY


def iter_cases():
    for g in (BOUNDS, LENGTH, EFFECTIVE, ABSORB, EXHAUST, RECOVERY):
        yield from g

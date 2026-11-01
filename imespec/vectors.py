"""imespec 黄金向量。

三组：
  bounds      parse_bounds 的正确性（C6：内部逗号）
  occlusion   遮挡比与可及性判定（C4/C5）
  unknown     拿不到键盘信息时必须报 unknown（C1）
"""

from __future__ import annotations

from core import (Rect, audit_xml, ime_from_windows, ime_rect, occlusion,
                  parse_bounds, parse_rect_flat, reachability)
from vectors_lib import xml_root_from

# --------------------------------------------------------------------- #
# bounds 解析
# --------------------------------------------------------------------- #

BOUNDS = [
    {
        "id": "standard",
        "why": "标准 `[x1,y1][x2,y2]`。",
        "s": "[126,136][933,325]",
        "expect": (126, 136, 933, 325),
    },
    {
        "id": "zero-origin",
        "why": "原点。",
        "s": "[0,0][1080,2400]",
        "expect": (0, 0, 1080, 2400),
    },
    {
        "id": "no-space-after-comma",
        "why": "逗号后无空格——uiautomator dump 的实际形态。",
        "s": "[0,1548][1080,1712]",
        "expect": (0, 1548, 1080, 1712),
    },
    {
        "id": "flat-four-space",
        "why": "AccessibilityWindowInfo 的 flattenToString：空格分隔四元组。",
        "s": "0 1517 1080 2400",
        "expect": (0, 1517, 1080, 2400),
        "parser": "flat",
    },
    {
        "id": "malformed-empty",
        "why": "空串 → None，不抛异常。",
        "s": "",
        "expect": None,
    },
    {
        "id": "malformed-garbage",
        "why": "垃圾输入 → None，不抛异常。",
        "s": "not-a-bounds",
        "expect": None,
    },
    {
        "id": "malformed-three-numbers",
        "why": "数字个数不对 → None。",
        "s": "[0,0][1080]",
        "expect": None,
    },
]

# --------------------------------------------------------------------- #
# 遮挡判定
# --------------------------------------------------------------------- #

IME = Rect(0, 1517, 1080, 2400)   # 实测键盘窗口

OCCLUSION = [
    {
        "id": "fully-inside",
        "why": "元素完全在键盘内 → 遮挡比 1.0 → occluded。",
        "el": Rect(0, 1712, 1080, 1935),
        "expect_ratio": 1.0,
        "expect_reach": "occluded",
    },
    {
        "id": "partially-overlapping",
        "why": "★ 实测用例：[0,1384][1080,1548] 与键盘重叠 31px/164px = 18.9%。",
        "el": Rect(0, 1384, 1080, 1548),
        "expect_ratio": 31 / 164,
        "expect_reach": "partially_occluded",
    },
    {
        "id": "fully-above",
        "why": "元素完全在键盘上方 → 0 → reachable。",
        "el": Rect(0, 328, 1080, 551),
        "expect_ratio": 0.0,
        "expect_reach": "reachable",
    },
    {
        "id": "touching-edge",
        "why": "正好贴上边界（y2 == ime.y1）→ 重叠 0 → reachable。",
        "el": Rect(0, 1000, 1080, 1517),
        "expect_ratio": 0.0,
        "expect_reach": "reachable",
    },
    {
        "id": "zero-area-element",
        "why": "零面积元素（退化 bounds）→ 遮挡比 0，不除零。",
        "el": Rect(100, 100, 100, 100),
        "expect_ratio": 0.0,
        "expect_reach": "reachable",
    },
    {
        "id": "element-covers-ime",
        "why": "元素比键盘还大（全屏容器）→ 遮挡比 < 1 → partially。",
        "el": Rect(0, 0, 1080, 2400),
        "expect_ratio": 883 / 2400,
        "expect_reach": "partially_occluded",
    },
]

# --------------------------------------------------------------------- #
# unknown：拿不到键盘信息
# --------------------------------------------------------------------- #

UNKNOWN = [
    {
        "id": "xml-only-clickable",
        "why": "只有 XML、键盘状态未知 → 每个元素必须报 unknown。",
        "nodes": [{"text": "按钮A", "clickable": "true",
                   "bounds": "[0,1712][1080,1935]"},
                  {"text": "按钮B", "clickable": "true",
                   "bounds": "[0,328][1080,551]"}],
        "expect_ime_known": False,
        "expect_all_unknown": True,
    },
    {
        "id": "xml-only-empty-tree",
        "why": "空树 → 0 个元素，ratio 0，不崩。",
        "nodes": [],
        "expect_ime_known": False,
        "expect_count": 0,
    },
]

# --------------------------------------------------------------------- #
# IME 窗口识别
# --------------------------------------------------------------------- #

WINDOWS = [
    {
        "id": "type-two-is-ime",
        "why": "type == 2 即 IME。★ 判据是 type，不是标题（C2）。",
        "windows": [
            {"type": 3, "title": None, "bounds_in_screen": "0 0 1080 74"},
            {"type": 2, "title": "English (US) (QWERTY)",
             "bounds_in_screen": "0 1517 1080 2400"},
            {"type": 1, "title": "Settings Services",
             "bounds_in_screen": "0 0 1080 2400"},
        ],
        "expect_ime": (0, 1517, 1080, 2400),
    },
    {
        "id": "no-ime-window",
        "why": "没有 type==2 的窗口 → 键盘没弹 → None。",
        "windows": [
            {"type": 3, "title": None, "bounds_in_screen": "0 0 1080 74"},
            {"type": 1, "title": "Settings Services",
             "bounds_in_screen": "0 0 1080 2400"},
        ],
        "expect_ime": None,
    },
    {
        "id": "ime-title-localized",
        "why": "标题随输入法而变（中文输入法标题不同），"
               "但 type 仍是 2 —— 证明标题不能当判据。",
        "windows": [
            {"type": 2, "title": "简体中文拼音",
             "bounds_in_screen": "0 1600 1080 2400"},
        ],
        "expect_ime": (0, 1600, 1080, 2400),
    },
]

ALL = BOUNDS + OCCLUSION + UNKNOWN + WINDOWS


def iter_cases():
    for group in (BOUNDS, OCCLUSION, UNKNOWN, WINDOWS):
        yield from group


def load() -> list[dict]:
    return list(iter_cases())

"""blindspot 黄金向量。"""

from __future__ import annotations

from core import Rect, blind_regions, cross_check, parse_bounds, parse_rect_flat

# --------------------------------------------------------------------- #
# bounds 解析
# --------------------------------------------------------------------- #

BOUNDS = [
    {"id": "standard", "why": "标准形态。",
     "s": "[126,136][933,325]", "expect": (126, 136, 933, 325)},
    {"id": "no-space", "why": "逗号后无空格——uiautomator 实际形态。",
     "s": "[0,1548][1080,1712]", "expect": (0, 1548, 1080, 1712)},
    {"id": "flat", "why": "AccessibilityWindowInfo 的 flattenToString。",
     "s": "0 1517 1080 2400", "expect": (0, 1517, 1080, 2400),
     "parser": "flat"},
    {"id": "empty", "why": "空串 → None。", "s": "", "expect": None},
    {"id": "garbage", "why": "垃圾 → None。",
     "s": "not-a-bounds", "expect": None},
]

# --------------------------------------------------------------------- #
# 盲区识别
# --------------------------------------------------------------------- #

WINDOWS = [
    {"id": "type-two-is-blind",
     "why": "type == 2 即 IME，即盲区。",
     "windows": [
         {"type": 3, "title": None, "bounds_in_screen": "0 0 1080 74"},
         {"type": 2, "title": "English (US) (QWERTY)",
          "bounds_in_screen": "0 1517 1080 2400"}],
     "expect": [(0, 1517, 1080, 2400)]},
    {"id": "no-ime",
     "why": "没有 type==2 → 无盲区。",
     "windows": [{"type": 3, "title": None,
                  "bounds_in_screen": "0 0 1080 74"}],
     "expect": []},
    {"id": "title-localized-still-blind",
     "why": "★ 标题换成中文输入法，type 仍是 2 → 仍是盲区。证明标题不能当判据。",
     "windows": [{"type": 2, "title": "简体中文拼音",
                  "bounds_in_screen": "0 1600 1080 2400"}],
     "expect": [(0, 1600, 1080, 2400)]},
    {"id": "type-one-not-blind",
     "why": "★ 反向：标题是输入法名但 type==1，不得当盲区。",
     "windows": [{"type": 1, "title": "English (US) (QWERTY)",
                  "bounds_in_screen": "0 1517 1080 2400"}],
     "expect": []},
    {"id": "toast-type-not-added",
     "why": "★ type==2004（toast）未经验证，不得 加入盲区（C2）。",
     "windows": [{"type": 2004, "title": "toast",
                  "bounds_in_screen": "0 2000 1080 2100"}],
     "expect": []},
]

# --------------------------------------------------------------------- #
# 幻影可点
# --------------------------------------------------------------------- #

BLIND = [Rect(0, 1517, 1080, 2400)]

PHANTOM = [
    {"id": "fully-inside",
     "why": "完全在盲区内 → 幻影。",
     "nodes": [{"clickable": "true", "bounds": "[0,1712][1080,1935]",
                "text": ""}],
     "expect_count": 1, "expect_ratio": 1.0},
    {"id": "partially-inside",
     "why": "★ 实测用例：[0,1384][1080,1548] 与键盘重叠 31/164 = 18.9%。",
     "nodes": [{"clickable": "true", "bounds": "[0,1384][1080,1548]",
                "text": ""}],
     "expect_count": 1, "expect_ratio": 31 / 164},
    {"id": "outside",
     "why": "完全在盲区上方 → 不是幻影。",
     "nodes": [{"clickable": "true", "bounds": "[0,328][1080,551]",
                "text": ""}],
     "expect_count": 0},
    {"id": "touching-edge",
     "why": "y2 正好等于 blind.y1 → 重叠 0 → 不是幻影。",
     "nodes": [{"clickable": "true", "bounds": "[0,1000][1080,1517]",
                "text": ""}],
     "expect_count": 0},
    {"id": "not-clickable",
     "why": "不可点的节点即使压住也不算幻影。",
     "nodes": [{"clickable": "false", "bounds": "[0,1712][1080,1935]",
                "text": ""}],
     "expect_count": 0},
    {"id": "malformed-bounds",
     "why": "bounds 畸形 → 跳过，不崩。",
     "nodes": [{"clickable": "true", "bounds": "garbage", "text": ""}],
     "expect_count": 0},
]

ALL = BOUNDS + WINDOWS + PHANTOM


def iter_cases():
    for g in (BOUNDS, WINDOWS, PHANTOM):
        yield from g

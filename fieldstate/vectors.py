"""fieldstate 黄金向量。

设计原则沿用 uidref：**每个用例必须测它声称的规则，不能空转**。
这里由 `TestNotVacuous` 负责。

向量分三组：
  xml-layer   只有 XML 属性时的判定（D1 必须返回 unknown）
  api-layer   有无障碍 API 字段时的判定（D1 必须精确）
  discriminators  D1 的正确答案从哪个字段来
"""

from __future__ import annotations

import json
from pathlib import Path

# -----------------------------------------------------------------------
# XML 层：只有 uiautomator dump 的属性
# -----------------------------------------------------------------------

XML_LAYER = [
    {
        "id": "xml-empty-text",
        "why": "text 为空字符串。这是唯一一种 text == '' 判据碰巧对的情况——"
               "字段无 hint。**不能说这一例通过了就说法判据可靠。**",
        "node": {"text": "", "focused": "true", "focusable": "true",
                 "class": "android.widget.EditText"},
        "expect": {"d1_is_empty": "unknown", "d1_reliable": False,
                   "d2_is_focused": "focused", "d2_reliable": True,
                   "d3_is_writable": "writable_heuristic",
                   "d3_reliable": False, "layer": "xml"},
    },
    {
        "id": "xml-empty-with-hint",
        "why": "★ 核心用例。字段为空、有 hint，XML 的 text 报的是 hint。"
               "text 非空 → text == '' 判据会错判成 nonempty。",
        "node": {"text": "Search\nsettings", "focused": "true",
                 "class": "android.widget.EditText"},
        "expect": {"d1_is_empty": "unknown", "d1_reliable": False,
                   "heuristic_newline_in_text": True},
    },
    {
        "id": "xml-nonempty",
        "why": "字段真有内容。text 非空且无换行——与上一条在 text 非空这点上"
               "无法区分，这正是问题所在。",
        "node": {"text": "PROBE", "focused": "true",
                 "class": "android.widget.EditText"},
        "expect": {"d1_is_empty": "unknown", "d1_reliable": False,
                   "heuristic_newline_in_text": False},
    },
    {
        "id": "xml-focusable-not-focused",
        "why": "focusable=true 但 focused=false。判定聚焦必须用 focused（C2）。",
        "node": {"text": "PROBE", "focusable": "true", "focused": "false",
                 "class": "android.widget.EditText"},
        "expect": {"d2_is_focused": "unfocused", "d2_reliable": True},
    },
    {
        "id": "xml-focusable-missing",
        "why": "focusable 缺失时不得回退到 focusable。",
        "node": {"text": "PROBE", "focused": "true",
                 "class": "android.widget.EditText"},
        "expect": {"d2_is_focused": "focused"},
    },
    {
        "id": "xml-non-edittext",
        "why": "class 不是 EditText → 只读（启发式）。",
        "node": {"text": "静态文本", "focused": "false",
                 "class": "android.widget.TextView"},
        "expect": {"d3_is_writable": "readonly_heuristic",
                   "d3_reliable": False},
    },
]

# ---------------------------------------------------------------------------
# API 层：textin/refapp PROBE_STATE 的 JSON 字段（SPEC §5）
# ---------------------------------------------------------------------------

API_LAYER = [
    {
        "id": "api-empty-hint",
        "why": "★ is_showing_hint_text=true → 空。这是 D1 的正确答案。",
        "json": {"focus": "input", "is_editable": True,
                 "is_showing_hint_text": True,
                 "text_selection_start": -1, "text_selection_end": -1,
                 "is_focused": True, "text": "Search settings"},
        "expect": {"d1_is_empty": "empty", "d1_reliable": True,
                   "layer": "api"},
    },
    {
        "id": "api-nonempty",
        "why": "is_showing_hint_text=false → 非空。",
        "json": {"focus": "input", "is_editable": True,
                 "is_showing_hint_text": False,
                 "text_selection_start": 5, "text_selection_end": 5,
                 "is_focused": True, "text": "PROBE"},
        "expect": {"d1_is_empty": "nonempty", "d1_reliable": True},
    },
    {
        "id": "api-selection-minus-one",
        "why": "次选判据：text_selection_start < 0 → 空。"
               "用于拿不到 is_showing_hint_text 的后端。",
        "json": {"focus": "input", "is_editable": True,
                 "is_showing_hint_text": None,
                 "text_selection_start": -1, "text_selection_end": -1,
                 "is_focused": True, "text": "任何值都不看"},
        "expect": {"d1_is_empty": "empty", "d1_reliable": True},
    },
    {
        "id": "api-selection-zero",
        "why": "text_selection_start == 0 → 有内容（光标在首位）。"
               "0 不是负数，不得判成空。",
        "json": {"focus": "input", "is_editable": True,
                 "text_selection_start": 0, "text_selection_end": 0,
                 "is_focused": True, "text": "x"},
        "expect": {"d1_is_empty": "nonempty", "d1_reliable": True},
    },
    {
        "id": "api-readonly",
        "why": "is_editable=false → 只读。聚焦了也不能写。",
        "json": {"focus": "input", "is_editable": False,
                 "is_showing_hint_text": False,
                 "text_selection_start": 3, "text_selection_end": 3,
                 "is_focused": True, "text": "abc"},
        "expect": {"d1_is_empty": "nonempty",
                   "d3_is_writable": "readonly", "d3_reliable": True},
    },
    {
        "id": "api-no-focus",
        "why": "focus=none → 未聚焦。",
        "json": {"focus": "none"},
        "expect": {"d2_is_focused": "unfocused", "d2_reliable": True},
    },
]

# ---------------------------------------------------------------------------
# 判别器：D1 的答案来自哪个字段
# ---------------------------------------------------------------------------

DISCRIMINATORS = [
    {
        "id": "hint-field-beats-text",
        "why": "同一个字段，text 非空但 is_showing_hint_text=true → 判空。"
               "证明判据来自 hint 字段，不来自 text。",
        "text": "Search\nsettings",
        "is_showing_hint_text": True,
        "expect": "empty",
    },
    {
        "id": "hint-field-beats-text-neg",
        "why": "反过来：text 为空但 is_showing_hint_text=false → 判非空。"
               "证明不是简单地'看 text'。",
        "text": "",
        "is_showing_hint_text": False,
        "expect": "nonempty",
    },
]

ALL = XML_LAYER + API_LAYER


def iter_cases():
    for group in (XML_LAYER, API_LAYER):
        yield from group


def load() -> list[dict]:
    return list(iter_cases())


def dump_json(path: str | Path) -> None:
    Path(path).write_text(
        json.dumps({"xml_layer": XML_LAYER, "api_layer": API_LAYER,
                    "discriminators": DISCRIMINATORS},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

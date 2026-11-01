"""imespec 核心：键盘遮挡与元素可及性判定。

**它回答什么**：一个元素报着合法的 bounds 和 clickable=true，
点它真的能点到你想要的东西吗？——**不一定，键盘可能正压在它上面。**

一致性条件见 SPEC.md §6。
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

# AccessibilityWindowInfo 的 type 常量（公开 API，android.view.accessibility）
TYPE_APPLICATION = 1
TYPE_INPUT_METHOD = 2
TYPE_SYSTEM = 3
TYPE_ACCESSIBILITY_OVERLAY = 4
TYPE_SPLIT_SCREEN_DIVIDER = 5
TYPE_MAGNIFICATION_OVERLAY = 6


@dataclass(frozen=True)
class Rect:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def area(self) -> int:
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)

    def overlap(self, other: "Rect") -> int:
        w = min(self.x2, other.x2) - max(self.x1, other.x1)
        h = min(self.y2, other.y2) - max(self.y1, other.y1)
        return max(0, w) * max(0, h)

    def contains(self, other: "Rect") -> bool:
        return (self.x1 <= other.x1 and self.y1 <= other.y1
                and self.x2 >= other.x2 and self.y2 >= other.y2)


def parse_bounds(s: str) -> Rect | None:
    """解析 `uiautomator dump` 的 bounds：`[x1,y1][x2,y2]`。

    ★ 自己踩过的坑：第一版写 `s.replace('][',' ').replace('[','')
      .replace(']','').split()`，得到 `['0,1548', '1080,1712]`，
      `int('0,1548')` 直接 ValueError。**逗号在数字内部**，
      不能当分隔符。正确做法是先拆方括号再拆逗号。
    """
    if not s:
        return None
    try:
        parts = s.replace("[", " ").replace("]", " ").split()
        if len(parts) != 2:
            return None
        x1, y1 = (int(v) for v in parts[0].split(","))
        x2, y2 = (int(v) for v in parts[1].split(","))
        return Rect(x1, y1, x2, y2)
    except (ValueError, IndexError):
        return None


def parse_rect_flat(s: str) -> Rect | None:
    """解析 `AccessibilityWindowInfo.getBoundsInScreen().flattenToString()`
    的输出：`left top right bottom`（空格分隔）。"""
    if not s:
        return None
    try:
        v = [int(x) for x in s.split()]
        if len(v) != 4:
            return None
        return Rect(v[0], v[1], v[2], v[3])
    except ValueError:
        return None


# --------------------------------------------------------------------- #
# IME 窗口
# --------------------------------------------------------------------- #

def ime_from_windows(windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """从 `AccessibilityWindowInfo` 列表里找 IME 窗口。

    **判据是 `type == TYPE_INPUT_METHOD (2)`**，不是标题匹配——
    标题是 IME 的名字（"English (US) (QWERTY)"），随输入法而变，
    不能当判据。

    实测：键盘弹起时 `getWindows()` 返回 4 个窗口，其中 type==2 的那个
    bounds 是 `0 1517 1080 2400`。
    """
    for w in windows:
        if w.get("type") == TYPE_INPUT_METHOD:
            return w
    return None


def ime_rect(w: dict[str, Any]) -> Rect | None:
    return parse_rect_flat(w.get("bounds_in_screen", ""))


# --------------------------------------------------------------------- #
# 遮挡判定
# --------------------------------------------------------------------- #

def occlusion(element: Rect, ime: Rect | None) -> float:
    """元素被 IME 遮挡的面积比，0.0 ~ 1.0。

    `ime is None`（键盘没弹）→ 0.0。
    """
    if ime is None:
        return 0.0
    a = element.area
    if a == 0:
        return 0.0
    return element.overlap(ime) / a


def reachability(element: Rect, ime: Rect | None) -> str:
    """元素的可及性。

    | 遮挡比 | 结论 |
    |---|---|
    | 0 | `reachable` |
    | (0, 1) | `partially_occluded` |
    | >= 1 | `occluded` |

    边界：恰好 1.0 判 `occluded`（完全压住）。
    """
    r = occlusion(element, ime)
    if r <= 0.0:
        return "reachable"
    if r >= 1.0:
        return "occluded"
    return "partially_occluded"


# --------------------------------------------------------------------- #
# XML 层：拿不到键盘信息
# --------------------------------------------------------------------- #

def xml_clickable_nodes(root: ET.Element) -> list[ET.Element]:
    return [n for n in root.iter("node") if n.get("clickable") == "true"]


def ime_from_xml(root: ET.Element) -> dict[str, Any] | None:
    """★ 恒为 None。

    `uiautomator dump` 只捕获**活动 App 窗口**。IME 是独立窗口，
    XML 里一个节点都没有。实测：键盘弹起时 XML 有 35 个节点，
    package 全是 `com.google.android.settings.intelligence`。

    这个函数存在是为了让"XML 拿不到"这件事在代码里显式，
    而不是靠调用方忘记考虑。
    """
    return None


def audit_xml(root: ET.Element, ime: Rect | None) -> dict[str, Any]:
    """审计一份 XML dump。

    `ime is None` 时（也就是只能拿到 XML 时）：
      - 每个元素的 reachability 报 `unknown`
      - **不猜**。这是 SPEC C1：没有键盘信息时不得假定键盘不在。

    有 ime 时给出精确判定。
    """
    nodes = xml_clickable_nodes(root)
    items = []
    for n in nodes:
        r = parse_bounds(n.get("bounds") or "")
        if ime is None or r is None:
            reach = "unknown"
            ratio = None
        else:
            ratio = occlusion(r, ime)
            reach = reachability(r, ime)
        items.append({
            "text": n.get("text") or "",
            "bounds": n.get("bounds") or "",
            "clickable": True,
            "occlusion_ratio": ratio,
            "reachability": reach,
        })

    n_occluded = sum(1 for i in items if i["reachability"] == "occluded")
    n_partial = sum(1 for i in items
                    if i["reachability"] == "partially_occluded")
    return {
        "ime_known": ime is not None,
        "clickable_count": len(items),
        "occluded_count": n_occluded,
        "partially_occluded_count": n_partial,
        "unreachable_count": n_occluded + n_partial,
        "unreachable_ratio": ((n_occluded + n_partial) / len(items)
                              if items else 0.0),
        "items": items,
    }


# --------------------------------------------------------------------- #
# 证据复算（从 data/ 里的真机 dump 复算）
# --------------------------------------------------------------------- #

def audit_from_files(xml_path: str, windows_json_path: str) -> dict[str, Any]:
    """从保存的真机证据复算。用于 CI 里防回归。"""
    root = ET.parse(xml_path).getroot()
    wins = json.loads(open(windows_json_path, encoding="utf-8").read())
    ime = ime_rect(ime_from_windows(wins["windows"]) or {})
    return audit_xml(root, ime)

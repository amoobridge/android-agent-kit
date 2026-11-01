"""blindspot 核心：XML dump 的非 App 窗口盲区。

**它回答什么**：agent 有两条感知通道——
  * `screencap`（截图）：**完整**，含键盘
  * `uiautomator dump`（XML）：**有损**，看不见键盘

两条通道对"屏幕上有什么"给出**不一致**的答案。
本库把这种不一致显式化，并给出"能不能点"的判据。

一致性条件见 SPEC.md §6。
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Iterable

TYPE_INPUT_METHOD = 2


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
    """`[x1,y1][x2,y2]`。★ 逗号在数字内部，必须先拆方括号再拆逗号。"""
    if not s:
        return None
    try:
        p = s.replace("[", " ").replace("]", " ").split()
        if len(p) != 2:
            return None
        x1, y1 = (int(v) for v in p[0].split(","))
        x2, y2 = (int(v) for v in p[1].split(","))
        return Rect(x1, y1, x2, y2)
    except (ValueError, IndexError):
        return None


def parse_rect_flat(s: str) -> Rect | None:
    if not s:
        return None
    try:
        v = [int(x) for x in s.split()]
        return Rect(v[0], v[1], v[2], v[3]) if len(v) == 4 else None
    except ValueError:
        return None


# --------------------------------------------------------------------- #
# 盲区：非 App 窗口
# --------------------------------------------------------------------- #

def ime_from_windows(windows: Iterable[dict]) -> dict | None:
    """判据是 `type == TYPE_INPUT_METHOD (2)`，不是标题。"""
    for w in windows:
        if w.get("type") == TYPE_INPUT_METHOD:
            return w
    return None


def blind_regions(windows: Iterable[dict]) -> list[Rect]:
    """XML dump 看不见的屏幕区域。

    当前只认定 IME——那是唯一已在真机验证的一类。
    **不猜**：toast、系统权限对话框、通知栏等其他非 App 窗口
    是否也在 XML 盲区里，尚未验证，不得凭推测加入。
    """
    out = []
    w = ime_from_windows(windows)
    if w:
        r = parse_rect_flat(w.get("bounds_in_screen", ""))
        if r:
            out.append(r)
    return out


# --------------------------------------------------------------------- #
# 幻影可点：XML 说可点，实际在盲区里
# --------------------------------------------------------------------- #

def clickable_nodes(root: ET.Element) -> list[ET.Element]:
    return [n for n in root.iter("node") if n.get("clickable") == "true"]


def phantom_clickables(root: ET.Element, blind: list[Rect]) -> list[dict]:
    """XML 报 clickable=true 但 bounds 落在盲区内的元素。

    这些是**幻影目标**：agent 以为能点，点下去命中的是键盘。
    """
    out = []
    for n in clickable_nodes(root):
        r = parse_bounds(n.get("bounds") or "")
        if r is None:
            continue
        for b in blind:
            if b.overlap(r) > 0:
                out.append({
                    "text": n.get("text") or "",
                    "bounds": n.get("bounds") or "",
                    "rect": r,
                    "blind": b,
                    "occlusion_ratio": (b.overlap(r) / r.area
                                        if r.area else 0.0),
                })
                break
    return out


# --------------------------------------------------------------------- #
# 截图侧：唯一完整通道
# --------------------------------------------------------------------- #

def region_stats(img: Any, rect: Rect) -> dict[str, Any]:
    """统计一个矩形区域的像素。

    用于**验证**盲区确实不是 App 内容：键盘区域的像素统计与
    App 背景显著不同。

    返回 dominant 颜色与占比。`img` 是 PIL Image（RGB）。
    """
    box = img.crop((rect.x1, rect.y1, rect.x2, rect.y2))
    px = box.load()
    w, h = box.size
    total = 0
    counts: dict[tuple[int, int, int], int] = {}
    step = max(1, w // 40)
    for y in range(0, h, max(1, h // 40)):
        for x in range(0, w, step):
            c = px[x, y][:3]
            counts[c] = counts.get(c, 0) + 1
            total += 1
    if not total:
        return {"dominant": None, "dominant_ratio": 0.0, "sampled": 0}
    dom, n = max(counts.items(), key=lambda kv: kv[1])
    return {"dominant": dom, "dominant_ratio": n / total, "sampled": total}


def verify_blind_in_screenshot(img: Any, blind: list[Rect],
                               app_ref: Rect | None = None) -> dict:
    """用截图验证盲区。

    ★ 关键判据不是"颜色是什么"，而是**盲区与 App 参考区域的
    像素统计不同**——说明那里确实不是 App 内容。
    """
    res = {"regions": [], "verified": None}
    for b in blind:
        st = region_stats(img, b)
        entry = {"blind": b, **st}
        if app_ref is not None:
            ref = region_stats(img, app_ref)
            entry["app_dominant"] = ref["dominant"]
            entry["same_as_app"] = (st["dominant"] == ref["dominant"])
        res["regions"].append(entry)
    if res["regions"]:
        res["verified"] = any(not e.get("same_as_app", True)
                              for e in res["regions"])
    return res


# --------------------------------------------------------------------- #
# 跨通道一致性
# --------------------------------------------------------------------- #

def cross_check(root: ET.Element, windows: list[dict],
                img: Any = None) -> dict[str, Any]:
    """两条通道的一致性报告。

    `img` 为 None 时（只有 XML + 窗口列表）：
      - 仍能判定幻影可点（IME bounds 是精确的）
      - 但 `screenshot_agrees` 报 None，**不假装验证过**

    有 `img` 时：用截图验证盲区确实非 App 内容。
    """
    blind = blind_regions(windows)
    phantoms = phantom_clickables(root, blind)
    cl = clickable_nodes(root)
    out = {
        "blind_regions": [b.__dict__ for b in blind],
        "clickable_count": len(cl),
        "phantom_count": len(phantoms),
        "phantom_ratio": (len(phantoms) / len(cl) if cl else 0.0),
        "phantoms": phantoms,
        "screenshot_agrees": None,
    }
    if img is not None and blind:
        # App 参考区域：盲区上方的同宽条带。
        # 用它做基线，才能回答"盲区里是不是 App 内容"。
        w, h = img.size
        b = blind[0]
        ref = Rect(b.x1, max(0, b.y1 - 400), b.x2, b.y1)
        v = verify_blind_in_screenshot(img, blind, app_ref=ref)
        out["screenshot_agrees"] = v["verified"]
        out["screenshot_regions"] = v["regions"]
        out["app_reference"] = ref.__dict__
    return out


def cross_check_from_files(xml_path: str, windows_json_path: str,
                           png_path: str | None = None) -> dict:
    root = ET.parse(xml_path).getroot()
    wins = json.loads(open(windows_json_path, encoding="utf-8").read())
    img = None
    if png_path:
        from PIL import Image
        img = Image.open(png_path).convert("RGB")
    return cross_check(root, wins["windows"], img)


# --------------------------------------------------------------------- #
# SPEC C7 —— 截图与 IME bounds 不一致时显式报告
# --------------------------------------------------------------------- #

def ime_agreement(screenshot_ime_top: int | None,
                  window_ime_top: int | None,
                  tolerance: int = 0) -> dict:
    """C7：两条通道对「IME 上边界」的认定是否一致。

    不一致时必须显式报告，不得静默取其一。

    为什么需要：`screencap` 截到整个屏幕（键盘在里面），
    `AccessibilityWindowInfo` 报 IME 窗口 bounds。两者应描述同一个键盘。
    若不一致（截图里键盘起点 y=1517，窗口报 y=1500），
    说明有一条通道拿到的信息是错的——此时按任何一条做判定都可能错。

    `screenshot_ime_top is None`（没有截图）→ `agreement` 为 None，
    **不假装验证过**（与 `screenshot_agrees` 同一条原则）。
    """
    if screenshot_ime_top is None or window_ime_top is None:
        return {"agreement": None,
                "screenshot_ime_top": screenshot_ime_top,
                "window_ime_top": window_ime_top,
                "reason": "缺一条通道，无法比对"}
    delta = abs(screenshot_ime_top - window_ime_top)
    agree = delta <= tolerance
    return {"agreement": agree,
            "screenshot_ime_top": screenshot_ime_top,
            "window_ime_top": window_ime_top,
            "delta": delta,
            "tolerance": tolerance,
            "reason": "" if agree else
                      f"两通道对 IME 上边界认定相差 {delta}px，超过容差 {tolerance}px"}

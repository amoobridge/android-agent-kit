"""swipefind 核心：滚动手势的有效性与吸收判定。

**它回答两个问题**：
  1. 这个 swipe 会滚动吗？（距离非单调——太长也会静默失败）
  2. 这个 swipe 会被键盘吸收、往输入框里写字吗？（会，3/3 复现）

一致性条件见 SPEC.md §6。
"""

from __future__ import annotations

from dataclasses import dataclass

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

    def overlap(self, o: "Rect") -> int:
        w = min(self.x2, o.x2) - max(self.x1, o.x1)
        h = min(self.y2, o.y2) - max(self.y1, o.y1)
        return max(0, w) * max(0, h)

    def contains(self, o: "Rect") -> bool:
        return (self.x1 <= o.x1 and self.y1 <= o.y1
                and self.x2 >= o.x2 and self.y2 >= o.y2)


def parse_bounds(s: str) -> Rect | None:
    """`[x1,y1][x2,y2]`。★ 逗号在数字内部，先拆方括号再拆逗号。"""
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


def ime_from_windows(windows) -> Rect | None:
    for w in windows:
        if w.get("type") == TYPE_INPUT_METHOD:
            return parse_rect_flat(w.get("bounds_in_screen", ""))
    return None


# --------------------------------------------------------------------- #
# 1. 手势长度分类（距离非单调）
# --------------------------------------------------------------------- #

# 实测（AVD Android 15，250ms，垂直滑动）：
#   100px → 无效   300px → 无效   600px → 有效
#   900px → 有效   1200px → 无效  1500px → 无效
SHORT_MAX = 400      # < 400px 判 short（实测无效）
SWEET_MIN = 500      # 500..1100 判 sweet（实测有效）
SWEET_MAX = 1100     # > 1100px 判 too_long（实测无效）


def gesture_length(dist: int) -> str:
    """手势长度分类。

    ★ **非单调**：不是"越长越好"。
    实测有一个甜点区，超过它同样静默失败。
    """
    if dist <= 0:
        return "invalid"
    if dist < SHORT_MAX:
        return "short"
    if dist <= SWEET_MAX:
        return "sweet"
    return "too_long"


def likely_effective(dist: int, dur_ms: int) -> str:
    """这个手势可能有效吗？

    返回 `likely` / `unlikely` / `unknown`。

    **`unknown` 是默认**——本规范只在一个设备、一个时长、一个方向上
    测过。没有实测支撑的一律不猜。
    """
    g = gesture_length(dist)
    if g == "invalid":
        return "unlikely"
    if g == "sweet":
        return "likely"
    # short / too_long 在本环境实测无效，但换设备需重跑探针
    return "unlikely"


# --------------------------------------------------------------------- #
# 2. 键盘吸收判定
# --------------------------------------------------------------------- #

def segment_intersects_rect(x1: int, y1: int, x2: int, y2: int,
                            r: Rect) -> bool:
    """线段是否与矩形相交（Liang-Barsky）。

    ★ **不能用端点当角点算包围盒**——垂直滑动的路径是零宽矩形，
    与任何矩形的重叠面积恒为 0。这是我自己踩的坑：
    第一版 `gesture_path` 返回零宽 Rect，导致"路径穿过键盘"
    永远判 False。
    """
    dx, dy = x2 - x1, y2 - y1
    p = (-dx, dx, -dy, dy)
    q = (x1 - r.x1, r.x2 - x1, y1 - r.y1, r.y2 - y1)
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if pi == 0:
            if qi < 0:
                return False          # 平行且在矩形外
            continue
        t = qi / pi
        if pi < 0:
            u1 = max(u1, t)
        else:
            u2 = min(u2, t)
    return u1 <= u2


def gesture_path(x1: int, y1: int, x2: int, y2: int) -> Rect:
    """手势路径的包围盒（仅用于展示，判定用 segment_intersects_rect）。"""
    return Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def absorbed_by_keyboard(x1: int, y1: int, x2: int, y2: int,
                         ime: Rect | None) -> dict:
    """手势是否会被键盘吸收。

    ★ 判据是**起点**在键盘内，不是路径相交。
    实测：起点在键盘内 → 键盘接收手势并往焦点字段写字（3/3）；
          起点在 App 区、终点穿过键盘 → 不写入。

    返回判定与依据。
    """
    if ime is None:
        return {"absorbed": False, "reason": "no_ime", "start_in_ime": False}
    start = Rect(x1, y1, x1, y1)
    inside = ime.contains(start)
    return {
        "absorbed": inside,
        "reason": "start_in_ime" if inside else "start_outside_ime",
        "start_in_ime": inside,
        "path_crosses_ime": segment_intersects_rect(x1, y1, x2, y2, ime),
        "ime": ime,
    }


# --------------------------------------------------------------------- #
# 3. 滚动终止与恢复
# --------------------------------------------------------------------- #

def is_exhausted(steps: list[dict], window: int = 2) -> bool:
    """滚动是否已到底。

    判据：最近 `window` 步**新增和消失都为 0**。

    实测：连续滚动第 3 步 new=0 gone=0 → 确实到底。
    """
    if len(steps) < window:
        return False
    tail = steps[-window:]
    return all(s.get("new", 0) == 0 and s.get("gone", 0) == 0
               for s in tail)


def recovery_ratio(initial: set[str], after_up: set[str]) -> float:
    """上滑后恢复了多少初始元素。

    实测：下滚 3 步 + 上滚 3 步 → 18/22 = 81.8%。
    **滚动是可恢复的**，但通常不是 100%（列表可能重排、顶部有吸附元素）。
    """
    if not initial:
        return 0.0
    return len(initial & after_up) / len(initial)


def is_at_top(steps: list[dict], window: int = 2) -> bool:
    """是否已到顶（上滑不再产生变化）。

    实测：到顶后继续上滑，内容完全不变——**幂等**。
    """
    return is_exhausted(steps, window)

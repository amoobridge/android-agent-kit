"""swipefind 实验 5：精确定位 swipe 时长阈值 + 距离依赖 + 键盘区起点。

已知 ≤200ms 无效、≥300ms 有效。本实验：
  A) 在 200~300ms 之间二分定位阈值
  B) 固定时长改距离，看阈值是否随距离变
  C) 起点落在键盘区（blindspot 场景）会怎样
"""

from __future__ import annotations

import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.probe_swipe import cap, reset_home, sh, sig, swipe, texts  # noqa


def count_change(b: ET.Element, a: ET.Element) -> tuple[int, int]:
    tb, ta = set(texts(b)), set(texts(a))
    return len(ta - tb), len(tb - ta)


def reset_to_top() -> ET.Element | None:
    """可靠的复位：回启动器再进设置，而不是 am start + BACK。"""
    sh("input", "keyevent", "KEYCODE_HOME")
    time.sleep(1.5)
    sh("am", "start", "-a", "android.settings.SETTINGS")
    time.sleep(2.5)
    return cap()


def exp_a_threshold() -> list[dict]:
    print("=" * 72)
    print("实验 5A · 二分定位时长阈值（距离固定 1800→600）")
    print("=" * 72)
    rows = []
    for d in (200, 220, 240, 260, 280, 300):
        reset_to_top()
        b = cap()
        if b is None:
            continue
        swipe(540, 1800, 540, 600, d)
        a = cap()
        if a is None:
            continue
        new, gone = count_change(b, a)
        rows.append({"dur_ms": d, "new": new, "gone": gone,
                     "effective": new + gone >= 3})
        print(f"  {d:4}ms  新增 {new:3}  消失 {gone:3}  "
              f"{'✅ 有效' if new+gone >= 3 else '❌ 无效'}")
    return rows


def exp_b_distance() -> list[dict]:
    print()
    print("=" * 72)
    print("实验 5B · 阈值是否随距离变（时长固定 250ms）")
    print("=" * 72)
    rows = []
    for (y1, y2, label) in ((1800, 1700, "100px"),
                            (1800, 1500, "300px"),
                            (1800, 1200, "600px"),
                            (1800, 900, "900px"),
                            (1800, 600, "1200px"),
                            (1800, 300, "1500px")):
        reset_to_top()
        b = cap()
        if b is None:
            continue
        swipe(540, y1, 540, y2, 250)
        a = cap()
        if a is None:
            continue
        new, gone = count_change(b, a)
        rows.append({"dist": label, "new": new, "gone": gone,
                     "effective": new + gone >= 3})
        print(f"  距离 {label:6}  新增 {new:3}  消失 {gone:3}  "
              f"{'✅ 有效' if new+gone >= 3 else '❌ 无效'}")
    return rows


def exp_c_from_keyboard() -> list[dict]:
    print()
    print("=" * 72)
    print("实验 5C · 起点落在键盘区（blindspot 场景）")
    print("=" * 72)
    sh("am", "start", "-a", "android.settings.APP_SEARCH_SETTINGS")
    time.sleep(2.5)
    sh("input", "tap", "530", "230")
    time.sleep(2.0)
    sh("am", "broadcast", "-a", "com.textin.refapp.SET_TEXT",
       "--es", "text_b64", "bmV0")
    time.sleep(3.0)
    kb = sh("dumpsys", "input_method").strip()
    shown = "mInputShown=true" in kb
    print(f"  键盘弹起: {shown}")

    b = cap()
    if b is None:
        return []
    tb = set(texts(b))
    # 起点 (540,2000) 在键盘区内，终点 (540,1000)
    swipe(540, 2000, 540, 1000, 400)
    a = cap()
    if a is None:
        return []
    ta = set(texts(a))
    new, gone = len(ta - tb), len(tb - ta)
    still = "mInputShown=true" in sh("dumpsys", "input_method")
    row = {"keyboard_up": shown, "start_in_keyboard": True,
           "new": new, "gone": gone, "keyboard_still_up": still}
    print(f"  从键盘区起滑（400ms）→ 新增 {new}  消失 {gone}  "
          f"键盘仍在: {still}")
    print(f"  ★ {'滚动发生了' if new+gone >= 3 else '滚动没发生'}")

    # 对照：起点在 App 区
    reset_to_top()
    b2 = cap()
    swipe(540, 1400, 540, 400, 400)
    a2 = cap()
    if b2 is not None and a2 is not None:
        n2, g2 = count_change(b2, a2)
        print(f"  对照（起点在 App 区 1400→400）→ 新增 {n2}  消失 {g2}")
        row["control_new"] = n2
        row["control_gone"] = g2
    return [row]


def main() -> int:
    out = {}
    out["threshold"] = exp_a_threshold()
    out["distance"] = exp_b_distance()
    out["from_keyboard"] = exp_c_from_keyboard()
    f = ROOT = Path(__file__).resolve().parent.parent / "data" / \
        "swipe_experiments.json"
    prev = {}
    if f.exists():
        try:
            prev = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    prev.update(out)
    f.write_text(json.dumps(prev, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    print(f"\n已存证 → {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

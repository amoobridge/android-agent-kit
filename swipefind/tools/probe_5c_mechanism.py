"""swipefind 实验 6：验证 5C 的机制。

5C 观察到：从键盘区起滑（540,2000)→(540,1000) 400ms → 新增 13 消失 2，
而对照（540,1400)→(540,400) → 0 0。
两个候选解释必须分开：
  H1  滑动手势把键盘划掉了，露出更多 App 内容
  H2  搜索 Results 列表本身很长，键盘区的起滑真的滚动了它
判据：滑完之后键盘还在不在、App 窗口 bounds 变不变。
"""

from __future__ import annotations

import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.probe_swipe import cap, sh, sig, swipe, texts  # noqa


def ime_shown() -> bool:
    return "mInputShown=true" in sh("dumpsys", "input_method")


def focus() -> bool:
    out = sh("dumpsys", "window")
    return "InputMethod" in out and "mCurrentFocus" in out


def main() -> int:
    print("=" * 72)
    print("实验 6 · 验证 5C 机制：划掉键盘 vs 滚动列表")
    print("=" * 72)

    sh("am", "start", "-a", "android.settings.APP_SEARCH_SETTINGS")
    time.sleep(2.5)
    sh("input", "tap", "530", "230")
    time.sleep(2.0)
    sh("am", "broadcast", "-a", "com.textin.refapp.SET_TEXT",
       "--es", "text_b64", "bmV0")
    time.sleep(3.0)

    b = cap()
    assert b is not None
    tb = set(texts(b))
    kb0 = ime_shown()
    print(f"\n滑前：键盘={kb0}  文本数={len(tb)}")
    print(f"      前 6 条: {[t[:28] for t in texts(b)[:6]]}")

    swipe(540, 2000, 540, 1000, 400)
    a = cap()
    assert a is not None
    ta = set(texts(a))
    kb1 = ime_shown()
    print(f"滑后：键盘={kb1}  文本数={len(ta)}  新增={len(ta-tb)}  消失={len(tb-ta)}")
    print(f"      前 6 条: {[t[:28] for t in texts(a)[:6]]}")
    print(f"      ★ 键盘{'被划掉了' if kb0 and not kb1 else '仍在'}")
    if kb1:
        print("      → H2：键盘没掉，是列表真的滚动了")
    else:
        print("      → H1：键盘被划掉，露出更多 App 内容")

    # 再滑一次，看是否还能滚（H2 应继续滚，H1 应无更多内容）
    swipe(540, 2000, 540, 1000, 400)
    c = cap()
    if c is not None:
        tc = set(texts(c))
        print(f"\n再滑一次：新增={len(tc-ta)}  消失={len(ta-tc)}  键盘={ime_shown()}")
        if len(tc - ta) > 0:
            print("      → 支持 H2（列表可继续滚动）")

    # 对照实验：同样手势但起点在 App 区（键盘上方）
    print("\n--- 对照：起点在 App 区，终点也避开键盘 ---")
    sh("am", "start", "-a", "android.settings.APP_SEARCH_SETTINGS")
    time.sleep(2.5)
    sh("input", "tap", "530", "230")
    time.sleep(2.0)
    sh("am", "broadcast", "-a", "com.textin.refapp.SET_TEXT",
       "--es", "text_b64", "bmV0")
    time.sleep(3.0)
    b2 = cap()
    assert b2 is not None
    tb2 = set(texts(b2))
    # 键盘从 1517 开始；起点 1400 终点 400，完全在 App 区
    swipe(540, 1400, 540, 400, 400)
    a2 = cap()
    assert a2 is not None
    ta2 = set(texts(a2))
    print(f"  对照滑后：新增={len(ta2-tb2)}  消失={len(tb2-ta2)}  键盘={ime_shown()}")
    print(f"      前 6 条: {[t[:28] for t in texts(a2)[:6]]}")

    # 关键判别：列表到底有多长
    print("\n--- 列表长度判别：一路下滚看能滚几步 ---")
    n = 0
    prev = cap()
    for i in range(12):
        swipe(540, 1700, 540, 900, 400)
        time.sleep(1.0)
        cur = cap()
        if prev is None or cur is None:
            break
        if sig(cur) == sig(prev):
            break
        n += 1
        prev = cur
    print(f"  可滚动步数: {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

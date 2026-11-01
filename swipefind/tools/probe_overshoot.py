"""swipefind 实验 4：验证"滚过头不可恢复"是不是真的。

实验 3 得出 restored=0/6，这违反直觉。必须先排除装置问题再下结论：
  A) 上滑手势本身有效吗？
  B) 初始 6 条文本的采集方式对吗？
  C) 是真的回不去，还是回到了别的位置？
"""

from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.probe_swipe import cap, reset_home, sh, sig, swipe, texts  # noqa


def main() -> int:
    print("=" * 72)
    print("实验 4 · 验证 overshoot 不可恢复（排除装置问题）")
    print("=" * 72)

    reset_home()
    b = cap()
    assert b is not None
    t0 = texts(b)
    print(f"\n[A] 初始前 8 条文本:")
    for i, t in enumerate(t0[:8]):
        print(f"     {i}. {t[:50]!r}")

    # B) 上滑一次，看是否有效
    print("\n[B] 上滑一次（600→1800, 300ms）")
    swipe(540, 600, 540, 1800, 300)
    u1 = cap()
    assert u1 is not None
    print(f"     变化: {sig(u1) != sig(b)}  前 8 条:")
    for i, t in enumerate(texts(u1)[:8]):
        print(f"     {i}. {t[:50]!r}")

    # C) 下滚 3 步再上滚 3 步，看是否回到原点
    print("\n[C] 下滚 3 步 → 上滚 3 步")
    for _ in range(3):
        swipe(540, 1800, 540, 600, 300)
    d = cap()
    assert d is not None
    print(f"     下滚 3 步后前 5 条: {[t[:30] for t in texts(d)[:5]]}")
    for _ in range(3):
        swipe(540, 600, 540, 1800, 300)
    r = cap()
    assert r is not None
    tr = texts(r)
    print(f"     上滚 3 步后前 5 条: {[t[:30] for t in tr[:5]]}")
    back = set(t0) & set(tr)
    print(f"     ★ 恢复的初始元素: {len(back)}/{len(t0)}")

    # D) 上滚 10 步（远超下滚步数），看能否到顶
    print("\n[D] 再上滚 10 步，看能否到顶")
    for _ in range(10):
        swipe(540, 600, 540, 1800, 300)
    t = cap()
    assert t is not None
    tt = texts(t)
    back2 = set(t0) & set(tt)
    print(f"     前 5 条: {[x[:30] for x in tt[:5]]}")
    print(f"     ★ 恢复的初始元素: {len(back2)}/{len(t0)}")
    print(f"     与上滚 3 步后相同: {sig(t) == sig(r)}")

    # E) 用 scroll 命令而非 swipe 试试
    print("\n[E] 用 input scroll / keyevent 对比")
    sh("input", "keyevent", "KEYCODE_PAGE_UP")
    time.sleep(1.5)
    k = cap()
    if k is not None:
        print(f"     PAGE_UP 后前 5 条: {[x[:30] for x in texts(k)[:5]]}")
        print(f"     恢复的初始元素: {len(set(t0) & set(texts(k)))}/{len(t0)}")
    sh("input", "scroll")     # 无参数 = 默认方向
    time.sleep(1.5)
    k2 = cap()
    if k2 is not None:
        print(f"     input scroll 后前 5 条: {[x[:30] for x in texts(k2)[:5]]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

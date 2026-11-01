"""swipefind 实验 7：确认"键盘区起滑会被键盘吸收并写入文本"。

实验 6 观察到 net → "net by"。这是 blindspot  tap 发现的手势版，
且可能更糟（一次滑动能写入多个字符）。必须干净复现一次。
"""

from __future__ import annotations

import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.probe_swipe import cap, sh, texts  # noqa


def setup() -> ET.Element | None:
    sh("am", "start", "-a", "android.settings.APP_SEARCH_SETTINGS")
    time.sleep(2.5)
    sh("input", "tap", "530", "230")
    time.sleep(2.0)
    sh("am", "broadcast", "-a", "com.textin.refapp.SET_TEXT",
       "--es", "text_b64", "bmV0")     # base64("net")
    time.sleep(3.0)
    return cap()


def field(root: ET.Element) -> str | None:
    for n in root.iter("node"):
        if n.get("bounds") == "[126,136][933,325]":
            return n.get("text")
    return None


def main() -> int:
    print("=" * 72)
    print("实验 7 · 键盘区起滑会被吸收并写入文本（干净复现）")
    print("=" * 72)

    rows = []
    trials = [
        ("键盘区垂直上滑", 540, 2000, 540, 1000, 400),
        ("键盘区斜滑",     700, 2100, 380, 1200, 400),
        ("键盘区短滑",     540, 1900, 540, 1600, 400),
    ]
    for label, x1, y1, x2, y2, d in trials:
        b = setup()
        assert b is not None
        t0 = field(b)
        kb0 = "mInputShown=true" in sh("dumpsys", "input_method")
        sh("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(d))
        time.sleep(2.5)
        a = cap()
        assert a is not None
        t1 = field(a)
        kb1 = "mInputShown=true" in sh("dumpsys", "input_method")
        changed = t0 != t1
        rows.append({"label": label, "before": t0, "after": t1,
                     "keyboard_before": kb0, "keyboard_after": kb1,
                     "field_changed": changed})
        print(f"\n[{label}] ({x1},{y1})→({x2},{y2}) {d}ms")
        print(f"  字段: {t0!r} → {t1!r}   "
              f"{'★ 被键盘吸收并写入' if changed else '未变'}")
        print(f"  键盘: {kb0} → {kb1}")

    # 对照：完全在 App 区的滑动
    b = setup()
    assert b is not None
    t0 = field(b)
    sh("input", "swipe", "540", "1400", "540", "400", "400")
    time.sleep(2.5)
    a = cap()
    assert a is not None
    t1 = field(a)
    print(f"\n[对照 · App 区滑动] (540,1400)→(540,400)")
    print(f"  字段: {t0!r} → {t1!r}   "
          f"{'★ 也被写入' if t0 != t1 else '未变（正确：滑动滚动列表）'}")

    f = Path(__file__).resolve().parent.parent / "data" / \
        "keyboard_swipe.json"
    f.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    print(f"\n已存证 → {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

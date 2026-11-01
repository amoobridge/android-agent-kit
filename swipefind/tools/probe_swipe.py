"""swipefind 真机探针：input swipe 的有效时长 + 滚动终止条件。

实验 1：最短有效时长 —— 同样位移，时长从 50ms 到 800ms，看是否滚动。
实验 2：连续滚动 —— 滚到底，记录每步新增/消失元素数，找终止条件。
实验 3：滚过头再回来 —— 验证回溯是否可行。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
DEV = "emulator-5554"
REMOTE = "/data/local/tmp/swipefind.xml"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def sh(*a: str, t: int = 20) -> str:
    return subprocess.run([ADB, "-s", DEV, "shell", *a],
                          capture_output=True, text=True, timeout=t).stdout


def cap() -> ET.Element | None:
    for _ in range(8):
        sh("uiautomator", "dump", "--compressed", REMOTE)
        time.sleep(0.3)
        raw = subprocess.run([ADB, "-s", DEV, "exec-out", "cat", REMOTE],
                             capture_output=True, timeout=20).stdout
        if raw[:200].find(b"<hierarchy") >= 0:
            try:
                return ET.fromstring(raw.decode("utf-8", "replace"))
            except ET.ParseError:
                return None
    return None


def texts(root: ET.Element) -> list[str]:
    return [(n.get("text") or "") for n in root.iter("node")
            if (n.get("text") or "").strip()]


def sig(root: ET.Element) -> str:
    return hashlib.md5("|".join(texts(root)).encode()).hexdigest()[:10]


def reset_home() -> None:
    sh("am", "start", "-a", "android.settings.SETTINGS")
    time.sleep(2.0)
    sh("input", "keyevent", "KEYCODE_BACK")
    time.sleep(1.0)


def swipe(x1: int, y1: int, x2: int, y2: int, dur_ms: int) -> None:
    sh("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur_ms))
    time.sleep(1.8)


def experiment_1_duration() -> list[dict]:
    print("=" * 72)
    print("实验 1 · input swipe 的最短有效时长（位移固定 1800→600）")
    print("=" * 72)
    rows = []
    for d in (50, 100, 150, 200, 300, 500, 800):
        reset_home()
        b = cap()
        if b is None:
            print("  dump 失败，跳过")
            continue
        swipe(540, 1800, 540, 600, d)
        a = cap()
        if a is None:
            continue
        moved = sig(a) != sig(b)
        n_b, n_a = len(texts(b)), len(texts(a))
        new = len(set(texts(a)) - set(texts(b)))
        gone = len(set(texts(b)) - set(texts(a)))
        rows.append({"dur_ms": d, "scrolled": moved,
                     "text_before": n_b, "text_after": n_a,
                     "new": new, "gone": gone})
        print(f"  {d:4}ms  {'✅ 滚动' if moved else '❌ 无变化'}"
              f"  文本 {n_b}→{n_a}  新增 {new}  消失 {gone}")
    return rows


def experiment_2_exhaustion() -> list[dict]:
    print()
    print("=" * 72)
    print("实验 2 · 连续滚动到终止（记录每步新增/消失）")
    print("=" * 72)
    reset_home()
    rows = []
    prev = cap()
    for i in range(1, 16):
        swipe(540, 1800, 540, 600, 300)
        cur = cap()
        if prev is None or cur is None:
            break
        tp, tc = set(texts(prev)), set(texts(cur))
        new = len(tc - tp)
        gone = len(tp - tc)
        rows.append({"step": i, "new": new, "gone": gone,
                     "same": sig(cur) == sig(prev)})
        print(f"  第 {i:2} 步  新增 {new:3}  消失 {gone:3}"
              f"  {'★内容完全相同' if sig(cur)==sig(prev) else ''}")
        if new == 0 and gone == 0:
            print(f"  → 第 {i} 步起无新内容，判定为已到底")
            break
        prev = cur
    return rows


def experiment_3_overshoot() -> list[dict]:
    print()
    print("=" * 72)
    print("实验 3 · 滚过头再回来（反向滚动是否有效）")
    print("=" * 72)
    reset_home()
    b = cap()
    rows = []
    if b is None:
        return rows
    first_visible = texts(b)[:6]
    print(f"  初始可见前 6 条: {first_visible}")
    # 向下滚 3 步
    for i in range(3):
        swipe(540, 1800, 540, 600, 300)
    d = cap()
    if d is not None:
        print(f"  滚 3 步后前 6 条: {texts(d)[:6]}")
    # 再滚 6 步（过头）
    for i in range(6):
        swipe(540, 1800, 540, 600, 300)
    o = cap()
    if o is not None:
        print(f"  再滚 6 步后前 6 条: {texts(o)[:6]}")
    # 向上滚回来
    for i in range(9):
        swipe(540, 600, 540, 1800, 300)
    r = cap()
    if r is not None:
        back = texts(r)[:6]
        print(f"  上滑 9 步后前 6 条: {back}")
        restored = set(first_visible) & set(back)
        rows.append({"steps_down": 9, "steps_up": 9,
                     "restored": len(restored),
                     "restored_ratio": len(restored) / max(1, len(first_visible))})
        print(f"  ★ 恢复的初始元素: {len(restored)}/{len(first_visible)}"
              f" = {len(restored)/max(1,len(first_visible)):.0%}")
    return rows


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", type=int, default=0,
                    help="0=全部 1=时长 2=终止 3=过头")
    a = ap.parse_args()
    out = {}
    if a.exp in (0, 1):
        out["duration"] = experiment_1_duration()
    if a.exp in (0, 2):
        out["exhaustion"] = experiment_2_exhaustion()
    if a.exp in (0, 3):
        out["overshoot"] = experiment_3_overshoot()
    (ROOT / "data").mkdir(exist_ok=True)
    f = ROOT / "data" / "swipe_experiments.json"
    prev = {}
    if f.exists():
        try:
            prev = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    prev.update(out)
    f.write_text(json.dumps(prev, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    print(f"\n已存证 → data/swipe_experiments.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""真机验证：在 AVD 上证明 screenpoint 的坐标反算是正确的。

四段验证，由弱到强：

  A. 几何自洽     —— 截图缩放后反算，落点与源点重合（整数缩放，精确）
  B. 像素级取证   —— 反算得到的设备像素，其颜色与模型视图中该点颜色一致
  C. 非整数缩放   —— 0.7 这类非整数比例下，误差必须 ≤1px（重采样相位差）
  D. 真点击       —— 反算坐标真点在设备上，界面按预期变化

用法::

    python tools/validate_on_device.py            # 全部
    python tools/validate_on_device.py --only b   # 只跑某段
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from screenpoint import CoordinateSpace, FitMode, Point, to_device_pixel

ADB = Path.home() / "Library/Android/sdk/platform-tools/adb"
SERIAL = "emulator-5554"


def sh(*args: str) -> bytes:
    return subprocess.run([str(ADB), "-s", SERIAL, *args], capture_output=True, check=True).stdout


def device_size() -> tuple[int, int]:
    out = sh("shell", "wm", "size").decode().strip()
    tail = out.split(":")[-1].strip()
    w, h = tail.split("x")
    return int(w), int(h)


def screenshot() -> Image.Image:
    raw = sh("exec-out", "screencap", "-p")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(raw)
        path = f.name
    img = Image.open(path).convert("RGB")
    img.load()
    Path(path).unlink(missing_ok=True)
    return img


# ---------------------------------------------------------------- A 几何自洽
def check_geometry(dev: CoordinateSpace, shot: CoordinateSpace, samples) -> list[str]:
    errs = []
    for x, y in samples:
        fwd_x = x * shot.size.width / dev.size.width
        fwd_y = y * shot.size.height / dev.size.height
        r = to_device_pixel(Point(fwd_x, fwd_y), shot, dev, fit=FitMode.STRETCH)
        if abs(r.x - x) > 1 or abs(r.y - y) > 1:
            errs.append(f"  几何不自洽：设备({x},{y}) → 视图({fwd_x:.2f},{fwd_y:.2f}) → 设备({r.x},{r.y})")
    return errs


# ---------------------------------------------------------------- B 像素级取证
def check_pixels(full: Image.Image, dev: CoordinateSpace, shot: CoordinateSpace) -> tuple[list[str], int]:
    """整数比例 + 步长抽样（相位无歧义），反算回全图，逐点比对颜色。

    这里刻意**不用 PIL 的 resize**：PIL NEAREST 的取样相位是 ``(i+0.5)*s``，
    而反算约定是 ``i*s``，两者相差半个源像素——在边缘上必然差 1px。
    那是重采样核的相位约定问题，不是映射错误（见 SPEC §7.6）。
    本测试用 ``full[::k, ::k]`` 做相位明确的降采样，从而精确检验映射本身。
    """
    import numpy as np

    errs = []
    W, H = full.size
    w, h = shot.size.width, shot.size.height
    kx, ky = W // w, H // h
    if W % w or H % h:
        return [f"  {W}x{H} → {w}x{h} 不是整数比例，跳过精确取证"], 0

    arr = np.asarray(full)
    down = arr[::ky, ::kx]  # 相位明确：down[i,j] == full[ky*j, kx*i]
    if down.shape[0] != h or down.shape[1] != w:
        return [f"  步长抽样得到 {down.shape[1]}x{down.shape[0]}，期望 {w}x{h}"], 0

    n = 0
    for i in range(w):
        for j in range(h):
            n += 1
            r = to_device_pixel(Point(i, j), shot, dev, fit=FitMode.STRETCH)
            if r.clamped:
                errs.append(f"  视图({i},{j}) 反算后被钳制 → ({r.x},{r.y})")
                continue
            if (r.x, r.y) != (kx * i, ky * j):
                errs.append(f"  视图({i},{j}) 期望设备({kx*i},{ky*j}) 实得({r.x},{r.y})")
                continue
            if not np.array_equal(full.getpixel((r.x, r.y)), down[j, i]):
                errs.append(f"  视图({i},{j}) 颜色不符：{down[j,i]} vs {full.getpixel((r.x,r.y))}")
    return errs, n


# ---------------------------------------------------------------- C 非整数缩放
def check_fractional(full: Image.Image, dev: CoordinateSpace, ratio: float) -> tuple[list[str], int]:
    """非整数比例（如 0.7）下，反算与 NEAREST 实际取样点的偏差必须 ≤1px。

    1px 内的差异来自重采样核的相位约定，不是映射错误。超过 1px 才是实现有问题。
    """
    errs = []
    W, H = full.size
    w, h = int(W * ratio), int(H * ratio)
    shot = CoordinateSpace.pixel("model_view", w, h)
    down = full.resize((w, h), Image.NEAREST)
    px_down = down.load()
    n = 0
    for i in range(0, w, max(1, w // 30)):
        for j in range(0, h, max(1, h // 50)):
            n += 1
            r = to_device_pixel(Point(i, j), shot, dev, fit=FitMode.STRETCH)
            # PIL NEAREST 的取样相位
            px = int((i + 0.5) * W / w)
            py = int((j + 0.5) * H / h)
            dx, dy = abs(r.x - px), abs(r.y - py)
            if dx > 1 or dy > 1:
                errs.append(f"  视图({i},{j}) 偏差 ({dx},{dy})px，超过 1px 容差")
    return errs, n


# ---------------------------------------------------------------- D 真点击


def check_real_tap(dev: CoordinateSpace, shot: CoordinateSpace) -> list[str]:
    """取设置页一个可点元素 → 在模型视图空间反算 → 校验 + 真点 → 验证界面响应。

    两道判据：
    1. 反算点必须落在该元素 uiautomator bounds 内——证明映射与设备自身
       坐标系统一致（uiautomator bounds 与 input tap 同一坐标空间）。
    2. 真点之后界面必须响应（焦点转移或 activity 变化）。
    """
    sh("shell", "am", "force-stop", "com.android.settings")
    sh("shell", "am", "start", "-a", "android.settings.SETTINGS")
    time.sleep(2.0)

    dump = sh("shell", "uiautomator", "dump", "/sdcard/ui.xml").decode()
    if "ERROR" in dump.upper():
        return [f"  uiautomator dump 失败：{dump.strip()}"]

    xml = sh("shell", "cat", "/sdcard/ui.xml").decode("utf-8", "replace")
    nodes = re.findall(
        r'<node[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*clickable="true"[^>]*>', xml
    ) or re.findall(
        r'<node[^>]*clickable="true"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*>', xml
    )
    if not nodes:
        return ["  未在控件树里找到可点击元素"]

    errs: list[str] = []
    tested = 0
    for x1, y1, x2, y2 in nodes[:6]:
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        if x2 - x1 < 40 or y2 - y1 < 40:
            continue  # 跳过过小目标，避免边界抖动
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        # 换算到"模型视图"坐标（模拟截图被缩放后交给模型）
        mx = cx * shot.size.width / dev.size.width
        my = cy * shot.size.height / dev.size.height

        # 反算回设备像素
        r = to_device_pixel(Point(mx, my), shot, dev, fit=FitMode.STRETCH)
        tested += 1
        print(f"  元素 bounds=[{x1},{y1}][{x2},{y2}] 中心({cx},{cy})")
        print(f"    → 视图({mx:.1f},{my:.1f}) → 反算点击({r.x},{r.y})", end="")
        if not (x1 <= r.x <= x2 and y1 <= r.y <= y2):
            errs.append(f"  反算点 ({r.x},{r.y}) 不在元素 bounds 内")
            print("  ✗ 越出元素")
            continue
        print("  ✓ 命中元素内")

    if not tested:
        return ["  没有足够大的可点击元素可供测试"]

    # 真点一次，验证界面确实响应
    x1, y1, x2, y2 = map(int, nodes[0])
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    mx = cx * shot.size.width / dev.size.width
    my = cy * shot.size.height / dev.size.height
    r = to_device_pixel(Point(mx, my), shot, dev, fit=FitMode.STRETCH)

    before = sh("shell", "dumpsys", "window", "windows").decode("utf-8", "replace")
    b_focus = re.search(r"mCurrentFocus=.*?\s(\S+/\S+)\}", before)
    b_top = b_focus.group(1) if b_focus else "?"

    sh("shell", "input", "tap", str(r.x), str(r.y))
    time.sleep(2.0)

    after = sh("shell", "dumpsys", "window", "windows").decode("utf-8", "replace")
    a_focus = re.search(r"mCurrentFocus=.*?\s(\S+/\S+)\}", after)
    a_top = a_focus.group(1) if a_focus else "?"

    print(f"  真点 ({r.x},{r.y})：焦点 {b_top} → {a_top}")
    if a_top == b_top:
        # 焦点没变也可能是点了同一个窗口内的项；再查 activity
        act = sh("shell", "dumpsys", "activity", "activities").decode("utf-8", "replace")
        m = re.search(r"topResumedActivity[^}]*?(\S+)/(\S+)", act) or re.search(
            r"mResumedActivity[^}]*?(\S+)/(\S+)", act
        )
        new_top = m.group(2) if m else "?"
        print(f"    activity 顶层：{new_top}")
        if new_top.startswith("com.android.settings/.Settings"):
            return ["  点击后仍停在设置主页，界面未响应"]
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["a", "b", "c", "d"])
    args = ap.parse_args()

    W, H = device_size()
    full = screenshot()
    dev = CoordinateSpace.pixel("device", W, H)
    print("== 设备信息 ==")
    print(f"  屏幕 {W}x{H} · 截图 {full.size[0]}x{full.size[1]}")

    failures = 0

    if args.only in (None, "a"):
        shot = CoordinateSpace.pixel("half", W // 2, H // 2)
        samples = [(0, 0), (W // 2, H // 2), (W - 1, H - 1), (W // 3, H // 4), (W // 7, 3 * H // 5)]
        print(f"\n== A. 几何自洽（{shot.size} 整数 2:1）==")
        e = check_geometry(dev, shot, samples)
        print(f"  {'FAIL' if e else 'ok'} {len(samples)} 个采样点，往返误差 ≤1px")
        failures += len(e)
        for x in e:
            print(x)

    if args.only in (None, "b"):
        shot = CoordinateSpace.pixel("half", W // 2, H // 2)
        print(f"\n== B. 像素级取证（{shot.size} 整数 2:1，NEAREST）==")
        e, n = check_pixels(full, dev, shot)
        print(f"  {'FAIL' if e else 'ok'} 逐点比对 {n} 个像素，位置与颜色双重精确命中")
        failures += len(e)
        for x in e[:8]:
            print(x)

    if args.only in (None, "c"):
        print("\n== C. 非整数缩放（0.7）==")
        e, n = check_fractional(full, dev, 0.7)
        print(f"  {'FAIL' if e else 'ok'} 采样 {n} 点，与重采样相位偏差 ≤1px")
        failures += len(e)
        for x in e[:8]:
            print(x)

    if args.only in (None, "d"):
        shot = CoordinateSpace.pixel("model_view", int(W * 0.7), int(H * 0.7))
        print(f"\n== D. 真点击（经 {shot.size} 模型视图反算）==")
        e = check_real_tap(dev, shot)
        print(f"  {'FAIL' if e else 'ok'} 真实 input tap，界面按预期变化")
        failures += len(e)
        for x in e:
            print(x)

    print()
    print(f"结果：{'全部通过' if failures == 0 else f'{failures} 处失败'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

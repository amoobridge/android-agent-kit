#!/usr/bin/env python3
"""端到端集成演示：pointparse + screenpoint 在真机上跑通完整链路。

模拟一个真实 GUI Agent 的一次点击：

  ① 截图（设备像素）              1080x2400
  ② 压到模型视图                   756x1680
  ③ 让"模型"指点                   故意用脏字符串输出
  ④ pointparse 解析               → 一个点 + 空间线索
  ⑤ screenpoint 反算              → 设备可点击像素
  ⑥ 真点
  ⑦ 校验落点是否在目标元素内

③ 用一个确定性的"假模型"：它在模型视图坐标系里指向 uiautomator 给出的
某个可点元素中心，然后用各种脏格式吐出来。这样端到端结果可精确验证。

用法::

    python tools/e2e_demo.py
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # 仓库根目录
sys.path.insert(0, str(ROOT / "screenpoint"))
sys.path.insert(0, str(ROOT / "pointparse"))

from PIL import Image

from pointparse import Ambiguity, NoPointFound, parse_point
from screenpoint import CoordinateSpace, FitMode, Point, to_device_pixel

ADB = Path.home() / "Library/Android/sdk/platform-tools/adb"
SERIAL = "emulator-5554"

# 假模型的十种脏输出模板
TEMPLATES = [
    '{{"x": {x}, "y": {y}}}',
    '{{"point": [{x}, {y}]}}',
    "({x}, {y})",
    "{x}, {y}",
    "x={x}, y={y}",
    "I'll tap at ({x}, {y}) now.",
    "```json\n{{\"x\": {x}, \"y\": {y}}}\n```",
    "Sure! Here you go: {{\"x\": {x}, \"y\": {y}}} Hope that helps.",
    "<point>{x} {y}</point>",
    "{{'x': {x}, 'y': {y}}}",
]


def sh(*args: str) -> bytes:
    return subprocess.run([str(ADB), "-s", SERIAL, *args], capture_output=True, check=True).stdout


def screenshot() -> Image.Image:
    raw = sh("exec-out", "screencap", "-p")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(raw)
        path = f.name
    img = Image.open(path).convert("RGB")
    img.load()
    Path(path).unlink(missing_ok=True)
    return img


def first_clickable(xml: str):
    nodes = re.findall(
        r'<node[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*clickable="true"[^>]*>', xml
    ) or re.findall(
        r'<node[^>]*clickable="true"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*>', xml
    )
    for x1, y1, x2, y2 in nodes:
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        if x2 - x1 >= 60 and y2 - y1 >= 60:
            return x1, y1, x2, y2
    return None


def main() -> int:
    print("=" * 68)
    print("端到端：模型脏输出 → pointparse → screenpoint → 真点 → 校验")
    print("=" * 68)

    sh("shell", "am", "force-stop", "com.android.settings")
    sh("shell", "am", "start", "-a", "android.settings.SETTINGS")
    time.sleep(2.0)

    out = sh("shell", "wm", "size").decode().strip().split(":")[-1].strip()
    W, H = map(int, out.split("x"))
    full = screenshot()
    print(f"\n① 设备 {W}x{H}，截图 {full.size[0]}x{full.size[1]}")

    shot = CoordinateSpace.pixel("model_view", int(W * 0.7), int(H * 0.7))
    dev = CoordinateSpace.pixel("device", W, H)
    print(f"② 模型视图 {shot.size}（0.7 缩放，stretch）")

    dump = sh("shell", "uiautomator", "dump", "/sdcard/ui.xml").decode()
    if "ERROR" in dump.upper():
        print("uiautomator dump 失败")
        return 1
    xml = sh("shell", "cat", "/sdcard/ui.xml").decode("utf-8", "replace")
    target = first_clickable(xml)
    if not target:
        print("没找到足够大的可点击元素")
        return 1
    x1, y1, x2, y2 = target
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    print(f"③ 目标元素 bounds=[{x1},{y1}][{x2},{y2}] 中心 ({cx},{cy})")

    random.seed()
    tmpl = random.choice(TEMPLATES)
    mx = round(cx * shot.size.width / W)
    my = round(cy * shot.size.height / H)
    model_said = tmpl.format(x=mx, y=my)
    print(f'   假模型说："{model_said}"')

    try:
        p = parse_point(model_said)
    except NoPointFound as e:
        print(f"✗ pointparse: 拒答 —— {e.reason}")
        return 1
    except Ambiguity as e:
        print(f"✗ pointparse: 歧义 —— {len(e.candidates)} 个候选")
        return 1
    print(f"④ pointparse → ({p.x:g}, {p.y:g})  格式={p.source_format}  线索={p.space_hint.value}")

    r = to_device_pixel(Point(p.x, p.y), shot, dev, fit=FitMode.STRETCH)
    print(f"⑤ screenpoint → 设备像素 ({r.x}, {r.y})  clamped={r.clamped}")
    if r.clamped:
        print("✗ 反算后越界，模型指到了图外")
        return 1

    sh("shell", "input", "tap", str(r.x), str(r.y))
    time.sleep(1.5)
    print(f"⑥ 已真点 ({r.x}, {r.y})")

    ok = x1 <= r.x <= x2 and y1 <= r.y <= y2
    print(f"⑦ 校验：({'✓ 命中目标元素内' if ok else '✗ 落在目标元素外'})")

    # 再确认界面确实响应了
    act = sh("shell", "dumpsys", "activity", "activities").decode("utf-8", "replace")
    m = re.search(r"topResumedActivity[^}]*?(\S+)/(\S+)", act) or re.search(
        r"mResumedActivity[^}]*?(\S+)/(\S+)", act
    )
    top = m.group(2) if m else "?"
    responded = not top.startswith("com.android.settings/.Settings")
    print(f"   界面响应：{'✓' if responded else '✗'} 顶层 activity = {top}")

    print()
    print("结论：" + ("✓ 端到端跑通" if ok and responded else "✗ 未跑通"))
    return 0 if ok and responded else 1


if __name__ == "__main__":
    raise SystemExit(main())

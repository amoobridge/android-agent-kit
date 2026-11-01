"""imespec 真机探针：同时抓 XML dump 与窗口列表，复算遮挡。

**它做什么**：
  1. 打开一个有输入框的界面
  2. 聚焦 → 键盘弹起
  3. 抓 `AccessibilityWindowInfo`（经 textin/refapp 的 LIST_WINDOWS 广播）
  4. 抓 `uiautomator dump` XML
  5. 用 imespec 复算：多少可点元素被键盘挡住
  6. 存证到 data/，供 CI 复算

用法：
    python tools/probe_ime.py                # 键盘弹起状态
    python tools/probe_ime.py --no-keyboard  # 键盘收起状态（对照）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
DEV = "emulator-5554"
REMOTE = "/data/local/tmp/imespec.xml"
SEARCH = "android.settings.APP_SEARCH_SETTINGS"
APP = "com.textin.refapp"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import audit_xml, ime_from_windows, ime_rect  # noqa: E402


def sh(*a: str, timeout: int = 25) -> subprocess.CompletedProcess:
    return subprocess.run([ADB, "-s", DEV, "shell", *a],
                          capture_output=True, text=True, timeout=timeout)


def exec_out(*a: str) -> bytes:
    return subprocess.run([ADB, "-s", DEV, "exec-out", *a],
                          capture_output=True, timeout=25).stdout


def dump_xml() -> ET.Element | None:
    for _ in range(10):
        sh("uiautomator", "dump", "--compressed", REMOTE)
        time.sleep(0.3)
        raw = exec_out("cat", REMOTE)
        if raw[:200].find(b"<hierarchy") >= 0:
            try:
                return ET.fromstring(raw.decode("utf-8", "replace"))
            except ET.ParseError:
                return None
    return None


def get_windows() -> dict:
    sh("am", "broadcast", "-a", f"{APP}.LIST_WINDOWS")
    time.sleep(1.5)
    raw = exec_out("run-as", APP, "cat", "files/last_windows.json")
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"windows": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-keyboard", action="store_true")
    ap.add_argument("--json", type=str, default="")
    a = ap.parse_args()

    # 前置检查：无障碍服务必须绑上
    out = sh("dumpsys", "accessibility").stdout
    if "Bound services:{}" in out and "textin" not in out:
        print("❌ 无障碍服务未绑定。先执行：")
        print(f"   adb -s {DEV} shell settings put secure \\")
        print(f"       enabled_accessibility_services {APP}/.SetTextService")
        print(f"   adb -s {DEV} shell settings put secure accessibility_enabled 1")
        return 2

    sh("am", "start", "-a", SEARCH)
    time.sleep(2.5)

    if a.no_keyboard:
        sh("input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.5)
    else:
        sh("input", "tap", "530", "230")          # 聚焦 → 键盘弹起
        time.sleep(2.0)
        sh("am", "broadcast", "-a", f"{APP}.SET_TEXT",
           "--es", "text_b64", "bmV0")            # base64("net")
        time.sleep(3.0)

    wins = get_windows()
    root = dump_xml()
    if root is None:
        print("❌ dump 失败")
        return 1

    ime_w = ime_from_windows(wins.get("windows", []))
    ime = ime_rect(ime_w) if ime_w else None
    r = audit_xml(root, ime)

    print()
    print("=" * 68)
    label = "键盘收起" if a.no_keyboard else "键盘弹起"
    print(f"imespec 真机探针 · {label}")
    print("=" * 68)

    if ime:
        print(f"IME 窗口  : {ime_w['title']!r}  "
              f"bounds=[{ime.x1},{ime.y1}][{ime.x2},{ime.y2}]")
        print(f"占屏幕    : {(ime.y2 - ime.y1) / 2400 * 100:.1f}%")
    else:
        print("IME 窗口  : 无（键盘未弹起，或窗口列表不可得）")

    print(f"可点元素  : {r['clickable_count']}")
    print(f"完全遮挡  : {r['occluded_count']}")
    print(f"部分遮挡  : {r['partially_occluded_count']}")
    print(f"不可及    : {r['unreachable_count']}"
          f"（{r['unreachable_ratio']:.1%}）")
    print()
    print("明细：")
    for it in r["items"]:
        mark = {"occluded": "★★完全遮挡", "partially_occluded": "★部分遮挡",
                "reachable": "", "unknown": "（键盘状态未知）"}[it["reachability"]]
        ratio = (f"{it['occlusion_ratio']:6.1%}"
                 if it["occlusion_ratio"] is not None else "  未知")
        print(f"  {it['bounds']:20} {ratio}  {it['text'][:26]!r} {mark}")

    # 存证
    tag = "no_keyboard" if a.no_keyboard else "keyboard_up"
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / f"dump_{tag}.xml").write_bytes(
        ET.tostring(root, encoding="utf-8", xml_declaration=True))
    (ROOT / "data" / f"windows_{tag}.json").write_text(
        json.dumps(wins, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已存证 → data/dump_{tag}.xml, data/windows_{tag}.json")

    if a.json:
        Path(a.json).write_text(json.dumps(r, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(f"已写入 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

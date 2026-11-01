"""blindspot 真机探针：同时抓截图与 XML，复算幻影可点。

**它做什么**：
  1. 打开有输入框的界面，聚焦 → 键盘弹起
  2. 抓 `AccessibilityWindowInfo`（经 textin/refapp 的 LIST_WINDOWS 广播）
  3. 抓 `uiautomator dump` XML
  4. 抓 `screencap` 截图
  5. 用 blindspot 复算：多少 XML 可点元素是幻影
  6. **可选**：真点一个幻影坐标，验证行为后果
  7. 存证到 data/，供 CI 复算
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
REMOTE = "/data/local/tmp/blindspot.xml"
SEARCH = "android.settings.APP_SEARCH_SETTINGS"
APP = "com.textin.refapp"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import cross_check  # noqa: E402


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


def search_field_text(root: ET.Element) -> str | None:
    for n in root.iter("node"):
        if n.get("bounds") == "[126,136][933,325]":
            return n.get("text")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tap-phantom", action="store_true",
                    help="真点一个幻影坐标，验证行为后果")
    a = ap.parse_args()

    out = sh("dumpsys", "accessibility").stdout
    if "Bound services:{}" in out and "textin" not in out:
        print("❌ 无障碍服务未绑定。先执行：")
        print(f"   adb -s {DEV} shell settings put secure \\")
        print(f"       enabled_accessibility_services {APP}/.SetTextService")
        return 2

    sh("am", "start", "-a", SEARCH)
    time.sleep(2.5)
    sh("input", "tap", "530", "230")
    time.sleep(2.0)
    sh("am", "broadcast", "-a", f"{APP}.SET_TEXT", "--es", "text_b64", "bmV0")
    time.sleep(3.0)

    wins = get_windows()
    root = dump_xml()
    if root is None:
        print("❌ dump 失败")
        return 1

    before_text = search_field_text(root)
    exec_out("screencap", "-p", "/sdcard/blindspot.png")
    png = exec_out("cat", "/sdcard/blindspot.png")

    from PIL import Image  # noqa: F401
    import io
    img = Image.open(io.BytesIO(png)).convert("RGB")

    r = cross_check(root, wins.get("windows", []), img)

    print()
    print("=" * 70)
    print("blindspot 真机探针 · XML 的非 App 窗口盲区")
    print("=" * 70)
    print(f"盲区        : {r['blind_regions']}")
    print(f"截图验证    : {r['screenshot_agrees']}"
          f"  （截图是唯一完整通道）")
    print(f"可点元素    : {r['clickable_count']}")
    print(f"幻影可点    : {r['phantom_count']}"
          f"（{r['phantom_ratio']:.1%}）")
    print()
    print("幻影明细：")
    for p in r["phantoms"]:
        print(f"  {p['bounds']:20} 遮挡 {p['occlusion_ratio']:6.1%}"
              f"  {p['text'][:30]!r}")
    print()
    print("截图侧像素统计（盲区 vs App 参考区）：")
    for e in r.get("screenshot_regions", []):
        print(f"  盲区 dominant {e['dominant']} "
              f"({e['dominant_ratio']:.0%})  "
              f"App 参考 dominant {e.get('app_dominant')}  "
              f"相同={e.get('same_as_app')}")

    # ---- 可选：真点幻影 ----
    if a.tap_phantom and r["phantoms"]:
        # 选一个完全被压住的
        full = [p for p in r["phantoms"] if p["occlusion_ratio"] >= 1.0]
        if not full:
            print("\n⚠️ 没有完全遮挡的幻影，跳过行为测试")
            return 0
        t = full[0]["rect"]
        tx, ty = (t.x1 + t.x2) // 2, (t.y1 + t.y2) // 2
        print(f"\n>>> 行为测试：点击幻影 {full[0]['bounds']} 的中心 "
              f"({tx},{ty})")
        print(f"    点击前搜索框 text = {before_text!r}")
        sh("input", "tap", str(tx), str(ty))
        time.sleep(2.5)
        root2 = dump_xml()
        after_text = search_field_text(root2) if root2 is not None else None
        print(f"    点击后搜索框 text = {after_text!r}")
        if before_text != after_text:
            print("    ★★ 点击落在键盘上，向 App 写入了数据。")
            print("       XML 声称的目标未被触发——静默状态污染。")
        else:
            print("    搜索框未变（可能该位置不是字符键）")

    # 存证
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "dump_before_tap.xml").write_bytes(
        ET.tostring(root, encoding="utf-8", xml_declaration=True))
    (ROOT / "data" / "windows_keyboard_up.json").write_text(
        json.dumps(wins, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "data" / "screencap_keyboard_up.png").write_bytes(png)
    print(f"\n已存证 → data/（dump_before_tap.xml, "
          f"windows_keyboard_up.json, screencap_keyboard_up.png）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

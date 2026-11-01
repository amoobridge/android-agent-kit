#!/usr/bin/env python3
"""从 AVD 抓取真实 uiautomator dump，作为 uidref 的黄金向量素材。

刻意覆盖不同界面形态，因为降噪规则必须在所有形态上都不丢可交互元素：
  长列表 / 带开关的表单 / 数字键盘 / 弹窗 / 键盘弹起 / 桌面网格 / 相机
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

ADB = Path.home() / "Library/Android/sdk/platform-tools/adb"
SERIAL = "emulator-5554"
OUT = Path(__file__).resolve().parent.parent / "dumps"

# (名字, 启动 intent, 额外准备 shell 命令)
SCREENS = [
    ("settings-main",    "am start -a android.settings.SETTINGS", []),
    ("settings-display", "am start -a android.settings.DISPLAY_SETTINGS", []),
    ("settings-sound",   "am start -a android.settings.SOUND_SETTINGS", []),
    ("settings-battery", "am start -a android.intent.action.POWER_USAGE_SUMMARY", []),
    ("settings-apps",    "am start -a android.settings.APPLICATION_SETTINGS", []),
    ("settings-storage", "am start -a android.settings.INTERNAL_STORAGE_SETTINGS", []),
    ("settings-a11y",    "am start -a android.settings.ACCESSIBILITY_SETTINGS", []),
    ("settings-security","am start -a android.settings.SECURITY_SETTINGS", []),
    ("settings-lang",    "am start -a android.settings.LOCALE_SETTINGS", []),
    ("contacts",         "am start -n com.google.android.contacts/com.android.contacts.activities.PeopleActivity", []),
    ("calendar",         "am start -n com.google.android.calendar/com.android.calendar.AllInOneActivity", []),
    ("launcher",         "am start -n com.google.android.apps.nexuslauncher/.NexusLauncherActivity", []),
    ("camera",           "am start -n com.android.camera2/com.android.camera.CameraLauncher", []),
    ("settings-device",  "am start -a android.settings.DEVICE_INFO_SETTINGS", []),
    ("settings-search",  "am start -a android.settings.SETTINGS", ["input keyevent 82"]),
    ("dialog-longpress", "am start -a android.settings.DATE_SETTINGS", ["input swipe 540 1200 540 400 300"]),
]


def sh(*args: str) -> str:
    return subprocess.run(
        [str(ADB), "-s", SERIAL, "shell", *args],
        capture_output=True, text=True, timeout=60,
    ).stdout


def dump(name: str) -> tuple[bool, str]:
    # 先试 --compressed：AVD 长时间运行后不带压缩会被 OOM Kill
    # （输出 Killed、不产文件、也不返回非零码）。详见 http_api.capture_via_adb。
    remote = "/data/local/tmp/_uidref_cap.xml"
    xml = ""
    for extra in (["--compressed"], []):
        sh("rm", "-f", remote)
        sh("uiautomator", "dump", *extra, remote)
        for _ in range(6):
            xml = sh("exec-out", "cat", remote)
            if "<?xml" in xml and "<hierarchy" in xml:
                break
        if "<?xml" in xml and "<hierarchy" in xml:
            break
        xml = ""
    if "<?xml" not in xml or "<hierarchy" not in xml:
        return False, "dump 失败"
    pkg = ""
    for line in xml.split("><"):
        if 'package="' in line:
            pkg = line.split('package="')[1].split('"')[0]
            break
    p = OUT / f"{name}.xml"
    p.write_text(xml, encoding="utf-8")
    return True, f"{xml.count('<node'):4d} 节点 {len(xml):6d}B pkg={pkg}"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    ok = 0
    for name, intent, prep in SCREENS:
        sh(*intent.split())
        for cmd in prep:
            sh(*cmd.split())
        time.sleep(1.8)
        good, info = dump(name)
        print(f"  {'✓' if good else '✗'} {name:20s} {info}")
        ok += good
    print(f"\n抓到 {ok}/{len(SCREENS)} 个界面 → {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

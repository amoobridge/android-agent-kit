"""navspec 实验：`am start` 是恢复原语，不是导航原语。

实测记录（AVD Android 15，设置 App）：

不 force-stop（任务已存在）：
  am start -a android.settings.SETTINGS        → "Connected devices"  ❌
  am start -a android.settings.WIFI_SETTINGS   → "Android Auto/65.54kB" ❌
  am start -n com.android.settings/.wifi.WifiSettings → "Connected devices" ❌

force-stop 后：
  am start -a android.settings.SETTINGS        → "Settings/Search settings" ✅
  am start -a android.settings.WIFI_SETTINGS   → "T-Mobile/Connected 3G"   ✅
  am start -n com.android.settings/.wifi.WifiSettings → "net/Wi-Fi"       ✅（3/3 可重复）

★ 两种情况下 `am start` 都返回 0、都打印 `Starting: Intent ...`。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
DEV = "emulator-5554"
REMOTE = "/data/local/tmp/_navspec.xml"


def sh(*a):
    return subprocess.run([ADB, "-s", DEV, *a], capture_output=True,
                          timeout=30).stdout.decode("utf-8", "replace")


def landing() -> str:
    """落点 = 前两个可见文本。"""
    sh("shell", "rm", "-f", REMOTE)
    sh("shell", "uiautomator", "dump", "--compressed", REMOTE)
    time.sleep(0.6)
    raw = subprocess.run([ADB, "-s", DEV, "exec-out", "cat", REMOTE],
                         capture_output=True, timeout=20).stdout
    txt = raw.decode("utf-8", "replace")
    out = []
    for part in txt.split('text="')[1:]:
        v = part.split('"')[0]
        if v.strip():
            out.append(v)
        if len(out) >= 2:
            break
    return " / ".join(out) if out else "(empty)"


CASES = [
    ("am start -a android.settings.SETTINGS",
     ["am", "start", "-a", "android.settings.SETTINGS"], "Settings"),
    ("am start -a android.settings.WIFI_SETTINGS",
     ["am", "start", "-a", "android.settings.WIFI_SETTINGS"], "Wi-Fi"),
    ("am start -n com.android.settings/.wifi.WifiSettings",
     ["am", "start", "-n", "com.android.settings/.wifi.WifiSettings"],
     "Wi-Fi"),
]


def main() -> int:
    rows = []
    for label, argv, expect in CASES:
        for forced in (False, True):
            if forced:
                sh("am", "force-stop", "com.android.settings")
                time.sleep(2.0)
            sh(*argv)
            time.sleep(3.0)
            got = landing()
            rows.append({"command": label, "forced_stop": forced,
                         "landed": got, "expected_hint": expect})
            tag = "✅" if expect.lower() in got.lower() else "❌"
            print(f"  [{'force-stop' if forced else 'no-stop  '}] {label}")
            print(f"      → {got}   {tag}")

    f = "data/nav_experiments.json"
    json.dump(rows, open(f, "w"), ensure_ascii=False, indent=2)
    print(f"\n已存证 → {f}")

    no_stop = [r for r in rows if not r["forced_stop"]]
    with_stop = [r for r in rows if r["forced_stop"]]
    print(f"\n★ 不 force-stop：{sum(1 for r in no_stop if r['expected_hint'].lower() in r['landed'].lower())}/{len(no_stop)} 落对")
    print(f"★ force-stop  ：{sum(1 for r in with_stop if r['expected_hint'].lower() in r['landed'].lower())}/{len(with_stop)} 落对")
    return 0


if __name__ == "__main__":
    sys.exit(main())

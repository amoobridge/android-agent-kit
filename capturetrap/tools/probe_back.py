"""navspec 实验 1：KEYCODE_BACK 在各种状态下到底做什么。

候选状态：
  S1 键盘弹起 + 搜索页   → 预期：收起键盘？还是返回？
  S2 子页面（Wi-Fi 设置） → 预期：返回上一级
  S3 顶层设置页          → 预期：回桌面？还是不动？
  S4 有对话框            → 预期：关闭对话框
  S5 键盘弹起 + 子页面    → 最危险：一步做了两件事

判据：每次 BACK 前后记录 (焦点包名/Activity, 键盘状态, 内容签名)。
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
D = ["-s", "emulator-5554"]
REMOTE = "/data/local/tmp/_nav.xml"


def sh(*a):
    """★ encoding 用 errors="replace"——dumpsys 输出含非 UTF-8 字节。

    这是本探针自己的坑：text=True 默认 strict，遇到 0xb5 直接抛
    UnicodeDecodeError 让整个实验崩掉。
    """
    return subprocess.run([ADB, *D, *a], capture_output=True, timeout=30
                          ).stdout.decode("utf-8", "replace")


def state() -> dict:
    out = sh("dumpsys", "window")
    focus = ""
    for ln in out.splitlines():
        if "mCurrentFocus" in ln or "mFocusedApp" in ln:
            focus = ln.strip()
            break
    kb = "mInputShown=true" in sh("dumpsys", "input_method")
    root = cap()
    sig = ""
    if root is not None:
        sig = hashlib.sha256(ET.tostring(root)).hexdigest()[:12]
    return {"focus": focus[:70], "keyboard": kb, "sig": sig}


def cap():
    """二进制读 + 前 200 字节判定。★ 与 probe_swipe.py 一致。

    两个坑都已踩过：
    ① 用 startswith("<hierarchy") 判会恒 False——输出以 <?xml 声明开头
    ② text=True 解码 + 文件被并发覆写时会读到 NUL 填充
    """
    for _ in range(8):
        # ★★ 先删再 dump。uiautomator 是**原地覆写**：读的时候可能拿到
        # 上一份内容，而旧文件同样是合法 XML、前 200 字节判定照样通过
        # → 你读到的是"有效的旧界面"，还以为界面没变。
        sh("shell", "rm", "-f", REMOTE)
        sh("uiautomator", "dump", "--compressed", REMOTE)
        time.sleep(0.3)
        raw = subprocess.run([ADB, *D, "exec-out", "cat", REMOTE],
                             capture_output=True, timeout=20).stdout
        if raw[:200].find(b"<hierarchy") >= 0:
            try:
                return ET.fromstring(raw.decode("utf-8", "replace"))
            except ET.ParseError:
                return None
    return None


def label(root):
    if root is None:
        return "?"
    ts = [n.get("text", "") for n in root.iter("node")
          if n.get("text")]
    return " | ".join(ts[:3])[:60]


def back(n=1):
    for _ in range(n):
        sh("input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.8)


def main() -> int:
    rows = []

    def rec(name, note):
        rows.append({"state": name, "note": note, **state()})
        r = rows[-1]
        print(f"  [{name}] {note}")
        print(f"       focus={r['focus'][:55]}")
        print(f"       keyboard={r['keyboard']}  sig={r['sig']}  "
              f"label={label(cap())[:40]}")

    print("=" * 72)
    print("navspec 实验 1 · KEYCODE_BACK 在各状态下做什么")
    print("=" * 72)

    # ---------- S1 键盘弹起 + 搜索页 ----------
    print("\n--- S1 键盘弹起 + 搜索页 ---")
    sh("am", "start", "-a", "android.settings.APP_SEARCH_SETTINGS")
    time.sleep(2.5)
    sh("input", "tap", "530", "230")
    time.sleep(2.0)
    sh("am", "broadcast", "-a", "com.textin.refapp.SET_TEXT",
       "--es", "text_b64", "bmV0")
    time.sleep(3.0)
    rec("S1_before", "键盘弹起")
    back(1)
    rec("S1_after_1back", "BACK 一次")
    s1_kb_dismissed = not rows[-1]["keyboard"]
    back(1)
    rec("S1_after_2back", "BACK 两次")

    # ---------- S5 键盘弹起 + 子页面 ----------
    print("\n--- S5 键盘弹起 + 子页面（最危险）---")
    sh("am", "start", "-n", "com.android.settings/.wifi.WifiSettings")
    time.sleep(3.0)
    # 在 WifiSettings 里让键盘弹起：点右上角的 + 号或搜索
    sh("input", "tap", "1000", "240")
    time.sleep(2.5)
    kb5 = "mInputShown=true" in sh("dumpsys", "input_method")
    rec("S5_before", f"键盘={kb5}")
    if kb5:
        back(1)
        rec("S5_after_1back", "BACK 一次 —— 是收键盘还是返回？")

    # ---------- S2 子页面 ----------
    print("\n--- S2 子页面（WifiSettings）---")
    sh("am", "start", "-n", "com.android.settings/.wifi.WifiSettings")
    time.sleep(3.0)
    rec("S2_before", "子页面")
    back(1)
    rec("S2_after_1back", "BACK 一次")

    # ---------- S3 顶层设置页 ----------
    print("\n--- S3 顶层设置页 ---")
    sh("input", "keyevent", "KEYCODE_HOME")
    time.sleep(1.5)
    sh("am", "start", "-a", "android.settings.SETTINGS")
    time.sleep(2.5)
    rec("S3_before", "顶层设置页")
    back(1)
    rec("S3_after_1back", "BACK 一次")

    # ---------- S4 对话框 ----------
    print("\n--- S4 对话框（Wi-Fi 长按已存网络）---")
    sh("am", "start", "-n", "com.android.settings/.wifi.WifiSettings")
    time.sleep(3.0)
    sh("input", "swipe", "540", "1800", "540", "900", "400")
    time.sleep(2.0)
    sh("input", "swipe", "540", "1800", "540", "900", "400")
    time.sleep(2.0)
    sh("input", "longpress", "540", "1700")
    time.sleep(2.5)
    rec("S4_before", "长按后")
    back(1)
    rec("S4_after_1back", "BACK 一次")

    with open("data/back_experiments.json", "w") as f:
        import json
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\n已存证 → data/back_experiments.json")
    print(f"\n★ S1 键盘被 BACK 收掉了吗: {s1_kb_dismissed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

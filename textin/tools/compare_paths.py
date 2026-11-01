"""textin · 两条路径的真机对照。

**它测什么**：同一段文本，分别走
  A 路  `adb shell input text <text>`
  B 路  `adb shell am broadcast --es text_b64 <base64>` → 无障碍 ACTION_SET_TEXT
然后把输入框实际内容读回来比对。

**为什么要分开证明两件事**：

    传输（base64）   保证文本原样到达 Bundle
    API（SET_TEXT）  保证文本原样落进输入框

只证后者不证前者等于没证——第一版用 `--es text "a\\`b\\`c"` 直接传，
回读是 `ac`，跟 `input text` 的失败一模一样。那不是 SET_TEXT 的错，
是 `am broadcast --es` **同样经过设备侧 shell**。

base64 字符集 [A-Za-z0-9+/=] 不含 shell 元字符，
所以 text_b64 是"穿过设备 shell 而不被解释"的传输形式。

用法：
    python tools/compare_paths.py              # 全量 19 用例
    python tools/compare_paths.py --json o.json
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
DEV = "emulator-5554"
PKG = "com.textin.refapp"
SEARCH = "android.settings.APP_SEARCH_SETTINGS"
REMOTE = "/data/local/tmp/cmp.xml"
ACTION = "com.textin.refapp.SET_TEXT"

CASES = [
    ("纯 ASCII",       "hello"),
    ("带空格",         "hello world"),
    ("中文",           "你好世界"),
    ("emoji",          "hi😀ok"),
    ("井号",           "a#b"),
    ("分号",           "a;b"),
    ("反引号",         "a`b`c"),
    ("美元",           "a$b"),
    ("单引号",         "a'b"),
    ("双引号",         'a"b'),
    ("竖线",           "a|b"),
    ("与号",           "a&b"),
    ("圆括号",         "a(b)c"),
    ("百分号",         "a%s"),
    ("空格加百分号",   "a b%s"),
    ("反斜杠",         "a\\b"),
    ("星号问号",       "a*b?"),
    ("首尾空格",       " pad "),
    ("长串 200",       "x" * 200),
]


def sh(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run([ADB, "-s", DEV, *args],
                          capture_output=True, text=True, timeout=timeout)


def _dump() -> ET.Element | None:
    for _ in range(8):
        sh("shell", "uiautomator", "dump", "--compressed", REMOTE)
        time.sleep(0.25)
        out = subprocess.run([ADB, "-s", DEV, "exec-out", "cat", REMOTE],
                             capture_output=True, timeout=30)
        if out.stdout[:200].find(b"<hierarchy") >= 0:
            try:
                return ET.fromstring(out.stdout.decode("utf-8", "replace"))
            except ET.ParseError:
                return None
    return None


def field_state() -> tuple[str | None, bool]:
    root = _dump()
    if root is None:
        return None, False
    for n in root.iter("node"):
        if "EditText" in (n.get("class") or ""):
            return (n.get("text") or ""), (n.get("focused") == "true")
    return None, False


def focus_field() -> bool:
    root = _dump()
    if root is None:
        return False
    for n in root.iter("node"):
        if "EditText" in (n.get("class") or ""):
            b = n.get("bounds", "")
            try:
                xs = [int(v) for v in
                      b.replace("][", ",").strip("[]").split(",")]
                cx, cy = (xs[0] + xs[2]) // 2, (xs[1] + xs[3]) // 2
            except (ValueError, IndexError):
                return False
            for _ in range(3):
                sh("shell", "input", "tap", str(cx), str(cy))
                time.sleep(0.5)
                _, focused = field_state()
                if focused:
                    return True
            return False
    return False


def _delete_round() -> None:
    sh("shell", "input keyevent KEYCODE_MOVE_END; "
       + " ".join(["input keyevent KEYCODE_DEL"] * 60))


def establish_baseline(max_rounds: int = 12) -> str:
    prev = None
    for _ in range(max_rounds):
        txt = field_state()[0]
        if txt == prev:
            return txt
        prev = txt
        _delete_round()
        time.sleep(0.3)
    return prev or ""


def clear_until(baseline: str, max_rounds: int = 8) -> str:
    for _ in range(max_rounds):
        txt = field_state()[0]
        if txt == baseline:
            return txt
        _delete_round()
        time.sleep(0.3)
    return field_state()[0] or ""


def show(s: str | None) -> str:
    if s is None:
        return "<无框>"
    return (s.replace("\t", "\\t").replace("\n", "\\n")
             .replace(" ", "␣"))[:24] or "<空>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=str, default="")
    a = ap.parse_args()

    # 0) 确认服务真的绑上了。**没绑上不出具结论**——
    #    第一版就是服务没绑定还发了半天广播，什么也没发生。
    d = sh("shell", "dumpsys", "accessibility").stdout
    if "Bound services:{}" in d or PKG not in d:
        print(f"❌ 无障碍服务未绑定。先执行：")
        print(f"   adb -s {DEV} shell settings put secure "
              f"enabled_accessibility_services {PKG}/.SetTextService")
        print(f"   adb -s {DEV} shell settings put secure accessibility_enabled 1")
        return 2

    sh("shell", "am", "start", "-a", SEARCH)
    time.sleep(1.5)
    if not focus_field():
        print("❌ 无法聚焦输入框——不出具结论。")
        return 2
    baseline = establish_baseline()

    print("=== textin · 两条路径真机对照 ===")
    print(f"服务已绑定 ✅   空态基线 = {show(baseline)!r}\n")
    print(f"{'用例':<12} {'原文':<20} {'A input text':<20} {'B SET_TEXT':<20}")
    print("-" * 76)

    rows = []
    for name, text in CASES:
        if not focus_field():
            print(f"{name:<12} ❌ 焦点丢失，中止")
            return 2
        got = clear_until(baseline)
        if got != baseline:
            print(f"{name:<12} ❌ 清空失败，中止")
            return 2

        # ---- A 路 ----
        subprocess.run([ADB, "-s", DEV, "shell", "input", "text", text],
                       capture_output=True, text=True, timeout=30)
        time.sleep(0.7)
        a_got = field_state()[0]

        # ---- 清场后走 B 路 ----
        if not focus_field():
            return 2
        if clear_until(baseline) != baseline:
            print(f"{name:<12} ❌ 清空失败，中止")
            return 2
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        subprocess.run([ADB, "-s", DEV, "shell", "am", "broadcast",
                        "-a", ACTION, "--es", "text_b64", b64],
                       capture_output=True, text=True, timeout=30)
        time.sleep(1.4)
        b_got = field_state()[0]

        a_ok, b_ok = (a_got == text), (b_got == text)
        print(f"{name:<12} {show(text):<20} "
              f"{('✅ ' if a_ok else '❌ ') + show(a_got):<20} "
              f"{('✅ ' if b_ok else '❌ ') + show(b_got):<20}")
        rows.append({"name": name, "input": text,
                     "a_input_text": a_got, "a_ok": a_ok,
                     "b_set_text": b_got, "b_ok": b_ok})

    print("-" * 76)
    na = sum(1 for r in rows if r["a_ok"])
    nb = sum(1 for r in rows if r["b_ok"])
    print(f"A `input text`   通过 {na}/{len(rows)}")
    print(f"B `SET_TEXT`     通过 {nb}/{len(rows)}")
    print()
    print("★ B 路的文本经 base64 传输，所以它同时证明了：")
    print("    ① base64 能穿过设备侧 shell 而不被解释")
    print("    ② ACTION_SET_TEXT 把 Bundle 里的文本原样落进输入框")
    print("★ 只证②不证①等于没证——`am broadcast --es text` 也过 shell。")

    if a.json:
        Path(a.json).write_text(json.dumps(
            {"baseline": baseline, "rows": rows},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {a.json}")
    return 0 if nb == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

"""textin · `adb shell input text` 真机取证（v4，判定口径修正）。

## 为什么要改判定口径

v1/v2/v3 连续三版都得出「全坏」，但**错的是我的判定，不是设备**：

| 版 | 错在哪 | 假结论 |
|---|---|---|
| v1 | 没聚焦输入框，按键全部落空 | `input text` 100% 坏 |
| v2 | 清空不干净，回读恒为上一轮残留 | 所有输入都坏 |
| v3 | 同上，且没意识到 hint 问题 | 同上 |

**v4 发现的真问题**：这个搜索框的 `text` 属性在**空的时候返回提示文字**
（`text="Search settings"`，package `com.google.android.settings.intelligence`）。
所以「`text == ""` 就是空字段」这个假设是错的——
按它判定，空字段会被当成有内容，输入成功也会被判失败。

**v4 的做法**：不猜 hint，改用**三分判定**——
拿输入前的回读当基线，只比较变化：

    干净      after == text              输入结果与原文完全一致
    部分       after != before 且 text ⊆ after   有东西落进去了，但不全对
    无变化     after == before           什么都没落

用法：
    python tools/probe_input_text.py
    python tools/probe_input_text.py --verbose --json out.json
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
SEARCH = "android.settings.APP_SEARCH_SETTINGS"
REMOTE = "/data/local/tmp/textin.xml"

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
    """一次 adb 调用发 60 个 DEL。"""
    sh("shell", "input keyevent KEYCODE_MOVE_END; "
       + " ".join(["input keyevent KEYCODE_DEL"] * 60))


def establish_baseline(max_rounds: int = 12) -> str:
    """**删到稳定**：连续两轮删除后回读不再变化，即认为是空态。

    ★ 为什么用"稳定"而不是"等于某个已知值"：
    空字段的 `text` 是 hint，而 hint 是什么我们事先不知道（各 ROM 不同）。
    更麻烦的是设置搜索框会**记住上次的查询**，force-stop 也带回来。

    v5 正是死在这：startup 时抓到的 baseline 恰好是上一轮残留的 200 个 x，
    于是"删到等于 baseline"第一轮就通过了——**基线本身是脏的**。
    用"删到不再变化"就不依赖任何初始状态。
    """
    prev = None
    for _ in range(max_rounds):
        txt = field_state()[0]
        if txt == prev:
            return txt
        prev = txt
        _delete_round()
        time.sleep(0.3)
    return prev or ""


def clear_until_baseline(baseline: str, max_rounds: int = 8) -> str:
    """删到回读回到 `baseline`（空态），返回最终回读。"""
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
             .replace(" ", "␣"))[:26] or "<空>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", type=str, default="")
    a = ap.parse_args()

    sh("shell", "am", "start", "-a", SEARCH)
    time.sleep(1.5)
    if not focus_field():
        print("❌ 无法聚焦输入框——不出具结论。")
        return 2

    baseline = establish_baseline()
    print("=== textin · `adb shell input text` 真机取证 ===")
    print("输入框已聚焦（focused=true 已验证）")
    print(f"空态基线（删到稳定后回读）= {show(baseline)!r}")
    print('  ↑ 非空即 hint 被报进 text 属性；基线靠「删到不再变化」确定\n')
    print(f"{'用例':<14} {'原文':<24} {'回读':<24} 判定")
    print("-" * 78)

    results = []
    for name, text in CASES:
        if not focus_field():
            print(f"{name:<14} ❌ 焦点丢失，中止")
            return 2
        got = clear_until_baseline(baseline)
        if got != baseline:
            print(f"{name:<14} ❌ 清空失败（回读={show(got)}），中止")
            return 2

        p = subprocess.run([ADB, "-s", DEV, "shell", "input", "text", text],
                           capture_output=True, text=True, timeout=30)
        time.sleep(0.8)
        after, _ = field_state()

        # 三分判定：不假设空字段长什么样
        if after == text:
            verdict = "✅ 干净"
        elif after != baseline and text in after:
            verdict = "⚠️ 部分"
        elif after == baseline:
            verdict = "❌ 无变化"
        else:
            verdict = "❌ 不符"

        print(f"{name:<14} {show(text):<24} {show(after):<24} {verdict}")
        if a.verbose:
            print(f"          adb rc={p.returncode} "
                  f"stderr={p.stderr.strip()[:70]!r}")
        results.append({"name": name, "input": text, "got": after,
                        "before": baseline, "verdict": verdict,
                        "adb_rc": p.returncode,
                        "adb_stderr": p.stderr.strip()[:150]})

    print("-" * 78)
    n_clean = sum(1 for r in results if r["verdict"].startswith("✅"))
    n_part = sum(1 for r in results if r["verdict"].startswith("⚠️"))
    n_none = sum(1 for r in results if r["verdict"] == "❌ 无变化")
    n_bad = sum(1 for r in results if r["verdict"] == "❌ 不符")
    print(f"干净 {n_clean} · 部分 {n_part} · 无变化 {n_none} · 不符 {n_bad}"
          f"  （共 {len(results)}）\n")
    print("★ 三分判定，不假设空字段的 text 是空串——v3 就错在这。")
    print("★ subprocess 用参数列表、不经本机 shell，失败都来自设备侧。")

    if a.json:
        Path(a.json).write_text(json.dumps(
            {"baseline": baseline, "results": results},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {a.json}")
    return 0 if (n_part + n_none + n_bad) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

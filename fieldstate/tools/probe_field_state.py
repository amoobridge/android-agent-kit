"""fieldstate · 真机勘察：字段状态的可观测面。

**它回答什么**：一个输入框，agent 能从无障碍树里看到什么？
  具体四问：
    Q1 字段为空时，`text` 报什么？（hint 会不会被报成 text）
    Q2 `hint` 属性暴露了吗？
    Q3 `focused` 可靠吗？
    Q4 `textSelectionStart/End` 暴露了吗？

**为什么要单独问**：textin 的 refapp 已经证明 `ACTION_SET_TEXT` 能把文本
原样写进输入框。但"能不能写"之前还有四个判定，它们全世界的 agent 都在
ad-hoc 解决，而其中 Q1 是一个 silent failure：
**字段明明是空的，`text` 却非空**——于是 agent 认为"已经有内容了"，
跳过写入，或者更糟：先清场再写，而清场逻辑基于 `text != ""` 判断有没有内容。

用法：
    python tools/probe_field_state.py            # 扫多个界面
    python tools/probe_field_state.py --json o.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
DEV = "emulator-5554"
REMOTE = "/data/local/tmp/fieldstate.xml"

# 每个界面：名字 + 打开的 intent/命令
SCREENS = [
    ("设置搜索（有 hint）",   ["am", "start", "-a", "android.settings.APP_SEARCH_SETTINGS"]),
    ("设置主页",              ["am", "start", "-a", "android.settings.SETTINGS"]),
    ("WIFI 列表",             ["am", "start", "-a", "android.settings.WIFI_SETTINGS"]),
    ("日期时间",              ["am", "start", "-a", "android.settings.DATE_SETTINGS"]),
    ("显示",                  ["am", "start", "-a", "android.settings.DISPLAY_SETTINGS"]),
]

ATTRS = ["text", "hint", "focused", "focusable", "editable", "enabled",
         "clickable", "long-clickable", "password", "scrollable", "selected",
         "checkable", "checked", "class", "resource-id", "content-desc",
         "text-selection-start", "text-selection-end", "cursor-visible"]


def sh(*a: str, timeout: int = 25) -> subprocess.CompletedProcess:
    return subprocess.run([ADB, "-s", DEV, "shell", *a],
                          capture_output=True, text=True, timeout=timeout)


def dump() -> ET.Element | None:
    for _ in range(8):
        sh("uiautomator", "dump", "--compressed", REMOTE)
        time.sleep(0.25)
        out = subprocess.run([ADB, "-s", DEV, "exec-out", "cat", REMOTE],
                             capture_output=True, timeout=25)
        if out.stdout[:200].find(b"<hierarchy") >= 0:
            try:
                return ET.fromstring(out.stdout.decode("utf-8", "replace"))
            except ET.ParseError:
                return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=str, default="")
    a = ap.parse_args()

    all_screens = []
    for name, cmd in SCREENS:
        sh(*cmd)
        time.sleep(1.6)
        root = dump()
        if root is None:
            print(f"❌ {name}: dump 失败")
            continue

        fields = []
        for n in root.iter("node"):
            cls = n.get("class") or ""
            if "EditText" not in cls:
                continue
            rec = {k: n.get(k) for k in ATTRS}
            rec["bounds"] = n.get("bounds")
            fields.append(rec)

        print(f"\n=== {name} —— {len(fields)} 个 EditText ===")
        for f in fields:
            t = f["text"]
            print(f"  text={t!r}")
            print(f"    hint={f['hint']!r}  focused={f['focused']!r}  "
                  f"focusable={f['focusable']!r}  editable={f['editable']!r}")
            print(f"    text-selection-start={f['text-selection-start']!r}  "
                  f"text-selection-end={f['text-selection-end']!r}  "
                  f"cursor-visible={f['cursor-visible']!r}")
            print(f"    password={f['password']!r}  enabled={f['enabled']!r}  "
                  f"rid={f['resource-id']!r}")
        all_screens.append({"screen": name, "fields": fields})

    # ---- 汇总四问 ----
    print("\n" + "=" * 70)
    print("四问汇总")
    print("=" * 70)

    total = sum(len(s["fields"]) for s in all_screens)
    nonempty_text = sum(1 for s in all_screens for f in s["fields"] if f["text"])
    empty_text = total - nonempty_text
    hint_exposed = sum(1 for s in all_screens for f in s["fields"]
                       if f["hint"] is not None)
    sel_exposed = sum(1 for s in all_screens for f in s["fields"]
                      if f["text-selection-start"] is not None)

    print(f"Q1  字段为空时 text 报什么？")
    print(f"    共 {total} 个 EditText，text 非空 {nonempty_text}，text 为空 {empty_text}")
    print(f"    → text 为空的那 {empty_text} 个，说明『空』确实会报 ''")
    print(f"    → 但 text 非空的 {nonempty_text} 个里，哪些是 hint 报上来的？")
    print(f"       （需要人工看上面的明细——本脚本不下结论）")
    print(f"Q2  hint 属性暴露了吗？    {hint_exposed}/{total}")
    print(f"Q3  focused 属性可用吗？  "
          f"{sum(1 for s in all_screens for f in s['fields'] if f['focused'] is not None)}/{total}")
    print(f"Q4  text-selection-start 暴露了吗？  {sel_exposed}/{total}")

    if a.json:
        out = Path(a.json)
        if not out.is_absolute():
            out = DATA / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"screens": all_screens}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\n已写入 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

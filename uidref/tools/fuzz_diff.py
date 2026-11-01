#!/usr/bin/env python3
"""跨语言差分模糊测试。

为什么需要它：43 条黄金向量是**人工挑的**，16 个真实 dump 是**安卓产的真实形态**。
两者都通过，只能说明"在已知输入上一致"。规范的价值在于**任何人任何语言
实现都得到同一结果**——那需要随机输入上的差分。

做法：随机生成 uiautomator 形态的 XML，同时喂 Python 与 JS 参考实现，
比对结构化输出。任何分歧都是规范歧义的直接证据。

用法::

    python tools/fuzz_diff.py --n 2000 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uidref import parse_xml  # noqa: E402

JS_DIR = ROOT / "js"

CLASSES = [
    "android.view.View", "android.widget.TextView", "android.widget.Button",
    "android.widget.ImageButton", "android.widget.EditText",
    "android.widget.CheckBox", "android.widget.Switch",
    "android.widget.RadioButton", "android.widget.SeekBar",
    "android.widget.LinearLayout", "android.widget.FrameLayout",
    "android.widget.RelativeLayout", "android.widget.ScrollView",
    "android.widget.HorizontalScrollView", "androidx.recyclerview.widget.RecyclerView",
    "android.widget.ListView", "android.widget.GridView",
    "android.webkit.WebView", "androidx.viewpager.widget.ViewPager",
    "com.vendor.CustomThing", "", "weird.pkg.Deeply.Nested.Btn",
]

RIDS = [
    "", "com.android.settings:id/wifi_settings", "android:id/content",
    "com.x:id/content_parent", "android:id/decor_content_parent",
    "android:id/container", "android:id/root", "android:id/main",
    "android:id/frame", "android:id/wrapper", "com.x:id/ok_button",
    "no_slash_at_all", "trailing/slash/",
]

TEXTS = [
    "", "OK", "Wi-Fi", "已连接", "取消", "设置", "a" * 80,
    "带 & 实体", '带 " 引号', "带 < 尖括号", "日本語テキスト", "🙂 emoji",
    " 前后空格 ", "重复", "重复",
]


def _esc(value: str, q: str) -> str:
    """按引号风格转义。不转义就会生成**非法 XML**——
    Python 的严格解析器会报错，而我手写的 JS 解析器会容忍，
    于是每条输入都"分歧"，但那不是规范歧义，是生成器烂。"""
    v = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return v.replace(q, "&quot;" if q == '"' else "&apos;")


def _attr(rng: random.Random, name: str, value: str) -> str:
    q = '"'
    return f"{name}={q}{_esc(value, q)}{q}"


def gen_node(rng: random.Random, depth: int) -> str:
    """随机生成一个 <node>，带随机嵌套。"""
    cls = rng.choice(CLASSES)
    rid = rng.choice(RIDS)
    text = rng.choice(TEXTS)
    desc = rng.choice(TEXTS)
    clickable = rng.choice(["true", "false", "false", "true"])
    scrollable = rng.choice(["true", "false", "false", "false"])
    longclick = rng.choice(["true", "false", "false"])
    enabled = rng.choice(["true", "true", "true", "false"])
    checked = rng.choice(["true", "false", "false"])
    password = rng.choice(["true", "false", "false", "false"])

    # bounds：合法 / 零面积 / 逆序 / 负坐标 / 畸形 / 缺省
    kind = rng.choice(["ok", "ok", "ok", "zero", "reversed", "negative", "garbage", "missing"])
    if kind == "ok":
        x1, y1 = rng.randint(0, 1000), rng.randint(0, 2000)
        x2, y2 = x1 + rng.randint(1, 800), y1 + rng.randint(1, 600)
        bounds = f"[{x1},{y1}][{x2},{y2}]"
    elif kind == "zero":
        bounds = f"[{rng.randint(0,900)},{rng.randint(0,900)}][{rng.randint(0,900)},{rng.randint(0,900)}]"
    elif kind == "reversed":
        x1, y1 = rng.randint(100, 900), rng.randint(100, 900)
        bounds = f"[{x1},{y1}][{rng.randint(0,50)},{rng.randint(0,50)}]"
    elif kind == "negative":
        bounds = f"[-{rng.randint(1,50)},-{rng.randint(1,50)}][{rng.randint(0,200)},{rng.randint(0,200)}]"
    elif kind == "garbage":
        bounds = rng.choice(["", "null", "[0,0]", "garbage", "[a,b][c,d]"])
    else:
        bounds = None

    attrs = [
        _attr(rng, "index", str(rng.randint(0, 40))),
        _attr(rng, "text", text),
        _attr(rng, "resource-id", rid),
        _attr(rng, "class", cls),
        _attr(rng, "package", "com.example"),
        _attr(rng, "content-desc", desc),
        _attr(rng, "checkable", rng.choice(["true", "false"])),
        _attr(rng, "checked", checked),
        _attr(rng, "clickable", clickable),
        _attr(rng, "enabled", enabled),
        _attr(rng, "focusable", rng.choice(["true", "false"])),
        _attr(rng, "focused", rng.choice(["true", "false"])),
        _attr(rng, "scrollable", scrollable),
        _attr(rng, "long-clickable", longclick),
        _attr(rng, "password", password),
        _attr(rng, "selected", rng.choice(["true", "false"])),
    ]
    if bounds is not None:
        attrs.append(_attr(rng, "bounds", bounds))
    rng.shuffle(attrs)

    kids = []
    if depth < 3 and rng.random() < 0.6:
        for _ in range(rng.randint(1, 3)):
            kids.append(gen_node(rng, depth + 1))

    body = " ".join(attrs)
    if kids:
        return f"<node {body}>{''.join(kids)}</node>"
    return f"<node {body}/>"


def gen_doc(rng: random.Random) -> str:
    n = rng.randint(0, 6)
    nodes = "".join(gen_node(rng, 0) for _ in range(n))
    rot = rng.choice(["0", "0", "1", "3"])
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
        f'<hierarchy rotation="{rot}">{nodes}</hierarchy>'
    )


def js_parse(xml: str) -> dict:
    """调 JS 参考实现，返回结构化输出。"""
    script = (
        "const {parse}=require('./uidref.js');"
        "const s=parse(process.argv[1]);"
        "process.stdout.write(JSON.stringify({package:s.package,rotation:s.rotation,"
        "elements:s.elements.map(e=>({ref:e.ref,role:e.role,label:e.label,bounds:e.bounds,"
        "clickable:e.clickable,long_clickable:e.long_clickable,scrollable:e.scrollable,"
        "editable:e.editable,checked:e.checked,disabled:e.disabled,password:e.password}))}));"
    )
    r = subprocess.run(
        ["node", "-e", script, xml], cwd=JS_DIR,
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        return {"__error__": r.stderr.strip().splitlines()[-1] if r.stderr else "unknown"}
    return json.loads(r.stdout)


def py_parse(xml: str) -> dict:
    try:
        s = parse_xml(xml)
    except Exception as e:  # noqa: BLE001
        return {"__error__": f"{type(e).__name__}: {e}"}
    return {
        "package": s.package,
        "rotation": s.rotation,
        "elements": [
            {
                "ref": e.ref, "role": e.role, "label": e.label,
                "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                "clickable": e.clickable, "long_clickable": e.long_clickable,
                "scrollable": e.scrollable, "editable": e.editable,
                "checked": e.checked, "disabled": e.disabled,
                "password": e.password,
            }
            for e in s
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--keep", type=int, default=5, help="最多留几条分歧样本")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    both_err = agree = diverge = 0
    samples = []

    for i in range(args.n):
        xml = gen_doc(rng)
        a, b = py_parse(xml), js_parse(xml)
        if "__error__" in a and "__error__" in b:
            both_err += 1
            continue
        if a == b:
            agree += 1
            continue
        diverge += 1
        if len(samples) < args.keep:
            samples.append((i, xml, a, b))

    print(f"随机输入 {args.n} 条（seed={args.seed}）")
    print(f"  一致            {agree}")
    print(f"  两侧都报错      {both_err}")
    print(f"  分歧            {diverge}")

    for i, xml, a, b in samples:
        print(f"\n── 分歧 #{i} ──")
        print("XML:", xml[:400])
        print("py :", json.dumps(a, ensure_ascii=False)[:400])
        print("js :", json.dumps(b, ensure_ascii=False)[:400])

    if diverge:
        print("\n❌ 存在分歧——每一条都是规范歧义的直接证据，应回写 SPEC")
        return 1
    print("\n✅ 两侧在随机输入上完全一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

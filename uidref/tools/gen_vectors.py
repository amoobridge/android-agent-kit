#!/usr/bin/env python3
"""生成 uidref 黄金向量。

向量是**自包含**的：每个用例内嵌一小段合成 XML，不依赖 dumps/，
这样任何语言的实现都能对着跑。

刻意覆盖容易写错的规则：
  标签继承 / 结构性 id / scrollable 不继承 / 禁用仍给 ref /
  EditText 无需 clickable / 畸形 bounds / ref 编号确定性 / 角色推断

> **2026-10-27 重写。** 旧版有两个 bug 让向量**全盘失效却仍然 34/34 通过**：
>
> 1. `_node()` 把 kwarg 名**直接当 XML 属性名**。调用点为绕开 Python 关键字
>    限制改写的 `cls=` / `desc=` / `rid=` 于是泄漏成字面 XML 属性，
>    而默认的 `class="android.view.View"` / `resource-id=""` 留在原地。
>    → 8 个角色用例实际都在跑 `android.view.View`；
>      "EditText → input" 那条**一个元素都没产出**（View 不算可交互）。
> 2. `_node()` 恒返回**自闭合** `<node .../>`，`_wrap()` 只做拼接。
>    → 所谓"子孙"其实是**兄弟**。
>      `label-inheritance` 四条用例的标签全是空串，一条都没测到继承。
>
> 现在 `_node()` 有属性名翻译表，且支持 children。
> `tests/test_uidref.py::TestVectorsWellFormed` 有元测试守这两个 bug。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uidref import parse_xml

OUT = Path(__file__).resolve().parent.parent / "vectors"

# 友好名 → 真实 XML 属性名。
# Python 的 `class` 是关键字、`resource-id`/`content-desc` 不是合法标识符，
# 所以调用点用短名，在这里统一翻译。**漏翻译 = 属性泄漏 = 向量失效。**
# 注意 ``long_clickable``（下划线）≠ ``long-clickable``（连字符）——
# 写错就是一次静默泄漏（2026-10-27 实际踩到）。
_ELEMENT_KEYS = ("ref", "role", "label", "bounds", "center", "clickable",
                 "long_clickable", "scrollable", "editable", "checked",
                 "disabled", "password")

_ATTR_ALIAS = {
    "cls": "class",
    "desc": "content-desc",
    "rid": "resource-id",
    "long_clickable": "long-clickable",
}

# uiautomator dump 的合法属性全集。元测试用它查泄漏。
_VALID_ATTRS = frozenset({
    "index", "text", "resource-id", "class", "package", "content-desc",
    "checkable", "checked", "clickable", "enabled", "focusable", "focused",
    "scrollable", "long-clickable", "password", "selected", "bounds",
})


def _node(kids=None, **kw) -> str:
    """生成一个 <node>。

    ``kids`` 是内嵌的子节点 XML 字符串列表——**必须是真子孙，不能是兄弟**，
    否则标签继承测不到（旧版 bug #2）。
    用关键字传，是为了避开「位置参数不能出现在关键字参数后」的语法限制。
    """
    d = {
        "index": "0", "text": "", "resource-id": "", "class": "android.view.View",
        "package": "com.example", "content-desc": "", "checkable": "false",
        "checked": "false", "clickable": "false", "enabled": "true",
        "focusable": "false", "focused": "false", "scrollable": "false",
        "long-clickable": "false", "password": "false", "selected": "false",
        "bounds": "[0,0][100,100]",
    }
    for k, v in kw.items():
        real = _ATTR_ALIAS.get(k, k)
        if real not in _VALID_ATTRS:
            # 硬失败，绝不静默。历史上正是「静默多一个属性」让向量全盘失效。
            raise TypeError(
                f"_node() 收到未知属性 {k!r}（映射后 {real!r}）。"
                f"合法属性：{sorted(_VALID_ATTRS)}"
            )
        d[real] = v
    attrs = " ".join(f'{k}="{v}"' for k, v in d.items())
    if kids:
        return f"<node {attrs}>{''.join(kids)}</node>"
    return f"<node {attrs}/>"


def _wrap(*nodes: str, rotation: str = "0") -> str:
    return (
        '<?xml version=\'1.0\' encoding=\'UTF-8\' standalone=\'yes\' ?>'
        f'<hierarchy rotation="{rotation}">{"".join(nodes)}</hierarchy>'
    )


def case(xml: str, why: str) -> dict:
    """跑参考实现，把结果固化成用例。"""
    s = parse_xml(xml)
    return {
        "in": xml,
        "why": why,
        "out": {
            "package": s.package,
            "rotation": s.rotation,
            "elements": [
                {
                    "ref": e.ref,
                    "role": e.role,
                    "label": e.label,
                    "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                    # center 是真正被 tap 的值，必须进向量——否则 §5 的
                    # floor-vs-向零截断歧义在一致性测试里根本没有覆盖面
                    #（2026-10-27 由 verify_impl.py 反向验证暴露）。
                    "center": [e.bounds.cx, e.bounds.cy],
                    "clickable": e.clickable,
                    "long_clickable": e.long_clickable,
                    "scrollable": e.scrollable,
                    "editable": e.editable,
                    "checked": e.checked,
                    "disabled": e.disabled,
                    "password": e.password,
                }
                for e in s
            ],
        },
    }


VECTORS = []

# ---------------------------------------------------------------- 基本判定
VECTORS.append({
    "id": "actionable-detection-001",
    "title": "什么算可交互",
    "why": "ref 的发放范围必须精确：clickable/long-clickable/scrollable/EditText 四种，"
           "其余一律不发。多发会让 digest 变噪声，漏发会让模型点不到。",
    "cases": [
        case(_wrap(_node(clickable="true", text="OK")), "clickable 即发 ref"),
        case(_wrap(_node(long_clickable="true", text="Hold")), "long-clickable 即发 ref"),
        case(_wrap(_node(scrollable="true")), "scrollable 即发 ref"),
        case(_wrap(_node(cls="android.widget.EditText")), "EditText 无需 clickable 也发 ref"),
        case(_wrap(_node(text="只是文字")), "纯 TextView 不发 ref"),
        case(_wrap(_node(cls="android.widget.LinearLayout")), "纯布局不发 ref"),
        case(_wrap(_node(focusable="true", text="可聚焦")), "仅 focusable 不发 ref"),
    ],
})

# ---------------------------------------------------------------- 标签继承
VECTORS.append({
    "id": "label-inheritance-001",
    "title": "标签继承：匿名可点行的文字在子孙上",
    "why": "安卓里可点的行几乎总是匿名 LinearLayout，text/content-desc/resource-id 全空，"
           "文字在子 TextView 上。不继承就得到空标签，模型无法区分行与行。",
    "cases": [
        case(_wrap(_node(
            kids=[_node(cls="android.widget.TextView", text="Wi-Fi"),
                  _node(cls="android.widget.TextView", text="已连接")],
            clickable="true", cls="android.widget.LinearLayout",
            bounds="[0,0][1080,200]",
        )), "clickable 行继承两段子孙文本"),
        case(_wrap(_node(
            kids=[_node(cls="android.widget.TextView", text="Wi-Fi"),
                  _node(cls="android.widget.TextView", text="Wi-Fi")],
            clickable="true", cls="android.widget.LinearLayout",
            bounds="[0,0][1080,200]",
        )), "重复文本去重"),
        case(_wrap(_node(
            kids=[_node(cls="android.widget.TextView", text="整页文字一"),
                  _node(cls="android.widget.TextView", text="整页文字二")],
            scrollable="true", cls="android.widget.ScrollView",
            bounds="[0,0][1080,2000]",
        )), "scrollable 容器**不**继承——它的标签等于整页内容，是噪声"),
        case(_wrap(_node(
            kids=[_node(cls="android.widget.TextView", text=t)
                  for t in ("A", "B", "C", "D", "E")],
            clickable="true", cls="android.widget.LinearLayout",
            bounds="[0,0][1080,200]",
        )), "继承上限 4 段，防爆"),
        case(_wrap(_node(
            kids=[_node(cls="android.widget.TextView", desc="无障碍描述")],
            clickable="true", cls="android.widget.LinearLayout",
            bounds="[0,0][1080,200]",
        )), "子孙缺 text 时回退 content-desc"),
        case(_wrap(_node(
            kids=[_node(cls="android.widget.TextView", text="孙"),
                  _node(kids=[_node(cls="android.widget.TextView", text="深一层")],
                        cls="android.widget.LinearLayout")],
            clickable="true", cls="android.widget.LinearLayout",
            bounds="[0,0][1080,200]",
        )), "隔代也算子孙（不限直接子节点）"),
    ],
})

# ---------------------------------------------------------------- 标签优先级
VECTORS.append({
    "id": "label-priority-001",
    "title": "标签优先级 text > content-desc > resource-id > 继承",
    "why": "四种来源的优先级必须固定，否则同一界面在不同实现下标签不同。",
    "cases": [
        case(_wrap(_node(clickable="true", text="文字", desc="描述",
                         rid="com.x:id/a")), "text 优先于 content-desc"),
        case(_wrap(_node(clickable="true", desc="描述",
                         rid="com.x:id/a")), "无 text 时用 content-desc"),
        case(_wrap(_node(clickable="true",
                         rid="com.android.settings:id/wifi_settings")),
             "无 text/desc 时用 resource-id 最后一段"),
        case(_wrap(_node(clickable="true", rid="android:id/content")),
             "结构性 id 不当标签，回退继承（此处无子孙 → 空）"),
        case(_wrap(_node(clickable="true", rid="com.x:id/content_parent")),
             "content_parent 是结构性 id"),
        case(_wrap(_node(clickable="true", rid="android:id/decor_content_parent")),
             "decor_content_parent 是结构性 id"),
        case(_wrap(_node(clickable="true", rid="android:id/container")),
             "container 是结构性 id"),
    ],
})

# ---------------------------------------------------------------- 状态标志
VECTORS.append({
    "id": "state-flags-001",
    "title": "禁用/选中/密码状态必须显式",
    "why": "enabled=false 的节点仍然要发 ref 并标 disabled——否则模型会反复点一个"
           "死按钮却看不出为什么没反应。",
    "cases": [
        case(_wrap(_node(clickable="true", text="灰的", enabled="false")),
             "禁用仍发 ref 且标 disabled"),
        case(_wrap(_node(clickable="true", text="开的", checkable="true", checked="true")),
             "checked"),
        case(_wrap(_node(cls="android.widget.EditText", password="true")), "password"),
        case(_wrap(_node(clickable="true", text="禁用且选中", enabled="false",
                         checkable="true", checked="true")), "多标志并存"),
    ],
})

# ---------------------------------------------------------------- 角色推断
VECTORS.append({
    "id": "role-inference-001",
    "title": "角色推断",
    "why": "角色决定模型怎么理解这个元素。clickable 的布局类必须是 item——"
           "叫它 box 对模型没有信息量。",
    "cases": [
        case(_wrap(_node(clickable="true", cls="android.widget.Button", text="Btn")),
             "Button → btn"),
        case(_wrap(_node(clickable="true", cls="android.widget.LinearLayout", text="Row")),
             "clickable 布局 → item"),
        case(_wrap(_node(cls="android.widget.EditText")), "EditText → input"),
        case(_wrap(_node(clickable="true", cls="android.widget.CheckBox")),
             "CheckBox → switch"),
        case(_wrap(_node(scrollable="true", cls="android.widget.ScrollView")),
             "ScrollView → scroll"),
        case(_wrap(_node(scrollable="true",
                         cls="androidx.recyclerview.widget.RecyclerView")),
             "RecyclerView → list"),
        case(_wrap(_node(cls="android.widget.SeekBar", clickable="true")), "SeekBar → slider"),
        case(_wrap(_node(clickable="true", cls="android.widget.ImageButton",
                         desc="Up")), "ImageButton → btn"),
        case(_wrap(_node(clickable="true", cls="android.webkit.WebView")), "WebView → webview"),
        case(_wrap(_node(clickable="true", cls="android.widget.RadioButton")), "RadioButton → radio"),
        case(_wrap(_node(clickable="true", cls="android.widget.FrameLayout")),
             "clickable FrameLayout → item"),
    ],
})

# ---------------------------------------------------------------- 边界与鲁棒
VECTORS.append({
    "id": "robustness-001",
    "title": "畸形输入不得崩溃",
    "why": "uiautomator 在界面切换时可能吐出不完整 XML。解析器必须鲁棒，"
           "但也不能把畸形节点静默算成可交互。",
    "cases": [
        case(_wrap(), "空 hierarchy → 0 元素"),
        case(_wrap(_node(clickable="true", text="畸形", bounds="[0,0][0,0]")),
             "零面积 bounds 跳过（点了也没用）"),
        case(_wrap(_node(clickable="true", text="逆序", bounds="[100,100][50,50]")),
             "x2<x1 的 bounds 跳过"),
        case(_wrap(_node(clickable="true", text="负坐标", bounds="[-10,-10][50,50]")),
             "负坐标允许——某些悬浮窗如此"),
        case(_wrap(_node(clickable="true", text="负中心", bounds="[-4,-4][3,3]")),
             "中心为负时 必须 floor：floor(-0.5) = -1，向零截断会得 0"),
        case(_wrap(_node(clickable="true", text="跨零", bounds="[-101,-101][-10,-10]")),
             "和为奇数且为负：floor(-55.5) = -56，向零截断会得 -55"),
        case(_wrap(_node(clickable="true", text="缺 bounds")),
             "缺 bounds 属性不崩溃"),
    ],
})

# ---------------------------------------------------------------- 确定性
VECTORS.append({
    "id": "determinism-001",
    "title": "ref 编号必须确定",
    "why": "同一 XML 必须得到同一组 ref，否则黄金向量无意义、回归测试会假失败。",
    "cases": [
        case(_wrap(
            _node(clickable="true", text="一", bounds="[0,0][100,100]"),
            _node(clickable="true", text="二", bounds="[0,100][100,200]"),
            _node(clickable="true", text="三", bounds="[0,200][100,300]"),
        ), "文档序编号 e1 e2 e3"),
        case(_wrap(_node(
            kids=[_node(clickable="true", text="外层", bounds="[0,0][1080,200]"),
                  _node(clickable="true", text="内层", bounds="[10,10][100,100]")],
            scrollable="true", bounds="[0,0][1080,2000]",
        )), "外层先于内层（深度优先）"),
        case(_wrap(
            _node(clickable="true", text="一", bounds="[0,0][100,100]"),
            _node(clickable="true", text="二", bounds="[0,100][100,200]"),
            _node(clickable="true", text="三", bounds="[0,200][100,300]"),
        ), "同一份 XML 再跑一次，ref 不变"),
    ],
})


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()

    n = 0
    problems = []
    for v in VECTORS:
        # 自检 1：不得有泄漏属性
        for i, c in enumerate(v["cases"]):
            for m in re.finditer(r'<node\b([^>]*)>', c["in"]):
                for a in re.finditer(r'([a-zA-Z_-]+)=', m.group(1)):
                    if a.group(1) not in _VALID_ATTRS:
                        problems.append(f"{v['id']} case#{i} 泄漏属性 {a.group(1)}")
        # 自检 1.5：center 必须等于 floor 取整的 bounds 中心
        for i, c in enumerate(v["cases"]):
            for e in c["out"]["elements"]:
                x1, y1, x2, y2 = e["bounds"]
                want = [(x1 + x2) // 2, (y1 + y2) // 2]
                if e["center"] != want:
                    problems.append(
                        f"{v['id']} case#{i} center={e['center']} != floor 中心 {want}")
        # 自检 2：非空输出
        for i, c in enumerate(v["cases"]):
            _ok_empty = any(k in c["why"] for k in
                            ("0 元素", "跳过", "不发 ref", "纯 ", "仅 ", "空"))
            if not c["out"]["elements"] and not _ok_empty:
                problems.append(f"{v['id']} case#{i} 期望 0 元素但 why 没说：{c['why']}")

        p = OUT / f"{v['id']}.json"
        p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {p.name:34s} {len(v['cases']):3d} cases")
        n += len(v["cases"])

    if problems:
        print("\n!! 生成期自检失败：")
        for x in problems:
            print("   ", x)
        return 1
    print(f"\n共 {len(VECTORS)} 个向量文件，{n} 条用例；生成期自检通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

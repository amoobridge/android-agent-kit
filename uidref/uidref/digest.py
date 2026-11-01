"""uidref · uiautomator XML → Snapshot。

两条硬规则（SPEC §2 / §3）：

1. **可交互元素一个都不能丢**。判定为可交互的节点必须全部拿到 ref。
   宁可 digest 变长，不可静默丢弃。
2. **标签继承**。可交互节点常是匿名 LinearLayout（无 text / 无 id / 无 desc），
   其文字在子孙 TextView 上。此时标签 = 子孙文本拼接。
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from .model import Bounds, Element, Snapshot, is_structural_id, role_of

__all__ = ["parse_xml", "parse_file", "digest_of"]


# ---------------------------------------------------------------- 工具
def _parse_bounds(s: str) -> Bounds | None:
    """``[0,66][147,192]`` → Bounds。畸形返回 None。"""
    try:
        a, b = s.split("][")
        x1, y1 = (int(v) for v in a.lstrip("[").split(","))
        x2, y2 = (int(v) for v in b.rstrip("]").split(","))
    except (ValueError, AttributeError):
        return None
    if x2 < x1 or y2 < y1:
        return None
    return Bounds(x1, y1, x2, y2)


def _t(node: ET.Element, name: str) -> str:
    v = node.get(name)
    return v if v is not None else ""


def _flag(node: ET.Element, name: str) -> bool:
    return _t(node, name) == "true"


def _is_actionable(node: ET.Element) -> bool:
    """可交互 = 可点 / 可长按 / 可滚动 / 可编辑。

    注意 ``enabled == false`` 的节点**仍然算**可交互——它需要被展示出来
    并标 ``disabled``，否则模型会反复尝试点击一个死按钮却不知道为什么。
    """
    if _flag(node, "clickable"):
        return True
    if _flag(node, "long-clickable"):
        return True
    if _flag(node, "scrollable"):
        return True
    if _t(node, "class").rsplit(".", 1)[-1].endswith("EditText"):
        return True
    return False


def _descendant_text(node: ET.Element, cap: int = 4) -> str:
    """拼接子孙文本，去重保序，最多 cap 段。

    uiautomator 的可点行常常是匿名 LinearLayout，文字在子 TextView 上。
    """
    seen: list[str] = []
    for child in node.iter():
        if child is node:
            continue
        txt = (_t(child, "text") or _t(child, "content-desc")).strip()
        if txt and txt not in seen:
            seen.append(txt)
        if len(seen) >= cap:
            break
    return " · ".join(seen)


def _label(node: ET.Element) -> str:
    """SPEC §3 的标签优先级。

    继承（取子孙文本）**只对 clickable 节点生效**。理由：scrollable 容器的
    "标签"等于整页内容，是纯噪声；而 clickable 行常是匿名布局，文字在子孙
    TextView 上，不继承就会得到空标签、模型无法区分这一行和那一行。
    """
    for key in ("text", "content-desc"):
        v = _t(node, key).strip()
        if v:
            return v
    rid = _t(node, "resource-id").strip()
    if rid and not is_structural_id(rid):
        # 取最后一段：com.android.settings:id/wifi_settings -> wifi_settings
        return rid.rsplit("/", 1)[-1]
    if _flag(node, "clickable"):
        return _descendant_text(node)
    return ""


def _snapshot_id(package: str, rotation: int, root_xml: str) -> str:
    h = hashlib.sha256(f"{package}|{rotation}|{root_xml}".encode()).hexdigest()[:12]
    return f"s{h}"


# ---------------------------------------------------------------- 主入口
def parse_xml(xml: str | bytes) -> Snapshot:
    """解析 uiautomator dump 的 XML 文本。"""
    if isinstance(xml, bytes):
        xml = xml.decode("utf-8", "replace")
    root = ET.fromstring(xml)
    return _build(root, xml)


def parse_file(path: str | Path) -> Snapshot:
    p = Path(path)
    return parse_xml(p.read_text(encoding="utf-8"))


def digest_of(xml: str | bytes) -> str:
    """便捷入口：XML → digest 文本。"""
    return parse_xml(xml).digest()


def _build(root: ET.Element, raw: str) -> Snapshot:
    package = ""
    rotation = 0
    width = height = 0
    nodes_total = 0
    elements: list[Element] = []

    # 顶层属性
    try:
        rotation = int(_t(root, "rotation") or 0)
    except ValueError:
        rotation = 0

    # 深度优先遍历，uiautomator 的输出即文档序
    stack: list[tuple[ET.Element, int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        nodes_total += 1
        if not package:
            package = _t(node, "package")

        if _is_actionable(node):
            b = _parse_bounds(_t(node, "bounds"))
            if b is not None and b.width > 0 and b.height > 0:
                cls = _t(node, "class")
                elements.append(
                    Element(
                        ref="",  # 稍后统一编号
                        role=role_of(cls, clickable=_flag(node, "clickable")),
                        label=_label(node),
                        bounds=b,
                        clickable=_flag(node, "clickable"),
                        long_clickable=_flag(node, "long-clickable"),
                        scrollable=_flag(node, "scrollable"),
                        editable=cls.rsplit(".", 1)[-1].endswith("EditText"),
                        checked=_flag(node, "checked"),
                        disabled=_t(node, "enabled") == "false",
                        password=_flag(node, "password"),
                        depth=depth,
                        class_name=cls,
                        resource_id=_t(node, "resource-id"),
                    )
                )
                width = max(width, b.x2)
                height = max(height, b.y2)

        # 逆序压栈，保证弹出顺序 = 文档顺序
        for child in reversed(list(node)):
            stack.append((child, depth + 1))

    # 统一编号 —— 确定性：同 XML 必得同 ref
    numbered = tuple(replace(e, ref=f"e{i}") for i, e in enumerate(elements, start=1))

    return Snapshot(
        snapshot_id=_snapshot_id(package, rotation, raw),
        package=package,
        rotation=rotation,
        width=width,
        height=height,
        elements=numbered,
        nodes_total=nodes_total,
        xml_bytes=len(raw.encode("utf-8")),
    )

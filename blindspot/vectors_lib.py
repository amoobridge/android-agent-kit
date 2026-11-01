"""测试辅助：从节点字典列表构造 <node> 元素。"""
from __future__ import annotations

import xml.etree.ElementTree as ET


def xml_root_from(nodes: list[dict]) -> ET.Element:
    root = ET.Element("hierarchy")
    for n in nodes:
        root.append(ET.Element("node", {k: v for k, v in n.items()
                                        if v is not None}))
    return root

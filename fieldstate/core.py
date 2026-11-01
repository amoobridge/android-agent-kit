"""fieldstate 核心：字段状态模型与四个判定。

**设计原则**：判不出就说判不出，不猜。
XML dump 层对 D1（是否为空）没有可靠判据，本实现返回 `unknown`，
而不是用 `text == ""` 猜一个。**一个会说"我不知道"的库，
比一个给出自信错答案的库有用。**

一致性条件见 SPEC.md §6。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

# XML dump 暴露的 EditText 相关属性（SPEC §1.4 全量清点）
_XML_ATTRS = (
    "text", "resource-id", "class", "package", "content-desc",
    "clickable", "enabled", "focusable", "focused",
    "long-clickable", "password", "selected", "bounds",
)


@dataclass(frozen=True)
class FieldState:
    """一个输入框的可观测状态。"""

    # ---- XML 层可观测 ----
    text: str | None = None
    focused: str | None = None
    focusable: str | None = None
    cls: str | None = None
    enabled: str | None = None
    password: str | None = None
    content_desc: str | None = None
    resource_id: str | None = None
    bounds: str | None = None

    # ---- 无障碍 API 层可观测（XML 不暴露，SPEC §1.4）----
    is_editable: bool | None = None
    is_showing_hint_text: bool | None = None
    text_selection_start: int | None = None
    text_selection_end: int | None = None
    api_is_focused: bool | None = None

    extra: dict[str, Any] = field(default_factory=dict)

    # ---- 便捷判据 ----
    @property
    def is_edit_text_class(self) -> bool:
        """class 名含 EditText。**启发式**，SPEC C3。"""
        return "EditText" in (self.cls or "")

    @property
    def has_newline_in_text(self) -> bool:
        """text 属性值含裸换行符。

        实测空字段显示 hint 时，`uiautomator dump` 的 XML 会在空格处断开，
        于是属性值里出现换行。**这是启发式，规范不推荐**
        （SPEC §7 边界 4：多行框里用户真输入换行时会误判）。
        """
        return "\n" in (self.text or "")


def state_from_xml(node: ET.Element) -> FieldState:
    """从一个 <node> 元素构造 FieldState。"""
    return FieldState(
        text=node.get("text"),
        focused=node.get("focused"),
        focusable=node.get("focusable"),
        cls=node.get("class"),
        enabled=node.get("enabled"),
        password=node.get("password"),
        content_desc=node.get("content-desc"),
        resource_id=node.get("resource-id"),
        bounds=node.get("bounds"),
    )


def state_from_api(d: dict[str, Any]) -> FieldState:
    """从 textin/refapp PROBE_STATE 的 JSON 构造 FieldState（SPEC C7）。"""
    # ★ `focus` 与 `is_focused` 是两个字段，且**不等价**：
    #   focus == "none"  表示"根本没找到焦点输入节点"——这是**更强**的信号，
    #                     此时 refapp 不会去调 isFocused()，所以该字段缺席。
    #   is_focused       表示"找到了节点，它聚焦/没聚焦"。
    # 拿 focus=none 判 unfocused 是正确的；反之只看到 is_focused 缺席
    # 就判 unknown 会丢掉一个本来确定的答案。
    if d.get("focus") == "none":
        focused = "false"
    elif d.get("is_focused") is not None:
        focused = "true" if d["is_focused"] else "false"
    else:
        focused = None

    # ★ 抓到的真 bug（此前 42 条测试全绿）：
    #   `d2_is_focused` 原先优先读 `api_is_focused`（原始布尔），
    #   而本函数已把 `focus == "none"` 归一成 focused="false"。
    #   当后端给出 focus="none" 同时 is_focused=true（脏数据/陈旧快照）时，
    #   原始布尔会覆盖归一结果，把「根本没找到焦点输入节点」报成 focused。
    #
    #   SPEC 注释写的是 focus=none 是**更强**的信号——优先级搞反了。
    #   修法：归一结果存在时，清掉原始布尔，不让它有机会覆盖。
    if focused == "false" and d.get("focus") == "none":
        d = dict(d)
        d.pop("is_focused", None)

    return FieldState(
        text=d.get("text"),
        focused=focused,
        focusable=None,
        cls=None,
        enabled=None,
        password=None,
        content_desc=None,
        resource_id=None,
        bounds=None,
        is_editable=d.get("is_editable"),
        is_showing_hint_text=d.get("is_showing_hint_text"),
        text_selection_start=d.get("text_selection_start"),
        text_selection_end=d.get("text_selection_end"),
        api_is_focused=d.get("is_focused"),
    )


# ----------------------------------------------------------------------
# 四个判定
# ----------------------------------------------------------------------

def d1_is_empty(st: FieldState) -> str:
    """D1 字段是否为空。

    返回 `"empty"` / `"nonempty"` / `"unknown"`。

    ★ 关键：XML 层 **判不出**，返回 `unknown`。
    只有拿到 `is_showing_hint_text` 或 `text_selection_start` 才有答案。

    SPEC C1：不得只用 `text` 为空字符串作判据。
    """
    if st.is_showing_hint_text is not None:
        # API 层：精确
        return "empty" if st.is_showing_hint_text else "nonempty"

    if st.text_selection_start is not None:
        # API 层次选：无光标 = 无内容
        return "empty" if st.text_selection_start < 0 else "nonempty"

    # XML 层：没有判据。
    #
    # `text == ""` 只在"字段无 hint"时成立（SPEC §1.1 第三行）。
    # 空字段有 hint 时 text 非空 → 猜"nonempty" 是错的；
    # 猜"empty" 则在用户真输入了内容时是错的。
    # 两个方向都会错，所以不猜。
    return "unknown"


def d2_is_focused(st: FieldState) -> str:
    """D2 字段是否聚焦。

    SPEC C2：必须用 `focused`，不得用 `focusable`。

    ★ `focused`（归一结果）优先于 `api_is_focused`（原始布尔）。
    前者已经吃过 `focus == "none"` 这个更强的信号；后者没有。
    顺序反了会把「没找到焦点输入节点」报成 focused。
    """
    if st.focused is not None:
        if st.focused == "true":
            return "focused"
        if st.focused == "false":
            return "unfocused"
    if st.api_is_focused is not None:
        return "focused" if st.api_is_focused else "unfocused"
    return "unknown"


def d3_is_writable(st: FieldState) -> str:
    """D3 字段是否可写。

    SPEC C3：必须用 `isEditable()`；XML 层只能用 class 名，且是启发式。
    """
    if st.is_editable is not None:
        return "writable" if st.is_editable else "readonly"
    if st.is_edit_text_class:
        return "writable_heuristic"
    return "readonly_heuristic"


def d4_reliable(st: FieldState) -> bool:
    """D4 判定是否可用。

    清场收敛判据是"回读不再变化"（SPEC C5），它不依赖 D1，
    所以 XML 层也能用——**前提是回读的 text 在清场过程中会变**。
    空字段显示 hint 时，DEL 不会改变 text，于是"不再变化"立即成立，
    判据仍然正确（本来就是空的）。

    SPEC C6：D4 与 D1 是两个问题，不互相替代。
    """
    return st.text is not None


def verdict(st: FieldState) -> dict[str, Any]:
    """给出四个判定 + 每个判定的可靠度标注。"""
    d1 = d1_is_empty(st)
    d2 = d2_is_focused(st)
    d3 = d3_is_writable(st)

    return {
        "d1_is_empty": d1,
        "d1_reliable": d1 != "unknown",
        "d2_is_focused": d2,
        "d2_reliable": d2 != "unknown",
        "d3_is_writable": d3,
        "d3_reliable": not d3.endswith("_heuristic"),
        "d4_clear_verdict_available": d4_reliable(st),
        # 启发式信号（SPEC C1a：只有 XML 时才用，且必须标注）
        "heuristic_newline_in_text": st.has_newline_in_text,
        # 该状态是从哪一层来的
        "layer": "api" if st.is_showing_hint_text is not None else "xml",
    }


def xml_node(text=None, focused=None, focusable=None, cls=None,
             enabled=None, password=None, **kw) -> ET.Element:
    """测试辅助：造一个 <node> 元素。"""
    attrs = {}
    if text is not None:
        attrs["text"] = text
    if focused is not None:
        attrs["focused"] = focused
    if focusable is not None:
        attrs["focusable"] = focusable
    if cls is not None:
        attrs["class"] = cls
    if enabled is not None:
        attrs["enabled"] = enabled
    if password is not None:
        attrs["password"] = password
    attrs.update(kw)
    return ET.Element("node", attrs)

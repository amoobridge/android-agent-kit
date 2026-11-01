"""uidref · 核心类型。

Snapshot 是 uidref 的中心对象：一次 uiautomator dump 的**可交互投影**。
模型看到的是 digest，执行时用 ref 回到 Snapshot 解析出 bounds。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

# 角色表。顺序即优先级，先命中先返回。
_ROLE_BY_CLASS_SUFFIX = (
    ("EditText", "input"),
    ("CheckBox", "switch"),
    ("Switch", "switch"),
    ("ToggleButton", "switch"),
    ("CompoundButton", "switch"),
    ("RadioButton", "radio"),
    ("SeekBar", "slider"),
    ("ProgressBar", "progress"),
    ("Spinner", "spinner"),
    ("RecyclerView", "list"),
    ("ListView", "list"),
    ("AbsListView", "list"),
    ("GridView", "grid"),
    ("ScrollView", "scroll"),
    ("HorizontalScrollView", "scroll"),
    ("ViewPager", "pager"),
    ("TabWidget", "tabs"),
    ("TabLayout", "tabs"),
    ("Button", "btn"),
    ("ImageButton", "btn"),
    ("FloatingActionButton", "btn"),
    ("CheckedTextView", "check"),
    ("WebView", "webview"),
    ("ImageView", "img"),
    ("TextView", "text"),
    ("LinearLayout", "box"),
    ("FrameLayout", "box"),
    ("RelativeLayout", "box"),
    ("ConstraintLayout", "box"),
    ("ViewGroup", "box"),
    ("View", "box"),
)


# 结构性 resource-id：对模型无语义，不该当标签用
_STRUCTURAL_IDS = frozenset({
    "content", "content_parent", "contentPanel", "customPanel", "parentPanel",
    "decor_content_parent", "container", "root", "main", "frame", "wrapper",
    "android:id/content", "android:id/list", "android:id/empty",
})


def is_structural_id(resource_id: str) -> bool:
    """该 resource-id 是否对模型无语义（结构性容器）。"""
    if not resource_id:
        return True
    short = resource_id.rsplit("/", 1)[-1]
    return short in _STRUCTURAL_IDS or resource_id in _STRUCTURAL_IDS


def role_of(class_name: str, *, clickable: bool = False) -> str:
    """由控件类名推断角色。

    取类名最后一段（去掉包名），按后缀匹配。未命中回退 ``box``。

    ``clickable=True`` 且类名是布局类时回退 ``item`` —— 安卓里"可点的行"
    几乎总是匿名 LinearLayout/FrameLayout，叫它 ``box`` 对模型没有信息量。
    """
    simple = class_name.rsplit(".", 1)[-1]
    for suffix, role in _ROLE_BY_CLASS_SUFFIX:
        if simple == suffix or simple.endswith(suffix):
            if role == "box" and clickable:
                return "item"
            return role
    return "item" if clickable else "box"


@dataclass(frozen=True, slots=True)
class Bounds:
    """设备像素矩形。闭开区间 [x1, x2) x [y1, y2)。"""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def cx(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def cy(self) -> int:
        return (self.y1 + self.y2) // 2

    def contains(self, x: int, y: int) -> bool:
        return self.x1 <= x < self.x2 and self.y1 <= y < self.y2

    def __str__(self) -> str:
        return f"[{self.x1},{self.y1}][{self.x2},{self.y2}]"


@dataclass(frozen=True, slots=True)
class Element:
    """一个**可交互**元素。

    Attributes
    ----------
    ref:
        引用名，形如 ``e7``。仅在本 Snapshot 内有效。
    role:
        推断出的角色（``btn`` / ``item`` / ``input`` / ``switch`` / ``list`` ...）。
    label:
        展示给模型的标签。可能来自 text / content-desc / resource-id /
        子孙文本拼接，见 SPEC §3。
    bounds:
        设备像素矩形。
    clickable / long_clickable / scrollable / editable:
        原始标志。
    checked / disabled / password:
        附加状态。
    depth:
        在原始树里的深度，仅用于排查。
    class_name:
        原始类名，便于审计。
    resource_id:
        原始 resource-id（完整形式），便于审计。
    """

    ref: str
    role: str
    label: str
    bounds: Bounds
    clickable: bool
    long_clickable: bool
    scrollable: bool
    editable: bool
    checked: bool
    disabled: bool
    password: bool
    depth: int
    class_name: str
    resource_id: str

    @property
    def flags(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.checked:
            out.append("checked")
        if self.disabled:
            out.append("disabled")
        if self.password:
            out.append("password")
        return tuple(out)

    def line(self) -> str:
        """digest 里的一行。"""
        label = self.label if self.label else f"<{self.role} {self.bounds.width}x{self.bounds.height}>"
        label = label.replace("\n", " ").strip()
        if len(label) > 60:
            label = label[:57] + "..."
        flags = f" ({','.join(self.flags)})" if self.flags else ""
        return f"{self.ref:>4}  {self.role:<6} {label}{flags}  {self.bounds}"


@dataclass(frozen=True, slots=True)
class Snapshot:
    """一次 dump 的可交互投影。

    ``refs`` 只在本次快照内有效。界面一变，旧 ref 一律视为过期，
    必须重新 snapshot，**不得**猜测复用。
    """

    snapshot_id: str
    package: str
    rotation: int
    width: int
    height: int
    elements: tuple[Element, ...] = field(default_factory=tuple)
    # 统计：原始树规模，用于量化压缩比
    nodes_total: int = 0
    xml_bytes: int = 0

    _by_ref: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_ref", {e.ref: e for e in self.elements})

    def __len__(self) -> int:
        return len(self.elements)

    def __iter__(self) -> Iterator[Element]:
        return iter(self.elements)

    def get(self, ref: str) -> Element | None:
        """宽松查询：未知 ref 返回 None。用于检查，不用于执行。"""
        return self._by_ref.get(ref)

    def resolve(self, ref: str) -> Element:
        """严格解析：未知 ref 抛 :class:`StaleRefError`。

        **执行点击前一律用这个。** 界面一变，旧 ref 全部过期；
        此时必须重新 snapshot，**绝不**回退到"最近的活元素"——
        静默点错比报错危险得多。
        """
        e = self._by_ref.get(ref)
        if e is None:
            raise StaleRefError(ref, self.snapshot_id)
        return e

    def digest(self) -> str:
        """渲染给模型看的紧凑文本。"""
        head = (
            f"[{self.snapshot_id}] {self.package} "
            f"{self.width}x{self.height} rot={self.rotation} "
            f"elements={len(self.elements)}"
        )
        return "\n".join([head, *(e.line() for e in self.elements)])

    def metrics(self) -> dict:
        """量化指标。

        ``actionable_recall`` **必须为 1.0**：可交互节点一个都不能丢。
        其余指标用于评估压缩效果与标签质量。
        """
        d = self.digest()
        labeled = sum(1 for e in self.elements if e.label)
        return {
            "snapshot_id": self.snapshot_id,
            "package": self.package,
            "nodes_total": self.nodes_total,
            "elements": len(self.elements),
            "xml_bytes": self.xml_bytes,
            "digest_bytes": len(d),
            "compression": round(self.xml_bytes / len(d), 2) if d else 0.0,
            "est_tokens": len(d) // 4,
            "labeled": labeled,
            "label_coverage": round(labeled / len(self.elements), 4) if self.elements else 0.0,
            "disabled": sum(1 for e in self.elements if e.disabled),
            "editable": sum(1 for e in self.elements if e.editable),
            "scrollable": sum(1 for e in self.elements if e.scrollable),
        }

    def est_tokens(self) -> int:
        """粗略 token 估算：字符数 / 4。仅用于量化，不是精确值。"""
        return len(self.digest()) // 4


class StaleRefError(KeyError):
    """ref 不属于本 Snapshot，或引用的元素已不可用。

    **绝不**回退到"最近的活元素"——静默点击错的东西比报错危险得多。
    """

    def __init__(self, ref: str, snapshot_id: str):
        self.ref = ref
        self.snapshot_id = snapshot_id
        super().__init__(f"ref {ref!r} 不属于快照 {snapshot_id!r}，请重新 snapshot")


__all__ = [
    "Bounds",
    "Element",
    "Snapshot",
    "StaleRefError",
    "is_structural_id",
    "role_of",
]

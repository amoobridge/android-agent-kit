"""uidref · 安卓 UI 元素引用层。

让模型**引用元素**，而不是猜坐标。

    click e14        而不是        click (540, 1200)

digest 把 uiautomator dump 压成模型读得动的紧凑文本，
ref 让模型能精确指回设备像素。
"""

from .digest import digest_of, parse_file, parse_xml
from .model import Bounds, Element, Snapshot, StaleRefError, role_of

__version__ = "0.1.0"

__all__ = [
    "Bounds",
    "Element",
    "Snapshot",
    "StaleRefError",
    "digest_of",
    "parse_file",
    "parse_xml",
    "role_of",
    "__version__",
]

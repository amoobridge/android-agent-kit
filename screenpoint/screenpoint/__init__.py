"""screenpoint — GUI Agent 坐标真值层。

让 agent 的每一次点击，落在它以为落的地方。
"""

from .core import (
    CoordinateSpace,
    FitMode,
    GridKind,
    MappingError,
    Point,
    Rect,
    Size,
)
from .mapping import (
    DevicePixel,
    Transform,
    map_point,
    map_rect,
    scale_transform,
    to_device_pixel,
)

__version__ = "0.1.0"

__all__ = [
    "CoordinateSpace",
    "FitMode",
    "GridKind",
    "MappingError",
    "Point",
    "Rect",
    "Size",
    "DevicePixel",
    "Transform",
    "map_point",
    "map_rect",
    "scale_transform",
    "to_device_pixel",
    "__version__",
]

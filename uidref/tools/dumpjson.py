#!/usr/bin/env python3
"""把 uiautomator XML 转成与 JS 侧完全同构的 JSON，供跨语言差分比对。"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from uidref import parse_file

out = {}
for f in sys.argv[1:]:
    s = parse_file(f)
    out[f] = {
        "package": s.package,
        "rotation": s.rotation,
        "elements": [
            {
                "ref": e.ref, "role": e.role, "label": e.label,
                "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                "center": [e.bounds.cx, e.bounds.cy],
                "clickable": e.clickable, "long_clickable": e.long_clickable,
                "scrollable": e.scrollable, "editable": e.editable,
                "checked": e.checked, "disabled": e.disabled,
                "password": e.password,
            }
            for e in s
        ],
    }
print(json.dumps(out, ensure_ascii=False, indent=1))

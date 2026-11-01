#!/usr/bin/env python3
"""生成 screenpoint 黄金测试向量。

向量是规范的**可执行形式**：任何语言的实现，跑通全部向量即视为一致。
期望值由参考实现计算，并抽人工核算关键项。
"""

from __future__ import annotations

import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from screenpoint import CoordinateSpace, FitMode, Point, map_point, to_device_pixel

OUT = Path(__file__).resolve().parent.parent


def sp(name, w, h):
    return CoordinateSpace.pixel(name, w, h)


def norm(name, w, h, n=1000.0):
    return CoordinateSpace.normalized(name, w, h, grid_n=n)


def build(bid, title, why, src, dst, fit, points, *, to_pixel=False):
    cases = []
    for x, y in points:
        if to_pixel:
            r = to_device_pixel(Point(x, y), src, dst, fit=fit)
            cases.append({
                "in": [x, y],
                "out": [r.x, r.y],
                "clamped": r.clamped,
            })
        else:
            r = map_point(Point(x, y), src, dst, fit=fit)
            cases.append({"in": [x, y], "out": [r.x, r.y]})
    return {
        "id": bid,
        "title": title,
        "why": why,
        "src": describe(src),
        "dst": describe(dst),
        "fit": fit.value,
        "cases": cases,
    }


def describe(s: CoordinateSpace) -> dict:
    d = {"kind": s.kind.value, "width": s.size.width, "height": s.size.height}
    if s.is_normalized:
        d["grid_n"] = s.grid_n
    return d


vectors = []

# ---------------------------------------------------------------- 01 基础缩放
vectors.append(build(
    "stretch-identity-001",
    "相同尺寸：恒等映射",
    "回归基线。尺寸相同时任何模式都必须是恒等，否则库有系统性偏移。",
    sp("device", 1080, 2400), sp("model_view", 1080, 2400), FitMode.STRETCH,
    [(0, 0), (540, 1200), (1079, 2399), (1080, 2400)],
))

vectors.append(build(
    "stretch-half-001",
    "0.5 等比缩小（最常见：为省 token 把截图压一半）",
    "最常见的真实场景。1080x2400 → 540x1200，比例 2.0。",
    sp("model_view", 540, 1200), sp("device", 1080, 2400), FitMode.STRETCH,
    [(0, 0), (270, 600), (540, 1200), (135, 300), (1, 1)],
))

vectors.append(build(
    "stretch-asym-001",
    "两轴不同比例（各向异性）",
    "宽高比改变时 stretch 会失真。此向量锁定数学：x 与 y 用不同系数。",
    sp("model_view", 800, 600), sp("device", 1080, 1920), FitMode.STRETCH,
    [(0, 0), (400, 300), (800, 600), (100, 150)],
))

# ---------------------------------------------------------------- 02 留白与裁切
vectors.append(build(
    "fit-pillarbox-001",
    "Pillarbox：宽屏内容塞进窄屏，左右留白",
    "模型看到的内容居中、两侧有黑边。按比例硬乘会整体右偏——这是 silent failure 之王。",
    sp("model_view", 1080, 1920), sp("device", 1080, 2400), FitMode.FIT,
    [(0, 0), (540, 960), (1080, 1920), (270, 480)],
))

vectors.append(build(
    "fit-letterbox-001",
    "Letterbox：窄屏内容塞进宽屏，上下留白",
    "上下留白场景。offset_y 为负，映射后 y 会落在屏幕外，需钳制。",
    sp("model_view", 1920, 1080), sp("device", 1080, 2400), FitMode.FIT,
    [(0, 0), (960, 540), (1920, 1080), (480, 270)],
))

vectors.append(build(
    "crop-cover-001",
    "Crop：等比放大覆盖，超出裁掉",
    "截图被裁时，模型只能看到中间区域。边缘目标的映射会越界。",
    sp("model_view", 1080, 1080), sp("device", 1080, 2400), FitMode.CROP,
    [(0, 0), (540, 540), (1080, 1080), (270, 270)],
))

# ---------------------------------------------------------------- 03 归一化网格
vectors.append(build(
    "normalized-1000-001",
    "0-1000 归一化网格 → 像素（UI-TARS / Gemini 风格）",
    "模型返回 0-1000 的整数。换算必须是 v/N*W，不是 v/W。",
    norm("model_view", 1080, 2400, 1000), sp("device", 1080, 2400), FitMode.STRETCH,
    [(0, 0), (500, 500), (1000, 1000), (250, 750), (333, 667)],
))

vectors.append(build(
    "normalized-1-001",
    "0-1 归一化坐标 → 像素",
    "另一类模型用 0-1 小数。与 0-1000 只是 grid_n 不同。",
    norm("model_view", 1080, 2400, 1), sp("device", 1080, 2400), FitMode.STRETCH,
    [(0, 0), (0.5, 0.5), (1, 1), (0.25, 0.75)],
))

vectors.append(build(
    "normalized-to-scaled-001",
    "归一化网格 → 缩放后的设备像素（组合场景）",
    "模型既用归一化、截图又缩放。两步换算必须合成一步，避免中间取整。",
    norm("model_view", 1080, 2400, 1000), sp("device", 1440, 3200), FitMode.STRETCH,
    [(0, 0), (500, 500), (1000, 1000)],
))

# ---------------------------------------------------------------- 04 取整与钳制
vectors.append(build(
    "rounding-half-up-001",
    "四舍五入规则（half-up）",
    "唯一取整规则。0.5 必须向上，不能是 banker's rounding。",
    sp("model_view", 3, 3), sp("device", 10, 10), FitMode.STRETCH,
    [(0, 0), (1, 1), (2, 2), (1, 0), (0, 1), (2, 1), (1, 2)],
    to_pixel=True,
))

vectors.append(build(
    "clamp-out-of-range-001",
    "越界必须钳制并上报",
    "模型常返回略超值域的点。静默丢弃比钳制更糟；钳制了不报同样糟。",
    sp("model_view", 1000, 1000), sp("device", 1080, 2400), FitMode.STRETCH,
    [(-50, -50), (1050, 1050), (5000, 5000), (0, 0), (1000, 1000)],
    to_pixel=True,
))

# ---------------------------------------------------------------- 05 真实机型
vectors.append(build(
    "real-device-pixel8-001",
    "真实链路：Pixel 8 截图压到 0.7 喂模型",
    "端到端真实参数。1080x2400 → 756x1680（0.7）。",
    sp("model_view", 756, 1680), sp("device", 1080, 2400), FitMode.STRETCH,
    [(378, 840), (100, 200), (756, 1680), (0, 0)],
))

vectors.append(build(
    "real-device-token-budget-001",
    "真实链路：Anthropic 1568 长边预算",
    "1568 长边是常见视觉 token 预算。1080x2400 → 702x1568。",
    sp("model_view", 702, 1568), sp("device", 1080, 2400), FitMode.STRETCH,
    [(351, 784), (0, 0), (702, 1568)],
))

(OUT / "vectors").mkdir(exist_ok=True)
for v in vectors:
    p = OUT / "vectors" / f"{v['id']}.json"
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {p.name}  ({len(v['cases'])} cases)")

print(f"\n共 {len(vectors)} 个向量文件，{sum(len(v['cases']) for v in vectors)} 条用例")
